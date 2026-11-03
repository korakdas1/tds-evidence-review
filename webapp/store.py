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
import stat
import threading
import uuid
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path

from src.schema import parse_json
from src.pdf_ingestion import MAX_BYTES

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


DEFAULT_MAX_STORAGE_BYTES = 512 * 1024 * 1024
DEFAULT_MAX_DOCUMENTS = 2000


class StaleRunError(Exception):
    """A newer analysis run was committed while a decision was being recorded."""


class UnsafeStorageError(Exception):
    """A storage path is not a regular private file/directory."""


class StorageLimitError(Exception):
    """The local document store would exceed its configured quota."""


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


CONTEXT_FIELDS = ("id", "case_id", "sequence", "created_at", "contract_sha256", "invoice_sha256",
                  "metadata_json", "method", "supplied_extraction_json", "report_sha256")


def context_hash(run):
    return hashlib.sha256(canonical({k: run[k] for k in CONTEXT_FIELDS}).encode("utf-8")).hexdigest()


def decoded_object(raw):
    try:
        value = parse_json(raw)
        return (value, True) if isinstance(value, dict) else ({}, False)
    except (ValueError, TypeError, RecursionError):
        return {}, False


class Store:
    def __init__(self, data_dir, max_storage_bytes=DEFAULT_MAX_STORAGE_BYTES, max_documents=DEFAULT_MAX_DOCUMENTS):
        if not hasattr(os, "O_NOFOLLOW") or os.open not in os.supports_dir_fd:
            raise RuntimeError("Secure local document storage requires POSIX no-follow directory operations")
        self.max_storage_bytes = max_storage_bytes
        self.max_documents = max_documents
        self.data_dir = Path(data_dir).resolve()
        self.documents_dir = self.data_dir / "documents"
        if self.documents_dir.is_symlink() or (self.data_dir / "review.sqlite3").is_symlink():
            raise UnsafeStorageError("Storage paths must not be symbolic links")
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
        if self.db_path.is_symlink() or (self.db_path.exists() and not self.db_path.is_file()):
            raise UnsafeStorageError("Database path must be a regular file, not a link")
        db = sqlite3.connect(str(self.db_path), timeout=10)
        if self.db_path.exists():
            os.chmod(self.db_path, 0o600)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        return db

    # Documents -----------------------------------------------------------------
    @contextmanager
    def document_folder(self, digest, create=False):
        """Open both internal directory levels without following links (POSIX local app)."""
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise UnsafeStorageError("Invalid document identity")
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        root = os.open(self.documents_dir, flags)
        try:
            if create:
                try:
                    os.mkdir(digest, 0o700, dir_fd=root)
                except FileExistsError:
                    pass
            folder = os.open(digest, flags, dir_fd=root)
            try:
                yield folder
            finally:
                os.close(folder)
        finally:
            os.close(root)

    @staticmethod
    def _write_document(folder, name, data):
        temporary = ".upload-" + uuid.uuid4().hex
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=folder)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            # Replaces the directory entry, never a symlink target; no predictable .restore path.
            os.replace(temporary, name, src_dir_fd=folder, dst_dir_fd=folder)
        finally:
            try:
                os.unlink(temporary, dir_fd=folder)
            except FileNotFoundError:
                pass

    def save_document(self, name, data):
        digest = hashlib.sha256(data).hexdigest()
        clean = safe_name(name)
        try:
            with self.lock, closing(self.connect()) as db, db:
                db.execute("BEGIN IMMEDIATE")  # Quota and duplicate check serialize across Store instances.
                row = db.execute("SELECT * FROM documents WHERE sha256 = ?", (digest,)).fetchone()
                if row is not None:
                    record = dict(row)
                    self.document_path(record)
                    with self.document_folder(digest, create=True) as folder:
                        self._write_document(folder, record["name"], data)
                    return record
                count, used = db.execute("SELECT COUNT(*), COALESCE(SUM(size), 0) FROM documents").fetchone()
                if count >= self.max_documents or used + len(data) > self.max_storage_bytes:
                    raise StorageLimitError("Local storage limit reached; use a new --data-dir or a higher --max-storage-mb.")
                with self.document_folder(digest, create=True) as folder:
                    self._write_document(folder, clean, data)
                    record = dict(sha256=digest, name=clean, size=len(data),
                                  stored_path=str(Path("documents") / digest / clean), created_at=now())
                    try:
                        db.execute("INSERT INTO documents VALUES (:sha256, :name, :size, :stored_path, :created_at)", record)
                        db.commit()
                    except Exception:
                        os.unlink(clean, dir_fd=folder)
                        raise
                    return record
        except (OSError, ValueError):
            raise UnsafeStorageError("Document storage path is unavailable or unsafe") from None

    def document(self, digest):
        with closing(self.connect()) as db:
            row = db.execute("SELECT * FROM documents WHERE sha256 = ?", (digest,)).fetchone()
        return dict(row) if row else None

    def document_path(self, record):
        expected = Path("documents") / record["sha256"] / record["name"]
        if (Path(record["stored_path"]) != expected or safe_name(record["name"]) != record["name"]
                or not re.fullmatch(r"[0-9a-f]{64}", record["sha256"])):
            raise ValueError("Invalid stored document path")
        path = self.data_dir / expected
        if any(p.is_symlink() for p in (self.documents_dir, path.parent, path)):
            raise ValueError("Stored document links are not allowed")
        return path

    def read_document(self, digest):
        """Return the same bounded, verified bytes that may be served; no verify/read race."""
        record = self.document(digest)
        if record is None:
            return "MISSING", None, None
        try:
            path = self.document_path(record)
            with self.document_folder(digest) as folder:
                fd = os.open(record["name"], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=folder)
                with os.fdopen(fd, "rb") as stream:
                    info = os.fstat(stream.fileno())
                    if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_BYTES or info.st_size != record["size"]:
                        return "HASH_MISMATCH", None, path
                    data = stream.read(MAX_BYTES + 1)
        except (OSError, ValueError, UnsafeStorageError):
            return "MISSING", None, None
        if len(data) != record["size"] or hashlib.sha256(data).hexdigest() != digest:
            return "HASH_MISMATCH", None, path
        return "VERIFIED", data, path

    def verify_document(self, digest):
        state, _, path = self.read_document(digest)
        return state, path

    # Cases, runs and events --------------------------------------------------------
    @staticmethod
    def prepare_case(reference, title, origin):
        return dict(id=uuid.uuid4().hex, reference=reference, title=title, created_at=now(), origin=origin)

    def create_case(self, reference, title, origin):
        case = self.prepare_case(reference, title, origin)
        with self.lock, closing(self.connect()) as db, db:
            db.execute("INSERT INTO cases VALUES (:id, :reference, :title, :created_at, :origin)", case)
        return case

    def add_run(self, case_id, contract_sha, invoice_sha, metadata, method, supplied_extraction, report,
                event=None, new_case=None):
        report_json = json.dumps(report, ensure_ascii=True, sort_keys=True)
        with self.lock, closing(self.connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            if new_case is not None:
                db.execute("INSERT INTO cases VALUES (:id, :reference, :title, :created_at, :origin)", new_case)
                self._insert_event(db, case_id, None, "system", "CASE_CREATED", None,
                                   {k: new_case[k] for k in ("title", "reference", "origin")})
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
            if event is not None:
                actor, payload = event
                payload = dict(payload, run_sequence=sequence, report_sha256=run["report_sha256"],
                               context_sha256=context_hash(run))
                self._insert_event(db, case_id, run["id"], actor, "ANALYSIS_RUN", None, payload)
        return run

    def append_event(self, case_id, run_id, actor, kind, target, payload, expect_latest_run=None):
        payload_json = canonical(payload)
        with self.lock, closing(self.connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")  # Serialise chain appends across processes too.
            if expect_latest_run is not None:
                latest = db.execute("SELECT id FROM runs WHERE case_id = ? ORDER BY sequence DESC LIMIT 1",
                                    (case_id,)).fetchone()
                if latest is None or latest["id"] != expect_latest_run:
                    raise StaleRunError(case_id)
            event_id = self._insert_event(db, case_id, run_id, actor, kind, target, payload)
        return self.event(event_id)

    @staticmethod
    def _insert_event(db, case_id, run_id, actor, kind, target, payload):
        payload_json = canonical(payload)
        last = db.execute("SELECT hash FROM events WHERE case_id = ? ORDER BY id DESC LIMIT 1", (case_id,)).fetchone()
        prev = last["hash"] if last else GENESIS
        created = now()
        digest = event_hash(prev, case_id, run_id, created, actor, kind, target, payload_json)
        cursor = db.execute(
            "INSERT INTO events (case_id, run_id, created_at, actor, kind, target, payload_json, prev_hash, hash) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (case_id, run_id, created, actor, kind, target, payload_json, prev, digest))
        return cursor.lastrowid

    def event(self, event_id):
        with closing(self.connect()) as db:
            row = db.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
        return self._event(row)

    @staticmethod
    def _event(row):
        record = dict(row)
        record["payload"], record["payload_valid"] = decoded_object(record.pop("payload_json"))
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
        record["context_sha256"] = context_hash(record)
        record["metadata"], metadata_ok = decoded_object(record.pop("metadata_json"))
        supplied = record.pop("supplied_extraction_json")
        record["supplied_extraction"], supplied_ok = decoded_object(supplied) if supplied else (None, True)
        record["stored_json_check"] = "VALID" if metadata_ok and supplied_ok else "INVALID"
        if "report_json" in record:
            raw = record.pop("report_json")
            record["row_hash_check"] = record["report_integrity"] = (
                "VERIFIED" if hashlib.sha256(raw.encode("utf-8")).hexdigest() == record["report_sha256"]
                else "HASH_MISMATCH")
            record["report"], report_ok = decoded_object(raw)
            if not report_ok:
                record["stored_json_check"] = "INVALID"
                record["unparsed_report_text"] = raw  # Forensic export only; never rendered as findings.

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
