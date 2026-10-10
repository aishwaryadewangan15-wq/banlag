"""RC-2 reproduction of Codex RC1_ARCHITECTURE_AUDIT.md P1-1, P1-2 and P2-1..5, with paired positive controls.
Run with cwd = an isolated APP copy (baseline RC-1 for BEFORE, RC-2 for AFTER). Fake fetchers and DUMMY keys only; no network."""
import datetime as dt
import hashlib
import http.client
import json
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, str(Path.cwd()))
from banlag import collector
from banlag.citations import coherence, reference_formulation
from banlag.claims import analyze_surface
from banlag.engine import evaluate, evaluate_run, publication_gate
from banlag.legal import entry_by_id, registry
from banlag import provenance as P

ING = ['dicyclomine', 'paracetamol', 'clidinium bromide']
F08 = entry_by_id('F08')
X = 'Dicyclomine, Paracetamol and Clidinium Bromide'
LEAD = X + ' are used to treat abdominal cramps.'
BAN = 'The Central Government has prohibited the fixed dose combination of ' + X + ' for human use.'
rows = []


def rec(group, name, want, ok, got):
    rows.append({'group': group, 'name': name, 'want': want, 'ok': bool(ok), 'got': got})
    print(f"{'PASS' if ok else 'FAIL'} {group:<6} {name:<70} want {want:<34} got {got}")


def payload(text, org=None, refs=None, blocks=None, status=None):
    p = {'source_kind': 'SYNTHETIC_TEST', 'query': 'q', 'ingredients': ING,
         'google': {'search_metadata': {'id': 'S1'}, 'search_parameters': {'q': 'q'}, 'organic_results': org or [],
                    'ai_overview': {'text_blocks': blocks or [{'type': 'paragraph', 'snippet': text, 'reference_indexes': [0] if refs else []}],
                                    'references': refs or []}}}
    if status is not None:
        p['explicit_status_query'] = status
    return p


def organic(s):
    return [{'position': 1, 'title': 'Regulatory report', 'link': 'https://news.example.invalid/r', 'snippet': s}]


def lt(text, **kw):
    r = evaluate(payload(text, **kw))
    return r['answers'][0]['prereg_label'], r['evidence_tier']


def t3(statement, idx=(0,)):
    url = 'https://ref.example.invalid/p'
    p = payload(None, refs=[{'index': 0, 'link': url}], blocks=[{'type': 'paragraph', 'snippet': LEAD, 'reference_indexes': list(idx)}])
    return evaluate(p, verified_snapshots=[{'url': url, 'text': statement, 'sha256': '0' * 64}])['evidence_tier']


# ---------------- P1-1 negated target membership ----------------
NEG = 'It does not contain paracetamol.'
got = lt(LEAD + ' ' + NEG); rec('P1-1', 'answer: target "does not contain paracetamol"', 'B/F, tier 0', got[0] in ('B', 'F') and got[1] == 0, got)
got = lt(LEAD, org=organic(BAN + ' ' + NEG))[1]; rec('P1-1', 'organic T2: ban + "does not contain paracetamol"', 'tier 1', got == 1, got)
got = t3(BAN + ' ' + NEG); rec('P1-1', 'snapshot T3: ban + "does not contain paracetamol"', 'tier 1', got == 1, got)
got = lt(LEAD + ' ' + X + ' does not contain omeprazole.'); rec('P1-1', 'control: target "does not contain omeprazole"', 'E/1', got == ('E', 1), got)
got = lt(LEAD + ' It does not contain omeprazole.'); rec('P1-1', 'control: "It does not contain omeprazole"', 'E/1', got == ('E', 1), got)
got = lt(LEAD + ' Another medicine, used for reflux, does not contain paracetamol.'); rec('P1-1', 'control: another medicine lacks paracetamol', 'E/1', got == ('E', 1), got)
got = lt(LEAD); rec('P1-1', 'control: genuine exact formulation', 'E/1', got == ('E', 1), got)
got = lt(LEAD, org=organic(BAN))[1]; rec('P1-1', 'control: clean organic ban', 'tier 2', got == 2, got)
got = t3(BAN); rec('P1-1', 'control: clean snapshot ban', 'tier 3', got == 3, got)

# ---------------- P1-2 query-hinted status ----------------
BAD = 'This formulation also contains omeprazole. This combination is prohibited in India.'
r = evaluate(payload(LEAD, status={'query': 'is dicyclomine paracetamol clidinium bromide prohibited in india', 'answer_text': BAD}))
rec('P1-2', 'explicit status: "also contains omeprazole" + prohibited', 'not D, no contrast', r['status_answer_label'] != 'D' and not r['explicit_status_contrast'],
    (r['status_answer_label'], r['explicit_status_contrast']))
r = evaluate(payload(LEAD, status={'answer_text': BAD}))
rec('P1-2', 'explicit status without question text', 'not D, no contrast', r['status_answer_label'] != 'D' and not r['explicit_status_contrast'],
    (r['status_answer_label'], r['explicit_status_contrast']))
