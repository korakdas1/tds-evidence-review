# Phase 5: local review workspace (user interface)

> **Phase 5B audit note:** several claims below were corrected by the independent self-audit in [PHASE_5B_AUDIT.md](PHASE_5B_AUDIT.md). That audit found and fixed one high, three medium and seven low-severity defects, including undetected forged run reports, a navigation race and the mobile dashboard overflow. Current test count: 134/134. The text below is kept as originally written.

Implemented on `feature/full-product`, based on Phase 4 commit `a5db3a971bc88e3d54e56bde40987966abfb97c1`. Submitted `main` remains `e075a9087b8f4dbebee3fe74f2cb427c5bc3a3c0`. No live LLM requests, tax-rule changes, evidence-validation changes or Phase 6 work occurred.

## What was built

A local web application around the unchanged Phase 4 PDF pipeline. A finance reviewer can:

- upload a contract PDF and an optional invoice PDF, or open a synthetic sample;
- enter the transaction details by hand (they are never read from the PDFs);
- run the existing offline evidence review;
- read each page's extracted text with highlighted supporting quotations, and open the original PDF beside it;
- see validated evidence, AI suggestions, contradictions, missing information and rejected items as separate groups;
- record quotation checks, interpretation decisions, corrections, document checks, notes and case status;
- correct transaction details and run the analysis again, keeping every earlier run;
- read a persistent, tamper-evident review history and export it as JSON.

## Launch

```bash
python -m pip install -r requirements-pdf.txt   # pypdf 6.21.4, as in Phase 4
python review_app.py --open                      # http://127.0.0.1:8765/
```

Options: `--port 8765`, `--data-dir local_data` (the default; Git-ignored). Any host that is not a loopback address is refused. The app needs no internet access, API key or build step.

## Technology choice

The backend is standard-library Python plus the optional `pypdf`, and earlier phases were audited for dependency and network exposure. The application therefore adds **no new dependencies**:

- Server: `http.server.ThreadingHTTPServer` and `sqlite3` from the standard library.
- Frontend: plain ES modules, HTML and CSS served as static files. There is no npm, bundler, CDN or web font.
- Original PDFs open in the browser's built-in PDF viewer.

A React or Vite stack would have added a toolchain and an audit surface without adding review capability.

## Design system

Colour tells the reader **who is making a claim**:

| Colour | Meaning |
|---|---|
| Green | Validated by the existing rule checks |
| Violet | AI or supplied-extraction suggestion, not verified |
| Red | Clauses that contradict each other |
| Amber | Missing information or a document problem |
| Grey | Blocked by a safety check |
| Blue | A human reviewer's decision |

Three type voices separate the sources of text:

- Sans-serif is the application speaking.
- Serif is the contract's own words, used in quotations.
- Monospace is raw extracted page text, where character offsets matter.

Light and dark themes are both available. The layout is responsive down to 390 px, keyboard focus is visible, reduced-motion preferences are respected, and every status code also has plain-English wording.

## User journey

1. **Reviews (dashboard).** Lists cases with:
   - the automated finding in plain words;
   - a small colour tally of evidence types;
   - review progress ("2 of 6 checks");
   - status filters: awaiting review, in review, escalated, record complete.

   Side panels offer a contract drop zone, six synthetic samples and the colour key.
2. **New review.** Three steps:
   - Documents: contract required, invoice optional.
   - Transaction details: manual, with a note on Act selection by date.
   - Method: offline rule checks by default; supplied-extraction replay as an advanced option.

   Missing details are explained inline. A progress overlay shows each real request step.
3. **Workspace.** The header shows the automated finding, document reading status, a "Statutory proposal: Withheld for human review" cell and review progress. A permanent banner says decisions never change findings, release a proposal or authorise withholding.
   - **Left pane:** pages of the contract or invoice in three views: *Extracted text* with highlights, *Original PDF* and *Layout reading*. Flagged pages carry an amber dot.
   - **Evidence tab:** the finding panel (labelled "not a tax decision") and evidence cards grouped as listed above. Each card shows the quotation, its page and character range (re-verified; clicking jumps to and pulses the highlight), plain-English reasons and the review controls.
   - **Transaction tab:** manual fields, Act selection, run method and fingerprints, legal reference texts and limitations. It also holds "Correct details and run again".
   - **Documents tab:** file fingerprint check, page table, two-reading check and a document-check decision.
   - **History tab:** hash-chain status, analysis runs (earlier runs are viewable read-only) and a timeline of every system and reviewer event.
