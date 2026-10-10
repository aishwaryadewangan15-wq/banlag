"""Approval-gated SerpApi collector. Writes sealed captures to the local store; never runs from the web server or tests.

    python -m banlag.collector plans/first_feasibility_probe.json --show        # print plan + SHA-256, no network
    python -m banlag.collector plans/first_feasibility_probe.json --dry-run     # print exact requests (key redacted), no network
    set BANLAG_SERPAPI_APPROVAL=<plan sha256>
    python -m banlag.collector plans/first_feasibility_probe.json --approve <plan sha256>

Two independent approval signals must both equal the SHA-256 of the exact plan file, so an edited plan is refused.
Hard cap: plan.max_calls (<= 3). No retries, no extra calls, no call-count changes. The API key comes only from the
SERPAPI_API_KEY environment variable and is never printed, logged, stored or written into a capture.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import sys
import time
import uuid
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from . import capture_store

ENDPOINT = 'https://serpapi.com/search.json'
HARD_CAP = 3
MAX_BYTES = 8 * 1024 * 1024
COLLECTOR_VERSION = '0.2.0'
ALLOWED_ENGINES = {'google', 'google_ai_overview', 'google_ai_mode'}
FORBIDDEN_PARAMS = {'api_key', 'async', 'output', 'json_restrictor', 'zero_trace'}


class Stop(RuntimeError):
    pass


def load_plan(path):
    raw = Path(path).read_bytes()
    plan = json.loads(raw.decode('utf-8'))
    if plan.get('schema') != 'banlag.plan.v1':
        raise Stop('unknown plan schema')
    if not 1 <= int(plan.get('max_calls', 0)) <= HARD_CAP or len(plan.get('calls', [])) > plan['max_calls']:
        raise Stop(f'plan must declare 1..{HARD_CAP} calls and list no more than max_calls')
    for c in plan['calls']:
        if c.get('engine') not in ALLOWED_ENGINES:
            raise Stop(f"engine {c.get('engine')!r} not allowed")
        if FORBIDDEN_PARAMS & set(c.get('params', {})):
            raise Stop('plan may not set ' + ', '.join(sorted(FORBIDDEN_PARAMS & set(c['params']))))
    return plan, hashlib.sha256(raw).hexdigest()


def _default_fetch(params, key):
    """One HTTPS GET. Returns (status, bytes). The URL (which contains the key) is never logged or raised."""
    req = Request(ENDPOINT + '?' + urlencode({**params, 'api_key': key}), headers={'User-Agent': 'BANLAG-collector/' + COLLECTOR_VERSION})
    try:
        with urlopen(req, timeout=45) as resp:
            return resp.status, resp.read(MAX_BYTES + 1)
    except HTTPError as e:
        return e.code, e.read(MAX_BYTES + 1)
    except (URLError, TimeoutError, OSError) as e:
        raise Stop('network failure: ' + type(e).__name__) from None


def _redact(raw, key):
    if key and key.encode('utf-8') in raw:
        return raw.replace(key.encode('utf-8'), b'[REDACTED]'), True
    return raw, False


def run(plan_path, approve, env=None, fetch=None, store=capture_store.STORE, key_path=capture_store.KEY_PATH, now=None, out=print):
    env = os.environ if env is None else env
    plan, plan_sha = load_plan(plan_path)
    if approve != plan_sha or env.get('BANLAG_SERPAPI_APPROVAL') != plan_sha:
        raise Stop('STOP: this exact plan has not been approved (need --approve <sha256> and BANLAG_SERPAPI_APPROVAL=<sha256>).')
    key = env.get('SERPAPI_API_KEY')
    if not key:
        raise Stop('STOP: SERPAPI_API_KEY is not set in the environment.')
    try:  # pre-flight: the sealing key must be usable and outside every synced folder BEFORE any billable call
        capture_store.load_key(key_path, create=True)
    except capture_store.UnsafeKeyLocation as ex:
        raise Stop('STOP: ' + str(ex)) from None
    fetch = fetch or _default_fetch
    now = now or (lambda: dt.datetime.now(dt.timezone.utc))
    run_id = 'run-' + now().strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:6]
    calls_made, results = 0, {}
    plan_summary = {k: plan.get(k) for k in ('purpose', 'case', 'ingredients')}
    for i, call in enumerate(plan['calls']):
        params = dict(call.get('params', {}), engine=call['engine'])
        if call.get('page_token_from'):
            parent = results.get(call['page_token_from'])
            ao = ((parent or {}).get('response') or {}).get('ai_overview') or {}
            if not ao.get('page_token') or ao.get('text_blocks'):
                out(f"skip {call['call_id']}: parent has {'inline text_blocks' if ao.get('text_blocks') else 'no page_token'}; no call made")
                continue
            params['page_token'] = ao['page_token']
        if calls_made >= plan['max_calls'] or calls_made >= HARD_CAP:
            raise Stop('hard call cap reached')
        calls_made += 1
        t0 = time.monotonic()
        status, raw = fetch(params, key)
        elapsed = round((time.monotonic() - t0) * 1000)
        truncated = len(raw) > MAX_BYTES
        raw, redacted = _redact(raw[:MAX_BYTES], key)
        response = None
        if status == 200 and not truncated:
            try:
                response = json.loads(raw.decode('utf-8'))
            except (UnicodeDecodeError, ValueError):
                response = None
        md = (response or {}).get('search_metadata') or {}
        record = {
            'capture_id': f"{run_id}-{call['call_id']}", 'run_id': run_id, 'call_id': call['call_id'], 'call_index': i,
            'role': call.get('role'), 'parent_call_id': call.get('page_token_from'),
            'request': {'endpoint': ENDPOINT, 'engine': call['engine'],
                        'params': {k: v for k, v in params.items() if k != 'api_key' and k != 'engine'}},
            'http_status': status, 'received_at': now().isoformat(timespec='seconds'), 'elapsed_ms': elapsed,
            'truncated': truncated, 'key_redacted_from_raw': redacted,
            'provider': {k: md.get(k) for k in ('id', 'created_at', 'processed_at', 'status', 'json_endpoint')},
            'provider_error': (response or {}).get('error'),
            'plan_sha256': plan_sha, 'plan': plan_summary, 'collector_version': COLLECTOR_VERSION,
        }
        path = capture_store.seal(record, raw, store=store, key_path=key_path)
        results[call['call_id']] = {'record': record, 'response': response}
        out(f"sealed {call['call_id']} http={status} search_id={md.get('id')} -> {Path(path).name}")
        provider_status = md.get('status')
        if status != 200 or response is None or response.get('error') or provider_status != 'Success':
            out(f"STOP after {call['call_id']}: http={status} provider_status={provider_status!r} error={str((response or {}).get('error'))[:120]!r}; "
                'no further calls (no retries).')
            break
    out(f'run {run_id}: {calls_made} billable call(s) attempted (cap {plan["max_calls"]}).')
    return run_id, calls_made


def main(argv=None):
    ap = argparse.ArgumentParser(description='BANLAG approval-gated SerpApi collector (<= 3 calls).')
    ap.add_argument('plan')
    ap.add_argument('--show', action='store_true', help='print the plan and its SHA-256; no network')
    ap.add_argument('--dry-run', action='store_true', help='print the exact requests (no key); no network')
    ap.add_argument('--approve', help='SHA-256 of the exact plan file the user approved')
    a = ap.parse_args(argv)
    try:
        plan, sha = load_plan(a.plan)
        if a.show or a.dry_run or not a.approve:
            print(json.dumps(plan, indent=1))
            print('PLAN SHA-256:', sha)
            if a.dry_run:
                for c in plan['calls']:
                    print('WOULD CALL', ENDPOINT, json.dumps(dict(c.get('params', {}), engine=c['engine'])),
                          '(page_token from ' + c['page_token_from'] + ')' if c.get('page_token_from') else '')
            if not a.approve:
                print('No --approve given: nothing was sent.')
            return 0
        run(a.plan, a.approve)
        return 0
    except Stop as e:
        print(str(e), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
