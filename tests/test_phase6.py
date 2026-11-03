"""Phase 6 hardening: versioned Act selection, fail-closed integrity, resource limits.

No model, network or subprocess use. Fixtures are synthetic development regression cases,
not independent validation.
"""
import hashlib
import importlib.util
import io
import json
import sqlite3
import tempfile
import threading
import tracemalloc
import unittest
import zlib
from contextlib import redirect_stderr
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import http.client

from src.pipeline import run_batch
from src.rules import ACT_SELECTION, NEW_ACT, OLD_ACT, RULES, load_act_selection, select_act
from webapp.server import App, make_handler
from webapp.store import StaleRunError, canonical

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures" / "phase6"
HOST = {"Host": "127.0.0.1:8765", "X-TDS-Review": "1"}
HAS_PYPDF = importlib.util.find_spec("pypdf") is not None


def bomb_pdf(pages=20, raw_bytes=74_000_000):
    """A small file whose page streams each inflate to about 74 MB."""
    stream = zlib.compress(b"BT /F1 9 Tf 10 10 Td (x) Tj ET\n" + b" " * raw_bytes, 9)
    objects = [None, None, b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    kids = []
    for _ in range(pages):
        objects.append(b"<< /Length %d /Filter /FlateDecode >>\nstream\n" % len(stream) + stream + b"\nendstream")
        objects.append(b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 3 0 R >> >> "
                       b"/Contents %d 0 R >>" % len(objects))
        kids.append(len(objects))
    objects[0] = b"<< /Type /Catalog /Pages 2 0 R >>"
    objects[1] = b"<< /Type /Pages /Kids [" + b" ".join(b"%d 0 R" % k for k in kids) + b"] /Count %d >>" % pages
    out, offsets = bytearray(b"%PDF-1.4\n"), []
    for number, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1) + b"".join(b"%010d 00000 n \n" % o for o in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)
    return bytes(out)


class ActSelectionRuleTests(unittest.TestCase):
    def config(self):
        return json.loads((ROOT / "src" / "act_selection_v1.json").read_text())

    def test_frozen_development_cases(self):
        manifest = json.loads((FIXTURES / "manifest.json").read_text())
        raw = (FIXTURES / "act_selection_cases.json").read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), manifest["files"]["act_selection_cases.json"])
        data = json.loads(raw)
        self.assertEqual(data["kind"], "DEVELOPMENT_REGRESSION_CASES_NOT_INDEPENDENT_VALIDATION")
        for case in data["cases"]:
            with self.subTest(case=case["id"]):
                result = select_act(case["credit_date"], case["payment_date"])
                self.assertEqual(result["status"], case["expected_status"])
                self.assertEqual(result["applicable_act"], case["expected_act"])
                self.assertEqual(result["trigger_date"], case["expected_trigger_date"])
                self.assertEqual(result["rule_version"], "act_selection@1.0.0")
                if result["status"] != "RESOLVED":
                    self.assertTrue(result["validation_failures"])

    def test_config_matches_cited_source_and_adds_no_tax_parameters(self):
        source = next(r for r in RULES["rules"] if r["id"] == ACT_SELECTION["source_rule_id"])
        self.assertEqual(source["effective_from"], "2026-04-01")
        self.assertEqual(ACT_SELECTION["boundaries"][-1].isoformat(), source["effective_from"])
        self.assertEqual((OLD_ACT, NEW_ACT), ("Income-tax Act, 1961", "Income-tax Act, 2025"))
        # Structural guard: the config can only carry Act periods, never rates, thresholds or classifications.
        config = self.config()
        self.assertEqual(set(config), {"id", "version", "checked_on", "source_rule_id", "trigger", "required_dates",
                                       "date_format", "periods", "verification_status", "note"})
        self.assertTrue(all(set(p) == {"act", "effective_from", "effective_to"} for p in config["periods"]))
        self.assertIn("NOT_INDEPENDENTLY_LEGALLY_VALIDATED", self.config()["verification_status"])

    def test_malformed_configs_fail_at_load(self):
        mutations = {
            "gap": lambda c: c["periods"][1].update(effective_from="2026-04-02"),
            "overlap": lambda c: c["periods"][1].update(effective_from="2026-03-31"),
            "open_start": lambda c: c["periods"][0].update(effective_from="2000-01-01"),
            "open_end": lambda c: c["periods"][1].update(effective_to="2030-01-01"),
            "duplicate_act": lambda c: c["periods"][1].update(act=c["periods"][0]["act"]),
            "single_period": lambda c: c.update(periods=c["periods"][:1]),
            "unsupported_trigger": lambda c: c.update(trigger="LATER_OF_REQUIRED_DATES"),
            "one_date_only": lambda c: c.update(required_dates=["payment_date"]),
            "bad_version": lambda c: c.update(version="v1"),
            "missing_key": lambda c: c.pop("periods"),
            "source_disagrees": lambda c: (c["periods"][0].update(effective_to="2026-04-30"),
                                           c["periods"][1].update(effective_from="2026-05-01")),
            "unknown_source": lambda c: c.update(source_rule_id="invented_rule"),
            "bad_date": lambda c: c["periods"][0].update(effective_to="31-03-2026"),
        }
        for name, mutate in mutations.items():
            with self.subTest(mutation=name):
                config = self.config()
                mutate(config)
                with self.assertRaises(ValueError):
                    load_act_selection(config)

    def test_injected_config_is_used_and_traced(self):
        config = self.config()
        config["version"] = "9.9.9"
        loaded = load_act_selection(config)
        self.assertEqual(select_act("2026-04-01", "2026-04-02", loaded)["rule_version"], "act_selection@9.9.9")

    def test_implementation_hashes_include_rule_config(self):
        from tests.test_core import transaction
        result = run_batch([transaction()], "baseline", "unit")
        self.assertIn("src/act_selection_v1.json", result["implementation_sha256"])
        self.assertEqual(result["results"][0]["date_selection"]["rule_version"], "act_selection@1.0.0")


