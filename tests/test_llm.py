"""Network is mocked throughout; these are not model-performance experiments."""
import io
import json
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import Mock, patch

from main import write_results
from src.evidence import lexical_extract
from src.extraction import ModelError, NoRedirect, OpenRouterClient
from src.pipeline import run_batch
from src.schema import CUSTOMER, INSUFFICIENT, OUT, transaction_input
from tests.test_core import process, transaction


class StubClient:
    configured = True
    model = "unit-test-stub"

    def __init__(self, outputs):
        self.outputs = iter(outputs)
        self.calls = 0

    def complete(self, record, mode):
        self.calls += 1
        value = next(self.outputs)
        if isinstance(value, Exception):
            raise value
        return {"raw_output": value, "returned_model": self.model, "usage": {}}


class LLMPipelineTests(unittest.TestCase):
    def test_no_credentials_never_calls_network(self):
        with patch.dict("os.environ", {}, clear=True), patch("urllib.request.build_opener") as opener:
            for mode in ("direct-llm", "hybrid"):
                result = run_batch([transaction()], mode, "unit")
                self.assertEqual(result["run_status"], "NOT_RUN")
                self.assertEqual(result["api_calls"], 0)
                self.assertEqual(result["evaluation"]["metrics"]["status_agreement"]["denominator"], 0)
                self.assertEqual(result["evaluation"]["safety_target"]["status"], "NOT_EVALUATED")
            opener.assert_not_called()

    def test_baseline_does_not_use_configured_client(self):
        client = StubClient([])
        result = process(transaction(), client=client)
        self.assertEqual(result["run_status"], "OK")
        self.assertEqual(client.calls, 0)

    def test_direct_raw_retained_and_no_table_proposal(self):
        raw = json.dumps({"factual_status": CUSTOMER})
        result = process(transaction(), "direct-llm", StubClient([raw]))
        self.assertEqual(result["raw_output"], raw)
        self.assertEqual(result["raw_model_status"], CUSTOMER)
        self.assertEqual(result["factual_evidence_status"], CUSTOMER)
        self.assertIsNone(result["proposed_table_item"])
        self.assertEqual(result["api_calls"], 1)

    def test_nonresident_wrapper_does_not_hide_raw_model_error(self):
        record = transaction(payee_residency="Non-resident", expected_fact_status=OUT)
        result = run_batch([record], "direct-llm", "unit", StubClient([json.dumps({"factual_status": CUSTOMER})]))
        self.assertEqual(result["results"][0]["factual_evidence_status"], OUT)
        metrics = result["evaluation"]["metrics"]
        self.assertEqual(metrics["status_agreement"]["numerator"], 1)
        self.assertEqual(metrics["raw_model_status_agreement"]["numerator"], 0)

    def test_hybrid_one_call_validates_evidence(self):
        record = transaction()
        client = StubClient([json.dumps(lexical_extract(record["contract_excerpt"]))])
        result = process(record, "hybrid", client)
        self.assertEqual(result["factual_evidence_status"], CUSTOMER)
        self.assertTrue(all(q["verbatim"] for q in result["supporting_quotes"]))
        self.assertEqual(client.calls, 1)

    def test_hybrid_fabricated_quote_abstains(self):
        facts = lexical_extract("Supplier supplies workers. Customer supervises workers.")
        result = process(transaction("Supplier handles payroll."), "hybrid", StubClient([json.dumps(facts)]))
        self.assertEqual(result["factual_evidence_status"], INSUFFICIENT)
        self.assertEqual(result["quote_provenance"], {"valid": 0, "total": 2})
        self.assertIsNone(result["proposed_table_item"])

    def test_injected_model_extra_legal_fields_rejected(self):
        raw = json.dumps({"factual_status": CUSTOMER, "rate": "1%"})
        result = process(transaction(), "direct-llm", StubClient([raw]))
        self.assertEqual(result["run_status"], "ERROR")
        self.assertEqual(result["raw_output"], raw)
        self.assertIsNone(result["proposed_table_item"])

    def test_model_error_does_not_crash_batch(self):
        client = StubClient(["not-json", json.dumps({"factual_status": CUSTOMER})])
        result = run_batch([transaction(id="a"), transaction(id="b")], "direct-llm", "unit", client)
        self.assertEqual([r["run_status"] for r in result["results"]], ["ERROR", "OK"])
        self.assertEqual(result["api_calls"], 2)

    def test_unavailable_one_probe_then_not_run(self):
        client = StubClient([ModelError("HTTP_401", unavailable=True)])
        result = run_batch([transaction(id="a"), transaction(id="b")], "hybrid", "unit", client)
        self.assertEqual(result["run_status"], "NOT_RUN")
        self.assertEqual(result["api_calls"], 1)
        self.assertEqual(result["evaluation"]["metrics"]["api_errors"]["numerator"], 1)
        self.assertEqual(result["evaluation"]["metrics"]["api_errors"]["denominator"], 1)

    def test_safety_target_does_not_pass_unexecuted_cases(self):
        cases = [transaction(id=str(i), variant="CONTROL_REMOVED", expected_fact_status=INSUFFICIENT) for i in range(4)]
        result = run_batch(cases, "hybrid", "unit", StubClient([ModelError("HTTP_429", unavailable=True)]))
        self.assertEqual(result["evaluation"]["safety_target"]["status"], "NOT_EVALUATED")


