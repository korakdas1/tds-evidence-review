"""Controlled live integration, entirely mocked; no real model requests."""
from contextlib import closing
import copy
import json
import sqlite3
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from src.extraction import ModelError
from src.live_provider import isolated_request, request_once
from webapp.live import LiveController, validate_config
from webapp.server import App
from tests.test_webapp import HOST, SAMPLES

CONFIG = dict(model='synthetic/fixed:free', allowed_models=['synthetic/fixed:free'], api_key='unit-test-not-a-credential',
              max_requests=4, timeout_seconds=1, max_spend_usd=0)


def response(config, record, mode):
    return dict(raw_output=json.dumps(dict(personnel_supplied='yes', worker_supervisor='customer',
        supporting_quotes=[dict(fact='personnel_supplied', value='yes', quote="The Vendor supplies six warehouse workers for the Customer's distribution site."),
                           dict(fact='worker_supervisor', value='customer', quote='The Customer supervises each worker during every shift.')],
        missing_facts=[], contradictory_evidence=[])), returned_model=config['model'],
        response_metadata=dict(provider_cost_usd=0), usage=dict(prompt_tokens=10, completion_tokens=20, total_tokens=30))


def stall(config, record, mode):
    time.sleep(10)
    return response(config, record, mode)


class ControlledLiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.calls = []
        def transport(config, record, mode):
            self.calls.append((record, mode))
            return response(config, record, mode)
        self.app = App(self.tmp.name, live_config=CONFIG, _live_transport=transport, _live_interval=0)
        uploaded = self.app.service.upload('synthetic.pdf', (SAMPLES / 'warehouse_agreement.pdf').read_bytes())
        sample = next(s for s in self.app.service.samples() if s['id'] == 'warehouse')
        self.body = dict(metadata=sample['metadata'], title='Synthetic live integration',
                         contract_sha256=uploaded['sha256'], method='live_hybrid')
        for target in ('urllib.request.urlopen', 'urllib.request.build_opener', 'src.extraction.OpenRouterClient.complete'):
            guard = patch(target, side_effect=AssertionError('No real provider requests in development'))
            mocked = guard.start()
            self.addCleanup(guard.stop)
            self.addCleanup(mocked.assert_not_called)

    def call(self, method, path, body=None, headers=None):
        result = self.app.handle(method, path, headers or HOST, json.dumps(body).encode() if body is not None else b'')
        return result.status, json.loads(result.body)

    def prepare(self, body=None):
        body = dict(body or self.body)
        status, result = self.call('POST', '/api/live/prepare', body)
        self.assertEqual(status, 200, result)
        body['live_confirmation'] = result['token']
        return body

    def test_default_app_ignores_environment_credentials_and_rejects_live(self):
        offline = App(self.tmp.name)
        self.assertIsNone(offline.service.live)
        response = offline.handle('POST', '/api/cases', HOST, json.dumps(self.body).encode())
        self.assertEqual(response.status, 403)
        self.assertEqual(self.calls, [])

    def test_config_public_has_model_and_limits_without_key(self):
        status, config = self.call('GET', '/api/live/config')
        self.assertEqual(status, 200)
        self.assertEqual(config['model'], CONFIG['model'])
        self.assertEqual(config['max_spend_usd'], 0)
        self.assertNotIn(CONFIG['api_key'], json.dumps(config))

    def test_no_confirmation_no_transmission(self):
        self.assertEqual(self.call('POST', '/api/cases', self.body)[0], 400)
        self.assertEqual(self.calls, [])
        self.assertEqual(self.app.store.cases(), [])

    def test_preparation_and_cancel_do_not_transmit_or_reserve(self):
        self.prepare()
        self.assertEqual(self.calls, [])
        self.assertEqual(self.app.service.live.public()['requests_reserved'], 0)
        self.assertEqual(self.app.store.cases(), [])

    def test_confirmation_is_one_use_and_bound_to_metadata(self):
        body = self.prepare()
        body['metadata'] = dict(body['metadata'], credit_date='2026-03-31')
        self.assertEqual(self.call('POST', '/api/cases', body)[0], 409)
        body['metadata'] = self.body['metadata']
        self.assertEqual(self.call('POST', '/api/cases', body)[0], 409)
        self.assertEqual(self.calls, [])

    def test_confirmation_expiry(self):
        body = self.prepare()
        token = body['live_confirmation']
        _, binding = self.app.service.live.pending[token]
        self.app.service.live.pending[token] = (0, binding)
        self.assertEqual(self.call('POST', '/api/cases', body)[0], 409)
        self.assertEqual(self.calls, [])

    def test_mocked_pipeline_preserves_evidence_and_withholds_proposal(self):
        body = self.prepare()
        status, view = self.call('POST', '/api/cases', body)
        self.assertEqual(status, 201, view)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(view['run']['execution']['execution_kind'], 'SIMULATED')
        self.assertEqual(view['run']['model_network_calls'], 0)
        self.assertEqual(view['run']['execution']['usage']['total_tokens'], 30)
        self.assertIsNone(view['finding']['proposed_table_item'])
        self.assertEqual(view['integrity']['status'], 'VERIFIED')
        self.assertTrue(all(c['spans_verified'] for c in view['evidence']))
        self.assertEqual(self.call('POST', '/api/cases', body)[0], 409)
        self.assertEqual(len(self.calls), 1)

    def test_unknown_interpretation_remains_review_only(self):
        def suggested(c, record, mode):
            sample = next(s for s in self.app.service.samples() if s['id'] == 'event-crew')
            return dict(raw_output=json.dumps(sample['supplied_extraction']), returned_model=c['model'])
        self.app.service.live.transport = suggested
        sample = next(s for s in self.app.service.samples() if s['id'] == 'event-crew')
        from webapp.service import ROOT
        doc = self.app.service.upload('event.pdf', (ROOT / sample['contract']).read_bytes())
        body = dict(self.body, contract_sha256=doc['sha256'])
        status, view = self.call('POST', '/api/cases', self.prepare(body))
        self.assertEqual(status, 201)
        self.assertTrue(any(c['category'] == 'ai_suggestion' for c in view['evidence']))
        self.assertEqual(view['finding']['validated_facts']['worker_supervisor'], 'unknown')
        self.assertIsNone(view['finding']['proposed_table_item'])

    def test_429_stops_persistently_without_retry(self):
        def fail(*args):
            self.calls.append('HTTP_429')
            raise ModelError('HTTP_429', unavailable=True)
        self.app.service.live.transport = fail
        status, view = self.call('POST', '/api/cases', self.prepare())
        self.assertEqual(status, 201)
        self.assertEqual(view['finding']['run_status'], 'NOT_RUN')
        self.assertEqual(len(self.calls), 1)
        self.assertTrue(self.app.service.live.public()['stopped'])
        restarted = LiveController(self.app.store, CONFIG, _transport=response)
        self.assertTrue(restarted.public()['stopped'])
        self.assertEqual(self.call('POST', '/api/live/prepare', self.body)[0], 409)
        self.assertEqual(len(self.calls), 1)

    def test_budget_reservations_survive_restart_and_concurrency(self):
        errors, successes = [], []
        def reserve():
            try:
                successes.append(self.app.service.live.reserve('synthetic'))
            except ModelError as e:
                errors.append(e.code)
        threads = [threading.Thread(target=reserve) for _ in range(8)]
        for t in threads: t.start()
        for t in threads: t.join()
        self.assertEqual(len(successes), 4)
        self.assertEqual(errors, ['LIVE_REQUEST_BUDGET_EXHAUSTED'] * 4)
        restarted = LiveController(self.app.store, CONFIG, _transport=response)
        self.assertEqual(restarted.public()['remaining_requests'], 0)

    def test_pacing_and_append_only_budget(self):
        self.app.service.live.minimum_interval = 15
        self.app.service.live.reserve('one')
        with self.assertRaisesRegex(ModelError, 'PACING'):
            self.app.service.live.reserve('two')
        with closing(self.app.store.connect()) as db, db:
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute('DELETE FROM live_requests')

    def test_model_mismatch_and_nonzero_cost_stop_and_abstain(self):
        for bad in ('model', 'cost'):
            with self.subTest(bad=bad), tempfile.TemporaryDirectory() as folder:
                from webapp.store import Store
                def transport(c, r, m):
                    result = response(c, r, m)
                    if bad == 'model': result['returned_model'] = 'other/model'
                    else: result['response_metadata']['provider_cost_usd'] = 1
                    return result
                controller = LiveController(Store(folder), CONFIG, _transport=transport, _minimum_interval=0)
                from webapp.live import ControlledClient
                with self.assertRaises(ModelError):
                    ControlledClient(controller, 'synthetic').complete({}, 'hybrid')
                self.assertTrue(controller.public()['stopped'])

    def test_input_limit_reserves_nothing(self):
        from webapp.live import ControlledClient
        with self.assertRaisesRegex(ModelError, 'INPUT_LIMIT'):
            ControlledClient(self.app.service.live, 'synthetic').complete({'contract_excerpt':'x' * 100001}, 'hybrid')
        self.assertEqual(self.app.service.live.public()['requests_reserved'], 0)
        self.assertEqual(self.calls, [])

    def test_host_and_csrf_guard_confirmation(self):
        self.assertEqual(self.call('POST', '/api/live/prepare', self.body, {'Host':'evil.example'})[0], 421)
        self.assertEqual(self.call('POST', '/api/live/prepare', self.body, {'Host':'127.0.0.1:8765'})[0], 403)
        self.assertEqual(self.calls, [])

    def test_invalid_free_model_allowlist_spending_and_limits(self):
        for changes in [dict(model='openrouter/free'), dict(model='synthetic/paid'), dict(allowed_models=[]),
                        dict(max_spend_usd=1), dict(max_spend_usd=float('nan')), dict(api_key=''),
                        dict(max_requests=True), dict(max_requests=33), dict(timeout_seconds=61)]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                validate_config(dict(CONFIG, **changes))

    def test_document_identity_and_reliability_checked_before_transmission(self):
        from webapp.live import ControlledClient
        for document, code in [(dict(file_sha256='changed', status='EXTRACTED'), 'CHANGED_SINCE_CONSENT'),
                               (dict(file_sha256='expected', status='NEEDS_DOCUMENT_REVIEW'), 'RELIABLE_DOCUMENT')]:
            client = ControlledClient(self.app.service.live, 'synthetic', 'expected')
            client.validate_document(document)
            with self.assertRaisesRegex(ModelError, code):
                client.complete({}, 'hybrid')
        self.assertEqual(self.calls, [])
        self.assertEqual(self.app.service.live.public()['requests_reserved'], 0)

    def test_fabricated_quote_never_becomes_supported_fact(self):
        def hallucinated(c, record, mode):
            result = response(c, record, mode)
            extraction = json.loads(result['raw_output'])
            extraction['supporting_quotes'][1]['quote'] = 'The recipient commands all staff without exception.'
            result['raw_output'] = json.dumps(extraction)
            return result
        self.app.service.live.transport = hallucinated
        _, view = self.call('POST', '/api/cases', self.prepare())
        self.assertEqual(view['finding']['validated_facts']['worker_supervisor'], 'unknown')
        self.assertIsNone(view['finding']['proposed_table_item'])
        self.assertTrue(any(c['mapping_status'] == 'UNRESOLVED' for c in view['evidence']))

    def test_malformed_model_output_is_error_not_completed_extraction(self):
        def malformed(c, record, mode):
            return dict(raw_output='{', returned_model=c['model'])
        self.app.service.live.transport = malformed
        _, view = self.call('POST', '/api/cases', self.prepare())
        self.assertEqual(view['finding']['run_status'], 'ERROR')
        self.assertEqual(view['run']['execution']['pipeline_error'], 'INVALID_MODEL_JSON')
        self.assertIsNone(view['finding']['proposed_table_item'])

    def test_rerun_never_inherits_live_transmission(self):
        _, view = self.call('POST', '/api/cases', self.prepare())
        status, after = self.call('POST', '/api/cases/' + view['case']['id'] + '/runs',
            dict(metadata=dict(self.body['metadata'], credit_date='2026-03-31'), reviewer='Synthetic', reason='Date correction'))
        self.assertEqual(status, 201, after)
        self.assertEqual(after['run']['method'], 'baseline')
        self.assertEqual(len(self.calls), 1)


