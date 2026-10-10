"""RC-3 reproduction (Codex RC2_ACCEPTANCE_AUDIT.md P1 family + P2 question binding + suspected no-lead default), with controls.
Run with cwd = an isolated APP copy (RC-2 for BEFORE, RC-3 for AFTER). Fake fetchers and DUMMY keys only; no network."""
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
from banlag import collector, semantics
from banlag.engine import evaluate, evaluate_run
from banlag.legal import entry_by_id

ING = ['dicyclomine', 'paracetamol', 'clidinium bromide']
F08 = entry_by_id('F08')
X = 'Dicyclomine, Paracetamol and Clidinium Bromide'
LEAD = X + ' are used to treat abdominal cramps.'
BAN = 'The Central Government has prohibited the fixed dose combination of ' + X + ' for human use.'
SQ = 'is dicyclomine paracetamol clidinium bromide prohibited for manufacture sale or distribution in india in 2026'
rows = []


def rec(group, name, want, ok, got):
    rows.append({'group': group, 'name': name, 'want': want, 'ok': bool(ok), 'got': got})
    print(f"{'PASS' if ok else 'FAIL'} {group:<5} {name:<78} want {want:<26} got {json.dumps(got, default=str)[:150]}")


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


def ev(text, **kw):
    r = evaluate(payload(text, **kw))
    a = r['answers'][0]
    return {'label': a['prereg_label'], 'composition': a['analysis']['subject'].get('composition_verdict'), 'tier': r['evidence_tier'],
            'contrast': r['explicit_status_contrast'], 'gate': r['publication_gate']['decision'], 'origin': r['origin']}


def t3(statement):
    url = 'https://ref.example.invalid/p'
    p = payload(None, refs=[{'index': 0, 'link': url}], blocks=[{'type': 'paragraph', 'snippet': LEAD, 'reference_indexes': [0]}])
    r = evaluate(p, verified_snapshots=[{'url': url, 'text': statement, 'sha256': '0' * 64}])
    return r['evidence_tier']


# ---- P1: denial within / before the lead (answers)
for name, text in [('semicolon: LEAD; the tablet does not contain paracetamol', LEAD[:-1] + '; the tablet does not contain paracetamol.'),
                   ('comma-joined: LEAD, but the tablet does not contain paracetamol', LEAD[:-1] + ', but the tablet does not contain paracetamol.'),
                   ('reversed: It does not contain paracetamol. LEAD', 'It does not contain paracetamol. ' + LEAD),
                   ('block before lead', None)]:
    if text is None:
        r = evaluate(payload(None, blocks=[{'type': 'paragraph', 'snippet': 'The tablet does not contain paracetamol.'}, {'type': 'paragraph', 'snippet': LEAD}]))
        a = r['answers'][0]
        got = {'label': a['prereg_label'], 'composition': a['analysis']['subject'].get('composition_verdict'), 'tier': r['evidence_tier']}
    else:
        got = ev(text)
    rec('P1', 'answer ' + name, 'B/F, T0', got['label'] in ('B', 'F') and got['tier'] == 0, got)
for name, text in [('X does not contain paracetamol. This combination is prohibited in India.', X + ' does not contain paracetamol. This combination is prohibited in India.'),
                   ('LEAD; this combination is prohibited in India; the tablet does not contain paracetamol.',
                    LEAD[:-1] + '; this combination is prohibited in India; the tablet does not contain paracetamol.')]:
    got = ev(text)
    rec('P1', 'no D: ' + name[:60], 'not D', got['label'] != 'D', got)
# ---- P1: organic T2 / snapshot T3 / sealed
for name, s in [('BAN; the tablet does not contain paracetamol', BAN[:-1] + '; the tablet does not contain paracetamol.'),
                ('It does not contain paracetamol. BAN', 'It does not contain paracetamol. ' + BAN),
                ('X does not contain paracetamol. BAN', X + ' does not contain paracetamol. ' + BAN)]:
    got = ev(LEAD, org=organic(s))
    rec('P1', 'organic T2: ' + name, 'E, T1', (got['label'], got['tier']) == ('E', 1), got)
    got = t3(s)
    rec('P1', 'snapshot T3: ' + name, 'T1', got == 1, got)