4. **Review controls.** Each card asks two separate questions:
   - "Does this text appear in the original PDF exactly as quoted?"
   - "Do you agree this sentence shows that …?"

   Disagreeing allows an optional correction, recorded beside the unchanged automated value. Case status choices are: in review, escalated to a tax specialist, review record complete, and reopen. **No option approves a tax treatment.**

Screenshots of these screens, all using synthetic data, are in `results/phase5/screenshots/`.

## Backend changes (for audit)

**No existing source file was modified.** `src/`, `main.py`, the demos, the evaluation scripts, the datasets, the frozen fixtures, the existing tests and all historical results are byte-identical to `a5db3a9`. Modified tracked files: `.gitignore` (adds `local_data/`), plus Phase 5 sections appended to `README.md`, `ARCHITECTURE.md` and `THIRD_PARTY_NOTICES.md`. New files:

| File | Purpose |
|---|---|
| `webapp/server.py` | HTTP adapter and routing; `App.handle()` is a pure function so it can be tested without sockets |
| `webapp/service.py` | Workflow: uploads, case creation, analysis runs, re-runs, samples, reviewer-event validation, view model |
| `webapp/store.py` | Append-only SQLite store with a per-case SHA-256 hash chain |
| `webapp/static/**` | Frontend: `index.html`, `css/app.css`, `js/{app,api,dom,ui,lexicon}.js`, `js/views/{dashboard,new-review,workspace}.js` |
| `webapp/samples/generate_samples.py`, `*.pdf`, `samples.json` | Deterministic synthetic sample documents and the sample manifest |
| `review_app.py` | Launcher |
| `tests/test_webapp.py` | 16 tests |
| `results/phase5/` | Test outputs, demo output, security audit, screenshots |

### How the existing pipeline is called

`ReviewService._analyse()` calls the unchanged `review_pdf_contract(metadata, contract_path, invoice_path, mode, client)`:

- **Offline rule checks:** `mode="baseline"`, `client=None`. The adapter itself supplies an unconfigured `OpenRouterClient("", "")`, as in Phase 4.
- **Supplied extraction replay:** `mode="hybrid"` with `ReplayClient`. This returns a caller-supplied five-field extraction JSON, has no network code, and is labelled `SUPPLIED_EXTRACTION_REPLAY_NOT_A_MODEL`.

The existing report counts the replay as `api_calls: 1`. The app records `model_network_calls: 0` and `simulated_client_invocations: 1` separately and displays both, so the replay is never presented as a model result. Supplied extractions are checked with the existing `extraction_errors()`.

### API routes

All routes are served only on loopback. Every POST requires the header `X-TDS-Review: 1`. The `Host` must be `127.0.0.1`, `localhost` or `[::1]`, otherwise the server returns 421.

| Route | Purpose |
|---|---|
| `GET /api/health` | Parser availability; `model_calls: DISABLED` |
| `POST /api/documents` | Raw PDF body plus an `X-Filename` header. Limits: 5 MiB, `.pdf` name and `%PDF-` magic. The basename is sanitised and stored under `<data>/documents/<sha256>/` |
| `GET /api/documents/<sha256>/file` | Serves the PDF only if the stored bytes still hash to `<sha256>`; otherwise 409 |
| `GET/POST /api/cases` | List cases; create a case and run the first analysis |
| `GET /api/cases/<id>[?run=<run_id>]` | View model for the latest or an earlier run |
| `POST /api/cases/<id>/events` | Record a reviewer event (validated below) |
| `POST /api/cases/<id>/runs` | Re-run with corrected details; requires a reviewer, a reason and at least one changed field |
| `GET /api/cases/<id>/export` | Full record: cases, runs with reports, events and chain status |
| `GET /api/samples`, `POST /api/samples/<id>/cases` | Sample list; open a sample (its files are hash-checked first) |

### Persistence

The tables are `documents`, `cases`, `runs` and `events`:
- **Append-only:** SQLite triggers abort every UPDATE and DELETE on all four tables.
- **Immutable runs:** each run stores the full report JSON and its SHA-256, re-verified on read.
- **Hash chain:** each event stores `prev_hash` and `hash = sha256(canonical[prev_hash, case_id, run_id, created_at, actor, kind, target, payload_json])`. `verify_chain()` recomputes the chain.
- **Derived state:** case status and per-item decisions are computed from the latest relevant event.

