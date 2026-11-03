"""Phase 5 local review app: workflow, persistence and request-guard tests.

No model, network or subprocess use. Reviewer decisions must never alter the automated
analysis, release a statutory proposal or authorise a tax treatment.
"""
import hashlib
import http.client
import importlib.util
import json
import os
import re
import socket
import stat
import time
import sqlite3
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from webapp.samples.generate_samples import DOCUMENTS, build_pdf
from webapp.server import CSP, App, loopback, make_handler, serve
from webapp.service import EFFECT
from webapp.store import Store

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "webapp" / "samples"
STATIC = ROOT / "webapp" / "static"
HOST = {"Host": "127.0.0.1:8765", "X-TDS-Review": "1"}
HAS_PYPDF = importlib.util.find_spec("pypdf") is not None


class StaticAndSampleTests(unittest.TestCase):
    def test_sample_pdfs_are_deterministic_and_match_manifest(self):
        manifest = json.loads((SAMPLES / "samples.json").read_text())
        pinned = {Path(s[r]).name: s[r + "_sha256"] for s in manifest["samples"]
                  for r in ("contract", "invoice") if r in s and s[r].startswith("webapp/")}
        self.assertEqual(set(pinned), set(DOCUMENTS))
        for name, pages in DOCUMENTS.items():
            data = build_pdf(pages)
            self.assertEqual(data, (SAMPLES / name).read_bytes(), name)
            self.assertEqual(hashlib.sha256(data).hexdigest(), pinned[name])

    def test_frontend_is_offline_and_never_injects_html(self):
        for path in STATIC.rglob("*"):
            if path.suffix not in (".js", ".html", ".css", ".svg"):
                continue
            text = path.read_text(encoding="utf-8")
            with self.subTest(file=path.name):
                self.assertNotIn("innerHTML", text)
                self.assertNotIn("insertAdjacentHTML", text)
                self.assertNotIn("eval(", text)
                urls = set(re.findall(r"https?://[^\s\"'`)]+", text)) - {"http://www.w3.org/2000/svg"}
                self.assertEqual(urls, set(), "frontend must not load remote resources")


