# Multi-phase autonomous development plan

Authorized scope: Phases 6C, 6D, 7A, 8A and 9, sequentially, on `feature/full-product` only. Start: `df101eaa98045a775e34288a3f00613f0448ccb2`, 175 tests. Submitted `main`: `e075a9087b8f4dbebee3fe74f2cb427c5bc3a3c0`. No live inference, paid API, public deployment, main changes, legal reinterpretation or historical-data edits.

## Acceptance matrix and evidence plan

| Phase | Required implementation and verification | State / evidence |
|---|---|---|
| 6C | Linux worker wall/CPU/memory limits; terminate/reap; bounded input/output; explicit failures; zero partial trust; original fixtures; contained 43 KB stress; responsive HTTP server; all original 175 tests | VERIFIED: 187/187 tests; 19/19 fixture outcomes; stress CPU-limited/reaped at 4.018 s; `PHASE_6C_REPORT.md` |
| 6D | Optional reviewer-held external history checkpoint or signed export; explain exact trust claim; committed Chrome/Firefox browser harness covering decisions, tampering, mobile, PDF warnings, accessibility basics; repeatable instructions | Pending |
| 7A | Offline default; explicit live choice + configured model + external-transmission notice + per-run confirmation; allowlist/spend/request/time limits; no paid fallback; existing evidence/review safeguards; distinct offline/simulated/live records; mocked E2E only | Pending |
| 8A | Reproducible baseline/direct/hybrid comparison; agreement/incorrect confidence/abstention/provenance/unsupported interpretation/latency/token/cost accounting; preserve frozen data; versioned protocol and independent-practitioner input format; distinguish offline/simulated/historical/live | Pending |
| 9 | Focused usability, security/errors, complete offline demo, fresh clone setup, architecture/operations/portfolio README, private-file audit, regression gates | Pending |

For each phase: implement focused changes; run relevant regressions, then all prior tests; preserve failed development logs; verify frozen artifacts; secret/file review; create `PHASE_<name>_REPORT.md`; commit/push only this branch; verify remote; update Issue #1; continue automatically. Reports record exact commands/counts and limitations. A green test suite alone is not proof of broad security or legal correctness.

## Completion audit

Before marking the durable goal complete, verify all five reports and their implementation gates against current files, executed commands, browser behavior and remote commits. Confirm previous tests pass, failed parser output never becomes trusted evidence, mocked live workflows require explicit confirmation, decisions remain separate from findings, evaluation is honestly labelled, setup works from a fresh clone, and the public repository contains no secrets/private data. Independent practitioner validation and actual live-model performance remain unmet external evidence unless separately provided/authorized; neither is required to fabricate for these phases.

## Progress / decision log

- Start: read supplied multi-phase objective and current Phase 6 audit; clean worktree on requested start SHA; fetched development/main refs. Active goal already exists in conversation state.
- 6C design: retain the parser/provenance core, add a resource-isolated Python worker used by document reviews (server, PDF demo and PDF evaluation). Keep low-level parser callable for trusted unit diagnostics; no in-process fallback from the public review path. Resource isolation is not a full security sandbox.

- 6C verified: original 175 + 12 new tests pass; frozen outcomes unchanged; 43,115-byte stress returns CPU_LIMIT, no spans, reaped. Secret/file review passed. Next: commit/push verified 6C, then external checkpoint and browser harness work in 6D.