class ProviderBoundaryTests(unittest.TestCase):
    def test_worker_total_deadline_and_reaping_without_network(self):
        import multiprocessing
        tick = time.monotonic()
        with self.assertRaisesRegex(ModelError, 'LIVE_WALL_TIMEOUT'):
            isolated_request(CONFIG, {}, 'hybrid', _transport=stall)
        self.assertLess(time.monotonic() - tick, 3)
        self.assertEqual(multiprocessing.active_children(), [])

    def test_worker_success_is_explicitly_mocked(self):
        result = isolated_request(CONFIG, {}, 'hybrid', _transport=response)
        self.assertEqual(result['returned_model'], CONFIG['model'])

    def test_refusal_truncation_and_http_failure_are_sanitized(self):
        from unittest.mock import MagicMock
        import urllib.error
        record = dict(id='SYN', invoice_description='Synthetic', contract_excerpt='Vendor supplies workers.',
                      payer_type='company', payee_legal_form='company', payee_residency='India resident',
                      credit_date='2026-04-01', payment_date='2026-04-01')
        for message, finish, code in [(dict(content=None, refusal='private refusal'), 'stop', 'MODEL_REFUSAL'),
                                      (dict(content='{}'), 'length', 'INCOMPLETE_MODEL_OUTPUT')]:
            opened = MagicMock()
            opened.__enter__.return_value.read.return_value = json.dumps(dict(model=CONFIG['model'],
                choices=[dict(message=message, finish_reason=finish)])).encode()
            with patch('urllib.request.build_opener') as factory:
                factory.return_value.open.return_value = opened
                with self.assertRaisesRegex(ModelError, code):
                    request_once(CONFIG, record, 'hybrid')
        with patch('urllib.request.build_opener') as factory:
            factory.return_value.open.side_effect = urllib.error.HTTPError('private-url', 429, 'private-body', {}, None)
            with self.assertRaisesRegex(ModelError, '^HTTP_429$'):
                request_once(CONFIG, record, 'hybrid')
            self.assertEqual(factory.return_value.open.call_count, 1)

    def test_http_envelope_free_only_redacts_and_never_falls_back(self):
        record = dict(id='SYN', invoice_description='Synthetic', contract_excerpt='Vendor supplies workers.',
                      payer_type='company', payee_legal_form='company', payee_residency='India resident',
                      credit_date='2026-04-01', payment_date='2026-04-01')
        raw = dict(model=CONFIG['model'], choices=[dict(finish_reason='stop', message=dict(content=CONFIG['api_key']))], usage=dict(cost=0))
        from unittest.mock import MagicMock
        opened = MagicMock()
        opened.__enter__.return_value.read.return_value = json.dumps(raw).encode()
        with patch('urllib.request.build_opener') as factory:
            factory.return_value.open.return_value = opened
            result = request_once(CONFIG, record, 'hybrid')
            request = factory.return_value.open.call_args.args[0]
            payload = json.loads(request.data)
            self.assertEqual(payload['provider']['max_price'], dict(prompt=0, completion=0))
            self.assertFalse(payload['provider']['allow_fallbacks'])
            self.assertNotIn('models', payload)
            self.assertEqual(factory.return_value.open.call_count, 1)
            self.assertEqual(result['raw_output'], '[REDACTED_API_KEY]')
