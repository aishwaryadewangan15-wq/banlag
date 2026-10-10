"""Extra reproductions required by claudeINS.txt that Codex's harness does not cover. No network.
Usage (cwd = an isolated APP copy): python repro_codex2_extra.py"""
import datetime as dt, hashlib, json, shutil, sys, tempfile
from pathlib import Path
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, str(Path.cwd()))
from banlag import corpus, capture_store, collector
from banlag.engine import evaluate, evaluate_run
from banlag.citations import reference_formulation, relation_to
ING = ['dicyclomine', 'paracetamol', 'clidinium bromide']
out = []


def rec(name, expect, ok, got):
    out.append((name, expect, ok, got))
    print(f"{'PASS' if ok else 'FAIL'}  {name:<62} expect: {expect:<52} got: {got}")


# Corpus: cached verification then tamper; then restore.
tmp = Path(tempfile.mkdtemp())
try:
    shutil.copyfile('evidence/g1_corpus.json', tmp / 'g1_corpus.json'); shutil.copyfile('evidence/CORPUS_MANIFEST.json', tmp / 'CORPUS_MANIFEST.json')
    args = (str(tmp / 'g1_corpus.json'), str(tmp / 'CORPUS_MANIFEST.json'))
    r1 = corpus.build_cases(*args)
    rec('corpus: first load of pristine copy', 'VERIFIED', r1['corpus']['integrity']['status'] == 'VERIFIED', r1['corpus']['integrity']['status'])
    good = (tmp / 'g1_corpus.json').read_bytes()
    bad = good.replace(b'is used to treat abdominal cramps', b'is used to treat abdominal crampz', 1)
    (tmp / 'g1_corpus.json').write_bytes(bad)
    man = json.loads((tmp / 'CORPUS_MANIFEST.json').read_text(encoding='utf-8'))
    (tmp / 'CORPUS_MANIFEST.json').write_text(json.dumps(dict(man, corpus_sha256=hashlib.sha256(bad).hexdigest())), encoding='utf-8')
    r2 = corpus.build_cases(*args)
    rec('corpus: tamper + rehash AFTER a cached verification', 'FAILED', r2['corpus']['integrity']['status'] == 'FAILED', f"{r2['corpus']['integrity']['status']} / {r2['g1']['locked']['verdict']}")
    (tmp / 'g1_corpus.json').write_bytes(good); (tmp / 'CORPUS_MANIFEST.json').write_text(json.dumps(man), encoding='utf-8')
    r3 = corpus.build_cases(*args)
    rec('corpus: recovery after restoring valid evidence', 'VERIFIED + G1_PASS', r3['corpus']['integrity']['status'] == 'VERIFIED' and r3['g1']['locked']['verdict'] == 'G1_PASS', f"{r3['corpus']['integrity']['status']} / {r3['g1']['locked']['verdict']}")
    for label, m in (('schema-invalid manifest (list)', []), ('manifest missing fields', {'corpus_sha256': hashlib.sha256(good).hexdigest()})):
        (tmp / 'CORPUS_MANIFEST.json').write_text(json.dumps(m), encoding='utf-8')
        r = corpus.build_cases(*args)
        rec('corpus: ' + label, 'FAILED', r['corpus']['integrity']['status'] == 'FAILED', r['corpus']['integrity']['status'])
    (tmp / 'CORPUS_MANIFEST.json').write_text(json.dumps(man), encoding='utf-8')
    c = json.loads(good.decode('utf-8'))
    c['records'][0]['gold_label'] = 'E' if c['records'][0]['gold_label'] != 'E' else 'D'
    same_count = json.dumps(c, ensure_ascii=False, indent=1).encode('utf-8')
    (tmp / 'g1_corpus.json').write_bytes(same_count)
    (tmp / 'CORPUS_MANIFEST.json').write_text(json.dumps(dict(man, corpus_sha256=hashlib.sha256(same_count).hexdigest())), encoding='utf-8')
    r = corpus.build_cases(*args)
    rec('corpus: same record count, changed label, rehashed', 'FAILED', r['corpus']['integrity']['status'] == 'FAILED', r['corpus']['integrity']['status'])
