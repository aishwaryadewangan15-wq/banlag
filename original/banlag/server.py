"""Local-only, zero-dependency API and UI. Makes no outbound requests of any kind.

Hardening: binds 127.0.0.1; rejects foreign Host headers (DNS rebinding) and cross-site POSTs; JSON bodies only,
<= 2 MB and <= 64 levels deep; screenshots served only if listed in the corpus manifest and hash-identical; strict CSP.
Live SerpApi captures are made only by the separate approval-gated CLI (banlag.collector); this server only reads
the sealed store.
"""
import hashlib
import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from . import __version__
from .capture_store import STORE, run_sources
from .claims import _valid_index, reference_index_map
from .corpus import build_cases
from .engine import evaluate, evaluate_run
from .legal import match_formula, registry
from .public import CONTRACT, observe_answer, public

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / 'web'
SHOTS = ROOT / 'evidence' / 'screenshots'
TYPES = {'.html': 'text/html; charset=utf-8', '.css': 'text/css; charset=utf-8', '.js': 'text/javascript; charset=utf-8',
         '.svg': 'image/svg+xml', '.jpg': 'image/jpeg', '.json': 'application/json; charset=utf-8'}
STATIC = {'/': 'index.html', '/app.js': 'app.js', '/style.css': 'style.css', '/samples.js': 'samples.js'}
MAX_BODY = 2 * 1024 * 1024
MAX_DEPTH = 64
CSP = ("default-src 'self'; connect-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
       "object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'")


def _depth(obj, limit=MAX_DEPTH):
    stack = [(obj, 1)]
    while stack:
        cur, d = stack.pop()
        if d > limit:
            return False
        if isinstance(cur, dict):
            stack.extend((v, d + 1) for v in cur.values())
        elif isinstance(cur, list):
            stack.extend((v, d + 1) for v in cur)
    return True


def _shot_hashes():
    """Screenshot hashes from the VERIFIED corpus (anchored digest), not from the replaceable manifest; empty if integrity fails."""
    return build_cases()['corpus'].get('screenshots', {})


def _trim_case(c):
    def rec(r):
        if not r:
            return None
        return {k: r[k] for k in ('record_id', 'engine_label', 'gold_label', 'captured_at', 'current_use_strength', 'flags')}
    return {'id': c['entry']['id'], 'notice': c['entry']['notice'], 'composition': c['entry']['composition'], 'pib_item': c['entry']['pib_item'],
            'query_id': c['entry']['query_id'], 'in_family': c['in_family'], 'g1_locked': c['g1_locked'], 'g1_engine': c['g1_engine'],
            'g1_positive': c['g1_positive'], 'headline': c['headline'], 'contrast': (c['paired_prompt_contrast'] or {}).get('result'),
            'uses': {'A': rec(c['uses']['A']), 'B': rec(c['uses']['B'])}, 'status': rec(c['status']), 'ai_mode': rec(c['ai_mode'])}


PLANS = ROOT / 'plans'


def _chip(i, unique, dup_counts):
    """Source chip for one claim-side index: a duplicated or malformed index is disclosed, never resolved to one source."""
    if not _valid_index(i):
        return {'source': f'[{i!r}] malformed index — not linked', 'more': 0, 'unresolved': True}
    if i in dup_counts:
        return {'source': f'[{i}] ambiguous — {dup_counts[i]} references share this index', 'more': 0, 'unresolved': True}
    return {'source': f"[{i}] {(unique.get(i) or {}).get('source') or '?'}", 'more': 0}


def _answer_view(a, target=None):
    by_block = {}
    for c in a['analysis']['claims']:
        by_block.setdefault(c['block_id'], []).append({k: c.get(k) for k in ('id', 'text', 'types', 'cues', 'cue_kinds', 'use_binding', 'restriction')})
    unique, dup, _ = reference_index_map(a['references'])  # the engine's rule: no last-write-wins
    dup_counts = {i: sum(1 for r in a['references'] if isinstance(r, dict) and type(r.get('index')) is int and r['index'] == i) for i in dup}
    blocks = [dict(b, claims=by_block.get(b['id'], []),
                   chips=[_chip(i, unique, dup_counts) for i in (b.get('reference_indexes') if isinstance(b.get('reference_indexes'), list) else [])])
              for b in a['blocks']]
    return {'surface': a['surface'], 'status': a['status'], 'prereg_label': a['prereg_label'], 'current_use_strength': a['current_use_strength'],
            'citation_binding': a['citation_binding'], 'tier': a['tier'], 'search_id': a['search_id'], 'created_at': a['created_at'],
            'decision_trace': a['analysis']['decision_trace'], 'subject': a['analysis']['subject'], 'flags': a['analysis']['flags'],
            'blocks': blocks, 'source_cards': [], 'references': a['references'], 'citation_coherence': a['citation_coherence'],
            'tier2_hits': a['tier2_hits'], 'observations': observe_answer(a['blocks'], a['references'], target)}


