# Independent Phase 6 audit

## Verdict: BLOCKED for arbitrary untrusted PDF ingestion

The repaired implementation is suitable for its local, synthetic demonstration on Linux. **Phase 6 does not receive an unconditional READY designation.** A 43,115-byte PDF within the file/page/stream limits exhausted the audit worker's CPU budget. Production ingestion still runs inside the server and has neither that worker's CPU deadline nor its process memory cap. Isolated parsing is a release prerequisite for arbitrary untrusted PDFs. No large sandbox or Phase 7 feature was implemented in this audit.

Audited starting commit: `b63e4f5d9c543a695c3cbdaa51dfaeda1dfbf55d` on `feature/full-product`. Both remote heads were independently verified; submitted `main` remains `e075a9087b8f4dbebee3fe74f2cb427c5bc3a3c0`. The repository was already **public**; its visibility was not changed. The local web application is not a public deployment.

`PHASE_6_REPORT.md` was read but left unchanged as historical evidence. Its 155-test result was reproduced before fixes, then supplemented with adversarial probes. No live LLM calls, paid APIs, tax interpretations, rules, benchmark labels or historical results were changed.

## Confirmed findings and fixes

Severity is relative to this single-user, loopback application. Filesystem/database attacks below require write access to its local data directory; they are not unauthenticated remote exploits.

| Finding | Severity | Reproduction and result | Resolution |
|---|---|---|---|
| Run metadata and document/method identity were outside the report anchor | **High integrity** | Change `runs.metadata_json` credit date to `2025-01-01` without changing the report or history. The API said `VERIFIED` while displaying the old 2025-Act result. Substituting a registered document or method was likewise not covered by the anchor. | Each new analysis event anchors the complete run context: IDs, sequence/time, document hashes, manual metadata, method, supplied extraction and report hash. API/detail/list/export reject mismatched context; reruns cannot silently reuse untrusted context. |
| Upload/repair paths followed symlinks | **Medium, local file write** | A `<digest>` directory link redirected a new upload outside storage. A predictable `.restore` link caused re-upload to truncate an unrelated sentinel file. | No-follow directory descriptors and exclusive random temporary files; atomic replacement never follows the destination entry. Unsafe internal directories/database paths are rejected. Tests verify sentinel bytes remain unchanged. |
| Quota check did not serialize across Store instances | **Medium** | Code inspection showed the quota SELECT preceded the write transaction; independent instances could both observe free capacity. | `BEGIN IMMEDIATE` covers duplicate/quota checks and registration. Eight independent Store connections concurrently attempt a one-document quota: one succeeds, seven receive quota errors; a duplicate remains free. |
| Case/run and history anchor committed separately | **Medium reliability** | Inject an event-write failure: one case row remained but the case list hid it. A run could similarly be committed without its anchor. | Analyze first, then commit new case, creation event, run and analysis event in one transaction. Fault-injection tests roll back all three tables; a failed rerun leaves the previous run trusted. Uploads remain reusable separate objects. |
| Malformed persisted JSON broke all case-list retrieval | **Medium reliability** | Replace `report_json` with `{broken`; the list raised `JSONDecodeError`. | Strict decoding marks invalid objects untrusted. Malformed report/metadata/extraction/event payloads suppress findings and export only under forensic warnings rather than breaking the list. This is not recovery for arbitrary SQLite/schema corruption. |
| A forged case title still appeared in ordinary API/list headers | **Medium integrity presentation** | Phase 6 detected an edited title but still returned `Approved for withholding` as the case title. | Untrusted case labels are neutralized in detail/list/top-level export. The original is retained only in explicitly forensic export content. Untrusted case status is also explicitly failed. |
| PDF bytes could change between verification and serving; damaged files were read without a size cap | **Medium reliability/integrity** | Code read `path.read_bytes()` after a separate hash check. Stored files could also grow beyond the upload limit. | One bounded no-follow read returns the exact verified bytes used by HTTP. A snapshot-race regression confirms served bytes retain the verified hash; a 30 MiB damaged file is rejected before content read. |
| Short/ambiguous HTTP bodies and malformed action types | **Low** | A short body could be processed after EOF despite a larger Content-Length; duplicate lengths/Transfer-Encoding were not explicitly refused. `kind: []` caused a TypeError. | Reject incomplete bodies, duplicate lengths and transfer encodings; reject bad host/CSRF headers before reading bodies; return 408 on read timeout and 400 for non-string actions. Ephemeral port 0 now uses its actual bound port. |
| README contradicted current visibility/frontend behavior | **Low documentation** | It said “No frontend” and “repository remains private” below an otherwise current web-app introduction. GitHub reports public and the browser app is implemented. | Corrected current statements, test count, parser risk and legacy-record behavior; historical reports retained. |

