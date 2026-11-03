# Phase 5B: independent self-audit of the review workspace

Audited commit: `ef4ed0f` (Phase 5) on `feature/full-product`. Submitted `main` remains `e075a9087b8f4dbebee3fe74f2cb427c5bc3a3c0`. The Phase 5 report was treated as a set of claims to verify, not as evidence. No Phase 6 work was started.

## Verdict: READY, for local use with synthetic or authorised documents

The audit found **one high, three medium and seven low-severity defects**, plus one flaky test. All are fixed, and six backend regression tests were written so that they fail on `ef4ed0f` and pass after the fixes. The full suite passes 134/134, unchanged across four consecutive runs. No review action can change an automated finding or release a statutory proposal; this is confirmed by tests and by code inspection. The data to be pushed contains no credentials, private documents or databases.

"Ready" covers the stated scope: a single-user local prototype. The remaining risks below are design limits, not open defects.

## Findings

| # | Severity | Finding | How it was confirmed | Fix | Regression check |
|---|---|---|---|---|---|
| 1 | **High** | A stored analysis could be forged without detection. Editing a run's `report_json` and recomputing that row's own `report_sha256` still showed **"VERIFIED"** and **"History intact"**, and the forged finding was displayed (`CONFLICTING_EVIDENCE` became customer-directed). The Phase 5 tamper-evidence claim was overstated. | Script against a scratch database | Each run is now anchored to the `report_sha256` recorded in its hash-chained `ANALYSIS_RUN` event (`anchor_runs`). If either check fails: the case shows a red integrity banner, the finding is masked in the workspace and on the dashboard, review controls are removed, and the API refuses new events (409). | `test_forged_report_with_recomputed_row_hash_is_detected_and_locks_review`, `test_broken_history_refuses_new_decisions`; browser |
| 2 | Medium | Navigation race. Leaving a case before it finished loading showed the old case workspace under the `#/new` URL, and the form never appeared. | Browser, with the case request delayed by 1.2 s | Each navigation renders into its own container, so a late result lands in a detached node. | Browser: the form shows and the workspace does not |
| 3 | Medium | Uploaded contracts and the review database were readable by other OS users (folders 0775, files 0644). | `stat` on the data folder | Data folders are created 0700, and the database and uploaded files 0600. | `test_local_data_is_private_to_the_user` |
| 4 | Medium | The mobile dashboard overflowed horizontally (543 px of content on a 390 px screen). Phase 5 had checked only the workspace at mobile width. | Browser, `scrollWidth` | The single-column grids use `minmax(0, 1fr)` so long titles can shrink. | Browser: dashboard, form and workspace all 390 px; tablet 805/820 px |
| 5 | Low | A client that sent less body than its `Content-Length` held a server thread forever. | Raw socket | 20 s request socket timeout. | `test_stalled_request_times_out_and_cross_origin_preflight_fails` |
| 6 | Low | The hash chain could fork if two server processes used the same data folder, because the lock was per process. | Code review; fork insert proven possible | `BEGIN IMMEDIATE` on appends, plus a unique index on `(case_id, prev_hash)`. | `test_chain_cannot_fork_even_from_another_process` |
| 7 | Low | Recording any decision rebuilt the original-PDF view, reloading the PDF and losing the reviewer's place. | Browser: a different iframe element after the decision | A decision redraws only the header and analysis panes. | Browser: same iframe after a decision |
| 8 | Low | A "correction" equal to the automated value was accepted (for example, disagree and correct to the same answer). | Old code accepted it (test fails on `ef4ed0f`) | Rejected with 400. The UI already hid that option. | Added to `test_invalid_review_actions_are_rejected` |
| 9 | Low (accessibility) | Each file slot had an invisible second tab stop. Dialogs had no focus trap: Tab left the "Add note" dialog for the page behind. | Browser, real Tab key events | The hidden file inputs are removed from tab order; dialogs trap Tab and Shift+Tab. | Browser tab traces |
| 10 | Low | "Correct details and run again" could silently change a non-standard stored residency value to the first menu option. | Code review (reachable through API-created cases) | The recorded value is kept as an extra option, marked "(as recorded)". | Code review |
| 11 | Low | Flaky test: `test_real_server_answers_on_loopback` intermittently raised `BrokenPipeError`. The server correctly answered 413 before the 600 KB body was sent, racing the client. | Failed once in the audit run | The test declares an oversized length without sending the body. | 15 repeated runs plus 4 full-suite runs, all passing |
| 12 | Info | Some browsers, such as Chrome on Android, do not display PDFs inline, and long documents overflowed the page list. | Review | Added an "open it in a new tab" link (still behind the active-content gate); the page list wraps. | Browser |

### Investigation: red borders on populated New Review fields

This is not a code defect. Computed styles were measured in Chrome:
- Untouched fields: border `rgb(195, 205, 216)`.
- After an empty submit: required fields get `aria-invalid="true"` and border `rgb(179, 38, 58)`.
- After real typing: the attribute is removed and the border returns to grey. Measured on the populated form: 0 invalid fields, 0 red borders.

Two causes produced the observed red borders:
- **Phase 5 screenshot `14`** was taken before the clear-on-edit handler existed, so the error state persisted after the fields were filled.
- **The committed `08-new-review-form.png`** was captured during the 0.15 s border transition after scripted edits.

The screenshot has been replaced with a settled capture. Fields that are still empty correctly stay red after a failed submit.

### Claims in the Phase 5 report that were wrong or overstated

