"""BANLAG - One Missing Fact: local, offline, keyless demo server (Python stdlib only).

    python -I -B app.py [--port 8765]

Binds 127.0.0.1 only. Serves three static files from web/ and a small JSON API. No outbound requests,
no third-party assets, no telemetry. Request bodies and raw request paths are never logged.
Evidence trust: one fail-closed decision (adapters.archived_aio.decide) made against CODE-pinned anchors is
consumed by every evidence response, comparison and corruption demo. Every JSON response passes the
output gate (adapters.sanitize.gate).
"""
import copy
import json
import os
import subprocess
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from adapters import archived_aio as A  # noqa: E402
from adapters import sanitize as S  # noqa: E402
from core import facts as F  # noqa: E402
from core import minimax as M  # noqa: E402
from core import register as R  # noqa: E402
from core import witness as W  # noqa: E402

HOST = '127.0.0.1'
MAX_BODY = 65536
STATIC = {'/': ('index.html', 'text/html; charset=utf-8'),
          '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
          '/style.css': ('style.css', 'text/css; charset=utf-8')}
ROUTES = {('GET', '/'): 'index', ('GET', '/app.js'): 'app.js', ('GET', '/style.css'): 'style.css',
          ('GET', '/api/evidence'): 'evidence', ('POST', '/api/solve'): 'solve', ('POST', '/api/verify'): 'verify',
          ('POST', '/api/tamper'): 'tamper', ('POST', '/api/scope'): 'scope'}
