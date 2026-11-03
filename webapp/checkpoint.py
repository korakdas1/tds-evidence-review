"""Optional, reviewer-held history receipt; not a signature or legal attestation."""
import hashlib
import os
import re
import sqlite3
from pathlib import Path

from src.schema import parse_json
from .service import ReviewService
from .store import Store, canonical, now

MAX_CHECKPOINT_BYTES = 1024 * 1024


class CheckpointError(ValueError):
    pass


class ReadSnapshot(Store):
    """Reuse read methods against one read-only SQLite snapshot, without initializing it."""
    def __init__(self, data_dir):
        self.data_dir = Path(data_dir).resolve()
        self.documents_dir = self.data_dir / 'documents'
        self.db_path = self.data_dir / 'review.sqlite3'
        if self.db_path.is_symlink() or not self.db_path.is_file():
            raise CheckpointError('A regular existing review database is required')
        self.db = sqlite3.connect(self.db_path.as_uri() + '?mode=ro', uri=True, timeout=10)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA query_only=ON')
        self.db.execute('BEGIN')

    def connect(self):
        # closing() in Store readers must not close the shared transaction.
        class Borrowed:
            def execute(_, *args):
                return self.db.execute(*args)
            def close(_):
                pass
        return Borrowed()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.db.close()


def _state(store, case_id):
    case = store.case(case_id)
    runs = store.runs(case_id, include_report=True)
    events = store.events(case_id)
    if not case or not runs or not events:
        raise CheckpointError('Case has no complete history')
    service = ReviewService(store)
    for run in runs:
        if service.assess(case, run, events)['status'] != 'VERIFIED':
            raise CheckpointError('Case, report, history or documents failed verification')
    return events, runs


def create_checkpoint(data_dir, case_id):
    with ReadSnapshot(data_dir) as store:
        events, runs = _state(store, case_id)
        body = dict(schema='tds-external-checkpoint-v1', case_id=case_id,
                    created_at=now(), event_count=len(events), history_head=events[-1]['hash'],
                    runs=[dict(id=r['id'], report_sha256=r['report_sha256'],
                               context_sha256=r['context_sha256']) for r in runs])
    if len(canonical(body).encode()) > MAX_CHECKPOINT_BYTES - 200:
        raise CheckpointError('Checkpoint exceeds size limit')
    return dict(body=body, sha256=hashlib.sha256(canonical(body).encode()).hexdigest())


def _require(condition):
    if not condition:
        raise ValueError("Invalid checkpoint")


def _validate(receipt):
    try:
        body = receipt['body']
        _require(set(receipt) == {'body', 'sha256'})
        _require(set(body) == {'schema', 'case_id', 'created_at', 'event_count', 'history_head', 'runs'})
        _require(body['schema'] == 'tds-external-checkpoint-v1')
        _require(isinstance(body['case_id'], str) and re.fullmatch(r'[0-9a-f]{32}', body['case_id']))
        _require(type(body['event_count']) is int and body['event_count'] > 0)
        _require(isinstance(body['created_at'], str))
        _require(isinstance(body['history_head'], str) and re.fullmatch(r'[0-9a-f]{64}', body['history_head']))
        _require(isinstance(body['runs'], list) and body['runs'])
        ids = set()
        for r in body['runs']:
            _require(set(r) == {'id', 'report_sha256', 'context_sha256'})
            _require(isinstance(r['id'], str) and r['id'] not in ids)
            ids.add(r['id'])
            for k in ('report_sha256', 'context_sha256'):
                _require(isinstance(r[k], str) and re.fullmatch(r'[0-9a-f]{64}', r[k]))
        _require(receipt['sha256'] == hashlib.sha256(canonical(body).encode()).hexdigest())
    except (AssertionError, KeyError, TypeError, ValueError):
        raise CheckpointError('Invalid checkpoint format or checksum') from None
    return body


def verify_checkpoint(data_dir, receipt):
    body = _validate(receipt)
    with ReadSnapshot(data_dir) as store:
        events, runs = _state(store, body['case_id'])
        count = body['event_count']
        if len(events) < count or events[count - 1]['hash'] != body['history_head']:
            raise CheckpointError('History differs from the externally held checkpoint')
        current = {r['id']: r for r in runs}
        for held in body['runs']:
            if held['id'] not in current or any(current[held['id']][k] != held[k] for k in held):
                raise CheckpointError('Report/context differs from the externally held checkpoint')
        return dict(status='MATCHES_EXTERNAL_CHECKPOINT', anchored_events=count,
                    later_events=len(events) - count, anchored_runs=len(body['runs']),
                    limitation='Only the held prefix is anchored. No authenticated reviewer, trusted timestamp, '
                               'legal approval or protection if the external copy is replaced.')


def write_checkpoint(path, data_dir, receipt):
    _validate(receipt)
    path = Path(path).absolute()
    # Keeping the receipt with mutable application data defeats its intended purpose.
    if Path(data_dir).resolve() in (path.resolve(), *path.resolve().parents):
        raise CheckpointError('Keep the checkpoint outside the application data directory')
    data = (canonical(receipt) + '\n').encode()
    if len(data) > MAX_CHECKPOINT_BYTES:
        raise CheckpointError('Checkpoint exceeds size limit')
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'wb') as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())


def read_checkpoint(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise CheckpointError('Checkpoint must be a regular file')
    with path.open('rb') as f:
        data = f.read(MAX_CHECKPOINT_BYTES + 1)
    if len(data) > MAX_CHECKPOINT_BYTES:
        raise CheckpointError('Checkpoint exceeds size limit')
    try:
        receipt = parse_json(data.decode('utf-8'))
    except (ValueError, TypeError, RecursionError):
        raise CheckpointError('Checkpoint is not valid JSON') from None
    _validate(receipt)
    return receipt