r = evaluate(payload(LEAD, status={'query': 'is dicyclomine paracetamol clidinium bromide omeprazole prohibited in india',
                                   'answer_text': 'This combination is prohibited in India.'}))
rec('P1-2', 'status question names an extra ingredient', 'not D, no contrast', r['status_answer_label'] != 'D' and not r['explicit_status_contrast'],
    (r['status_answer_label'], r['explicit_status_contrast']))
p = payload(LEAD)
p['status_capture'] = {'search_metadata': {'id': 'S2'}, 'search_parameters': {'q': 'is dicyclomine paracetamol clidinium bromide prohibited in india'},
                       'ai_overview': {'text_blocks': [{'type': 'paragraph', 'snippet': BAD}], 'references': []}, 'organic_results': []}
r = evaluate(p)
rec('P1-2', 'status capture: "also contains omeprazole" + prohibited', 'not D, no contrast', r['status_capture']['label'] != 'D' and not r['explicit_status_contrast'],
    (r['status_capture']['label'], r['explicit_status_contrast']))
r = evaluate(payload(LEAD, status={'query': 'is dicyclomine paracetamol clidinium bromide prohibited in india', 'answer_text': 'This combination is prohibited in India.'}))
rec('P1-2', 'control: plain "This combination is prohibited in India."', 'D, contrast', r['status_answer_label'] == 'D' and r['explicit_status_contrast'],
    (r['status_answer_label'], r['explicit_status_contrast']))
r = evaluate(payload(LEAD, status={'answer_text': 'This combination is prohibited in India.'}))
rec('P1-2', 'control: same, question text absent', 'D, contrast', r['status_answer_label'] == 'D' and r['explicit_status_contrast'],
    (r['status_answer_label'], r['explicit_status_contrast']))
a = analyze_surface([{'id': 'b0', 'type': 'paragraph', 'label': None, 'text': BAD, 'chips': []}], target_entry=F08, subject_hint=set(ING))
rec('P1-2', 'analyze_surface(subject_hint) composition verdict', 'not null / not EXACT', a['subject'].get('composition_verdict') not in (None, 'SUPPORTED_EXACT'),
    (a['prereg_label'], a['subject'].get('composition_verdict')))

# ---------------- P2-1 malformed claim indexes ----------------
for bad in (False, 0.0):
    got = t3(BAN, idx=(bad,)); rec('P2-1', f'claim reference_indexes [{bad!r}] binds T3', 'tier 1', got == 1, got)

# ---------------- P2-2 citation restriction binding ----------------
ref = {'index': 0, 'title': X + ' tablets', 'snippet': 'Chlordiazepoxide is prohibited in India.', 'link': 'https://x.invalid/p', 'source': 'S'}
blocks = [{'id': 'b0', 'type': 'paragraph', 'label': None, 'text': LEAD, 'reference_indexes': [], 'chips': []},
          {'id': 'b1', 'type': 'paragraph', 'label': None, 'text': 'This combination is prohibited in India.', 'reference_indexes': [0], 'chips': []}]
coh = coherence(analyze_surface(blocks, [ref], 'REFERENCE_INDEX_BOUND', F08), [ref])
rec('P2-2', 'exact title + other-entity ban snippet suppresses finding', 'finding reported', bool(coh['findings']), coh['status'])
ref_ok = {'index': 0, 'title': 'Prohibition of ' + X, 'snippet': BAN, 'link': 'https://x.invalid/q', 'source': 'S'}
coh = coherence(analyze_surface(blocks, [ref_ok], 'REFERENCE_INDEX_BOUND', F08), [ref_ok])
rec('P2-2', 'control: reference states the exact ban', 'no finding', not coh['findings'], coh['status'])

# ---------------- P2-3 green highlight on a rejected formulation ----------------
node = shutil.which('node')
js = (Path('web') / 'app.js').read_text(encoding='utf-8')
fn = re.search(r'const QUALIFIERS = .*?\nfunction claimClass\(c\) \{.*?\n\}', js, re.S).group(0)
sb = re.search(r'const SUBJECT_BINDINGS = [^;]+;', js).group(0)
claims = {}
for k, s in (('rejected', LEAD + ' This combination is prohibited in India. Omeprazole is also in it.'), ('exact', LEAD + ' This combination is prohibited in India.')):
    an = evaluate(payload(s))['answers'][0]['analysis']
    claims[k] = next(c for c in an['claims'] if c.get('restriction'))
out = json.loads(subprocess.run([node, '-e', sb + '\n' + fn + '\nconst C=' + json.dumps(claims) + ';console.log(JSON.stringify({rejected: claimClass(C.rejected), exact: claimClass(C.exact)}))'],
                                capture_output=True, text=True, timeout=30, check=True).stdout)
rec('P2-3', 'JS claimClass on composition-DIFFERENT answer', 'not c-restrict', out['rejected'] != 'c-restrict', out['rejected'])
rec('P2-3', 'control: JS claimClass on exact answer', 'c-restrict', out['exact'] == 'c-restrict', out['exact'])