# ---- suspected no-lead default
st = semantics.text_composition('Antispasmodic combinations are prohibited in India.', ING)
rec('NOLEAD', 'text_composition with no target named', 'not SUPPORTED_EXACT', st['verdict'] != 'SUPPORTED_EXACT', st['verdict'])
for name, s in [('target split across sentences', 'Dicyclomine and Paracetamol are prohibited in India. Clidinium Bromide too.'),
                ('superset sentence, exact clause', X + ' is prohibited in India; chlordiazepoxide is also in it.'),
                ('only a pronoun', 'It is prohibited in India.'),
                ('two products, target not named', 'Dicyclomine + Paracetamol is prohibited in India. Clidinium bromide is sold.')]:
    got = ev(LEAD, org=organic(s))
    rec('NOLEAD', 'organic T2: ' + name, 'T1', got['tier'] == 1, got)
    rec('NOLEAD', 'snapshot T3: ' + name, 'T1', t3(s) == 1, t3(s))
# ---- P2: status question binding
BAD_Q = 'is omeprazole prohibited in india'
for name, status, want in [('missing question, anaphoric answer', {'answer_text': 'This combination is prohibited in India.'}, False),
                           ('wrong question, target-naming answer', {'query': BAD_Q, 'answer_text': X + ' is prohibited in India.'}, False),
                           ('validated question, clean answer (control)', {'query': SQ, 'answer_text': 'This combination is prohibited in India.'}, True)]:
    r = evaluate(payload(LEAD, status=status))
    got = {'label': r['status_answer_label'], 'contrast': r['explicit_status_contrast'], 'validation': r['status_question_validation'],
           'uses_tier': r['evidence_tier']}
    rec('P2', 'explicit status: ' + name, f'contrast {want}', r['explicit_status_contrast'] is want and r['evidence_tier'] == 1, got)
for name, q, ans, want in [('status_capture missing q', None, 'This combination is prohibited in India.', False),
                           ('status_capture wrong q', BAD_Q, X + ' is prohibited in India.', False),
                           ('status_capture validated q (control)', SQ, 'This combination is prohibited in India.', True)]:
    p = payload(LEAD)
    p['status_capture'] = {'search_metadata': {'id': 'S2'}, 'search_parameters': {'q': q} if q else {},
                           'ai_overview': {'text_blocks': [{'type': 'paragraph', 'snippet': ans}], 'references': []}, 'organic_results': []}
    r = evaluate(p)
    rec('P2', name, f'contrast {want}', r['explicit_status_contrast'] is want,
        {'label': r['status_capture']['label'], 'contrast': r['explicit_status_contrast'], 'validation': r['status_capture'].get('question_validation')})
# ---- positive controls
got = ev(LEAD); rec('CTRL', 'exact LEAD', 'E, T1', (got['label'], got['tier']) == ('E', 1), got)
got = ev(LEAD + ' This combination is prohibited in India.'); rec('CTRL', 'exact LEAD + Indian ban', 'D', got['label'] == 'D', got)
got = ev(LEAD[:-1] + '; it does not contain omeprazole.'); rec('CTRL', 'LEAD; it does not contain omeprazole (non-member)', 'E, T1', (got['label'], got['tier']) == ('E', 1), got)
got = ev(LEAD[:-1] + '; another medicine for reflux does not contain paracetamol.'); rec('CTRL', 'LEAD; another medicine lacks paracetamol', 'E, T1', (got['label'], got['tier']) == ('E', 1), got)
got = ev('This combination contains dicyclomine, paracetamol and clidinium bromide; it is used to treat abdominal cramps.')
rec('CTRL', 'lead list via "contains" stays exact', 'E, T1', (got['label'], got['tier']) == ('E', 1), got)
got = ev(LEAD, org=organic(BAN)); rec('CTRL', 'clean organic ban', 'T2', got['tier'] == 2, got)
rec('CTRL', 'clean snapshot ban', 'T3', t3(BAN) == 3, t3(BAN))
# ---- HTTP + JS + sealed
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
    d = post(payload(LEAD[:-1] + '; the tablet does not contain paracetamol.'))
    rec('HTTP', 'API semicolon denial', 'tier 0', d['evidence_tier'] == 0, d['evidence_tier'])
    d = post(payload(LEAD, org=organic(BAN[:-1] + '; the tablet does not contain paracetamol.')))
    rec('HTTP', 'API contradictory organic', 'tier 1', d['evidence_tier'] == 1, d['evidence_tier'])
    d = post(payload(LEAD, status={'answer_text': 'This combination is prohibited in India.'}))
    rec('HTTP', 'API missing-question contrast', 'false', d['explicit_status_contrast'] is False, d['explicit_status_contrast'])
