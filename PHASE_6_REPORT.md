# Phase 6: reliability, rule versioning and release quality

- **Starting point:** Phase 5B commit `19103a249ff26150c93956fc81594395495b0262`, with 134 tests passing.
- **Implementation commit:** `ee62e45d03605914cf5c000f1b0382b85103588b` on `feature/full-product`.
- **Follow-up commit:** this report plus a one-line server-log fix, made after the fresh-clone check (see *Reproduction*). Its SHA is recorded in GitHub Issue #1 and can be found with `git log -1 --format=%H -- PHASE_6_REPORT.md`.
- **Unchanged:** submitted `main` is still `e075a9087b8f4dbebee3fe74f2cb427c5bc3a3c0`.
- **Out of scope:** no live model calls, paid services, public deployment or new legal classifications.

## Summary

Phase 6 is engineering hardening. The visual design and workflows are unchanged.

| | Count | Notes |
|---|---|---|
| High-severity defects found and fixed | 1 | |
| Medium-severity defects found and fixed | 5 | |
| Low-severity defects found and fixed | 9 | |
| Test-harness errors of my own | 3 | Recorded below, not product defects |
| Tests passing | 155/155 | 134 previous + 21 new |

Of the 16 new behavioural tests (integrity, PDF, reliability and server), 14 fail on the Phase 5B code and pass now. The two that pass on the old code are guards for behaviour that was already correct. The 5 rule-versioning tests need the new configuration API to run at all.

Legal behaviour is unchanged. The three historical baselines are identical apart from the new `rule_version` field: status agreement stays **16/16, 12/12 and 9/12**. The frozen PDF evaluation is identical to Phase 4: **19/19 expected outcomes, 25/25 items mapped, 26/26 fragments verified, 10/10 invalid-location probes rejected**.

## Defects found, severity and fixes

| # | Severity | Defect (how it was confirmed) | Fix | Regression evidence |
|---|---|---|---|---|
| 1 | **High** | **The API exposed untrusted findings.** When a stored run failed its integrity check, only the browser masked the finding. `GET /api/cases/<id>`, `GET /api/cases` and the export still returned the forged finding, evidence and page text. (Confirmed by code inspection and tests against `19103a2`.) | One `assess()` check is used by every read path. When it fails, the server withholds the finding, evidence, missing-information list and page text, and returns diagnostics only: each check's result, the stored and recorded hashes, and the recorded history. Exports put such runs in a `forensic_untrusted` section with an UNTRUSTED warning, and new decisions are refused. | `IntegrityAndReliabilityTests`: forged row, forged hash, missing anchor, broken chain, case-record tampering; each asserts that the untrusted strings are absent from the API responses |
| 2 | Medium | **PDF decompression bomb.** A 1.4 MB, 20-page PDF drove the process to about 1.5 GB of memory, because pypdf inflates each stream up to 75 MB before the existing 2 MiB page check runs. (Measured.) | Parsing runs under temporary, context-local `pypdf.apply_configuration` limits of 8 MiB per stream for every filter. Hitting the limit is reported per page as `DECOMPRESSION_LIMIT`. Measured result: 0.36 s and 47 MB. The global pypdf settings are restored afterwards. | `test_decompression_bomb_is_bounded_and_flagged` (peak traced memory under 200 MB); frozen PDF evaluation unchanged |
| 3 | Medium | **Unbounded concurrent analyses** multiplied defect 2. | One analysis at a time; a waiting request gets 503 with a retry message after 20 s. | `test_analysis_concurrency_limit` |
| 4 | Medium | **Unbounded disk use** by uploads. | Storage quota, default 512 MiB and 2,000 documents, set with `--max-storage-mb`. Over quota returns 507 with instructions. Duplicates do not count. | `test_storage_quota` |
| 5 | Medium | **"Upload it again" could never work.** Uploads are de-duplicated by hash, so re-uploading identical bytes returned the damaged or missing stored copy unchanged. (Found during browser testing: a 409 on a deliberately damaged sample.) | Identical bytes are authentic by hash, so a re-upload now atomically restores a missing or altered stored copy (0600). | `test_reuploading_identical_bytes_repairs_a_damaged_stored_copy` |
| 6 | Low | **Case record not anchored.** The case title, reference and origin were not checked against the history, so a title could be changed to, for example, "Approved for withholding". | The case row is compared with the hash-chained `CASE_CREATED` event. | `test_case_record_tampering` |
| 7 | Low | **Checks allowed on a damaged PDF.** A reviewer could record "matches the PDF" or a document check when the stored PDF was damaged and could not be displayed. | New `DOCUMENTS_UNAVAILABLE` state: the trusted analysis stays visible, but quotation and document checks are refused (409) and hidden in the UI. Notes and status changes still work. | `test_corrupted_stored_document_keeps_trusted_analysis_but_blocks_pdf_checks` |
| 8 | Low | **Decision/re-run race.** A decision could attach to a run that was superseded while the request was in flight. | The latest run is re-checked inside the event's write transaction. | `test_decision_racing_a_rerun_is_refused` |
| 9 | Low | **Export had no integrity information.** It carried no integrity status or checksum and exported compromised runs as normal data. | Export v2: per-run integrity, `integrity_status`, the quarantined section, and a `content_sha256` checksum (documented as a transit checksum, not a signature). | `test_export_checksum_and_status` |
| 10 | Low | **Lenient request parsing.** API bodies accepted duplicate JSON keys and NaN, unlike the pipeline's own parser. | The strict `parse_json` is used for request bodies, and responses use `allow_nan=False`. | `test_strict_json_and_safe_responses` |
| 11 | Low | **Unexpected errors left no local trace.** | The exception *type* only is logged locally, because messages can contain document text. Clients still get a generic message. SQLite "busy" returns 503. | `test_unexpected_errors_are_generic_to_clients_and_typed_in_the_log` |
| 12 | Low (accessibility) | **Keyboard and dialog gaps.** Tabs had no arrow-key support or roving tabindex. The viewer's document switcher misused `role="tab"`. Dialogs left the page behind reachable. | Arrow, Home and End keys move between tabs, with a roving tabindex and `aria-controls`. The switcher is a pressed-button group. The background is `inert` while a dialog is open. | Chrome and Firefox keyboard checks |
| 13 | Low (accuracy) | **Overstated wording.** The UI said history entries "cannot be edited or deleted", which implies tamper-proofing. | Now: "The app never edits or deletes entries… tamper-evident, not tamper-proof." The diagnostics panel states the unsigned-SQLite limit. | Text review |
| 14 | Low | **Startup banner missing from redirected logs.** | `flush=True`. | Checked with redirected output |
| 15 | Low | **No way to export a failed case.** The untrusted screen offered no export. | Added an "Export forensic record" link. | Browser |

