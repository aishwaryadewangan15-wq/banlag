"""Offline smoke test for this rights-conscious release folder; HTTP traffic is loopback only."""
import hashlib
import json
import os
from pathlib import Path
import queue
import re
import subprocess
import sys
import threading
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
EXCLUDED = {
    'original/evidence/CORPUS_MANIFEST.json',
    'original/evidence/g1_corpus.json',
    'omf/data/aio_f08_derivative.json',
    'omf/data/evidence_pins.json',
}


def require(ok, message):
    if not ok:
        raise AssertionError(message)


def request(base, path, payload=None):
    data = None if payload is None else json.dumps(payload).encode('utf-8')
    req = Request(base + path, data=data,
                  headers={'Content-Type': 'application/json'} if data is not None else {})
    try:
        with urlopen(req, timeout=5) as response:
            return response.status, response.read()
    except HTTPError as exc:
        return exc.code, exc.read()


def json_get(base, path):
    code, body = request(base, path)
    require(code == 200, f'{path}: expected HTTP 200, got {code}')
    return json.loads(body)


def privacy_and_manifest():
    for rel in EXCLUDED:
        require(not (ROOT / rel).exists(), f'excluded evidence present: {rel}')
    require(not (ROOT / 'original/evidence/screenshots').exists(), 'excluded screenshot directory present')
    files = [p for p in ROOT.rglob('*') if p.is_file() and p.name != 'PACKAGE_SHA256_MANIFEST.json']
    require(not any(p.suffix.lower() in {'.jpg', '.jpeg', '.png', '.webp', '.log', '.pyc'} for p in files),
            'image, generated log, or bytecode artifact present')
    require(not any({'.git', '__pycache__', 'node_modules'} & set(p.parts) for p in files),
            'repository/cache/dependency artifact present')
    manifest_path = ROOT / 'PACKAGE_SHA256_MANIFEST.json'
    require(manifest_path.is_file(), 'package manifest missing')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    expected = {str(p.relative_to(ROOT)).replace('\\', '/'): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in files}
    entries = manifest.get('files', manifest)
    if isinstance(entries, list):
        actual = {x['path']: x['sha256'] for x in entries}
    else:
        actual = entries
    require(actual == expected, 'package manifest does not exactly match payload hashes')
    private_path = re.compile(r'(?i)[A-Z]:' + r'\\' + r'(?:Users|HACK' + 'ATHON' + r')' + r'\\')
    key_literal = re.compile(r'(?i)(?:serpapi[_-]?key|api[_-]?key)\s*[:=]\s*["\'][^"\']{8,}["\']')
    for p in files:
        if p.suffix.lower() not in {'.py', '.js', '.html', '.css', '.md', '.json', '.bat'}:
            continue
        text = p.read_text(encoding='utf-8', errors='replace')
        require(not private_path.search(text), f'local personal/project path found in {p.relative_to(ROOT)}')
        require(not key_literal.search(text), f'credential-like literal found in {p.relative_to(ROOT)}')
    return len(files)


