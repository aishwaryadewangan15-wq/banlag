"""Build a read-only static replay of the BANLAG workbench (for GitHub Pages).

    python scripts/build_static_demo.py [--out _site]

It starts the normal local server in-process on a free port, and saves every GET response the UI uses as JSON. It also
pre-renders POST responses for the built-in hostile samples and for exact-match checks of the ten notified sets and
close variants. Then it copies the web UI next to them with relative paths. The web UI switches to replay mode when
static-config.js sets window.BANLAG_STATIC = true. Nothing is computed in the browser, and no request leaves the page.
Requires Node.js to read the sample payloads from web/samples.js (exactly as the browser serialises them).
"""
import argparse
import itertools
import json
import shutil
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from banlag.legal import norm, registry  # noqa: E402
from banlag.server import Handler  # noqa: E402

_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # never route the loopback server through a proxy
DEFAULT_UI_INPUT = ['dicyclomine', 'paracetamol']  # the value pre-filled in the matcher box (web/index.html)


def _start():
    srv = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    Handler.log_message = lambda *a, **k: None
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f'http://127.0.0.1:{srv.server_address[1]}'


def _req(base, path, body=None):
    data = body.encode('utf-8') if isinstance(body, str) else None
    req = urllib.request.Request(base + path, data=data, method='POST' if data is not None else 'GET',
                                 headers={'Content-Type': 'application/json'} if data is not None else {})
    try:
        with _OPENER.open(req, timeout=60) as r:
            return r.status, json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode('utf-8'))


def _sample_bodies():
    node = shutil.which('node')
    if not node:
        raise SystemExit('Node.js is required to read web/samples.js')
    prog = ("global.window={};require(process.argv[1]);"
            "console.log(JSON.stringify(window.BANLAG_SAMPLES.map(s=>JSON.stringify(s.payload))));")
    out = subprocess.run([node, '-e', prog, str(ROOT / 'web' / 'samples.js')], capture_output=True, text=True, check=True, timeout=60)
    return json.loads(out.stdout)


def _match_inputs():
    db = registry()
    sets = {tuple(DEFAULT_UI_INPUT)}
    others = sorted(db['other_actives'])
    for e in db['entries']:
        ing = e['ingredients']
        sets.add(tuple(ing))
        if len(ing) > 1:
            sets.update(itertools.combinations(ing, len(ing) - 1))
        for extra in others:
            sets.add(tuple(ing) + (extra,))
    # every one-ingredient superset across notices (e.g. F08 + chlordiazepoxide = F09)
    all_ings = sorted({i for e in db['entries'] for i in e['ingredients']})
    for e in db['entries']:
        for extra in all_ings:
            if extra not in e['ingredients']:
                sets.add(tuple(e['ingredients']) + (extra,))
    return sorted(sets)


def build(out):
    out = Path(out)
    if out.exists():
        shutil.rmtree(out)
    (out / 'api').mkdir(parents=True)
    srv, base = _start()
    try:
        index = {}
        status, overview = _req(base, '/api/overview')
        assert status == 200, overview
        gets = ['/api/overview', '/api/registry', '/api/status', '/api/live'] + [f"/api/case/{c['id']}" for c in overview['cases']]
        for path in gets:
            status, data = _req(base, path)
            if status != 200:
                raise SystemExit(f'{path} returned {status}: {data}')
            (out / 'api' / (path[len('/api/'):].replace('/', '_') + '.json')).write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        n = 0
        for body in _sample_bodies():
            status, data = _req(base, '/api/evaluate', body)
            data['__status'] = status
            name = f'post_evaluate_{n}.json'
            (out / 'api' / name).write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
            index['evaluate:' + body] = name
            n += 1
        for i, names in enumerate(_match_inputs()):
            status, data = _req(base, '/api/match', json.dumps({'ingredients': list(names)}))
            data['__status'] = status
            name = f'post_match_{i}.json'
            (out / 'api' / name).write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
            index['match:' + '|'.join(sorted(norm(x) for x in names))] = name
        (out / 'api' / '_post_index.json').write_text(json.dumps(index, ensure_ascii=False, sort_keys=True), encoding='utf-8')
    finally:
        srv.shutdown()

    web = ROOT / 'web'
    for f in ('app.js', 'style.css', 'samples.js'):
        shutil.copy2(web / f, out / f)
    html = (web / 'index.html').read_text(encoding='utf-8')
    for a in ('style.css', 'samples.js', 'app.js'):
        html = html.replace(f'"/{a}"', f'"{a}"')
    html = html.replace('<script src="samples.js" defer></script>', '<script src="static-config.js"></script>\n<script src="samples.js" defer></script>')
    html = html.replace('<title>BANLAG — Disclosure Audit</title>', '<title>BANLAG — Read-only demo</title>')
    (out / 'index.html').write_text(html, encoding='utf-8')
    (out / 'static-config.js').write_text("'use strict';\nwindow.BANLAG_STATIC = true;\n", encoding='utf-8')
    shots = out / 'evidence' / 'screenshots'
    shots.mkdir(parents=True)
    for p in (ROOT / 'evidence' / 'screenshots').glob('*.jpg'):
        shutil.copy2(p, shots / p.name)
    (out / '.nojekyll').write_text('', encoding='utf-8')
    return out, len(index)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--out', default=str(ROOT / '_site'))
    a = ap.parse_args(argv)
    out, n = build(a.out)
    print(f'static demo written to {out} ({n} pre-rendered POST responses)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
