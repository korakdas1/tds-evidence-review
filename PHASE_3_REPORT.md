# Phase 3 — post-submission AI evidence architecture

## Scope and preservation

Work is on `feature/full-product`, fetched from the existing remote branch. The submitted commit and `main` remain `e075a9087b8f4dbebee3fe74f2cb427c5bc3a3c0`. No history rewriting, tax-rule changes, new rates, frontend, ingestion feature or Phase 4 implementation is included. All original 72 test files, both prior datasets/manifests and historical experimental artifacts remain unchanged. `results/phase3/preservation.json` records their starting hashes.

## Investigation and implemented design

The original hybrid extracts with an LLM but uses the baseline's `sentence_predicates()` as its factual-support gate. It cannot automatically validate unfamiliar interpretations. Its raw extraction and rejected quotes were already retained; the issue was both a narrow promotion gate and a lack of explicit review semantics.

`src/review_evidence.py` now separates exact-source AI leads from validated factual evidence. It adds four case states: `SUPPORTED_FACTUAL_EVIDENCE`, `AI_SUGGESTED_REQUIRING_REVIEW`, `CONTRADICTORY_EVIDENCE`, and `INSUFFICIENT_EVIDENCE`. Individual unsafe items are `REJECTED_BY_SAFETY_GUARD`. Each item carries the asserted predicate, exact quote, character positions, surrounding sentences and review reasons. Unfamiliar opposing claims can be marked as an **unverified** contradiction rather than a proven conflict.

The original validator remains unchanged and is the only automatic factual promotion gate. New conservative vetoes also block proposals for recognized unsafe context. AI suggestions do not enter `validated_facts`; only that channel reaches the unchanged legal rules. A model cannot grant itself a supported state or human approval. All treatment remains provisional and requires qualified human review.

**Solved:** unfamiliar exact-source evidence has an explicit, auditable review path, distinct from fabricated or known unsafe quotations. **Not solved:** independent semantic verification or increased automatic classification recall. This deliberately small change does not claim an AI advantage over patterns. See [ARCHITECTURE.md](ARCHITECTURE.md) for the data flow, schemas, vetoes and boundaries.

## Frozen evaluation construction

`tresata_challenge_v3.json` is a separately versioned 12-case synthetic development set, authored after source inspection. It covers familiar supervision, unfamiliar customer/vendor paraphrases, outcome monitoring, prohibitions, deleted clauses, unfamiliar conflict, clipped negation, a deliberately fabricated extraction, injection, missing control and recognized conflict. The eight gold anchors all occur exactly in source. Schema, labels and IDs were checked before evaluation.

`phase3_extraction_fixtures.json` holds hand-authored good/bad extractor responses and predetermined review-state expectations. These are **not generated model results**. P3_09 intentionally has an invalid extracted quote; no gold evidence anchor is fabricated. Fixtures isolate the validation architecture from model behavior.

Both files and labels were frozen before old-baseline execution or Phase 3 implementation, in `phase3_manifest.json`:

- Challenge SHA-256: `c33232531c3632f40e85833361368a291e2a1558f39c1ee59c68e913897d60d0`.
- Fixture SHA-256: `7deda6d06b7d2a89f860da6bb521b1b12fe0796a854abd024474de65cebcddb3`.

No label, fixture or prompt was tuned after examining model outputs. These source-informed, self-authored cases are not an independently validated holdout. `before_freeze.json` pins the first-pass reports from the submitted architecture.

## Measured architecture comparison: identical simulated extractions

| Metric | Submitted baseline | Submitted hybrid fixtures | Improved hybrid fixtures |
| --- | --- | --- | --- |
| Factual-status agreement | 9/12 | 8/12 | 8/12 |
| Incorrect confident directional decisions | 0/12 | 0/12 | 0/12 |
| Directional false-negative abstentions / directional gold | 2/4 | 3/4 | 3/4 |
| Abstentions, including conflict | 10/12 | 11/12 | 11/12 |
| Appropriate insufficient abstentions | 6/6 | 6/6 | 6/6 |
| Recognized conflict / conflict gold | 1/2 | 1/2 | 1/2 |
| Quote provenance errors | 0/19 | 1/29 | 1/29 |
| Verbatim but unverified interpretations | 0/19 | 11/28 | 11/28 |
| Cases with explicit AI-suggested review state | Not implemented | Not implemented | 3/12 |
| Live model requests | 0 | 0 | 0 |

The deliberately fabricated quote is rejected both before and after; the quote error is in the fixture, not a failed validator. Duplicate supporting/contradiction entries are counted as submitted, explaining the quote denominators. All 12 improved fixture review states match their frozen policy expectations. This is a routing check, not semantic model accuracy. The unchanged baseline also reran at 9/12 after implementation.

