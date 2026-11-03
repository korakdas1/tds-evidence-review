"""Frozen Phase 3 comparison. Offline by default; pinned free model only on explicit opt-in."""
import argparse
import hashlib
import json
import os
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from src.evaluation import evaluate, ratio
from src.extraction import DIRECT_PROMPT, EXTRACTION_PROMPT, ModelError, NoRedirect, OpenRouterClient
from src.pipeline import run_batch
from src.schema import CUSTOMER, VENDOR, INSUFFICIENT, CONFLICT, OUT, ROOT, load_input

METHODS = ("direct-llm", "hybrid")


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value, key=""):
    text = json.dumps(value, indent=2, ensure_ascii=False) + "\n"
    if key:
        text = text.replace(key, "[REDACTED_API_KEY]")
    temporary = path.with_suffix(".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def comparison(cases, rows):
    pairs = [(c, r) for c, r in zip(cases, rows) if r["run_status"] == "OK"]
    directional = (CUSTOMER, VENDOR)
    false_positive = [(c, r) for c, r in pairs if r["factual_evidence_status"] in directional
                      and r["factual_evidence_status"] != c["expected_fact_status"]]
    gold_positive = [(c, r) for c, r in pairs if c["expected_fact_status"] in directional]
    false_negative = [(c, r) for c, r in gold_positive if r["factual_evidence_status"] not in directional]
    insufficient = [(c, r) for c, r in pairs if c["expected_fact_status"] == INSUFFICIENT]
    quotes = [q for _, r in pairs for q in r["supporting_quotes"]]
    extraction_applicable = bool(rows) and rows[0]["method"] != "direct-llm"
    return {
        "successful": ratio(len(pairs), len(cases)),
        "execution_failures": ratio(sum(r["run_status"] in ("ERROR", "INVALID_INPUT") for r in rows), len(cases)),
        "not_run": ratio(sum(r["run_status"] == "NOT_RUN" for r in rows), len(cases)),
        "api_errors": ratio(sum(r["api_error"] for r in rows), sum(r["api_calls"] for r in rows), unit="API attempts"),
        "attempted_but_not_usable": ratio(sum(r["api_calls"] > 0 and r["run_status"] != "OK" for r in rows), sum(r["api_calls"] for r in rows), unit="API attempts"),
        "refusals": ratio(sum(r["api_calls"] > 0 and (bool((r.get("response_metadata") or {}).get("refusal")) or r.get("not_run_or_error_reason") == "MODEL_REFUSAL") for r in rows), sum(r["api_calls"] for r in rows), unit="API attempts"),
        "false_positive_directional": ratio(len(false_positive), len(pairs)),
        "false_negative_directional": ratio(len(false_negative), len(gold_positive)),
        "abstentions": ratio(sum(r["factual_evidence_status"] in (INSUFFICIENT, CONFLICT, OUT) for _, r in pairs), len(pairs)),
        "appropriate_insufficient_abstentions": ratio(sum(r["factual_evidence_status"] == INSUFFICIENT and r["proposed_table_item"] is None for _, r in insufficient), len(insufficient)),
        "missing_control_evidence": ratio(sum(r["validated_facts"]["worker_supervisor"] == "unknown" for _, r in pairs) if extraction_applicable else 0, len(pairs) if extraction_applicable else 0, reason=None if extraction_applicable else "Direct mode has no predicate extraction"),
        "quote_errors": ratio(sum(not q["verbatim"] for q in quotes), len(quotes), unit="submitted quotes"),
        "exact_but_unverified_interpretations": ratio(sum(q["verbatim"] and not q["semantic_guard_passed"] for q in quotes), sum(q["verbatim"] for q in quotes), unit="verbatim quotes"),
        "review_only_cases": ratio(sum((r.get("evidence_review") or {}).get("state") == "AI_SUGGESTED_REQUIRING_REVIEW" for _, r in pairs), len(pairs)),
        "false_positive_case_ids": [c["id"] for c, _ in false_positive],
        "false_negative_case_ids": [c["id"] for c, _ in false_negative],
        "case_results": [dict(case_id=c["id"], expected=c["expected_fact_status"], observed=r["factual_evidence_status"],
                              run_status=r["run_status"], matches=r["run_status"] == "OK" and c["expected_fact_status"] == r["factual_evidence_status"],
                              evidence_state=(r.get("evidence_review") or {}).get("state"),
                              proposal=r["proposed_table_item"], validation_failures=r["validation_failures"])
                         for c, r in zip(cases, rows)],
        "interpretation": "Directional false negatives may be justified safety abstentions. Unexecuted cases never count as predictions. Direct mode has no fact/quote extraction; those metrics are not applicable."
    }


class FixtureClient:
    configured = True
    model = "HAND_AUTHORED_FIXTURE_NOT_A_MODEL"

    def __init__(self, fixtures):
        self.fixtures = {f["case_id"]: f["extraction"] for f in fixtures}

    def complete(self, record, mode):
        return {"raw_output": json.dumps(self.fixtures[record["id"]]), "returned_model": None}


def fixture_report(cases, input_digest, fixtures):
    report = run_batch(cases, "hybrid", input_digest, FixtureClient(fixtures))
    report["experiment_kind"] = "HAND_AUTHORED_FIXTURE_REPLAY_NOT_LLM_RESULTS"
    report["simulated_client_calls"], report["api_calls"] = report["api_calls"], 0
    for row in report["results"]:
        row["simulated_client_calls"], row["api_calls"] = row["api_calls"], 0
    report["evaluation"] = evaluate(cases, report["results"], "hybrid")
    report["comparison"] = comparison(cases, report["results"])
    return report


def configuration_key(path):
    key = os.getenv("OPENROUTER_API_KEY", "")
    if not key and path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("export "):
                line = line[7:]
            name, sep, value = line.partition("=")
            if sep and name.strip() == "OPENROUTER_API_KEY":
                key = value.strip().strip("\"'")
    return key.strip()


def free_model_preflight(model, key):
    if not key:
        return "KEY_NOT_CONFIGURED"
    # No automatic router, paid model, provider/model list or fallback allowed.
    if not model.endswith(":free") or "/" not in model or model.startswith("openrouter/"):
        return "PINNED_FREE_MODEL_REQUIRED"
    try:
        opener = urllib.request.build_opener(NoRedirect())
        with opener.open("https://openrouter.ai/api/v1/models", timeout=30) as response:
            models = json.load(response)["data"]
        selected = next((m for m in models if m["id"] == model), None)
        if not selected or not all(float(selected.get("pricing", {}).get(k, "1" if k in ("prompt", "completion") else "0")) == 0 for k in ("prompt", "completion", "request")):
            return "FREE_PRICING_NOT_VERIFIED"
        request = urllib.request.Request("https://openrouter.ai/api/v1/key", headers={"Authorization": "Bearer " + key})
        with opener.open(request, timeout=30) as response:
            info = json.load(response)["data"]
        remaining = info.get("limit_remaining")
        if remaining is not None and float(remaining) <= 0:
            return "KEY_LIMIT_EXHAUSTED"
        return None
    except (OSError, ValueError, KeyError, TypeError):
        return "PREFLIGHT_UNAVAILABLE"


class FixedClient(OpenRouterClient):
    def __init__(self, key, model, events_path):
        super().__init__(api_key=key, model=model)
        self.events_path, self.last_completed, self.blocked = events_path, None, None

    def complete(self, record, mode):
        if self.blocked:
            raise ModelError("STOPPED_AFTER_" + self.blocked, unavailable=True)
        if self.last_completed is not None:
            time.sleep(max(0, 15 - (time.monotonic() - self.last_completed)))
        started = time.monotonic()
        event = dict(case_id=record["id"], method=mode, requested_model=self.model)
        try:
            response = super().complete(record, mode)
            event.update(response)
            if response.get("returned_model") != self.model:
                raise ModelError("RETURNED_MODEL_MISMATCH", unavailable=True)
            if (response.get("response_metadata") or {}).get("refusal"):
                raise ModelError("MODEL_REFUSAL")
            return response
        except ModelError as error:
            self.blocked = error.code
            event["error"] = error.code
            raise
        finally:
            self.last_completed = time.monotonic()
            event["runtime_seconds"] = round(self.last_completed - started, 6)
            with self.events_path.open("a", encoding="utf-8") as stream:
                stream.write((json.dumps(event) + "\n").replace(self.api_key, "[REDACTED_API_KEY]"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--live-model", help="Explicit fixed provider/model:free; omitted means no network")
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    args = parser.parse_args()
    manifest = json.loads((ROOT / "phase3_manifest.json").read_text())
    for name, expected in manifest["files"].items():
        if digest(ROOT / name) != expected:
            raise ValueError("Frozen Phase 3 input/fixture hash mismatch")
    _, cases, input_digest = load_input(ROOT / "tresata_challenge_v3.json")
    fixtures = json.loads((ROOT / "phase3_extraction_fixtures.json").read_text())["fixtures"]
    args.output_dir.mkdir(parents=True, exist_ok=False)
    baseline = run_batch(cases, "baseline", input_digest, OpenRouterClient("", ""))
    baseline["comparison"] = comparison(cases, baseline["results"])
    save(args.output_dir / "baseline.json", baseline)
    save(args.output_dir / "hybrid_fixtures.json", fixture_report(cases, input_digest, fixtures))
    key = configuration_key(args.env_file) if args.live_model else ""
    blocked = free_model_preflight(args.live_model, key) if args.live_model else "LIVE_NOT_REQUESTED"
    protocol = dict(frozen_dataset_sha256=input_digest, requested_model=args.live_model,
                    started_at_utc=datetime.now(timezone.utc).isoformat(),
                    automatic_retries=0, paid_fallback=False, pacing_seconds=15, max_requests=24,
                    preflight_status=blocked or "FREE_MODEL_AND_KEY_LIMIT_VERIFIED",
                    prompt_sha256={"direct-llm": hashlib.sha256(DIRECT_PROMPT.encode()).hexdigest(),
                                   "hybrid": hashlib.sha256(EXTRACTION_PROMPT.encode()).hexdigest()},
                    implementation_sha256={str(p.relative_to(ROOT)):digest(p) for p in list((ROOT / "src").glob("*.py")) + [ROOT / "evaluate_phase3.py"]})
    save(args.output_dir / "protocol.json", protocol, key)
    client = FixedClient(key, args.live_model, args.output_dir / "requests.jsonl") if not blocked else None
    rows = {method: [] for method in METHODS}
    for index, case in enumerate(cases):
        for method in METHODS:
            chosen = client if not blocked else OpenRouterClient("", args.live_model or "")
            row = run_batch([case], method, input_digest, chosen)["results"][0]
            row["input_index"] = index
            if row["not_run_or_error_reason"] == "MODEL_REFUSAL":
                row["api_error"] = False  # Refusal is separate from transport/provider failure.
            if blocked:
                row["not_run_or_error_reason"] = blocked
            elif row["run_status"] != "OK":
                blocked = row["not_run_or_error_reason"] or "EXECUTION_FAILURE"
            elif (row.get("response_metadata") or {}).get("refusal"):
                blocked = "MODEL_REFUSAL"
            rows[method].append(row)
            payload = dict(method=method, requested_model=args.live_model, input_sha256=input_digest,
                           results=rows[method], planned_cases=len(cases), global_stop_reason=blocked,
                           evaluation=evaluate(cases[:len(rows[method])], rows[method], method),
                           comparison=comparison(cases[:len(rows[method])], rows[method]))
            save(args.output_dir / (method + ".json"), payload, key)
            print(json.dumps(dict(case_id=case["id"], method=method, status=row["run_status"],
                                  returned_model=row["returned_model"], reason=row["not_run_or_error_reason"])), flush=True)
    save(args.output_dir / "completion.json", dict(api_calls=sum(r["api_calls"] for rs in rows.values() for r in rs),
         stop_reason=blocked, frozen_inputs_unchanged=all(digest(ROOT / p)==h for p,h in manifest["files"].items()),
         successful_by_method={m:sum(r["run_status"]=="OK" for r in rs) for m,rs in rows.items()}), key)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
