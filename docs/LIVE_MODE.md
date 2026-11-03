# Explicit, free-only live extraction (Phase 7A)

The default app is fully offline. Merely having an API key or `.env` file does not enable inference. Phase 7A was developed and verified with mocks only; **no real model request was made**. Historical model experiments remain separate artifacts, not evidence of this integration's live availability or quality.

Only an operator who has permission to transmit the particular contract and transaction details should enable this mode. Choose an actually available fixed free model from OpenRouter's catalog; this example is a placeholder, not a recommendation or verified model listing:

```sh
# Supply OPENROUTER_API_KEY securely in the process environment. Never paste it in chat or commit it.
export TDS_LIVE_MODEL='provider/model:free'
export TDS_LIVE_ALLOWED_MODELS='provider/model:free'
export TDS_LIVE_MAX_REQUESTS=4
export TDS_LIVE_MAX_SPEND_USD=0
export TDS_LIVE_TIMEOUT_SECONDS=45
python review_app.py --enable-live
```

No environment file is sourced or auto-loaded. Without the startup flag, these values are ignored. Invalid configuration fails startup without contacting a provider. The default method remains **Offline rule checks**, even when enabled. On a new review, deliberately select **External AI extraction**, read the configured model and warning, and submit. Uploads stay local while a second per-run dialog asks permission. Cancel sends nothing. Confirmation is single-use, expires after five minutes and is bound to that exact request's metadata and document hashes. A changed request needs fresh confirmation. Corrections/re-runs are offline; create a new explicitly confirmed live review to transmit again.

## What is sent and stored

One extraction request contains extracted contract text and manual transaction fields (including invoice description, payer/vendor types/residency and dates). The invoice PDF bytes, original contract PDF bytes, reviewer names and local filesystem paths are not sent. The warning must be read in light of the contents: manual fields can still contain sensitive information. OpenRouter and its selected upstream provider receive the text; this application cannot guarantee their retention policies. No automatic/background transmission occurs.

Before sending, the client requires a reliable extracted document matching the consented hash. The existing factual/provenance validators process the response; unfamiliar evidence remains review-only, bad quotes are rejected, and PDF proposals remain withheld. The report, view and append-only history include `LIVE` or `SIMULATED`, configured/returned model, consent binding digest, request reservation, latency, token usage if supplied, pipeline errors and reported provider cost if present. Missing cost is `null`, not invented as zero. Mock token/cost values are labelled simulated. Provider bodies/headers are excluded from sanitized errors. Raw model content is stored privately as part of the ordinary review report, not committed to Git.

`model_network_calls` counts attempted external calls; it cannot prove whether a timed-out worker reached the provider. The persistent request ledger reserves a call before starting transport, so crashes/timeouts/partial failures consume the budget rather than silently freeing it. A crash after sending but before committing the case can leave a reservation without a completed run; do not infer that no data was sent. No request is retried automatically.

## Limits and stops

- One fixed `:free` model, explicitly allowlisted. Routers such as `openrouter/free`, paid models and fallback model arrays are disabled.
- Zero-dollar-only limit. Requests also set provider prompt/completion max prices to zero, require parameter support and disable provider fallbacks. No automatic paid fallback. A nonzero/invalid reported cost or unexpected model stops further requests and rejects the response; this is not a substitute for provider-side key spending controls.
- 1–32 total request reservations per local database; count survives restart and is serialized in SQLite. Default minimum interval 15 seconds. The counter is local, not a provider billing ledger or defence against the OS owner replacing the database/changing configuration.
- 1–60 seconds total inference-worker wall time (default 45), enforced by kill/reap, including slow response reads; no redirects or inherited HTTP proxy configuration; fixed HTTPS endpoint; 100,000-byte serialized input limit and 1 MiB response/IPC limit; 1,400 requested output tokens.
- Any transport/provider safety failure (including HTTP 429, refusal, unexpected model or nonzero cost) persists a stop in the local database. No automatic retry or reset UI. Diagnose it before deliberately starting a separately configured review workspace; preserve the failed record. Malformed extraction JSON is recorded as an extraction error; it never becomes a successful finding.

Free availability, provider support and pricing can change. The fixed-model and price restrictions may yield an error instead of a response. Check [OpenRouter's free-variant documentation](https://openrouter.ai/docs/guides/routing/model-variants/free) and [provider routing parameters](https://openrouter.ai/docs/guides/routing/provider-selection) before any separately authorized real experiment. No paid-model support is implemented.

## Reproduce the offline verification

```sh
python -m unittest tests.test_live_app -v
python -m unittest discover -v
# Optional installed browsers; uses an injected mock provider, never a real API.
python -m browser_tests.live --output results/local/live-ui-mocked.json
python -m browser_tests.run --output results/local/offline-ui-regression.json
```

The mock-only constructor seam is Python test code, never an HTTP request field. The UI labels mock execution `SIMULATED`; neither the report nor the tests claim real-model accuracy, live availability, independent validation or legal approval.
