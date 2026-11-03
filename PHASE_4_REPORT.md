# Phase 4 — PDF ingestion with source provenance

Implemented on `feature/full-product`, based on Phase 3 commit `8f9cfc779400f7880947e7b12c7b48dba71748e0`. Submitted `main` remains `e075a9087b8f4dbebee3fe74f2cb427c5bc3a3c0`. No live LLM requests, tax-rule changes, frontend or Phase 5 implementation occurred.

## Functionality and files

- `src/pdf_ingestion.py`: bounded local selectable-text extraction, per-page raw text, document/file/page hashes, whitespace-only reversible source mapping, exact quotes and surrounding context, safe extraction failures.
- `src/document_review.py`: additive adapter to the existing pipeline, separate invoice extraction, manually supplied transaction fields, canonical evidence items and an authoritative document-review gate. Exact source mapping never upgrades uncertain AI interpretation.
- `pdf_demo.py`: offline synthetic example and optional custom contract/invoice plus manual JSON metadata; output files are exclusive-create.
- `evaluate_pdfs.py`: reproducible frozen-fixture evaluation with per-file reports, source checks, invalid-location probes and implementation hashes.
- `tests/test_pdf.py`: 26 focused tests. `tests/fixtures/generate_pdf_v1.py` and `tests/fixtures/pdf_v1/`: separately versioned synthetic fixtures and frozen expectations.
- `requirements-pdf.txt`, `THIRD_PARTY_NOTICES.md`: optional pypdf 6.21.4, Python 3.9+, BSD 3-Clause; authoring dependencies and intentional security fixtures explained.
- `.gitattributes`: PDFs are binary to prevent text conversion and misleading whitespace diffs; frozen PDF bytes were not edited.
- `README.md`, `ARCHITECTURE.md`, this report and `results/phase4/`: documentation, extraction/evaluation outputs, tests and audit evidence.

All pre-existing source, tests, datasets, prompts, manifests and historical results remain byte-identical. Only README and architecture documentation changed among the 132 pre-existing tracked files. The preservation snapshot is `results/phase4/preservation.json`.

## Fixture construction and freeze

The suite contains 18 synthetic PDFs and one deliberately unsupported text file, constructed around specified extraction risks. ReportLab 5.1.0, Pillow 13.0.0 and pypdf 6.21.4 authored fixtures; these are not real contracts or independently validated ground truth. Labels and hashes were frozen before first extraction evaluation. No labels or PDF bytes changed after results were observed.

Manifest SHA-256:

```
9b43dca7273fc9240fbc281b3aac3bb7d6b8a28e3521b84e961ad583ae784342
```

`fixture_freeze.json` pins every fixture, metadata and manifest. `extraction_first_pass.json` preserves the first pass. Poppler rendered 16 renderable documents / 21 pages for visual inspection; a contact sheet and the displaced-negation page were inspected. Blank pages, rotation and unreadable glyphs are intentional. Corrupt and encrypted inputs were excluded from preview rendering; the encrypted fixture contains the supported synthetic text. Preview images and authoring packages remain outside Git.

## Actual results

Executed with Python 3.13.12 and pypdf 6.21.4. The complete suite passed **113/113 tests: all 87 original tests plus 26 PDF tests**, with no skips. The original 87 separately passed with site packages disabled. Python 3.8 grammar parsing was checked for new Python modules; no Python 3.8 runtime was available, and the optional parser requires Python 3.9+.

| Measurement | Result |
|---|---:|
| Expected fixture extraction outcomes | 19/19 |
| Extracted without detected document issues | 9/19 |
| Requires document review | 7/19 |
| Rejected | 3/19 |
| Canonical evidence items mapped | 25/25 |
| Original-page fragments verified | 26/26 |
| Deliberately invalid source locations rejected | 10/10 |
| PDF statutory proposals released | 0/19 |
| Live API calls | 0 |

The extra page fragment comes from a cross-page quotation. Multiple representations of the same fact/value/quote in pipeline diagnostics are deduplicated into one canonical evidence item with origin paths. These counts demonstrate extraction/provenance behavior on authored fixtures, not model accuracy or legal correctness.

| Fixture(s) | Extraction outcome | Review behavior |
|---|---|---|
| supported, multipage, wrapped | EXTRACTED (3) | Supported textual customer-control finding; exact page mapping |
| cross_page | EXTRACTED (1) | Two page fragments; final finding abstains pending visual review |
| negation_lines, negation_pages | EXTRACTED (2) | Abstain; split negation does not yield confident control |
| missing | EXTRACTED (1) | Abstain for missing supervisor evidence |
| conflicting | EXTRACTED (1) | Conflicting evidence retained |
| invoice | EXTRACTED (1) | No control inferred; manual metadata remains separate |
| reading_order | NEEDS_DOCUMENT_REVIEW (1) | Plain extraction falsely appears positive; layout disagreement suppresses that finding |
| empty, scanned, partial | NEEDS_DOCUMENT_REVIEW (3) | Missing page text; OCR/manual review; no invented replacement |
| rotated, active_content, unreadable | NEEDS_DOCUMENT_REVIEW (3) | Rotation, detected action and unreadable text respectively flagged |
| encrypted, corrupted, unsupported.txt | REJECTED (3) | Explicit unsupported-encryption, malformed-PDF or unsupported-file reason |

