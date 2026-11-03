# Optional externally held history checkpoint

The local database is unsigned. Its append-only triggers and hash chain detect ordinary edits, but someone controlling the file can remove the triggers and rewrite the entire chain. An independently held checkpoint adds a comparison against a history prefix outside that database.

After reviewing a case, copy its ID from the workspace URL and run:

```sh
python review_checkpoint.py create --data-dir local_data --case CASE_ID --output /reviewer-controlled-folder/case-checkpoint.json
python review_checkpoint.py verify --data-dir local_data --checkpoint /reviewer-controlled-folder/case-checkpoint.json
```

Use an existing writable folder outside the application's data directory. Creation refuses an existing output and writes mode 0600. Keep an independent copy under the reviewer's control, for example offline media. A file elsewhere on the same compromised computer is not independent protection. No credential or signing infrastructure is added.

Verification opens the existing SQLite database read-only in one consistent snapshot; it does not initialize, repair, migrate or change it. It checks all current reports, their context anchors, chain and document hashes, then compares the held event-prefix hash and report/context digests. Missing/damaged files fail verification; a receipt is never issued for an unverified run. Appended events are counted separately, not externally attested. CLI exit 0 means matching; exit 1 is an explicit failure. Errors omit SQL, document contents and private paths.

A matching receipt establishes consistency with **that particular held copy**, assuming SHA-256 collision resistance and an uncompromised verifier. It does not establish who authored the events, a trusted timestamp, factual truth, legal correctness, or that later events are authentic. Deletions after the checkpoint can go undetected. Replacing both the database and the held receipt defeats the check. The receipt's own checksum is for accidental corruption, not a signature. Reviewer decisions still do not alter findings or release statutory proposals.

Receipts contain identifiers, hashes, event counts and an untrusted local creation time, not extracted contract text. Treat them as private case metadata and keep them out of Git. These commands require the existing application's POSIX storage environment; no network/model call is made.
