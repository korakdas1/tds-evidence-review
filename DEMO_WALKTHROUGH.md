# Demo walkthrough

Run these commands from the repository root with Python 3.8+. They use only the standard library, make **no API calls**, and do not overwrite any dataset or saved result. Outputs below were captured by executing the commands during Phase 2A; the capture is in `results/phase2a/demo_outputs.json`.

## 1. Supported factual extraction

The offline baseline finds individual-worker supervision. Quote positions use zero-based character offsets with an exclusive end. A provisional factual result still requires human review.

```bash
python - <<'PY'
from src.schema import BENCHMARK, load_input
from src.pipeline import run_batch
_, cases, digest = load_input(BENCHMARK)
case = next(c for c in cases if c["id"] == "S01_CUSTOMER_CONTROL")
r = run_batch([case], "baseline", digest)["results"][0]
q = next(q for q in r["supporting_quotes"] if q["fact"] == "worker_supervisor")
print("case:", r["case_id"])
print("personnel_supplied:", r["validated_facts"]["personnel_supplied"])
print("worker_supervisor:", r["validated_facts"]["worker_supervisor"])
print("status:", r["factual_evidence_status"])
print("quote:", q["quote"])
print("position:", q["positions"][0])
print("human_review_required:", r["human_review_required"])
PY
```

Actual output:

```text
case: S01_CUSTOMER_CONTROL
personnel_supplied: yes
worker_supervisor: customer
status: EVIDENCE_SUPPORTS_CUSTOMER_DIRECTED_MANPOWER
quote: The customer team leader allocates daily tickets, determines working shifts, and directly supervises the assigned engineers while they work.
position: {'start': 276, 'end': 416}
human_review_required: True
```

## 2. Missing supervision evidence

Removing the supervision clause leaves personnel supply but no reliable controller. Abstention is the correct result for this case.

```bash
python - <<'PY'
from src.schema import BENCHMARK, load_input
from src.pipeline import run_batch
_, cases, digest = load_input(BENCHMARK)
case = next(c for c in cases if c["id"] == "S01_CONTROL_REMOVED")
r = run_batch([case], "baseline", digest)["results"][0]
print("case:", r["case_id"])
print("worker_supervisor:", r["validated_facts"]["worker_supervisor"])
print("status:", r["factual_evidence_status"])
print("proposed_table_item:", r["proposed_table_item"])
print("human_review_required:", r["human_review_required"])
PY
```

Actual output:

```text
case: S01_CONTROL_REMOVED
worker_supervisor: unknown
status: INSUFFICIENT_TO_ESTABLISH_CONTROL
proposed_table_item: None
human_review_required: True
```

## 3. Recorded live quote-interpretation error

This command reads the preserved Phase 1B response; it does not contact OpenRouter. The model treated an explicit prohibition as customer supervision. The exact quote passed provenance but failed factual support; the validator abstained. This historical example is not a new model evaluation.

```bash
python - <<'PY'
import json
from pathlib import Path
report = json.loads(Path("results/phase1b/run-20261103-01/hybrid.json").read_text())
r = next(r for r in report["results"] if r["case_id"] == "S01_VENDOR_CONTROL")
q = next(q for q in r["supporting_quotes"] if q["fact"] == "worker_supervisor")
print("recorded_model:", r["returned_model"])
print("asserted_worker_supervisor:", r["extracted_facts"]["worker_supervisor"])
print("quote:", q["quote"])
print("verbatim:", q["verbatim"])
print("semantic_guard_passed:", q["semantic_guard_passed"])
print("validated_worker_supervisor:", r["validated_facts"]["worker_supervisor"])
print("status:", r["factual_evidence_status"])
print("validation_failures:", r["validation_failures"])
PY
```

Actual output:

```text
recorded_model: xingchen-agi/xing4.0-29b-a4b:free
asserted_worker_supervisor: customer
quote: Customer may communicate desired service results but shall not direct the individual engineers.
verbatim: True
semantic_guard_passed: False
validated_worker_supervisor: unknown
status: INSUFFICIENT_TO_ESTABLISH_CONTROL
validation_failures: ['Quote does not pass conservative factual support check', 'Unsupported asserted fact: worker_supervisor']
```

## Evaluation context

The original baseline remains 16/16 provisional-label agreement. On the source-informed synthetic challenge, agreement moved from 8/12 before fixes to 12/12 after fixes; the latter is development-set performance. The original first pass and historical live failures remain unchanged. See [PHASE_2A_REPORT.md](PHASE_2A_REPORT.md). None of these outputs establishes legally validated tax accuracy.