def _evaluate_view(res):
    target = (res.get('formulation') or {}).get('entry') if isinstance(res.get('formulation'), dict) else None
    for a in res.get('answers') or []:
        if isinstance(a, dict) and isinstance(a.get('blocks'), list):
            a['observations'] = observe_answer(a['blocks'], a.get('references'), target)
    return res


def live_runs():
    out = []
    for run_id, (store_dir, calls) in run_sources().items():
        rec0 = calls[0]['record'] or {}
        view = {'run_id': run_id, 'case': (rec0.get('plan') or {}).get('case'), 'plan_sha256': rec0.get('plan_sha256'),
                'calls': [{'call_id': (c['record'] or {}).get('call_id'), 'engine': ((c['record'] or {}).get('request') or {}).get('engine'),
                           'origin': c['origin'], 'reasons': c['reasons'], 'http_status': (c['record'] or {}).get('http_status'),
                           'search_id': ((c['record'] or {}).get('provider') or {}).get('id'),
                           'provider_created_at': ((c['record'] or {}).get('provider') or {}).get('created_at'),
                           'raw_sha256': (c['record'] or {}).get('raw_sha256'),
                           'params': ((c['record'] or {}).get('request') or {}).get('params', {})} for c in calls]}
        try:
            ev = evaluate_run(run_id, store=store_dir)
        except (KeyError, ValueError) as ex:
            view['error'] = str(ex)[:200]
            out.append(view)
            continue
        view.update({k: ev.get(k) for k in ('origin', 'evidence_tier', 'verified_evidence_tier', 'tier_status', 'query', 'captured_at', 'organic_binding',
                                             'status_capture', 'publication_gate', 'release_status', 'safety_banner', 'organic')})
        view['provenance'] = {k: (ev.get('provenance') or {}).get(k) for k in ('statement', 'clock_check', 'linkage', 'live_verified')}
        view['notice'] = ((ev.get('formulation') or {}).get('entry') or {}).get('notice')
        target = (ev.get('formulation') or {}).get('entry')
        view['answers'] = [_answer_view(a, target) for a in ev.get('answers', []) if a['status'] == 'PRESENT']
        out.append(view)
    return out


def plans_view(runs):
    out = []
    for p in sorted(PLANS.glob('*.json')):
        raw = p.read_bytes()
        sha = hashlib.sha256(raw).hexdigest()
        out.append({'file': f'plans/{p.name}', 'sha256': sha, 'plan': json.loads(raw.decode('utf-8')),
                    'executed_runs': [r['run_id'] for r in runs if r.get('plan_sha256') == sha]})
    return out


def overview():
    r = build_cases()
    db = registry()
    runs = run_sources()
    return {'corpus': r['corpus'], 'g1': r['g1'], 'agreement': r['agreement'], 'disagreements': r['disagreements'],
            'benchmark': r['benchmark'], 'adversarial': r['adversarial'], 'notice_integrity': r['notice_integrity'], 'cases': [_trim_case(c) for c in r['cases']],
            'controls': [{k: e[k] for k in ('record_id', 'query', 'engine_label', 'subject')} for e in r['controls']],
            'legal_source': db['source'], 'legal_status': db['legal_status'],
            'live': {'sealed_runs': len(runs), 'plans': len(list(PLANS.glob('*.json')))}}