This is tamper-evident local bookkeeping, not a signed attestation.

### Review-event invariants

These are enforced in `service.record_event`:

- **Allowed kinds and decisions only:**
  - `QUOTE_CHECK`: `MATCHES_DOCUMENT`, `DOES_NOT_MATCH`, `UNCLEAR`
  - `INTERPRETATION_REVIEW`: `AGREE`, `DISAGREE`, `NEEDS_MORE_INFORMATION`
  - `DOCUMENT_CHECK`: `READING_ORDER_AND_COMPLETENESS_CONFIRMED`, `ISSUES_FOUND`
  - `CASE_STATUS`: `IN_REVIEW`, `ESCALATED_TO_QUALIFIED_TAX_REVIEW`, `REVIEW_RECORD_COMPLETE`, `REOPENED`
  - `NOTE`

  There is no approval, classification or withholding decision.
- **Targets:** each target must exist in the latest run. Events against a superseded run return 409.
- **Corrections:** allowed only with `DISAGREE`, only for valid values of that fact. They are stored with `applied_to_automated_analysis: false`.
- **Effect marker:** every reviewer event stores `effect = {changes_automated_findings: false, releases_statutory_proposal: false, authorizes_tax_treatment_or_withholding: false}`.
- **Reviewer identity:** names are required (up to 80 characters) and recorded as `SELF_DECLARED_LOCAL_REVIEWER_NOT_AUTHENTICATED`. Notes are limited to 4,000 characters, and control characters are rejected.
- **Origin:** set by server code only; an API caller cannot label an upload as a sample.

### View model

These rules live in `service.build_view`:

- **One card per quotation.** Canonical `evidence_items` are grouped by quotation; each fact/value claim becomes a separately reviewable assertion.
- **Card category,** in priority order:
  1. *Contradiction:* a supervisor claim while the text-level supervisor is conflicting, or a card that only lists contradictory evidence.
  2. *AI suggestion:* `AI_SUGGESTED_REQUIRING_REVIEW`.
  3. *Rejected:* `REJECTED_BY_SAFETY_GUARD`.
  4. *Validated:* `SUPPORTED_FACTUAL_EVIDENCE`.
  5. *Unvalidated:* anything else.
- **Duplicates.** A "cited as contradictory" duplicate of a primary claim on the same quotation is shown but needs no separate decision.
- **Span display.** Every page fragment is re-checked with the existing `verify_location()`, and the stored file hash must still match. Only spans passing both checks are highlighted or clickable.
- **On hold.** Document issues mark cards `suspended_by_document_review`. The page shows both the relied-on facts (reset by the adapter) and the text-level reading, labelled "on hold".

### Security headers

- **App page:** a strict CSP (`script-src 'self'`, `frame-ancestors 'none'`, no inline script or style), `nosniff`, `no-referrer`, and same-origin COOP/CORP.
- **PDF responses:** `frame-ancestors 'self'` only.
- **Uploads:** request bodies are size-checked before reading (JSON 512 KiB, uploads 5 MiB).
- **Errors:** unexpected exceptions return a generic 500, never a traceback.
- **Frontend:** never uses `innerHTML`; all document text is inserted as text nodes.
- **Active content:** PDFs flagged `ACTIVE_CONTENT_NOT_EXECUTED` are not embedded until the reviewer explicitly chooses to open them.

## Synthetic samples

Four new PDFs are generated deterministically by a small stdlib writer, with no timestamps, and are pinned by hash in `samples.json`. A test regenerates the bytes and compares them. Parties are fictional placeholders.

| Sample | Method | Actual outcome through the unchanged pipeline |
|---|---|---|
| Warehouse manpower support (+ invoice) | Offline rule checks | Customer-directed manpower supported by two validated quotations; proposal withheld |
| Event crew with unfamiliar wording | Supplied extraction replay; a **hand-authored** extraction labelled "Not a model output" | Supply validated; coordinator clause stays an AI suggestion (`EXACT_SOURCE_BUT_INTERPRETATION_NOT_VERIFIED`); finding insufficient |
| Plant maintenance with conflicting clauses | Offline rule checks | Conflicting evidence; two red contradiction cards |
| Reading order, cross-page, scanned | Offline rule checks on the frozen Phase 4 fixtures (by manifest hash) | Needs document review; text facts on hold; the scanned page infers nothing |

