"""Linux resource-isolated PDF extraction. No in-process fallback; not a security sandbox.

Only bounded bytes and a trusted parser callable enter the spawned Python process. The
parent accepts bounded JSON only after a successful exit; no pickle is read from the
worker. A private temporary result file avoids blocking on a half-written pipe frame.
"""
import hashlib
import json
import math
import multiprocessing
import os
import signal
import stat
import sys
import tempfile
import time
from pathlib import Path

from .pdf_ingestion import MAX_BYTES, MAX_PAGES, MAX_PAGE_CHARS, MAX_TOTAL_CHARS, compile_text, read_pdf
from .schema import parse_json

DEFAULT_LIMITS = dict(wall_seconds=8.0, cpu_seconds=4, memory_bytes=256 * 1024 * 1024,
                      output_bytes=16 * 1024 * 1024)
CPU_EXIT, MEMORY_EXIT, OUTPUT_EXIT, PARSER_EXIT = 71, 72, 73, 74


def validate_limits(limits):
    if set(limits) != set(DEFAULT_LIMITS):
        raise ValueError("Worker limits must contain wall_seconds, cpu_seconds, memory_bytes and output_bytes")
    if (isinstance(limits['wall_seconds'], bool) or not isinstance(limits['wall_seconds'], (float, int))
            or not math.isfinite(limits['wall_seconds']) or not 0 < limits['wall_seconds'] <= 60):
        raise ValueError("Wall deadline must be positive and at most 60 seconds")
    for name in ('cpu_seconds', 'memory_bytes', 'output_bytes'):
        if type(limits[name]) is not int or limits[name] <= 0:
            raise ValueError("Worker integer limits must be positive")
    if limits['memory_bytes'] > 1024 * 1024 * 1024 or limits['output_bytes'] > DEFAULT_LIMITS['output_bytes']:
        raise ValueError("Worker limits exceed supported bounds")
    return dict(limits)


def _entry(source, destination, limits, parser):
    """No untrusted parsing before these OS limits are installed."""
    import resource
    try:
        os.setsid()
        os.environ.clear()  # Do not expose inherited provider credentials to parser code.
        os.chdir(str(Path(source).parent))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        resource.setrlimit(resource.RLIMIT_AS, (limits['memory_bytes'],) * 2)
        resource.setrlimit(resource.RLIMIT_CPU, (limits['cpu_seconds'], limits['cpu_seconds'] + 1))
        resource.setrlimit(resource.RLIMIT_FSIZE, (limits['output_bytes'],) * 2)
        signal.signal(signal.SIGXCPU, lambda *args: os._exit(CPU_EXIT))
        signal.signal(signal.SIGXFSZ, lambda *args: os._exit(OUTPUT_EXIT))
        # Third-party errors must not put document strings or tracebacks in server logs.
        with open(os.devnull, 'wb') as sink:
            os.dup2(sink.fileno(), 1)
            os.dup2(sink.fileno(), 2)
        result = parser(source)
        encoded = json.dumps(result, ensure_ascii=True, allow_nan=False).encode('utf-8')
        if len(encoded) > limits['output_bytes']:
            os._exit(OUTPUT_EXIT)
        with open(destination, 'xb') as output:
            output.write(encoded)
            output.flush()
        os._exit(0)
    except MemoryError:
        os._exit(MEMORY_EXIT)
    except BaseException:
        os._exit(PARSER_EXIT)


def _empty(name, digest, code):
    return dict(schema_version='pdf-text-v1', name=name, document_id='sha256:' + digest if digest else None,
                file_sha256=digest, status='REJECTED', issues=[code], pages=[], text='', segments=[],
                text_sha256=hashlib.sha256(b'').hexdigest(), human_review_required=True, extractor=None,
                normalization='No source text accepted from a failed input or worker.',
                limits=dict(file_bytes=MAX_BYTES, pages=MAX_PAGES))


def _valid_result(doc, digest):
    """Validate the extraction envelope and all normalized source data before use."""
    try:
        if (not isinstance(doc, dict) or doc['schema_version'] != 'pdf-text-v1'
                or doc['file_sha256'] != digest or doc['document_id'] != 'sha256:' + digest
                or doc['human_review_required'] is not True
                or doc['status'] not in ('EXTRACTED', 'NEEDS_DOCUMENT_REVIEW', 'REJECTED')
                or not isinstance(doc['issues'], list) or not all(isinstance(x, str) for x in doc['issues'])
                or not isinstance(doc['pages'], list) or len(doc['pages']) > MAX_PAGES):
            return False
        if doc['status'] == 'REJECTED':
            return not doc['pages'] and doc['text'] == '' and doc['segments'] == []
        if not doc['pages']:
            return False
        expected_status = 'NEEDS_DOCUMENT_REVIEW' if doc['issues'] or any(p.get('issues') for p in doc['pages']) else 'EXTRACTED'
        if doc['status'] != expected_status:
            return False
        total = 0
        for number, page in enumerate(doc['pages'], 1):
            if (type(page['page_number']) is not int or page['page_number'] != number
                    or not isinstance(page['text'], str) or len(page['text']) > MAX_PAGE_CHARS
                    or page['status'] not in ('EXTRACTED', 'NEEDS_DOCUMENT_REVIEW')
                    or not isinstance(page['issues'], list) or not all(isinstance(x,str) for x in page['issues'])
                    or not isinstance(page['order_check'], str)):
                return False
            layout = page['alternate_layout_text']
            if layout is not None and (not isinstance(layout, str) or len(layout) > MAX_PAGE_CHARS):
                return False
            if hashlib.sha256(page['text'].encode('utf-8')).hexdigest() != page['text_sha256']:
                return False
            if page['status'] != ('NEEDS_DOCUMENT_REVIEW' if page['issues'] else 'EXTRACTED'):
                return False
            total += len(page['text'])
        if total > MAX_TOTAL_CHARS:
            return False
        text, segments = compile_text(doc['pages'])
        return (doc['text'] == text and doc['segments'] == segments
                and doc['text_sha256'] == hashlib.sha256(text.encode('utf-8')).hexdigest())
    except (KeyError, TypeError, AttributeError, UnicodeError, RecursionError):
        return False


