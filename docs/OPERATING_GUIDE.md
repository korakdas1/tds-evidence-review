# Local operating and demonstration guide

## Install and start

Use Linux with Python 3.9+; the verified environment is Python 3.13.12. PDF workers depend on Linux resource limits and the storage layer on POSIX no-follow operations. The original JSON baseline remains available without PDF dependencies. Start from a fresh checkout of the development branch, preserving submitted `main`:

```sh
git clone --branch feature/full-product https://github.com/korakdas1/tds-evidence-review.git
cd tds-evidence-review
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-pdf.txt
python local_demo.py
python review_app.py --open
```

After dependency installation the default app and demos need no internet or credentials. `local_demo.py` uses only frozen synthetic files and a temporary database, then removes its scratch uploads/history; it does not touch `local_data`. Its original historical-LLM section is a replay of the preserved earlier record, not a new model response. `python demo.py` remains the minimal dependency-free JSON demo; `python pdf_demo.py` remains the PDF provenance demo.

For the browser workflow, open the Warehouse sample; follow an evidence page reference, compare **Original PDF**, record a quote/interpretation decision, inspect Transaction and History, correct a manual date and rerun. All PDF statutory proposals remain withheld. Open Event crew for a **hand-authored simulated** suggestion, and Scanned page for missing selectable text. The offline and mocked-live browser harnesses reproduce these paths; see [browser tests](../browser_tests/README.md) and [live controls](LIVE_MODE.md).

## Data, backups and privacy

Only this computer can connect via loopback; this is a local single-user prototype, not a publicly deployed service. Reviewer names are self-declared, not logins. Avoid sharing the data directory with untrusted OS users. Uploaded PDFs and SQLite records are private files in `local_data/` (Git-ignored); use another explicitly chosen private folder with `--data-dir` if needed. The app records immutable analysis runs and append-only decisions rather than editing prior findings.

Stop the app before copying the complete data directory for a consistent backup, or use SQLite's supported online-backup tooling under your own administration. Keep documents and database together. Preserve a separate [external checkpoint](EXTERNAL_CHECKPOINTS.md) under independent reviewer control if you need to detect changes from a held history prefix. A checkpoint is not a signature, authenticated reviewer or legal approval.

Exports can contain full source text, manual financial metadata and raw model output. Store them privately; do not commit real exports/contracts or include `.env` in archives. Untrusted runs are placed only in the explicitly labelled forensic quarantine portion of exports. Do not mistake that section for validated evidence. The public repository contains synthetic demonstration/test documents and historical synthetic experiments; no real contracts are required for demonstrations.

## Failure handling

- **No selectable text / scan:** no OCR is performed. Obtain a reliable text PDF or review the original manually.
- **CPU/memory/time/output limit or parser failure:** the isolated worker discards all partial text/spans and is reaped. The UI explains the failure. Do not raise limits blindly to make a complex document pass. Resource isolation still runs under the same OS account; hostile-code isolation would require a stronger sandbox.
- **Reading-order disagreement/cross-page wording:** facts remain on hold; compare the original visually. Exact extracted characters do not prove printed reading order or actual working practice.
- **Stored file damaged or missing:** source comparison is unavailable. Re-uploading identical bytes repairs the stored document; a different document belongs in a new case. Do not replace files manually and assume old quotations apply.
- **History/report/context integrity failure:** findings and decisions are suppressed by the server, including list/API/export trusted sections. Preserve the database for investigation and create a new review from verified source documents/manual inputs. Do not remove triggers or rewrite hashes to hide a failure.
- **Quota reached:** the default 512 MiB/2,000-document quota covers registered upload files. Duplicate content does not consume another upload slot. Database history and orphan files are not covered; monitor disk space. The app offers no automatic destructive purge. Stop it and archive a complete workspace rather than deleting individual referenced files.
- **Database busy:** wait for the current local operation to finish and try again. Completed prior history is retained. A failed initial analysis does not create a partial case; provider attempt reservations intentionally survive failed report commits.
- **Live timeout/429/provider refusal:** no automatic retry. A durable stop is recorded; diagnose before choosing a separately configured workspace. No implicit reset or paid fallback is provided. Lack of a completed run does not prove a timed-out provider never received data.

## Verification commands

```sh
python -m unittest discover -v
python evaluate_pdfs.py --output-dir results/local/pdf-check-new
python evaluate_comparison.py --output-dir results/local/comparison-new
python tools/release_check.py --output results/local/security-new.json
# Optional browser dependencies and binaries installed separately:
python -m browser_tests.run --output results/local/browser-new.json
python -m browser_tests.live --output results/local/mocked-live-new.json
```

Use fresh output names; preserved reports are never replaced. The release checker is a local Git inventory/pattern/known-secret scan, not a complete vulnerability assessment. No test suite authenticates tax correctness, reviewer independence or provider claims. The browser harness covers focused labels, keyboard/focus and mobile overflow, not complete WCAG compliance or native PDF-viewer security.

## Dependencies and readiness

Runtime PDF dependency: pinned `pypdf` 6.21.4 ([BSD-3-Clause](https://github.com/py-pdf/pypdf/blob/6.21.4/LICENSE)); standard library for HTTP/SQLite and workers. Optional browser tests use Playwright 1.64.1 ([Apache-2.0](https://github.com/microsoft/playwright-python/blob/v1.64.1/LICENSE)) and separately installed Chrome/Firefox binaries with their own distribution terms; no browser binary is committed. The repository itself has no selected open-source license; public visibility alone is not a reuse license.

Suitable for an independently reviewed **local synthetic demonstration**. Not a production tax product, public hosting target, hostile-document security sandbox, authenticated multi-user system or independently practitioner-validated classifier. Live integration has only mock-based development verification; actual provider availability/performance requires separate authorization and evidence. No Phase 10, paid service or public deployment is started by these commands.

To reproduce fresh-clone setup for a committed development snapshot, run `python tools/fresh_clone_check.py --output-dir results/local/fresh-clone-new`. It clones the local committed branch into a disposable folder, builds a fresh virtual environment, installs only the pinned PDF runtime dependency from PyPI, runs the full suite/demos/evaluation, starts a real loopback server and checks a synthetic review/export. It excludes credential-related environment variables and never copies `.env` or makes inference calls. The temporary checkout is removed; command logs and exact commit SHA remain in the chosen output folder.
