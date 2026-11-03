"""Review workflow around the unchanged Phase 4 PDF adapter.

Nothing here alters evidence validation, legal rules or proposal behaviour. Reviewer
events are stored beside each append-only analysis run; they never feed back into it.
"""
import hashlib
import importlib.util
import json
import re
import threading
from pathlib import Path

from src.document_review import review_pdf_contract
from src.evidence import extraction_errors
from src.pdf_ingestion import MAX_BYTES, verify_location
from src.schema import parse_json

from .store import StaleRunError, StorageLimitError, UnsafeStorageError, canonical

ROOT = Path(__file__).resolve().parent.parent
SAMPLES_FILE = Path(__file__).resolve().parent / "samples" / "samples.json"
FIXTURE_MANIFEST = ROOT / "tests" / "fixtures" / "pdf_v1" / "manifest.json"

METADATA_FIELDS = ("id", "invoice_description", "payer_type", "payee_residency",
                   "payee_legal_form", "credit_date", "payment_date")
METHODS = ("baseline", "supplied_extraction", "live_hybrid")
SUPPORTED = "SUPPORTED_FACTUAL_EVIDENCE"
SUGGESTED = "AI_SUGGESTED_REQUIRING_REVIEW"
REJECTED = "REJECTED_BY_SAFETY_GUARD"

# Every stored reviewer event carries this explicit statement of non-effect.
EFFECT = {"changes_automated_findings": False, "releases_statutory_proposal": False,
          "authorizes_tax_treatment_or_withholding": False}
DECISIONS = {
    "QUOTE_CHECK": ("MATCHES_DOCUMENT", "DOES_NOT_MATCH", "UNCLEAR"),
    "INTERPRETATION_REVIEW": ("AGREE", "DISAGREE", "NEEDS_MORE_INFORMATION"),
    "DOCUMENT_CHECK": ("READING_ORDER_AND_COMPLETENESS_CONFIRMED", "ISSUES_FOUND"),
    "CASE_STATUS": ("IN_REVIEW", "ESCALATED_TO_QUALIFIED_TAX_REVIEW", "REVIEW_RECORD_COMPLETE", "REOPENED"),
    "NOTE": (None,),
}
CORRECTIONS = {"personnel_supplied": ("yes", "no", "unknown"),
               "worker_supervisor": ("customer", "vendor", "unknown", "conflicting")}
MAX_NOTE = 4000
MAX_FIELD = 500


class ServiceError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


def digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def pdf_parser():
    spec = importlib.util.find_spec("pypdf")
    if spec is None:
        return dict(available=False, version=None)
    import pypdf
    return dict(available=True, version=pypdf.__version__)


class ReplayClient:
    """Returns a caller-supplied extraction. No network, no model; counted as simulated."""
    configured = True
    model = "SUPPLIED_EXTRACTION_REPLAY_NOT_A_MODEL"

    def __init__(self, extraction):
        self.raw = json.dumps(extraction, ensure_ascii=True)
        self.calls = 0

    def complete(self, record, mode):
        self.calls += 1
        return {"raw_output": self.raw, "returned_model": None, "usage": {}}


def clean_text(value, name, limit=MAX_FIELD, required=False):
    if value is None:
        value = ""
    if not isinstance(value, str):
        raise ServiceError(400, name + " must be text")
    value = value.strip()
    if required and not value:
        raise ServiceError(400, name + " is required")
    if len(value) > limit:
        raise ServiceError(400, "{} must be at most {} characters".format(name, limit))
    if re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", value):
        raise ServiceError(400, name + " contains control characters")
    return value


def clean_metadata(value):
    if not isinstance(value, dict):
        raise ServiceError(400, "Transaction details must be an object")
    unknown = set(value) - set(METADATA_FIELDS)
    if unknown:
        raise ServiceError(400, "Unexpected transaction field: " + sorted(unknown)[0])
    # Blank values are kept: the existing pipeline reports them as invalid input or date review.
    return {name: clean_text(value.get(name), name) for name in METADATA_FIELDS}