The invoice fixture is also processed through the contract adapter as a text stress test. Separate invoice ingestion is covered by automated tests and the recorded invoice demo. `evaluation-final/` holds all 19 detailed reports and the aggregate summary. There were no unexpected fixture outcome mismatches.

Original JSON baseline agreement is unchanged: **16/16** on the original set (false-confident evidence-removed decisions **0/4**), **12/12** on challenge v2, **9/12** on Phase 3 v3. Existing JSON provisional-reference behavior remains intact. See the new `original_baseline`, `v2_baseline` and `v3_baseline` artifacts; historical runs were not overwritten.

## Development failures preserved

The initial 111-test suite and subsequent 112-test suite passed. An added malformed-Unicode probe then failed: unencodable extracted text reached the outer rejection boundary instead of a page-level review status. A separate source-verification probe exposed an escaping Unicode encoding exception. The fix checks encodability at the page boundary and treats unencodable mapping input as failed verification. `unicode_regression_before_fix.txt` preserves the failed test; `release_tests.txt` records all 113 passing afterward. Fixtures and expectations were unchanged. The final evaluation preserved the original 19/19 extraction outcomes and source counts.

The authoring-only `add_js` call emitted a dependency deprecation warning. Runtime ingestion does not call it. Expected corrupted/encrypted/unsupported failures are reported above rather than counted as successfully extracted documents.

## Commands actually executed

From the repository, the following commands ran successfully unless explicitly described as the preserved failing probe:

```bash
.venv/bin/python -m unittest discover -v
.venv/bin/python -S -m unittest tests.test_core tests.test_llm tests.test_reliability tests.test_demo tests.test_phase3 -v
.venv/bin/python evaluate_pdfs.py --output-dir results/phase4/evaluation-v1
.venv/bin/python evaluate_pdfs.py --output-dir results/phase4/evaluation-final
.venv/bin/python pdf_demo.py --output results/phase4/demo.json
.venv/bin/python pdf_demo.py --contract tests/fixtures/pdf_v1/supported.pdf --metadata tests/fixtures/pdf_v1/transaction.json --invoice tests/fixtures/pdf_v1/invoice.pdf --output results/phase4/invoice_demo.json
.venv/bin/python demo.py
.venv/bin/python main.py --input tresata_adversarial_cases.json --mode baseline --output results/phase4/original_baseline.json
.venv/bin/python main.py --input tresata_challenge_v2.json --mode baseline --output results/phase4/v2_baseline.json
.venv/bin/python main.py --input tresata_challenge_v3.json --mode baseline --output results/phase4/v3_baseline.json
```

Saved outputs already exist; use a fresh `results/local/` path when reproducing. The default `python pdf_demo.py` writes no files. Its supported example prints page 1 `[0:24]` `Vendor supplies workers.` and page 1 `[25:57]` `Customer supervises each worker.`, followed by mandatory human review and statutory proposal withheld. Full actual terminal output is in `demo_output.txt`.

## Limits and remaining work

Provenance addresses extracted Unicode text, not visual glyph coordinates. Whitespace normalization retains original strings and a source map, but does not reconstruct original PDF layout. Plain/layout agreement from the same parser does not prove reading order, visibility or completeness. Hidden text, nested forms/images and complex layouts remain weaknesses. Exact quotes establish provenance, not semantic interpretation or actual working practices.

Every PDF-derived statutory proposal is withheld pending visual review, including clean selectable text. No workflow to record that confirmation exists yet. Detected source issues also suppress supported factual reliance. AI suggestions remain review-only. These are conservative boundaries, not a recall improvement or independently validated tax accuracy.

File, page, decoded-stream and text limits help with local inputs but do not provide a hard CPU/memory sandbox: parsing and decompression occur before some checks. OCR, password decryption, hostile public upload handling and legally relevant invoice-field inference are out of scope. The parser is an optional dependency; PDF tests explicitly skip when it is absent.

## Security and release

The release audit is recorded in `results/phase4/security_audit.json`: credentials and private files remain excluded; all included PDFs are hash-pinned synthetic fixtures. The intentional active-content fixture is flagged and never executed, and the encrypted fixture password is a public test value. No real financial documents, confidential assignment documents or private conversations were added. Pattern and exact-secret scans are bounded checks, not proof that arbitrary future documents are safe.

The delivery commit SHA is available without a self-referential hash in this file:

```bash
git log -1 --format=%H -- PHASE_4_REPORT.md
```

The final handoff and Issue #1 record the full SHA after push. Only `feature/full-product` is released; `main`, prior commits and repository visibility are preserved.

## Recommended Phase 5 interface (not implemented)

A small local reviewer interface could show manual transaction fields alongside a page preview and selected exact extracted passage, with plain/normalized views and document warnings. Verify the source hash before displaying saved spans. Keep supported textual evidence and AI suggestions visibly separate. Record reviewer identity/time, original evidence, corrections and decisions as an append-only audit record. Confirming a quote must not imply legal approval; statutory treatment still needs qualified review. Start with this review workflow before considering OCR or broad document automation.
