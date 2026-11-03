# Run report — Phase 1B and initial submission, 3 November 2026

**The live evaluation is incomplete.** The 32-request protocol stopped after **5 requests**: **4 usable responses, 1 provider/client response failure, 27 unexecuted requests, and 0 retries**. The stop reason was `INVALID_PROVIDER_RESPONSE`, not HTTP 429. Partial results were preserved. Phase 1B made no further request, GitHub push or visibility change. Subsequent private GitHub submission checks are recorded below.

The unchanged automated suite subsequently passed **51/51 tests**. These findings are suitable for an explicitly partial-evaluation submission. They do not establish a completed three-method comparison, the live four-case safety target, or legally validated TDS-classification accuracy.

## Integrity and protocol

All 16 original synthetic cases, labels, dates and anchors are unchanged. `benchmark_manifest.json` is unchanged. The benchmark SHA-256 remains:

```text
a0744ad70703d0ddef563d7b713ffa604cffd927ba2a14675a4f7a7caf4f4699
```

Validation confirms 16 unique records, the requested variant mix, valid dates and **12/12** verbatim anchors. Historical reports—including the initial development failure, offline baseline, both HTTP 429 attempts and the successful smoke test—were preserved byte-for-byte. The previous README and run report were archived in the new Phase 1B directory before documentation updates.

Before requests began, passive metadata capture was added to `src/extraction.py` and `src/pipeline.py` for provider/model identifiers, finish reasons and explicit refusal metadata. `run_live_evaluation.py` added pacing, checkpoints and a stop shared by both methods. **No prompt, test, evidence interpretation rule or classification rule was changed for this evaluation. No implementation tuning followed the outputs.**

[protocol.json](results/phase1b/run-20261103-01/protocol.json) records code/test hashes, prompt hashes, historical file hashes and case order before the first request. [integrity.json](results/phase1b/run-20261103-01/integrity.json) verifies preservation afterward. The predeclared protocol used:

- Only `openrouter/free`; no paid-model fallback or alternate-model list.
- Dataset order, direct then hybrid for each case, maximum 32 calls.
- At least 15 seconds after each request completed before the next request. The minimum measured gap was **15.000172 seconds**.
- Existing prompts, temperature 0, maximum 1,400 output tokens and a 45-second request timeout.
- One call per case/method, zero retries. Any API/network/client block stopped both methods.
- Per-response checkpoints and explicit `NOT_RUN` records for unexecuted work.

