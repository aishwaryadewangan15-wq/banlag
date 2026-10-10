"""Untested phrasings, to report residual risk honestly (not added to the suite). cwd = APP."""
import sys
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, '.')
from banlag.engine import evaluate

ING = ['dicyclomine', 'paracetamol', 'clidinium bromide']
LEAD = 'Dicyclomine, Paracetamol and Clidinium Bromide are used to treat abdominal cramps.'


def lt(text, organic=None):
    p = {'source_kind': 'SYNTHETIC_TEST', 'query': 'q', 'ingredients': ING,
         'google': {'search_metadata': {'id': 'S1'}, 'search_parameters': {'q': 'q'}, 'organic_results': organic or [],
                    'ai_overview': {'text_blocks': [{'type': 'paragraph', 'snippet': text}], 'references': []}}}
    r = evaluate(p)
    return r['answers'][0]['prereg_label'], r['evidence_tier']


org = lambda s: [{'position': 1, 'title': 'n', 'link': 'https://news.example.invalid/n', 'snippet': s}]
print('composition (safe = B):')
for t in ['Dicyclomine, Paracetamol and Clidinium Bromide alongside omeprazole are used to treat abdominal cramps.',
          'Dicyclomine, Paracetamol and Clidinium Bromide co-formulated with omeprazole are used to treat abdominal cramps.',
          'Dicyclomine, Paracetamol and Clidinium Bromide combined with omeprazole are used to treat abdominal cramps.',
          'Dicyclomine, Paracetamol and Clidinium Bromide, and omeprazole too, are used to treat abdominal cramps.',
          'Dicyclomine, Paracetamol and Clidinium Bromide are used to treat abdominal cramps. Omeprazole is also in it.']:
    print(' ', lt(t), t)
print('restriction status (safe = not D):')
for s in ['This combination was banned in India until the Supreme Court struck down the notification.',
          'This combination is banned in India, according to a 2019 rumour that was never confirmed.',
          'Some reports say this combination is banned in India.',
          'This combination is banned in Nepal and sold in India.',
          'This combination is banned in Kerala.']:
    print(' ', lt(LEAD + ' ' + s), s)
print('T2 (safe = tier 1):')
for s in ['U.S. regulators have banned Dicyclomine, Paracetamol and Clidinium Bromide.',
          'Dicyclomine, Paracetamol and Clidinium Bromide is banned in Nepal, a neighbour of India.']:
    print(' ', lt(LEAD, org(s)), s)