CSP = ("default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'none'; "
       "font-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
ORIGINAL_RUN_DIR = os.environ.get('OMF_ORIGINAL_RUN_DIR', os.path.join(HERE, 'NO_RAW_ARCHIVE_CONFIGURED'))
VERIFIER = os.path.join(HERE, 'verifier', 'independent.py')
REGISTRY_PATH = os.path.join(HERE, 'data', 'registry_scope.json')
DEFAULT_BLOCK = '/ai_overview/text_blocks/1'


class BadJSON(ValueError):
    pass


def _no_dupes(pairs):
    keys = [k for k, _ in pairs]
    if len(keys) != len(set(keys)):
        raise BadJSON('duplicate key')
    return dict(pairs)


class State:
    def __init__(self):
        self.register = R.load(REGISTRY_PATH)   # raises NONCANONICAL_REGISTER on a non-canonical register
        try:
            with open(os.path.join(HERE, 'data', 'aio_f08_derivative.json'), 'rb') as f:
                served = A.parse_json(f.read())
        except (OSError, A.EvidenceError):
            served = {}
        self.expected, self.raw_problem = A.load_verified_raw(ORIGINAL_RUN_DIR, self.register) \
            if os.path.isdir(ORIGINAL_RUN_DIR) else (None, 'RAW_ABSENT')
        self.decision, proj = A.decide(served, self.expected, self.raw_problem)
        self.projection = proj if proj is not None else A.reproject({})
        self.view = A.public_view(self.projection, self.decision)

    def evidence(self):
        reg = self.register
        return {
            'evidence_state': self.decision['state'], 'evidence_authentic': self.decision['authentic'],
            'raw_check': 'RAW_REVERIFIED' if self.expected is not None else self.raw_problem,
            'derivative': self.view, 'default_block': DEFAULT_BLOCK,
            'scope': A.scope_analysis(self.view, reg, DEFAULT_BLOCK),
            'register': {'register_id': reg['register_id'], 'digest': reg['digest'], 'scope_note': reg['scope_note'],
                         'official_source': reg['official_source'],
                         'cases': [{k: c[k] for k in ('id', 'notice', 'composition', 'ingredients')} for c in reg['cases']]},
            'caveat': W.CAVEAT,
        }

    def scope(self, pointer, corrupt):
        if corrupt in CORRUPTIONS:
            val, note = CORRUPTIONS[corrupt]
            mutated = A.corrupt_block(self.projection, pointer, val, delete=val is None)
            decision, proj = A.decide(mutated, self.expected, self.raw_problem)
            view = A.public_view(proj, decision)
        else:
            view, note = self.view, None
        blk = next((b for b in view['blocks'] if b.get('pointer') == pointer), None)
        return {'scope': A.scope_analysis(view, self.register, pointer), 'block': blk, 'corruption': note,
                'evidence_state': view['trust']['state']}


def run_verifier(witness, expected_facts, mode):
    """Independent verifier in a SEPARATE isolated Python process (no shared imports or memory)."""
    args = [sys.executable, '-I', '-B', VERIFIER, '--registry', REGISTRY_PATH, '--mode',
            mode if mode in ('strict', 'tie_valid') else 'strict']
    if expected_facts is not None:
        args += ['--expect-facts', json.dumps(expected_facts)]
    t0 = time.monotonic()
    p = subprocess.run(args, input=json.dumps(witness).encode('utf-8'), capture_output=True, timeout=15,
                       cwd=os.path.dirname(VERIFIER))
    try:
        out = json.loads(p.stdout.decode('utf-8'))
    except ValueError:
        out = {'verdict': 'FAIL', 'reason': 'verifier produced no verdict'}
    out['process'] = {'isolated_subprocess': True, 'exit_code': p.returncode,
                      'elapsed_ms': round((time.monotonic() - t0) * 1000)}
    return out


def tamper(state, witness, kind):
    """Adversarial edits for the demo. Every one is re-sealed (fresh digest) unless noted."""
    w = copy.deepcopy(witness)
    if kind == 'swap_question':
        cands = [c for c in state.register['cases'] if c['id'] in w.get('candidate_ids', [])]
        s = M.Solver(cands)
        C = frozenset(c['id'] for c in cands)
        alts = [(a, y, n) for a, y, n in s._questions(C) if a != w.get('question')]
        if alts:
            a, y, n = alts[0]
            w.update(question=a, partition={'yes': sorted(y), 'no': sorted(n)})
            return W.seal(w), f'question replaced by {a!r} (a real split) with matching partitions; digest re-sealed'
        others = sorted({i for c in state.register['cases'] for i in c['ingredients']} - {w.get('question')}
                        - {f['term'] for f in w.get('facts', {}).get('present', [])})
        if not w.get('question') or not others:
            return None, 'no question to tamper with in this state'
        w['question'] = others[0]
        return W.seal(w), f'question replaced by {others[0]!r} (it does not split these candidates); digest re-sealed'
    if kind == 'inflate_depth' and isinstance(w.get('worst_case_depth'), int):
        w['worst_case_depth'] += 1
        return W.seal(w), 'claimed depth increased by one and re-sealed'
    if kind == 'drop_fact' and w.get('facts', {}).get('present'):
        dropped = w['facts']['present'].pop()
        return W.seal(w), f'present fact {dropped["term"]!r} removed and re-sealed'
    if kind == 'edit_unsealed':
        w['candidate_ids'] = list(reversed(w.get('candidate_ids', [])))
        return w, 'candidate list edited without re-sealing'
    return None, 'tamper kind not applicable to this witness'


CORRUPTIONS = {'swap': ([5, 7], 'indexes swapped to other valid references [5,7]'),
               'out_of_range': ([99], 'index 99 does not exist'),
               'negative': ([-1], 'negative index'),
               'nested': ([[1, 2]], 'nested array'),
               'remove': (None, 'reference_indexes removed')}


class Handler(BaseHTTPRequestHandler):
    server_version = 'OMF/1.1'
    sys_version = ''
    state = None

    def log_message(self, fmt, *args):  # never log bodies, raw paths or exception text
        pass

    def log_request(self, code='-', size='-'):
        route = ROUTES.get((self.command, self.path.split('?')[0]), 'other')
        sys.stderr.write(f'{time.strftime("%H:%M:%S")} {self.command if self.command in ("GET", "POST", "HEAD") else "OTHER"} '
                         f'route={route} {code}\n')

    def log_error(self, fmt, *args):
        sys.stderr.write(f'{time.strftime("%H:%M:%S")} request error (details withheld)\n')

    def _host_ok(self):
        port = self.server.server_address[1]
        return self.headers.get('Host') in (f'127.0.0.1:{port}', f'localhost:{port}')

    def _send(self, code, body, ctype='application/json; charset=utf-8'):
        if isinstance(body, (dict, list)):
            body, _ = S.gate(body)
            body = json.dumps(body, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Content-Security-Policy', CSP)
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Cross-Origin-Resource-Policy', 'same-origin')
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(body)

    def do_GET(self):
        if not self._host_ok():
            return self._send(421, {'error': 'HOST_NOT_ALLOWED'})
        path = self.path.split('?')[0]
        if path in STATIC:
            name, ctype = STATIC[path]
            with open(os.path.join(HERE, 'web', name), 'rb') as f:
                return self._send(200, f.read(), ctype)
        if path == '/api/evidence':
            return self._send(200, self.state.evidence())
        return self._send(404, {'error': 'NOT_FOUND'})

    def do_POST(self):
        if not self._host_ok():
            return self._send(421, {'error': 'HOST_NOT_ALLOWED'})
        port = self.server.server_address[1]
        origin = self.headers.get('Origin')
        if origin is not None and origin not in (f'http://127.0.0.1:{port}', f'http://localhost:{port}'):
            return self._send(403, {'error': 'ORIGIN_NOT_ALLOWED'})
        if (self.headers.get('Content-Type') or '').split(';')[0].strip() != 'application/json':
            return self._send(415, {'error': 'JSON_ONLY'})
        try:
            n = int(self.headers.get('Content-Length', '-1'))
        except ValueError:
            n = -1
        if n < 0 or n > MAX_BODY:
            return self._send(413, {'error': 'BODY_TOO_LARGE_OR_MISSING_LENGTH'})
        try:
            body = json.loads(self.rfile.read(n).decode('utf-8'), object_pairs_hook=_no_dupes)
        except BadJSON:
            return self._send(400, {'error': 'DUPLICATE_JSON_KEY'})
        except (ValueError, RecursionError, UnicodeDecodeError):
            return self._send(400, {'error': 'MALFORMED_JSON'})
        if not isinstance(body, dict):
            return self._send(400, {'error': 'OBJECT_REQUIRED'})
        path = self.path.split('?')[0]
        try:
            if path == '/api/solve':
                return self._send(200, W.run(self.state.register, body))
            if path == '/api/verify':
                return self._send(200, run_verifier(body.get('witness'), body.get('expected_facts'),
                                                    body.get('mode', 'strict')))
            if path == '/api/tamper':
                w, note = tamper(self.state, body.get('witness') or {}, body.get('kind'))
                return self._send(200, {'witness': w, 'note': note})
            if path == '/api/scope':
                ptr = body.get('pointer')
                if not isinstance(ptr, str) or not A.POINTER.match(ptr):
                    return self._send(400, {'error': 'INVALID_REQUEST'})
                return self._send(200, self.state.scope(ptr, body.get('corrupt')))
        except F.FactError as e:
            return self._send(400, {'error': e.code, 'detail': e.detail})
        except subprocess.TimeoutExpired:
            return self._send(504, {'error': 'VERIFIER_TIMEOUT'})
        except (TypeError, KeyError, AttributeError, ValueError):
            return self._send(400, {'error': 'INVALID_REQUEST'})
        return self._send(404, {'error': 'NOT_FOUND'})

    def do_HEAD(self):
        return self.do_GET()


def make_server(port=8765):
    Handler.state = State()
    srv = ThreadingHTTPServer((HOST, port), Handler)
    srv.daemon_threads = True
    return srv


def main(argv):
    port = 8765
    if '--port' in argv:
        port = int(argv[argv.index('--port') + 1])
    t0 = time.monotonic()
    srv = make_server(port)
    st = Handler.state
    print(f'One Missing Fact on http://{HOST}:{srv.server_address[1]}/  (evidence: {st.decision["state"]}; '
          f'authentic={st.decision["authentic"]}; register {st.register["digest"][:12]}; pid {os.getpid()}; '
          f'startup {round((time.monotonic() - t0) * 1000)} ms)', flush=True)
    print('Ctrl+C to stop. Offline; bound to 127.0.0.1 only.', flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()


if __name__ == '__main__':
    main(sys.argv)