### Investigated with no defect

- **Date parsing.** It already rejected non-ASCII digits, whitespace and newlines, impossible dates and year 0. These are now frozen regression cases.
- **Missing history anchors.** These were already caught by Phase 5B's anchor check; they are now tested explicitly.
- **Concurrent reviewer events.** 8 threads × 5 events produced one linear chain of 42 entries.
- **Active-content PDFs.** These are still flagged and gated before the browser viewer opens them.

### My own test-harness errors (not product defects)

- **Wrong "real bug" call.** I briefly reported that clicking a dashboard row did not open the case. In fact my script matched the loading-skeleton rows, which share the `case-row` class. A real mouse click works in Chrome and both Firefox builds. The claim is retracted.
- **Blank Firefox PDF pane.** Playwright's Firefox 155 build ships with `pdfjs.disabled = true`. Real Firefox 158 renders the original PDF with pdf.js inside the app's CSP.
- **Non-independent Firefox 158 check.** An early run's decision check reused a stamp from an earlier run. The final runs use a fresh case and require the stamp count to go from 0 to 1.

## Rule versioning

`src/act_selection_v1.json` (`act_selection@1.0.0`) replaces the hard-coded boundary, Act names and trigger in `src/rules.py`.

**`load_act_selection()` runs at import and fails rather than guesses.** It requires:
- the only implemented trigger: the earlier of credit and payment date, with both dates required;
- at least two distinct Acts, in contiguous, ordered, non-overlapping periods with open ends;
- a semantic version;
- agreement with the `effective_from` of the cited `act_transition` rule in `rules_v1.json`.

13 malformed-config variants are rejected in tests.

**Traceability.** Every date result now includes `rule_version`. The config file is included in pipeline `implementation_sha256`. `OLD_ACT`, `NEW_ACT` and `BOUNDARY` are derived from the config for compatibility.

**What it does not do.** The config holds only Act periods; a test enforces its exact key set. It adds no rates, thresholds or classifications and is labelled `NOT_INDEPENDENTLY_LEGALLY_VALIDATED`. As before, dates before the boundary map to the 1961 Act. The prototype does not model that Act's own commencement; this existing behaviour is documented in a fixture, not endorsed.

**Development regression cases.** `tests/fixtures/phase6/act_selection_cases.json` holds 23 synthetic cases, hash-pinned in a manifest and labelled `DEVELOPMENT_REGRESSION_CASES_NOT_INDEPENDENT_VALIDATION`. They cover:
- boundary days and the earlier-of rule in both orders;
- a leap day;
- impossible dates;
- missing, empty, integer, compact, slash-separated, datetime and ISO-week values;
- whitespace and non-ASCII digits.

Result: 23/23 (`results/phase6/act_selection_development_results.json`). This checks the refactor; it is not legal validation.

## Tests and actual results

