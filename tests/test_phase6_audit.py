"""Independent Phase 6 adversarial regressions. Synthetic, offline, no legal assertions."""
import hashlib
import importlib.util
import json
import socket
import sqlite3
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from webapp.server import App, make_handler
from webapp.store import Store, StorageLimitError, UnsafeStorageError
from webapp.service import ServiceError

ROOT = Path(__file__).resolve().parent.parent
HOST = {"Host": "127.0.0.1:8765", "X-TDS-Review": "1"}


@unittest.skipUnless(importlib.util.find_spec("pypdf"), "Requires optional PDF dependency")
class AuditIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.app = App(Path(self.temp.name) / 'store')
        guard = patch('src.extraction.OpenRouterClient.complete', side_effect=AssertionError('No model calls'))
        mocked = guard.start()
        self.addCleanup(guard.stop)
        self.addCleanup(mocked.assert_not_called)

    def sample(self):
        return self.app.service.create_sample_case('warehouse')

    def tamper(self, statement, values=(), trigger='runs_no_update'):
        with closing(sqlite3.connect(self.app.store.db_path)) as db, db:
            db.execute('DROP TRIGGER IF EXISTS ' + trigger)
            db.execute(statement, values)

    def failed(self, case_id):
        paths = ['/api/cases/' + case_id, '/api/cases', '/api/cases/' + case_id + '/export']
        responses = [self.app.handle('GET', p, HOST) for p in paths]
        self.assertEqual([r.status for r in responses], [200, 200, 200])
        view, cases, export = [json.loads(r.body) for r in responses]
        self.assertIsNone(view['finding'])
        self.assertEqual(view['evidence'], [])
        self.assertEqual(cases[0]['integrity'], 'FAILED')
        self.assertEqual(export['runs'], [])
        self.assertEqual(export['integrity_status'], 'INTEGRITY_FAILED')
        self.assertIn('UNTRUSTED', export['forensic_untrusted']['warning'])
        return view

    def test_manual_metadata_is_bound_to_report_anchor(self):
        view = self.sample()
        metadata = dict(view['run']['metadata'], credit_date='2025-01-01')
        self.tamper('UPDATE runs SET metadata_json=?', (json.dumps(metadata),))
        result = self.failed(view['case']['id'])
        self.assertIn('run_context', result['integrity']['failed_checks'])
        with self.assertRaises(ServiceError) as cm:
            self.app.service.rerun(view['case']['id'], dict(metadata=metadata, reviewer='Synthetic auditor', reason='Retry'))
        self.assertEqual(cm.exception.status, 409)

    def test_document_substitution_and_method_are_bound(self):
        view = self.sample()
        sha = view['documents'][1]['sha256']
        self.tamper('UPDATE runs SET contract_sha256=?, method=?', (sha, 'supplied_extraction'))
        self.failed(view['case']['id'])

    def test_legacy_unanchored_context_is_not_retroactively_certified(self):
        view = self.sample()
        # Model a legacy run by removing context binding and recomputing only that newest event.
        from webapp.store import event_hash, canonical
        with closing(sqlite3.connect(self.app.store.db_path)) as db, db:
            db.row_factory = sqlite3.Row
            row = dict(db.execute("SELECT * FROM events WHERE kind='ANALYSIS_RUN'").fetchone())
            payload = json.loads(row['payload_json']); payload.pop('context_sha256')
            raw = canonical(payload)
            digest = event_hash(row['prev_hash'], row['case_id'], row['run_id'], row['created_at'], row['actor'], row['kind'], row['target'], raw)
            db.execute('DROP TRIGGER events_no_update')
            db.execute('UPDATE events SET payload_json=?, hash=? WHERE id=?', (raw, digest, row['id']))
        self.failed(view['case']['id'])

    def test_malformed_stored_json_does_not_break_case_list(self):
        view = self.sample()
        for field, value in [('report_json','{broken'), ('metadata_json','[]'), ('supplied_extraction_json','NaN')]:
            self.tamper('UPDATE runs SET ' + field + '=?', (value,))
            self.failed(view['case']['id'])

    def test_malformed_event_is_quarantined(self):
        view = self.sample()
        self.tamper("UPDATE events SET payload_json='[]' WHERE kind='ANALYSIS_RUN'", trigger='events_no_update')
        self.failed(view['case']['id'])

    def test_forged_case_title_not_presented_by_api_or_list(self):
        view = self.sample()
        self.tamper("UPDATE cases SET title='Approved for withholding'", trigger='cases_no_update')
        for path in ['/api/cases', '/api/cases/' + view['case']['id']]:
            self.assertNotIn(b'Approved for withholding', self.app.handle('GET', path, HOST).body)

    def test_forged_case_export_quarantines_title(self):
        view = self.sample()
        self.tamper("UPDATE cases SET title='Approved for withholding'", trigger='cases_no_update')
        export = self.app.service.export(view['case']['id'])
        self.assertEqual(export['case']['title'], 'Untrusted case record')
        self.assertEqual(export['forensic_untrusted']['case_record']['title'], 'Approved for withholding')

    def test_download_serves_exact_verified_snapshot(self):
        view = self.sample()
        sha = view['documents'][0]['sha256']
        state, data, path = self.app.store.read_document(sha)
        path.write_bytes(b'%PDF-1.4 changed after verification')
        with patch.object(self.app.store, 'read_document', return_value=(state, data, path)):
            response = self.app.document_file(sha)
        self.assertEqual(response.status, 200)
        self.assertEqual(response.body, data)
        self.assertEqual(hashlib.sha256(response.body).hexdigest(), sha)

    def test_initial_analysis_failure_leaves_no_case(self):
        with patch.object(self.app.service, '_analyse', side_effect=ServiceError(503, 'injected busy')):
            with self.assertRaises(ServiceError):
                self.sample()
        self.assertEqual(self.app.store.cases(), [])

    def test_history_write_failure_rolls_back_case_run_and_events(self):
        original = self.app.store._insert_event
        def fail_analysis(*args):
            if args[4] == 'ANALYSIS_RUN':
                raise sqlite3.OperationalError('injected failure')
            return original(*args)
        with patch.object(self.app.store, '_insert_event', side_effect=fail_analysis):
            with self.assertRaises(sqlite3.OperationalError):
                self.sample()
        with closing(self.app.store.connect()) as db:
            self.assertEqual([db.execute('SELECT COUNT(*) FROM ' + t).fetchone()[0] for t in ('cases','runs','events')], [0,0,0])

    def test_rerun_failure_preserves_previous_run(self):
        view = self.sample()
        body = dict(metadata=dict(view['run']['metadata'], credit_date='2026-10-09'), reviewer='Auditor', reason='Synthetic test')
        with patch.object(self.app.store, '_insert_event', side_effect=sqlite3.OperationalError('injected failure')):
            with self.assertRaises(sqlite3.OperationalError):
                self.app.service.rerun(view['case']['id'], body)
        self.assertEqual(len(self.app.store.runs(view['case']['id'])), 1)
        self.assertEqual(self.app.service.case_view(view['case']['id'])['integrity']['status'], 'VERIFIED')

    def test_nonstring_action_returns_validation_error(self):
        view = self.sample()
        response = self.app.handle('POST', '/api/cases/' + view['case']['id'] + '/events', HOST, b'{"kind":[],"reviewer":"Auditor"}')
        self.assertEqual(response.status, 400)


class AuditStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = Store(self.root / 'store')
        self.data = (ROOT / 'tests/fixtures/pdf_v1/supported.pdf').read_bytes()

    def test_restore_symlink_cannot_overwrite_unrelated_file(self):
        rec = self.store.save_document('synthetic.pdf', self.data)
        path = self.store.document_path(rec); path.write_bytes(b'damaged')
        victim = self.root/'unrelated.txt'; victim.write_bytes(b'KEEP')
        path.with_name(path.name+'.restore').symlink_to(victim)
        self.store.save_document('synthetic.pdf', self.data)
        self.assertEqual(victim.read_bytes(), b'KEEP')
        self.assertEqual(self.store.verify_document(rec['sha256'])[0], 'VERIFIED')

    def test_upload_directory_symlink_is_rejected(self):
        outside = self.root/'outside'; outside.mkdir()
        sha = hashlib.sha256(self.data).hexdigest()
        (self.store.documents_dir/sha).symlink_to(outside, target_is_directory=True)
        with self.assertRaises(UnsafeStorageError):
            self.store.save_document('escape.pdf', self.data)
        self.assertEqual(list(outside.iterdir()), [])

    def test_existing_storage_symlinks_are_rejected(self):
        for leaf in ('documents','review.sqlite3'):
            data_dir = self.root/leaf.replace('.','_'); data_dir.mkdir()
            target = self.root/('target_'+leaf)
            if leaf == 'documents': target.mkdir()
            else: target.write_bytes(b'KEEP')
            (data_dir/leaf).symlink_to(target)
            with self.assertRaises(UnsafeStorageError): Store(data_dir)

    def test_replaced_database_symlink_is_refused(self):
        self.store.db_path.unlink()
        victim = self.root/'unrelated.txt'; victim.write_bytes(b'KEEP')
        self.store.db_path.symlink_to(victim)
        with self.assertRaises(UnsafeStorageError): self.store.cases()
        self.assertEqual(victim.read_bytes(), b'KEEP')

    def test_damaged_large_file_is_not_read_unbounded(self):
        rec = self.store.save_document('synthetic.pdf', self.data)
        path = self.store.document_path(rec)
        with path.open('wb') as stream: stream.truncate(30*1024*1024)
        self.assertEqual(self.store.read_document(rec['sha256'])[:2], ('HASH_MISMATCH', None))

    def test_quota_across_independent_stores_and_duplicate_uploads(self):
        stores = [Store(self.root/'quota', max_documents=1) for _ in range(8)]
        gate = threading.Barrier(len(stores))
        def upload(pair):
            n,store = pair; gate.wait()
            try: store.save_document('test.pdf', self.data+str(n).encode()); return 'stored'
            except StorageLimitError: return 'quota'
        with ThreadPoolExecutor(max_workers=8) as pool:
            outcomes = list(pool.map(upload, enumerate(stores)))
        self.assertEqual(outcomes.count('stored'), 1)
        self.assertEqual(outcomes.count('quota'), 7)
        with closing(stores[0].connect()) as db:
            rec = dict(db.execute('SELECT * FROM documents').fetchone())
        data=stores[0].document_path(rec).read_bytes()
        stores[1].save_document('duplicate.pdf', data)
        self.assertEqual(len(list((self.root/'quota/documents').glob('*/*.pdf'))),1)

    def test_file_write_failure_cleans_temporary_and_database(self):
        with patch('webapp.store.os.replace', side_effect=OSError('injected disk failure')):
            with self.assertRaises(UnsafeStorageError): self.store.save_document('test.pdf', self.data)
        with closing(self.store.connect()) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM documents').fetchone()[0],0)
        self.assertFalse(list(self.store.documents_dir.glob('*/.*')))


class AuditHttpTests(unittest.TestCase):
    def test_ambiguous_and_short_requests_never_mutate(self):
        with tempfile.TemporaryDirectory() as tmp:
            app=App(tmp,0)
            server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(app,request_timeout=0.2));app.port=server.server_port
            worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
            try:
                variants=[('Content-Length: 100\r\n',b'{}',400),
                          ('Content-Length: 2\r\nContent-Length: 3\r\n',b'{}',400),
                          ('Transfer-Encoding: chunked\r\nContent-Length: 2\r\n',b'{}',400)]
                for framing,body,status in variants:
                    with socket.create_connection(('127.0.0.1',app.port),timeout=3) as sock:
                        request=('POST /api/samples/warehouse/cases HTTP/1.0\r\nHost: 127.0.0.1:%d\r\nX-TDS-Review: 1\r\n'%app.port+framing+'\r\n').encode()+body
                        sock.sendall(request);sock.shutdown(socket.SHUT_WR)
                        self.assertIn((' '+str(status)+' ').encode(),sock.recv(4096).split(b'\r\n')[0])
                self.assertEqual(app.store.cases(),[])
            finally:
                server.shutdown();server.server_close();worker.join()
