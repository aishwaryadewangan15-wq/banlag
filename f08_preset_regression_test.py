"""Regression test for the release-only hypothetical F08 starter preset."""
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


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def call(base, path, payload=None):
    data = None if payload is None else json.dumps(payload).encode('utf-8')
    request = Request(base + path, data=data,
                      headers={'Content-Type': 'application/json'} if data is not None else {})
    try:
        with urlopen(request, timeout=5) as response:
            return response.status, response.read()
    except HTTPError as exc:
        return exc.code, exc.read()


def main():
    page = (ROOT / 'omf/web/index.html').read_text(encoding='utf-8')
    js = (ROOT / 'omf/web/app.js').read_text(encoding='utf-8')
    require('data-preset="query">Hypothetical F08 register example' in page,
            'F08 preset button is missing or no longer selects query preset')
    require("b.addEventListener('click', () => preset(b.dataset.preset))" in js,
            'F08 preset button click handler is missing')
    require('const observed = S.ev.derivative && S.ev.derivative.query_terms_observed;' in js and
            'Array.isArray(observed) && observed.length > 0 ? observed : f08.ingredients' in js,
            'empty-array safe F08 fallback is missing from the preset handler')

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
    try:
        deadline = time.monotonic() + 25
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
        status, body = call(base, '/omf/api/evidence')
        require(status == 200, 'evidence API failed')
        evidence = json.loads(body)
        require(evidence.get('evidence_state') == 'PROJECTION_MISMATCH',
                'test did not exercise omitted-evidence state')
        require(evidence['derivative'].get('query_terms_observed') == [],
                'expected the fail-closed empty query-terms array')
        f08 = next(c for c in evidence['register']['cases'] if c['id'] == 'F08')
        expected_terms = {'dicyclomine', 'paracetamol', 'clidinium bromide'}
        require(set(f08['ingredients']) == expected_terms, 'F08 registry ingredient mapping changed')
        f09 = next(c for c in evidence['register']['cases'] if c['id'] == 'F09')
        require(set(f09['ingredients']) == expected_terms | {'chlordiazepoxide'},
                'F09 registry mapping no longer distinguishes F08 by chlordiazepoxide')

        # The pre-fix UI used `observed || fallback`; JavaScript [] is truthy, so it posted no facts.
        empty_status, empty_body = call(base, '/omf/api/solve', {'present': [], 'absent': []})
        require(empty_status == 200, 'empty-facts control solve failed')
        empty = json.loads(empty_body)
        require(len(empty['result']['candidate_ids']) == 10 and
                empty['result']['question'] == 'serratiopeptidase',
                'empty-facts control no longer reproduces the reported failure state')

        preset_facts = {'present': [{'term': term, 'provenance': 'HYPOTHETICAL'}
                                    for term in f08['ingredients']], 'absent': []}
        status, body = call(base, '/omf/api/solve', preset_facts)
        require(status == 200, 'F08 hypothetical preset facts rejected by solve API')
        solved = json.loads(body)
        require({x['term'] for x in solved['accepted']['present']} == expected_terms,
                'F08 preset facts were not accepted as hypothetical present facts')
        require(solved['result']['candidate_ids'] == ['F08', 'F09'],
                'F08 preset did not reduce candidates to F08 and F09')
        require(solved['result']['question'] == 'chlordiazepoxide',
                'F08 preset did not select chlordiazepoxide as the next question')
        print('PASS F08 preset regression: click binding and non-empty fallback guard present; empty-array failure reproduced; F08 registry facts accepted; candidates F08/F09; next question chlordiazepoxide')
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
