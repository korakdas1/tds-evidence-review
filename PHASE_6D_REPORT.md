# Phase 6D — external trust checkpoint and repeatable browser testing

Status: VERIFIED for the local prototype. No legal attestation, authenticated reviewer identity, or production-security claim. Base/fallback: `d64a7d2803f88ca74979d4bc2539bc56c9338875`. The phase commit is obtained with `git log -1 --format=%H -- PHASE_6D_REPORT.md`; the full SHA is also recorded in Issue #1 after push.

## Implementation and evidence

Added `webapp/checkpoint.py` and `review_checkpoint.py`: create an optional small external receipt, verify a consistent read-only SQLite snapshot, compare held prefix and report/context hashes, require intact reports/documents/history, exclusive private writes outside app data, bounded strict JSON, sanitized failures. No signatures or hidden database modifications. Added nine focused regression tests, including a fully self-consistent history rewrite that the local verifier accepts but the external receipt rejects, and deletion of an anchored tail. Decisions remain separate from findings.

Added `browser_tests/run.py`, its README and pinned optional `requirements-browser.txt`. Synthetic temporary stores, no provider access, loopback-only browser HTTP requests, explicit browser versions, exclusive output files, resource cleanup. No application UI changes.

Executed:

- `.venv/bin/python -m pip install -r requirements-browser.txt` — Playwright 1.64.1.
- `.venv/bin/python -m playwright install firefox` — Firefox 157.0.
- `.venv/bin/python -m unittest tests.test_checkpoints -v` — final **9/9**, 2.603 s.
- `.venv/bin/python -m unittest discover -v` — **196/196**, 31.597 s; original 187 tests unchanged, zero skips.
- `.venv/bin/python -m browser_tests.run --output results/phase6d/browser_final.json` — installed Google Chrome **154.0.8037.57, 25/25**; Playwright Firefox **157.0, 25/25**.
- `.venv/bin/python tools/release_check.py --output results/phase6d/security.json` and `git diff --check` — release checks recorded beside this report.

Browser checks cover fresh/manual PDF upload, validation, exact source selection, roving tabs, modal focus/inert/Escape, named visible controls, one reviewer decision appended with unchanged findings, original PDF frame/title, damaged-file quote-control suppression, forged report UI/list/export quarantine, scan warnings, 390px dashboard/workspace overflow, no uncaught browser errors and no external HTTP attempts. Native PDF raster rendering and a complete accessibility audit are not claimed.

## Development failures retained

`checkpoint_first.txt`: 9 tests ran, one failure/five errors. Validator initially expected hyphenated 36-character UUIDs while existing Store IDs are 32-character hex; one test read a document hash from the presentation view rather than the stored run. Corrected those new-code integration mistakes and test connection cleanup. `checkpoint_fixed.txt` and `full_tests.txt` record successful reruns.

`browser_first.json`: Chrome passed 24 checks, then failed the external-request assertion because its built-in PDF viewer uses `chrome-extension:` resources. The final harness separates browser-internal schemes from external HTTP traffic; final Chrome saw only `chrome-extension`, Firefox none. Both made zero external HTTP requests. No application behaviour was weakened to pass a test.

## Security and limitations

The receipt proves consistency only with its independently held copy. It is not a signature, trusted timestamp, reviewer authentication, factual proof or legal approval. Changes after the held prefix can be lost undetected. Replacing both receipt and database defeats verification; keep a copy independently controlled. README, architecture and `docs/EXTERNAL_CHECKPOINTS.md` explain this. Checkpoints contain hashes/IDs, not contract text, and should remain private.

Historical datasets, rules, prompts, submission artifacts, tests and results are untouched. Runtime databases and `.env` remain ignored. New committed results contain only synthetic test data and versions. No live model calls, API spending, public deployment, main changes or visibility changes. Resource isolation from 6C remains a resource boundary, not a complete hostile-code sandbox.

Next authorized step: Phase 7A explicit live inference controls, tested exclusively with mocked responses.
