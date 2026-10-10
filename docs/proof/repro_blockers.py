"""Reproduce the four audit blockers against pristine V0.1 (no network). Usage: python repro_v01_blockers.py <project_root>"""
import json, sys
sys.path.insert(0, sys.argv[1])
from banlag.core import evaluate

def show(name, r):
    print(f"--- {name}")
    print("  evidence_tier:", r['evidence_tier'], "| source_kind:", r['source_kind'], "| captured_at:", r['captured_at'])
    print("  cited:", json.dumps(r['cited_pages']))

# C1: self-declared SerpApi capture, bogus timestamp, no search metadata
c1 = {'source_kind': 'SERPAPI_LIVE_CAPTURE', 'captured_at': 'tomorrow', 'query': 'anything at all',
      'ingredients': ['amoxicillin', 'serratiopeptidase'],
      'ai_overview': {'ai_overview': {'text_blocks': [{'snippet': 'Amoxicillin + serratiopeptidase is commonly prescribed.'}], 'references': []}},
      'google': {'organic_results': [{'snippet': 'Government prohibits amoxicillin + serratiopeptidase'}]}}
show('C1 forged SERPAPI_LIVE_CAPTURE, captured_at=tomorrow, no search_metadata', evaluate(c1))

# C2: unwarned AIO with NO citations + AI Mode citing a page; cited page captured
c2 = {'source_kind': 'BROWSER_RESEARCH', 'captured_at': '2026-10-10',
      'ingredients': ['amoxicillin', 'serratiopeptidase'],
      'ai_overview': {'ai_overview': {'text_blocks': [{'snippet': 'Amoxicillin + serratiopeptidase is commonly prescribed.'}], 'references': []}},
      'ai_mode': {'text_blocks': [{'snippet': 'This combination was banned in India.'}], 'references': [{'index': 0, 'link': 'https://gov.example.invalid/notice'}]},
      'cited_page_captures': [{'url': 'https://gov.example.invalid/notice', 'capture_time': 'x', 'capture_method': 'x',
                               'source_text': 'Section 26A prohibits amoxicillin + serratiopeptidase'}]}
show('C2 cross-surface join (AIO has zero citations; AI Mode cites the page)', evaluate(c2))

# C3: fabricated cited-page text on a .invalid URL
c3 = {'source_kind': 'BROWSER_RESEARCH', 'captured_at': '2026-10-10',
      'ingredients': ['amoxicillin', 'serratiopeptidase'],
      'ai_overview': {'ai_overview': {'text_blocks': [{'snippet': 'Amoxicillin + serratiopeptidase is commonly prescribed.'}], 'references': [{'index': 0, 'link': 'https://fiction.invalid/p'}]}},
      'cited_page_captures': [{'url': 'https://fiction.invalid/p', 'capture_time': 'made up', 'capture_method': 'made up',
                               'source_text': 'Section 26A prohibits amoxicillin + serratiopeptidase'}]}
show('C3 self-asserted source_text on fictional URL', evaluate(c3))

# H4: ingredients in one sentence, a ban on a different product in another
h4 = json.loads(json.dumps(c3))
h4['cited_page_captures'][0]['source_text'] = 'Amoxicillin + serratiopeptidase is an ingredient combination. A ban on a completely different product was announced.'
show('H4 adjacent unrelated ban counted as exact restriction', evaluate(h4))