def clean_method(method, supplied):
    if method not in METHODS:
        raise ServiceError(400, "Unknown analysis method")
    if method in ("baseline", "live_hybrid"):
        return None
    if isinstance(supplied, str):
        try:
            supplied = parse_json(supplied)
        except (ValueError, TypeError, RecursionError):
            raise ServiceError(400, "Supplied extraction is not valid JSON") from None
    errors = extraction_errors(supplied)
    if errors:
        raise ServiceError(400, "Supplied extraction: " + errors[0])
    return supplied


UNTRUSTED = "Integrity check failed. Stored analysis content is withheld; only diagnostics are returned."


class ReviewService:
    def __init__(self, store, analysis_slots=1, analysis_wait_seconds=20, live=None):
        self.store = store
        self.live = live
        # PDF parsing is CPU and memory heavy; bound how many run at once.
        self.analysis_slots = threading.BoundedSemaphore(analysis_slots)
        self.analysis_wait_seconds = analysis_wait_seconds

    # Analysis --------------------------------------------------------------------
    def _analyse(self, contract_sha, invoice_sha, metadata, method, supplied, live_client=None):
        paths = {}
        for role, sha in (("contract", contract_sha), ("invoice", invoice_sha)):
            if sha is None:
                continue
            state, path = self.store.verify_document(sha)
            if state != "VERIFIED":
                raise ServiceError(409, "Stored {} file is {}; upload it again".format(role, state.lower()))
            paths[role] = path
        client = live_client or (ReplayClient(supplied) if method == "supplied_extraction" else None)
        if not self.analysis_slots.acquire(timeout=self.analysis_wait_seconds):
            raise ServiceError(503, "Another analysis is still running. Try again in a moment.")
        try:
            report = review_pdf_contract(metadata, paths["contract"], paths.get("invoice"),
                                         mode="hybrid" if client else "baseline", client=client)
        finally:
            self.analysis_slots.release()
        for role, sha in (("contract", contract_sha), ("invoice", invoice_sha)):
            if sha is not None and report["documents"][role]["file_sha256"] != sha:
                raise ServiceError(409, "Stored document changed during analysis; upload it again")
        if live_client is not None:
            report['execution'] = dict(live_client.audit)
            report['execution']['pipeline_outcome'] = report['review']['run_status']
            report['execution']['pipeline_error'] = report['text_analysis']['not_run_or_error_reason']
        return report, (client.calls if method == 'supplied_extraction' else 0)

    def _run(self, case, contract_sha, invoice_sha, metadata, method, supplied, actor, reason, changed=None, new_case=False, live_client=None):
        report, simulated = self._analyse(contract_sha, invoice_sha, metadata, method, supplied, live_client)
        payload = dict(method=method, reason=reason, report_status=report["status"],
                       factual_evidence_status=report["review"]["factual_evidence_status"],
                       statutory_proposal="WITHHELD", model_network_calls=report.get("execution", {}).get("model_network_calls", 0),
                       simulated_client_invocations=simulated)
        if "execution" in report:
            payload["execution"] = report["execution"]
        if changed:
            payload["changed_fields"] = changed
        return self.store.add_run(case["id"], contract_sha, invoice_sha, metadata, method, supplied, report,
                                  event=(actor, payload), new_case=case if new_case else None)

    def _document(self, sha, role, required):
        if sha is None and not required:
            return None
        if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{64}", sha):
            raise ServiceError(400, "Choose a {} PDF".format(role))
        if self.store.document(sha) is None:
            raise ServiceError(404, "The {} file was not found; upload it again".format(role))
        return sha

    def upload(self, name, data):
        name = clean_text(name, "File name", 255, required=True)
        if len(data) > MAX_BYTES:
            raise ServiceError(413, "PDF is larger than the 5 MiB limit")
        if not data:
            raise ServiceError(400, "The file is empty")
        if not name.lower().endswith(".pdf") or not data.startswith(b"%PDF-"):
            raise ServiceError(415, "Only PDF files can be reviewed")
        try:
            record = self.store.save_document(name, data)
        except StorageLimitError as exc:
            raise ServiceError(507, str(exc)) from None
        except UnsafeStorageError:
            raise ServiceError(409, "Document storage path is unsafe or unavailable; check the data folder") from None
        return dict(sha256=record["sha256"], name=record["name"], size=record["size"])

    def create_case(self, body, origin="UPLOAD"):
        if not isinstance(body, dict):
            raise ServiceError(400, "Expected a JSON object")
        metadata = clean_metadata(body.get("metadata"))
        title = clean_text(body.get("title"), "Title", 160) or metadata["id"] or "Untitled review"
        contract = self._document(body.get("contract_sha256"), "contract", True)
        invoice = self._document(body.get("invoice_sha256"), "invoice", False)
        method = body.get("method", "baseline")
        supplied = clean_method(method, body.get("supplied_extraction"))
        # Origin is set by server code only; API callers cannot label an upload as a sample.
        case = self.store.prepare_case(metadata["id"] or "UNREFERENCED", title, origin)
        live_client = None
        if method == 'live_hybrid':
            if self.live is None:
                raise ServiceError(403, 'Live inference is disabled; start explicitly with --enable-live')
            live_client = self.live.consume(body)
        self._run(case, contract, invoice, metadata, method, supplied, "system", "Initial analysis", new_case=True,
                  live_client=live_client)
        return self.case_view(case["id"])

    def rerun(self, case_id, body):
        case = self._case(case_id)
        if not isinstance(body, dict):
            raise ServiceError(400, "Expected a JSON object")
        actor = clean_text(body.get("reviewer"), "Reviewer name", 80, required=True)
        reason = clean_text(body.get("reason"), "Reason", MAX_NOTE, required=True)
        existing = self.store.runs(case_id)
        if not existing or self.assess(case, self.store.run(existing[-1]["id"]), self.store.events(case_id))["status"] == "FAILED":
            raise ServiceError(409, "Untrusted or incomplete analysis; create a new case with verified documents and manual details")
        latest = existing[-1]
        metadata = clean_metadata(body.get("metadata"))
        method = body.get("method", 'baseline' if latest['method'] == 'live_hybrid' else latest['method'])
        if method == 'live_hybrid':
            raise ServiceError(400, 'Start a new live review with fresh per-run confirmation; corrections rerun offline')
        supplied = clean_method(method, body.get("supplied_extraction", latest["supplied_extraction"]))
        changed = {name: dict(before=latest["metadata"].get(name), after=metadata[name])
                   for name in METADATA_FIELDS if latest["metadata"].get(name) != metadata[name]}
        if method != latest["method"]:
            changed["method"] = dict(before=latest["method"], after=method)
        if supplied != latest["supplied_extraction"] and method == "supplied_extraction":
            changed["supplied_extraction"] = dict(before="(previous)", after="(replaced)")
        if not changed:
            raise ServiceError(400, "Nothing changed; edit a transaction field before running again")
        self._run(case, latest["contract_sha256"], latest["invoice_sha256"], metadata, method, supplied,
                  actor, reason, changed)
        return self.case_view(case_id)

    # Samples ---------------------------------------------------------------------
    def samples(self):
        data = json.loads(SAMPLES_FILE.read_text(encoding="utf-8"))
        fixture_hashes = {}
        if FIXTURE_MANIFEST.is_file():
            fixture_hashes = {f["file"]: f["sha256"] for f in json.loads(FIXTURE_MANIFEST.read_text())["fixtures"]}
        result = []
        for sample in data["samples"]:
            entry = dict(sample)
            for role in ("contract", "invoice"):
                if role in entry and entry[role + "_sha256"] == "fixture-manifest":
                    entry[role + "_sha256"] = fixture_hashes.get(Path(entry[role]).name)
            if "metadata_file" in entry:
                entry["metadata"] = {k: v for k, v in json.loads((ROOT / entry["metadata_file"]).read_text()).items()
                                     if k in METADATA_FIELDS}
            result.append(entry)
        return result

    def public_samples(self):
        return [dict(id=s["id"], title=s["title"], summary=s["summary"], method=s["method"],
                     has_invoice="invoice" in s, contract_name=Path(s["contract"]).name)
                for s in self.samples()]

    def create_sample_case(self, sample_id):
        sample = next((s for s in self.samples() if s["id"] == sample_id), None)
        if sample is None:
            raise ServiceError(404, "Unknown sample")
        hashes = {}
        for role in ("contract", "invoice"):
            if role not in sample:
                continue
            data = (ROOT / sample[role]).read_bytes()
            if hashlib.sha256(data).hexdigest() != sample[role + "_sha256"]:
                raise ServiceError(409, "Sample file does not match its frozen hash")
            try:
                hashes[role] = self.store.save_document(Path(sample[role]).name, data)["sha256"]
            except StorageLimitError as exc:
                raise ServiceError(507, str(exc)) from None
        body = dict(title=sample["title"], metadata=sample["metadata"],
                    contract_sha256=hashes["contract"], invoice_sha256=hashes.get("invoice"),
                    method=sample["method"], supplied_extraction=sample.get("supplied_extraction"))
        return self.create_case(body, origin="SAMPLE")

    # Reviewer events -----------------------------------------------------------------
    def record_event(self, case_id, body):
        self._case(case_id)
        if not isinstance(body, dict):
            raise ServiceError(400, "Expected a JSON object")
        kind = body.get("kind")
        if not isinstance(kind, str) or kind not in DECISIONS:
            raise ServiceError(400, "Unknown review action")
        actor = clean_text(body.get("reviewer"), "Reviewer name", 80, required=True)
        note = clean_text(body.get("note"), "Note", MAX_NOTE, required=kind == "NOTE")
        decision = body.get("decision")
        if decision not in DECISIONS[kind]:
            raise ServiceError(400, "Choose a valid decision")
        runs = self.store.runs(case_id)
        if not runs:
            raise ServiceError(409, "Case has no completed analysis; create a new case")
        run = self.store.run(runs[-1]["id"])
        if body.get("run_id") not in (None, run["id"]):
            raise ServiceError(409, "This analysis has been superseded; reload the latest run")
        integrity = self.assess(self.store.case(case_id), run, self.store.events(case_id))
        if integrity["status"] == "FAILED":
            raise ServiceError(409, "This case failed an integrity check; no further decisions can be recorded")
        if integrity["status"] == "DOCUMENTS_UNAVAILABLE" and kind in ("QUOTE_CHECK", "DOCUMENT_CHECK"):
            raise ServiceError(409, "The stored PDF failed its integrity check, so it cannot be compared; upload it again in a new case")
        view = build_view(self.store, run)
        target = body.get("target")
        label = None
        if kind == "QUOTE_CHECK":
            card = next((c for c in view["evidence"] if c["key"] == target), None)
            if card is None:
                raise ServiceError(400, "Unknown quotation")
            label = card["quote"]
        elif kind == "INTERPRETATION_REVIEW":
            assertion = next((a for c in view["evidence"] for a in c["assertions"]
                              if a["key"] == target and a["reviewable"]), None)
            if assertion is None:
                raise ServiceError(400, "Unknown evidence assertion")
            label = "{}={}".format(assertion["fact"], assertion["value"])
        elif kind == "DOCUMENT_CHECK":
            if target not in [d["role"] for d in view["documents"]]:
                raise ServiceError(400, "Unknown document")
            label = target
        elif target is not None:
            raise ServiceError(400, "This action has no target")
        payload = dict(decision=decision, note=note, target_label=label, run_sequence=run["sequence"],
                       actor_type="SELF_DECLARED_LOCAL_REVIEWER_NOT_AUTHENTICATED", effect=EFFECT)
        correction = body.get("correction")
        if correction is not None:
            if kind != "INTERPRETATION_REVIEW" or decision != "DISAGREE":
                raise ServiceError(400, "A correction can only accompany a disagreement")
            if assertion["fact"] not in CORRECTIONS or correction not in CORRECTIONS[assertion["fact"]]:
                raise ServiceError(400, "Invalid corrected value for this fact")
            if correction == assertion["value"]:
                raise ServiceError(400, "A correction must differ from the automated value")
            payload["correction"] = dict(fact=assertion["fact"], reviewer_value=correction,
                                         automated_value=assertion["value"],
                                         applied_to_automated_analysis=False)
        try:
            # Re-checked inside the write transaction: a concurrent re-run cannot be missed.
            self.store.append_event(case_id, run["id"], actor, kind, target, payload, expect_latest_run=run["id"])
        except StaleRunError:
            raise ServiceError(409, "This analysis has been superseded; reload the latest run") from None
        return self.case_view(case_id)

    # Views --------------------------------------------------------------------------
    def _case(self, case_id):
        case = self.store.case(case_id) if isinstance(case_id, str) else None
        if case is None:
            raise ServiceError(404, "Case not found")
        return case

    def assess(self, case, run, events, chain=None):
        """Integrity of one stored run. FAILED content must never be presented as a finding."""
        chain = chain or self.store.verify_chain(case["id"])
        anchored = [e["payload"].get("report_sha256") for e in events
                    if e["kind"] == "ANALYSIS_RUN" and e["run_id"] == run["id"]]
        created = next((e["payload"] for e in events if e["kind"] == "CASE_CREATED"), None)
        contexts = [e["payload"].get("context_sha256") for e in events
                    if e["kind"] == "ANALYSIS_RUN" and e["run_id"] == run["id"]]
        checks = dict(
            run_context="MATCHES" if contexts == [run.get("context_sha256")] else "MISSING_OR_MISMATCH",
            stored_json=run.get("stored_json_check", "INVALID"),
            history_payloads="VALID" if all(e.get("payload_valid", True) for e in events) else "INVALID",
            report_row_hash=run.get("row_hash_check", "NOT_CHECKED"),
            history_anchor="MISSING" if not anchored else ("MATCHES" if anchored == [run["report_sha256"]] else "MISMATCH"),
            history_chain=chain["status"],
            case_record="MISSING" if created is None else (
                "MATCHES" if (created.get("title"), created.get("reference"), created.get("origin"))
                == (case["title"], case["reference"], case["origin"]) else "MISMATCH"))
        documents = {}
        for role, sha in (("contract", run["contract_sha256"]), ("invoice", run["invoice_sha256"])):
            if sha is not None:
                documents[role] = self.store.verify_document(sha)[0]
        expected = dict(run_context="MATCHES", stored_json="VALID", history_payloads="VALID", report_row_hash="VERIFIED", history_anchor="MATCHES", history_chain="INTACT", case_record="MATCHES")
        # A failed report anchor already covers its context hash; report it once.
        failed = sorted(k for k, v in checks.items() if v != expected[k]
                        and not (k == "run_context" and checks["history_anchor"] != "MATCHES"))
        if failed:
            status = "FAILED"
        elif any(v != "VERIFIED" for v in documents.values()):
            status = "DOCUMENTS_UNAVAILABLE"
        else:
            status = "VERIFIED"
        return dict(status=status, checks=checks, documents=documents, failed_checks=failed,
                    chain=chain, limitation="Local, unsigned SQLite history: tamper-evident for edits that do not "
                    "recompute every hash; not tamper-proof.")

    def case_view(self, case_id, run_id=None):
        case = self._case(case_id)
        runs = self.store.runs(case_id)
        if not runs:
            raise ServiceError(409, "Case has no completed analysis; create a new case")
        selected = runs[-1]["id"] if run_id is None else run_id
        if selected not in [r["id"] for r in runs]:
            raise ServiceError(404, "Run not found")
        run = self.store.run(selected)
        events = self.store.events(case_id)
        chain = self.store.verify_chain(case_id)
        integrity = self.assess(case, run, events, chain)
        run_list = [dict(id=r["id"], sequence=r["sequence"], created_at=r["created_at"], method=r["method"]) for r in runs]
        if integrity["status"] == "FAILED":
            return untrusted_view(self.store, case, run, events, integrity, run_list, selected == runs[-1]["id"])
        anchor_runs([run], events)
        view = build_view(self.store, run)
        decisions = latest_decisions(events, run["id"])
        for card in view["evidence"]:
            card["quote_decision"] = decisions.get(("QUOTE_CHECK", card["key"]))
            for assertion in card["assertions"]:
                assertion["decision"] = decisions.get(("INTERPRETATION_REVIEW", assertion["key"]))
        for document in view["documents"]:
            document["decision"] = decisions.get(("DOCUMENT_CHECK", document["role"]))
        view.update(case=case, case_status=case_status(events), events=events, integrity=integrity,
                    chain=chain, is_latest=selected == runs[-1]["id"], runs=run_list, progress=progress(view))
        return view

    def list_cases(self):
        items = []
        for case in self.store.cases():
            runs = self.store.runs(case["id"])
            if not runs:
                continue
            events = self.store.events(case["id"])
            run = self.store.run(runs[-1]["id"])
            integrity = self.assess(case, run, events)
            item = dict(
                id=case["id"], reference=case["reference"], title=case["title"], origin=case["origin"],
                created_at=case["created_at"], last_activity=events[-1]["created_at"] if events else case["created_at"],
                run_count=len(runs), method=runs[-1]["method"], status=case_status(events),
                integrity="FAILED" if integrity["status"] == "FAILED" else "VERIFIED",
                integrity_status=integrity["status"], failed_checks=integrity["failed_checks"])
            if integrity["status"] == "FAILED":
                # Fail closed: no finding, evidence or document details from an untrusted run.
                if integrity["checks"]["case_record"] != "MATCHES":
                    item.update(title="Untrusted case record", reference=case["id"], origin="UNTRUSTED")
                item["status"] = "INTEGRITY_FAILED"
                item.update(report_status=None, factual_status=None, documents=[], evidence_counts={},
                            missing_count=0, progress=dict(done=0, total=0))
                items.append(item)
                continue
            view = build_view(self.store, anchor_runs([run], events)[0])
            decisions = latest_decisions(events, run["id"])
            for card in view["evidence"]:
                card["quote_decision"] = decisions.get(("QUOTE_CHECK", card["key"]))
                for assertion in card["assertions"]:
                    assertion["decision"] = decisions.get(("INTERPRETATION_REVIEW", assertion["key"]))
            for document in view["documents"]:
                document["decision"] = decisions.get(("DOCUMENT_CHECK", document["role"]))
            counts = {}
            for card in view["evidence"]:
                counts[card["category"]] = counts.get(card["category"], 0) + 1
            item.update(report_status=view["report_status"], factual_status=view["finding"]["factual_evidence_status"],
                        documents=[dict(role=d["role"], name=d["name"], status=d["status"]) for d in view["documents"]],
                        evidence_counts=counts, missing_count=len(view["missing_information"]),
                        progress=progress(view))
            items.append(item)
        return items

    def export(self, case_id):
        case = self._case(case_id)
        events = self.store.events(case_id)
        chain = self.store.verify_chain(case_id)
        trusted, quarantined = [], []
        for run in self.store.runs(case_id, include_report=True):
            integrity = self.assess(case, run, events, chain)
            run["integrity"] = {k: integrity[k] for k in ("status", "checks", "documents", "failed_checks")}
            (quarantined if integrity["status"] == "FAILED" else trusted).append(run)
        export = dict(schema_version="tds-review-export-v2", case=case, chain=chain, events=events,
                      integrity_status="INTEGRITY_FAILED" if quarantined else "VERIFIED", runs=trusted,
                      statement="Review record only. No tax determination, withholding authorization or statutory proposal release.",
                      checksum_note="content_sha256 covers this file's other content (canonical JSON). It detects "
                                    "accidental change in transit; it is not a signature.")
        if quarantined:
            export["forensic_untrusted"] = dict(
                warning="UNTRUSTED: these stored runs failed integrity checks. Do not rely on any finding below.",
                runs=quarantined)
        if any(r["integrity"]["checks"]["case_record"] != "MATCHES" for r in quarantined):
            export["forensic_untrusted"]["case_record"] = case
            export["case"] = dict(case, title="Untrusted case record", reference=case["id"], origin="UNTRUSTED")
        export["content_sha256"] = hashlib.sha256(canonical(export).encode("utf-8")).hexdigest()
        return export