finally:
    shutil.rmtree(tmp, ignore_errors=True)

# Citation views.
T3 = 'Dicyclomine + Paracetamol + Clidinium Bromide Tablets'
cases = [
    ('title exact; snippet swaps in chlordiazepoxide', {'title': T3, 'snippet': 'Dicyclomine + Paracetamol + Chlordiazepoxide tablets.', 'link': 'https://x.invalid/p'}, lambda rel: rel != 'EXACT'),
    ('title exact; URL slug names a 4-drug set', {'title': T3, 'snippet': '', 'link': 'https://x.invalid/dicyclomine-paracetamol-clidinium-bromide-chlordiazepoxide'}, lambda rel: rel != 'EXACT'),
    ('snippet describes two formulations', {'title': 'Antispasmodics', 'snippet': 'Dicyclomine + Paracetamol and Dicyclomine + Paracetamol + Clidinium Bromide are both sold.', 'link': 'https://x.invalid/p'}, lambda rel: rel != 'EXACT'),
    ('no view names a complete formulation', {'title': 'Overview', 'snippet': 'Antispasmodic medicines.', 'link': 'https://x.invalid/p'}, lambda rel: rel == 'NO_FORMULATION_NAMED'),
    ('POSITIVE: title, snippet and slug agree', {'title': T3, 'snippet': 'A combination of dicyclomine, paracetamol and clidinium bromide for cramps.', 'link': 'https://x.invalid/dicyclomine-paracetamol-clidinium-bromide'}, lambda rel: rel == 'EXACT'),
]
for name, ref, check in cases:
    f = reference_formulation(dict(ref, index=0))
    rel = relation_to(set(ING), f)
    rec('citation: ' + name, 'see rule', check(rel), rel)

# Authenticated (sealed) synthetic capture containing a false legal statement must not be promoted.
sys.path.insert(0, str(Path.cwd() / 'tests'))
from tests.test_capture_store import PLAN, KEY, FakeFetch, fake_responses
tmp = Path(tempfile.mkdtemp())
try:
    resp = fake_responses()
    resp[0]['organic_results'] = [{'position': 1, 'link': 'https://egazette.gov.in/x.pdf', 'title': 'x',
                                   'snippet': 'Dicyclomine, Paracetamol and Clidinium Bromide, a combination sold in India, is banned in the United States.'}]
    resp[1]['ai_overview']['text_blocks'][0]['snippet'] = 'Dicyclomine, Paracetamol and Clidinium Bromide (plus omeprazole) are used to treat abdominal cramps.'
    sha = hashlib.sha256(PLAN.read_bytes()).hexdigest()
    run_id, _ = collector.run(PLAN, sha, env={'BANLAG_SERPAPI_APPROVAL': sha, 'SERPAPI_API_KEY': KEY}, fetch=FakeFetch(resp), store=tmp / 's',
                              key_path=tmp / 'k' / 'key', now=lambda: dt.datetime(2026, 10, 10, 10, 0, 5, tzinfo=dt.timezone.utc), out=lambda *a: None)
    r = evaluate_run(run_id, tmp / 's', tmp / 'k' / 'key')
    a = r['answers'][0]
    rec('sealed synthetic: "(plus omeprazole)" + US ban organic', 'label B/F, verified tier 0', a['prereg_label'] in ('B', 'F') and r['verified_evidence_tier'] == 0,
        f"{r['origin']} label={a['prereg_label']} verified={r['verified_evidence_tier']}")
finally:
    shutil.rmtree(tmp, ignore_errors=True)
print(f"\nFAILURES: {sum(1 for x in out if not x[2])} / {len(out)}")
