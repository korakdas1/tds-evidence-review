"""External receipts use synthetic cases; no credentials or network."""
from contextlib import closing
import copy
import hashlib
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from webapp.checkpoint import (CheckpointError, ReadSnapshot, create_checkpoint,
                              verify_checkpoint, write_checkpoint, read_checkpoint)
from webapp.service import ReviewService
from webapp.store import Store, canonical, event_hash, GENESIS


class CheckpointTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.store = Store(self.root / 'data')
        self.service = ReviewService(self.store)
        self.view = self.service.create_sample_case('warehouse')
        self.case = self.view['case']['id']
        self.receipt = create_checkpoint(self.store.data_dir, self.case)

    def verify(self, receipt=None):
        return verify_checkpoint(self.store.data_dir, receipt or self.receipt)

    def test_roundtrip_private_exclusive_external_file(self):
        path = self.root / 'held.json'
        write_checkpoint(path, self.store.data_dir, self.receipt)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.verify(read_checkpoint(path))['status'], 'MATCHES_EXTERNAL_CHECKPOINT')
        with self.assertRaises(FileExistsError):
            write_checkpoint(path, self.store.data_dir, self.receipt)
        with self.assertRaises(CheckpointError):
            write_checkpoint(self.store.data_dir / 'held.json', self.store.data_dir, self.receipt)
        self.assertNotIn('Vendor supplies', path.read_text())

    def test_appended_events_do_not_claim_external_attestation(self):
        before = self.view['finding']
        after = self.service.record_event(self.case, dict(kind='NOTE', reviewer='Synthetic Reviewer', note='Checked'))
        result = self.verify()
        self.assertEqual(result['later_events'], 1)
        self.assertIn('Only the held prefix', result['limitation'])
        self.assertEqual(before, after['finding'])

    def test_complete_self_consistent_rewrite_fails_external_checkpoint(self):
        with closing(sqlite3.connect(str(self.store.db_path))) as db, db:
            db.execute('DROP TRIGGER events_no_update')
            db.execute("UPDATE events SET actor='replacement'")
            db.row_factory = sqlite3.Row
            prev = GENESIS
            for row in db.execute('SELECT * FROM events ORDER BY id').fetchall():
                digest = event_hash(prev, row['case_id'], row['run_id'], row['created_at'], row['actor'],
                                    row['kind'], row['target'], row['payload_json'])
                db.execute('UPDATE events SET prev_hash=?, hash=? WHERE id=?', (prev, digest, row['id']))
                prev = digest
        self.assertEqual(self.store.verify_chain(self.case)['status'], 'INTACT')
        self.assertEqual(self.service.case_view(self.case)['integrity']['status'], 'VERIFIED')
        with self.assertRaisesRegex(CheckpointError, 'externally held'):
            self.verify()

    def test_anchored_tail_deletion_is_detected(self):
        self.service.record_event(self.case, dict(kind='NOTE', reviewer='Synthetic', note='Held note'))
        self.receipt = create_checkpoint(self.store.data_dir, self.case)
        with closing(sqlite3.connect(str(self.store.db_path))) as db, db:
            db.execute('DROP TRIGGER events_no_delete')
            db.execute('DELETE FROM events WHERE id=(SELECT MAX(id) FROM events)')
        self.assertEqual(self.store.verify_chain(self.case)['status'], 'INTACT')
        with self.assertRaises(CheckpointError):
            self.verify()

    def test_modified_report_and_context_fail(self):
        with closing(sqlite3.connect(str(self.store.db_path))) as db, db:
            db.execute('DROP TRIGGER runs_no_update')
            db.execute("UPDATE runs SET metadata_json='{}'")
        with self.assertRaises(CheckpointError):
            self.verify()
        with self.assertRaises(CheckpointError):
            create_checkpoint(self.store.data_dir, self.case)

    def test_bad_checksum_schema_count_and_duplicate_ids(self):
        for field, value in [('event_count', True), ('event_count', -1), ('case_id', []),
                             ('history_head', 'x'), ('schema', 'other'), ('runs', [])]:
            receipt = copy.deepcopy(self.receipt)
            receipt['body'][field] = value
            receipt['sha256'] = hashlib.sha256(canonical(receipt['body']).encode()).hexdigest()
            with self.subTest(field=field), self.assertRaises(CheckpointError):
                self.verify(receipt)
        receipt = copy.deepcopy(self.receipt)
        receipt['sha256'] = '0' * 64
        with self.assertRaises(CheckpointError):
            self.verify(receipt)

    def test_read_only_snapshot_does_not_modify_database(self):
        before = self.store.db_path.read_bytes()
        modified = self.store.db_path.stat().st_mtime_ns
        self.verify()
        self.assertEqual(before, self.store.db_path.read_bytes())
        self.assertEqual(modified, self.store.db_path.stat().st_mtime_ns)
        with ReadSnapshot(self.store.data_dir) as snapshot:
            with self.assertRaises(sqlite3.OperationalError):
                snapshot.connect().execute("INSERT INTO cases VALUES ('x','x','x','x','x')")

    def test_missing_database_is_not_created_and_damaged_document_fails(self):
        absent = self.root / 'absent'
        with self.assertRaises(CheckpointError):
            verify_checkpoint(absent, self.receipt)
        self.assertFalse(absent.exists())
        sha = self.store.run(self.view['run']['id'])['contract_sha256']
        _, path = self.store.verify_document(sha)
        path.write_bytes(b'damaged')
        with self.assertRaises(CheckpointError):
            self.verify()

    def test_invalid_oversized_and_symlink_receipts(self):
        path = self.root / 'bad'
        for data in [b'{', b'x' * (1024 * 1024 + 1), b'null', b'[]']:
            path.write_bytes(data)
            with self.assertRaises(CheckpointError):
                read_checkpoint(path)
        link = self.root / 'link'
        link.symlink_to(path)
        with self.assertRaises(CheckpointError):
            read_checkpoint(link)
        with self.assertRaises(FileExistsError):
            write_checkpoint(link, self.store.data_dir, self.receipt)
