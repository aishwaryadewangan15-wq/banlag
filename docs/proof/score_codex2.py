"""Score Codex's second-audit probe outputs against explicit expected SAFE outcomes. Usage: score_codex2.py <hostile-results.json>"""
import json, sys
sys.stdout.reconfigure(encoding='utf-8')
rows = json.load(open(sys.argv[1], encoding='utf-8'))
POS_RESTRICT = 'The Central Government has prohibited the fixed dose combination of Dicyclomine, Paracetamol and Clidinium Bromide for human use.'
fails = 0
seen = {}
for r in rows:
    n = r['name']
    seen[n] = seen.get(n, 0) + 1
    k = seen[n]
    exp, ok = None, None
    if n == 'original_1_unknown_extra' or n.startswith('fresh_1_') and 'citation' not in n:
        exp, ok = 'label B/F (not exact), tier 0', r['label'] in ('B', 'F') and r['tier'] == 0
    elif n == 'original_1_citation':
        exp, ok = 'relation not EXACT', r['relation'] != 'EXACT'
    elif n == 'original_1_tier2':
        exp, ok = 'E with tier 1 (no T2 from an altered composition)', (r['label'], r['tier']) == ('E', 1)
    elif n == 'fresh_1_citation_tie':
        snip = r['ref']['snippet']
        if snip.endswith('...'):
            exp, ok = 'EXACT supported by complete title; truncated snippet recorded, not contradicting', r['relation'] in ('EXACT',) and r['formulation'].get('truncated_views') == ['snippet']
        else:
            exp, ok = 'not EXACT (conflicting / added component)', r['relation'] != 'EXACT'
    elif n.startswith('original_4_'):
        exp, ok = 'not D (negated/revoked)', r['label'] != 'D'
    elif n.startswith('original_5_'):
        exp, ok = 'tier <= 1', r['tier'] <= 1
    elif n in ('original_2_body_tamper', 'original_2_manifest_missing', 'fresh_2_body_and_manifest_rehashed', 'fresh_2_null_manifest'):
        st = r['integrity']['status'] if isinstance(r.get('integrity'), dict) else r.get('error')
        exp, ok = 'integrity FAILED, nothing eligible', st == 'FAILED' and (r.get('q02_g1_positive') in (False, None))
    elif n.startswith('fresh_4_'):
        if n.endswith('are prohibited in India.'):
            exp, ok = 'POSITIVE CONTROL: D', r['label'] == 'D'
        else:
            exp, ok = 'not D (negated/conditional/proposed/revoked/historical)', r['label'] != 'D'
    elif n.startswith('fresh_5_'):
        is_pos = n.endswith(POS_RESTRICT)
        t3 = n.startswith('fresh_5_tier3_')
        if is_pos:
            exp, ok = 'POSITIVE CONTROL: tier ' + ('3' if t3 else '2'), r['tier'] == (3 if t3 else 2)
        else:
            exp, ok = 'tier 1 (not a current Indian restriction on the exact set)', r['tier'] == 1
    elif n == 'original_3_forged_keyless_archive':
        exp, ok = 'verified 0, WITHHOLD', r['verified_tier'] == 0 and r['gate']['decision'] == 'WITHHOLD'
    elif n.startswith('original_P2_'):
        coh = r.get('coherence') or {}
        exp, ok = 'POSITIVE CONTROL E/T1; coherence never "coherent"', (r['label'], r['tier']) == ('E', 1) and 'COHERENT' not in str(coh.get('status', ''))
    else:
        exp, ok = '?', None
    fails += ok is False
    print(f"{'PASS' if ok else 'FAIL' if ok is False else '????'}  {n[:88]:<88} expect: {exp}")
print(f'\nFAILURES: {fails} / {len(rows)}')
