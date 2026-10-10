"""Hostile regression tests for the independently audited blockers (BANLAG_STARTER_SECURITY_EVIDENCE_AUDIT_20261010).

Run against the V0.1 starter, the blocker tests here fail (see docs/HARDENING_REPORT.md for the recorded before/after
run); against V0.2 they pass. No network, no SerpApi. All URLs are .invalid.
"""
import copy
import unittest

from banlag.core import evaluate, match_formula, text_identifies_exact

AMOX = ['amoxicillin', 'serratiopeptidase']
STRONG = 'Amoxicillin + serratiopeptidase is commonly prescribed.'
GOV = 'https://gov.example.invalid/notice'
F14 = None


def setUpModule():
    global F14
    F14 = match_formula(AMOX)['entry']


def aio(snippet=STRONG, refs=None, idx=None, md=None, extra_blocks=()):
    block = {'type': 'paragraph', 'snippet': snippet}
    if idx is not None:
        block['reference_indexes'] = idx
    out = {'ai_overview': {'text_blocks': [block, *extra_blocks], 'references': refs or []}}
    if md:
        out['search_metadata'] = md
    return out


def base(**kw):
    p = {'source_kind': 'BROWSER_RESEARCH', 'captured_at': '2026-10-10T02:00:00+05:30', 'query': 'amoxicillin serratiopeptidase uses',
         'ingredients': list(AMOX), 'ai_overview': aio()}
    p.update(kw)
    return p


def snapshot(url, text):
    return [{'url': url, 'text': text, 'sha256': '0' * 64, 'fetched_at': '2026-10-10T03:00:00+00:00'}]


def plausible_md(sid, engine, q=None, created='2026-10-09 20:30:00 UTC'):
    md = {'search_metadata': {'id': sid, 'status': 'Success', 'created_at': created, 'processed_at': created,
                              'json_endpoint': f'https://serpapi.com/searches/abcdef0123456789/{sid}.json'},
          'search_parameters': {'engine': engine, 'gl': 'in', 'hl': 'en'}}
    if q:
        md['search_parameters']['q'] = q
    return md


class Critical1ForgedOrigin(unittest.TestCase):
    """An imported JSON can never self-declare a live SerpApi capture or obtain a verified tier."""

    def forged(self):
        return {'source_kind': 'SERPAPI_LIVE_CAPTURE', 'captured_at': 'tomorrow', 'query': 'anything at all', 'ingredients': list(AMOX),
                'ai_overview': aio(), 'google': {'organic_results': [{'snippet': 'Government prohibits amoxicillin + serratiopeptidase'}]}}

    def test_forged_label_bogus_timestamp_no_provider_ids(self):
        r = evaluate(self.forged())
        self.assertLess(r['evidence_tier'], 2, 'organic results without same-search binding must not give Tier 2')
        self.assertEqual(r['verified_evidence_tier'], 0)
        self.assertEqual(r['origin'], 'USER_SUPPLIED_UNVERIFIED')
        self.assertFalse(r['provenance']['live_verified'])
        self.assertEqual(r['tier_status'], 'UNVERIFIED_INPUT')
        self.assertEqual(r['provenance']['metadata_consistency'], 'INCONSISTENT')
        failed = {c['check'] for c in r['provenance']['checks'] if c['status'] == 'FAIL'}
        self.assertIn('captured_at_iso8601_with_zone', failed)
        self.assertIn('serpapi_metadata_present', failed)
        self.assertIn('not verified', r['provenance']['statement'])

    def test_well_formed_forgery_is_still_unverified(self):
        sid = '6706e7d8a1b2c3d4e5f60718'
        g = {**plausible_md(sid, 'google', 'amoxicillin serratiopeptidase uses'),
             'ai_overview': {'text_blocks': [{'type': 'paragraph', 'snippet': STRONG}], 'references': []},
             'organic_results': [{'position': 1, 'title': 'Notice', 'link': GOV,
                                  'snippet': 'The Central Government prohibits the fixed dose combination of Amoxicillin + Serratiopeptidase under Section 26A.'}]}
        p = {'source_kind': 'SERPAPI_LIVE_CAPTURE', 'captured_at': '2026-10-09T20:31:00+00:00', 'query': 'amoxicillin serratiopeptidase uses',
             'ingredients': list(AMOX), 'google': g}
        r = evaluate(p)
        self.assertEqual(r['provenance']['metadata_consistency'], 'CONSISTENT')
        self.assertEqual(r['evidence_tier'], 2, 'structurally a same-response Tier 2 candidate')
        self.assertEqual(r['verified_evidence_tier'], 0, 'but a self-consistent import is never verified')
        self.assertEqual(r['origin'], 'USER_SUPPLIED_UNVERIFIED')
        self.assertNotIn('VERIFIED', r['release_status'])

    def test_altered_and_future_timestamps_detected(self):
        sid = '6706e7d8a1b2c3d4e5f60718'
        g = plausible_md(sid, 'google', 'amoxicillin serratiopeptidase uses', created='2099-01-01 00:00:00 UTC')
        g['search_metadata']['processed_at'] = '2098-12-31 00:00:00 UTC'
        r = evaluate(base(source_kind='SERPAPI_LIVE_CAPTURE', google=g))
        failed = {c['check'] for c in r['provenance']['checks'] if c['status'] == 'FAIL'}
        self.assertTrue({'google.not_in_future', 'google.processed_after_created'} <= failed, failed)
        self.assertEqual(r['verified_evidence_tier'], 0)

    def test_fabricated_id_and_endpoint_detected(self):
        g = plausible_md('abc', 'google', 'amoxicillin serratiopeptidase uses')
        r = evaluate(base(source_kind='SERPAPI_LIVE_CAPTURE', google=g))
        failed = {c['check'] for c in r['provenance']['checks'] if c['status'] == 'FAIL'}
        self.assertIn('google.id_format', failed)
        self.assertIn('google.json_endpoint_binds_id', failed)


