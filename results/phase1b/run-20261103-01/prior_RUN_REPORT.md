# Run report — 3 November 2026

The minimum prototype is implemented and runs offline. **51 automated tests passed.** The final baseline agreed with **16/16 synthetic provisional factual labels** and made **0/4 false-confident decisions** on the evidence-removed cases. No live model ran. These are development-set factual results, not validated tax-classification accuracy.

## Dataset integrity

The user-provided `tresata_adversarial_cases.json` existed before implementation. It was inspected first and never rewritten. Its SHA-256 before and after development is:

```text
a0744ad70703d0ddef563d7b713ffa604cffd927ba2a14675a4f7a7caf4f4699
```

Validation: **16/16** records have unique IDs, valid required content and dates, accepted provisional labels and synthetic flags. **12/12** evidence anchors are exact substrings. The four scenario groups each contain the three requested variants with identical invoice descriptions and a common contract prefix. Four additional edge cases are present. **No adjustments to cases or labels were necessary.** The flat payer/payee schema is supported by code. [Validation artifact](results/benchmark_validation.json).

The hash was recorded in `benchmark_manifest.json` before any evaluation. Label metadata and IDs are excluded from extractor/model input. Source-file hashes are included in the final result JSON for reproducibility. The initial development artifact predates that source-hash feature.

## Files and implemented features

| Files | Purpose |
| --- | --- |
| `main.py`, `src/__init__.py` | CLI, JSON/CSV output, batch exit status |
| `src/schema.py`, `benchmark_manifest.json` | Existing-schema adapter, validation, frozen-data integrity |
| `src/extraction.py` | Keyword baseline, single-call direct/hybrid prompts and optional standard-library OpenRouter client |
| `src/evidence.py` | Quote locations, factual support checks, conservative negation/quality-control/injection checks, contradiction detection |
| `src/rules.py`, `src/rules_v1.json` | Earlier-event Act selection, residency gate, versioned static sources and provisional mapping |
| `src/pipeline.py`, `src/evaluation.py` | Record isolation, retained raw model output, review reports, denominated metrics |
| `tests/__init__.py`, `tests/test_core.py`, `tests/test_llm.py` | Offline unit and mocked integration tests |
| `.gitignore`, `README.md`, `RUN_REPORT.md` | Python/private-file exclusions, usage, limitations and this report |
| `results/baseline.{json,csv}` | Final offline benchmark |
| `results/direct-llm.{json,csv}`, `results/hybrid.{json,csv}` | Explicit `NOT_RUN` records |
| `results/*_console.txt`, `results/test_run.txt`, `results/benchmark_validation.json` | Captured command output and integrity evidence |
| `results/development/initial_baseline.{json,csv}` | Preserved first-run failure |

The benchmark JSON was retained, not created. `.git` was initialized on branch `main`; `origin` is `https://github.com/korakdas1/tds-evidence-review.git`. Git initialization initially hit the workspace's read-only `.git` mount and then succeeded using the authorized elevated command. **No commit or push was made; remote visibility was not changed or independently checked.** No frontend or deployment was created.

## Commands actually executed

From the project directory:

```bash
git init -b main
git remote add origin https://github.com/korakdas1/tds-evidence-review.git
git status --short
git remote -v
sha256sum tresata_adversarial_cases.json
python main.py --validate-benchmark
python main.py --input tresata_adversarial_cases.json --mode baseline
python main.py --input tresata_adversarial_cases.json --mode direct-llm
python main.py --input tresata_adversarial_cases.json --mode hybrid
python -m unittest discover -v
python -m compileall -q main.py src
git diff --check
```

The final tests and runs were captured with these actual commands:

```bash
python -m unittest discover -v > results/test_run.txt 2>&1
python main.py --validate-benchmark > results/benchmark_validation.json
python main.py --input tresata_adversarial_cases.json --mode baseline > results/baseline_console.txt
python main.py --input tresata_adversarial_cases.json --mode direct-llm > results/direct-llm_console.txt
python main.py --input tresata_adversarial_cases.json --mode hybrid > results/hybrid_console.txt
```

Additional local inspection scripts checked schema/counts/anchors, read saved metrics, and parsed every Python file using `ast.parse(..., feature_version=(3, 8))`. Runtime: **Python 3.13.12**. Python 3.8 grammar parsing passed; execution under Python 3.8 was **not tested**. No third-party packages were installed. Primary-source text and the OpenRouter request/error documentation were checked through browsing during development; the application itself does not retrieve legal rules.

## Automated tests

Final recorded run: **51 tests, 51 passed, 0 failed, 0 skipped**, in **0.030 seconds**. [Full output](results/test_run.txt).

Coverage includes the April 1 boundary, both earlier-event orders, missing/invalid dates, exact/repeated/Unicode quote locations, fabricated and semantically unsupported quotes, clipped negation, supply versus task allocation, service-quality monitoring, conditional clauses, contradictions and omitted opposing evidence, embedded instructions, missing control, scope/residency, malformed records and annotations, duplicate IDs, frozen hashes and overwrite protection.

OpenRouter tests use mocks: they verify request field isolation, raw-output retention, one-call behavior, unsupported model schema, malformed provider output, missing credentials, unavailable models, HTTP errors, timeouts, redirects and secret redaction. **Mock responses do not establish model quality or live-provider compatibility.**