def main():
    count = privacy_and_manifest()
    env = {k: v for k, v in os.environ.items()
           if k.upper() in {'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'PATH', 'PATHEXT', 'TEMP', 'TMP',
                            'USERPROFILE', 'HOMEDRIVE', 'HOMEPATH', 'APPDATA', 'LOCALAPPDATA',
                            'PROCESSOR_ARCHITECTURE', 'NUMBER_OF_PROCESSORS'}}
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    env['OMF_ORIGINAL_RUN_DIR'] = str(ROOT / 'NO_ARCHIVE_CONFIGURED')
    env['BANLAG_KEY_DIR'] = str(ROOT / 'NO_LOCAL_KEYS')
    proc = subprocess.Popen([sys.executable, '-I', '-B', str(ROOT / 'run_integrated.py')],
                            cwd=ROOT, env=env, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, bufsize=1)
    lines = queue.Queue()

    def read_output():
        try:
            for line in proc.stdout:
                lines.put(line.rstrip())
        finally:
            lines.put(None)

    threading.Thread(target=read_output, daemon=True).start()
    base = None
    transcript = []
    deadline = time.monotonic() + 25
    try:
        while time.monotonic() < deadline:
            try:
                line = lines.get(timeout=max(0.05, deadline - time.monotonic()))
            except queue.Empty:
                break
            if line is None:
                break
            transcript.append(line)
            match = re.search(r'http://127\.0\.0\.1:(\d+)/', line)
            if match:
                base = 'http://127.0.0.1:' + match.group(1)
                break
        require(base is not None, 'server did not bind loopback: ' + ' | '.join(transcript))
        require(all('http://127.0.0.1:' in x for x in transcript if x.startswith('BANLAG integrated offline server')),
                'launcher did not report loopback-only binding')

        code, page = request(base, '/')
        require(code == 200 and b'One Missing Fact' in page, 'BANLAG page or integrated navigation missing')
        require(b'Official Gazette notifications' in page and b'PIB source' in page,
                'prominent Government source attribution missing')
        for path in ('/api/status', '/api/overview', '/api/case/F08'):
            code, _ = request(base, path)
            require(code == 200, f'BANLAG route failed: {path} ({code})')
        ov = json_get(base, '/api/overview')
        require(ov['corpus']['integrity']['status'] == 'FAILED', 'missing G1 corpus did not fail closed')
        require(ov['corpus']['n_records'] == 0 and ov['corpus']['screenshots'] == {},
                'missing G1 corpus exposed historical records or screenshots')
        require(ov['g1']['locked']['verdict'] == 'INTEGRITY_FAILED' and not ov['g1']['locked_labels'],
                'historical G1 result was reported despite missing evidence')
        sys.path.insert(0, str(ROOT / 'original'))
        from banlag.corpus import build_cases
        internal = build_cases()
        require(all(c['publication_gate']['decision'] == 'WITHHOLD' for c in internal['cases']),
                'BANLAG publication gate was not fail-closed')
        code, case = request(base, '/api/case/F08')
        case_obj = json.loads(case)
        require(code == 200 and case_obj.get('uses', {}).get('A') is None and case_obj.get('uses', {}).get('B') is None,
                'BANLAG case still presents historical uses evidence')
        code, app_js = request(base, '/app.js')
        require(code == 200 and b'historical G1 search corpus and Google screenshots are omitted' in app_js,
                'BANLAG UI missing truthful evidence disclosure')
        code, samples = request(base, '/samples.js')
        require(code == 200 and b'BANLAG_SAMPLES = []' in samples, 'unexpected sample fixtures')
        code, _ = request(base, '/evidence/screenshots/AIMode_Q01.jpg')
        require(code == 404, 'removed screenshot route did not return not found')

        code, omf_page = request(base, '/omf/')
        require(code == 200 and b'One Missing Fact' in omf_page and b'/omf/app.js' in omf_page,
                'OMF navigation/page failed')
        code, omf_js = request(base, '/omf/app.js')
        require(code == 200 and b'HYPOTHETICAL' in omf_js and b'Historical Google/SerpApi captures are omitted' in omf_js,
                'OMF hypothetical/evidence disclosure missing')
        ev = json_get(base, '/omf/api/evidence')
        require(ev.get('evidence_state') == 'PROJECTION_MISMATCH' and ev.get('evidence_authentic') is False,
                'omitted evidence was not marked unavailable/unverified')
        derivative = ev.get('derivative') or {}
        require(not derivative.get('blocks') and not derivative.get('references'),
                'historical captured text or references were exposed')
        require('not verified' in omf_js.decode('utf-8').lower(), 'OMF UI does not say historical evidence is not verified')
        terms = sorted(next(c for c in ev['register']['cases'] if c['id'] == 'F08')['ingredients'])
        facts = {'present': [{'term': x, 'provenance': 'HYPOTHETICAL'} for x in terms], 'absent': []}

        def solve(present, absent=()):
            payload = {'present': [{'term': x, 'provenance': 'HYPOTHETICAL'} for x in present],
                       'absent': [{'term': x, 'provenance': 'HYPOTHETICAL'} for x in absent]}
            code, body = request(base, '/omf/api/solve', payload)
            require(code == 200, f'OMF solver failed: {code}')
            return json.loads(body)

        first = solve(terms)
        second = solve(terms)
        question = first['result']['question']
        require(question and second['result']['question'] == question and
                first['result']['worst_case_depth'] == second['result']['worst_case_depth'] and
                first['witness'] == second['witness'], 'solver is not deterministic for the same hypothetical facts')
        yes = solve([*terms, question])
        no = solve(terms, [question])
        require(yes['result']['candidate_ids'] and no['result']['candidate_ids'], 'YES/NO branches missing')
        require(b"kind === 'UNKNOWN'" in omf_js and b'neither branch taken, candidates unchanged' in omf_js,
                'UNKNOWN does not preserve the open state')
        accepted = first['accepted']
        expected = {'present': [x['term'] for x in accepted['present']],
                    'absent': [x['term'] for x in accepted['absent']]}
        code, body = request(base, '/omf/api/verify', {'witness': first['witness'], 'expected_facts': expected})
        require(code == 200 and json.loads(body).get('verdict') == 'PASS', 'independent verifier rejected witness')
        code, body = request(base, '/omf/api/tamper', {'witness': first['witness'], 'kind': 'swap_question'})
        require(code == 200 and json.loads(body).get('witness'), 'tamper demo failed')
        code, body = request(base, '/omf/api/verify', {'witness': json.loads(body)['witness'], 'expected_facts': expected})
        require(code == 200 and json.loads(body).get('verdict') == 'FAIL', 'tampered witness was not rejected')
        code, body = request(base, '/omf/api/solve', {'present': 'malformed', 'absent': []})
        require(code == 400 and b'INVALID_REQUEST' in body, 'malformed OMF input was not rejected')
        code, _ = request(base, '/omf/api/not-a-route')
        require(code == 404, 'unknown OMF route unexpectedly fell through')
        print(f'PASS exact candidate ({count} payload files): fail-closed missing evidence; BANLAG routes/attribution; OMF navigation; hypothetical deterministic minimax; YES/NO/UNKNOWN; independent verify PASS; tamper FAIL; malformed 400; manifest/privacy checks; loopback-only HTTP, no external requests made')
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)


if __name__ == '__main__':
    main()