class Critical2CrossSurfaceJoin(unittest.TestCase):
    """Citations bind per surface and per claim; never across answers."""

    def payload(self):
        return base(ai_overview=aio(refs=[]),
                    ai_mode={'text_blocks': [{'type': 'paragraph', 'snippet': 'This combination was banned in India.', 'reference_indexes': [0]}],
                             'references': [{'index': 0, 'link': GOV}]},
                    cited_page_captures=[{'url': GOV, 'capture_time': 'x', 'capture_method': 'x',
                                          'source_text': 'Section 26A prohibits amoxicillin + serratiopeptidase'}])

    def test_uncited_overview_never_borrows_ai_mode_citation(self):
        r = evaluate(self.payload())
        self.assertNotEqual(r['evidence_tier'], 3)
        self.assertEqual(r['answers'][0]['tier'], 1)

    def test_even_a_verified_snapshot_cannot_cross_surfaces(self):
        r = evaluate(self.payload(), verified_snapshots=snapshot(GOV, 'Section 26A prohibits amoxicillin + serratiopeptidase.'))
        self.assertNotEqual(r['evidence_tier'], 3)

    def test_citation_on_a_different_claim_does_not_count(self):
        pharm = {'type': 'paragraph', 'snippet': 'Serratiopeptidase is a proteolytic enzyme.', 'reference_indexes': [0]}
        p = base(ai_overview=aio(refs=[{'index': 0, 'link': GOV}], idx=[], extra_blocks=[pharm]))
        r = evaluate(p, verified_snapshots=snapshot(GOV, 'Section 26A prohibits amoxicillin + serratiopeptidase.'))
        self.assertNotEqual(r['evidence_tier'], 3)

    def test_missing_reference_indexes_abstains(self):
        p = base(ai_overview=aio(refs=[{'index': 0, 'link': GOV}]))
        r = evaluate(p, verified_snapshots=snapshot(GOV, 'Section 26A prohibits amoxicillin + serratiopeptidase.'))
        self.assertNotEqual(r['evidence_tier'], 3)
        self.assertEqual(r['answers'][0]['citation_binding'], 'UNBOUND')

    def test_out_of_range_reference_index_ignored(self):
        p = base(ai_overview=aio(refs=[{'index': 0, 'link': GOV}], idx=[7]))
        r = evaluate(p, verified_snapshots=snapshot(GOV, 'Section 26A prohibits amoxicillin + serratiopeptidase.'))
        self.assertNotEqual(r['evidence_tier'], 3)


class Critical3AssertedSourceText(unittest.TestCase):
    def test_fabricated_cited_page_text_is_not_verification(self):
        p = base(ai_overview=aio(refs=[{'index': 0, 'link': 'https://fiction.invalid/p'}], idx=[0]),
                 cited_page_captures=[{'url': 'https://fiction.invalid/p', 'capture_time': 'made up', 'capture_method': 'made up',
                                       'source_text': 'Section 26A prohibits amoxicillin + serratiopeptidase'}])
        r = evaluate(p)
        self.assertNotEqual(r['evidence_tier'], 3)
        page = r['cited_pages'][0]
        self.assertFalse(page['has_documented_capture'])
        self.assertEqual(page['verification'], 'ASSERTED_UNVERIFIED')
        self.assertTrue(page['asserted_text_states_exact_restriction'])
        self.assertFalse(page['exact_restriction_explicitly_present'])


