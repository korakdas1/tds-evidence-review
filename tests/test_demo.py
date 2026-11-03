"""The recruiter demo must work offline and distinguish replay from fresh extraction."""
import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

import demo
from src.schema import CUSTOMER, INSUFFICIENT, load_input


class DemoTests(unittest.TestCase):
    def setUp(self):
        for target in ("urllib.request.build_opener", "src.extraction.OpenRouterClient.complete"):
            guard = patch(target, side_effect=AssertionError("Demo must remain offline"))
            guard.start()
            self.addCleanup(guard.stop)

    def test_without_credentials_shows_supported_case_and_abstention(self):
        output = io.StringIO()
        with patch.dict("os.environ", {}, clear=True), redirect_stdout(output):
            self.assertEqual(demo.main(), 0)
        text = output.getvalue()
        _, cases, _ = load_input(demo.BENCHMARK)
        supported = next(c for c in cases if c["id"] == "S01_CUSTOMER_CONTROL")
        self.assertIn(supported["evidence_anchors"][0], text)
        self.assertIn("Factual status: " + CUSTOMER, text)
        self.assertIn("S01_CONTROL_REMOVED", text)
        self.assertIn("Supervisor: unknown", text)
        self.assertIn("Factual status: " + INSUFFICIENT, text)
        self.assertIn("Needs Review (abstains)", text)
        self.assertIn("not legally validated", text)

    def test_configured_environment_is_ignored_and_replay_matches_archive(self):
        with patch.dict("os.environ", {"OPENROUTER_API_KEY": "demo-test-placeholder",
                                       "OPENROUTER_MODEL": "unused:free"}), \
                patch("src.extraction.os.getenv", side_effect=AssertionError("Do not read credentials")):
            text = demo.demo_text()
        archive = json.loads(demo.HISTORICAL_REPORT.read_text(encoding="utf-8"))
        row = next(r for r in archive["results"] if r["case_id"] == "S01_VENDOR_CONTROL")
        quote = next(q for q in row["supporting_quotes"] if q["fact"] == "worker_supervisor")
        self.assertIn("REPLAYED HISTORICAL LLM EVIDENCE", text)
        self.assertIn("not a new model run", text)
        self.assertIn(row["returned_model"], text)
        self.assertIn(quote["quote"], text)
        self.assertIn("Rejected assertion: worker_supervisor=" + row["extracted_facts"]["worker_supervisor"], text)
        self.assertIn("verbatim=True; factual support=False", text)
        self.assertIn("Validated supervisor: unknown", text)
        self.assertEqual(text.count("Review: Needs Review"), 3)
        self.assertNotIn("demo-test-placeholder", text)

    def test_missing_archive_reports_error_without_partial_demo(self):
        out, err = io.StringIO(), io.StringIO()
        with patch.object(demo, "HISTORICAL_REPORT", Path(__file__) / "absent.json"), \
                redirect_stdout(out), redirect_stderr(err):
            self.assertEqual(demo.main(), 2)
        self.assertEqual(out.getvalue(), "")
        self.assertIn("Demo unavailable", err.getvalue())
        self.assertNotIn("Traceback", err.getvalue())


if __name__ == "__main__":
    unittest.main()