def untrusted_view(store, case, run, events, integrity, run_list, is_latest):
    """Diagnostics only: identifiers, hash checks and the recorded (unverified) history."""
    documents = []
    for role, state in integrity["documents"].items():
        sha = run["contract_sha256"] if role == "contract" else run["invoice_sha256"]
        record = store.document(sha) or {}
        documents.append(dict(role=role, name=record.get("name"), sha256=sha, integrity=state,
                              file_url=None, pages=[], issues=[], status=None))
    if integrity["checks"]["case_record"] != "MATCHES":
        case = dict(case, title="Untrusted case record", reference=case["id"], origin="UNTRUSTED")
    return dict(case=case, untrusted=True, notice=UNTRUSTED, integrity=integrity,
                forensic=dict(run_id=run["id"], run_sequence=run["sequence"],
                              stored_report_sha256=run["report_sha256"],
                              anchored_report_sha256=[e["payload"].get("report_sha256") for e in events
                                                      if e["kind"] == "ANALYSIS_RUN" and e["run_id"] == run["id"]],
                              chain=integrity["chain"]),
                run=dict(id=run["id"], sequence=run["sequence"], created_at=run["created_at"], method=run["method"],
                         report_integrity="FAILED", metadata=None, supplied_extraction=None,
                         report_sha256=run["report_sha256"]),
                finding=None, evidence=[], missing_information=[], documents=documents,
                report_status=None, manual_field_sources={}, limitations=[],
                case_status="INTEGRITY_FAILED", events=events, events_verified=integrity["chain"]["status"] == "INTACT",
                chain=integrity["chain"], is_latest=is_latest, runs=run_list, progress=dict(done=0, total=0))


