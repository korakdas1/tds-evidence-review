# Phase 6C — isolated PDF parser

**Gate: PASSED on Linux.** The starting 175 tests and 12 new worker tests pass (**187/187**, no skips). The previous 43,115-byte stress recipe is stopped by the runtime worker's CPU limit and reaped, with no retained source text or page spans. No live model calls occurred. This is resource containment, not a complete security sandbox or production-readiness claim.

Start/fallback: `df101eaa98045a775e34288a3f00613f0448ccb2`. Work is only on `feature/full-product`; submitted `main` stays `e075a9087b8f4dbebee3fe74f2cb427c5bc3a3c0`. All prior reports, tests, fixtures, manifests, datasets and prompts remain unchanged.

## Implementation

`src/pdf_worker.py` launches a fresh Python process through the standard-library spawn context. Before parsing it clears inherited environment variables, disables core dumps, suppresses raw parser diagnostics and applies Linux limits:

| Resource | Default |
|---|---:|
| Parent wall deadline, including startup | 8 seconds |
| Worker CPU soft/hard budget | 4 / 5 seconds |
| Worker address space | 256 MiB |
| Parent regular-file input read | 5 MiB |
| Worker serialized result / output file | 16 MiB |

The parent snapshots bounded bytes in a private temporary directory, waits only to the wall deadline, kills the worker/session when needed, reaps it and removes temporary files. A complete bounded JSON result is accepted only after exit zero. File identity, page schema, text hashes and normalization mapping are rechecked. No pickle is accepted as a worker result. Spawn's trusted Python startup arguments contain only local paths, configured limits and a trusted parser function, not document-defined executable instructions.

Explicit failures include CPU limit, memory limit, wall timeout, output limit, parser exception, crash, invalid result, startup failure and unsupported platform. Failed workers contribute no pages, text or coordinates. Existing document-review gates then abstain and keep statutory proposals withheld. Internal MemoryError exceptions now propagate to the worker boundary rather than masquerading as partial extraction success.

`src/document_review.py` uses this wrapper by default. Consequently the server, PDF demo and PDF evaluator share the isolated path. The low-level `src/pdf_ingestion.read_pdf()` is retained for trusted parser diagnostics and existing unit tests; it is not the public untrusted-document entry point. There is no silent in-process fallback. `evaluate_pdfs.py` now fingerprints the worker implementation too.

## Executed evidence

- Original suite after integration: **175/175**, 21.284 s (`development_existing_tests.txt`).
- New worker suite: **12/12**, 9.175 s (`worker_tests_first.txt`).
- Final complete suite: **187/187**, 31.590 s (`final_tests.txt`).
- Frozen PDF per-case outcomes are identical to the prior independent audit: **19/19** expected outcomes (9 extracted, 7 requiring document review, 3 rejected); **25/25** canonical evidence items mapped; **26/26** fragments verified; **10/10** invalid location probes rejected; **0/19** statutory proposals released.
- Default PDF demo executed successfully with the same factual result and exact page offsets; output is in `results/phase6c/demo.txt`.

The tests exercise all frozen fixtures through both parser and worker, CPU/memory exhaustion, a crashed parser, sanitized exceptions, output overflow, special/oversized files, invalid configuration, inconsistent source output and a deliberately written result followed by a stalled process. The stalled result is discarded. `os.waitpid` verifies that stopped children have already been reaped. A real loopback HTTP test requests health while a parser worker is stalled: health responds within 0.8 seconds, the analysis eventually returns an abstaining review, and no worker remains active. No provider is contacted.

Actual stress result (`stress_containment.json`):

- Input: **43,115 bytes**, SHA-256 `7cd1eb895b25a11395d9f343603eff3cc531699d67e4b6a820c6c57ceb7e80e7`.
- Worker status: **PDF_WORKER_CPU_LIMIT**, exit code **71**.
- Elapsed: **4.017970 seconds**; **reaped = true**.
- Retained text characters: **0**; retained pages: **0**.

The synthetic recipe reuses the unchanged prior audit generator. No historical PDF or result was edited. A first PDF evaluation is preserved alongside `pdf-evaluation-final`; the second records the worker's source hash after adding it to evaluator implementation metadata. Per-case metrics did not change. No development test failure occurred in this phase.

## Reproduction

```bash
.venv/bin/python -m unittest discover -v
.venv/bin/python -m unittest tests.test_pdf_worker -v
.venv/bin/python -m tests.phase6c_probe --output results/local/phase6c-stress-new.json
.venv/bin/python evaluate_pdfs.py --output-dir results/local/phase6c-pdf-new
.venv/bin/python pdf_demo.py
.venv/bin/python tools/release_check.py --output results/local/release-check-new.json
```

Create the local output parent when needed. Recorded commands used `results/phase6c/` destinations; use new paths for repeat runs. Tests with local HTTP servers require loopback socket permission. Python 3.13.12 and pypdf 6.21.4 were used. Document review requires Linux; script callers should use a guarded `if __name__ == '__main__'` entry point for spawn. The JSON-only workflow remains unchanged.

## Security and limits

The release secret/file check is `results/phase6c/security_audit.json`. It scans known credential values without printing them, token patterns, tracked/unignored files and reachable history, and verifies protected artifacts and `main`. New content contains only code, synthetic test evidence and documentation; no source PDFs, local databases or private inputs were added. Environment files remain excluded.

The worker retains the same OS account's filesystem and network permissions. Clearing its environment is not an access-control sandbox. It does not execute PDF actions, OCR commands or provider calls, but an interpreter/parser compromise is beyond this resource boundary. The parent validates a bounded extraction envelope, not independently attested visual meaning. File/image reading order limitations, mandatory review, unsigned local history and upload/history storage limits remain. Extremely constrained hosts may reject otherwise valid documents under the memory cap; the result must remain an explicit review failure. Arbitrary third-party PDF safety and public hosting are not certified.

## Delivery and next phase

Added worker, 12 tests, stress-recording command, reusable read-only release checker, living multi-phase plan and evidence. Updated the adapter, MemoryError handling, evaluator fingerprinting, README and architecture documentation. No legal mapping changed.

Delivery SHA is the commit introducing this report, recorded in Issue #1 and recoverable with `git log -1 --format=%H -- PHASE_6C_REPORT.md`. After verified commit/push, proceed to the already-authorized **Phase 6D**: reviewer-controlled external checkpoints and repeatable browser regression tests. Live-model calls remain separately unauthorized.