OpenRouter documents its [free router](https://openrouter.ai/docs/guides/routing/routers/free-router) as selecting from available free models. Routing can vary, so this is not a fixed-model comparison. The ignored `.env` file was parsed as data without shell sourcing; values were loaded only into the evaluation process. No credential values were logged.

## Live outcomes

| Measure | Direct LLM | Hybrid extraction + rules |
| --- | --- | --- |
| Planned / attempted cases | **16 / 3** | **16 / 2** |
| Usable, schema-valid outputs / attempts | **2/3** | **2/2** |
| Request failures / attempts | **1/3** | **0/2** |
| Unexecuted cases | **13/16** | **14/16** |
| Status agreement, failed attempts counted incorrect | **2/3** | **1/2** |
| Status agreement on usable outputs only | **2/2** | **1/2** |
| Correct completed cases / planned cases (coverage) | **2/16** | **1/16** |
| Evidence-validation failure cases / usable outputs | Not applicable | **1/2** |
| Model-reported missing-fact cases | Not extracted | **0/2** |
| Validator-identified missing reliable supervision evidence | Not extracted | **1/2** |
| Verbatim submitted quotations | Quotes not requested | **4/4** |
| Fabricated / non-verbatim quotations | Not applicable | **0/4** |
| Quotes rejected for factual meaning | Not applicable | **1/4** |
| Entire frozen-anchor retrieval | Not applicable | **1/2** |
| Validated supervisor agreement | Not extracted | **1/2**, derived provisional targets |
| Explicit refusals observed / usable outputs | **0/2** | **0/2** |
| Failed requests with unavailable refusal status | **1** | **0** |
| Human review required / usable outputs | **2/2** | **2/2** |

There were **0 HTTP 429 errors among these 5 attempts**, **0 observed truncations among 4 usable responses**, and **0 retries**. Raw and wrapped direct-category agreement were both 2/3 when the failure is included. No independent personnel-supply labels exist, so no personnel extraction correctness score was invented.

Request 5, direct classification of `S01_CONTROL_REMOVED`, failed with `INVALID_PROVIDER_RESPONSE`. The client rejected the response before retaining content or model metadata. The exact HTTP status, underlying model, refusal status and detailed cause are unavailable. The retained diagnostic cannot distinguish an unexpected provider envelope from a client parsing incompatibility. This failure is not labelled HTTP 429, a refusal, or a successful abstention.

Total wall time including pacing and checkpoints was **103.264478 seconds**. This is a partial-run duration, not full-benchmark latency. Response timings and raw successful outputs are retained in `requests.jsonl`.

### Actual models and case outcomes

| Case | Method | Returned model | Outcome |
| --- | --- | --- | --- |
| `S01_CUSTOMER_CONTROL` | Direct | `dots-studio/dots-3-note-preview:free` | Correct customer-directed factual status |
| `S01_CUSTOMER_CONTROL` | Hybrid | `nvidia/nemotron-3.5-super-vl:free` | Supported extraction; correct customer-directed status |
| `S01_VENDOR_CONTROL` | Direct | `nvidia/nemotron-3.5-super-vl:free` | Correct vendor-directed factual status |
| `S01_VENDOR_CONTROL` | Hybrid | `xingchen-agi/xing4.0-29b-a4b:free` | Incorrect customer-supervisor assertion rejected; final status insufficient |
| `S01_CONTROL_REMOVED` | Direct | Unavailable | Provider/client response failure; global stop |

There were three observed model IDs: dots once, Nvidia twice and Xingchen once. **0/2** paired cases used the same model across methods. Architecture and model differences are confounded; these scores cannot establish hybrid improvement or direct-model superiority.

### Missing evidence and quote error

For `S01_VENDOR_CONTROL`, the hybrid model asserted customer supervision and quoted:

> Customer may communicate desired service results but shall not direct the individual engineers.

The quote was exact but contradicted the asserted fact. The validator rejected it, emitted two messages (failed factual-support check and unsupported supervisor assertion), and reduced supervision to unknown. The model omitted the actual supplier-supervision clause and reported no missing facts. Validation requested reliable supervision evidence and proposed no table item. This prevented accepting an unsupported customer-directed conclusion, but **did not recover the expected vendor-directed status**. The mismatch remains in the score; no fix or rerun was performed.

### Evidence-removed safety target

**NOT_EVALUATED for both live methods.** Direct attempted one of four evidence-removed cases but obtained no usable response; the other three were unexecuted. Hybrid attempted none. Both therefore have **0/4 usable evidence-removed outputs**, with a model false-confidence denominator of **0/0**.

The existing direct evaluator reports 0 false-confident final outputs / 1 attempted removed case because the failed request falls back to review. This is error handling, not successful model abstention: correct model abstentions were **0/1 attempts**. It must not be reported as 0/4 safety success. The contradiction, injection, old-Act crossover and nonresident edge cases were not reached in this live run.

## Earlier runs, preserved unchanged

| Stage | Actual result | Evidence |
| --- | --- | --- |
| Initial offline development baseline | **13/16** agreement; **1/4** false-confident removed decisions | `results/development/initial_baseline.json` and CSV |
| Corrected offline baseline | **16/16** agreement; **0/4** false-confident removed decisions; **29/29** verbatim quotes; **8/12** entire anchors | `results/baseline.json` and CSV |
| Earlier direct live attempt | **1 request**, HTTP 429, **0 usable outputs**, 15 unexecuted cases | `results/direct-llm.json` |
| Earlier hybrid live attempt | **1 request**, HTTP 429, **0 usable outputs**, 15 unexecuted cases | `results/hybrid.json` |
| One-case smoke test | **1 request**, **1 valid matching output**, **0 retries**, **7.378189 seconds** | `results/local/tds-one-case-smoke-lh5fv9i6.json` (Git-ignored) |

Both HTTP 429 attempts requested `google/gemma-4-26b-a4b-it:free`; no serving model was recorded. The later smoke test requested `openrouter/free`, returned `cohere/north-mini-code:free`, and correctly classified `S01_CUSTOMER_CONTROL`. The smoke result is excluded from Phase 1B scores. Earlier no-credential runs described in the archived report were NOT_RUN; the subsequent HTTP 429 artifacts already existed before this phase and were not overwritten here.

The initial offline implementation confused supplying engineers with supervising them. It was corrected and regression-tested during development, with labels unchanged. The baseline's four remaining full-anchor retrieval misses are the multi-sentence vendor anchors; it quotes the decisive supervision sentence. These are visible development-set results, not held-out validation.

## Commands and post-run tests

These commands were actually executed for this phase:

```bash
git status --short
git remote -v
git check-ignore -v .env
python -m unittest discover -v > /tmp/tds-phase1b-preflight-tests.txt 2>&1
python -m py_compile run_live_evaluation.py
python -u run_live_evaluation.py --env-file .env --output-dir results/phase1b/run-20261103-01
python -m unittest discover -v > results/phase1b/run-20261103-01/test_run.txt 2>&1
python -m compileall -q main.py run_live_evaluation.py src tests
git ls-files --stage
git diff --cached --name-only -z
git rev-list --all
git ls-files --others --exclude-standard
git ls-files --others --ignored --exclude-standard
```

Additional read-only scripts validated the benchmark, checked hashes, aggregated recorded responses and scanned Git-eligible and ignored files without printing secret values. The evaluation command exited **1** for the global stop, not success for a completed benchmark.

Preflight tests: **51/51 passed**. After the evaluation: **51/51 passed, 0 failed, 0 skipped**, in **0.043 seconds**, using Python **3.13.12**. [Post-run output](results/phase1b/run-20261103-01/test_run.txt). The test files were unchanged. Coverage includes dates, provenance, negation, contradictions, injection, scope, malformed records, dataset integrity, redaction and mocked LLM failures. Mocks are not model-performance measurements. Python 3.8 runtime testing remains unperformed.

## Read-only Git security audit

[Audit details](results/phase1b/run-20261103-01/git_security_audit.json) contain the inventory and bounded exact-key/pattern checks. At the Phase 1B audit, Git had **0 tracked files, 0 staged files and 0 local commits**; these are historical pre-submission counts. The audit did not mutate the Git index, commits, configuration or remote visibility.

**A real API key exists locally in `.env`.** That file is Git-ignored, untracked, unstaged and restricted to **0600**. The key was found only there. **0 secret findings** occurred in Git-eligible source, data, documentation and result candidates. No confidential assignment document, financial document, document attachment/archive or unexpected candidate file was found. The result content inspected is synthetic. Ignored Python caches and the local smoke report are expected generated files.

The scan is bounded, not proof that every sensitive string could be detected. At that audit there was no committed history to scan, and remote contents and visibility were not queried. Exclude `.env` from submission archives: Git ignore rules do not protect a manually zipped working directory. No push was performed during Phase 1B.

## Files, limitations and submission readiness

The original CLI, schema adapter, evidence checks, static rules, metrics, tests, dataset and manifest remain. This phase added `run_live_evaluation.py`, passive response metadata fields, and `results/phase1b/run-20261103-01/` with protocol, request log, per-method JSON/CSV, integrity check, summary, post-run tests, audit and archived documentation. README and this report now reflect the partial live findings. No frontend or infrastructure was added.

The prototype is **submission-ready as an explicitly partial live evaluation**, provided the PDF retains the failure, denominators, absent safety coverage and mixed-model limitation. It is **not ready to claim a completed full live benchmark, independently validated factual accuracy, or tax-classification accuracy**. The offline benchmark, smoke test, live interpretation error and deterministic rejection are usable evidence of implemented behavior.

Legal mappings remain provisional and require qualified human review. Rates, thresholds, exemptions, treaties, comprehensive payer eligibility, nonresident treatment, old-Act category mapping, actual working-practice verification and final tax actions remain unimplemented. Official-source verification is not practitioner validation. The visible synthetic development set, limited lexical checks, incomplete coverage and variable models limit generalization. No license has been selected. The initial submission is intended for the existing private repository; visibility must remain private. Any future evaluation must have a distinct run identity and preserve these artifacts.

See [README.md](README.md) for architecture, commands and primary sources, and [summary.json](results/phase1b/run-20261103-01/summary.json) for machine-readable counts.


## Initial private GitHub submission

Release preparation reran `python -m unittest discover -v`: **51 tests passed, 0 failed, 0 skipped**, in **0.033 seconds**, on Python 3.13.12. The output is preserved separately at [results/release/test_run.txt](results/release/test_run.txt); historical test logs were not overwritten. `python main.py --validate-benchmark` again returned VALID. No source, test or evaluation-result changes were made for release, and no LLM/API experiment was run.

The GitHub read-only repository check confirmed `private: true`, default branch `main`, and the configured repository `korakdas1/tds-evidence-review`. `git ls-remote --heads origin` found no remote branches before the initial commit. The release must not change repository visibility.

A fresh pre-commit [security audit](results/release/security_audit.json) covers the exact-key and credential-pattern checks, candidate inventory, exclusions and preservation hashes. `.env` remains local, ignored and excluded, as do caches and local reports. No private financial data, confidential assignment document, private conversation log or unrelated file was identified in the reviewed submission files. The included raw model responses concern only the existing synthetic cases. The committed [file inventory](results/release/files.txt) identifies the intended submission files; the staged blobs are checked again before committing.

Only README/RUN_REPORT release-status wording and new release-check artifacts were added to the preserved prototype. Historical reports, including their original timestamps, failures, incomplete-run results and old pre-submission Git counts, retain their original bytes. The exact initial commit and remote verification are reported through Git history and the final release handoff, rather than a self-referential commit SHA inside this file.

Public-readiness: suitable for optional public viewing **as a synthetic prototype and partial live evaluation**, with its documented failures, varying models and untested safety coverage. It is not a validated compliance system or a completed live benchmark. No open-source license has been selected. The repository must remain private until the owner separately decides whether to make it public.