def anchor_runs(runs, events):
    """A run is trusted only if its own hash matches AND the chained ANALYSIS_RUN event recorded it."""
    anchors = {e["run_id"]: e["payload"].get("report_sha256") for e in events if e["kind"] == "ANALYSIS_RUN"}
    for run in runs:
        if "report_integrity" in run and anchors.get(run["id"]) != run["report_sha256"]:
            run["report_integrity"] = "NOT_MATCHING_REVIEW_HISTORY"
    return runs


def latest_decisions(events, run_id):
    found = {}
    for event in events:
        if event["run_id"] == run_id and event["kind"] in ("QUOTE_CHECK", "INTERPRETATION_REVIEW", "DOCUMENT_CHECK"):
            found[(event["kind"], event["target"])] = dict(
                decision=event["payload"]["decision"], note=event["payload"].get("note"),
                correction=event["payload"].get("correction"), actor=event["actor"],
                created_at=event["created_at"], event_id=event["id"])
    return found


def case_status(events):
    status = "AWAITING_REVIEW"
    for event in events:
        if event["kind"] == "CASE_STATUS":
            status = event["payload"].get("decision", "INTEGRITY_FAILED")
        elif event["actor"] != "system" and status == "AWAITING_REVIEW":
            status = "IN_REVIEW"
    return "IN_REVIEW" if status == "REOPENED" else status