finally:
    srv.shutdown(); srv.server_close()
node = shutil.which('node')
js = (Path('web') / 'app.js').read_text(encoding='utf-8')
fn = re.search(r'const QUALIFIERS = .*?\nfunction claimClass\(c\) \{.*?\n\}', js, re.S).group(0)
sb = re.search(r'const SUBJECT_BINDINGS = [^;]+;', js).group(0)
claims = {}
for k, s in (('denied', X + ' does not contain paracetamol. This combination is prohibited in India.'), ('exact', LEAD + ' This combination is prohibited in India.')):
    an = evaluate(payload(s))['answers'][0]['analysis']
    claims[k] = next(c for c in an['claims'] if c.get('restriction'))
out = json.loads(subprocess.run([node, '-e', sb + '\n' + fn + '\nconst C=' + json.dumps(claims) + ';console.log(JSON.stringify({denied: claimClass(C.denied), exact: claimClass(C.exact)}))'],
                                capture_output=True, text=True, timeout=30, check=True).stdout)
rec('JS', 'claimClass: lead denies paracetamol + ban', 'not c-restrict', out['denied'] != 'c-restrict', out['denied'])
rec('JS', 'claimClass: exact + ban (control)', 'c-restrict', out['exact'] == 'c-restrict', out['exact'])
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


r = sealed(LEAD[:-1] + '; the tablet does not contain paracetamol.', BAN)
rec('SEAL', 'sealed: semicolon AI denial + clean organic ban', 'verified 0, WITHHOLD, no contrast',
    r['verified_evidence_tier'] == 0 and r['publication_gate']['decision'] == 'WITHHOLD' and not r['explicit_status_contrast'],
    {'origin': r['origin'], 'label': r['answers'][0]['prereg_label'], 'verified': r['verified_evidence_tier'], 'gate': r['publication_gate']['decision'],
     'contrast': r['explicit_status_contrast']})
r = sealed(LEAD, BAN[:-1] + '; the tablet does not contain paracetamol.')
rec('SEAL', 'sealed: exact AI + contradictory organic', 'verified 1', r['verified_evidence_tier'] == 1,
    {'label': r['answers'][0]['prereg_label'], 'verified': r['verified_evidence_tier'], 'gate': r['publication_gate']['decision']})
r = sealed(LEAD, BAN, 'This combination is prohibited in India.')
rec('SEAL', 'control: sealed exact + clean ban + validated status', 'verified 2, contrast, ELIGIBLE',
    r['verified_evidence_tier'] == 2 and r['explicit_status_contrast'] and r['publication_gate']['decision'] == 'ELIGIBLE_FOR_REVIEW',
    {'verified': r['verified_evidence_tier'], 'contrast': r['explicit_status_contrast'], 'gate': r['publication_gate']['decision'],
     'status_validation': r['status_capture'].get('question_validation') if r.get('status_capture') else None})
bad = [x for x in rows if not x['ok']]
print(f"\nRC-3 reproduction: {len(rows) - len(bad)} meet expectation / {len(rows)}  (failing groups: {', '.join(sorted({x['group'] for x in bad})) or 'none'})")
(Path.cwd().parent / 'repro_rc3_results.json').write_text(json.dumps(rows, ensure_ascii=False, indent=1, default=str), encoding='utf-8')
