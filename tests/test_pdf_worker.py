"""Resource containment regressions. All fixtures/probes are synthetic; no providers."""
import copy
import hashlib
import http.client
import importlib.util
import json
import multiprocessing
import os
import signal
import sys
import tempfile
import threading
import time
import unittest
import zlib
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from src.document_review import review_pdf_contract
from src.pdf_ingestion import read_pdf
from src.pdf_worker import DEFAULT_LIMITS, read_pdf_isolated
from tests.test_phase6 import bomb_pdf
from webapp.server import App, make_handler

FIXTURES=Path(__file__).parent/'fixtures/pdf_v1'


def cpu_parser(path):
    while True:
        pass


def memory_parser(path):
    allocation=bytearray(1024*1024*1024)
    return {'unexpected':len(allocation)}


def failing_parser(path):
    raise ValueError('PRIVATE_SENTINEL_MUST_NOT_LEAK')


def crash_parser(path):
    os._exit(99)


def partial_then_stall(path):
    (Path(path).parent/'result.json').write_text(json.dumps(read_pdf(path)))
    time.sleep(30)


def forged_parser(path):
    doc=read_pdf(path);doc['pages'][0]['text']='forged unsupported evidence'
    return doc


def stress_bytes():
    encoded=zlib.compress(b'q Q\n'*480000,9)
    with patch('tests.test_phase6.zlib.compress',return_value=encoded):
        return bomb_pdf(pages=20,raw_bytes=0)