The three unfamiliar-evidence cases P3_02, P3_03 and P3_07 move from generic validation failure to an explicit uncertain review state. Their existing raw quotes were already visible previously, so **this is not increased quote retrieval**. The confident outcomes and provisional proposals do not improve or become less conservative.

### Every first-pass mismatch

| Case | Failure category and interpretation | After Phase 3 |
| --- | --- | --- |
| P3_02 | False-negative directional abstention: unfamiliar buyer-side control | Review-only lead; still insufficient for automatic validation. |
| P3_03 | False-negative directional abstention: unfamiliar supplier control | Review-only lead; still insufficient for automatic validation. |
| P3_06 (fixture hybrid only) | False-negative abstention: extraction cherry-picks deleted customer clause and omits current supplier clause | Unsafe quote remains rejected; no automatic substitution of a model claim with a guessed correction. Baseline independently recognizes the current vendor clause. |
| P3_07 | Missed factual conflict: both opposing clauses use unfamiliar language | Both claims remain review-only, with unverified contradiction flag. No assertion of a proven conflict or confident direction. |

These are implementation/coverage limitations, not label corrections. Conservative abstention is justified at the system-validation layer even when the author-assigned factual reading is directional. No annotation change was made to improve agreement.

## Live comparison

The authorized fixed model was **`cohere/north-mini-code:free`**. The [OpenRouter model catalogue](https://openrouter.ai/api/v1/models) listed zero prompt/completion pricing; the runner additionally checked request pricing and available key limit. No key limit amounts or other private account data were stored. The same prompts were used throughout, with 15-second spacing and no paid/model fallback.

**The live comparison is incomplete.** There were **12 attempted requests out of 24 planned**: **11 usable responses**, **1 `INVALID_PROVIDER_RESPONSE` failure** on hybrid P3_06, and **12 unexecuted requests** (six per method). Both methods stopped globally, with **zero retries**. All **11/11 usable responses** returned the exact fixed model ID. The failed response had no decoded model ID; the sanitized error does not identify the underlying provider-body defect. No HTTP 429 occurred in this run; older 429 failures remain untouched.

| Live result | Direct LLM | Improved hybrid |
| --- | --- | --- |
| Usable outputs / planned cases | 6/12 | 5/12 |
| API attempts | 6/12 planned | 6/12 planned |
| API/client failures / attempts | 0/6 | 1/6 |
| Unexecuted cases | 6/12 | 6/12 |
| Agreement among usable outputs | 4/6 | 3/5 |
| Agreement including the attempted failure as unsuccessful | 4/6 | 3/6 |
| Incorrect confident directions among usable outputs | 2/6 | 0/5 |
| Directional false-negative abstentions / completed directional gold | 0/4 | 2/3 |
| Abstention among usable outputs | 0/6 | 4/5 |
| Appropriate abstention on completed insufficient cases | 0/2 | 2/2 |
| Quote provenance errors | N/A: direct mode produces no quotes | 0/9 submitted quotes |
| Missing validated control | N/A | 4/5 usable outputs |
| Exact quotes failing interpretation checks | N/A | 3/9 quotes (two unfamiliar, one unsupported inference) |
| Explicit review-only cases | N/A | 2/5 usable outputs |
| Request elapsed time excluding pacing (including failed request) | 25.041449 seconds / 6 attempts | 45.829888 seconds / 6 attempts |

There were **0 refusal signals among 11 decoded responses**; the one undecodable response is not asserted to be refusal-free. Existing general metrics include the attempted failed hybrid case in some denominators (e.g. 5/6 fallback/abstention statuses); `comparison` and this table separately exclude failed cases from prediction/abstention counts. Never treat the fallback status of an execution failure as a valid model decision. No live contradiction, injection or fabricated-quote challenge was reached. The original four-case live safety target was not evaluated here.

### Matched subset: the same five completed cases

P3_01 through P3_05 are the only common completed cases. Comparing full baseline 9/12 with unequal partial live denominators would be misleading:

| Common-subset metric | Baseline | Direct LLM | Improved hybrid |
| --- | --- | --- | --- |
| Agreement | 3/5 | 3/5 | 3/5 |
| Incorrect confident directions | 0/5 | 2/5 | 0/5 |
| Directional false-negative abstentions / directional gold | 2/3 | 0/3 | 2/3 |
| Abstentions | 4/5 | 0/5 | 4/5 |

Direct LLM incorrectly called **P3_04** (outcome sign-off only) and **P3_05** (prohibition of customer supervision) vendor-directed service. Neither proves vendor control. Hybrid correctly left P3_04 unknown. On P3_05 it also asserted vendor control, quoting `Customer must not supervise workers.` The quotation was exact, but both the old validator and new review layer rejected that unsupported inference; the improved output remained insufficient with no statutory proposal. These errors are preserved, not corrected in the saved model output.

On P3_02 and P3_03, the model supplied the exact unfamiliar customer/vendor clauses. They are now explicit review-only leads; automatic classification still abstains. Comparing the **same five saved hybrid extractions** through the unchanged submitted validator produces identical factual statuses and proposals (**3/5 agreement before and after**). The additional value is structured review visibility for **2/5 cases**, not improved confident recall or increased quote retrieval. `live_analysis.json` records this zero-new-request replay, per-case results and common-subset metrics.

After the run, a focused mocked regression added an early stop for the rare case of an explicit refusal accompanying parseable content, so such a response cannot count as a successful prediction. No observed response had that condition. This runner-only hardening did not change prompts, the evidence architecture, labels or saved live results, and no model rerun was made. `live-01/protocol.json` preserves the exact code hashes used for that experiment; `live_freeze.json` pins its artifacts. Final offline verification uses the updated runner. This is openly documented development, not independent validation.

## Regression verification and commands

The original 72 tests passed unchanged. The initial expanded suite passed **86/86** during development. After adding the explicit-refusal regression, the final suite passed **87/87** (72 unchanged original tests plus 15 new tests). Added tests cover review-only unfamiliar claims, preservation of supported provisional behavior, exact/fabricated/clipped quotes, stale and outcome-only context, injection, unfamiliar versus recognized conflicts, stricter veto enforcement, malformed extraction, free-model/preflight restrictions, model-ID mismatch and a global first-error stop. Provider calls are mocked in tests; these results are not model experiments.

The original 16-case baseline rerun remains **16/16**, including **0/4** false-confident evidence-removed decisions. The Phase 2A baseline remains **12/12**. `python demo.py` still works, including its explicitly historical replay. New outputs are under `results/phase3/`; previous results were never overwritten.

Commands executed from the repository root (each comparison output directory is unique):

```bash
python -m unittest discover -v
python evaluate_phase3.py --output-dir results/phase3/offline-01
python evaluate_phase3.py --output-dir results/phase3/live-01 --live-model cohere/north-mini-code:free
python evaluate_phase3.py --output-dir results/phase3/final-offline
python main.py --input tresata_adversarial_cases.json --mode baseline --output results/phase3/original_baseline.json
python main.py --input tresata_challenge_v2.json --mode baseline --output results/phase3/challenge_v2_baseline.json
python demo.py
```

The old first-pass baseline and fixture replay were executed with `run_batch()` before any implementation changes. Their outputs and implementation hashes remain in `before_baseline.json` and `before_hybrid_fixtures.json`. `before_after_summary.json` contains per-case and aggregate before/after comparisons. For new reproduction use the ignored, fresh `results/local/` directories shown in ARCHITECTURE.md instead of these preserved paths. All new execution used Python 3.13.12; Python 3.8 grammar compatibility was checked, but a Python 3.8 interpreter was not tested.

## Remaining weaknesses and Phase 4 recommendation

The supported channel is still pattern-limited. Review-only leads may be irrelevant or wrong; exact provenance is not semantic verification. The same wording that escapes the baseline's positive patterns can escape its contradiction checks. Broad negation/context vetoes can create additional conservative abstentions. Sentence context cannot resolve distant qualifications, unmarked supersession, actual party identities or working practices. There is no independent adjudicator, human-confirmation storage, or calibration study. The small targeted fixture score is not production reliability or legal accuracy.

Phase 4 may proceed as a separate, explicitly authorized effort: minimal extraction of text from public/synthetic PDFs, retaining document/page/span provenance and flagging unreadable/scanned input. Preserve the current review boundary and add tests for altered reading order and split negation. Before claiming AI benefit, obtain independently annotated unfamiliar contracts and measure the usefulness and false-lead rate of the review-only channel. Do not begin OCR, UI or tax-rule expansion as an automatic continuation of this work.

## Release

The final suite passed **87/87**. The read-only security review found no credential or private-data matches in **132 staged release files**, including **47 changed/new files**, and **91 reachable historical Git blobs**. `.env` remains ignored and untracked with mode 0600; caches and local/private files are excluded. Frozen inputs, original tests/tax rules, historical results, first-pass outputs and the captured live run passed integrity checks. Only README and the additive pipeline integration differ among the 87 previously tracked files; the other **85 remain byte-for-byte unchanged**. The audit is a scoped scan and content review, not a guarantee against every possible sensitive item. Evidence is recorded in `results/phase3/security_audit.json`; the working branch is `feature/full-product`, with no changes to `main` or repository visibility.

The final verified branch commit is supplied in the completion handoff and can be retrieved with `git log -1 --format=%H -- PHASE_3_REPORT.md`. The submitted commit remains an ancestor; `main` must remain at `e075a9087b8f4dbebee3fe74f2cb427c5bc3a3c0`. Issue #1 receives a verified progress comment after the development-branch push; later roadmap phases remain unstarted.
