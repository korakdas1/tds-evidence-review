# Phase 2A — reliability report

The unchanged baseline scored **8/12** on the supplied challenge. Focused evidence-extraction corrections raised agreement to **12/12 on this development set**, while preserving all three appropriate insufficient-evidence abstentions and recording zero incorrect confident directional decisions. The original benchmark remains **16/16**. The original **51/51 tests** and full **69/69 tests** pass. **No live LLM calls, prompt changes, tax-law mapping changes or tax-scope expansion occurred.**

## Dataset inspection and immutable first pass

`tresata_challenge_v2.json` is a separate 12-case synthetic set. Its metadata explicitly says it was crafted after source-code review, so **neither the first pass nor the post-fix score is an unbiased independent holdout estimate**. Labels are provisional factual readings, not practitioner-validated legal ground truth.

Schema validation found all 12 required transaction records well formed, IDs unique, expected factual statuses recognized, dates/expected Acts consistent, synthetic flags present and **10/10 exact evidence anchors**. The envelope has different metadata from v1, but its flat record schema is already supported. **No data, anchor or label adjustment was necessary or made.**

The SHA-256, recorded before evaluation in `challenge_v2_manifest.json`, is:

```text
082a4e57276cd1eb61c3543f02fc53cf747a64e35932429509a4273b5b0ecf4a
```

The original dataset and manifest are untouched; the original dataset hash remains:

```text
a0744ad70703d0ddef563d7b713ffa604cffd927ba2a14675a4f7a7caf4f4699
```

The first-pass implementation hashes were checked against fallback commit **fbe81240d6cd26107dc544690fe9b8c73e825220** and match byte-for-byte. The baseline was run before implementation edits:

```bash
python main.py --input tresata_challenge_v2.json --mode baseline --output results/phase2a/first_pass/baseline.json
```

The original predictions are in [first_pass/baseline.json](results/phase2a/first_pass/baseline.json) and CSV. [comparison.json](results/phase2a/first_pass/comparison.json) records every expected/observed status, incorrect confident decision, abstention, missing/conflicting evidence, date outcome and quotation count. [mismatch_review.json](results/phase2a/first_pass/mismatch_review.json) classifies the failures. `first_pass_freeze.json` records those artifacts' hashes. They were never overwritten after fixes.

## Exact before-and-after outcomes

| Case | Expected | Unchanged first pass | Final post-fix |
| --- | --- | --- | --- |
| `CH01_CUSTOMER_PASSIVE` | Customer | Insufficient | Customer |
| `CH02_VENDOR_PASSIVE` | Vendor | Vendor | Vendor |
| `CH03_OUTCOME_ONLY` | Insufficient | Insufficient | Insufficient |
| `CH04_UNRELATED_NEGATION` | Customer | Customer | Customer |
| `CH05_VENDOR_EXCLUSIVE` | Vendor | Vendor | Vendor |
| `CH06_FUTURE_CONDITION` | Insufficient | Insufficient | Insufficient |
| `CH07_CROSSOVER` | Customer | Insufficient | Customer |
| `CH08_CONFLICTING_CURRENT` | Conflict | Conflict | Conflict |
| `CH09_VENDOR_SERVICE_OUTCOME` | Vendor | Insufficient | Vendor |
| `CH10_MISSING_SUPERVISOR` | Insufficient | Insufficient | Insufficient |
| `CH11_STALE_CLAUSE` | Customer | Conflict | Customer |
| `CH12_NONRESIDENT` | Out of scope | Out of scope | Out of scope |

| Metric | Unchanged first pass | Final post-fix development run |
| --- | --- | --- |
| Provisional factual-status agreement | **8/12** | **12/12** |
| Incorrect confident customer/vendor classifications | **0/12 cases** | **0/12 cases** |
| Incorrect / all confident customer/vendor outputs | **0/3** | **0/7** |
| Abstentions, including conflict and out-of-scope routing | **9/12** | **5/12** |
| Appropriate insufficient-evidence abstentions | **3/3** | **3/3** |
| False-confident outputs on expected-insufficient cases | **0/3** | **0/3** |
| Current contradictory-clause case | **1/1** | **1/1** |
| Spurious conflict caused by a stale clause | **1/12 cases** | **0/12 cases** |
| Act selection | **12/12** | **12/12** |
| March 31 credit / April payment crossover | **1/1** | **1/1** |
| Nonresident routing | **1/1** | **1/1** |
| Supervisor agreement, derived provisional targets | **7/11** | **11/11** |
| Exact quotation provenance | **18/18 entries** | **25/25 entries** |
| Entire frozen-anchor retrieval | **6/10** | **10/10** |
| Human review required | **12/12** | **12/12** |
| Execution failures | **0/12** | **0/12** |
| Live API calls | **0** | **0** |

