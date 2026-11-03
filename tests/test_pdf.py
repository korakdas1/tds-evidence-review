"""Synthetic PDF integration and provenance tests; no model, network, OCR or subprocess use."""
import copy
import builtins
import hashlib
import importlib.util
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

import pdf_demo
from src.document_review import review_pdf_contract
from src.pdf_ingestion import compile_text, locate_quote, map_span, read_pdf, verify_location
from src.schema import CUSTOMER, CONFLICT, INSUFFICIENT
from src.pipeline import run_batch
from src.extraction import OpenRouterClient
from tests.test_core import process, transaction
from tests.test_llm import StubClient

FIXTURES = Path(__file__).resolve().parent / "fixtures/pdf_v1"
HAS_PYPDF = importlib.util.find_spec("pypdf") is not None


@unittest.skipUnless(HAS_PYPDF, "Optional PDF tests require pip install -r requirements-pdf.txt")
class PDFTests(unittest.TestCase):
    def setUp(self):
        self.metadata = json.loads((FIXTURES / "transaction.json").read_text())
        for target in ("urllib.request.build_opener", "urllib.request.urlopen",
                       "socket.create_connection", "subprocess.Popen", "os.system",
                       "src.extraction.OpenRouterClient.complete"):
            guard = patch(target, side_effect=AssertionError("PDF review must stay local and offline"))
            mocked = guard.start()
            self.addCleanup(guard.stop)
            self.addCleanup(mocked.assert_not_called)

    def review(self, name, **kwargs):
        return review_pdf_contract(self.metadata, FIXTURES / name, **kwargs)

    def test_frozen_fixture_hashes_and_declared_outcomes(self):
        manifest = json.loads((FIXTURES / "manifest.json").read_text())
        for entry in manifest["fixtures"]:
            with self.subTest(file=entry["file"]):
                path = FIXTURES / entry["file"]
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), entry["sha256"])
                self.assertEqual(read_pdf(path)["status"], entry["expected_status"])
        self.assertEqual(hashlib.sha256((FIXTURES / "transaction.json").read_bytes()).hexdigest(), manifest["transaction_sha256"])

    def test_supported_pdf_has_exact_hash_page_spans_and_no_released_proposal(self):
        report = self.review("supported.pdf")
        doc = report["documents"]["contract"]
        self.assertEqual(doc["file_sha256"], hashlib.sha256((FIXTURES / "supported.pdf").read_bytes()).hexdigest())
        self.assertEqual(report["review"]["factual_evidence_status"], CUSTOMER)
        self.assertIsNone(report["review"]["proposed_table_item"])
        self.assertIsNone(report["text_analysis"]["proposed_table_item"])
        for item in report["evidence_items"]:
            self.assertTrue(item["human_review_required"])
            self.assertFalse(item["may_support_statutory_proposal"])
            for occurrence in item["source_mapping"]["occurrences"]:
                for fragment in occurrence["fragments"]:
                    self.assertTrue(verify_location(doc, fragment))
                    self.assertEqual(fragment["page_number"], 1)

    def test_multipage_keeps_control_quote_on_page_two(self):
        report = self.review("multipage.pdf")
        q = next(i for i in report["evidence_items"] if i["fact"] == "worker_supervisor")
        self.assertEqual(q["source_mapping"]["occurrences"][0]["fragments"][0]["page_number"], 2)
        self.assertEqual(report["review"]["factual_evidence_status"], CUSTOMER)

    def test_whitespace_mapping_recovers_original_linebreaks(self):
        report = self.review("wrapped.pdf")
        q = next(i for i in report["evidence_items"] if i["fact"] == "worker_supervisor")
        self.assertEqual(q["quote"], "Customer directly supervises each worker.")
        fragment = q["source_mapping"]["occurrences"][0]["fragments"][0]
        self.assertIn("\n", fragment["quote"])
        self.assertTrue(verify_location(report["documents"]["contract"], fragment))

    def test_cross_page_sentence_maps_both_pages_but_requires_review(self):
        report = self.review("cross_page.pdf")
        q = next(i for i in report["evidence_items"] if i["fact"] == "worker_supervisor")
        occurrence = q["source_mapping"]["occurrences"][0]
        self.assertEqual([f["page_number"] for f in occurrence["fragments"]], [1, 2])
        self.assertTrue(occurrence["cross_page"])
        self.assertEqual(report["text_analysis"]["factual_evidence_status"], CUSTOMER)
        self.assertEqual(report["review"]["factual_evidence_status"], INSUFFICIENT)

    def test_split_negation_lines_and_pages_never_becomes_positive(self):
        for name in ("negation_lines.pdf", "negation_pages.pdf"):
            with self.subTest(name=name):
                report = self.review(name)
                self.assertIn("Customer must not supervise", report["documents"]["contract"]["text"])
                self.assertEqual(report["review"]["factual_evidence_status"], INSUFFICIENT)
                self.assertIsNone(report["review"]["proposed_table_item"])

    def test_displaced_negation_blocks_misleading_text_order(self):
        report = self.review("reading_order.pdf")
        page = report["documents"]["contract"]["pages"][0]
        self.assertEqual(page["order_check"], "DISAGREES")
        self.assertIn("not", page["alternate_layout_text"])
        self.assertEqual(report["text_analysis"]["factual_evidence_status"], CUSTOMER)
        self.assertEqual(report["review"]["factual_evidence_status"], INSUFFICIENT)
        self.assertEqual(report["review"]["validated_facts"]["worker_supervisor"], "unknown")

    def test_missing_and_conflicting_clauses(self):
        self.assertEqual(self.review("missing.pdf")["review"]["factual_evidence_status"], INSUFFICIENT)
        self.assertEqual(self.review("conflicting.pdf")["review"]["factual_evidence_status"], CONFLICT)

    def test_empty_scanned_partial_and_unreadable_pages_block_reliance(self):
        for name in ("empty.pdf", "scanned.pdf", "partial.pdf", "unreadable.pdf"):
            with self.subTest(name=name):
                report = self.review(name)
                self.assertEqual(report["status"], "NEEDS_DOCUMENT_REVIEW")
                self.assertEqual(report["review"]["factual_evidence_status"], INSUFFICIENT)
                self.assertIsNone(report["review"]["proposed_table_item"])
        self.assertEqual(read_pdf(FIXTURES / "scanned.pdf")["text"], "")

    def test_corrupted_encrypted_unsupported_and_missing_files_fail_safely(self):
        for name in ("corrupted.pdf", "encrypted.pdf", "unsupported.txt", "absent.pdf"):
            with self.subTest(name=name):
                report = self.review(name)
                self.assertEqual(report["documents"]["contract"]["status"], "REJECTED")
                self.assertEqual(report["status"], "NEEDS_DOCUMENT_REVIEW")
                self.assertFalse(report["evidence_items"])

    def test_file_and_page_limits(self):
        self.assertIn("FILE_SIZE_LIMIT", read_pdf(FIXTURES / "supported.pdf", max_bytes=10)["issues"])
        self.assertIn("PAGE_COUNT_LIMIT", read_pdf(FIXTURES / "multipage.pdf", max_pages=1)["issues"])
        self.assertIn("INVALID_LIMIT", read_pdf(FIXTURES / "supported.pdf", max_pages=0)["issues"])

    def test_decoded_stream_and_text_limits(self):
        for variable, code in (("MAX_STREAM_BYTES", "CONTENT_STREAM_LIMIT"),
                               ("MAX_PAGE_CHARS", "TEXT_SIZE_LIMIT"), ("MAX_TOTAL_CHARS", "TEXT_SIZE_LIMIT")):
            with self.subTest(variable=variable), patch("src.pdf_ingestion." + variable, 10):
                result = read_pdf(FIXTURES / "supported.pdf")
                self.assertIn(code, result["pages"][0]["issues"])
                self.assertEqual(result["text"], "")

    def test_parser_exception_is_a_page_failure(self):
        with patch("pypdf._page.PageObject.extract_text", side_effect=ValueError("untrusted parser detail")):
            result = read_pdf(FIXTURES / "supported.pdf")
        self.assertIn("PAGE_EXTRACTION_FAILED", result["pages"][0]["issues"])
        self.assertNotIn("untrusted parser detail", json.dumps(result))

    def test_embedded_javascript_is_flagged_never_executed(self):
        report = self.review("active_content.pdf")
        self.assertIn("ACTIVE_CONTENT_NOT_EXECUTED", report["documents"]["contract"]["issues"])
        self.assertEqual(report["review"]["factual_evidence_status"], INSUFFICIENT)

    def test_invalid_source_coordinates_hash_quote_and_context_rejected(self):
        doc = read_pdf(FIXTURES / "supported.pdf")
        original = locate_quote(doc, "Customer supervises each worker.")["occurrences"][0]["fragments"][0]
        alterations = [{"page_number":0}, {"page_number":99}, {"start":-1}, {"end":99999},
                       {"start":True}, {"file_sha256":"wrong"}, {"document_id":"other"},
                       {"document_name":"other.pdf"},
                       {"quote":"invented"}, {"context":{"start":0,"end":1,"text":"bad"}}]
        for change in alterations:
            with self.subTest(change=change):
                self.assertFalse(verify_location(doc, dict(original, **change)))

    def test_tampered_text_map_and_page_text_fail_closed(self):
        original = read_pdf(FIXTURES / "supported.pdf")
        for field in ("segments", "text", "page_text"):
            doc = copy.deepcopy(original)
            if field == "segments":doc[field][0]["page_start"] += 1
            elif field == "text":doc[field] += "invented"
            else:doc["pages"][0]["text"] += "invented"
            with self.subTest(field=field):
                self.assertEqual(map_span(doc, 0, 6)["status"], "UNRESOLVED")
        for start,end in ((-1,5),(0,99999),(5,2),(True,3)):
            self.assertEqual(map_span(original,start,end)["status"], "UNRESOLVED")

    def test_incorrect_pipeline_positions_are_unresolved_and_blocked(self):
        doc = read_pdf(FIXTURES / "supported.pdf")
        record = dict(self.metadata, contract_excerpt=doc["text"])
        batch = run_batch([record], "baseline", doc["file_sha256"], OpenRouterClient("", ""))
        batch["results"][0]["supporting_quotes"][0]["positions"] = [{"start":10000,"end":10010}]
        with patch("src.document_review.run_batch", return_value=batch):
            report = self.review("supported.pdf")
        self.assertIn("SOURCE_MAPPING_UNRESOLVED", report["review"]["document_issues"])
        self.assertEqual(report["review"]["factual_evidence_status"], INSUFFICIENT)
        self.assertTrue(any(i["source_mapping"]["status"] == "UNRESOLVED" and not i["source_mapping"]["occurrences"] for i in report["evidence_items"]))

    def test_exact_pdf_quote_does_not_promote_review_only_ai_claim(self):
        extraction = dict(personnel_supplied="yes", worker_supervisor="customer", missing_facts=[], contradictory_evidence=[],
                          supporting_quotes=[dict(fact="personnel_supplied",value="yes",quote="Vendor supplies workers."),
                                             dict(fact="worker_supervisor",value="customer",quote="Customer directly")])
        report = self.review("wrapped.pdf", mode="hybrid", client=StubClient([json.dumps(extraction)]))
        item = next(i for i in report["evidence_items"] if i["fact"] == "worker_supervisor")
        self.assertEqual(item["source_mapping"]["status"], "MAPPED_TO_EXTRACTED_TEXT")
        self.assertEqual(item["interpretation_status"], "AI_SUGGESTED_REQUIRING_REVIEW")
        self.assertEqual(report["review"]["validated_facts"]["worker_supervisor"], "unknown")
        self.assertIsNone(report["review"]["proposed_table_item"])

    def test_invoice_does_not_fill_missing_manual_dates_or_identity(self):
        manual = copy.deepcopy(self.metadata)
        manual.pop("credit_date")
        report = review_pdf_contract(manual, FIXTURES/"supported.pdf", FIXTURES/"invoice.pdf")
        self.assertEqual(report["documents"]["invoice"]["status"], "EXTRACTED")
        self.assertEqual(report["review"]["date_selection"]["status"], "NEEDS_DATE_REVIEW")
        manual.pop("payer_type")
        report = review_pdf_contract(manual, FIXTURES/"supported.pdf", FIXTURES/"invoice.pdf")
        self.assertEqual(report["review"]["run_status"], "INVALID_INPUT")

    def test_manual_contract_override_rejected_and_metadata_not_mutated(self):
        original = copy.deepcopy(self.metadata)
        self.review("supported.pdf")
        self.assertEqual(self.metadata, original)
        with self.assertRaises(ValueError):
            review_pdf_contract(dict(original, contract_excerpt="fake"), FIXTURES/"supported.pdf")

    def test_partial_invoice_also_requires_document_review(self):
        report = self.review("supported.pdf", invoice_path=FIXTURES/"scanned.pdf")
        self.assertIn("INVOICE_TEXT_INCOMPLETE_OR_UNRELIABLE", report["review"]["document_issues"])
        self.assertIsNone(report["review"]["proposed_table_item"])

    def test_json_workflow_keeps_its_existing_provisional_behavior(self):
        result = process(transaction("Vendor supplies workers. Customer supervises each worker."))
        self.assertEqual(result["factual_evidence_status"], CUSTOMER)
        self.assertIsNotNone(result["proposed_table_item"])

    def test_cli_offline_demo_and_existing_output_protection(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)/"demo.json"
            with redirect_stdout(io.StringIO()) as printed:
                self.assertEqual(pdf_demo.main(["--output",str(output)]), 0)
            self.assertIn("Page 1", printed.getvalue())
            self.assertIn("Human review: REQUIRED", printed.getvalue())
            self.assertEqual(json.loads(output.read_text())["api_calls"], 0)
            original = output.read_bytes()
            with redirect_stderr(io.StringIO()), redirect_stdout(io.StringIO()):
                self.assertEqual(pdf_demo.main(["--output",str(output)]), 2)
            self.assertEqual(output.read_bytes(), original)

    def test_custom_pdf_requires_explicit_metadata(self):
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
            pdf_demo.main(["--contract",str(FIXTURES/"supported.pdf")])
        self.assertEqual(error.exception.code, 2)

    def test_missing_optional_parser_returns_clear_error(self):
        original_import = builtins.__import__
        def without_parser(name, *args, **kwargs):
            if name == "pypdf":
                raise ImportError("Not installed")
            return original_import(name, *args, **kwargs)
        with patch("builtins.__import__", side_effect=without_parser):
            report = read_pdf(FIXTURES/"supported.pdf")
        self.assertIn("PDF_DEPENDENCY_MISSING_INSTALL_REQUIREMENTS_PDF", report["issues"])
        self.assertEqual(report["status"], "REJECTED")

    def test_unencodable_parser_text_and_tampered_source_fail_safely(self):
        with patch("pypdf._page.PageObject.extract_text", return_value="\ud800"):
            doc = read_pdf(FIXTURES/"supported.pdf")
        self.assertEqual(doc["status"], "NEEDS_DOCUMENT_REVIEW")
        self.assertEqual(doc["text"], "")
        doc = read_pdf(FIXTURES/"supported.pdf")
        location = locate_quote(doc, "Vendor supplies workers.")["occurrences"][0]["fragments"][0]
        doc["pages"][0]["text"] = "\ud800"
        self.assertFalse(verify_location(doc, location))
        self.assertEqual(map_span(doc, 0, 1)["status"], "UNRESOLVED")


if __name__ == "__main__":
    unittest.main()
