'use strict';
// SYNTHETIC hostile samples reproducing the independent security audit. Every URL is .invalid; nothing here is evidence.
window.BANLAG_SAMPLES = [
  {name: 'Forged “SerpApi live capture”', note: 'Audit CRITICAL 1: self-declared SerpApi origin, captured_at="tomorrow", no provider IDs, organic snippet with no same-search binding.',
   payload: {source_kind: 'SERPAPI_LIVE_CAPTURE', captured_at: 'tomorrow', query: 'anything at all', ingredients: ['amoxicillin', 'serratiopeptidase'],
     ai_overview: {ai_overview: {text_blocks: [{type: 'paragraph', snippet: 'Amoxicillin + serratiopeptidase is commonly prescribed.'}], references: []}},
     google: {organic_results: [{position: 1, title: 'SYNTHETIC', link: 'https://gov.example.invalid/n', snippet: 'Government prohibits amoxicillin + serratiopeptidase'}]}}},
  {name: 'Cross-surface citation join', note: 'Audit CRITICAL 2: the AI Overview cites nothing; AI Mode cites a page; imported page text asserts a ban.',
   payload: {source_kind: 'BROWSER_RESEARCH', captured_at: '2026-10-10T02:00:00+05:30', query: 'amoxicillin serratiopeptidase uses', ingredients: ['amoxicillin', 'serratiopeptidase'],
     ai_overview: {ai_overview: {text_blocks: [{type: 'paragraph', snippet: 'Amoxicillin + serratiopeptidase is commonly prescribed.'}], references: []}},
     ai_mode: {text_blocks: [{type: 'paragraph', snippet: 'This combination was banned in India.', reference_indexes: [0]}], references: [{index: 0, link: 'https://gov.example.invalid/notice'}]},
     cited_page_captures: [{url: 'https://gov.example.invalid/notice', capture_time: 'x', capture_method: 'x', source_text: 'Section 26A prohibits amoxicillin + serratiopeptidase'}]}},
  {name: 'Self-asserted cited-page text', note: 'Audit CRITICAL 3: a claim-bound citation URL plus invented source_text, capture_time and capture_method.',
   payload: {source_kind: 'BROWSER_RESEARCH', captured_at: '2026-10-10T02:00:00+05:30', query: 'amoxicillin serratiopeptidase uses', ingredients: ['amoxicillin', 'serratiopeptidase'],
     ai_overview: {ai_overview: {text_blocks: [{type: 'paragraph', snippet: 'Amoxicillin + serratiopeptidase is commonly prescribed.', reference_indexes: [0]}], references: [{index: 0, link: 'https://fiction.invalid/p'}]}},
     cited_page_captures: [{url: 'https://fiction.invalid/p', capture_time: 'made up', capture_method: 'made up', source_text: 'Section 26A prohibits amoxicillin + serratiopeptidase'}]}},
  {name: 'Adjacent unrelated ban', note: 'Audit HIGH 4: the ingredients in one sentence, a ban on a different product in the next.',
   payload: {source_kind: 'BROWSER_RESEARCH', captured_at: '2026-10-10T02:00:00+05:30', query: 'amoxicillin serratiopeptidase uses', ingredients: ['amoxicillin', 'serratiopeptidase'],
     ai_overview: {ai_overview: {text_blocks: [{type: 'paragraph', snippet: 'Amoxicillin + serratiopeptidase is commonly prescribed.', reference_indexes: [0]}], references: [{index: 0, link: 'https://fiction.invalid/p'}]}},
     cited_page_captures: [{url: 'https://fiction.invalid/p', capture_time: 'x', capture_method: 'x', source_text: 'Amoxicillin + serratiopeptidase is an ingredient combination. A ban on a completely different product was announced.'}]}},
  {name: 'Unrelated ban must not hide an omission', note: 'V0.1 gap: any ban word anywhere suppressed the finding. Claim-level reading keeps the omission.',
   payload: {source_kind: 'SYNTHETIC_TEST', captured_at: 'SYNTHETIC', query: 'amoxicillin serratiopeptidase uses', ingredients: ['amoxicillin', 'serratiopeptidase'],
     ai_overview: {ai_overview: {text_blocks: [{type: 'paragraph', snippet: 'Amoxicillin + serratiopeptidase is commonly prescribed for infections. Separately, a different combination product was banned in India.'}], references: []}}}}
];
