#!/usr/bin/env python3
"""Run evidence review offline, or explicitly configure an optional LLM experiment."""
import argparse
import csv
import json
import os
import sys
from pathlib import Path

from src.pipeline import run_batch
from src.schema import BENCHMARK, MANIFEST, load_input, validate_benchmark


def redact(value):
    key = os.getenv("OPENROUTER_API_KEY")
    return str(value).replace(key, "[REDACTED_API_KEY]") if key else str(value)


def safe_output_path(path, input_path):
    path = Path(path)
    if path.suffix.lower() != ".json":
        raise ValueError("Output must have a .json extension")
    for candidate in (path, path.with_suffix(".csv")):
        for protected in (Path(input_path), BENCHMARK, MANIFEST):
            if candidate.resolve() == protected.resolve() or (candidate.exists() and protected.exists() and os.path.samefile(str(candidate), str(protected))):
                raise ValueError("Refusing to overwrite input, frozen benchmark, or manifest")
    return path


def write_results(result, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(result, indent=2, ensure_ascii=False)
    key = os.getenv("OPENROUTER_API_KEY")
    if key:
        serialized = serialized.replace(key, "[REDACTED_API_KEY]")
    path.write_text(serialized + "\n", encoding="utf-8")
    with path.with_suffix(".csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["case_id", "method", "run_status", "applicable_act", "factual_evidence_status",
                         "human_review_required", "validation_failure_count", "runtime_seconds"])
        for row in result["results"]:
            values = [row["case_id"], row["method"], row["run_status"], row["date_selection"]["applicable_act"],
                      row["factual_evidence_status"], row["human_review_required"], len(row["validation_failures"]), row["runtime_seconds"]]
            # Prevent formulas if an arbitrary input ID is later opened in a spreadsheet.
            values = [redact(v) if v is not None else "" for v in values]
            writer.writerow([("'" + v) if v.startswith(("=", "+", "-", "@", "\t", "\r")) else v for v in values])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="tresata_adversarial_cases.json")
    parser.add_argument("--mode", choices=("baseline", "direct-llm", "hybrid"), default="baseline")
    parser.add_argument("--output", help="JSON report; a CSV summary is written beside it")
    parser.add_argument("--validate-benchmark", action="store_true", help="Check frozen hash/schema/anchors, then exit")
    args = parser.parse_args(argv)
    try:
        if args.validate_benchmark:
            validation = validate_benchmark(args.input)
            print(json.dumps(validation, indent=2))
            return 0 if validation["status"] == "VALID" else 2
        data, cases, digest = load_input(args.input)
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        frozen = digest == manifest["sha256"]
        if Path(args.input).resolve() == BENCHMARK.resolve() or frozen:
            check = validate_benchmark(args.input)
            if check["status"] != "VALID":
                raise ValueError("Frozen benchmark validation failed: " + "; ".join(check["failures"]))
        default = Path("results") / (args.mode + ".json") if frozen else Path("results/local") / (args.mode + ".json")
        output = safe_output_path(args.output or default, args.input)
        result = run_batch(cases, args.mode, digest)
        result["dataset"] = {"frozen_benchmark": frozen, "synthetic": frozen or all(isinstance(c, dict) and c.get("synthetic") is True for c in cases),
                             "annotation_warning": "Expected labels are provisional synthetic annotations, not validated tax-law ground truth"}
        write_results(result, output)
        print("{}: {} | {} cases | {} API calls".format(args.mode, result["run_status"], len(cases), result["api_calls"]))
        reasons = sorted({r["not_run_or_error_reason"] for r in result["results"] if r["not_run_or_error_reason"]})
        if reasons:
            print("Run notes: " + ", ".join(reasons))
        for row in result["results"]:
            print(redact("{} | {} | {} | {} | human review required".format(row["case_id"], row["run_status"], row["date_selection"]["applicable_act"] or "NEEDS_DATE_REVIEW", row["factual_evidence_status"])))
        metric = result["evaluation"]["metrics"]["status_agreement"]
        print("Synthetic status agreement: {}/{} (eligible: {})".format(metric["numerator"], metric["denominator"], metric["eligible"]))
        print("Safety target: " + result["evaluation"]["safety_target"]["status"])
        print(redact("Reports: {} and {}".format(output, output.with_suffix(".csv"))))
        return 1 if any(r["run_status"] in ("ERROR", "INVALID_INPUT") for r in result["results"]) else 0
    except (OSError, ValueError, UnicodeError, RecursionError) as exc:
        # Avoid echoing input content, paths with credentials, or provider diagnostics.
        message = str(exc) if isinstance(exc, ValueError) and not isinstance(exc, json.JSONDecodeError) else type(exc).__name__
        key = os.getenv("OPENROUTER_API_KEY")
        if key:
            message = message.replace(key, "[REDACTED_API_KEY]")
        print("Input/output error: " + message, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