“Confident” here means a customer- or vendor-directed factual status. A spurious conflict is separately reported as an error; it is not hidden by the zero incorrect directional decisions. Quote entries include repeated entries for separate predicates or contradictory-evidence lists. Verbatim provenance does not prove that the passage is current or correctly interpreted. No separate personnel-supply correctness score is claimed because no independent predicate labels were supplied.

The old evaluator's four-`CONTROL_REMOVED` safety metric is not applicable to this challenge's variant names and remains NOT_EVALUATED. The separate comparison explicitly scores its **three expected-insufficient cases** instead. The original benchmark's four-case target was rerun and remains **0/4 false-confident decisions**, with **4/4 correct abstentions**. These denominators are not pooled or substituted for the incomplete live evaluation.

## Every first-pass mismatch and ambiguity review

| Case | Classification | Diagnosis and action |
| --- | --- | --- |
| CH01_CUSTOMER_PASSIVE | False negative | The old vocabulary missed technicians/Purchaser, the separated makes-people-available construction, and passive worker supervision. Added bounded vocabulary/supply recognition and direct passive-worker subjects. |
| CH07_CROSSOVER | False negative | The text supplies workers to Company and then names Company as supervisor. The generic alias was not recognized. Added binding only when an operative personnel-supply sentence explicitly identifies Company as recipient. The old-Act date selection was already correct and was not changed. |
| CH09_VENDOR_SERVICE_OUTCOME | False negative | The restricted people vocabulary missed agents in an explicit allocation-to-each-agent clause. Added worker nouns; customer outcome inspection still does not establish worker direction. |
| CH11_STALE_CLAUSE | Implementation error: false conflict | Splitting at the colon discarded the obsolete-draft label, allowing stale vendor supervision to conflict with the operative customer clause. Explicit draft/obsolete/deleted/superseded labels now exclude that sentence before interpreting its factual predicates. |

**CH03, CH06 and CH10 were justified abstentions**, not failures: service outcome monitoring, a future unsigned arrangement, and unspecified supervision do not establish current control. They remain insufficient after the fixes. CH08 correctly retains both current opposing clauses as conflict. CH12 remains out of scope. CH04's unrelated payroll negation was in a separate sentence and already worked; no general negation parser was added.

No annotation error or ambiguity requiring a label change was identified in these 12 excerpts. That finding does not independently validate the annotations. Real-world party identities and document precedence can be substantially more ambiguous than these fixtures.

## Focused implementation and regression checks

Only `src/evidence.py` changed in runtime code. The original input handling, model prompts/client, report pipeline, evaluation code and tax-rule files were not changed. No case IDs, expected labels or complete benchmark sentences were inserted into extraction logic. New tests use different sentences and quantities from the challenge.

Changes cover:

- Direct passive worker subjects, including coordinated instructed/supervised verbs. Service output or worker attributes must not be mistaken for the people subject.
- Additional worker nouns and the Purchaser role; personnel made available is distinguished from making worker records available.
- The Company alias only when an explicit supply-to-recipient relationship is present. Unknown aliases and complex multi-actor grammar abstain instead of assigning a later party's verb to an earlier actor.
- Explicit inoperative draft labels considered before stripping clause headings. This is not a general contractual-precedence resolver.
- Future/conditional control kept out of current evidence. The strengthened guard also protects against a failure exposed by a supplemental workers-based regression, even though the original challenge's future-agents case happened to abstain already.