class HTTPClientTests(unittest.TestCase):
    def mock_response(self, content, **extra):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = json.dumps({"choices": [{"message": {"content": content}}], "model": "mock-returned", **extra}).encode()
        return response

    def test_request_uses_only_transaction_fields_and_single_call(self):
        record = transaction(id="CUSTOMER_CONTROL", expected_fact_status=CUSTOMER,
                             evidence_anchors=["label-secret"], scenario="test", label_note="secret-label")
        client = OpenRouterClient("unit-test-key", "mock:free")
        with patch("urllib.request.build_opener") as builder:
            builder.return_value.open.return_value = self.mock_response("{}", usage={"total_tokens": 12})
            result = client.complete(record, "hybrid")
            request = builder.return_value.open.call_args[0][0]
            payload = json.loads(request.data)
            self.assertEqual(json.loads(payload["messages"][1]["content"]), transaction_input(record))
            self.assertNotIn("expected_fact_status", request.data.decode())
            self.assertNotIn("label-secret", request.data.decode())
            self.assertNotIn("unit-test-key", request.data.decode())
            self.assertEqual(payload["messages"][0]["role"], "system")
            self.assertEqual(client.calls, 1)
            self.assertEqual(result["usage"], {"total_tokens": 12})
            self.assertEqual(builder.return_value.open.call_args[1]["timeout"], 45)

    def test_http_error_body_not_logged(self):
        client = OpenRouterClient("unit-test-key", "mock:free")
        error = urllib.error.HTTPError(client.endpoint, 401, "unit-test-key", {}, io.BytesIO(b"unit-test-key"))
        with patch("urllib.request.build_opener") as builder:
            builder.return_value.open.side_effect = error
            with self.assertRaises(ModelError) as raised:
                client.complete(transaction(), "hybrid")
            self.assertEqual(str(raised.exception), "HTTP_401")
            self.assertTrue(raised.exception.unavailable)

    def test_timeout_sanitized(self):
        with patch("urllib.request.build_opener") as builder:
            builder.return_value.open.side_effect = TimeoutError("private diagnostics")
            with self.assertRaises(ModelError) as raised:
                OpenRouterClient("test", "mock:free").complete(transaction(), "hybrid")
            self.assertEqual(str(raised.exception), "NETWORK_OR_TIMEOUT")

    def test_malformed_provider_response(self):
        with patch("urllib.request.build_opener") as builder:
            response = self.mock_response("{}")
            response.read.return_value = b"not JSON"
            builder.return_value.open.return_value = response
            with self.assertRaises(ModelError) as raised:
                OpenRouterClient("test", "mock:free").complete(transaction(), "hybrid")
            self.assertEqual(str(raised.exception), "INVALID_PROVIDER_RESPONSE")

    def test_redirect_disallowed(self):
        self.assertIsNone(NoRedirect().redirect_request(None, None, 302, "", {}, "https://example.com"))

    def test_echoed_secret_redacted(self):
        with patch("urllib.request.build_opener") as builder:
            builder.return_value.open.return_value = self.mock_response("unit-test-key")
            response = OpenRouterClient("unit-test-key", "mock:free").complete(transaction(), "hybrid")
            self.assertEqual(response["raw_output"], "[REDACTED_API_KEY]")

    def test_secret_redaction_in_json_and_csv(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict("os.environ", {"OPENROUTER_API_KEY": "unit-test-key"}):
            result = run_batch([transaction(id="unit-test-key")], "baseline", "test")
            path = Path(temp) / "out.json"
            write_results(result, path)
            self.assertNotIn("unit-test-key", path.read_text())
            self.assertNotIn("unit-test-key", path.with_suffix(".csv").read_text())


if __name__ == "__main__":
    unittest.main()
