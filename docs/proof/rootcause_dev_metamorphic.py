"""Developer metamorphic probes (written by Claude; NOT the independent evaluator's hidden set). cwd = APP."""
import sys
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, '.')
from banlag.engine import evaluate
from banlag.citations import reference_formulation, relation_to

ING = ['dicyclomine', 'paracetamol', 'clidinium bromide']
X = 'Dicyclomine, Paracetamol and Clidinium Bromide'
LEAD = X + ' are used to treat abdominal cramps.'
BAN = 'The Central Government has prohibited the fixed dose combination of ' + X + ' for human use.'
rows = []


def run(text, org=None, refs=None, snaps=None):
    p = {'source_kind': 'SYNTHETIC_TEST', 'query': 'q', 'ingredients': ING,
         'google': {'search_metadata': {'id': 'S1'}, 'search_parameters': {'q': 'q'}, 'organic_results': org or [],
                    'ai_overview': {'text_blocks': [{'type': 'paragraph', 'snippet': text, 'reference_indexes': [0] if refs else []}], 'references': refs or []}}}
    r = evaluate(p, verified_snapshots=snaps)
    return r['answers'][0]['prereg_label'], r['evidence_tier']


def org(s, url='https://news.example.invalid/r'):
    return [{'position': 1, 'title': 'Report', 'link': url, 'snippet': s}]


def t3(s):
    url = 'https://ref.example.invalid/p'
    return run(LEAD, refs=[{'index': 0, 'link': url}], snaps=[{'url': url, 'text': s, 'sha256': '0' * 64}])[1]


def check(group, name, got, ok):
    rows.append((group, name, got, ok))


# A. composition: additions must not stay exact (want B or F, tier 0); controls stay E/T1
for t in ['It has omeprazole too.', 'Omeprazole is added to this tablet.', 'Besides these three, it contains omeprazole.',
          'Its composition also includes omeprazole.', 'The tablet is also formulated with simethicone.',
          'Each capsule contains these three drugs plus domperidone.', 'This FDC also includes a fourth drug, rifaximin.',
          'It is made with dicyclomine, paracetamol, clidinium bromide and omeprazole.', 'The product contains four active ingredients.',
          'One of its ingredients is omeprazole.', 'Its ingredients also include charcoal.', 'In addition, each tablet carries 20 mg of omeprazole.']:
    lt = run(LEAD + ' ' + t)
    check('A-add', t, lt, lt[0] in ('B', 'F') and lt[1] == 0)
for t in ['A version with omeprazole is also sold.', 'Patients are sometimes also prescribed omeprazole separately.',
          'It should be taken with food.', 'It is available as 10 mg/325 mg/2.5 mg tablets.', 'Omeprazole, a separate drug, treats reflux.',
          'The combination contains three active ingredients that work together.', 'It does not contain omeprazole.',
          'Each tablet contains lactose as an excipient.']:
    lt = run(LEAD + ' ' + t)
    check('A-ctrl', t, lt, lt == ('E', 1))
# B. entity binding: India restriction on another entity must not become D / T2 / T3
for s in [X + ' is legal in India, but chlordiazepoxide combinations are banned in India.', 'Omeprazole is banned in India, unlike this combination.',
          'India has banned omeprazole, while this combination remains available.', 'Canada banned this combination; India banned omeprazole.',
          'This combination is sold in India, whereas a different combination is prohibited there.']:
    lt = run(LEAD + ' ' + s)
    check('B-ent', s, lt, lt[0] != 'D')
for s in [X + ' is legal in India, but chlordiazepoxide combinations are banned in India.', 'Omeprazole is banned in India, unlike ' + X + '.',
          'India has banned omeprazole, while ' + X + ' remains available.']:
    got = (run(LEAD, org(s))[1], t3(s))
    check('B-tier', s, got, got == (1, 1))
for s in ['India has banned this combination.', X + ' is now prohibited in India.', 'In India, this combination has been prohibited since June 2026.']:
    lt = run(LEAD + ' ' + s)
    check('B-pos', s, lt, lt[0] == 'D')
for s in ['India has banned ' + X + '.', BAN]:
    got = (run(LEAD, org(s))[1], t3(s))
    check('B-tierpos', s, got, got == (2, 3))
# C. polarity / conditions
for s in ['There is no ban on this combination in India.', 'Reports that this combination is banned in India are false.',
          'Claims that this combination is banned in India are unfounded.', 'This combination is banned in India only for paediatric use.',
          'This combination is banned in India except for export.', 'This combination would have been banned in India.',
          'This combination might be banned in India.', 'This combination is not banned in India; it was banned in Canada.',
          'Nobody has banned this combination in India.', 'It is false that this combination is prohibited in India.',
          'This combination is prohibited in India where clinically inappropriate.']:
    lt = run(LEAD + ' ' + s)
    check('C-neg', s, lt, lt[0] != 'D')
for s in ['Yes, this combination is banned in India.', 'This combination is banned in India, according to the Gazette notification.',
          'The Government of India has prohibited this combination.', 'This combination is banned in India and cannot be sold.']:
    lt = run(LEAD + ' ' + s)
    check('C-pos', s, lt, lt[0] == 'D')
# D. chronology
for s, want in [('This combination was banned in India in 2016; the ban was quashed in 2017.', 'NOT_D'),
                ('The ban on this combination in India was lifted, but it is now banned again in India.', 'D'),
                ('The 2016 ban on this combination was struck down, but the June 2026 notification prohibits this combination in India.', 'D'),
                ('This combination is prohibited in India. The ban on omeprazole was later revoked.', 'D'),
                ('This combination was prohibited in India. It was later revoked.', 'NOT_D')]:
    lt = run(LEAD + ' ' + s)
    check('D-chron', s, lt, (lt[0] == 'D') == (want == 'D'))
# E. citation views
T = 'Dicyclomine + Paracetamol + Clidinium Bromide Tablets'
for name, ref, want in [('snippet later known extra', {'title': T, 'snippet': X + ' tablets. Each tablet also contains simethicone.'}, ('CONFLICTING_VIEWS', 'MULTIPLE_FORMULATIONS')),
                        ('slug suffix unknown', {'title': T, 'snippet': '', 'link': 'https://x.invalid/dicyclomine-paracetamol-clidinium-bromide-magnesium-oxide-tablets'}, ('UNRECOGNISED_COMPONENT', 'CONFLICTING_VIEWS')),
                        ('slug furniture only', {'title': T, 'snippet': '', 'link': 'https://x.invalid/dicyclomine-paracetamol-clidinium-bromide-tablets-uses-price'}, ('EXACT',)),
                        ('snippet pharmacology control', {'title': T, 'snippet': X + ' tablets relieve cramps. Dicyclomine relaxes gut muscle.'}, ('EXACT',))]:
    f = reference_formulation(dict({'link': 'https://x.invalid/p'}, **ref, index=0))
    rel = relation_to(set(ING), f)
    check('E-cite', name, rel, rel in want)
fails = [r for r in rows if not r[3]]
for g, n, got, ok in rows:
    print('PASS' if ok else 'FAIL', g, got, '|', n[:110])
print(f'\nmetamorphic: {len(rows) - len(fails)} pass / {len(rows)}')
