import sys, json; sys.stdout.reconfigure(encoding='utf-8'); sys.path.insert(0, '.')
from banlag.engine import evaluate_run
r = evaluate_run('run-20261010T024515Z-9415e2', 'captures/store')
out = {'origin': r['origin'], 'tier': r['evidence_tier'], 'verified': r['verified_evidence_tier'], 'replay': r['replay_evidence_tier'],
       'gate': r['publication_gate']['decision'], 'answers': []}
for a in r['answers']:
    coh = a.get('citation_coherence') or {}
    out['answers'].append({'surface': a['surface'], 'label': a['prereg_label'], 'tier': a['tier'], 'trace': a['analysis']['decision_trace'],
        'restrictions': [{k: v for k, v in c['restriction'].items() if k in ('binding', 'jurisdiction', 'hedged', 'negated', 'revoked', 'historical', 'proposed')} | {'id': c['id']} for c in a['analysis']['claims'] if 'restriction' in c],
        'coh_status': coh.get('status'), 'refs': [(x['index'], x['relation'], x['ingredients'], x['registry_entry'], x['mentions_restriction']) for x in coh.get('references', [])],
        'findings': [(f['type'], f['claim_id'], [(s['index'], s['entry']) for s in f.get('other_notice_sources', [])], [s['index'] for s in f.get('unresolved_sources', [])], [(s['index'], s.get('relation')) for s in f.get('sources', [])]) for f in coh.get('findings', [])]})
print(json.dumps(out, ensure_ascii=False, indent=1))
