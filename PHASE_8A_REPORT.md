# Phase 8A — reproducible factual evaluation infrastructure

Status: VERIFIED offline infrastructure; independent practitioner validation remains **NOT_ESTABLISHED**. Zero live calls in this phase. Base/fallback `a84d71d2b7ca3a72b37b04adb163a0bdf3f026df`. Phase SHA: `git log -1 --format=%H -- PHASE_8A_REPORT.md`; full verified remote SHA posted on Issue #1.

## Added

`evaluate_comparison.py`, `src/comparison.py`, versioned `evaluation/protocol_v1.json`, a hash-pinned historical import manifest, practitioner case JSON Schema and documentation, plus 14 focused regression tests. No datasets, labels, prompts, tax rules, prior tests or recorded experiments were changed. README/architecture/plan describe actual behaviour.

The default runner executes the baseline and explicitly marks model methods NOT_RUN. Optional simulation uses a constant-insufficient direct stub (no model or labels read) and the unchanged Phase 3 extraction fixtures. Historical import preserves old rows and model IDs, including missing/error cases. It aligns by case ID, rechecks quotations against the source, records hashes before predictions and checks sources again afterwards, refuses output overwrite and never enables inference. Per-case JSON/CSV and exact metric denominators are produced.

## Actual results

All comparison runs used frozen inputs and made zero live requests. Initial accounting outputs remain under `offline`, `simulated`, `historical`; final versions add explicit API/missing-evidence/date/review metrics, source rechecks and a narrower model-consistency label without changing predictions.

| Run/method | Execution origin | Successful/planned | Factual matches/successful | Incorrect confident/successful | Successful abstentions/successful | Quote errors/submitted |
|---|---|---:|---:|---:|---:|---:|
| Original baseline | Current OFFLINE | 16/16 | 16/16 | 0/16 | 6/16 | 0/29 |
| v2 baseline | Current OFFLINE | 12/12 | 12/12 | 0/12 | 4/12 | 0/25 |
| v3 baseline | Current OFFLINE | 12/12 | 9/12 | 0/12 | 10/12 | 0/19 |
| v3 direct stub | SIMULATED, not a model | 12/12 | 6/12 | 0/12 | 12/12 | Not applicable |
| v3 hybrid fixture replay | SIMULATED, not a model | 12/12 | 8/12 | 0/12 | 11/12 | 1/29 |
| Phase 1B direct | HISTORICAL recorded live | 2/16 | 2/2 | 0/2 | 0/2 | Not applicable |
| Phase 1B hybrid | HISTORICAL recorded live | 2/16 | 1/2 | 0/2 | 1/2 | 0/4 |

Abstention here means successful insufficient/conflicting findings; out-of-scope is separately counted. Errors/missing runs are not successful abstentions. Original baseline missing-evidence target: **0/4** false confidence. Historical methods completed **0/4** evidence-removed cases, so their target is **NOT_EVALUATED**, never a pass.

v3 directional false negatives: baseline **2/4**, direct stub **4/4**, hybrid replay **3/4**; these include conservative abstentions and are not automatically implementation failures. Hybrid replay has **28/29** exact quotes, **11/28** exact-but-unverified/rejected interpretation entries, and the intentionally fabricated P3_09 quote is retained as an error. The replay's 8/12 matches the unchanged Phase 3 historical fixture results. The baseline's 9/12 also remains unchanged. No prompt or evidence-rule tuning followed these scores.

Historical direct retains **1/16 execution errors, 13/16 NOT_RUN**, with 3 recorded attempts; hybrid retains **0/16 execution errors, 14/16 NOT_RUN**, with 2 attempts. Historical returned models are `dots-studio/dots-3-note-preview:free`, `nvidia/nemotron-3.5-super-vl:free` (direct), and `nvidia/nemotron-3.5-super-vl:free`, `xingchen-agi/xing4.0-29b-a4b:free` (hybrid). This is not a fixed-model fair comparison. Provider cost was reported for **0/3** direct and **0/2** hybrid attempts, so cost remains null. Token counts and historical pipeline latencies are retained only where supplied. No current model latency or paid cost was invented.

## Commands and tests

Executed `.venv/bin/python evaluate_comparison.py` with:

- `--output-dir results/phase8a/final-offline`
- `--simulate --output-dir results/phase8a/final-simulated`
- `--input tresata_adversarial_cases.json --recorded-manifest evaluation/historical_phase1b_v1.json --output-dir results/phase8a/final-historical`
- `--input tresata_challenge_v2.json --output-dir results/phase8a/v2-offline`

Initial versions of the first three runs are separately preserved. `python -m unittest tests.test_comparison -v` initially passed 12/12. Two further import-origin/missing-row tests were added before the full suite. Final `python -m unittest discover -v` results are in `results/phase8a/full_tests.txt`; all **233/233** tests pass, including unchanged preceding 219. No test failure occurred in this phase. Security gate: `python tools/release_check.py --output results/phase8a/security.json` and `git diff --check`.

Tests cover case-ID alignment, bad hashes/anchors, frozen inputs, missing/error denominator accounting, opposite-direction FP/FN, no safety pass without coverage, independently rechecked quote errors, absent usage/cost/predicate labels, explicit simulation and output exclusivity, historical model mixing, missing recorded rows, rejection of simulation relabelled as live, practitioner annotation spans and unauthenticated identity declarations. Network/provider access is patched to fail during evaluation tests.

## Remaining evidence requirements

The practitioner format is prepared, not populated with fictional independent labels. It records qualification/permission/independence assertions and exact evidence offsets, but cannot authenticate those claims or validate legal interpretation. Independent qualified review remains external unmet evidence. `RECORDED_LIVE` import describes supplied files, not cryptographic provider attestation; genuine origin must be independently established before relying on a future import. No new live experiment, production-readiness or legal accuracy is claimed.

Security scan covers candidate/history files and exact known credentials; historical inputs/results and submitted main are preserved. Private future datasets/results must stay under ignored directories. Next authorized phase: product finishing, complete offline demonstration and fresh-clone verification.

Release check note: staging exposed standard CSV CRLF line endings as trailing whitespace in `git diff --check`. Added a path-scoped `.gitattributes` whitespace rule accepting CR-at-EOL for these CSV outputs; preserved their original bytes and all metric values. No benchmark result was rewritten to satisfy a formatting check.