## Actual test results

Executed with Python 3.13.12 and pypdf 6.21.4:

| Run | Result |
|---|---|
| Full suite (`python -m unittest discover -v`) | **129/129 passed**, no skips: 113 pre-existing + 16 new (`results/phase5/final_tests.txt`) |
| Pre-existing 113 alone | 113/113 passed (`preexisting_113_tests.txt`) |
| Original 87 with site packages disabled (`-S`) | 87/87 passed (`original_87_without_site_packages.txt`) |
| `python pdf_demo.py`, `python demo.py` | Both exit 0; `pdf_demo.py` output is byte-identical to `results/phase4/demo_output.txt` (`pdf_demo_output.txt`) |

The new tests patch `urllib`, `socket.create_connection`, `subprocess.Popen`, `os.system` and `OpenRouterClient.complete` to fail if they are called, then assert they never were. The tests cover:

- **Samples:** each sample's evidence categories, and that `proposed_table_item` is always `None`.
- **No effect from review:** confirming every quotation and reading, checking every document and completing the record leaves the finding and the report hash identical.
- **Corrections** are stored beside the unchanged automated result.
- **Rejected actions:** 11 invalid actions, including `APPROVED`, `TAX_TREATMENT_APPROVED`, a non-reviewable duplicate, a correction attached to an agreement, and an over-long note.
- **Re-runs:** a re-run requires a reason and a change, keeps run 1 with its decisions, and refuses events against the old run.
- **Storage and integrity:** UPDATE/DELETE blocked on all tables; the hash chain detects a forced edit; an altered stored file hides spans and the original.
- **Uploads:** path traversal in filenames, non-PDFs, empty and oversized files, and `contract_excerpt` injection in the details are all rejected.
- **Request guards:** foreign `Host`, missing CSRF header, static path traversal, CSP present.
- **Binding:** loopback-only binding, a real socket round trip on `127.0.0.1`, and a 413 for oversized bodies.
- **Frontend source:** no remote URLs and no `innerHTML`.

**Visual and interaction verification.** Headless Google Chrome was driven through the DevTools protocol by a throwaway script that used no project dependencies. The script covered:
- the dashboard, in its empty and populated states;
- form validation errors, and real file upload through the form;
- case creation and clicking a source chip, which highlights and pulses the span;
- recording a quotation check, and a disagreement with a correction;
- re-running with a corrected payment date, then escalating the status;
- the history timeline, the embedded original PDF, dark theme, and a 390 px mobile layout (page width confirmed at 390 px).

No console errors or exceptions were reported. **Firefox and Safari were not tested.**

The bounded security audit (`results/phase5/security_audit.json`) passed:
- no token patterns or configured secret values in the 38 new or changed files;
- no remote URLs in the frontend;
- `.env`, `local_data/` and uploaded documents are ignored.

## Limitations

- **Highlights are text offsets, not page positions.** They mark characters in the extracted text. The original PDF opens in the browser's own viewer, which cannot be highlighted. The UI says so next to every view, and no bounding boxes are drawn or implied.
- **No authentication.** Reviewer names are self-declared on one computer. This is not a multi-user system.
- **Tamper evidence is limited.** The hash chain detects edits made through SQLite but is not signed. Someone with file access can rebuild the database.
- **Browser viewer behaviour varies.** It was tested only in Chrome. PDFs with detected active content are gated, but a browser viewer may still execute document scripts if the reviewer opts in.
- **No AI suggestions offline.** The default rule checks never produce them, and the replay mode only shows how hand-supplied extractions are treated. No live model integration was added.
- **Proposals stay withheld.** Recording reviews does not, and cannot, release a statutory proposal. A future release workflow would need an explicit, separately reviewed design.
- **Upload robustness.** Parsing limits are inherited from Phase 4. They are not a sandbox, and the server is not hardened for hostile public uploads.
- **Scale.** The dashboard re-hashes stored files for every case on each load, which is fine for local use but not for large volumes.
- **Accessibility.** Keyboard and focus states were checked visually, but no full screen-reader audit was done.

## Release

Committed to `feature/full-product` after the validation above. Not merged into `main`. Phase 6 was not started.
