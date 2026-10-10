"""Reproduce the Codex P1 counterexamples against a BANLAG tree (no network). Usage: python repro_codex_p1.py <root>"""
import copy, datetime as dt, hashlib, importlib, json, shutil, sys, tempfile
from pathlib import Path
ROOT = Path(sys.argv[1])
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding='utf-8')
from banlag import engine, claims, corpus, capture_store, collector
from banlag.core import text_identifies_exact, match_formula
from banlag.legal import entry_by_id
F08 = entry_by_id('F08')
ING = ['dicyclomine', 'paracetamol', 'clidinium bromide']


def ans(text, organic=None):
    g = {'search_metadata': {'id': 'S1'}, 'search_parameters': {'q': 'q'},
         'ai_overview': {'text_blocks': [{'type': 'paragraph', 'snippet': text}], 'references': []},
         'organic_results': organic or []}
    r = engine.evaluate({'source_kind': 'SYNTHETIC_TEST', 'query': 'q', 'ingredients': ING, 'google': g})
    a = r['answers'][0]
    return f"label={a['prereg_label']} tier={r['evidence_tier']}"


def show(name, value):
    print(f'  {name:<74} -> {value}')


print('P1-1 UNKNOWN EXTRA INGREDIENT (target F08, 3 drugs)')
for t in ['The combination of dicyclomine, paracetamol, clidinium bromide and omeprazole is commonly prescribed for cramps.',
          'Omeprazole + dicyclomine + paracetamol + clidinium bromide is commonly prescribed.',
          'Dicyclomine, omeprazole, paracetamol and clidinium bromide combination is commonly prescribed.',
          'Dicyclomine/Paracetamol/Clidinium Bromide/Rifaximin tablets are commonly prescribed.',
          'A combination of dicyclomine, paracetamol, and clidinium bromide is commonly prescribed.  [control: exact]']:
    show(t[:74], ans(t.split('  [')[0]))
show('restriction text names F08 + omeprazole', text_identifies_exact('Section 26A prohibits the fixed dose combination of Dicyclomine + Paracetamol + Clidinium Bromide + Omeprazole in India.', F08))
try:
    from banlag.citations import reference_formulation, relation_to
    f = reference_formulation({'index': 0, 'title': 'Dicyclomine + Paracetamol + Clidinium Bromide + Omeprazole Tablets', 'link': 'https://x.invalid/p', 'snippet': ''})
    show('reference titled F08 + omeprazole: relation', relation_to(set(ING), f))
except ImportError as e:
    show('citations module', 'absent')

print('P1-2 CORPUS INTEGRITY')
tmp = Path(tempfile.mkdtemp())
try:
    for case, mutate in (('tampered corpus byte', 'tamper'), ('missing manifest', 'nomanifest')):
        c = tmp / case.replace(' ', '_')
        c.mkdir()
        data = (ROOT / 'evidence' / 'g1_corpus.json').read_bytes()
        if mutate == 'tamper':
            data = data.replace(b'is used to treat abdominal cramps', b'is used to treat abdominal crampz', 1)
        (c / 'g1_corpus.json').write_bytes(data)
        if mutate != 'nomanifest':
            shutil.copyfile(ROOT / 'evidence' / 'CORPUS_MANIFEST.json', c / 'CORPUS_MANIFEST.json')
        try:
            r = corpus.build_cases(str(c / 'g1_corpus.json'), str(c / 'CORPUS_MANIFEST.json'))
        except TypeError:  # pre-fix signature: patch module paths
            corpus.CORPUS_PATH, corpus.CORPUS_MANIFEST = c / 'g1_corpus.json', c / 'CORPUS_MANIFEST.json'
            corpus.load_corpus.cache_clear(); corpus.build_cases.cache_clear()
            r = corpus.build_cases()
        gates = sorted({x['publication_gate']['decision'] for x in r['cases']})
        show(case, f"G1={r['g1']['locked']['verdict']} positives={len(r['g1']['locked']['positives'])} notice_findings={len(r['notice_integrity'])} gates={gates}")
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print('P1-3 ARCHIVE PROVENANCE (hash-consistent run, key unavailable)')
tmp = Path(tempfile.mkdtemp())
try:
    store, key = tmp / 'store', tmp / 'k' / 'capture_hmac.key'
    sid = '6707a5e0aaaaaaaaaaaaaaa1'
    body = {'search_metadata': {'id': sid, 'status': 'Success', 'created_at': '2026-10-10 10:00:00 UTC', 'processed_at': '2026-10-10 10:00:00 UTC',
                                'json_endpoint': f'https://serpapi.com/searches/ab/{sid}.json'},
            'search_parameters': {'engine': 'google', 'q': 'dicyclomine paracetamol clidinium bromide uses'},
            'ai_overview': {'text_blocks': [{'type': 'paragraph', 'snippet': 'A combination of dicyclomine, paracetamol and clidinium bromide is commonly prescribed.', 'reference_indexes': [0]}],
                            'references': [{'index': 0, 'link': 'https://x.invalid', 'title': 't'}]},
            'organic_results': [{'position': 1, 'link': 'https://egazette.gov.in/x.pdf', 'title': 'Gazette', 'snippet': 'The Central Government hereby prohibits the manufacture, sale or distribution of the fixed dose combination of Dicyclomine + Paracetamol + Clidinium Bromide for human use.'}]}
    raw = json.dumps(body).encode()
    rec = {'capture_id': 'run-x-C1', 'run_id': 'run-x', 'call_id': 'C1', 'call_index': 0, 'role': 'uses_search', 'parent_call_id': None,
           'request': {'engine': 'google', 'params': {'q': 'dicyclomine paracetamol clidinium bromide uses'}}, 'http_status': 200,
           'received_at': '2026-10-10T10:00:05+00:00', 'provider': {k: body['search_metadata'][k] for k in ('id', 'created_at', 'processed_at', 'status', 'json_endpoint')},
           'plan_sha256': '0' * 64, 'plan': {'case': 'F08', 'ingredients': ING}}
    capture_store.seal(rec, raw, store=store, key_path=key)
    with_key = engine.evaluate_run('run-x', store, key)
    no_key = engine.evaluate_run('run-x', store, tmp / 'none' / 'k')
    for name, r in (('with local key', with_key), ('without key (public replay)', no_key)):
        show(name, f"origin={r['origin']} tier={r['evidence_tier']} verified_tier={r['verified_evidence_tier']} status={r['tier_status']} gate={r['publication_gate']['decision']}")