## Actual benchmark outcomes

All denominators below refer to the final offline run unless stated otherwise.

| Metric | Offline baseline | Direct LLM | Hybrid |
| --- | --- | --- | --- |
| Provisional factual-status agreement | **16/16** | NOT_RUN, 0/0 evaluated; 16 eligible | NOT_RUN, 0/0 evaluated; 16 eligible |
| Supported supervisor agreement | **15/15** | Not applicable to category-only output | NOT_RUN |
| Personnel-supply correctness | Not scored, 0/0 independently labelled | Not scored | Not scored |
| False-confident evidence-removed decisions | **0/4** | NOT_EVALUATED | NOT_EVALUATED |
| Correct evidence-removed abstention | **4/4** | NOT_RUN | NOT_RUN |
| Contradiction handling | **1/1** | NOT_RUN | NOT_RUN |
| Exact quote provenance | **29/29 submitted entries** | Quotes not requested | NOT_RUN |
| Entire frozen-anchor retrieval | **8/12 anchors** | Quotes not requested | NOT_RUN |
| Applicable-Act agreement | **16/16** | Not scored as a model experiment | Not scored as a model experiment |
| Old-Act crossover | **1/1** | NOT_RUN | NOT_RUN |
| Nonresident scope handling | **1/1** | NOT_RUN | NOT_RUN |
| Injection abstention | **1/1** | NOT_RUN | NOT_RUN |
| Human review required | **16/16** | Fallback reports require review | Fallback reports require review |
| Factual abstention / conflict / out-of-scope | **7/16** | NOT_RUN | NOT_RUN |
| Per-record execution errors | **0/16** | 0/0 attempted records | 0/0 attempted records |
| API errors / calls | **0/0**, no calls | **0/0**, no calls | **0/0**, no calls |

The supervisor metric derives expected customer/vendor/unknown/conflicting values from the frozen factual statuses; the nonresident case has no supervisor target and is excluded. This is not independently annotated extraction accuracy. No separate personnel-supply ground truth exists, so no score was invented. Exact quote entries include repeated quotations used for different predicates or contradictions.

Recorded batch-processing time was **0.006392 seconds for 16 baseline records**. This excludes interpreter startup and output serialization. Direct/hybrid skipped-run overhead was 0.000181 / 0.000176 seconds respectively, **not inference latency**. Model actually used: **none**. Neither `OPENROUTER_API_KEY` nor `OPENROUTER_MODEL` was configured. Saved LLM reports contain `NOT_RUN`, `OPENROUTER_NOT_CONFIGURED`, zero API calls and no invented predictions or measurements. Deterministic date/scope fallbacks still appear in those reports but are not scored as model results.

The baseline meets the predefined small-test safety target. It does not establish production reliability or comparative superiority over either unrun LLM method.

## Failures and limitations

The **first development run** scored **13/16**, with **1/4 false-confident decisions** on evidence-removed cases. It confused assigning engineers to a customer with supervising their work. This caused an erroneous vendor-control outcome for `S01_CONTROL_REMOVED` and spurious conflicts for `S01_CUSTOMER_CONTROL` and `X03_OLD_ACT_CREDIT`. The original artifacts are preserved. The code was corrected to distinguish assignment of personnel from assignment of tasks, and regression tests were added. The benchmark was not changed. The final score therefore measures performance on a visible development set, not an independent holdout.

Full-anchor retrieval remains **8/12**: each of the four vendor-control anchors combines a supervision sentence with a second sentence about service outcomes. The baseline quotes the decisive supervision sentence but does not return the entire combined anchor. This remains a reported retrieval miss, despite correct factual-status agreement. The injection case raises one intentional validation warning and abstains. There were no final execution errors.

The lexical semantic guard has limited English vocabulary and cannot establish general entailment, robust party resolution, contractual precedence or resistance to every prompt injection. It may abstain on valid unfamiliar wording and may misinterpret wording outside the tested patterns. Known role aliases include “conference organiser”; real party identities require review. Exact provenance is not semantic proof. Working practice is not verified against the contract.

Official statutory references and transition guidance were checked, but the proposed mapping has **not been validated by a chartered accountant or other qualified practitioner**. Vendor direction does not automatically mean professional/technical services. Rates, thresholds, exemptions, certificates, treaties, comprehensive payer eligibility, nonresident treatment, old-Act category mapping and final tax calculations are unimplemented. Static rules require maintenance. There is no production security assurance, frontend or deployment.

## Release and take-home suitability

The code and saved synthetic artifacts are ready for owner review and publication **as a clearly limited prototype**, not as a compliance product. The intended files contain code, synthetic cases, public-source references and test/evaluation outputs; no employer assignment document, personal financial data, real credentials or private conversation logs were included. Private input/output folders and credentials are ignored. No open-source license has been selected, and nothing has been pushed or made public.

The take-home PDF can accurately include the architecture, preserved benchmark hash, 51 passing tests, the final denominated offline metrics, initial failure and correction, and the LLM `NOT_RUN` status. It must retain the synthetic/provisional-label and development-set limitations. It cannot claim live LLM performance, hybrid improvement, validated legal accuracy or production readiness.

Sources and reproducible commands are in [README.md](README.md); row-level evidence is in [results/baseline.json](results/baseline.json).
