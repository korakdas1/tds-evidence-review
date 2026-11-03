#!/usr/bin/env python3
"""One frozen, paced evaluation. Checkpoint each response; never retry API blocks."""
import argparse
import hashlib
import json
import os
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from main import write_results
from src.evaluation import evaluate
from src.extraction import DIRECT_PROMPT, EXTRACTION_PROMPT, ModelError, OpenRouterClient
from src.pipeline import run_batch
from src.schema import BENCHMARK, MANIFEST, ROOT, load_input, validate_benchmark

METHODS = ("direct-llm", "hybrid")


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_configuration(path):
    values = {}
    # No shell evaluation, variable interpolation, or credential-value logging.
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("export "):
            line = line[7:].lstrip()
        name, sep, value = line.partition("=")
        if sep and name.strip() in ("OPENROUTER_API_KEY", "OPENROUTER_MODEL"):
            value = value.strip()
            if len(value) >= 2 and value[0] in ("'", '"') and value[-1] == value[0]:
                value = value[1:-1]
            values[name.strip()] = value.strip()
    if not values.get("OPENROUTER_API_KEY"):
        raise ValueError("API key absent or empty")
    if values.get("OPENROUTER_MODEL") != "openrouter/free":
        raise ValueError("This protocol permits only openrouter/free; no paid fallback")
    return values


def save_json(path, value, key):
    text = (json.dumps(value, indent=2, ensure_ascii=False) + "\n").replace(key, "[REDACTED_API_KEY]")
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