@unittest.skipUnless(HAS_PYPDF, "PDF tests require pip install -r requirements-pdf.txt")
class PdfResourceTests(unittest.TestCase):
    def test_decompression_bomb_is_bounded_and_flagged(self):
        import pypdf
        from src.pdf_ingestion import read_pdf
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bomb.pdf"
            path.write_bytes(bomb_pdf())
            self.assertLess(path.stat().st_size, 2 * 1024 * 1024)
            tracemalloc.start()
            try:
                doc = read_pdf(path)
                peak = tracemalloc.get_traced_memory()[1]
            finally:
                tracemalloc.stop()
        self.assertEqual(doc["status"], "NEEDS_DOCUMENT_REVIEW")
        self.assertTrue(all("DECOMPRESSION_LIMIT" in p["issues"] for p in doc["pages"]))
        self.assertLess(peak, 200 * 1024 * 1024, "peak traced memory must stay bounded")
        # Limits are temporary and context-local: the global pypdf configuration is restored.
        self.assertEqual(pypdf.get_configuration().zlib_maximum_output_length, 75_000_000)


@unittest.skipUnless(HAS_PYPDF, "Review app tests require pip install -r requirements-pdf.txt")
class IntegrityAndReliabilityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.app = App(self.tmp.name, 8765)
        for target in ("urllib.request.build_opener", "urllib.request.urlopen", "socket.create_connection",
                       "subprocess.Popen", "os.system", "src.extraction.OpenRouterClient.complete"):
            guard = patch(target, side_effect=AssertionError("Review app must stay local and offline"))
            guard.start()
            self.addCleanup(guard.stop)

    def call(self, method, path, body=None, headers=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode()
        response = self.app.handle(method, path, {**HOST, **(headers or {})}, body or b"")
        data = json.loads(response.body) if response.headers["Content-Type"] == "application/json" else response.body
        return response.status, data, response.body

    def sample(self, name="maintenance"):
        status, view, _ = self.call("POST", "/api/samples/{}/cases".format(name))
        self.assertEqual(status, 201)
        return view

    def db(self, *drop_triggers):
        db = sqlite3.connect(str(Path(self.tmp.name) / "review.sqlite3"))
        self.addCleanup(db.close)
        for trigger in drop_triggers:
            db.execute("DROP TRIGGER " + trigger)
        return db

    def assert_fails_closed(self, case_id, failed_check, secret_texts):
        status, view, raw = self.call("GET", "/api/cases/" + case_id)
        self.assertEqual(status, 200)
        self.assertEqual(view["integrity"]["status"], "FAILED")
        self.assertIn(failed_check, view["integrity"]["failed_checks"])
        self.assertTrue(view["untrusted"])
        self.assertIsNone(view["finding"])
        self.assertEqual((view["evidence"], view["missing_information"]), ([], []))
        self.assertTrue(all(d["pages"] == [] and d["file_url"] is None for d in view["documents"]))
        status, cases, list_raw = self.call("GET", "/api/cases")
        item = next(c for c in cases if c["id"] == case_id)
        self.assertEqual((item["integrity"], item["factual_status"], item["evidence_counts"]), ("FAILED", None, {}))
        for text in secret_texts:
            self.assertNotIn(text.encode(), raw, "untrusted content leaked in case view")
            self.assertNotIn(text.encode(), list_raw, "untrusted content leaked in case list")
        status, export, _ = self.call("GET", "/api/cases/{}/export".format(case_id))
        self.assertEqual((export["integrity_status"], export["runs"]), ("INTEGRITY_FAILED", []))
        self.assertIn("UNTRUSTED", export["forensic_untrusted"]["warning"])
        status, data, _ = self.call("POST", "/api/cases/{}/events".format(case_id),
                                    dict(kind="NOTE", note="x", reviewer="R"))
        self.assertEqual(status, 409)

    # Integrity: each tampering mode fails closed --------------------------------------------
    def test_forged_row_without_recomputed_hash(self):
        view = self.sample()
        db = self.db("runs_no_update")
        db.execute("UPDATE runs SET report_json = replace(report_json, 'CONFLICTING_EVIDENCE', 'OUT_OF_SCOPE')")
        db.commit()
        self.assert_fails_closed(view["case"]["id"], "report_row_hash", ["OUT_OF_SCOPE", "technician on site"])

    def test_forged_row_with_recomputed_hash(self):
        view = self.sample()
        db = self.db("runs_no_update")
        report = json.loads(db.execute("SELECT report_json FROM runs").fetchone()[0])
        report["review"]["factual_evidence_status"] = "EVIDENCE_SUPPORTS_CUSTOMER_DIRECTED_MANPOWER"
        forged = json.dumps(report, ensure_ascii=True, sort_keys=True)
        db.execute("UPDATE runs SET report_json = ?, report_sha256 = ?", (forged, hashlib.sha256(forged.encode()).hexdigest()))
        db.commit()
        self.assert_fails_closed(view["case"]["id"], "history_anchor",
                                 ["EVIDENCE_SUPPORTS_CUSTOMER_DIRECTED_MANPOWER", "technician on site"])

    def test_missing_history_anchor(self):
        view = self.sample()
        db = self.db("events_no_delete")
        db.execute("DELETE FROM events WHERE kind = 'ANALYSIS_RUN'")  # the newest entry: chain stays linked
        db.commit()
        status, data, _ = self.call("GET", "/api/cases/" + view["case"]["id"])
        self.assertEqual(data["integrity"]["checks"]["history_chain"], "INTACT")
        self.assertEqual(data["integrity"]["checks"]["history_anchor"], "MISSING")
        self.assert_fails_closed(view["case"]["id"], "history_anchor", ["technician on site"])

    def test_broken_history_chain(self):
        view = self.sample()
        db = self.db("events_no_update")
        db.execute("UPDATE events SET created_at = '2000-01-01T00:00:00+00:00' WHERE kind = 'CASE_CREATED'")
        db.commit()
        self.assert_fails_closed(view["case"]["id"], "history_chain", ["technician on site"])

    def test_case_record_tampering(self):
        view = self.sample()
        db = self.db("cases_no_update")
        db.execute("UPDATE cases SET title = 'Approved for withholding'")
        db.commit()
        self.assert_fails_closed(view["case"]["id"], "case_record", ["technician on site"])

    def test_corrupted_stored_document_keeps_trusted_analysis_but_blocks_pdf_checks(self):
        view = self.sample("warehouse")
        store = self.app.store
        path = store.document_path(store.document(view["documents"][0]["sha256"]))
        path.write_bytes(b"%PDF-1.4 replaced")
        status, view, _ = self.call("GET", "/api/cases/" + view["case"]["id"])
        self.assertEqual(view["integrity"]["status"], "DOCUMENTS_UNAVAILABLE")
        self.assertEqual(view["integrity"]["documents"]["contract"], "HASH_MISMATCH")
        self.assertEqual(view["finding"]["factual_evidence_status"], "EVIDENCE_SUPPORTS_CUSTOMER_DIRECTED_MANPOWER")
        self.assertTrue(all(not c["spans_verified"] for c in view["evidence"]))
        events = "/api/cases/{}/events".format(view["case"]["id"])
        for body, code in ((dict(kind="QUOTE_CHECK", target=view["evidence"][0]["key"], decision="UNCLEAR"), 409),
                           (dict(kind="DOCUMENT_CHECK", target="contract", decision="ISSUES_FOUND"), 409),
                           (dict(kind="NOTE", decision=None, note="Stored PDF changed"), 201)):
            status, data, _ = self.call("POST", events, dict(body, reviewer="R"))
            self.assertEqual(status, code, data)
        path.unlink()
        status, view, _ = self.call("GET", "/api/cases/" + view["case"]["id"])
        self.assertEqual(view["integrity"]["documents"]["contract"], "MISSING")

    def test_reuploading_identical_bytes_repairs_a_damaged_stored_copy(self):
        # Phase 6 defect: de-duplication returned the damaged copy, so re-uploading never helped.
        data = (ROOT / "webapp/samples/warehouse_agreement.pdf").read_bytes()
        headers = {"Content-Type": "application/pdf", "X-Filename": "warehouse_agreement.pdf"}
        status, doc, _ = self.call("POST", "/api/documents", data, headers)
        store = self.app.store
        path = store.document_path(store.document(doc["sha256"]))
        for damage in (lambda: path.write_bytes(b"%PDF-1.4 damaged"), path.unlink):
            damage()
            self.assertNotEqual(store.verify_document(doc["sha256"])[0], "VERIFIED")
            self.assertEqual(self.call("POST", "/api/documents", data, headers)[0], 201)
            self.assertEqual(store.verify_document(doc["sha256"])[0], "VERIFIED")
        self.assertEqual(self.call("POST", "/api/samples/warehouse/cases")[0], 201)

    def test_export_checksum_and_status(self):
        view = self.sample()
        status, export, _ = self.call("GET", "/api/cases/{}/export".format(view["case"]["id"]))
        self.assertEqual(export["integrity_status"], "VERIFIED")
        self.assertEqual(export["runs"][0]["integrity"]["status"], "VERIFIED")
        claimed = export.pop("content_sha256")
        self.assertEqual(hashlib.sha256(canonical(export).encode()).hexdigest(), claimed)

    # Reliability --------------------------------------------------------------------------------
    def test_storage_quota(self):
        self.app.store.max_storage_bytes = 4000
        first = (ROOT / "webapp/samples/warehouse_agreement.pdf").read_bytes()
        second = (ROOT / "webapp/samples/maintenance_agreement.pdf").read_bytes()
        headers = {"Content-Type": "application/pdf", "X-Filename": "a.pdf"}
        self.assertEqual(self.call("POST", "/api/documents", first, headers)[0], 201)
        self.assertEqual(self.call("POST", "/api/documents", first, headers)[0], 201, "duplicates are free")
        status, data, _ = self.call("POST", "/api/documents", second, headers)
        self.assertEqual(status, 507)
        self.assertIn("storage limit", data["error"])
        self.app.store.max_storage_bytes, self.app.store.max_documents = 10 ** 9, 1
        self.assertEqual(self.call("POST", "/api/documents", second, headers)[0], 507)

    def test_analysis_concurrency_limit(self):
        self.app.service.analysis_wait_seconds = 0.05
        self.assertTrue(self.app.service.analysis_slots.acquire(blocking=False))
        try:
            status, data, _ = self.call("POST", "/api/samples/warehouse/cases")
            self.assertEqual(status, 503)
        finally:
            self.app.service.analysis_slots.release()
        self.assertEqual(self.call("POST", "/api/samples/warehouse/cases")[0], 201)

    def test_decision_racing_a_rerun_is_refused(self):
        view = self.sample("warehouse")
        service, original = self.app.service, self.app.service.assess
        latest = self.app.store.run(view["run"]["id"])

        def assess_then_concurrent_rerun(*args, **kwargs):
            result = original(*args, **kwargs)
            run = service.store.add_run(view["case"]["id"], latest["contract_sha256"], latest["invoice_sha256"],
                                        latest["metadata"], "baseline", None, latest["report"])
            service.store.append_event(view["case"]["id"], run["id"], "system", "ANALYSIS_RUN", None,
                                       dict(report_sha256=run["report_sha256"]))
            service.assess = original
            return result
        service.assess = assess_then_concurrent_rerun
        status, data, _ = self.call("POST", "/api/cases/{}/events".format(view["case"]["id"]),
                                    dict(kind="QUOTE_CHECK", target=view["evidence"][0]["key"],
                                         decision="MATCHES_DOCUMENT", reviewer="R"))
        self.assertEqual(status, 409)
        self.assertFalse([e for e in self.app.store.events(view["case"]["id"]) if e["kind"] == "QUOTE_CHECK"])
        with self.assertRaises(StaleRunError):
            self.app.store.append_event(view["case"]["id"], view["run"]["id"], "R", "NOTE", None, {},
                                        expect_latest_run=view["run"]["id"])

    def test_concurrent_reviewer_events_keep_one_linear_chain(self):
        view = self.sample("warehouse")
        path = "/api/cases/{}/events".format(view["case"]["id"])
        statuses = []

        def worker(n):
            for i in range(5):
                statuses.append(self.call("POST", path, dict(kind="NOTE", note="n{}-{}".format(n, i), reviewer="R{}".format(n)))[0])
        threads = [threading.Thread(target=worker, args=(n,)) for n in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(statuses, [201] * 40)
        chain = self.app.store.verify_chain(view["case"]["id"])
        self.assertEqual((chain["status"], chain["events"]), ("INTACT", 42))

    def test_strict_json_and_safe_responses(self):
        view = self.sample("warehouse")
        path = "/api/cases/{}/events".format(view["case"]["id"])
        for body in (b'{"kind":"NOTE","kind":"CASE_STATUS","note":"x","reviewer":"R"}',
                     b'{"kind":"NOTE","note":"x","reviewer":"R","n":NaN}', b"\xff\xfe", b"[" * 100000):
            self.assertEqual(self.call("POST", path, body)[0], 400, body[:20])

    def test_active_content_pdf_is_flagged_for_gated_display(self):
        data = (ROOT / "tests/fixtures/pdf_v1/active_content.pdf").read_bytes()
        status, doc, _ = self.call("POST", "/api/documents", data, {"Content-Type": "application/pdf", "X-Filename": "a.pdf"})
        meta = json.loads((ROOT / "tests/fixtures/pdf_v1/transaction.json").read_text())
        status, view, _ = self.call("POST", "/api/cases", dict(metadata={k: v for k, v in meta.items()}, contract_sha256=doc["sha256"]))
        self.assertEqual(status, 201)
        self.assertTrue(view["documents"][0]["active_content"])


class ServerErrorTests(unittest.TestCase):
    def test_unexpected_errors_are_generic_to_clients_and_typed_in_the_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = App(tmp, 0)
            app.handle = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("Confidential clause text"))
            server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(app))
            threading.Thread(target=server.serve_forever, daemon=True).start()
            log = io.StringIO()
            try:
                with redirect_stderr(log):
                    conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
                    conn.request("GET", "/api/health")
                    response = conn.getresponse()
                    body = response.read()
                    conn.close()
            finally:
                server.shutdown()
                server.server_close()
        self.assertEqual(response.status, 500)
        self.assertNotIn(b"Confidential", body)
        self.assertIn("RuntimeError", log.getvalue())
        self.assertNotIn("Confidential", log.getvalue())
