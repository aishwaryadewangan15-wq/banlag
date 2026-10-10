"""Third developer batch, written after all fixes, run ONCE, results reported as-is (not used for tuning before freeze)."""
import sys
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, '.')
from banlag.engine import evaluate

ING = ['amoxicillin', 'serratiopeptidase']
X = 'Amoxicillin and Serratiopeptidase'
LEAD = X + ' tablets are prescribed for dental infections.'


def run(text, org=None):
    p = {'source_kind': 'SYNTHETIC_TEST', 'query': 'q', 'ingredients': ING,
         'google': {'search_metadata': {'id': 'S1'}, 'search_parameters': {'q': 'q'}, 'organic_results': org or [],
                    'ai_overview': {'text_blocks': [{'type': 'paragraph', 'snippet': text}], 'references': []}}}
    r = evaluate(p)
    return r['answers'][0]['prereg_label'], r['evidence_tier']


def org(s):
    return [{'position': 1, 'title': 'Update', 'link': 'https://u.example.invalid/x', 'snippet': s}]


cases = [
    ('add', LEAD + ' Some of these tablets are also loaded with lactobacillus.', 'nonE'),
    ('add', LEAD + ' The tablet also has a third active, bromelain.', 'nonE'),
    ('add', LEAD + ' Clavulanic acid is part of the same tablet.', 'nonE'),
    ('add', LEAD + ' Its third ingredient, trypsin, reduces swelling.', 'nonE'),
    ('ctrl', LEAD + ' Serratiopeptidase is an enzyme that reduces swelling.', 'E'),
    ('ctrl', LEAD + ' Clavulanic acid is a different medicine often given with amoxicillin.', 'E'),
    ('ctrl', LEAD + ' Take the tablets after meals with water.', 'E'),
    ('ent', LEAD + ' In India, the version with lactobacillus is prohibited.', 'nonD'),
    ('ent', LEAD + ' The prohibition in India covers amoxicillin with bromhexine, not this pair.', 'nonD'),
    ('neg', LEAD + ' Neither India nor any other country has banned this combination.', 'nonD'),
    ('neg', LEAD + ' It is a myth that this combination is banned in India.', 'nonD'),
    ('neg', LEAD + ' This combination may soon be prohibited in India.', 'nonD'),
    ('neg', LEAD + ' This combination is prohibited in India for veterinary use only.', 'nonD'),
    ('pos', LEAD + ' However, this combination is prohibited in India.', 'D'),
    ('pos', LEAD + ' This combination has been prohibited in India since 2026.', 'D'),
    ('t2', LEAD, 'T1', X + ' combination is banned in India, says a social media post.'),
    ('t2', LEAD, 'T1', X + ' was prohibited in India, but the Supreme Court stayed the notification.'),
    ('t2', LEAD, 'T1', X + ' is banned in India. The ban covers the version that also contains lactobacillus.'),
    ('t2pos', LEAD, 'T2', 'The Central Government has prohibited the manufacture, sale and distribution of the fixed dose combination of ' + X + ' for human use.'),
]
n = 0
for c in cases:
    g, text, want = c[0], c[1], c[2]
    lt = run(text, org(c[3])) if len(c) > 3 else run(text)
    ok = {'nonE': lt[0] != 'E', 'E': lt == ('E', 1), 'nonD': lt[0] != 'D', 'D': lt[0] == 'D', 'T1': lt == ('E', 1), 'T2': lt == ('E', 2)}[want]
    n += ok
    print('PASS' if ok else 'FAIL', g, want, lt, '|', (c[3] if len(c) > 3 else text)[len(LEAD) + 1 if len(c) == 3 else 0:][:110])
print(f'\nbatch3 (single run): {n} pass / {len(cases)}')