# ---------------- P2-4 source chips for duplicate indexes ----------------
from banlag.server import _answer_view
refs = [{'index': 0, 'title': 'A', 'link': 'https://x.invalid/1', 'source': 'First source'}, {'index': 0, 'title': 'B', 'link': 'https://x.invalid/2', 'source': 'Second source'}]
view = _answer_view(evaluate(payload(LEAD, refs=refs))['answers'][0])
chip = view['blocks'][0]['chips'][0]['source']
rec('P2-4', 'source chip for duplicated index 0', 'ambiguity disclosed', 'Second source' not in chip and 'First source' not in chip, chip)

# ---------------- P2-5 publication gate without composition ----------------
g = publication_gate(P.TRUSTED, {'status': 'EXACT_NOTIFICATION_MATCH', 'match_strength': 'LITERAL'}, '2026-10-10T10:00:00+00:00', True, registry()['legal_status'])
rec('P2-5', 'gate called without text_composition', 'WITHHOLD', g['decision'] == 'WITHHOLD', (g['decision'], g['withhold_reasons']))

# ---------------- HTTP / API ----------------
from banlag.server import Handler
srv = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
th = threading.Thread(target=srv.serve_forever, daemon=True)
th.start()
try:
    def post(obj):
        c = http.client.HTTPConnection('127.0.0.1', srv.server_port, timeout=10)
        c.request('POST', '/api/evaluate', body=json.dumps(obj).encode(), headers={'Content-Type': 'application/json'})
        d = json.loads(c.getresponse().read().decode())
        c.close()
        return d
    d = post(payload(LEAD + ' ' + NEG)); rec('HTTP', 'API: target "does not contain paracetamol"', 'tier 0', d['evidence_tier'] == 0, d['evidence_tier'])
    d = post(payload(LEAD, status={'answer_text': BAD})); rec('HTTP', 'API: contradictory status answer', 'no contrast', not d['explicit_status_contrast'], d['status_answer_label'])
    d = post(payload(LEAD, org=organic(BAN))); rec('HTTP', 'API control: clean organic ban', 'tier 2', d['evidence_tier'] == 2, d['evidence_tier'])
finally:
    srv.shutdown(); srv.server_close()

# ---------------- dummy-key sealed runs ----------------
sys.path.insert(0, str(Path.cwd() / 'tests'))
from tests.test_capture_store import PLAN, KEY, FakeFetch, fake_responses


def sealed(ai_text, org_text, status_text=None):
    tmp = Path(tempfile.mkdtemp())
    try:
        resp = fake_responses()
        resp[1]['ai_overview']['text_blocks'][0]['snippet'] = ai_text
        resp[0]['organic_results'] = organic(org_text)
        if status_text:
            resp[2]['ai_overview']['text_blocks'][0]['snippet'] = status_text
        sha = hashlib.sha256(PLAN.read_bytes()).hexdigest()
        run_id, _ = collector.run(PLAN, sha, env={'BANLAG_SERPAPI_APPROVAL': sha, 'SERPAPI_API_KEY': KEY}, fetch=FakeFetch(resp), store=tmp / 'store',
                                  key_path=tmp / 'private' / 'key', out=lambda *a: None, now=lambda: dt.datetime(2026, 10, 10, 10, 0, 5, tzinfo=dt.timezone.utc))
        return evaluate_run(run_id, tmp / 'store', tmp / 'private' / 'key')
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


r = sealed(LEAD + ' ' + NEG, BAN)
rec('SEAL', 'sealed: answer denies paracetamol + clean organic ban', 'verified 0, WITHHOLD', r['verified_evidence_tier'] == 0 and r['publication_gate']['decision'] == 'WITHHOLD',
    (r['origin'], r['answers'][0]['prereg_label'], r['verified_evidence_tier'], r['publication_gate']['decision']))
r = sealed(LEAD, BAN, BAD)
rec('SEAL', 'sealed: contradictory status capture', 'status not D, no contrast', r['status_capture']['label'] != 'D' and not r['explicit_status_contrast'],
    (r['status_capture']['label'], r['explicit_status_contrast'], r['verified_evidence_tier']))
r = sealed(LEAD, BAN, 'This combination is prohibited in India.')
rec('SEAL', 'control: sealed exact answer + ban + plain status', 'verified 2, D, contrast, ELIGIBLE',
    r['verified_evidence_tier'] == 2 and r['status_capture']['label'] == 'D' and r['explicit_status_contrast'] and r['publication_gate']['decision'] == 'ELIGIBLE_FOR_REVIEW',
    (r['verified_evidence_tier'], r['status_capture']['label'], r['explicit_status_contrast'], r['publication_gate']['decision']))

bad = [x for x in rows if not x['ok']]
print(f"\nRC-2 reproduction: {len(rows) - len(bad)} meet expectation / {len(rows)}  (defect rows failing: {', '.join(sorted({x['group'] for x in bad})) or 'none'})")
(Path.cwd().parent / 'repro_rc2_results.json').write_text(json.dumps(rows, ensure_ascii=False, indent=1, default=str), encoding='utf-8')
