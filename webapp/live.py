"""Explicit opt-in, one-use consent and persistent free-only request budget."""
from contextlib import closing
import hashlib
import json
import math
import os
import re
import secrets
import threading
import time

from src.extraction import ModelError
from src.live_provider import isolated_request, MAX_INPUT
from .store import canonical, now

NOTICE = ('Contract text and manually entered transaction details will be sent to OpenRouter and the '
          'selected external model provider. The invoice PDF itself is not sent. Use only synthetic or '
          'properly authorised content. Provider retention policies apply. This cannot approve tax treatment.')


def config_from_environment():
    """Used only after the operator starts with --enable-live; never reads .env automatically."""
    config = dict(model=os.getenv('TDS_LIVE_MODEL', ''), api_key=os.getenv('OPENROUTER_API_KEY', ''),
                  allowed_models=os.getenv('TDS_LIVE_ALLOWED_MODELS', '').split(','),
                  max_requests=int(os.getenv('TDS_LIVE_MAX_REQUESTS', '0')),
                  timeout_seconds=int(os.getenv('TDS_LIVE_TIMEOUT_SECONDS', '45')),
                  max_spend_usd=float(os.getenv('TDS_LIVE_MAX_SPEND_USD', '0')))
    validate_config(config)
    return config


def validate_config(c):
    model = c.get('model')
    if not isinstance(model, str) or not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+:free', model):
        raise ValueError('Choose one fixed :free model; routers and paid models are disabled')
    if model not in c.get('allowed_models', []):
        raise ValueError('Configured model must appear in TDS_LIVE_ALLOWED_MODELS')
    if not isinstance(c.get('api_key'), str) or not c['api_key'].strip():
        raise ValueError('OPENROUTER_API_KEY must be nonempty')
    if type(c.get('max_requests')) is not int or not 1 <= c['max_requests'] <= 32:
        raise ValueError('TDS_LIVE_MAX_REQUESTS must be 1..32')
    if type(c.get('timeout_seconds')) is not int or not 1 <= c['timeout_seconds'] <= 60:
        raise ValueError('TDS_LIVE_TIMEOUT_SECONDS must be 1..60')
    if type(c.get('max_spend_usd')) not in (int, float) or c['max_spend_usd'] != 0:
        raise ValueError('Only a zero-dollar spending limit is supported')


