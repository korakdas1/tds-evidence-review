# Evidence-Backed TDS Classification Review

A small Python prototype that reviews contractual evidence about who directs supplied workers. An invoice alone often omits this information. The tool returns a **factual-evidence status**, exact contract quotations, a date-based Act selection, and—only where supported—a **provisional** contract-work table reference for a qualified human reviewer.

It never determines a final tax treatment, calculates tax, authorizes withholding, or files returns. All included evaluation cases are synthetic, AI-authored, and not practitioner validated.

## Run locally

Python 3.8+; standard library only. No packages, API keys, frontend, database, or paid service are required for the baseline. Executed here on Python 3.13.12; Python 3.8 grammar compatibility was checked, but a Python 3.8 interpreter was not available for runtime testing.

```bash
# From the existing project folder:
python main.py --validate-benchmark
python main.py --input tresata_adversarial_cases.json --mode baseline
python -m unittest discover -v
```

An optional virtual environment can be created with `python -m venv .venv`; there is nothing to install with pip.

The baseline writes `results/baseline.json` and `results/baseline.csv`, and prints one line per case. Use `--output path/report.json` for another destination. Arbitrary inputs default to ignored `results/local/`. A batch continues after malformed records. Exit codes: `0` completed or explicitly `NOT_RUN`, `1` per-record input/model errors, `2` file, JSON, integrity or output error. Evidence warnings route for review without crashing the run.

## Input and frozen benchmark

The existing `tresata_adversarial_cases.json` was inspected, validated, and preserved **byte-for-byte**. No cases, anchors, dates or expected labels were changed. Its digest is pinned in `benchmark_manifest.json`:

```text
a0744ad70703d0ddef563d7b713ffa604cffd927ba2a14675a4f7a7caf4f4699
```

It contains 16 cases: four scenarios with customer-control, vendor-control and control-removed variants, plus conflict, injection, date-crossover and nonresident cases. All 12 supplied evidence anchors occur exactly in their contracts. The validator also checks IDs, dates, expected statuses, scenario groups and matching invoice descriptions. A hash mismatch blocks execution against the frozen benchmark. Dataset corrections would require a separately documented version and a fresh evaluation; do not change this manifest to conceal edits.

Input may be an object containing `cases`, as in the supplied dataset, or a nonempty array of records. The existing flat schema is used directly:

```json
{
  "id": "example-1",
  "invoice_description": "Monthly staffing service",
  "contract_excerpt": "Supplier supplies workers. Customer supervises workers.",
  "payer_type": "Indian resident private company",
  "payee_residency": "India resident",
  "payee_legal_form": "Indian resident private company",
  "credit_date": "2026-04-01",
  "payment_date": "2026-04-02"
}
```

Wrap this record in an array for a custom file. The six non-date transaction fields are nonempty strings; both dates must be valid `YYYY-MM-DD` strings to resolve the Act. Missing dates produce `NEEDS_DATE_REVIEW` and block any table proposal. Residency recognizes explicit resident/nonresident values; an unknown value requires review. Payer eligibility is not inferred from arbitrary text: the provisional proposal is restricted to the declared company payer type shown above.

Benchmark metadata (`expected_fact_status`, `expected_act`, `evidence_anchors`, `variant`, `scenario`, `label_note`) is consumed only by evaluation. Neither those fields nor the case ID, which can encode a label, are passed to extractors or the model.

## Architecture and three methods

```text
JSON -> input validation -> chosen method -> evidence checks -> date/scope rules
                                            -> human-review report -> evaluation
```

| Component | Implementation |
| --- | --- |
| Input / benchmark integrity | `src/schema.py`, `benchmark_manifest.json` |
| Extraction / optional HTTP | `src/extraction.py` |
| Exact quotes / lexical guard | `src/evidence.py` |
| Date selection / provisional mapping | `src/rules.py`, `src/rules_v1.json` |
| Batch isolation / reporting | `src/pipeline.py`, `main.py` |
| Metrics | `src/evaluation.py` |

1. **`baseline`**: Python patterns recognize personnel supply and individual-worker supervision, handle conservative negation and conflict checks, and abstain when no decisive clause is found. No LLM call.
2. **`direct-llm`**: One call proposes a factual category directly. Raw output is retained. It receives the same transaction fields but does not extract predicates or quotes, so it cannot propose a legal table item. The deterministic residency/date wrapper remains active; raw-category agreement is separately reported so scope overrides cannot hide model errors.
3. **`hybrid`**: One call extracts `personnel_supplied`, `worker_supervisor`, `supporting_quotes`, `missing_facts` and `contradictory_evidence`. Python validates the schema, exact provenance and conservative factual support, then applies the deterministic rules. There are no repair calls, retries, agent chains or runtime legal retrieval.

Every asserted predicate needs a supporting quote with `fact`, `value`, and `quote`. Exact matches use zero-based Python character offsets, with an exclusive end; repeated passages have all locations recorded. The validator checks complete surrounding sentences to reject clipped negation and distinguishes known quality-monitoring patterns from worker control. It flags recognized omitted contradictions and includes their locations as separate deterministic findings. Unsupported assertions block confident output. Embedded instruction patterns trigger review; strict output schemas reject extra legal/rate fields.

These lexical checks are deliberately narrow. A verbatim quote proves provenance, **not** correct interpretation. Prompt separation, schema validation and pattern detection are safeguards, not a guarantee against all adversarial wording. Actual working practices may differ from the contract.

