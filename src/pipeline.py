"""Per-record isolation, safe model failure handling, and common report format."""
import time
import hashlib
from pathlib import Path
from collections import Counter
from datetime import datetime, timezone

from .evidence import extraction_errors, unknown_facts, validate_evidence
from .evaluation import evaluate
from .extraction import ModelError, OpenRouterClient, baseline_extract
from .rules import factual_status, report_rules, select_act
from .schema import INSUFFICIENT, STATUSES, input_errors, parse_json


def run_batch(cases, mode, digest, client=None):
    if mode not in ("baseline", "direct-llm", "hybrid"):
        raise ValueError("Unknown mode")
    started = time.perf_counter()
    client = client or OpenRouterClient()
    reports = []
    unavailable = "OPENROUTER_NOT_CONFIGURED" if mode != "baseline" and not client.configured else None
    ids = Counter(c.get("id") for c in cases if isinstance(c, dict) and isinstance(c.get("id"), str))
    for index, original in enumerate(cases):
        record = original if isinstance(original, dict) else {}
        tick = time.perf_counter()
        errors = input_errors(original)
        if isinstance(record.get("id"), str) and ids[record["id"]] > 1:
            errors.append("Duplicate case ID")
        case_id = record.get("id") if isinstance(record.get("id"), str) else "record-" + str(index + 1)
        dates = select_act(record.get("credit_date"), record.get("payment_date"))
        facts, quotes, validation, context_findings = unknown_facts(), [], [], []
        extraction = None
        status, run_status, reason = INSUFFICIENT, "OK", None
        raw, returned_model, usage, raw_status = None, None, None, None
        response_metadata = None
        valid_count, total_count, api_calls, api_error = 0, 0, 0, False
        if errors:
            run_status, validation = "INVALID_INPUT", list(errors)
        elif unavailable:
            run_status, reason = "NOT_RUN", unavailable
        else:
            try:
                if mode == "baseline":
                    extraction = baseline_extract(record)
                else:
                    api_calls = 1
                    response = client.complete(record, mode)
                    raw, returned_model, usage = response["raw_output"], response.get("returned_model"), response.get("usage")
                    response_metadata = response.get("response_metadata")
                    try:
                        parsed = parse_json(raw)
                    except (ValueError, TypeError, RecursionError):
                        raise ModelError("INVALID_MODEL_JSON") from None
                    if mode == "hybrid":
                        extraction = parsed
                        if extraction_errors(extraction):
                            raise ModelError("INVALID_EXTRACTION_SCHEMA")
                    else:
                        if (not isinstance(parsed, dict) or set(parsed) != {"factual_status"}
                                or parsed["factual_status"] not in STATUSES):
                            raise ModelError("INVALID_DIRECT_SCHEMA")
                        raw_status = status = parsed["factual_status"]
                if extraction is not None:
                    validated = validate_evidence(record["contract_excerpt"], extraction)
                    facts, quotes, validation = validated["facts"], validated["quotes"], validated["validation_failures"]
                    context_findings = validated.get("context_findings", [])
                    valid_count, total_count = validated["provenance_valid"], validated["provenance_total"]
                    status = factual_status(facts)
            except ModelError as exc:
                run_status = "NOT_RUN" if exc.unavailable else "ERROR"
                reason = exc.code
                # Schema/model-output errors are execution errors, not transport/API errors.
                api_error = exc.code not in ("INVALID_MODEL_JSON", "INVALID_EXTRACTION_SCHEMA", "INVALID_DIRECT_SCHEMA")
                if exc.unavailable:
                    unavailable = exc.code  # One availability probe; do not repeat a known failing request.
                validation.append(exc.code)
        rules_failures = list(validation)
        if mode == "direct-llm":
            rules_failures.append("Direct category has no validated predicate extraction; no table proposal")
        if run_status != "OK":
            rules_failures.append("Method did not complete successfully")
        review = report_rules(record, status, dates, rules_failures)
        missing = list(facts["missing_facts"]) + dates["validation_failures"]
        if mode == "direct-llm":
            missing.append("Predicate extraction and validated contract quotes are not produced by direct baseline.")
        if run_status != "OK":
            missing.append("Successful extraction or classification run.")
        reports.append({"case_id": case_id, "input_index": index, "method": mode,
                        "run_status": run_status, "not_run_or_error_reason": reason,
                        "date_selection": dates, "extracted_facts": extraction,
                        "validated_facts": facts, "supporting_quotes": quotes,
                        "deterministic_context_findings": context_findings,
                        "quote_provenance": {"valid": valid_count, "total": total_count},
                        "missing_information": missing,
                        "validation_failures": validation + dates["validation_failures"],
                        "raw_output": raw, "raw_model_status": raw_status,
                        "returned_model": returned_model, "usage": usage,
                        "response_metadata": response_metadata,
                        "api_calls": api_calls, "api_error": api_error,
                        "runtime_seconds": round(time.perf_counter() - tick, 6), **review})
    statuses = Counter(r["run_status"] for r in reports)
    run_state = "NOT_RUN" if statuses.get("NOT_RUN") == len(cases) else (
        "COMPLETED" if statuses.get("OK") == len(cases) else "PARTIAL_OR_FAILED")
    result = {"schema_version": "1.0", "method": mode, "run_status": run_state,
              "generated_at_utc": datetime.now(timezone.utc).isoformat(),
              "input_sha256": digest, "case_count": len(cases),
              "configured_model": client.model if mode != "baseline" and client.configured else None,
              "models_used": sorted({r["returned_model"] for r in reports if r["returned_model"]}),
              "api_calls": sum(r["api_calls"] for r in reports),
              "runtime_seconds": round(time.perf_counter() - started, 6),
              "run_status_counts": dict(statuses), "results": reports}
    root = Path(__file__).resolve().parent.parent
    result["implementation_sha256"] = {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(list((root / "src").glob("*.py")) + [root / "main.py", root / "src/rules_v1.json"])
    }
    result["evaluation"] = evaluate(cases, reports, mode)
    return result
