# Evidence-Backed TDS Review (local prototype)

A local application and Python toolkit for checking what a vendor contract says about **who supplies workers and who supervises them**. That is the fact an invoice usually leaves out. For each contract it gives:
- a factual-evidence status;
- the exact quotations it relied on, with page and character references;
- the Income-tax Act selected by date;
- a separate human-review record.

Nothing in this repository determines tax treatment, calculates tax, authorises withholding or files returns. Every result requires review by a qualified person. All included documents and evaluation cases are synthetic and not practitioner-validated.

**Branches:** the submitted version is [`e075a9087b8f4dbebee3fe74f2cb427c5bc3a3c0`](https://github.com/korakdas1/tds-evidence-review/commit/e075a9087b8f4dbebee3fe74f2cb427c5bc3a3c0) on `main`. Post-submission development (Phases 3–6) is on `feature/full-product`.

## Quick start

You need Python 3.9 or later for the review app and PDF support (the JSON command-line baseline alone runs on 3.8). After installation nothing needs internet access, an API key or a paid service.

```bash
git clone https://github.com/korakdas1/tds-evidence-review.git
cd tds-evidence-review
git checkout feature/full-product
python -m venv .venv
source .venv/bin/activate              # Windows: .venv\Scripts\activate
python -m pip install -r requirements-pdf.txt   # pypdf 6.21.4, the only dependency
```

| To... | Run | Expect |
|---|---|---|
| Launch the review app | `python review_app.py --open` | Opens http://127.0.0.1:8765/ in your browser (this computer only) |
| Run the offline demo | `python demo.py` | Three JSON examples, including a replayed historical model mistake |
| Run the offline PDF demo | `python pdf_demo.py` | A synthetic PDF with page and character offsets; proposal withheld |
| Run all automated tests | `python -m unittest discover -v` | 155 tests, all passing, no network use |

App options:
- `--port 8765`
- `--data-dir local_data`: uploads and the review database; Git-ignored and private to your user account.
- `--max-storage-mb 512`: upload quota.

The app refuses to listen on anything except a loopback address.

### A five-minute synthetic walkthrough

1. Launch the app and open **Warehouse manpower support** under *Synthetic samples*.
2. Click a page reference on an evidence card. The exact sentence is highlighted in the extracted text. Switch to **Original PDF** to compare.
3. Answer the two review questions on a card. Your decision is stamped with your name and time.
4. Open **Event crew with unfamiliar wording** to see an *AI suggestion* kept apart from validated facts.
5. Open **Plant maintenance with conflicting clauses** to see contradictions.
6. Use **Correct details and run again** (Transaction tab) and **History** to see how re-runs and decisions are recorded.

## How analysis works today

- **Normal workflow: offline rule checks.** The contract text is read by the existing conservative, deterministic checks. No AI model is involved, so normal runs produce no AI suggestions.
- **AI-suggestion demonstration: simulated extraction.** The *Event crew* sample, and the advanced option *Replay a supplied extraction*, pass a hand-written extraction in a model's output format through the same validators. No model is called; the run records 0 model network calls and is labelled simulated.
- **Live model experiments** exist only as separate, opt-in research scripts (see *Optional OpenRouter experiments* below). They are not connected to the app and need explicit credentials and authorisation.

## Evidence states

| Shown as | Meaning | Can it support an automated finding? |
|---|---|---|
| Validated by rule checks (green) | An exact quotation passed the conservative pattern checks | Yes, for the factual status only. It never proves actual working practice. |
| AI suggestion, review only (violet) | An exact quotation an extraction proposed but the rules could not confirm | No. A lead for a person to judge. |
| Contradiction (red) | Clauses point to different supervisors | No. The finding becomes *conflicting* until a person resolves it. |
| Missing information (amber) | Facts the checks could not establish | No. |
| Rejected by a safety check (grey) | Blocked, for example negated, conditional or inoperative text, or an embedded instruction | No. Kept visible for audit. |
| On hold (amber note) | The document needs a visual check: scan, layout disagreement, cross-page quotation | No, until the document problem is resolved. |

**Mandatory human review.** Every case is marked as requiring review. Reviewer decisions are recorded separately and never change the automated findings. Confirming a quotation only confirms the words. The app has no "approve" option, and every statutory proposal from a PDF is withheld.

## What the application cannot do

- Decide the tax treatment, rate or amount; authorise withholding; or file anything.
- Read scanned pages (no OCR), password-protected PDFs, or files over 5 MiB or 20 pages.
- Guarantee reading order or completeness. Extracted text is not proof of what the printed page shows, so a reviewer must compare with the original.
- Place highlights on the printed page. Highlights mark character positions in the extracted text.
- Understand wording outside its narrow patterns. Unfamiliar but true facts may be reported as missing.
- Verify what happens in practice, as opposed to what the contract says.
- Provide multi-user accounts. Reviewer names are self-declared on one computer.
- Provide tamper-proof records. The history is hash-chained and checked, but it is unsigned local SQLite; see below.
- Infer any fact from an invoice. Invoices are shown for inspection only.

## Data, integrity and privacy

- **Where data lives.** Uploads and the database are stored only in `--data-dir`, with folders 0700 and files 0600. Uploads are capped by `--max-storage-mb`, and identical uploads are stored once.
- **Integrity checks.** Every analysis run is stored with its SHA-256 and anchored in a hash-chained review history. Each time a case is opened, the server re-checks:
  - the run's hash;
  - the history anchor;
  - the chain links;
  - the case record;
  - the stored PDFs.
- **Fail-closed behaviour.** If an analysis check fails, the API withholds the finding, evidence and page text and returns diagnostics only. Exports put such runs in a clearly marked `forensic_untrusted` section.
- **Unavailable PDFs.** If only a stored PDF is damaged, the analysis stays visible but PDF-based checks are disabled. Re-uploading the identical file restores it.
- **Limits of tamper evidence.** Someone with file access who recomputes every hash can still forge a consistent database, and deleting the newest history entries cannot be detected without an external copy. Treat this as tamper-evident, not tamper-proof.

## Rule versioning

Act selection lives in [`src/act_selection_v1.json`](src/act_selection_v1.json), version `act_selection@1.0.0`:
- **Rule:** the earlier of the credit and payment dates selects the Act; both dates are required; before 1 April 2026 is the 1961 Act, from then on the 2025 Act.
- **Load-time checks:** the file is validated when loaded (contiguous periods, a supported trigger, agreement with the cited `act_transition` source in [`src/rules_v1.json`](src/rules_v1.json)). An invalid file stops the program instead of guessing.
- **Traceability:** every date result carries `rule_version`, and both rule files are included in run implementation hashes.
- **Scope:** the configuration holds only Act periods. It contains no rates, thresholds or classifications, and it is not independently legally validated.

## Command-line demos

### Quick Demo

From the repository folder, with Python 3.8+:

```bash
python demo.py
```

No installation, internet, API key or other credentials are needed. The demo prints three short examples: a supported customer-directed case with its exact quote, a missing-supervision case that abstains, and the **replayed historical** `S01_VENDOR_CONTROL` LLM mistake. In that saved response, an exact quotation contradicted the asserted supervision; validation rejected it and required review.

The first two examples run the current deterministic pipeline. The third reads the unchanged Phase 1B artifact, clearly marked as a replay rather than a fresh model result. All three require human review; none establishes legally validated tax treatment. The demo does not write datasets or result files. See [DEMO_WALKTHROUGH.md](DEMO_WALKTHROUGH.md) for the underlying commands and evidence.

### Offline PDF demo (optional dependency)

Phase 4 adds local PDF provenance on `feature/full-product`. The original JSON interface and submitted `main` are unchanged. See [PHASE_4_REPORT.md](PHASE_4_REPORT.md) for actual results and limitations.

Use Python 3.9+ for the optional PDF dependency:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-pdf.txt
python pdf_demo.py
```

After installation, the demo works offline without credentials, API calls, OCR or external commands. It prints the synthetic document name/hash, page and exact extracted quote offsets, factual finding, and mandatory human review. All PDF-derived statutory proposals are withheld pending visual review; exact source mapping does not establish interpretation or legal validity.

For your own public or synthetic document, supply manual transaction metadata using the input fields below, omitting `contract_excerpt`. The optional invoice is extracted separately; dates, residency, payer and invoice description are never inferred from it:

```bash
python pdf_demo.py --contract contract.pdf --metadata transaction.json --invoice invoice.pdf --output results/local/my-pdf.json
python evaluate_pdfs.py --output-dir results/local/pdf-evaluation-new
```

Output destinations must be new. PDFs are limited to 5 MiB and 20 pages, with further extracted-text limits. Scans, malformed/encrypted files, extraction-order disagreements and incomplete pages require review. Cross-page quotations retain separate page fragments and require visual review. Offsets address extracted Unicode text, not PDF glyph or pixel coordinates. See [ARCHITECTURE.md](ARCHITECTURE.md) and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

Phase 4 validation: **113/113 tests passed** (87 preserved + 26 new); the original 87 also passed with site packages disabled. PDF fixtures: **19/19 expected outcomes**, comprising 9 extracted, 7 requiring document review and 3 rejected; **25/25 evidence items mapped, 26/26 page fragments verified, 10/10 invalid-location probes rejected**. No live LLM calls occurred. Original baseline agreement remains 16/16, 12/12 and 9/12 on the three historical synthetic sets. These are development checks, not independent model or legally validated accuracy.

## Project history and reports

[ARCHITECTURE.md](ARCHITECTURE.md) explains provenance versus interpretation and the proposal boundary. Phase reports record actual results, including failures:
- [PHASE_2A_REPORT.md](PHASE_2A_REPORT.md)
- [PHASE_3_REPORT.md](PHASE_3_REPORT.md)
- [PHASE_4_REPORT.md](PHASE_4_REPORT.md): PDF ingestion
- [PHASE_5_REPORT.md](PHASE_5_REPORT.md): review app
- [PHASE_5B_AUDIT.md](PHASE_5B_AUDIT.md): independent self-audit
- [PHASE_6_REPORT.md](PHASE_6_REPORT.md): hardening and rule versioning

## JSON command-line interface (standard library only)

Python 3.8+; standard library only. No packages, API keys, frontend, database, or paid service are required for the baseline. Executed here on Python 3.13.12; Python 3.8 grammar compatibility was checked, but a Python 3.8 interpreter was not available for runtime testing.

```bash
# From the existing project folder:
python main.py --validate-benchmark
python main.py --input tresata_adversarial_cases.json --mode baseline
python -m unittest discover -v
```

An optional virtual environment can be created with `python -m venv .venv`. The JSON workflow needs no packages. Install `requirements-pdf.txt` to run PDF ingestion and its tests; otherwise the PDF tests explicitly skip.

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
| Hybrid review-only AI suggestions / safety vetoes | `src/review_evidence.py` |
| Date selection / provisional mapping | `src/rules.py`, `src/rules_v1.json` |
| Batch isolation / reporting | `src/pipeline.py`, `main.py` |
| Metrics | `src/evaluation.py` |
| Paced, checkpointed live evaluation | `run_live_evaluation.py` |

1. **`baseline`**: Python patterns recognize personnel supply and individual-worker supervision, handle conservative negation and conflict checks, and abstain when no decisive clause is found. No LLM call.
2. **`direct-llm`**: One call proposes a factual category directly. Raw output is retained. It receives the same transaction fields but does not extract predicates or quotes, so it cannot propose a legal table item. The deterministic residency/date wrapper remains active; raw-category agreement is separately reported so scope overrides cannot hide model errors.
3. **`hybrid`**: One call extracts `personnel_supplied`, `worker_supervisor`, `supporting_quotes`, `missing_facts` and `contradictory_evidence`. Python validates the schema, exact provenance and conservative factual support, then applies the deterministic rules. There are no repair calls, retries, agent chains or runtime legal retrieval.

On the development branch, hybrid JSON also includes `evidence_review`: supported, AI-suggested requiring review, contradictory, or insufficient. Exact-source unfamiliar assertions remain visible with full sentence context, while known unsafe assertions are quarantined. Suggestions never enter validated facts or justify a table proposal. This improves review routing; it does not expand automatic factual acceptance beyond the original lexical gate.

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

### Phase 3: post-submission evidence architecture

The separately frozen 12-case v3 challenge scores **9/12** with the unchanged baseline. On identical hand-authored extraction fixtures, old and improved hybrid both score **8/12**; the new layer explicitly routes **3/12** cases as review-only AI suggestions without adding confident classifications. Fixtures are not model results, and the source-informed cases are not an independent holdout.

The fixed-model live attempt used `cohere/north-mini-code:free` and stopped on request 12 with `INVALID_PROVIDER_RESPONSE`: **11 usable responses, one failed attempt, 12 unexecuted requests, zero retries**. All 11 usable responses returned that same model ID. Direct LLM agreed on **4/6** usable cases; hybrid agreed on **3/5** (or 3/6 when the failed attempt is included). On the common five completed cases, all three methods agreed on **3/5**, with **2/5** incorrect confident decisions for direct LLM and **0/5** for baseline and hybrid. The improved hybrid exposes two unfamiliar clauses for review while still abstaining. This is an incomplete comparison, not validated tax accuracy or a demonstrated automatic-recall improvement.

The full suite passes **87/87 tests**, preserving the original 72. Original baseline benchmarks remain **16/16** and **12/12**. All earlier results remain unchanged. See [PHASE_3_REPORT.md](PHASE_3_REPORT.md) for denominators, failure cases, same-response before/after analysis and limitations.

### Phase 2A: offline reliability work

The separate `tresata_challenge_v2.json` has **12 synthetic cases and 10 exact anchors**. It was crafted after source review, so it is not an unbiased holdout. Its hash and validation record are in `challenge_v2_manifest.json`. The unchanged submission baseline scored **8/12**, with **0/12 incorrect confident directional classifications**. First-pass predictions and expected-versus-observed comparisons are permanently retained under `results/phase2a/first_pass/`.

Focused extraction fixes cover direct passive-worker subjects, additional worker vocabulary, an explicitly bound recipient alias, and clearly obsolete draft labels. Future conditions and ambiguous grammar retain conservative abstention. The final challenge score is **12/12 development-set agreement**, with **0/3 false-confident decisions on expected-insufficient cases** and **3/3 appropriate insufficient-evidence abstentions**. The original benchmark remains **16/16**, including **0/4 false-confident evidence-removed decisions**. These are synthetic factual-label metrics, not legally validated tax accuracy.

Phase 2A validation passed **69/69 tests**: the unchanged original 51 plus 18 regressions. No live model call, prompt change, tax-rule change or scope expansion occurred. The original submission commit `fbe81240d6cd26107dc544690fe9b8c73e825220` remains the fallback. See [PHASE_2A_REPORT.md](PHASE_2A_REPORT.md) for every first-pass mismatch and limitation, and [DEMO_WALKTHROUGH.md](DEMO_WALKTHROUGH.md) for three executed offline demonstrations.

To reproduce without overwriting saved evaluation artifacts:

```bash
python -m unittest discover -v
python main.py --input tresata_adversarial_cases.json --mode baseline --output /tmp/tds-original-recheck.json
python main.py --input tresata_challenge_v2.json --mode baseline --output /tmp/tds-challenge-recheck.json
```

Those commands use the current implementation. The saved 8/12 first pass used the unchanged fallback commit before any Phase 2A implementation edits.

### Preserved Phase 1 / 1B results

The offline baseline remains **16/16** provisional-status agreement, **0/4** false-confident evidence-removed decisions, **29/29** verbatim quote entries, and **8/12** entire frozen anchors. The first development baseline scored **13/16** with **1/4** false-confident removed-case decisions. Those original reports remain under `results/development/`; code was corrected during development, without changing labels.

The two earlier full-benchmark attempts each stopped after **one HTTP 429**, with no usable model result. Their reports remain unchanged at `results/direct-llm.json` and `results/hybrid.json`. A later one-case smoke test succeeded using `openrouter/free`, routed to `cohere/north-mini-code:free`, and matched the provisional label.

**Phase 1B is a partial live evaluation, not a completed 16-case comparison.** It stopped globally after request 5 returned `INVALID_PROVIDER_RESPONSE`: **4 usable responses, 1 failed request, 27 unexecuted requests, 0 retries**. No HTTP 429 occurred in this run. Underlying model/refusal details for the failed response were unavailable; its cause cannot be narrowed further from the retained diagnostic.

| Measure | Direct LLM | Hybrid |
| --- | --- | --- |
| Planned / attempted cases | 16 / 3 | 16 / 2 |
| Valid output schemas | 2 | 2 |
| Request failures / unexecuted cases | 1 / 13 | 0 / 14 |
| Factual-status agreement on attempted cases | **2/3**, including the failed attempt | **1/2** |
| Agreement on usable outputs only | 2/2 | 1/2 |
| Usable evidence-removed outputs | **0/4** | **0/4** |
| Four-case false-confidence target | **NOT_EVALUATED** | **NOT_EVALUATED** |
| Verbatim / submitted quotes | Not requested | **4/4** |
| Quotes rejected for factual meaning | Not applicable | **1/4** |

The rejected hybrid quote prohibited customer direction, but the model labelled it as customer supervision. Python rejected the interpretation and abstained; this was still a mismatch against the vendor-control expected status. There were **0 observed refusals across 4 usable responses**; refusal status is unknown for the failed request. The model reported missing facts in **0/2** hybrid outputs, while validation identified missing reliable supervision evidence in **1/2**.

Live routing selected `dots-studio/dots-3-note-preview:free` once, `nvidia/nemotron-3.5-super-vl:free` twice, and `xingchen-agi/xing4.0-29b-a4b:free` once. Both successfully paired cases used different models across the two methods. These incomplete, mixed-model results cannot establish which architecture is better. The benchmark is a visible development set; none of the metrics is legally validated TDS-classification accuracy.

The unchanged automated suite was rerun after the live attempt: **51/51 tests passed**. See [RUN_REPORT.md](RUN_REPORT.md), [the Phase 1B summary](results/phase1b/run-20261103-01/summary.json), and [the read-only Git audit](results/phase1b/run-20261103-01/git_security_audit.json). Original data, labels, manifest, test files and historical results were preserved.

### Paced live-evaluation runner

Phase 1B used this command once:

```bash
python -u run_live_evaluation.py --env-file .env --output-dir results/phase1b/run-20261103-01
```

The runner parses only the two OpenRouter entries as data, without sourcing shell code, and accepts only `openrouter/free`. It interleaves direct/hybrid requests for each case, waits at least 15 seconds after each completed request, checkpoints responses, records model/finish/refusal metadata, and stops both methods on the first API/network/client block. It has no retry or paid fallback. An existing output directory prevents accidental repetition. The protocol and code/test hashes were recorded before its first request. Prompts and classification rules were unchanged; only passive response metadata logging and the runner were added beforehand. No tuning followed the observed outputs.

The earlier CLI commands remain available, but the basic CLI does not provide this runner's pacing or cross-method stop policy. No further live requests were made after the stop. Any future evaluation must use a new output directory and remain distinct from these results.

## Primary legal sources and limits

Source text was checked on 3 November 2026 and recorded in `src/rules_v1.json`:

- [Finance Act, 2026](https://www.incometaxindia.gov.in/documents/d/guest/finance-act-2026-pdf-1), Section 90(b), Gazette page 58: the manpower addition to Section 402(47).
- [Amended Income-tax Act, 2025](https://www.incometaxindia.gov.in/documents/d/guest/income_tax_act_2025_as_amended_by_fa_act_2026-pdf), Sections 1(3), 393(1) Table 6(i)/6(iii), and 402(47)(f). Relevant PDF pages are 1, 471–472 and 508–509, using one-based page numbers.
- [Income Tax Department transition FAQs](https://www.incometax.gov.in/iec/foportal/help/all-topics/e-filing-services/tds-compliance): the earlier credit/payment event selects the Act across 1 April 2026.

Official-source verification is not practitioner validation of the factual-to-legal mapping. Any table proposal is explicitly provisional. The static rules require deliberate maintenance for later changes. The prototype does not assess exemptions, thresholds, payer eligibility beyond its narrow declared-company gate, treaty issues, professional-services qualification, contract precedence, or real working practices.

No frontend, production infrastructure, autonomous tax action or public deployment is included. The repository contains synthetic fixtures and prototype code; keep real contracts and private reports in ignored locations. Raw outputs on real inputs may themselves contain private text. The GitHub submission target is [korakdas1/tds-evidence-review](https://github.com/korakdas1/tds-evidence-review). The repository remains private; making it public is a separate owner decision.


## Initial GitHub submission checks

The release checks reran the unchanged offline suite: **51/51 tests passed**. The benchmark, manifest, source, tests and historical evaluation artifacts were preserved byte-for-byte. No live API experiment was run during release preparation. The release [test log](results/release/test_run.txt), [security audit](results/release/security_audit.json) and [file inventory](results/release/files.txt) accompany this snapshot.

The audit excludes `.env`, credential files, local caches and ignored local reports from the commit. Synthetic model outputs remain included as evaluation evidence; they are not private conversation logs. Historical `prior_*.md` files and older result files describe their original stages; use this README and RUN_REPORT.md for the current interpretation.

The submission is ready for review as a limited prototype with **incomplete live evaluation**. It does not demonstrate legally validated TDS accuracy or a completed live AI benchmark. No open-source license has been selected. Do not include the local `.env` file in any manually created submission archive.
