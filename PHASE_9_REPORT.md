# Phase 9 — product finishing and fresh-clone verification

Status: **READY for an independently reviewed local synthetic demonstration**, not production tax use or public hosting. No live inference, paid service, visibility change or main modification. Base/fallback: `cb56e2c0e0a3d27e9074165333949857ac3c70c5`. Implementation snapshot tested from a fresh clone: **`11ba8fff30665894aefa76d2f26700888b169782`**. This report/evidence-only completion commit is resolved by `git log -1 --format=%H -- PHASE_9_REPORT.md`; its full remote-verified SHA is recorded on Issue #1 and in the completion response. No implementation changes followed the fresh-clone test.

## Finished functionality and files

- `local_demo.py`: one-command complete, disposable offline review demonstration. Uses frozen synthetic warehouse, event-crew and scanned PDFs; shows exact quotation/page/offset, a review-only hand-authored suggestion, scan abstention, reviewer decision with unchanged findings, external checkpoint with separately counted later event, verified export and the original historical LLM-error demo. Real model calls: **0**; explicit simulated extraction invocations: **1**. Temporary data is removed; existing local data is untouched.
- `webapp/static/js/lexicon.js`: actionable messages for worker CPU/memory/time/output limits, crashes and unsupported platforms; partial output is explicitly untrusted. Existing visual design preserved.
- `tools/fresh_clone_check.py`: reproducible committed-snapshot clone/venv/install/tests/demos/evaluation/actual loopback HTTP verification. Credential-related environment values are excluded and `.env` is not copied.
- `tests/test_local_demo.py`: meaningful end-to-end no-network, review-separation, suggestion, checkpoint and export assertions. All prior tests unchanged.
- `docs/OPERATING_GUIDE.md`, README and architecture: installation, controls, private data/export handling, backup/recovery, failures, quota limits, dependency licensing, scope and actual readiness. Historical reports/results remain immutable.

## Actual checks

| Check | Actual result |
|---|---|
| Working-tree full suite | **234/234 passed**, 35.713 s, no skips |
| Fresh-clone full suite | **234/234 passed**, 36.222 s, no skips |
| Offline Chrome workflow | **25/25**, Google Chrome 154.0.8037.57 |
| Offline Firefox workflow | **25/25**, Playwright Firefox 157.0 |
| Mocked live consent workflow | **10/10 per browser**, same browser versions, one mock each and zero actual calls |
| Frozen PDF suite | **19/19** outcomes unchanged; 9 extracted, 7 review, 3 rejected |
| PDF provenance | **25/25** evidence items mapped, **26/26** fragments verified, **10/10** invalid locations rejected |
| PDF statutory proposals | **0/19** released |
| Fresh-clone HTTP | Offline health/parser available; synthetic warehouse review and verified export passed |
| Fresh-clone tracked files | `git diff --exit-code` passed; no tracked files modified by running the app/tests |

The frozen PDF per-case summary is exactly equal to Phase 6C's verified output. All five phase gates are traced in `results/phase9/completion_audit.json` and the living plan. The original 43,115-byte stress-case containment is covered again by the full suites; its preserved standalone result remains CPU-limited/reaped at 4.018 s with no retained text/pages. No new accuracy/recall tuning occurred in this phase.

Commands executed with `.venv/bin/python` in the working checkout:

```sh
local_demo.py
demo.py
pdf_demo.py
-m unittest discover -v
-m unittest tests.test_local_demo -v
evaluate_pdfs.py --output-dir results/phase9/pdf-evaluation
-m browser_tests.run --output results/phase9/browser_offline.json
-m browser_tests.live --output results/phase9/browser_mocked_live.json
tools/release_check.py --output results/phase9/security_candidate.json
tools/release_check.py --output results/phase9/security_precommit.json
tools/fresh_clone_check.py --output-dir results/phase9/fresh-clone
```

The last command took **40.463 s** and created a fresh **local Git clone of the exact committed snapshot**, without hardlinks, plus a new venv. It installed only `requirements-pdf.txt` from PyPI (pypdf **6.21.4**) using Python **3.13.12**. It then ran the full suite, all three demos, offline comparison and real ephemeral-loopback server/sample/export checks. All **10 subprocess commands exited 0**. Dependency setup used internet; demos/evaluation used no provider/internet and no credentials. This was not a claim that Python 3.9 itself or every Linux distribution was tested. The disposable checkout was removed, with full command logs, versions and SHA retained under `results/phase9/fresh-clone/`.

## Security and release integrity

Read-only release scans passed before the candidate commit, covering candidate files, reachable Git blobs, known credential values and common secret/private-path patterns. No `.env`, local database, private contract, browser binary, cache, confidential assignment document or private conversation was added. PDFs remain the frozen synthetic fixtures. The final scan and historical-byte comparisons are retained under `results/phase9/`. The scan is not a complete penetration test or proof that arbitrary private text can be detected automatically.

Manual review checked default-offline configuration, absence of implicit credential loading/transmission, one-use consent binding, pre-transmission document identity, no retry/paid fallback, durable request reservations/stops, sanitized errors, worker termination/reaping, immutable human-review effects and untrusted-content suppression. Existing adversarial tests and both browser workflows cover these boundaries; no new confirmed blocker was found within the documented local-demo scope.

GitHub repository visibility was read as **public**; no change was made. Remote `main` remained **`e075a9087b8f4dbebee3fe74f2cb427c5bc3a3c0`**. Development commits are additive, with the submitted snapshot and all previous failed experiments preserved. No force-push, merge or automatic deployment.

## Remaining limitations and recommendation

- Linux PDF workers enforce resource limits but are not a filesystem/network/RCE sandbox; same-OS-account permissions remain. Do not call this hardened hostile-document production hosting.
- Local names are not authenticated identities. External receipts prove consistency only with the separately held prefix, not trusted timestamps or legal/factual truth. Disk/history growth and privileged OS tampering remain operational concerns.
- Real live integration availability, provider retention, model quality and actual billing have not been validated by these mocked checks. Earlier live benchmarking remains incomplete and model-mixed. No new live call was authorized or executed.
- Independent practitioner annotation/validation remains **unmet external evidence**. The prepared schema and synthetic tests do not supply it. No legally validated TDS accuracy, production reliability or model superiority is claimed.
- No OCR, multi-user service, autonomous tax action, public app deployment or selected repository open-source license. Optional browser tests are a focused regression suite, not full accessibility/native-PDF-render certification.

The five authorized phases are complete within these limits. Recommended next decision is an independent local review and, only with separate authorization, practitioner-labelled data and a small fixed-free-model live evaluation. Do not start another development phase or deployment automatically.
