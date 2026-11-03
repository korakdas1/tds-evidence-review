"""Local, append-only review persistence (SQLite, standard library only).

Rows are never updated or deleted: SQLite triggers abort UPDATE/DELETE on every table.
Review events form a per-case SHA-256 hash chain so local edits are detectable. This is
tamper-evident bookkeeping for a single-user local prototype, not a signed attestation.
"""
import hashlib
import json
import os
import re
import sqlite3
import threading
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

GENESIS = "0" * 64
TABLES = ("documents", "cases", "runs", "events")
SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    sha256 TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    size INTEGER NOT NULL,
    stored_path TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS cases (
    id TEXT PRIMARY KEY,
    reference TEXT NOT NULL,
    title TEXT NOT NULL,
    created_at TEXT NOT NULL,
    origin TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES cases(id),
    sequence INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    contract_sha256 TEXT NOT NULL REFERENCES documents(sha256),
    invoice_sha256 TEXT REFERENCES documents(sha256),
    metadata_json TEXT NOT NULL,
    method TEXT NOT NULL,
    supplied_extraction_json TEXT,
    report_json TEXT NOT NULL,
    report_sha256 TEXT NOT NULL,
    UNIQUE (case_id, sequence)
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id TEXT NOT NULL REFERENCES cases(id),
    run_id TEXT REFERENCES runs(id),
    created_at TEXT NOT NULL,
    actor TEXT NOT NULL,
    kind TEXT NOT NULL,
    target TEXT,
    payload_json TEXT NOT NULL,
    prev_hash TEXT NOT NULL,
    hash TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS events_case ON events(case_id, id);
"""


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"))


def event_hash(prev_hash, case_id, run_id, created_at, actor, kind, target, payload_json):
    body = canonical([prev_hash, case_id, run_id, created_at, actor, kind, target, payload_json])
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def safe_name(name):
    """Basename only, conservative characters, original suffix kept for the parser's check."""
    base = Path(str(name).replace("\\", "/")).name
    stem, dot, suffix = base.rpartition(".")
    if not dot:
        stem, suffix = base, ""
    stem = re.sub(r"[^A-Za-z0-9 _.()-]+", "_", stem).strip(" .") or "document"
    suffix = re.sub(r"[^A-Za-z0-9]+", "", suffix)[:8].lower()
    return stem[:96] + ("." + suffix if suffix else "")


class Store:
    def __init__(self, data_dir):
        self.data_dir = Path(data_dir).resolve()
        self.documents_dir = self.data_dir / "documents"
        self.documents_dir.mkdir(parents=True, exist_ok=True)
        # Uploaded contracts and the review log are private to the current OS user.
        for folder in (self.data_dir, self.documents_dir):
            os.chmod(folder, 0o700)
        self.db_path = self.data_dir / "review.sqlite3"
        self.lock = threading.Lock()
        with closing(self.connect()) as db, db:
            db.executescript(SCHEMA)
            try:
                # One successor per chain link: a second process cannot fork a case history.
                db.execute("CREATE UNIQUE INDEX IF NOT EXISTS events_chain_link ON events(case_id, prev_hash)")
            except sqlite3.IntegrityError:
                pass  # An already-forked legacy database is reported by verify_chain instead.
            for table in TABLES:
                for action in ("UPDATE", "DELETE"):
                    db.execute(
                        "CREATE TRIGGER IF NOT EXISTS {t}_no_{a} BEFORE {a} ON {t} "
                        "BEGIN SELECT RAISE(ABORT, 'append-only review store'); END".format(t=table, a=action.lower()))
        os.chmod(self.db_path, 0o600)

    def connect(self):
        db = sqlite3.connect(str(self.db_path), timeout=10)
        if self.db_path.exists():
            os.chmod(self.db_path, 0o600)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        return db

    # Documents -----------------------------------------------------------------
    def save_document(self, name, data):
        digest = hashlib.sha256(data).hexdigest()
        clean = safe_name(name)
        with self.lock, closing(self.connect()) as db, db:
            row = db.execute("SELECT * FROM documents WHERE sha256 = ?", (digest,)).fetchone()
            if row is not None:
                return dict(row)
            folder = self.documents_dir / digest
            folder.mkdir(mode=0o700, parents=True, exist_ok=True)
            path = folder / clean
            if not path.exists():
                with open(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as stream:
                    stream.write(data)
            record = dict(sha256=digest, name=clean, size=len(data),
                          stored_path=str(path.relative_to(self.data_dir)), created_at=now())
            db.execute("INSERT INTO documents VALUES (:sha256, :name, :size, :stored_path, :created_at)", record)
            return record

    def document(self, digest):
        with closing(self.connect()) as db:
            row = db.execute("SELECT * FROM documents WHERE sha256 = ?", (digest,)).fetchone()
        return dict(row) if row else None

    def document_path(self, record):
        path = (self.data_dir / record["stored_path"]).resolve()
        if self.documents_dir not in path.parents:
            raise ValueError("Stored path escapes the document folder")
        return path

    def verify_document(self, digest):
        """Recompute the stored file hash before any display of saved spans."""
        record = self.document(digest)
        if record is None:
            return "MISSING", None
        try:
            path = self.document_path(record)
            data = path.read_bytes()
        except (OSError, ValueError):
            return "MISSING", None
        return ("VERIFIED" if hashlib.sha256(data).hexdigest() == digest else "HASH_MISMATCH"), path

    # Cases, runs and events --------------------------------------------------------
    def create_case(self, reference, title, origin):
        case = dict(id=uuid.uuid4().hex, reference=reference, title=title, created_at=now(), origin=origin)
        with self.lock, closing(self.connect()) as db, db:
            db.execute("INSERT INTO cases VALUES (:id, :reference, :title, :created_at, :origin)", case)
        return case

    def add_run(self, case_id, contract_sha, invoice_sha, metadata, method, supplied_extraction, report):
        report_json = json.dumps(report, ensure_ascii=True, sort_keys=True)
        with self.lock, closing(self.connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            sequence = db.execute("SELECT COALESCE(MAX(sequence), 0) + 1 FROM runs WHERE case_id = ?",
                                  (case_id,)).fetchone()[0]
            run = dict(id=uuid.uuid4().hex, case_id=case_id, sequence=sequence, created_at=now(),
                       contract_sha256=contract_sha, invoice_sha256=invoice_sha,
                       metadata_json=canonical(metadata), method=method,
                       supplied_extraction_json=canonical(supplied_extraction) if supplied_extraction is not None else None,
                       report_json=report_json,
                       report_sha256=hashlib.sha256(report_json.encode("utf-8")).hexdigest())
            db.execute("INSERT INTO runs VALUES (:id, :case_id, :sequence, :created_at, :contract_sha256, "
                       ":invoice_sha256, :metadata_json, :method, :supplied_extraction_json, :report_json, "
                       ":report_sha256)", run)
        return run

    def append_event(self, case_id, run_id, actor, kind, target, payload):
        payload_json = canonical(payload)
        with self.lock, closing(self.connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")  # Serialise chain appends across processes too.
            last = db.execute("SELECT hash FROM events WHERE case_id = ? ORDER BY id DESC LIMIT 1",
                              (case_id,)).fetchone()
            prev = last["hash"] if last else GENESIS
            created = now()
            digest = event_hash(prev, case_id, run_id, created, actor, kind, target, payload_json)
            cursor = db.execute(
                "INSERT INTO events (case_id, run_id, created_at, actor, kind, target, payload_json, prev_hash, hash) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (case_id, run_id, created, actor, kind, target, payload_json, prev, digest))
            event_id = cursor.lastrowid
        return self.event(event_id)

    def event(self, event_id):
        with closing(self.connect()) as db:
            row = db.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
        return self._event(row)

    @staticmethod
    def _event(row):
        record = dict(row)
        record["payload"] = json.loads(record.pop("payload_json"))
        return record

    def cases(self):
        with closing(self.connect()) as db:
            return [dict(r) for r in db.execute("SELECT * FROM cases ORDER BY created_at DESC, rowid DESC")]

    def case(self, case_id):
        with closing(self.connect()) as db:
            row = db.execute("SELECT * FROM cases WHERE id = ?", (case_id,)).fetchone()
        return dict(row) if row else None

    def runs(self, case_id, include_report=False):
        columns = "*" if include_report else (
            "id, case_id, sequence, created_at, contract_sha256, invoice_sha256, metadata_json, method, "
            "supplied_extraction_json, report_sha256")
        with closing(self.connect()) as db:
            rows = db.execute("SELECT {} FROM runs WHERE case_id = ? ORDER BY sequence".format(columns),
                              (case_id,)).fetchall()
        return [self._run(r) for r in rows]

    def run(self, run_id):
        with closing(self.connect()) as db:
            row = db.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        return self._run(row) if row else None

    @staticmethod
    def _run(row):
        record = dict(row)
        record["metadata"] = json.loads(record.pop("metadata_json"))
        supplied = record.pop("supplied_extraction_json")
        record["supplied_extraction"] = json.loads(supplied) if supplied else None
        if "report_json" in record:
            raw = record.pop("report_json")
            record["report_integrity"] = (
                "VERIFIED" if hashlib.sha256(raw.encode("utf-8")).hexdigest() == record["report_sha256"]
                else "HASH_MISMATCH")
            record["report"] = json.loads(raw)
        return record

    def events(self, case_id):
        with closing(self.connect()) as db:
            rows = db.execute("SELECT * FROM events WHERE case_id = ? ORDER BY id", (case_id,)).fetchall()
        return [self._event(r) for r in rows]

    def verify_chain(self, case_id):
        prev, count = GENESIS, 0
        with closing(self.connect()) as db:
            for row in db.execute("SELECT * FROM events WHERE case_id = ? ORDER BY id", (case_id,)):
                expected = event_hash(prev, row["case_id"], row["run_id"], row["created_at"], row["actor"],
                                      row["kind"], row["target"], row["payload_json"])
                if row["prev_hash"] != prev or row["hash"] != expected:
                    return dict(status="BROKEN", events=count, broken_at=row["id"])
                prev, count = row["hash"], count + 1
        return dict(status="INTACT", events=count, head=prev)