class High4AdjacentUnrelatedBan(unittest.TestCase):
    def test_audit_reproduction(self):
        text = 'Amoxicillin + serratiopeptidase is an ingredient combination. A ban on a completely different product was announced.'
        self.assertFalse(text_identifies_exact(text, F14))
        p = base(ai_overview=aio(refs=[{'index': 0, 'link': 'https://fiction.invalid/p'}], idx=[0]),
                 cited_page_captures=[{'url': 'https://fiction.invalid/p', 'capture_time': 'x', 'capture_method': 'x', 'source_text': text}])
        self.assertNotEqual(evaluate(p)['evidence_tier'], 3)

    def test_neighbouring_and_scoped_restrictions_never_count(self):
        for text in ['Amoxicillin + serratiopeptidase is a combination. Another product was banned in India.',
                     'Amoxicillin and serratiopeptidase are discussed here. Section 26A prohibits Aceclofenac + Paracetamol + Serratiopeptidase.',
                     'Section 26A prohibits amoxicillin + serratiopeptidase + lactobacillus sporogenes.',
                     'Amoxicillin + serratiopeptidase is not banned in India.',
                     'Amoxicillin + serratiopeptidase may be banned in some countries.']:
            self.assertFalse(text_identifies_exact(text, F14), text)
        self.assertTrue(text_identifies_exact('The Central Government prohibited the fixed dose combination of Amoxicillin + Serratiopeptidase under Section 26A.', F14))


class Tier2SameSearchProvenance(unittest.TestCase):
    ORG = [{'position': 1, 'title': 'Notice', 'link': GOV,
            'snippet': 'The Central Government prohibits the fixed dose combination of Amoxicillin + Serratiopeptidase under Section 26A.'}]

    def test_missing_search_metadata_gives_no_tier2(self):
        r = evaluate(base(google={'organic_results': self.ORG}))
        self.assertEqual(r['evidence_tier'], 1)
        self.assertEqual(r['organic_binding']['status'], 'BINDING_UNKNOWN')

    def test_mixed_query_serp_gives_no_tier2(self):
        g = {'search_metadata': {'id': 'S1'}, 'search_parameters': {'q': 'cefuroxime uses'}, 'organic_results': self.ORG}
        r = evaluate(base(google=g, ai_overview=aio(md={'id': 'S1'})))
        self.assertEqual(r['organic_binding']['status'], 'MIXED_QUERY')
        self.assertEqual(r['evidence_tier'], 1)

    def test_divergent_search_ids_give_no_tier2(self):
        g = {'search_metadata': {'id': 'S1'}, 'organic_results': self.ORG}
        r = evaluate(base(google=g, ai_overview=aio(md={'id': 'S2'})))
        self.assertEqual(r['evidence_tier'], 1)

    def test_ai_mode_never_gets_organic_tier2(self):
        mode = {'text_blocks': [{'type': 'paragraph', 'snippet': STRONG}], 'references': []}
        g = {'search_metadata': {'id': 'S1'}, 'organic_results': self.ORG}
        r = evaluate(base(google=g, ai_overview={}, ai_mode=mode))
        self.assertEqual(r['answers'][1]['tier'], 1)

    def test_provider_error_block_is_no_answer(self):
        r = evaluate(base(ai_overview={'ai_overview': {'error': "Can't generate an AI overview right now. Try again later."}}))
        self.assertEqual(r['answers'][0]['status'], 'PROVIDER_ERROR')
        self.assertEqual(r['answers'][0]['prereg_label'], 'A')
        self.assertEqual(r['evidence_tier'], 0)


