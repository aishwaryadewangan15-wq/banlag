import sys, json; sys.stdout.reconfigure(encoding='utf-8'); sys.path.insert(0, '.')
from banlag import corpus
r = corpus.build_cases()
out = {'integrity': r['corpus']['integrity']['status'], 'origin': r['corpus']['origin'], 'g1_locked': r['g1']['locked'], 'g1_engine': r['g1'].get('engine'),
       'summary_consistent': r['g1']['summary_table_consistent'], 'cases': []}
for q in r['cases']:
    out['cases'].append({'entry': q['entry']['id'], 'g1_positive': q['g1_positive'], 'g1_engine': q['g1_engine'], 'gate': q['publication_gate'].get('decision') if isinstance(q['publication_gate'], dict) else q['publication_gate']})
try:
    b = corpus.benchmark(); out['benchmark'] = {k: v for k, v in b.items() if not isinstance(v, (list, dict))} if isinstance(b, dict) else str(b)
except Exception as e: out['benchmark'] = 'ERR ' + repr(e)
print(json.dumps(out, ensure_ascii=False, indent=1, default=str))
