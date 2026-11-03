# Factual comparison protocol v1

This runner compares three methods on the same frozen inputs, preserves per-case outputs, and makes **no network/model requests**:

```sh
python evaluate_comparison.py --output-dir results/local/comparison-offline
python evaluate_comparison.py --simulate --output-dir results/local/comparison-simulated
python evaluate_comparison.py --input tresata_adversarial_cases.json --recorded-manifest evaluation/historical_phase1b_v1.json --output-dir results/local/comparison-historical
python evaluate_comparison.py --input tresata_challenge_v2.json --output-dir results/local/comparison-v2
```

Use a new output directory each time. Outputs: `protocol.json` (written before predictions), one method report per method, `summary.json` and per-case `cases.csv`. Known datasets must match their original manifests; new separately frozen data requires `--input-sha256 SHA256`. Exact evidence anchors and label schemas are validated first. Dataset, prompt, implementation and protocol hashes are recorded; watched sources are rechecked at completion. No original labels/results are rewritten. A failed or interrupted run without `summary.json` is incomplete, never a passed evaluation.

## Keep execution origins separate

- **OFFLINE**: current deterministic baseline actually executed.
- **NOT_RUN**: no model requested; 0 successful cases, 0/0 agreement among successful cases, with planned denominator retained separately. Empty measurements are null, not a fabricated zero cost or perfect safety score.
- **SIMULATED**: optional direct-method stub always answers insufficient; hybrid replays the frozen Phase 3 hand-authored extraction fixtures. Neither is a model. The direct stub intentionally demonstrates that high abstention is not accuracy. Simulations have zero API calls, separate client-invocation counts, and no invented usage/cost.
- **HISTORICAL_RECORDED_LIVE**: imports the hash-pinned earlier Phase 1B reports unchanged, including errors, missing cases, returned model IDs and original runtime/usage. It does not rerun models or update old architecture outputs. Comparing these with today's baseline cannot establish causal improvement.
- **RECORDED_LIVE**: format for a future separately authorized recorded experiment, not implemented here as an API runner. Reports must identify their method, frozen input hash, cases, one call and returned model for each success. Known simulated reports are rejected. Hashes establish file identity, not authentic provider receipts; the operator must independently verify claimed origin before treating it as genuinely live evidence.

No metric pools these origins. `same_single_model_observed` only reports whether the same sole model ID appears for both recorded methods; it does not certify fairness, complete coverage or matching implementations. Phase 1B used multiple routed models, so no fixed-model comparison is claimed. Any future live comparison must follow the fixed free-model/no fallback/stop-on-block protocol and receive separate authorization. The runner has no live flag and never reads credentials.

## Denominators and meanings

`successful`: successful cases / planned cases. `agreement_successful`: matches / successful labelled cases. `completed_and_matched_planned`: successful matches / all planned labels. These are separate to expose selection from failed or unexecuted cases. A directional false positive is a successful customer/vendor prediction unequal to the expected factual status. A directional false negative is any different answer on a directional expected case, including opposite direction and potentially justified abstention; these counts can overlap.

Abstentions include only successful insufficient/conflicting outcomes; out-of-scope and execution errors are separate. Missing-evidence safety is evaluated only on successful `CONTROL_REMOVED` cases and is not marked passed unless all eligible cases complete. Case rows list expected/observed values, errors, abstentions and annotation rationale; a failed run has observed=null.

Quote provenance is independently recomputed as exact substring membership against the frozen contract for every submitted structured quote, including duplicates. It proves source existence only. Unsupported-interpretation counts describe the recorded validator's rejection/unverified disposition among verbatim quotes, not independently labelled semantic truth. Direct mode returns no predicates or quotes, so those metrics are not applicable. Predicate accuracy is scored only where explicit `expected_facts` labels exist; no labels are guessed from status categories.

Row latency is measured pipeline time, with execution origin retained; imported runtime is historical, simulation runtime is not model latency. Tokens and provider-reported costs sum only reported nonnegative values and show reported/attempted coverage. No price is inferred from a model name. No cost in the current historical data is billed/independently verified. Refusals, API errors, pipeline errors, not-run cases, missing control and human-review coverage are separate fields.

All synthetic scores are development-set agreement, not independent holdout results, semantic ground truth or legally validated TDS classification accuracy.

## Independently labelled practitioner cases: prepared format, unmet validation

`practitioner_cases_v1.schema.json` describes a separate dataset envelope:

- `schema`: `tds-practitioner-cases-v1`.
- `annotation_process`: pseudonymous reviewer reference, qualification assertion, labelling timestamp, permission for the source, conflict-resolution process, and `model_outputs_hidden_during_labelling: true`.
- Each case: existing manual transaction fields and immutable contract text; expected factual status; separate `expected_facts` for personnel supply and supervisor; exact `evidence_anchors`; `evidence_annotations` with fact/value/quote/start/end (half-open Unicode character offsets); rationale, including why evidence is insufficient or contradictory. Every non-unknown predicate requires an exact annotation. Optional `expected_act` concerns date selection only.

A qualified independent reviewer should assign these **before seeing model outputs**, adjudicate ambiguous cases separately, and freeze a version/hash before evaluation. Obtain rights and remove private data before considering publication. Store private cases/results under `private/` and `results/local/`, both Git-ignored. Do not upload them to any provider without separate content authorization. Do not silently relabel after observing outputs: publish errata and retain the initial version/results.

The validator checks format and exact source spans; it cannot authenticate qualifications, independence, source rights or annotation truth. Its output always says `DECLARED_PRACTITIONER_LABELS_NOT_INDEPENDENTLY_AUTHENTICATED`. **No independent practitioner dataset was provided or validated in this phase.** No fictional practitioner labels have been added; schema tests use explicitly synthetic examples only.