## Optional OpenRouter experiments

Both environment variables must be explicitly set. No `.env` file is automatically loaded. Enter a key through your environment or secret manager; do not put it in source files or command history. For Bash:

```bash
read -rsp 'OpenRouter API key: ' OPENROUTER_API_KEY; echo
export OPENROUTER_API_KEY
export OPENROUTER_MODEL='your-chosen-available-model:free'
python main.py --input tresata_adversarial_cases.json --mode direct-llm
python main.py --input tresata_adversarial_cases.json --mode hybrid
unset OPENROUTER_API_KEY
```

The model string is a placeholder, not a claim that a particular free model is currently available. Select a model with JSON-object response support. No automatic fallback selects another or paid model. Each full method run makes at most one call per valid record; running both methods can make up to 32 calls on this dataset. Configuration opts in to sending those transaction fields to OpenRouter and its provider.

The HTTP client uses the documented [Chat Completions interface](https://openrouter.ai/docs/api_reference/overview), a 45-second request timeout, bounded response reads and no redirects. Missing configuration yields `NOT_RUN` with zero calls. Authentication, availability, quota or network failures stop further requests in that batch and record `NOT_RUN`, the sanitized reason and actual attempted-call count. Invalid model JSON is retained as raw output and counted as an execution error. No provider error bodies or authorization headers are logged. Any echoed configured key is redacted. [API error reference](https://openrouter.ai/docs/api_reference/errors-and-debugging).

## Reading results

Each JSON record includes its ID, execution status, Act/trigger date, extracted and validated facts, quotes and positions, factual status, missing information, validation failures, provisional reference when permitted, versioned sources, runtime and mandatory human-review flag. Always check `run_status` first: fallback statuses in a `NOT_RUN` record are **not model predictions**.

The five factual statuses are:

| Status | Meaning |
| --- | --- |
| `EVIDENCE_SUPPORTS_CUSTOMER_DIRECTED_MANPOWER` | Evidence supports supply of personnel with recipient direction of workers |
| `EVIDENCE_INDICATES_VENDOR_DIRECTED_SERVICE` | Evidence indicates vendor direction of workers; no automatic professional-services inference |
| `INSUFFICIENT_TO_ESTABLISH_CONTROL` | Decisive support is absent or rejected |
| `CONFLICTING_EVIDENCE` | Opposing supported facts require resolution |
| `OUT_OF_SCOPE` | Nonresident vendor; resident-payment prototype cannot map treatment |

All outputs require qualified human review. Old-Act transactions receive an Act selection but no old-Act category mapping. No rates or thresholds are implemented.

Metrics include exact numerators, denominators, units and reasons for unavailable scores. Supervisor agreement is derived from provisional factual labels; there are no independent personnel-supply labels, so that metric is not scored. Quote validity counts all submitted quotes, including rejected or duplicate entries. Full-anchor retrieval requires the entire supplied anchor inside one accepted quote. A zero denominator is `NOT_SCORED`, not a perfect score. Model execution failures count against labelled-case agreement; unavailable runs are excluded and clearly marked. The safety target can pass only if all four evidence-removed cases executed successfully.

## Actual results

The final offline baseline agreed with **16/16** provisional statuses, had **0/4** false-confident evidence-removed decisions, verified **29/29** submitted quote entries, and retrieved **8/12** entire frozen anchors. **51 automated tests passed**. Direct-LLM and hybrid live experiments were **NOT_RUN** because neither OpenRouter variable was configured; no model was used. Mocked integration tests are not model measurements.

The first development baseline scored **13/16** with **1/4** false-confident evidence-removed decisions. Its reports are preserved under `results/development/`. The implementation was corrected after that run; the labels were unchanged. This is a visible development benchmark, not a held-out accuracy estimate. See [RUN_REPORT.md](RUN_REPORT.md) for commands, results and failures.

## Primary legal sources and limits

Source text was checked on 3 November 2026 and recorded in `src/rules_v1.json`:

- [Finance Act, 2026](https://www.incometaxindia.gov.in/documents/d/guest/finance-act-2026-pdf-1), Section 90(b), Gazette page 58: the manpower addition to Section 402(47).
- [Amended Income-tax Act, 2025](https://www.incometaxindia.gov.in/documents/d/guest/income_tax_act_2025_as_amended_by_fa_act_2026-pdf), Sections 1(3), 393(1) Table 6(i)/6(iii), and 402(47)(f). Relevant PDF pages are 1, 471–472 and 508–509, using one-based page numbers.
- [Income Tax Department transition FAQs](https://www.incometax.gov.in/iec/foportal/help/all-topics/e-filing-services/tds-compliance): the earlier credit/payment event selects the Act across 1 April 2026.

Official-source verification is not practitioner validation of the factual-to-legal mapping. Any table proposal is explicitly provisional. The static rules require deliberate maintenance for later changes. The prototype does not assess exemptions, thresholds, payer eligibility beyond its narrow declared-company gate, treaty issues, professional-services qualification, contract precedence, or real working practices.

No frontend, production infrastructure, autonomous tax action or public deployment is included. The repository contains synthetic fixtures and prototype code; keep real contracts and private reports in ignored locations. Raw outputs on real inputs may themselves contain private text. Git is initialized with the requested GitHub remote; nothing has been pushed.
