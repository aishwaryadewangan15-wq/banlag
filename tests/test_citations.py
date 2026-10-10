"""Citation-formulation coherence and truncation handling. Synthetic SerpApi-shaped fixtures (.invalid URLs) that mirror
patterns first seen in a live capture; they are not the evidence."""
import unittest

from banlag.citations import reference_formulation, relation_to
from banlag.claims import restriction_statements
from banlag.engine import evaluate
from banlag.legal import entry_by_id

F08 = ['dicyclomine', 'paracetamol', 'clidinium bromide']
TRUNC = {'index': 1, 'title': 'Regulator notified regarding the Prohibition of', 'source': 'Reg A',
         'link': 'https://reg-a.example.invalid/updates/article/1/notified-regarding-the-prohibition-of-fixed-dose-combination-of-/',
         'snippet': 'The Government has prohibited the manufacture, sale, and distribution of the fixed dose combination (FDC) comprising Dicyclomine + Paracetamol + Clidinium Bromide ...'}
SUPER = {'index': 2, 'title': 'Prohibition on Manufacture, Sale and Distribution of Fixed Dose ...', 'source': 'Reg B',
         'link': 'https://reg-b.example.invalid/legal-update/prohibition-of-fixed-dose-combination-of-dicyclomine-paracetamol-clidinium-bromide-chlordiazepoxide-1/',
         'snippet': 'Prohibition on Manufacture, Sale and Distribution of Fixed Dose Combination of Dicyclomine + Paracetamol + Clidinium Bromide + Chlordiazepoxide 11-Jun-2026 | S.O. ...'}
EXACT_BAN = {'index': 3, 'title': 'Prohibition of Fixed Dose Combination of Dicyclomine + Paracetamol + Clidinium Bromide', 'source': 'Reg C',
             'link': 'https://reg-c.example.invalid/x', 'snippet': 'Central Government has prohibited the manufacture, sale and distribution of the fixed dose combination Dicyclomine + Paracetamol + Clidinium Bromide for human use.'}
PRODUCT = {'index': 0, 'title': 'Clidinium Bromide Dicyclomine HCl and Paracetamol Tablets', 'source': 'Maker', 'link': 'https://maker.example.invalid/p', 'snippet': 'A combination of three medicines.'}
TWO = {'index': 4, 'title': 'dicyclomine-paracetamol | View uses', 'source': 'Pharmacy', 'link': 'https://pharmacy.example.invalid/salt/dicyclomine-paracetamol', 'snippet': ''}


def payload(restriction_refs, use_refs=(0,), refs=(PRODUCT, TRUNC, SUPER)):
    blocks = [
        {'type': 'paragraph', 'snippet': 'The combination of Dicyclomine, Paracetamol, and Clidinium Bromide is used to relieve abdominal cramps.', 'reference_indexes': list(use_refs)},
        {'type': 'paragraph', 'snippet': 'Note: In India, the Central Government has prohibited certain fixed-dose combinations containing multiple anticholinergics like dicyclomine and clidinium bromide together.',
         'reference_indexes': list(restriction_refs)},
        {'type': 'list', 'reference_indexes': [4], 'list': [{'snippet': 'Paracetamol: An analgesic.'}]},
    ]
    return {'source_kind': 'SYNTHETIC_TEST', 'captured_at': 'SYNTHETIC', 'query': 'dicyclomine paracetamol clidinium bromide uses', 'ingredients': F08,
            'ai_overview': {'ai_overview': {'text_blocks': blocks, 'references': list(refs) + [TWO]}}}


class ReferenceFormulation(unittest.TestCase):
    def test_truncated_snippet_is_only_a_lower_bound(self):
        f = reference_formulation(TRUNC)
        self.assertTrue(f['truncated'])
        self.assertIsNone(f['registry_entry'])
        self.assertEqual(relation_to(set(F08), f), 'EXACT_LOWER_BOUND')

    def test_superset_reference_resolves_to_other_notice(self):
        f = reference_formulation(SUPER)
        self.assertEqual((f['registry_entry'], f['truncated'], f['mentions_restriction']), ('F09', False, True))
        self.assertEqual(relation_to(set(F08), f), 'SUPERSET')

    def test_salt_name_in_title_still_exact(self):
        self.assertEqual(relation_to(set(F08), reference_formulation(PRODUCT)), 'EXACT')

    def test_hyphenated_slug_title(self):
        self.assertEqual(reference_formulation(TWO)['ingredients'], ['dicyclomine', 'paracetamol'])

    def test_truncated_restriction_sentence_never_counts_as_exact(self):
        e = entry_by_id('F08')
        self.assertEqual(restriction_statements(TRUNC['snippet'], e), [])
        india_trunc = 'The Government of India has prohibited the fixed dose combination comprising Dicyclomine + Paracetamol + Clidinium Bromide ...'
        self.assertEqual(restriction_statements(india_trunc, e), [])
        self.assertTrue(restriction_statements(india_trunc, e, include_truncated=True)[0]['scope_truncated'])
        self.assertEqual(len(restriction_statements(EXACT_BAN['snippet'], e)), 1)


class ClaimCoherence(unittest.TestCase):
    def coh(self, **kw):
        r = evaluate(payload(**kw))
        return r['answers'][0], r['answers'][0]['citation_coherence']

    def test_restriction_sourced_to_a_different_notice_is_reported(self):
        a, coh = self.coh(restriction_refs=(1, 2))
        self.assertEqual(a['prereg_label'], 'F')
        f = [x for x in coh['findings'] if x['type'] == 'RESTRICTION_CITATIONS_DO_NOT_NAME_THIS_NOTICE']
        self.assertEqual(len(f), 1)
        self.assertEqual([(s['entry'], s['notice']) for s in f[0]['other_notice_sources']], [('F09', 'S.O. 3071(E)')])
        self.assertEqual([s['index'] for s in f[0]['unresolved_sources']], [1])

    def test_no_finding_when_a_cited_reference_names_this_exact_ban(self):
        _, coh = self.coh(restriction_refs=(3,), refs=(PRODUCT, TRUNC, SUPER, EXACT_BAN))
        self.assertFalse([x for x in coh['findings'] if x['type'] == 'RESTRICTION_CITATIONS_DO_NOT_NAME_THIS_NOTICE'])

    def test_current_use_claim_citing_a_two_drug_page_is_reported(self):
        _, coh = self.coh(restriction_refs=(1,), use_refs=(4,))
        f = [x for x in coh['findings'] if x['type'] == 'CURRENT_USE_CLAIM_CITES_OTHER_FORMULATION']
        self.assertEqual(f[0]['sources'][0]['relation'], 'SUBSET')

    def test_list_level_reference_indexes_are_inherited(self):
        a, coh = self.coh(restriction_refs=(1, 2))
        row = next(r for r in coh['claims'] if r['text'].startswith('An analgesic'))
        self.assertEqual([c['index'] for c in row['cited']], [4])

    def test_browser_style_answers_have_no_coherence_claims(self):
        r = evaluate({'source_kind': 'SYNTHETIC_TEST', 'ingredients': F08,
                      'ai_overview': {'ai_overview': {'text_blocks': [{'type': 'paragraph', 'snippet': 'The combination of dicyclomine, paracetamol and clidinium bromide is used to treat cramps.'}]}}})
        self.assertIsNone(r['answers'][0]['citation_coherence'])


if __name__ == '__main__':
    unittest.main()