finally:
    shutil.rmtree(tmp, ignore_errors=True)
corpus.CORPUS_PATH, corpus.CORPUS_MANIFEST = ROOT / 'evidence' / 'g1_corpus.json', ROOT / 'evidence' / 'CORPUS_MANIFEST.json'
for fn in ('load_corpus', 'build_cases'):
    getattr(getattr(corpus, fn), 'cache_clear', lambda: None)()
r = corpus.build_cases()
c = next(x for x in r['cases'] if x['entry']['id'] == 'F08')
show('browser-archive F08 publication gate', f"{c['publication_gate']['decision']} conditions={c['publication_gate']['conditions']}")

print('P1-4 RESTRICTION NEGATION / REVOCATION (answer text, target F08)')
for t in ['Dicyclomine + paracetamol + clidinium bromide is not currently banned in India and is commonly prescribed.',
          'Dicyclomine + paracetamol + clidinium bromide is not legally prohibited in India; it is commonly prescribed.',
          'The ban on dicyclomine + paracetamol + clidinium bromide in India was revoked, and it is commonly prescribed.',
          'Dicyclomine + paracetamol + clidinium bromide is no longer prohibited in India and is commonly prescribed.',
          'Dicyclomine + paracetamol + clidinium bromide is prohibited in India.  [control: active ban]']:
    show(t[:74], ans(t.split('  [')[0]))
show('identifies exact: "prohibition ... was revoked by the Central Government"',
     text_identifies_exact('The prohibition of the fixed dose combination of Dicyclomine + Paracetamol + Clidinium Bromide was revoked by the Central Government.', F08))

print('P1-5 TIER-2 ORGANIC RESTRICTIONS (strong omission answer, same response)')
E = 'A combination of dicyclomine, paracetamol, and clidinium bromide is commonly prescribed.'
for s in ['The US FDA banned the combination of Dicyclomine + Paracetamol + Clidinium Bromide.',
          'The prohibition on Dicyclomine + Paracetamol + Clidinium Bromide was revoked by the Central Government.',
          'Dicyclomine + Paracetamol + Clidinium Bromide was banned in India in 2016.',
          'The Central Government has proposed to prohibit Dicyclomine + Paracetamol + Clidinium Bromide.',
          'Dicyclomine + Paracetamol + Clidinium Bromide is banned.',
          'The Central Government has prohibited the fixed dose combination Dicyclomine + Paracetamol + Clidinium Bromide for human use.  [control]']:
    show(s[:74], ans(E, [{'position': 1, 'title': 'r', 'link': 'https://news.example.invalid/a', 'snippet': s.split('  [')[0]}]))