@unittest.skipUnless(HAS_PYPDF, "Review app tests require pip install -r requirements-pdf.txt")
class ReviewAppTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.app = App(self.tmp.name, 8765)
        for target in ("urllib.request.build_opener", "urllib.request.urlopen",
                       "socket.create_connection", "subprocess.Popen", "os.system",
                       "src.extraction.OpenRouterClient.complete"):
            guard = patch(target, side_effect=AssertionError("Review app must stay local and offline"))
            mocked = guard.start()
            self.addCleanup(guard.stop)
            self.addCleanup(mocked.assert_not_called)

    def call(self, method, path, body=None, headers=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode()
        response = self.app.handle(method, path, {**HOST, **(headers or {})}, body or b"")
        data = json.loads(response.body) if response.headers["Content-Type"] == "application/json" else response.body
        return response.status, data, response.headers

    def sample(self, name):
        status, view, _ = self.call("POST", "/api/samples/{}/cases".format(name))
        self.assertEqual(status, 201, view)
        return view

    def event(self, view, **body):
        body.setdefault("reviewer", "Test Reviewer")
        return self.call("POST", "/api/cases/{}/events".format(view["case"]["id"]), body)

    # Samples through the unchanged pipeline ---------------------------------------
    def test_samples_show_each_evidence_category_and_always_withhold_proposals(self):
        expected = {"warehouse": ["validated", "validated"], "event-crew": ["validated", "ai_suggestion"],
                    "maintenance": ["contradiction", "contradiction", "validated"], "scanned": []}
        for name, categories in expected.items():
            with self.subTest(sample=name):
                view = self.sample(name)
                self.assertEqual([c["category"] for c in view["evidence"]], categories)
                self.assertIsNone(view["finding"]["proposed_table_item"])
                self.assertEqual(view["finding"]["statutory_proposal"], "WITHHELD")
                self.assertEqual(view["run"]["model_network_calls"], 0)
                for card in view["evidence"]:
                    self.assertTrue(card["spans_verified"])
                    self.assertTrue(all(not a["may_support_statutory_proposal"] for a in card["assertions"]))
        status, cases, _ = self.call("GET", "/api/cases")
        self.assertEqual(len(cases), 4)

    def test_ai_suggestion_is_simulated_replay_and_not_a_validated_fact(self):
        view = self.sample("event-crew")
        self.assertEqual(view["run"]["method"], "supplied_extraction")
        self.assertEqual(view["run"]["simulated_client_invocations"], 1)
        self.assertEqual(view["finding"]["factual_evidence_status"], "INSUFFICIENT_TO_ESTABLISH_CONTROL")
        self.assertEqual(view["finding"]["validated_facts"]["worker_supervisor"], "unknown")
        suggestion = next(c for c in view["evidence"] if c["category"] == "ai_suggestion")
        self.assertIn("EXACT_SOURCE_BUT_INTERPRETATION_NOT_VERIFIED", suggestion["assertions"][0]["review_reasons"])

    def test_document_problems_put_text_facts_on_hold(self):
        view = self.sample("cross-page")
        self.assertEqual(view["report_status"], "NEEDS_DOCUMENT_REVIEW")
        self.assertIn("CROSS_PAGE_EVIDENCE_REQUIRES_VISUAL_REVIEW", view["finding"]["document_issues"])
        self.assertTrue(all(c["suspended_by_document_review"] for c in view["evidence"]))
        self.assertTrue(any(o["cross_page"] for c in view["evidence"] for o in c["occurrences"]))

    # Reviewer decisions have no legal effect ---------------------------------------------
    def test_confirming_quotes_and_readings_never_changes_findings_or_releases_proposal(self):
        view = self.sample("warehouse")
        before = (view["finding"], view["run"]["report_sha256"])
        for card in view["evidence"]:
            status, view, _ = self.event(view, kind="QUOTE_CHECK", target=card["key"], decision="MATCHES_DOCUMENT")
            self.assertEqual(status, 201)
            for assertion in card["assertions"]:
                status, view, _ = self.event(view, kind="INTERPRETATION_REVIEW", target=assertion["key"], decision="AGREE")
                self.assertEqual(status, 201)
        for doc in view["documents"]:
            status, view, _ = self.event(view, kind="DOCUMENT_CHECK", target=doc["role"],
                                         decision="READING_ORDER_AND_COMPLETENESS_CONFIRMED")
        status, view, _ = self.event(view, kind="CASE_STATUS", decision="REVIEW_RECORD_COMPLETE")
        self.assertEqual(view["case_status"], "REVIEW_RECORD_COMPLETE")
        self.assertEqual(view["progress"]["done"], view["progress"]["total"])
        self.assertEqual((view["finding"], view["run"]["report_sha256"]), before)
        self.assertIsNone(view["finding"]["proposed_table_item"])
        for event in view["events"]:
            if event["actor"] != "system":
                self.assertEqual(event["payload"]["effect"], EFFECT)
                self.assertFalse(any(event["payload"]["effect"].values()))

    def test_corrections_are_recorded_beside_unchanged_automated_result(self):
        view = self.sample("warehouse")
        assertion = next(a for c in view["evidence"] for a in c["assertions"] if a["fact"] == "worker_supervisor")
        status, view, _ = self.event(view, kind="INTERPRETATION_REVIEW", target=assertion["key"],
                                     decision="DISAGREE", correction="vendor", note="Clause 6 suggests otherwise")
        self.assertEqual(status, 201)
        stored = next(a for c in view["evidence"] for a in c["assertions"] if a["key"] == assertion["key"])
        self.assertEqual(stored["decision"]["correction"],
                         dict(fact="worker_supervisor", reviewer_value="vendor", automated_value="customer",
                              applied_to_automated_analysis=False))
        self.assertEqual(view["finding"]["validated_facts"]["worker_supervisor"], "customer")

    def test_invalid_review_actions_are_rejected(self):
        view = self.sample("maintenance")
        card = view["evidence"][0]
        duplicate = next(a for a in card["assertions"] if not a["reviewable"])
        primary = next(a for a in card["assertions"] if a["reviewable"])
        cases = [
            dict(kind="CASE_STATUS", decision="APPROVED"),
            dict(kind="CASE_STATUS", decision="TAX_TREATMENT_APPROVED"),
            dict(kind="WITHHOLDING_AUTHORISED", decision="YES"),
            dict(kind="QUOTE_CHECK", target="q_missing", decision="MATCHES_DOCUMENT"),
            dict(kind="INTERPRETATION_REVIEW", target=duplicate["key"], decision="AGREE"),
            dict(kind="INTERPRETATION_REVIEW", target=primary["key"], decision="AGREE", correction="vendor"),
            dict(kind="INTERPRETATION_REVIEW", target=primary["key"], decision="DISAGREE", correction="nobody"),
            dict(kind="INTERPRETATION_REVIEW", target=primary["key"], decision="DISAGREE", correction=primary["value"]),
            dict(kind="DOCUMENT_CHECK", target="invoice", decision="ISSUES_FOUND"),
            dict(kind="NOTE", decision=None, note="  "),
            dict(kind="NOTE", decision=None, note="ok", reviewer=""),
            dict(kind="NOTE", decision=None, note="x" * 4001),
        ]
        for body in cases:
            with self.subTest(body=body):
                status, data, _ = self.event(view, **body)
                self.assertEqual(status, 400, data)
        status, data, _ = self.call("POST", "/api/cases/unknown/events", dict(kind="NOTE", note="x", reviewer="r"))
        self.assertEqual(status, 404)

    def test_rerun_with_corrected_details_keeps_earlier_run_and_supersedes_decisions(self):
        view = self.sample("warehouse")
        first_run = view["run"]["id"]
        self.event(view, kind="QUOTE_CHECK", target=view["evidence"][0]["key"], decision="MATCHES_DOCUMENT")
        case = "/api/cases/{}/runs".format(view["case"]["id"])
        metadata = dict(view["run"]["metadata"])
        status, data, _ = self.call("POST", case, dict(reviewer="R", reason="none", metadata=metadata))
        self.assertEqual(status, 400, "an unchanged rerun is refused")
        metadata["payment_date"] = "2026-03-01"
        status, data, _ = self.call("POST", case, dict(reviewer="R", reason="", metadata=metadata))
        self.assertEqual(status, 400, "a reason is required")
        status, view, _ = self.call("POST", case, dict(reviewer="R", reason="Bank statement date", metadata=metadata))
        self.assertEqual(status, 201)
        self.assertEqual(view["run"]["sequence"], 2)
        self.assertEqual(view["finding"]["date_selection"]["applicable_act"], "Income-tax Act, 1961")
        self.assertIsNone(view["finding"]["proposed_table_item"])
        self.assertIsNone(view["evidence"][0]["quote_decision"])
        run_event = [e for e in view["events"] if e["kind"] == "ANALYSIS_RUN"][-1]
        self.assertEqual(run_event["payload"]["changed_fields"]["payment_date"],
                         dict(before="2026-10-20", after="2026-03-01"))
        status, old, _ = self.call("GET", "/api/cases/{}?run={}".format(view["case"]["id"], first_run))
        self.assertFalse(old["is_latest"])
        self.assertIsNotNone(old["evidence"][0]["quote_decision"])
        status, data, _ = self.event(view, kind="NOTE", note="late", run_id=first_run)
        self.assertEqual(status, 409)

    # Persistence and integrity -------------------------------------------------------------
    def test_store_is_append_only_and_hash_chain_detects_tampering(self):
        view = self.sample("warehouse")
        self.event(view, kind="NOTE", note="first")
        db = sqlite3.connect(str(Path(self.tmp.name) / "review.sqlite3"))
        self.addCleanup(db.close)
        for statement in ("UPDATE events SET actor = 'x'", "DELETE FROM events", "UPDATE runs SET method = 'x'",
                          "DELETE FROM cases", "UPDATE documents SET name = 'x'"):
            with self.subTest(statement=statement), self.assertRaises(sqlite3.DatabaseError):
                db.execute(statement)
        self.assertEqual(self.app.store.verify_chain(view["case"]["id"])["status"], "INTACT")
        db.execute("DROP TRIGGER events_no_update")
        db.execute("UPDATE events SET payload_json = replace(payload_json, 'first', 'edited')")
        db.commit()
        self.assertEqual(self.app.store.verify_chain(view["case"]["id"])["status"], "BROKEN")

    def test_forged_report_with_recomputed_row_hash_is_detected_and_locks_review(self):
        # Phase 5B regression: a run row edited together with its own hash used to show VERIFIED.
        view = self.sample("maintenance")
        db = sqlite3.connect(str(Path(self.tmp.name) / "review.sqlite3"))
        self.addCleanup(db.close)
        db.execute("DROP TRIGGER runs_no_update")
        report = json.loads(db.execute("SELECT report_json FROM runs WHERE id = ?", (view["run"]["id"],)).fetchone()[0])
        report["review"]["factual_evidence_status"] = "EVIDENCE_SUPPORTS_CUSTOMER_DIRECTED_MANPOWER"
        forged = json.dumps(report, ensure_ascii=True, sort_keys=True)
        db.execute("UPDATE runs SET report_json = ?, report_sha256 = ? WHERE id = ?",
                   (forged, hashlib.sha256(forged.encode()).hexdigest(), view["run"]["id"]))
        db.commit()
        status, view, _ = self.call("GET", "/api/cases/" + view["case"]["id"])
        # Phase 6: the API itself fails closed (previously only the UI masked the finding).
        self.assertEqual(view["integrity"]["status"], "FAILED")
        self.assertEqual(view["integrity"]["failed_checks"], ["history_anchor"])
        self.assertIsNone(view["finding"])
        self.assertEqual(self.call("GET", "/api/cases")[1][0]["integrity"], "FAILED")
        status, export, _ = self.call("GET", "/api/cases/{}/export".format(view["case"]["id"]))
        self.assertEqual(export["runs"], [])
        self.assertEqual(export["forensic_untrusted"]["runs"][0]["integrity"]["checks"]["history_anchor"], "MISMATCH")
        status, data, _ = self.event(view, kind="NOTE", note="should be refused")
        self.assertEqual(status, 409)

    def test_broken_history_refuses_new_decisions(self):
        view = self.sample("warehouse")
        db = sqlite3.connect(str(Path(self.tmp.name) / "review.sqlite3"))
        self.addCleanup(db.close)
        db.execute("DROP TRIGGER events_no_update")
        db.execute("UPDATE events SET actor = 'someone else' WHERE kind = 'CASE_CREATED'")
        db.commit()
        status, data, _ = self.event(view, kind="NOTE", note="x")
        self.assertEqual(status, 409)

    def test_chain_cannot_fork_even_from_another_process(self):
        view = self.sample("warehouse")
        event = self.app.store.events(view["case"]["id"])[-1]
        db = sqlite3.connect(str(Path(self.tmp.name) / "review.sqlite3"))
        self.addCleanup(db.close)
        with self.assertRaises(sqlite3.IntegrityError):
            db.execute("INSERT INTO events (case_id, run_id, created_at, actor, kind, target, payload_json, prev_hash, hash) "
                       "VALUES (?, ?, ?, 'x', 'NOTE', NULL, '{}', ?, 'f')",
                       (view["case"]["id"], event["run_id"], event["created_at"], event["prev_hash"]))

    @unittest.skipIf(os.name != "posix", "POSIX permission bits")
    def test_local_data_is_private_to_the_user(self):
        view = self.sample("warehouse")
        store = self.app.store
        self.assertEqual(stat.S_IMODE(os.stat(store.data_dir).st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(os.stat(store.documents_dir).st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(os.stat(store.db_path).st_mode), 0o600)
        path = store.document_path(store.document(view["documents"][0]["sha256"]))
        self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)

    def test_changed_stored_file_hides_spans_and_original(self):
        view = self.sample("warehouse")
        contract = view["documents"][0]
        status, data, headers = self.call("GET", contract["file_url"])
        self.assertEqual((status, headers["Content-Type"]), (200, "application/pdf"))
        path = self.app.store.document_path(self.app.store.document(contract["sha256"]))
        path.write_bytes(path.read_bytes() + b"\n% altered")
        status, view, _ = self.call("GET", "/api/cases/" + view["case"]["id"])
        self.assertEqual(view["documents"][0]["integrity"], "HASH_MISMATCH")
        self.assertIsNone(view["documents"][0]["file_url"])
        self.assertTrue(all(not c["spans_verified"] for c in view["evidence"]))
        status, data, _ = self.call("GET", "/api/documents/{}/file".format(contract["sha256"]))
        self.assertEqual(status, 409)

    def test_uploads_and_case_creation_validate_input(self):
        pdf = (SAMPLES / "warehouse_agreement.pdf").read_bytes()
        headers = {"Content-Type": "application/pdf", "X-Filename": "..%2F..%2Fevil%20name.pdf"}
        status, doc, _ = self.call("POST", "/api/documents", pdf, headers)
        self.assertEqual(status, 201)
        self.assertEqual(doc["name"], "evil name.pdf")
        stored = self.app.store.document_path(self.app.store.document(doc["sha256"]))
        self.assertIn(self.app.store.documents_dir, stored.parents)
        for body, extra, code in ((b"hello", {"X-Filename": "a.pdf"}, 415), (pdf, {"X-Filename": "a.txt"}, 415),
                                  (b"", {"X-Filename": "a.pdf"}, 400), (b"%PDF-" + b"0" * (5 * 1024 * 1024), {"X-Filename": "a.pdf"}, 413)):
            status, data, _ = self.call("POST", "/api/documents", body, {"Content-Type": "application/pdf", **extra})
            self.assertEqual(status, code, data)
        meta = json.loads((ROOT / "tests/fixtures/pdf_v1/transaction.json").read_text())
        meta = {k: v for k, v in meta.items() if k != "id"} | {"id": "T-1"}
        bad = [dict(metadata=meta, contract_sha256="0" * 64),
               dict(metadata={**meta, "contract_excerpt": "Customer supervises each worker."}, contract_sha256=doc["sha256"]),
               dict(metadata=meta, contract_sha256=doc["sha256"], method="live-llm"),
               dict(metadata=meta, contract_sha256=doc["sha256"], method="supplied_extraction", supplied_extraction="{"),
               dict(metadata=meta, contract_sha256=doc["sha256"], method="supplied_extraction", supplied_extraction={"x": 1})]
        for body in bad:
            with self.subTest(body=list(body)):
                status, data, _ = self.call("POST", "/api/cases", body)
                self.assertIn(status, (400, 404), data)
        status, view, _ = self.call("POST", "/api/cases", dict(metadata=meta, contract_sha256=doc["sha256"], origin="sample"))
        self.assertEqual(status, 201)
        self.assertEqual(view["case"]["origin"], "UPLOAD")
        self.assertEqual(view["finding"]["factual_evidence_status"], "EVIDENCE_SUPPORTS_CUSTOMER_DIRECTED_MANPOWER")
        self.assertEqual(set(view["manual_field_sources"].values()), {"MANUALLY_PROVIDED_NOT_INFERRED_FROM_PDF"})

    def test_export_contains_runs_events_and_non_determination_statement(self):
        view = self.sample("maintenance")
        status, export, headers = self.call("GET", "/api/cases/{}/export".format(view["case"]["id"]))
        self.assertEqual(status, 200)
        self.assertIn("attachment", headers["Content-Disposition"])
        self.assertEqual(export["chain"]["status"], "INTACT")
        self.assertEqual(export["runs"][0]["report_integrity"], "VERIFIED")
        self.assertIn("No tax determination", export["statement"])

    # Request guards -------------------------------------------------------------------------
    def test_request_guards(self):
        status, data, _ = self.call("GET", "/api/cases", headers={"Host": "attacker.example"})
        self.assertEqual(status, 421)
        status, data, _ = self.call("POST", "/api/samples/warehouse/cases", headers={"X-TDS-Review": ""})
        self.assertEqual(status, 403)
        for path in ("/../webapp/server.py", "/%2e%2e/src/rules.py", "/css/../../server.py", "/api/documents/../../x/file"):
            status, data, _ = self.call("GET", path)
            self.assertEqual(status, 404, path)
        status, data, headers = self.call("GET", "/")
        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Security-Policy"], CSP)
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        status, data, headers = self.call("GET", "/js/app.js")
        self.assertTrue(headers["Content-Type"].startswith("text/javascript"))
        self.assertEqual(self.call("GET", "/api/health")[1]["model_calls"], "DISABLED")


class BindingTests(unittest.TestCase):
    def test_only_loopback_addresses_are_accepted(self):
        self.assertTrue(loopback("127.0.0.1"))
        self.assertTrue(loopback("localhost"))
        self.assertFalse(loopback("0.0.0.0"))
        self.assertFalse(loopback("192.0.2.10"))
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(SystemExit):
            serve("0.0.0.0", 0, tmp)

    def test_real_server_answers_on_loopback(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = App(tmp, 0)
            server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(app))
            app.port = server.server_address[1]
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                self.assertEqual(server.server_address[0], "127.0.0.1")
                conn = http.client.HTTPConnection("127.0.0.1", app.port, timeout=5)
                conn.request("GET", "/api/health")
                response = conn.getresponse()
                self.assertEqual(response.status, 200)
                self.assertEqual(json.loads(response.read())["bound_to"], "loopback")
                conn.close()
                # Phase 5B: declare an oversized body without sending it. The server must refuse
                # before reading; sending the body raced the early 413 and made this test flaky.
                with socket.create_connection(("127.0.0.1", app.port), timeout=5) as raw:
                    raw.sendall("POST /api/cases HTTP/1.1\r\nHost: 127.0.0.1:{}\r\nX-TDS-Review: 1\r\n"
                                "Content-Type: application/json\r\nContent-Length: 600000\r\n\r\n".format(app.port).encode())
                    self.assertIn(b" 413 ", raw.recv(4096).split(b"\r\n")[0])
            finally:
                server.shutdown()
                server.server_close()

    def test_stalled_request_times_out_and_cross_origin_preflight_fails(self):
        # Phase 5B regression: a body shorter than Content-Length used to block a thread forever.
        with tempfile.TemporaryDirectory() as tmp:
            app = App(tmp, 0)
            server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(app, request_timeout=1))
            app.port = server.server_address[1]
            threading.Thread(target=server.serve_forever, daemon=True).start()
            try:
                started = time.monotonic()
                with socket.create_connection(("127.0.0.1", app.port), timeout=10) as raw:
                    raw.sendall("POST /api/cases HTTP/1.1\r\nHost: 127.0.0.1:{}\r\nX-TDS-Review: 1\r\n"
                                "Content-Length: 100\r\n\r\n{{}}".format(app.port).encode())
                    while raw.recv(4096):
                        pass
                self.assertLess(time.monotonic() - started, 8)
                conn = http.client.HTTPConnection("127.0.0.1", app.port, timeout=5)
                conn.request("OPTIONS", "/api/cases", headers={
                    "Host": "127.0.0.1:{}".format(app.port), "Origin": "http://attacker.example",
                    "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "x-tds-review"})
                response = conn.getresponse()
                self.assertGreaterEqual(response.status, 400)
                self.assertIsNone(response.getheader("Access-Control-Allow-Origin"))
                response.read()
                conn.close()
            finally:
                server.shutdown()
                server.server_close()