The new storage protections use POSIX directory-descriptor/no-follow operations. The web application now explicitly refuses unsupported platforms rather than silently falling back to unsafe path operations. Linux was tested; native Windows web storage is unsupported. JSON/PDF CLI behavior is unchanged. This portability restriction is documented rather than hidden.

## Existing local records and trust boundaries

Old local runs have no full context anchor. They are preserved byte-for-byte and remain available through forensic exports, but they **cannot be retroactively certified** from the information stored. Create a fresh case using verified originals and manually checked metadata. The audit does not rewrite old chains or backfill hashes from potentially altered rows. A regression constructs a legacy-style anchor and verifies this behavior.

An intact unsigned history is still not a signature. A local attacker who recomputes context/report/history hashes can forge a consistent database. Tail truncation requires an external chain-head record to detect. No new authenticity claim is made.

Reports with compromised findings remain quarantined in exports, as in the existing forensic design, with `INTEGRITY_FAILED`, an empty trusted-run list for wholly compromised cases, and an explicit UNTRUSTED warning. They are not erased. Recorded history remains visible as diagnostic history, not a replacement finding. Every reviewer action still has zero effect on automated facts, statutory proposals or withholding authorization.

## Independent results

| Check | Actual result |
|---|---:|
| Original suite, before changes, with loopback access | **155/155 passed**, no skips |
| Final suite | **175/175 passed**, no skips (155 unchanged + 20 new) |
| Original dependency-free suite, site packages disabled | **87/87 passed** |
| Original / v2 / v3 factual-status agreement | **16/16; 12/12; 9/12** |
| Original evidence-removed false-confident decisions | **0/4** |
| Frozen PDF expected outcomes | **19/19**, identical per-case outcomes to Phase 6 |
| PDF canonical evidence items mapped | **25/25** |
| Original-page source fragments verified | **26/26** |
| Invalid location probes rejected | **10/10** |
| PDF statutory proposals released | **0/19** |
| Historical protected files compared with starting commit | **275 unchanged** |
| Live LLM/API experiments | **0** |

All original test files remain unchanged. The 23 frozen Act-selection regression cases and 13 malformed-configuration variants ran as part of the suite. The code/configuration were inspected: the earlier valid date selects a configured period; missing or malformed dates require review; the transition matches the existing cited rule. The config and legal rules were not edited. This checks implementation consistency, not legal validation.

Results are under `results/phase6_codex_audit/`. The first sandboxed suite had three `PermissionError` failures from blocked local sockets; permitting only the required local test server execution reproduced 155/155. This was an environment restriction, not a product defect.

Development logs are preserved: one new fault-injection test initially indexed the wrong argument (test-harness mistake, corrected); an intermediate compatibility test exposed a redundant failed-check label; the first full post-fix run exposed the ephemeral-port guard regression (421 instead of the expected generic 500). Those were corrected, and the subsequent 172-test suite passed. Three further focused regressions brought the final passing count to 175. No failures or earlier experiments were overwritten.

## PDF resource investigation and remaining blocker

`tests/phase6_resource_probe.py` is an **audit-only** harness. It parses each synthetic stress input in a separate child process with 256 MiB address-space and 5/6-second CPU limits plus a 12-second outer timeout. These protections are **not present in the application**. Generated stress PDFs remain temporary and are not committed.

Corrected measurements from `pdf_resources_corrected.json`:

| Probe | Input | Result | Peak RSS / time |
|---|---:|---|---|
| Existing 20-page decompression bomb | 1,444,797 bytes | All 20 pages flagged `DECOMPRESSION_LIMIT` | 53,220 KiB; 0.336 s parse |
| Two pages of dense drawing operators | 3,841,102 bytes | Two pages require manual review; no selectable text | 171,712 KiB; 3.436 s parse |
| 20 compressed pages of dense drawing operators | **43,115 bytes** | Audit child killed at its hard CPU budget; exit **-9** | 6.021 s wall; no completed report |

The first measurement file used `getrusage` high-water values contaminated by the parent process's fork-time memory peak. It is preserved but **not used as parser-memory evidence**. The corrected harness reads Linux `/proc/self/status` `VmHWM` after exec. The killed probe has no completed peak-memory measurement; none is invented.

Per-stream decompression caps and the one-analysis semaphore help but do not bound total work or process memory. The semaphore wait timeout does not interrupt the parser already occupying it; HTTP body timeouts likewise do not cap analysis CPU time. The library can allocate for operators, objects, fonts and page traversal before application-level checks. Older unpinned pypdf versions lacking `apply_configuration` also retain their defaults; install the pinned requirements. A universal process-memory bound was not established.

**Required next reliability work:** a small isolated parser worker with enforced wall/CPU/memory limits, termination on deadline, a bounded result channel, and explicit timeout/resource-failure results. Keep it separate from the HTTP/SQLite process. This recommendation does not begin Phase 7 and no large sandbox was implemented here. Until then, use only the known synthetic/local demonstration inputs; arbitrary public PDFs can also be hostile.