def read_pdf_isolated(path, *, limits=None, _parser=None):
    """Review entry point. `_parser` is a trusted Python test seam, never HTTP input."""
    limits = validate_limits(DEFAULT_LIMITS if limits is None else limits)
    path = Path(path)
    digest = None
    trace = dict(isolation='LINUX_SPAWN_RESOURCE_LIMITS_NOT_SECURITY_SANDBOX', limits=limits,
                 pid=None, exit_code=None, reaped=True, elapsed_seconds=0.0)
    def failed(code):
        doc = _empty(path.name, digest, code)
        doc['worker'] = dict(trace, status=code)
        return doc
    if not sys.platform.startswith('linux'):
        return failed('PDF_WORKER_UNSUPPORTED_PLATFORM')
    try:
        # Reject special files before read; O_NONBLOCK prevents FIFO open hangs after a race.
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
        with os.fdopen(fd, 'rb') as source:
            info = os.fstat(source.fileno())
            if not stat.S_ISREG(info.st_mode):
                return failed('FILE_UNAVAILABLE')
            if info.st_size > MAX_BYTES:
                return failed('FILE_SIZE_LIMIT')
            data = source.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            return failed('FILE_SIZE_LIMIT')
        digest = hashlib.sha256(data).hexdigest()
    except OSError:
        return failed('FILE_UNAVAILABLE')
    if path.suffix.lower() != '.pdf' or not data.startswith(b'%PDF-'):
        return failed('UNSUPPORTED_FILE')
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix='tds-pdf-worker-') as tmp:
        source, destination = Path(tmp) / 'source.pdf', Path(tmp) / 'result.json'
        source.write_bytes(data)
        proc = multiprocessing.get_context('spawn').Process(
            target=_entry, args=(str(source), str(destination), limits, _parser or read_pdf), daemon=True)
        timed_out = False
        try:
            proc.start()
            trace['pid'] = proc.pid
            proc.join(max(0, limits['wall_seconds'] - (time.monotonic() - started)))
            timed_out = proc.is_alive()
            if timed_out:
                # Kill any descendants in the worker's own session, then reap the worker.
                try:
                    if os.getpgid(proc.pid) == proc.pid:
                        os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                if proc.is_alive():
                    proc.kill()
                proc.join()
            trace.update(exit_code=proc.exitcode, reaped=proc.exitcode is not None,
                         elapsed_seconds=round(time.monotonic() - started, 6))
            if timed_out:
                return failed('PDF_WORKER_WALL_TIMEOUT')
            if proc.exitcode != 0:
                code = {CPU_EXIT:'PDF_WORKER_CPU_LIMIT', MEMORY_EXIT:'PDF_WORKER_MEMORY_LIMIT',
                        OUTPUT_EXIT:'PDF_WORKER_OUTPUT_LIMIT', PARSER_EXIT:'PDF_WORKER_PARSER_FAILURE',
                        -signal.SIGXCPU:'PDF_WORKER_CPU_LIMIT', -signal.SIGKILL:'PDF_WORKER_RESOURCE_TERMINATED'}.get(
                            proc.exitcode, 'PDF_WORKER_CRASH')
                return failed(code)
            try:
                with destination.open('rb') as output:
                    encoded = output.read(limits['output_bytes'] + 1)
                if len(encoded) > limits['output_bytes']:
                    return failed('PDF_WORKER_OUTPUT_LIMIT')
                doc = parse_json(encoded.decode('utf-8'))
                if not _valid_result(doc, digest):
                    return failed('PDF_WORKER_INVALID_RESULT')
            except (OSError, ValueError, UnicodeError, RecursionError):
                return failed('PDF_WORKER_INVALID_RESULT')
            doc['name'] = path.name
            doc['worker'] = dict(trace, status='COMPLETED')
            return doc
        except (OSError, RuntimeError):
            return failed('PDF_WORKER_START_FAILURE')
        finally:
            if proc.pid is not None:
                if proc.is_alive():
                    proc.kill()
                    proc.join()
                proc.close()