Regression development was transparent: **9/17 initial added tests failed** on the old implementation. The first implementation pass exposed one remaining supplier-company modifier failure among 68 tests, then passed after correction. A further passive-subject regression exposed **two failing subcases** involving supervision of safety or attendance; the passive pattern was narrowed before the final run. All these failure logs remain under `results/phase2a/`. Intermediate post-fix outputs were retained; final outputs are separately under `results/phase2a/final/`.

Final checks executed:

```bash
python -m unittest discover -v
python -m unittest tests.test_core tests.test_llm -v
python main.py --input tresata_adversarial_cases.json --mode baseline --output results/phase2a/final/original_baseline.json
python main.py --input tresata_challenge_v2.json --mode baseline --output results/phase2a/final/challenge_baseline.json
```

**69/69 tests passed**, comprising **51 unchanged original tests + 18 new regression tests**; the original suite also passed separately. Final code-run test output is [final_tests.txt](results/phase2a/final_tests.txt). A separate release rerun also passed **69/69**, recorded in [release_tests.txt](results/phase2a/release_tests.txt). The original 16-case rerun remains **16/16**, **29/29** verbatim quote entries, **8/12** full anchors, and **0/4** false-confident removed decisions. Its historical artifact was not overwritten. All new execution was offline on Python 3.13.12; Python 3.8 runtime testing remains unperformed.

## Demonstration

[DEMO_WALKTHROUGH.md](DEMO_WALKTHROUGH.md) contains executed commands and captured stdout for a supported case, a missing-evidence abstention, and the recorded Phase 1B model mistake. The historical model quoted a prohibition on customer direction while asserting customer supervision; the validator rejected the interpretation despite exact provenance. That response is read from the preserved artifact, not regenerated or represented as a new model result. Captures are in `results/phase2a/demo_outputs.json`.

## Remaining weaknesses and PDF recommendation

This remains a small lexical prototype. Same-sentence unrelated negation can still produce a conservative false negative, even when a human could separate the clauses. Passive grammar is deliberately restricted to direct people subjects. Mixed current/obsolete material within one sentence, unmarked deletions, complex precedence, arbitrary party aliases, nonhuman meanings of worker nouns, and indirect/conditional wording can require review. Explicit inoperative wording in a synthetic excerpt is not proof of contractual legal effectiveness. Actual working practices are not verified.

Quotation provenance is not semantic correctness. No tax rates, thresholds, exemptions, nonresident tax treatment or other tax scope were added. The mapping is still provisional and requires qualified human review. The earlier live evaluation remains **4 usable responses from 5 attempts, 27 unexecuted requests**, with mixed models and no evaluated live four-case safety target. Offline improvements do not establish better live-LLM performance.

**Recommendation:** include a compact before/after row (8/12 to 12/12), explicitly labelled “targeted, source-informed synthetic challenge; post-fix development performance,” alongside the preserved 16/16 original baseline and 69 passing tests. Use one failure example and the demonstrated safe abstention/rejection to explain architectural judgment. Do not present 12/12 as independent reliability, legal accuracy, or a replacement for the incomplete live comparison. These qualifications belong in the four-page PDF even if they reduce room for feature descriptions.

## Release and fallback

The unchanged submission fallback is [fbe81240d6cd26107dc544690fe9b8c73e825220](https://github.com/korakdas1/tds-evidence-review/commit/fbe81240d6cd26107dc544690fe9b8c73e825220). Phase 2A is a descendant on `main`; the fallback and all historical artifacts remain accessible. No force push or visibility change is permitted. `.env` and local caches remain excluded. Changed-file and staged-blob security checks found no credentials or private information in the 82 release files, including 39 changed/new files. The audit also checked all 46 fallback-commit files. `.env` is ignored, untracked and permissioned 0600. Results are in `results/phase2a/security_audit.json`; the audit is not a guarantee against every possible form of sensitive data.

**Final commit SHA:** the full verified Phase 2A SHA is supplied in the release handoff. In this checkout, retrieve the report's exact commit with:

```bash
git log -1 --format=%H -- PHASE_2A_REPORT.md
```

A commit cannot contain its own literal SHA without changing that SHA; this report uses Git's verifiable commit identity rather than a fabricated or stale self-reference. No additional live experiment is part of this release.