class LiveController:
    def __init__(self, store, config, _transport=None, _minimum_interval=15):
        validate_config(config)
        self.store, self.config = store, dict(config)
        self.transport = _transport or isolated_request
        self.kind = 'SIMULATED' if _transport is not None else 'LIVE'
        self.minimum_interval = _minimum_interval
        self.pending, self.lock = {}, threading.Lock()
        with closing(store.connect()) as db, db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS live_requests (id TEXT PRIMARY KEY, created_at TEXT NOT NULL,
                    epoch REAL NOT NULL, binding_sha256 TEXT NOT NULL, model TEXT NOT NULL, execution_kind TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS live_stops (code TEXT NOT NULL, created_at TEXT NOT NULL);
            ''')
            for table in ('live_requests', 'live_stops'):
                for action in ('UPDATE', 'DELETE'):
                    db.execute("CREATE TRIGGER IF NOT EXISTS {}_no_{} BEFORE {} ON {} BEGIN SELECT RAISE(ABORT, 'append-only live ledger'); END".format(table, action.lower(), action, table))

    def public(self):
        with closing(self.store.connect()) as db:
            used = db.execute('SELECT COUNT(*) FROM live_requests').fetchone()[0]
            stopped = db.execute('SELECT COUNT(*) FROM live_stops').fetchone()[0] > 0
        return dict(enabled=True, model=self.config['model'], execution_kind=self.kind,
                    max_requests=self.config['max_requests'], requests_reserved=used,
                    remaining_requests=max(0, self.config['max_requests'] - used), stopped=stopped,
                    max_spend_usd=0, timeout_seconds=self.config['timeout_seconds'],
                    minimum_interval_seconds=self.minimum_interval, notice=NOTICE)

    @staticmethod
    def binding(body):
        return hashlib.sha256(canonical({k: v for k, v in body.items() if k != 'live_confirmation'}).encode()).hexdigest()

    def prepare(self, body):
        from .service import ServiceError, clean_metadata
        if not isinstance(body, dict) or body.get('method') != 'live_hybrid':
            raise ServiceError(400, 'Prepare a live hybrid review explicitly')
        clean_metadata(body.get('metadata'))
        sha = body.get('contract_sha256')
        if not isinstance(sha, str) or not re.fullmatch('[0-9a-f]{64}', sha) or self.store.verify_document(sha)[0] != 'VERIFIED':
            raise ServiceError(400, 'Upload a verified contract before requesting confirmation')
        status = self.public()
        if status['stopped'] or not status['remaining_requests']:
            raise ServiceError(409, 'Live request budget is exhausted or stopped; no request will be sent')
        with self.lock:
            self.pending = {k: v for k, v in self.pending.items() if v[0] > time.monotonic()}
            if len(self.pending) >= 100:
                raise ServiceError(429, 'Too many pending confirmations')
            token = secrets.token_urlsafe(32)
            self.pending[token] = (time.monotonic() + 300, self.binding(body))
        return dict(token=token, expires_in_seconds=300, model=status['model'], notice=NOTICE,
                    execution_kind=self.kind, binding_sha256=self.binding(body))

    def consume(self, body):
        from .service import ServiceError
        token = body.get('live_confirmation')
        if not isinstance(token, str):
            raise ServiceError(400, 'A fresh per-run external-transmission confirmation is required')
        with self.lock:
            held = self.pending.pop(token, None)
        if not held or held[0] <= time.monotonic() or held[1] != self.binding(body):
            raise ServiceError(409, 'Confirmation expired, was used, or does not match this review')
        return ControlledClient(self, held[1], body['contract_sha256'])

    def reserve(self, binding):
        with closing(self.store.connect()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT 1 FROM live_stops LIMIT 1').fetchone():
                raise ModelError('LIVE_CIRCUIT_STOPPED', unavailable=True)
            count, latest = db.execute('SELECT COUNT(*), MAX(epoch) FROM live_requests').fetchone()
            if count >= self.config['max_requests']:
                raise ModelError('LIVE_REQUEST_BUDGET_EXHAUSTED', unavailable=True)
            if latest is not None and time.time() - latest < self.minimum_interval:
                raise ModelError('LIVE_PACING_WAIT', unavailable=True)
            request_id = secrets.token_hex(16)
            db.execute('INSERT INTO live_requests VALUES (?,?,?,?,?,?)',
                       (request_id, now(), time.time(), binding, self.config['model'], self.kind))
        return request_id

    def stop(self, code):
        with closing(self.store.connect()) as db, db:
            db.execute('INSERT INTO live_stops VALUES (?,?)', (code, now()))


class ControlledClient:
    configured = True
    def __init__(self, controller, binding, document_sha256=None):
        self.controller, self.binding = controller, binding
        self.document_sha256 = document_sha256
        self.document_error = None
        self.model = controller.config['model']
        self.calls = 0
        self.audit = dict(execution_kind=controller.kind, configured_model=self.model,
                          consent_binding_sha256=binding, consent='EXPLICIT_ONE_USE_PER_RUN',
                          request_reserved=False, provider_requests_attempted=0, model_network_calls=0,
                          max_spend_usd=0, estimated_cost_usd=None)

    def validate_document(self, document):
        if document.get('file_sha256') != self.document_sha256:
            self.document_error = 'LIVE_DOCUMENT_CHANGED_SINCE_CONSENT'
        elif document.get('status') != 'EXTRACTED':
            self.document_error = 'LIVE_REQUIRES_RELIABLE_DOCUMENT_TEXT'

    def complete(self, record, mode):
        if self.document_error:
            raise ModelError(self.document_error)
        if self.calls:
            raise ModelError('LIVE_ONE_REQUEST_ONLY', unavailable=True)
        self.calls += 1
        if len(json.dumps(record).encode()) > MAX_INPUT:
            raise ModelError('LIVE_INPUT_LIMIT')
        request_id = self.controller.reserve(self.binding)
        self.audit.update(request_reserved=True, request_id=request_id,
                          provider_requests_attempted=1,
                          model_network_calls=1 if self.controller.kind == 'LIVE' else 0)
        tick = time.perf_counter()
        try:
            result = self.controller.transport(self.controller.config, record, mode)
            # Test transport also has to pass the same fixed-model, zero-cost envelope checks.
            if result.get('returned_model') not in (self.model, self.model.removesuffix(':free')):
                raise ModelError('UNEXPECTED_RETURNED_MODEL')
            meta = result.get('response_metadata') or {}
            cost = meta.get('provider_cost_usd')
            if cost is not None and (type(cost) not in (int, float) or cost != 0):
                raise ModelError('NONZERO_OR_INVALID_PROVIDER_COST', unavailable=True)
            result['response_metadata'] = dict(meta, execution_kind=self.controller.kind)
            self.audit.update(returned_model=result['returned_model'], usage=result.get('usage'),
                              estimated_cost_usd=cost, outcome='RESPONSE_RECEIVED')
            return result
        except ModelError as exc:
            self.audit.update(outcome=exc.code)
            # Never automatically probe again after transport/provider/safety failures.
            self.controller.stop(exc.code)
            raise
        except Exception:
            self.audit.update(outcome='LIVE_CLIENT_FAILURE')
            self.controller.stop('LIVE_CLIENT_FAILURE')
            raise ModelError('LIVE_CLIENT_FAILURE', unavailable=True) from None
        finally:
            self.audit['latency_seconds'] = round(time.perf_counter() - tick, 6)