class PacedClient(OpenRouterClient):
    def __init__(self, key, model, gap, events_path):
        super().__init__(api_key=key, model=model)
        self.gap, self.events_path = gap, events_path
        self.last_completed = None
        self.blocked = None

    def event(self, value):
        with self.events_path.open("a", encoding="utf-8") as stream:
            stream.write((json.dumps(value, ensure_ascii=False) + "\n").replace(self.api_key, "[REDACTED_API_KEY]"))
            stream.flush()

    def complete(self, record, mode):
        if self.blocked:
            raise RuntimeError("Protocol forbids requests after a block")
        if self.last_completed is not None:
            delay = self.gap - (time.monotonic() - self.last_completed)
            if delay > 0:
                time.sleep(delay)
        request_number = self.calls + 1
        self.event({"event": "request_started", "request_number": request_number,
                    "case_id": record["id"], "method": mode, "at_utc": utc_now()})
        started = time.monotonic()
        try:
            response = super().complete(record, mode)
            self.event({"event": "response_received", "request_number": request_number,
                        "case_id": record["id"], "method": mode, "at_utc": utc_now(),
                        "elapsed_seconds": round(time.monotonic() - started, 6), **response})
            return response
        except ModelError as error:
            # Global stop includes either method; no retry even on HTTP 429.
            self.blocked = error.code
            self.event({"event": "request_failed", "request_number": request_number,
                        "case_id": record["id"], "method": mode, "at_utc": utc_now(),
                        "elapsed_seconds": round(time.monotonic() - started, 6), "error": error.code})
            raise
        except Exception as error:
            self.blocked = "LOCAL_ERROR_" + type(error).__name__
            self.event({"event": "request_failed", "request_number": request_number,
                        "case_id": record["id"], "method": mode, "at_utc": utc_now(),
                        "error": self.blocked})
            raise ModelError(self.blocked, unavailable=True) from None
        finally:
            self.last_completed = time.monotonic()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    config = load_configuration(args.env_file)
    validation = validate_benchmark()
    if validation["status"] != "VALID":
        raise ValueError("Frozen benchmark validation failed")
    _, cases, input_digest = load_input(BENCHMARK)
    key, model = config["OPENROUTER_API_KEY"], config["OPENROUTER_MODEL"]
    # Only this process receives the configuration; write_results can redact the key.
    os.environ.update(config)
    history = [p for p in (ROOT / "results").rglob("*") if p.is_file()]
    code = [ROOT / "main.py", ROOT / "run_live_evaluation.py", ROOT / "src/rules_v1.json"]
    code += list((ROOT / "src").glob("*.py")) + list((ROOT / "tests").glob("*.py"))
    protected = {str(p.relative_to(ROOT)): digest(p) for p in [BENCHMARK, MANIFEST] + code + history}
    # A unique directory is the repeat-run guard; never overwrite a previous run.
    args.output_dir.mkdir(parents=True, exist_ok=False)
    protocol = {"phase": "1B", "frozen_before_requests_at_utc": utc_now(),
                "requested_model": model, "automatic_retries": 0, "paid_fallback": False,
                "request_gap_seconds_after_completion": 15, "timeout_seconds": 45,
                "max_tokens": 1400, "temperature": 0,
                "request_order": "dataset order; direct-llm then hybrid for each case",
                "max_requests": 32, "case_ids": [c["id"] for c in cases],
                "benchmark_sha256": input_digest, "protected_sha256": protected,
                "prompt_sha256": {"direct-llm": hashlib.sha256(DIRECT_PROMPT.encode()).hexdigest(),
                                  "hybrid": hashlib.sha256(EXTRACTION_PROMPT.encode()).hexdigest()},
                "stop_policy": "Any API/network/client block stops all remaining requests across both methods",
                "comparability": "Free-router underlying models may differ; this is not a fixed-model comparison",
                "validation": validation}
    save_json(args.output_dir / "protocol.json", protocol, key)
    client = PacedClient(key, model, 15, args.output_dir / "requests.jsonl")
    rows = {method: [] for method in METHODS}
    start = time.monotonic()

    def checkpoint(final=False):
        for method in METHODS:
            status_counts = Counter(row["run_status"] for row in rows[method])
            payload = {"schema_version": "1.0", "phase": "1B", "method": method,
                       "configured_model": model, "generated_at_utc": utc_now(),
                       "input_sha256": input_digest, "planned_case_count": 16,
                       "case_count": len(rows[method]), "api_calls": sum(r["api_calls"] for r in rows[method]),
                       "run_status": ("COMPLETED" if status_counts.get("OK") == 16 else
                                      "PARTIAL_OR_FAILED" if final else "IN_PROGRESS"),
                       "run_status_counts": dict(status_counts), "results": rows[method],
                       "models_used": sorted({r["returned_model"] for r in rows[method] if r["returned_model"]}),
                       "global_stop_reason": client.blocked,
                       "wall_seconds_including_pacing": round(time.monotonic() - start, 6),
                       "evaluation": evaluate(cases[:len(rows[method])], rows[method], method)}
            write_results(payload, args.output_dir / (method + ".json"))

    for index, case in enumerate(cases):
        for method in METHODS:
            if client.blocked:
                result = run_batch([case], method, input_digest, OpenRouterClient(api_key="", model=model))
                row = result["results"][0]
                row["not_run_or_error_reason"] = "STOPPED_AFTER_" + client.blocked
            else:
                result = run_batch([case], method, input_digest, client)
                row = result["results"][0]
            row["input_index"] = index
            rows[method].append(row)
            checkpoint()
            print(json.dumps({"case_id": case["id"], "method": method,
                              "status": row["run_status"], "model": row["returned_model"],
                              "error": row["not_run_or_error_reason"], "total_requests": client.calls}), flush=True)
    checkpoint(final=True)
    changed = [p for p, sha in protected.items() if not (ROOT / p).is_file() or digest(ROOT / p) != sha]
    save_json(args.output_dir / "integrity.json", {"protected_files_unchanged": not changed,
              "changed_files": changed, "live_request_attempts": client.calls,
              "automatic_retries": 0, "global_stop_reason": client.blocked,
              "finished_at_utc": utc_now(), "wall_seconds_including_pacing": round(time.monotonic() - start, 6)}, key)
    print(json.dumps({"finished": True, "requests": client.calls, "stop_reason": client.blocked,
                      "protected_files_unchanged": not changed}), flush=True)
    return 0 if client.blocked is None and not changed else 1


if __name__ == "__main__":
    raise SystemExit(main())
