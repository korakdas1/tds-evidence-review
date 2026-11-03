# Multi-phase autonomous development plan

Authorized scope: Phases 6C, 6D, 7A, 8A and 9, sequentially, on `feature/full-product` only. Start: `df101eaa98045a775e34288a3f00613f0448ccb2`, 175 tests. Submitted `main`: `e075a9087b8f4dbebee3fe74f2cb427c5bc3a3c0`. No live inference, paid API, public deployment, main changes, legal reinterpretation or historical-data edits.

## Acceptance matrix and evidence plan

| Phase | Required implementation and verification | State / evidence |
|---|---|---|
| 6C | Linux worker wall/CPU/memory limits; terminate/reap; bounded input/output; explicit failures; zero partial trust; original fixtures; contained 43 KB stress; responsive HTTP server; all original 175 tests | VERIFIED: 187/187 tests; 19/19 fixture outcomes; stress CPU-limited/reaped at 4.018 s; `PHASE_6C_REPORT.md` |
| 6D | Optional reviewer-held external history checkpoint or signed export; explain exact trust claim; committed Chrome/Firefox browser harness covering decisions, tampering, mobile, PDF warnings, accessibility basics; repeatable instructions | VERIFIED: 196/196 tests; Chrome/Firefox 25/25 checks each; `PHASE_6D_REPORT.md` |
| 7A | Offline default; explicit live choice + configured model + external-transmission notice + per-run confirmation; allowlist/spend/request/time limits; no paid fallback; existing evidence/review safeguards; distinct offline/simulated/live records; mocked E2E only | VERIFIED: 219/219 tests; mocked UI 10/10 per browser; offline UI 25/25 per browser; `PHASE_7A_REPORT.md` |
| 8A | Reproducible baseline/direct/hybrid comparison; agreement/incorrect confidence/abstention/provenance/unsupported interpretation/latency/token/cost accounting; preserve frozen data; versioned protocol and independent-practitioner input format; distinguish offline/simulated/historical/live | VERIFIED: 233/233 tests; frozen original/v2/v3 and simulated/historical comparisons; `PHASE_8A_REPORT.md` |
| 9 | Focused usability, security/errors, complete offline demo, fresh clone setup, architecture/operations/portfolio README, private-file audit, regression gates | VERIFIED: 234/234 current and fresh-clone tests; both browser workflows; `PHASE_9_REPORT.md` |

For each phase: implement focused changes; run relevant regressions, then all prior tests; preserve failed development logs; verify frozen artifacts; secret/file review; create `PHASE_<name>_REPORT.md`; commit/push only this branch; verify remote; update Issue #1; continue automatically. Reports record exact commands/counts and limitations. A green test suite alone is not proof of broad security or legal correctness.

## Completion audit

Before marking the durable goal complete, verify all five reports and their implementation gates against current files, executed commands, browser behavior and remote commits. Confirm previous tests pass, failed parser output never becomes trusted evidence, mocked live workflows require explicit confirmation, decisions remain separate from findings, evaluation is honestly labelled, setup works from a fresh clone, and the public repository contains no secrets/private data. Independent practitioner validation and actual live-model performance remain unmet external evidence unless separately provided/authorized; neither is required to fabricate for these phases.

## Progress / decision log

- Start: read supplied multi-phase objective and current Phase 6 audit; clean worktree on requested start SHA; fetched development/main refs. Active goal already exists in conversation state.
- 6C design: retain the parser/provenance core, add a resource-isolated Python worker used by document reviews (server, PDF demo and PDF evaluation). Keep low-level parser callable for trusted unit diagnostics; no in-process fallback from the public review path. Resource isolation is not a full security sandbox.

- 6C verified: original 175 + 12 new tests pass; frozen outcomes unchanged; 43,115-byte stress returns CPU_LIMIT, no spans, reaped. Secret/file review passed. Next: commit/push verified 6C, then external checkpoint and browser harness work in 6D.

- 6C committed/pushed as `d64a7d2803f88ca74979d4bc2539bc56c9338875`; remote verified and Issue #1 updated.
- 6D verified: 9 new checkpoint tests, all 196 tests pass; Chrome 154 and Firefox 157 each pass 25 browser checks. First development failures preserved; no frontend changes. Next: controlled live mode with mocked inference only.

- 6D committed/pushed as `a75668983069975ceff9408dbd140e0e7fdedd9f`; remote verified and Issue #1 updated.
- 7A verified with zero real requests: 219/219 tests; both browser workflows pass. Default remains offline, one-use consent + durable free-only request limits + inference deadline worker added. Incorrect mock quote caused an expected provenance rejection in the first test run; logs preserved. Next: evaluation infrastructure.

- 7A committed/pushed as `a84d71d2b7ca3a72b37b04adb163a0bdf3f026df`; remote verified and Issue #1 updated.
- 8A verified: versioned offline comparison/metric and practitioner schema infrastructure; original/v2/v3 baseline 16/16, 12/12, 9/12; explicit hand-authored hybrid replay 8/12; historical partial/model-mixed runs preserved. 233/233 tests. No actual live inference or independent practitioner validation. Next: finishing and fresh-clone audit.

- 8A committed/pushed as `cb56e2c0e0a3d27e9074165333949857ac3c70c5`; remote verified and Issue #1 updated.
- 9 implementation candidate `11ba8fff30665894aefa76d2f26700888b169782` passed a fresh clone/venv install, 234/234 tests, all demos, offline evaluation and actual loopback review/export. Current browser gates: 25/25 offline + 10/10 mocked live per Chrome/Firefox. Frozen PDF outcomes unchanged.
- Completion audit: all five reports and implementation gates verified in `results/phase9/completion_audit.json`; original historical bytes preserved. Final documentation/evidence commit and remote/Issue delivery follow the release scan. Independent practitioner validation and actual live-provider measurements remain explicitly external, not fabricated completion claims.