- **Tamper evidence:** the "report fingerprint (verified)" label did not detect a forged row (finding 1). It does now.
- **Keyboard checking:** "Keyboard and focus states were checked visually" was not substantiated; real keyboard testing found finding 9.
- **Mobile layout:** "Responsive down to 390 px" was true for the workspace only (finding 4).
- **Test stability:** the 129/129 result included a test that can fail by timing (finding 11).

## Requirement checks

**Review decisions cannot change findings or release proposals.**
- **Store:** the application only INSERTs. There is no UPDATE or DELETE statement, and triggers block both.
- **Analysis runs** are created only by case creation and re-runs, both through the unchanged `review_pdf_contract()`.
- **Proposals:** `proposed_table_item` is only read, and the PDF adapter always sets it to `None`.
- **Tests:**
  - Every decision type, including completing the record, leaves the finding and the report hash byte-identical.
  - A re-run with corrected details still has no proposal.
  - 12 invalid actions are rejected, including `APPROVED`, `TAX_TREATMENT_APPROVED` and a `WITHHOLDING_AUTHORISED` kind.
- **Browser:** escalating the status still shows "Withheld for human review".

**API security** (raw-socket probes against a running server):
- **Loopback only:** non-loopback binding is refused.
- **Host header:** foreign, missing and wrong-port values return 421, which blocks DNS rebinding.
- **CSRF:** a POST without `X-TDS-Review` returns 403, including a cross-origin `text/plain` form.
- **Cross-origin access:** CORS preflight returns 501 with no `Access-Control-Allow-Origin`, and cross-origin GET responses carry no CORS header.
- **Request bodies:** chunked or missing length returns 411; negative or huge length returns 413; stalled bodies time out.
- **Paths:** encoded and double-slash traversal attempts return 404.
- **Headers:** the strict CSP and `X-Frame-Options: DENY` are present.

**Uploads.**
- **Validation:** the 5 MiB limit, `.pdf` name and `%PDF-` magic are all enforced; a fake PDF returns `415 Only PDF files can be reviewed`.
- **Storage:** filenames are sanitised and confined to the documents folder.
- **Display:** PDFs are served `nosniff` only after a hash re-check, and active-content PDFs are gated.

**SQLite and hash chain.**
- **Append-only:** triggers abort UPDATE and DELETE on all four tables.
- **Detection:**
  - a forced event edit makes the chain report BROKEN;
  - a forged run is detected (finding 1);
  - a fork is impossible (finding 6).

## Browser results

These checks used headless Chrome driven over the DevTools protocol, with real file selection, real typing and real Tab, Shift+Tab and Escape keys.

**Upload and review flow.** Uploading a contract and invoice through the form works. Validation messages are plain English ("Enter the credit date.").

**Evidence.**
- A source chip highlights and pulses the exact span; Enter on a highlight selects its card.
- Recording a quotation check works.
- A disagreement with a correction is stored, and the automated value is not offered as a correction.

**Re-runs and history.**
- Correcting the payment date and running again creates run 2, and the history shows `Payment date: 2026-10-02 → 2026-10-20` with the chain intact.
- Escalation keeps the proposal withheld.
- A tampered case shows the banner and no controls, and the dashboard flags it.

**Theming and layout.**
- **Dark theme:** body text `rgb(228,234,240)` on `rgb(12,19,26)`.
- **Mobile (390 px):** dashboard, form and workspace all fit without horizontal scroll.
- **Tablet (820 px):** layout fits.
- **Console:** no errors, apart from the deliberate 415 probe.

**Firefox** (Playwright's bundled build, headless screenshot only) renders the dashboard correctly, including ES modules, `color-mix()` and `:has()`. Interactive flows were not run in Firefox; Safari was not tested.

Screenshots are in `results/phase5b/screenshots/`, and the replaced Phase 5 form screenshot is in `results/phase5/screenshots/08-new-review-form.png`.

## Tests

- `python -m unittest discover -v`: **134/134 passed**, no skips (113 pre-existing + 21 review-app tests). Output: `results/phase5b/final_tests.txt`.
- Original 87 with site packages disabled: 87/87 (`original_87_without_site_packages.txt`).
- `pdf_demo.py` output is byte-identical to `results/phase4/demo_output.txt`.
- Pre-Phase-5 source, datasets, fixtures and historical results are unchanged since `a5db3a9`.

## Pushed data

`results/phase5b/security_audit.json` reports PASS:
- It covered the 50 files differing from the remote branch and the 42 blobs in unpushed commits.
- It found no token patterns and no credential values from `.env`.
- `.env` is untracked, ignored and 0600; `local_data/` and uploads are ignored.
- The only PDFs are the four synthetic samples, and no databases, transcripts or conversations are included.

One scanner hit was triaged as a false positive: `README.md` contains the public `OPENROUTER_MODEL` identifier, which is already in the submitted `main`. Audit databases and uploads were kept in a scratch folder outside the repository.

## Remaining risks (not fixed; inherent to the current design)

- **Unsigned history:** someone with file access who recomputes every hash can rebuild a consistent forged database, and deleting the newest events is not detectable without an external anchor. Reviewers could record the history head hash shown in exports.
- **Self-declared names:** reviewer names are not authenticated, so this is not a multi-user system.
- **Opted-in PDFs:** if a reviewer opens a flagged active-content PDF anyway, the browser's viewer may run its scripts.
- **Browser coverage:** interactive testing was Chrome only; Firefox was a static render and Safari was untested. There is no JavaScript unit-test harness, so frontend regressions rely on the scripted browser checks above.
- **Accessibility:** no full screen-reader audit was done, and tabs do not support arrow-key navigation.
- **Uploads:** they are not a sandbox and disk use is unbounded. Re-uploading identical bytes keeps the first filename.
- **Scale:** the dashboard re-hashes every stored contract on each load, which is fine locally.
