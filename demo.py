"""Three offline examples: two current baseline runs and one saved historical replay."""
import sys
from pathlib import Path

from src.extraction import OpenRouterClient
from src.pipeline import run_batch
from src.schema import BENCHMARK, load_input, parse_json, validate_benchmark

ROOT = Path(__file__).resolve().parent
HISTORICAL_REPORT = ROOT / "results/phase1b/run-20261103-01/hybrid.json"


def demo_text():
    if validate_benchmark()["status"] != "VALID":
        raise ValueError("Frozen benchmark validation failed")
    _, cases, digest = load_input(BENCHMARK)
    selected = [next(c for c in cases if c["id"] == case_id)
                for case_id in ("S01_CUSTOMER_CONTROL", "S01_CONTROL_REMOVED")]
    # Explicit empty settings bypass environment credentials. Baseline never calls this client.
    batch = run_batch(selected, "baseline", digest,
                      client=OpenRouterClient(api_key="", model=""))
    if batch["run_status"] != "COMPLETED" or batch["api_calls"] != 0:
        raise ValueError("Offline baseline did not complete")
    supported, missing = batch["results"]
    supported_quote = next(q for q in supported["supporting_quotes"]
                           if q["fact"] == "worker_supervisor")

    # Replay recorded output and validation; do not rerun the model or relabel its response.
    archive = parse_json(HISTORICAL_REPORT.read_text(encoding="utf-8"))
    recorded = next(r for r in archive["results"] if r["case_id"] == "S01_VENDOR_CONTROL")
    rejected_quote = next(q for q in recorded["supporting_quotes"]
                          if q["fact"] == "worker_supervisor")
    if (recorded["run_status"] != "OK" or not rejected_quote["verbatim"]
            or rejected_quote["semantic_guard_passed"]):
        raise ValueError("Saved evidence does not contain the recorded rejection")

    def review(row):
        return row["review_status"].replace("_", " ").title()

    return "\n".join([
        "TDS evidence review - offline demo",
        "Synthetic examples; factual evidence only, not legally validated tax treatment.",
        "No API calls. All cases require human review.",
        "",
        "1. Supported customer-directed manpower | " + supported["case_id"],
        "   Source: current deterministic baseline",
        "   Supervisor: " + supported["validated_facts"]["worker_supervisor"],
        '   Exact quote: "' + supported_quote["quote"] + '"',
        "   Factual status: " + supported["factual_evidence_status"],
        "   Review: " + review(supported),
        "",
        "2. Missing supervision evidence | " + missing["case_id"],
        "   Source: current deterministic baseline",
        "   Supervisor: " + missing["validated_facts"]["worker_supervisor"],
        "   Factual status: " + missing["factual_evidence_status"],
        "   Missing: " + "; ".join(missing["missing_information"]),
        "   Review: " + review(missing) + " (abstains)",
        "",
        "3. REPLAYED HISTORICAL LLM EVIDENCE | " + recorded["case_id"],
        "   Source: results/phase1b/run-20261103-01/hybrid.json (not a new model run)",
        "   Recorded model: " + recorded["returned_model"],
        "   Rejected assertion: worker_supervisor=" + recorded["extracted_facts"]["worker_supervisor"],
        '   Verbatim quote: "' + rejected_quote["quote"] + '"',
        "   Recorded checks: verbatim=" + str(rejected_quote["verbatim"])
        + "; factual support=" + str(rejected_quote["semantic_guard_passed"]),
        "   Rejection: " + "; ".join(recorded["validation_failures"]),
        "   Validated supervisor: " + recorded["validated_facts"]["worker_supervisor"],
        "   Factual status: " + recorded["factual_evidence_status"],
        "   Review: " + review(recorded),
        "",
        "Exact quotation proves provenance, not correct interpretation or actual working practices.",
    ])


def main():
    try:
        output = demo_text()
    except (OSError, ValueError, KeyError, TypeError, StopIteration):
        print("Demo unavailable: required local benchmark or historical evidence is missing or invalid. "
              "Restore the repository's original data and results files.", file=sys.stderr)
        return 2
    print(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
