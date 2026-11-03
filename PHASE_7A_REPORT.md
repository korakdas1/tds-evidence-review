# Phase 7A — controlled live extraction, verified with mocks only

Status: VERIFIED integration, **zero real inference calls**. Actual provider availability and model quality are NOT_RUN. Base/fallback: `a75668983069975ceff9408dbd140e0e7fdedd9f`. Retrieve this phase's SHA with `git log -1 --format=%H -- PHASE_7A_REPORT.md`; full remote-verified SHA is posted on Issue #1.

## Implemented

`src/live_provider.py`, `webapp/live.py` add explicit free-only fixed-model configuration, model allowlist, zero-dollar max price, one-request/no fallback/no retry transport, bounded input/response, total wall-clock inference worker timeout with kill/reap, sanitized errors, persistent request reservations and failure stops. Default app remains offline. Startup requires `--enable-live`, explicit environment configuration and nonempty key; `.env` is never auto-loaded. The default model method remains baseline even when enabled.

The new-review interface displays the configured model and transmission warning, uploads locally, then requests separate per-run confirmation. An expiring single-use token binds to that request's documents and manual metadata. Cancel sends nothing. The document adapter checks extracted-document hash and reliable status before transmission, preventing a changed file from inheriting consent. Corrections rerun offline, never silently repeating a live request. No UI action approves tax treatment; proposals remain withheld and unfamiliar interpretations remain review-only. Execution records distinguish OFFLINE/SIMULATED/LIVE and include returned model, token usage, measured latency, cost if reported, and errors. Existing extraction prompts, tax mappings and benchmark data remain unchanged.

Changed `webapp/server.py`, `service.py` and focused frontend files; added `tests/test_live_app.py`, `browser_tests/live.py`, `docs/LIVE_MODE.md`. Updated README/architecture/plan. No visual redesign or additional runtime dependency.

## Actual verification

- `.venv/bin/python -m unittest tests.test_live_app -v`: first 19 tests had one failure because the hand-authored mock's supply quotation did not match the frozen PDF. The validator correctly rejected it. Corrected the mock quote, not the fixture/validator; 19/19 then passed. Both logs retained.
- `.venv/bin/python -m unittest discover -v`: initial 215-test run retained that same mock-fixture failure; after correction and four added safety cases, final **219/219**, **35.745 s**, no skips. All preceding 196 tests unchanged.
- `.venv/bin/python -m browser_tests.live --output results/phase7a/browser_live_first.json`: Chrome **154.0.8037.57, 10/10**; Firefox **157.0, 10/10**. Per browser: offline default, displayed model, no call on selection/preparation/cancel, second dialog confirmation, exactly one mock invocation, SIMULATED record, zero real calls, withheld proposal, provenance visible, no external browser traffic or uncaught errors.
- `.venv/bin/python -m browser_tests.run --output results/phase7a/browser_offline_regression.json`: both browsers **25/25** existing workflow checks.
- `.venv/bin/python tools/release_check.py --output results/phase7a/security.json`; `git diff --check`: release evidence retained alongside the results.

New unit cases cover defaults, public config redaction, absent/changed/expired/replayed consent, cancellation, exact quotes, unfamiliar interpretation, fabricated quotes, malformed JSON, persistent HTTP429 stop/no retry, concurrent budget reservations across restart, pacing, append-only ledger, model/cost mismatch, oversized input, document identity/reliability before transmission, host/CSRF guards, invalid config, offline corrections, worker success/deadline/reaping, HTTP envelope/redaction, refusal and truncated output. HTTP and provider boundaries are mocked; the only spawned inference-worker functions during tests return synthetic responses or deliberately sleep.

## Limitations and security

The sole test model ID is `synthetic/fixed:free`, an invented test identifier, **not an executed real model**. Token usage (10+20=30) and zero cost in mock responses are synthetic fixtures; not measurements of a provider. Timed-out attempts count against the durable budget; they cannot prove whether transmission reached the provider. Crash after sending but before storing a report may leave an attempt reservation without a completed run. Missing provider cost remains null. Max-price/free selection are safeguards, not independent billing verification; keep provider key spending controls too.

No paid-model support, router switching, live availability claim, legal accuracy claim, independent practitioner validation, deployment or multi-user authentication. Provider data retention remains external. Local OS owners can replace databases or alter limits; request counters are not tamper-proof billing records. External transmission is only appropriate with authorization for that content.

Security review checks changed files, all candidate files/reachable history, exact known credentials, ignored `.env`, submitted main, protected tests/data/prompts/results and unrelated private-file patterns. Results contain only synthetic data. No live experiments or main/visibility changes. All original historical artifacts remain intact.

Next authorized phase: 8A reproducible evaluation infrastructure with explicit offline/simulated/historical/live provenance and independent-practitioner input format, without inventing independent labels or live measurements.