| Check | Result |
|---|---|
| `python -m unittest discover -v` | **155/155 passed**, no skips (`results/phase6/final_tests.txt`) |
| Original 87 with site packages disabled | 87/87 |
| New Phase 6 behavioural tests against Phase 5B code | 14 of 16 fail as expected (the two passing are guards) |
| Historical baselines (`main.py --mode baseline`) | Identical apart from `rule_version`; 16/16, 12/12, 9/12 |
| Frozen PDF evaluation (`evaluate_pdfs.py`) | Identical to Phase 4 summary |
| `pdf_demo.py`, `demo.py` output | Byte-identical to the recorded Phase 4 and Phase 3 outputs |
| Fresh clone following README | New venv, `pip install` gives pypdf 6.21.4; demos OK; 155/155; `/api/health` OK; `--host 0.0.0.0` refused; `--max-storage-mb 0` rejected |

### Browser results

Full details are in `results/phase6/browser/`.

**Chrome** (headless, DevTools protocol):
- No interactive element lacks an accessible name on the dashboard, form, workspace tabs, dialogs or the untrusted screen.
- Arrow, Home and End navigation works with wrap-around and a roving tabindex.
- Dialogs make the background inert and restore it on Escape.
- A forged case shows diagnostics only, with no forged text anywhere. The forensic export reports INTEGRITY_FAILED with 0 trusted and 1 quarantined run.
- A damaged stored PDF shows the amber banner and no quotation checks.
- The full Phase 5B workflow regression passes.

**Firefox, over WebDriver BiDi:** 14/14 interaction checks pass on both **Playwright Firefox 155** and **system Firefox 158**. The checks cover:
- form validation, with real typing clearing errors;
- Shift+Tab reaching only visible drop zones;
- opening a case;
- exact-span highlighting;
- arrow-key tabs;
- recording a new decision on a fresh case;
- a focus trap and inert background in dialogs, and Escape;
- the PDF frame;
- a 390 px mobile layout with no overflow.

There were no console errors or warnings.

**Not tested:** Safari/WebKit (no engine available here) and screen readers.

## Security findings

The audit in `results/phase6/security_audit.json` passed. It covered 57 files changed since `19103a2`:
- no token patterns and no credential values from `.env`;
- no database, upload, profile or transcript files;
- no `eval`/`exec`/`subprocess`/`pickle`/`innerHTML` patterns in `webapp/` or `src/`;
- no remote URLs in the frontend;
- `.env` untracked, ignored and 0600; `local_data/` and uploads ignored;
- no new PDFs;
- `main` unchanged locally and on the remote.

Browser profiles and test databases stayed in scratch folders outside the repository.

The security-relevant fixes are items 1–5 and 7–11 above.

## Remaining limitations

- **Unsigned history.** Anyone with file access who recomputes every hash can build a consistent forged database. Deleting the newest history entries is undetectable without an external copy of the chain head. The protection is tamper-evident, not tamper-proof.
- **PDF parsing is in-process.** Memory is now bounded per stream and only one analysis runs at a time. There is still no CPU-time limit or OS sandbox for hostile documents, and pypdf logger silencing is process-global (safe only because of the single analysis slot).
- **Reviewer identity is self-declared.** This is a single-user, loopback-only prototype.
- **Browser coverage.** Safari is untested and no screen-reader audit was done. The browser checks are scratch scripts, not committed CI tests.
- **Legal scope.** The legal mapping is not practitioner-validated. The Act-selection config restates the existing rule only. Evaluation sets are synthetic development data, not independent validation, and there was no model evaluation in this phase.
- **Analysis capability.** No OCR, no visual-coordinate highlighting, and no reading-order guarantee. Invoices are for inspection only.

## Reproduction

```bash
git checkout feature/full-product
python -m pip install -r requirements-pdf.txt
python -m unittest discover -v                      # 155 tests
python review_app.py --open                         # http://127.0.0.1:8765/
python main.py --input tresata_adversarial_cases.json --mode baseline --output results/local/original-recheck.json
python evaluate_pdfs.py --output-dir results/local/pdf-evaluation-recheck
```

Output files and directories must be new; existing results are never overwritten. Phase 6 outputs are in `results/phase6/`.

## Recommendation for the next milestone

Before adding any live-model integration, build **trustworthy evaluation and audit foundations**:
1. **Practitioner-labelled holdout set.** A small one, written independently of the developers, to measure the rule checks and abstention honestly.
2. **External anchoring of the review history.** For example, export the chain head to a reviewer-held record, or sign exports, so truncation and full rewrites become detectable.
3. **Committed browser-test harness.** Turn the Chrome and Firefox scripts into a maintained harness that runs alongside the unit tests.
4. **Sandboxed parsing.** Run PDF parsing in a separate process with CPU and memory limits if documents may come from untrusted sources.

A live-model phase should begin only with explicit authorisation, a pinned model, a cost cap, and evaluation on that holdout set. Phase 6 does not start it.