class Handler(BaseHTTPRequestHandler):
    server_version = 'BANLAG-local'
    sys_version = ''

    def log_message(self, fmt, *args):
        # Never log bodies, query strings or headers.
        print('LOCAL HTTP', self.client_address[0], self.command, urlparse(self.path).path, flush=True)

    def _headers(self, code, typ='application/json; charset=utf-8', length=None):
        self.send_response(code)
        self.send_header('Content-Type', typ)
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Cross-Origin-Resource-Policy', 'same-origin')
        self.send_header('Content-Security-Policy', CSP)
        if length is not None:
            self.send_header('Content-Length', str(length))
        self.end_headers()

    def _json(self, obj, code=200):
        obj = public(obj, getattr(self, '_route', None))  # the public-output contract (allowlist): every response, every route
        if isinstance(obj, dict) and code == 200:
            obj['public_contract'] = CONTRACT
        data = json.dumps(obj, ensure_ascii=False, default=str).encode('utf-8')
        self._headers(code, length=len(data))
        self.wfile.write(data)

    def _host_ok(self):
        host = (self.headers.get('Host') or '').lower()
        port = self.server.server_address[1]
        return host in (f'127.0.0.1:{port}', f'localhost:{port}')

    def _same_origin(self):
        port = self.server.server_address[1]
        origin = self.headers.get('Origin')
        if origin is not None and origin not in (f'http://127.0.0.1:{port}', f'http://localhost:{port}'):
            return False
        return (self.headers.get('Sec-Fetch-Site') or 'same-origin') in ('same-origin', 'none')

    def do_GET(self):
        if not self._host_ok():
            return self._json({'error': 'Host not allowed'}, 421)
        path = self._route = urlparse(self.path).path
        try:
            if path == '/api/registry':
                return self._json(registry())
            if path == '/api/status':
                sealed = sum(len(calls) for _, calls in run_sources().values())
                return self._json({'name': 'BANLAG', 'version': __version__, 'serpapi_requests_made': 0, 'capture_mode': 'LOCAL_ONLY',
                                   'live_serpapi_enabled': False, 'sealed_serpapi_calls_in_store': sealed,
                                   'note': 'serpapi_requests_made counts requests by THIS server (always 0). Sealed captures come only from the approval-gated CLI.'})
            if path == '/api/overview':
                return self._json(overview())
            m = re.fullmatch(r'/api/case/(F\d\d)', path)
            if m:
                case = next((c for c in build_cases()['cases'] if c['entry']['id'] == m.group(1)), None)
                if not case:
                    return self._json({'error': 'not found'}, 404)
                return self._json(dict(case, live_runs=[r for r in live_runs() if r.get('case') == m.group(1)]))
            if path == '/api/live':
                runs = live_runs()
                return self._json({'runs': runs, 'plans': plans_view(runs), 'store': str(STORE.relative_to(ROOT))})
            m = re.fullmatch(r'/evidence/screenshots/([A-Za-z0-9_]+\.jpg)', path)
            if m:
                name = m.group(1)
                expected = _shot_hashes().get(name)
                p = SHOTS / name
                if not expected or not p.is_file():
                    return self._json({'error': 'not found'}, 404)
                data = p.read_bytes()
                if hashlib.sha256(data).hexdigest().upper() != expected:
                    return self._json({'error': 'screenshot hash mismatch; refusing to serve'}, 409)
                self._headers(200, TYPES['.jpg'], len(data))
                return self.wfile.write(data)
            asset = STATIC.get(path)
            if not asset:
                return self._json({'error': 'not found'}, 404)
            p = ASSETS / asset
            if not p.exists():
                return self._json({'error': 'asset not found'}, 404)
            data = p.read_bytes()
            self._headers(200, TYPES.get(p.suffix, 'application/octet-stream'), len(data))
            self.wfile.write(data)
        except Exception:
            return self._json({'error': 'Failed safely; see server log for the path only.'}, 500)

    def do_POST(self):
        if not self._host_ok():
            return self._json({'error': 'Host not allowed'}, 421)
        if not self._same_origin():
            return self._json({'error': 'Cross-site request refused'}, 403)
        path = self._route = urlparse(self.path).path
        if path not in ('/api/evaluate', '/api/match'):
            return self._json({'error': 'not found'}, 404)
        try:
            n = int(self.headers.get('Content-Length', '0'))
            if n < 1 or n > MAX_BODY:
                self.close_connection = True
                if MAX_BODY < n <= 4 * MAX_BODY:  # drain so the client sees the 413 instead of a reset
                    left = n
                    while left > 0:
                        chunk = self.rfile.read(min(65536, left))
                        if not chunk:
                            break
                        left -= len(chunk)
                return self._json({'error': 'Request body must be JSON <= 2 MB.'}, 413)
            if not self.headers.get('Content-Type', '').split(';')[0].strip() == 'application/json':
                return self._json({'error': 'application/json required'}, 415)
            body = json.loads(self.rfile.read(n).decode('utf-8'))
            if not _depth(body):
                return self._json({'error': f'JSON nested deeper than {MAX_DEPTH} levels'}, 400)
            if not isinstance(body, dict):
                raise ValueError('Expected a JSON object.')
            res = match_formula(body.get('ingredients')) if path == '/api/match' else _evaluate_view(evaluate(body))
            return self._json(res)
        except (ValueError, TypeError, UnicodeDecodeError, RecursionError) as ex:
            return self._json({'error': str(ex)[:300]}, 400)
        except Exception:
            return self._json({'error': 'Failed safely; see server log for the path only.'}, 500)

    def _refuse(self):
        self._json({'error': 'method not allowed'}, 405)

    do_PUT = do_DELETE = do_PATCH = _refuse


def main():
    host, port = '127.0.0.1', 8765
    server = ThreadingHTTPServer((host, port), Handler)
    print(f'BANLAG LOCAL http://{host}:{port} (zero outbound requests; SerpApi only via approved CLI)', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
