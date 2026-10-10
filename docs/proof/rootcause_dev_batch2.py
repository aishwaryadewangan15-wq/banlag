"""Second developer batch, written AFTER the fixes and run once without tuning. Not independent; reported as-is."""
import sys
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, '.')
from banlag.engine import evaluate

ING = ['dicyclomine', 'paracetamol', 'clidinium bromide']
X = 'dicyclomine, paracetamol and clidinium bromide'
LEAD = 'The combination of ' + X + ' is commonly prescribed for abdominal pain.'
rows = []


def run(text, org=None):
    p = {'source_kind': 'SYNTHETIC_TEST', 'query': 'q', 'ingredients': ING,
         'google': {'search_metadata': {'id': 'S1'}, 'search_parameters': {'q': 'q'}, 'organic_results': org or [],
                    'ai_overview': {'text_blocks': [{'type': 'paragraph', 'snippet': text}], 'references': []}}}
    r = evaluate(p)
    return r['answers'][0]['prereg_label'], r['evidence_tier']


def org(s):
    return [{'position': 1, 'title': 'Notice', 'link': 'https://n.example.invalid/x', 'snippet': s}]


cases = [
    # (group, text appended to LEAD or full organic snippet, mode, expectation)
    ('add', 'Many tablets of this kind also contain caffeine.', 'ans', 'safe'),   # variability-ish: E would be wrong only if it is the same product
    ('add', 'This particular brand adds caffeine to the three.', 'ans', 'nonE'),
    ('add', 'It is sold together with omeprazole in one strip.', 'ans', 'any'),
    ('add', 'Its full composition is dicyclomine, paracetamol, clidinium bromide and simethicone.', 'ans', 'nonE'),
    ('add', 'Apart from the three listed, the tablet holds omeprazole.', 'ans', 'nonE'),
    ('add', 'There is also omeprazole in each tablet.', 'ans', 'nonE'),
    ('ctrl', 'Each tablet holds the three ingredients in fixed doses.', 'ans', 'E'),
    ('ctrl', 'It is also sold under several brand names.', 'ans', 'E'),
    ('ctrl', 'Doctors sometimes add omeprazole as a separate tablet.', 'ans', 'E'),
    ('ctrl', 'Unlike omeprazole, it does not reduce stomach acid.', 'ans', 'E'),
    ('ent', 'In India, omeprazole sachets were banned, not this combination.', 'ans', 'nonD'),
    ('ent', 'Rifaximin is prohibited in India; this combination is sold in Canada.', 'ans', 'nonD'),
    ('ent', 'Although this combination is sold in India, Bangladesh has prohibited it.', 'ans', 'nonD'),
    ('pos', 'This combination has been banned in India since June 2026.', 'ans', 'D'),
    ('pos', 'Since 11 June 2026, its manufacture, sale and distribution have been prohibited in India.', 'ans', 'any'),
    ('neg', 'Whether this combination is banned in India is not clear.', 'ans', 'nonD'),
    ('neg', 'Contrary to rumours, this combination is not prohibited in India.', 'ans', 'nonD'),
    ('neg', 'This combination is banned in India if it contains more than 10 mg of dicyclomine.', 'ans', 'nonD'),
    ('neg', 'This combination is banned in India unless a doctor prescribes it.', 'ans', 'nonD'),
    ('neg', 'The ministry proposed banning this combination in India.', 'ans', 'nonD'),
    ('neg', 'This combination was banned in India until 2019.', 'ans', 'nonD'),
    ('neg', 'This combination was banned in India, though the ban was later stayed by a court.', 'ans', 'nonD'),
    ('t2neg', 'Bangladesh prohibited ' + X + ' in 2026; India has not.', 'org', 'T1'),
    ('t2neg', X + ' is prohibited in India for children under 12.', 'org', 'T1'),
    ('t2neg', 'Earlier reports said ' + X + ' was banned in India, but that was wrong.', 'org', 'T1'),
    ('t2neg', X + ' is prohibited in India. Each tablet also has 20 mg of omeprazole.', 'org', 'T1'),
    ('t2pos', 'The Government of India has prohibited the manufacture, sale and distribution of ' + X + ' for human use.', 'org', 'T2'),
    ('t2pos', 'Gazette notification S.O. 3078(E) prohibits ' + X + ' in India.', 'org', 'T2'),
]
for g, s, mode, want in cases:
    lt = run(LEAD + ' ' + s) if mode == 'ans' else run(LEAD, org(s))
    ok = {'nonE': lt[0] != 'E', 'E': lt == ('E', 1), 'nonD': lt[0] != 'D', 'D': lt[0] == 'D', 'T1': lt == ('E', 1), 'T2': lt == ('E', 2),
          'safe': lt[0] != 'D', 'any': True}[want]
    rows.append((g, s, lt, want, ok))
    print('PASS' if ok else 'FAIL', g, want, lt, '|', s[:110])
print(f"\nbatch2: {sum(r[4] for r in rows)} pass / {len(rows)}")