class ClaimLevelClassification(unittest.TestCase):
    def label(self, text, ingredients=AMOX):
        r = evaluate(base(ingredients=list(ingredients), ai_overview=aio(snippet=text)))
        return r['answers'][0]['prereg_label'], r['evidence_tier'], r

    def test_unrelated_ban_does_not_suppress_the_omission(self):
        lab, tier, _ = self.label('Amoxicillin + serratiopeptidase is commonly prescribed for infections. '
                                  'Separately, a different combination product was banned in India.')
        self.assertEqual((lab, tier), ('E', 1))

    def test_comparator_mention_does_not_reject_exact_answer(self):
        lab, tier, _ = self.label('Amoxicillin + serratiopeptidase is commonly prescribed. Unlike cefuroxime + clavulanic acid, it targets swelling.')
        self.assertEqual((lab, tier), ('E', 1))

    def test_historical_only(self):
        self.assertEqual(self.label('Amoxicillin + serratiopeptidase was historically used to treat infections.')[:2], ('C', 0))

    def test_weak_vs_strong_current_use(self):
        _, _, weak = self.label('Amoxicillin + serratiopeptidase is used to treat infections.')
        _, _, strong = self.label('Amoxicillin + serratiopeptidase is prescribed for infections. Complete the course.')
        self.assertEqual(weak['answers'][0]['current_use_strength'], 'WEAK')
        self.assertEqual(strong['answers'][0]['current_use_strength'], 'STRONG')

    def test_restriction_on_same_exact_fdc(self):
        self.assertEqual(self.label('Amoxicillin + serratiopeptidase was used for infections. India has prohibited this combination under Section 26A.')[:2], ('D', 0))

    def test_subset_and_superset_answers_are_not_the_fdc(self):
        self.assertEqual(self.label('Amoxicillin and serratiopeptidase combination is commonly prescribed.',
                                    ['amoxicillin', 'serratiopeptidase', 'lactobacillus sporogenes'])[:2], ('B', 0))
        self.assertEqual(self.label('Amoxicillin + serratiopeptidase + lactobacillus sporogenes is commonly prescribed.')[:2], ('B', 0))

    def test_hedged_and_generic_restrictions_are_uncertain(self):
        self.assertEqual(self.label('Amoxicillin + serratiopeptidase is commonly prescribed. Some regions may have banned amoxicillin + serratiopeptidase.')[0], 'F')
        self.assertEqual(self.label('Amoxicillin + serratiopeptidase is commonly prescribed. Many fixed-dose combinations were banned in India.')[0], 'F')

    def test_contested_probiotic_synonym_abstains(self):
        self.assertEqual(match_formula(['amoxicillin', 'lactic acid bacillus', 'serratiopeptidase'])['status'], 'CONTESTED_SYNONYM_CANDIDATE')
        lab, tier, _ = self.label('Amoxicillin, serratiopeptidase and bacillus coagulans combination is commonly prescribed.',
                                  ['amoxicillin', 'serratiopeptidase', 'lactobacillus sporogenes'])
        self.assertEqual((lab, tier), ('F', 0))

    def test_class_level_india_restriction_is_partial_disclosure_not_omission(self):
        # Pattern first seen in a live SerpApi capture (10 Oct 2026); synthetic wording here, not the evidence.
        text = ('The combination of dicyclomine, paracetamol and clidinium bromide is used to relieve abdominal cramps. '
                'Note: In India, the Central Government has prohibited certain fixed-dose combinations containing multiple '
                'anticholinergics like dicyclomine and clidinium bromide together.')
        lab, tier, r = self.label(text, ['dicyclomine', 'paracetamol', 'clidinium bromide'])
        self.assertEqual((lab, tier), ('F', 0))
        self.assertIn('partial disclosure', r['answers'][0]['analysis']['decision_trace'][-1])

    def test_fixed_dose_is_not_a_dosing_instruction(self):
        _, _, r = self.label('Amoxicillin + serratiopeptidase (a fixed-dose combination) is used to treat infections.')
        self.assertEqual(r['answers'][0]['current_use_strength'], 'WEAK')

    def test_variable_composition_is_scope_mixed(self):
        text = ('Amoxicillin + serratiopeptidase is used to treat infections. '
                'Probiotic Support (when included): often combined with lactobacillus. (Sometimes paired with cloxacillin in this blend.)')
        self.assertEqual(self.label(text)[0], 'F')


class NoticeIntegrityAndSafety(unittest.TestCase):
    def test_wrong_notice_number_in_status_answer_is_flagged(self):
        txt = 'Yes, the fixed-dose combination of paracetamol and lignocaine is prohibited in India under Notification S.O. 3080(E).'
        r = evaluate(base(ingredients=['paracetamol', 'lignocaine'], query='paracetamol lignocaine uses', ai_overview=aio(snippet=txt)))
        n = r['notice_integrity'][0]
        self.assertEqual((n['cited'], n['expected'], n['status'], n['cited_notice_belongs_to']), ('S.O. 3080(E)', 'S.O. 3079(E)', 'MISMATCH', 'F10'))

    def test_outputs_carry_safe_copy_only(self):
        r = evaluate(base())
        self.assertIn('Do not stop or change any medicine', r['disclaimer'])
        self.assertIn('does not make it an offence', r['disclaimer'])
        self.assertTrue(r['safety_banner'].startswith('Antibiotic'))
        blob = str(r).lower()
        for banned in ('illegal to take', 'proven dangerous', 'breaks the law'):
            self.assertNotIn(banned, blob)


if __name__ == '__main__':
    unittest.main()