@unittest.skipUnless(sys.platform.startswith('linux') and importlib.util.find_spec('pypdf'), 'Linux + optional pypdf required')
class PDFWorkerTests(unittest.TestCase):
    def assert_failed_reaped(self, result, code):
        self.assertEqual(result['status'],'REJECTED')
        self.assertIn(code,result['issues'])
        self.assertEqual(result['text'],'')
        self.assertEqual(result['pages'],[])
        self.assertEqual(result['segments'],[])
        trace=result['worker']
        self.assertTrue(trace['reaped'])
        if trace['pid']:
            with self.assertRaises(ChildProcessError):os.waitpid(trace['pid'],os.WNOHANG)
        self.assertNotIn('PRIVATE_SENTINEL',json.dumps(result))

    def test_all_frozen_fixtures_preserve_source_and_failures(self):
        manifest=json.loads((FIXTURES/'manifest.json').read_text())
        for fixture in manifest['fixtures']:
            with self.subTest(fixture=fixture['file']):
                path=FIXTURES/fixture['file'];before=read_pdf(path);after=read_pdf_isolated(path)
                for key in ('status','issues','text','pages','segments','file_sha256','name'):
                    self.assertEqual(after[key],before[key],key)
                self.assertTrue(after['worker']['reaped'])
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),fixture['sha256'])

    def test_cpu_deadline_is_not_caught_as_partial_page_failure(self):
        doc=read_pdf_isolated(FIXTURES/'supported.pdf',limits=dict(DEFAULT_LIMITS,cpu_seconds=1,wall_seconds=4),_parser=cpu_parser)
        self.assert_failed_reaped(doc,'PDF_WORKER_CPU_LIMIT')
        self.assertLess(doc['worker']['elapsed_seconds'],4)

    def test_memory_limit_is_explicit_and_reaped(self):
        doc=read_pdf_isolated(FIXTURES/'supported.pdf',_parser=memory_parser)
        self.assert_failed_reaped(doc,'PDF_WORKER_MEMORY_LIMIT')

    def test_wall_deadline_discards_even_complete_uncommitted_output(self):
        doc=read_pdf_isolated(FIXTURES/'supported.pdf',limits=dict(DEFAULT_LIMITS,wall_seconds=0.4),_parser=partial_then_stall)
        self.assert_failed_reaped(doc,'PDF_WORKER_WALL_TIMEOUT')
        self.assertLess(doc['worker']['elapsed_seconds'],1.5)

    def test_output_limit_discards_every_source_span(self):
        doc=read_pdf_isolated(FIXTURES/'supported.pdf',limits=dict(DEFAULT_LIMITS,output_bytes=128))
        self.assert_failed_reaped(doc,'PDF_WORKER_OUTPUT_LIMIT')

    def test_parser_exceptions_and_crashes_are_sanitized(self):
        for parser,code in ((failing_parser,'PDF_WORKER_PARSER_FAILURE'),(crash_parser,'PDF_WORKER_CRASH')):
            self.assert_failed_reaped(read_pdf_isolated(FIXTURES/'supported.pdf',_parser=parser),code)

    def test_worker_source_result_is_checked_before_pipeline_use(self):
        self.assert_failed_reaped(read_pdf_isolated(FIXTURES/'supported.pdf',_parser=forged_parser),'PDF_WORKER_INVALID_RESULT')

    def test_bounded_input_special_files_and_unsupported_platform(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'large.pdf'
            with path.open('wb') as stream:stream.truncate(8*1024*1024)
            self.assert_failed_reaped(read_pdf_isolated(path),'FILE_SIZE_LIMIT')
            fifo=Path(tmp)/'fifo.pdf';os.mkfifo(fifo)
            self.assert_failed_reaped(read_pdf_isolated(fifo),'FILE_UNAVAILABLE')
        with patch('src.pdf_worker.sys.platform','unsupported'):
            self.assert_failed_reaped(read_pdf_isolated(FIXTURES/'supported.pdf'),'PDF_WORKER_UNSUPPORTED_PLATFORM')

    def test_invalid_configuration_is_rejected_without_start(self):
        for field,value in (('wall_seconds',float('nan')),('wall_seconds',0),('cpu_seconds',True),('memory_bytes',-1),('output_bytes',32*1024*1024)):
            with self.subTest(field=field,value=value), self.assertRaises(ValueError):
                read_pdf_isolated(FIXTURES/'supported.pdf',limits=dict(DEFAULT_LIMITS,**{field:value}))

    def test_previous_43kb_stress_case_is_contained_by_default_worker(self):
        data=stress_bytes();self.assertEqual(len(data),43115)
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'stress.pdf';path.write_bytes(data)
            doc=read_pdf_isolated(path)
        self.assertIn(doc['worker']['status'],('PDF_WORKER_CPU_LIMIT','PDF_WORKER_WALL_TIMEOUT','PDF_WORKER_MEMORY_LIMIT'))
        self.assert_failed_reaped(doc,doc['worker']['status'])
        self.assertLess(doc['worker']['elapsed_seconds'],9)

    def test_failed_worker_never_supplies_validated_facts(self):
        meta=json.loads((FIXTURES/'transaction.json').read_text())
        with patch('src.document_review.read_pdf',side_effect=lambda p:read_pdf_isolated(p,_parser=crash_parser)):
            report=review_pdf_contract(meta,FIXTURES/'supported.pdf')
        self.assertEqual(report['review']['factual_evidence_status'],'INSUFFICIENT_TO_ESTABLISH_CONTROL')
        self.assertEqual(report['evidence_items'],[])
        self.assertIsNone(report['review']['proposed_table_item'])
        self.assertTrue(report['review']['human_review_required'])

    def test_http_server_remains_responsive_while_worker_is_stalled(self):
        with tempfile.TemporaryDirectory() as tmp:
            app=App(tmp,0)
            doc=app.service.upload('supported.pdf',(FIXTURES/'supported.pdf').read_bytes())
            server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(app));app.port=server.server_port
            server_thread=threading.Thread(target=server.serve_forever,daemon=True);server_thread.start()
            entered=threading.Event();response=[];errors=[]
            def isolated(path):
                entered.set()
                return read_pdf_isolated(path,limits=dict(DEFAULT_LIMITS,wall_seconds=1),_parser=partial_then_stall)
            def create():
                try:
                    conn=http.client.HTTPConnection('127.0.0.1',app.port,timeout=5)
                    body=json.dumps(dict(contract_sha256=doc['sha256'],metadata=json.loads((FIXTURES/'transaction.json').read_text())))
                    conn.request('POST','/api/cases',body,{'Content-Type':'application/json','X-TDS-Review':'1'})
                    res=conn.getresponse();response.append((res.status,json.loads(res.read())));conn.close()
                except Exception as exc:errors.append(type(exc).__name__)
            try:
                with patch('src.document_review.read_pdf',side_effect=isolated):
                    request_thread=threading.Thread(target=create);request_thread.start()
                    self.assertTrue(entered.wait(2))
                    started=time.monotonic();conn=http.client.HTTPConnection('127.0.0.1',app.port,timeout=2)
                    conn.request('GET','/api/health');health=conn.getresponse();health.read();conn.close()
                    self.assertEqual(health.status,200);self.assertLess(time.monotonic()-started,0.8)
                    request_thread.join(5)
                self.assertFalse(request_thread.is_alive());self.assertEqual(errors,[])
                self.assertEqual(response[0][0],201)
                self.assertEqual(response[0][1]['finding']['factual_evidence_status'],'INSUFFICIENT_TO_ESTABLISH_CONTROL')
                self.assertIsNone(response[0][1]['finding']['proposed_table_item'])
            finally:
                server.shutdown();server.server_close();server_thread.join()
        self.assertEqual(multiprocessing.active_children(),[])
