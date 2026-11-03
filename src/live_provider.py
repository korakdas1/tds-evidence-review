"""Bounded, one-request free-model transport. Does not load environment credentials."""
import json
import multiprocessing
import time
import urllib.error
import urllib.request

from .extraction import DIRECT_PROMPT, EXTRACTION_PROMPT, ModelError, NoRedirect
from .schema import parse_json, transaction_input

ENDPOINT = 'https://openrouter.ai/api/v1/chat/completions'
MAX_RESPONSE = 1024 * 1024
MAX_INPUT = 100000


def request_once(config, record, mode):
    """Only called in a bounded worker. No redirects, proxy inheritance, retries or fallback."""
    data = transaction_input(record)
    if len(json.dumps(data).encode()) > MAX_INPUT:
        raise ModelError('LIVE_INPUT_LIMIT')
    payload = dict(model=config['model'], temperature=0, max_tokens=1400,
                   provider=dict(allow_fallbacks=False, require_parameters=True,
                                 max_price=dict(prompt=0, completion=0)),
                   response_format=dict(type='json_object'),
                   messages=[dict(role='system', content=EXTRACTION_PROMPT if mode == 'hybrid' else DIRECT_PROMPT),
                             dict(role='user', content=json.dumps(data, ensure_ascii=False))])
    request = urllib.request.Request(ENDPOINT, data=json.dumps(payload).encode(),
        headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + config['api_key']}, method='POST')
    try:
        with urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect()).open(
                request, timeout=config['timeout_seconds']) as response:
            raw = response.read(MAX_RESPONSE + 1)
        if len(raw) > MAX_RESPONSE:
            raise ModelError('RESPONSE_TOO_LARGE')
        response = parse_json(raw.decode('utf-8'))
        if 'error' in response:
            raise ModelError('PROVIDER_ERROR', unavailable=True)
        choice = response['choices'][0]
        message = choice['message']
        if message.get('refusal'):
            raise ModelError('MODEL_REFUSAL')
        if choice.get('finish_reason') not in ('stop', 'end_turn'):
            raise ModelError('INCOMPLETE_MODEL_OUTPUT')
        raw = message['content']
        model = response.get('model')
        if not isinstance(raw, str) or not isinstance(model, str):
            raise ModelError('INVALID_PROVIDER_RESPONSE')
        # Some providers omit the free suffix in the response's canonical model ID.
        if model not in (config['model'], config['model'].removesuffix(':free')):
            raise ModelError('UNEXPECTED_RETURNED_MODEL')
        usage = response.get('usage') or {}
        cost = usage.get('cost')
        if cost is not None and (type(cost) not in (int, float) or cost != 0):
            raise ModelError('NONZERO_OR_INVALID_PROVIDER_COST', unavailable=True)
        return dict(raw_output=raw.replace(config['api_key'], '[REDACTED_API_KEY]'),
                    returned_model=model,
                    response_metadata=dict(finish_reason=choice.get('finish_reason'),
                                           execution_kind='LIVE', provider_cost_usd=cost),
                    usage={k: v for k, v in usage.items() if k in ('prompt_tokens', 'completion_tokens', 'total_tokens')
                           and type(v) is int and v >= 0})
    except urllib.error.HTTPError as exc:
        raise ModelError('HTTP_' + str(exc.code), unavailable=True) from None
    except ModelError:
        raise
    except (urllib.error.URLError, TimeoutError, OSError):
        raise ModelError('NETWORK_OR_TIMEOUT', unavailable=True) from None
    except Exception:
        raise ModelError('INVALID_PROVIDER_RESPONSE') from None


def _entry(pipe, config, record, mode, transport):
    try:
        result = dict(ok=True, response=transport(config, record, mode))
    except ModelError as exc:
        result = dict(ok=False, code=exc.code, unavailable=exc.unavailable)
    except BaseException:
        result = dict(ok=False, code='LIVE_WORKER_FAILURE', unavailable=True)
    try:
        raw = json.dumps(result, allow_nan=False).encode()
        if len(raw) > MAX_RESPONSE:
            raw = b'{"ok":false,"code":"RESPONSE_TOO_LARGE","unavailable":true}'
        pipe.send_bytes(raw)
    finally:
        pipe.close()


def isolated_request(config, record, mode, _transport=request_once):
    """Enforce a total wall deadline, even on slow-trickle HTTP responses; reap the child."""
    context = multiprocessing.get_context('spawn')
    parent, child = context.Pipe(duplex=False)
    worker = context.Process(target=_entry, args=(child, config, record, mode, _transport), daemon=True)
    started = time.monotonic()
    try:
        worker.start()
        child.close()
        if not parent.poll(config['timeout_seconds']):
            raise ModelError('LIVE_WALL_TIMEOUT', unavailable=True)
        # One framed, bounded message; only trusted Python serializes this output.
        data = parse_json(parent.recv_bytes(MAX_RESPONSE).decode())
        remaining = max(0, config['timeout_seconds'] - (time.monotonic() - started))
        worker.join(remaining)
        if worker.is_alive():
            raise ModelError('LIVE_WALL_TIMEOUT', unavailable=True)
        if worker.exitcode != 0:
            raise ModelError('LIVE_WORKER_FAILURE', unavailable=True)
        if not data['ok']:
            raise ModelError(data['code'], unavailable=data['unavailable'])
        return data['response']
    except ModelError:
        raise
    except Exception:
        raise ModelError('LIVE_WORKER_FAILURE', unavailable=True) from None
    finally:
        child.close()
        parent.close()
        if worker.pid is not None:
            if worker.is_alive():
                worker.kill()
            worker.join()
            worker.close()