## Browser and frontend verification

A fresh scratch database at `/tmp/tresata-codex-phase6-browser` was used through the connected Chrome browser, not an existing user database. The actual workflow:

1. Create the warehouse synthetic sample from the dashboard.
2. Navigate the supervision quotation, page 1 characters 371–426; inspect the original PDF visibly rendered beside the evidence.
3. Record “Matches the PDF” as **Synthetic Codex Auditor**; progress changes from 0/6 to 1/6 while the factual status remains unchanged and the statutory proposal stays withheld.
4. Correct credit date to `2026-03-31` and rerun. The UI shows Act 1961, the earlier trigger date, run 2 and zero model calls.
5. History retains all four entries, including the original run's quotation decision; the new run has no inherited decisions.
6. Click Export record; independently retrieve that local export and verify its checksum, two trusted runs, four events and withheld proposals.
7. Alter only the scratch run's stored metadata, reload, and verify the browser withholds finding/evidence/page text and displays a context-integrity failure.

`browser_workflow.json` records these observations. One stale accessibility node occurred after quotation navigation; refreshing the browser tree resolved it. It was an automation error, not an app defect. No CSS, layouts or visual design changed. Only labels/status recognition for the added integrity checks changed. No observed UI action implies legal approval. This audit did not repeat Firefox, Safari, screen-reader or mobile testing and does not inherit those claims from the previous report.

## Security review and operational limits

The final secret/file audit is recorded in `security_audit.json`. It checks staged/candidate files, reachable history, exact configured credential values without printing them, common token patterns, private-file inventory, historical preservation and ignored `.env`/`local_data`. All new report data is synthetic. An unrelated empty local `.aws` file was discovered; it was not read as credentials, changed or committed. `.gitignore` now excludes that credential location whether it is a file or directory.

Storage repair and new-upload tests cover fixed symlinks, directory links, database links, duplicate uploads, multiple Store connections, oversized damaged copies and injected write failures. No-follow descriptors protect internal upload traversal; this is not isolation from a malicious owner of the data directory. A hard crash after file replacement but before registration can still leave an orphan; registered-upload quota is not a quota for SQLite/history or arbitrary files placed by the OS user. Those bounds remain operational limitations. Irrecoverable SQLite corruption may require restoring a backup.

Host/CSRF/preflight, traversal, strict JSON, body limits, timeouts, generic client errors and concurrent chain-appending tests pass. The application remains loopback-only with self-declared reviewers. There is no claim of authenticated multi-user operation, tamper-proof storage or safe public hosting.

## Reproduction commands executed

```bash
git fetch origin feature/full-product main
.venv/bin/python -m unittest discover -v
.venv/bin/python -m unittest tests.test_phase6_audit -v
.venv/bin/python -S -m unittest tests.test_core tests.test_llm tests.test_reliability tests.test_demo tests.test_phase3 -v
.venv/bin/python main.py --input tresata_adversarial_cases.json --mode baseline --output results/phase6_codex_audit/original.json
.venv/bin/python main.py --input tresata_challenge_v2.json --mode baseline --output results/phase6_codex_audit/v2.json
.venv/bin/python main.py --input tresata_challenge_v3.json --mode baseline --output results/phase6_codex_audit/v3.json
.venv/bin/python evaluate_pdfs.py --output-dir results/phase6_codex_audit/pdf-evaluation
.venv/bin/python -m tests.phase6_resource_probe --output results/phase6_codex_audit/pdf_resources_corrected.json
.venv/bin/python demo.py
.venv/bin/python pdf_demo.py
.venv/bin/python review_app.py --port 8877 --data-dir /tmp/tresata-codex-phase6-browser
```

Outputs already exist; reproduce into NEW `results/local/` paths. The resource harness is Linux/POSIX-only and intentionally tests failure under external limits. No historical output files are regenerated.

## Delivery

Changed implementation: `webapp/store.py`, `webapp/service.py`, `webapp/server.py`; small diagnostic-label changes in `webapp/static/js/views/workspace.js`. Added `tests/test_phase6_audit.py`, audit-only `tests/phase6_resource_probe.py`, this report and audit results. Updated README, architecture documentation and credential-path ignore coverage. All legal/PDF core code and original tests remain unchanged.

The delivery commit is the commit introducing this report; its exact SHA is recorded in Issue #1 and the final handoff. Obtain it without a self-referential hash:

```bash
git log -1 --format=%H -- PHASE_6_CODEX_AUDIT.md
```

Only `feature/full-product` is committed/pushed after passing tests and secret/file checks. `main` and the submission commit remain unchanged. No force push, merge, visibility change or Phase 7 work is authorized or performed.