def progress(view):
    total = done = 0
    for card in view["evidence"]:
        reviewable = [a for a in card["assertions"] if a["reviewable"]]
        total += 1 + len(reviewable)
        done += bool(card.get("quote_decision")) + sum(bool(a.get("decision")) for a in reviewable)
    for document in view["documents"]:
        total += 1
        done += bool(document.get("decision"))
    return dict(done=done, total=total)


def card_category(assertions, text_conflict):
    facts = {a["fact"] for a in assertions}
    statuses = {a["text_status"] for a in assertions}
    if (text_conflict and "worker_supervisor" in facts) or facts == {"contradiction"}:
        return "contradiction"
    if SUGGESTED in statuses:
        return "ai_suggestion"
    if REJECTED in statuses:
        return "rejected"
    if SUPPORTED in statuses:
        return "validated"
    return "unvalidated"


def build_view(store, run):
    """Presentation model. Spans are shown only if the stored file and each location verify."""
    report = run["report"]
    analysis = report["text_analysis"]
    review = report["review"]
    documents = []
    for role, doc in report["documents"].items():
        sha = run["contract_sha256"] if role == "contract" else run["invoice_sha256"]
        integrity, _ = store.verify_document(sha)
        if doc.get("file_sha256") not in (None, sha):
            integrity = "HASH_MISMATCH"
        issues = list(doc["issues"]) + [i for p in doc["pages"] for i in p["issues"]]
        documents.append(dict(
            role=role, name=doc["name"], sha256=sha, status=doc["status"], issues=doc["issues"],
            extractor=doc.get("extractor"), integrity=integrity,
            file_url="/api/documents/{}/file".format(sha) if integrity == "VERIFIED" else None,
            active_content="ACTIVE_CONTENT_NOT_EXECUTED" in issues,
            analysed_for_evidence=role == "contract",
            pages=[dict(page_number=p["page_number"], text=p["text"], status=p["status"], issues=p["issues"],
                        order_check=p["order_check"], layout_text=p.get("alternate_layout_text"))
                   for p in doc["pages"]]))
    contract = report["documents"]["contract"]
    contract_ok = next(d for d in documents if d["role"] == "contract")["integrity"] == "VERIFIED"
    review_items = (analysis.get("evidence_review") or {}).get("items", [])
    text_conflict = (analysis.get("validated_facts") or {}).get("worker_supervisor") == "conflicting"
    cards = {}
    for item in report["evidence_items"]:
        quote = item["quote"]
        card = cards.get(quote)
        if card is None:
            occurrences = []
            for occurrence in item["source_mapping"]["occurrences"]:
                fragments = [dict(page_number=f["page_number"], start=f["start"], end=f["end"], quote=f["quote"],
                                  context=f["context"], verified=contract_ok and verify_location(contract, f))
                             for f in occurrence["fragments"]]
                occurrences.append(dict(cross_page=occurrence["cross_page"], fragments=fragments))
            context = next((c["text"] for r in review_items if r["quote"] == quote
                            for c in r.get("surrounding_context", [])), None)
            card = cards[quote] = dict(
                key="q_" + digest(quote), quote=quote, mapping_status=item["source_mapping"]["status"],
                occurrences=occurrences, sentence_context=context, assertions=[])
        reasons = next((r["review_reasons"] for r in review_items if r["quote"] == quote
                        and r["fact"] == item["fact"] and r["value"] == item["value"]), [])
        card["assertions"].append(dict(
            key="a_" + digest("\0".join([item["fact"], str(item["value"]), quote])),
            fact=item["fact"], value=item["value"], text_status=item["text_interpretation_status"],
            interpretation_status=item["interpretation_status"], review_reasons=reasons,
            may_support_statutory_proposal=item["may_support_statutory_proposal"]))
    evidence = []
    for card in cards.values():
        card["category"] = card_category(card["assertions"], text_conflict)
        primary = any(a["fact"] != "contradiction" for a in card["assertions"])
        for assertion in card["assertions"]:
            # A "cited as contradictory" duplicate of a primary assertion needs no separate decision.
            assertion["reviewable"] = not (primary and assertion["fact"] == "contradiction")
        card["suspended_by_document_review"] = any(
            a["interpretation_status"] == "DOCUMENT_REVIEW_REQUIRED" for a in card["assertions"])
        card["spans_verified"] = bool(card["occurrences"]) and all(
            f["verified"] for o in card["occurrences"] for f in o["fragments"])
        evidence.append(card)
    order = ("contradiction", "validated", "ai_suggestion", "rejected", "unvalidated")
    evidence.sort(key=lambda c: order.index(c["category"]))
    missing = list(dict.fromkeys(
        list(review["validated_facts"].get("missing_facts", [])) + list(analysis.get("missing_information", []))))
    method = run["method"]
    return dict(
        run=dict(id=run["id"], sequence=run["sequence"], created_at=run["created_at"], method=method,
                 metadata=run["metadata"], supplied_extraction=run["supplied_extraction"],
                 report_sha256=run["report_sha256"], report_integrity=run["report_integrity"],
                 model_network_calls=report.get('execution', {}).get('model_network_calls', 0),
                 execution=report.get('execution', {'execution_kind': 'SIMULATED' if method == 'supplied_extraction' else 'OFFLINE'}),
                 simulated_client_invocations=report["api_calls"] if method == "supplied_extraction" else 0),
        report_status=report["status"],
        finding=dict(
            factual_evidence_status=review["factual_evidence_status"], run_status=review["run_status"],
            evidence_review_state=(analysis.get("evidence_review") or {}).get("state"),
            validated_facts=dict(personnel_supplied=review["validated_facts"]["personnel_supplied"],
                                 worker_supervisor=review["validated_facts"]["worker_supervisor"]),
            text_level_facts=dict(personnel_supplied=analysis["validated_facts"]["personnel_supplied"],
                                  worker_supervisor=analysis["validated_facts"]["worker_supervisor"]),
            date_selection=review["date_selection"], proposed_table_item=review["proposed_table_item"],
            statutory_proposal="WITHHELD" if review["proposed_table_item"] is None else "PRESENT",
            human_review_reasons=review["human_review_reasons"],
            validation_failures=review["validation_failures"], document_issues=review["document_issues"],
            legal_sources=review["legal_sources"]),
        documents=documents, evidence=evidence, missing_information=missing,
        manual_field_sources=report["manual_field_sources"], limitations=report["limitations"])

