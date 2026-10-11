"""Inherited V0.1 starter tests (original: tests/baseline_v01/test_core.py, SHA-256 7ff098ae...f5).

21 of 23 inherited tests run here UNCHANGED. Two asserted behaviour the independent audits found unsafe and are changed
with the reason inline (search 'CHANGED IN V0.2'):
  - test_tier2_only_with_exact_organic: ADAPTED. Organic results now count only when bound to the same search as the
    AI answer, and only for a current Indian restriction; the fixture declares that binding and names India.
    The 'no exact organic -> no Tier 2' assertion is unchanged.
  - test_tier3_requires_actual_citation_and_capture: INVERTED. Imported page text is self-asserted (audit CRITICAL 3)
    and can never produce Tier 3. The uncited-URL and missing-method assertions are unchanged.
  - test_status_contrast_is_not_proof_by_itself: FIXTURE ADAPTED IN RC-3 (owner's RC-3 instruction, Codex RC-2 audit P2).
    A status contrast now requires that the separately asked question is supplied and names exactly the target, so the
    fixture supplies that question. Both assertions (contrast true with a uses observation; false without one) are unchanged;
    the question-absent case is covered by tests/test_audit4_lead_clause_binding.py.
"""
import copy,unittest
from banlag.core import registry,match_formula,classify,extract_ai,evaluate,text_identifies_exact

class RegistryTests(unittest.TestCase):
    def test_ten_exact_notices(self):
        db=registry();self.assertEqual(len(db['entries']),10)
        self.assertEqual(len(set(x['notice'] for x in db['entries'])),10)
        for entry in db['entries']:
            self.assertEqual(match_formula(entry['ingredients'])['entry']['id'],entry['id'])
    def test_aliases(self):
        self.assertEqual(match_formula(['amoxycillin','serrapeptase'])['entry']['id'],'F14')
        self.assertEqual(match_formula(['lidocaine','acetaminophen'])['entry']['id'],'F11')
        self.assertEqual(match_formula(['cefadroxil','probenecid'])['entry']['id'],'F15')
    def test_exact_scope_controls(self):
        for x in [['cefuroxime'],['amoxicillin','serratiopeptidase','clavulanic acid'],
                  ['dicyclomine','paracetamol'],['amoxicillin','lactic acid bacillus','serratiopeptidase'],
                  ['aceclofenac','paracetamol','serratiopeptidase'],['cefuroxime','clavulanic acid'],
                  ['amoxicillin','dicloxacillin','serratiopeptidase']]:
            self.assertNotEqual(match_formula(x)['status'],'EXACT_NOTIFICATION_MATCH',x)
    def test_unknown_not_guessed(self):
        self.assertEqual(match_formula(['amoxicillin','something unspecified'])['status'],'UNKNOWN_FORMULATION')
        self.assertEqual(match_formula(['amoxicillin','amoxicillin'])['status'],'UNKNOWN_FORMULATION')
    def test_adjacent_exact_bans_different(self):
        self.assertEqual(match_formula(['dicyclomine','paracetamol','clidinium bromide'])['entry']['id'],'F08')
        self.assertEqual(match_formula(['dicyclomine','paracetamol','clidinium bromide','chlordiazepoxide'])['entry']['id'],'F09')
        self.assertEqual(match_formula(['amoxicillin','serratiopeptidase','lactobacillus sporogenes'])['entry']['id'],'F12')
    def test_scope_proximity(self):
        entry=match_formula(['amoxicillin','serratiopeptidase'])['entry']
        self.assertTrue(text_identifies_exact('Section 26A prohibits manufacture of amoxicillin + serratiopeptidase',entry))
        self.assertFalse(text_identifies_exact('Amoxicillin + serratiopeptidase is described. ' + 'filler '*120 + 'Another formulation banned',entry))

class AnswerTests(unittest.TestCase):
    def test_clinical_labels(self):
        self.assertEqual(classify('This medicine is commonly prescribed to patients.'),'STRONG_CURRENT_USE_UNWARNED')
        self.assertEqual(classify('Previously used to treat infections.'),'HISTORICAL_DESCRIPTION')
        self.assertEqual(classify('Is used in treatment for infections.'),'GENERAL_USE_UNWARNED')
        self.assertEqual(classify('India prohibited manufacture and sale of this combination.'),'RESTRICTION_MENTIONED')
        self.assertEqual(classify('This drug is not banned in India.'),'LEGAL_STATUS_CONFLICT_REVIEW')
        self.assertEqual(classify(''), 'NO_AI_ANSWER')
    def test_ai_lists(self):
        obj={'ai_overview':{'text_blocks':[{'type':'paragraph','snippet':'Text'},{'type':'list','list':[{'snippet':'item'}]}],
                            'references':[{'index':0,'link':'https://example.invalid'}]},'search_metadata':{'id':'abc'}}
        d=extract_ai(obj)
        self.assertEqual(d['search_id'],'abc');self.assertEqual(d['text'],'Text\nitem')

class TierTests(unittest.TestCase):
    def setUp(self):
        self.data={'source_kind':'SYNTHETIC_TEST','captured_at':'SYNTHETIC',
                   'ingredients':['amoxicillin','serratiopeptidase'],
                   'ai_overview':{'ai_overview':{'text_blocks':[{'snippet':'Amoxicillin + serratiopeptidase is commonly prescribed.'}],
                                    'references':[{'index':0,'link':'https://example.invalid/page'}]}},
                   'google':{'organic_results':[]},'cited_page_captures':[]}
    def test_tier1(self):
        self.assertEqual(evaluate(self.data)['evidence_tier'],1)
    def test_tier2_only_with_exact_organic(self):
        data=copy.deepcopy(self.data)
        # CHANGED IN V0.2 (ADAPTED): declare that the organic results and the AI Overview share one search.
        # Without that binding, organic results can come from a different query/time (audit gap) and never give Tier 2.
        data['google']['search_metadata']={'id':'SYNTHETIC-SEARCH-1'};data['ai_overview']['search_metadata']={'id':'SYNTHETIC-SEARCH-1'}
        # CHANGED IN V0.2 (ADAPTED, Codex P1-5): a restriction of unspecified jurisdiction no longer establishes an Indian
        # prohibition, so the fixture names India ('Government of India'). Assertions unchanged.
        data['google']['organic_results']=[{'snippet':'Government of India prohibits amoxicillin + serratiopeptidase'}]
        self.assertEqual(evaluate(data)['evidence_tier'],2)
        data['google']['organic_results']=[{'snippet':'Another drug banned'}]
        self.assertEqual(evaluate(data)['evidence_tier'],1)
    def test_tier3_requires_actual_citation_and_capture(self):
        data=copy.deepcopy(self.data)
        data['cited_page_captures']=[{'url':'https://example.invalid/page','source_text':'Section 26A prohibits amoxicillin + serratiopeptidase',
                                     'capture_time':'SYNTHETIC','capture_method':'SYNTHETIC'}]
        # CHANGED IN V0.2 (INVERTED): V0.1 returned 3 here. Imported source_text/capture_time/capture_method are
        # self-asserted (audit CRITICAL 3); only a locally snapshotted page can support Tier 3.
        self.assertNotEqual(evaluate(data)['evidence_tier'],3)
        self.assertEqual(evaluate(data)['evidence_tier'],1)
        data['cited_page_captures'][0]['url']='https://example.invalid/uncited'
        self.assertEqual(evaluate(data)['evidence_tier'],1)
        data['cited_page_captures'][0]['url']='https://example.invalid/page'
        del data['cited_page_captures'][0]['capture_method']
        self.assertEqual(evaluate(data)['evidence_tier'],1)
    def test_fail_closed_wrong_target_answer(self):
        self.data['ai_overview']['ai_overview']['text_blocks'][0]['snippet']='Cefuroxime + clavulanate is commonly prescribed.'
        result=evaluate(self.data)
        self.assertEqual(result['evidence_tier'],0)
        self.assertEqual(result['answers'][0]['classification'],'ENTITY_MENTION_UNVERIFIED')
    def test_fail_closed_missing_ai(self):
        self.data['ai_overview']={}
        self.assertEqual(evaluate(self.data)['evidence_tier'],0)
    def test_fail_closed_nonexact(self):
        self.data['ingredients'].append('clavulanic acid')
        self.assertEqual(evaluate(self.data)['evidence_tier'],0)
    def test_status_contrast_is_not_proof_by_itself(self):
        # CHANGED IN RC-3: the separately asked question must be supplied and name exactly the target (fixture only).
        self.data['explicit_status_query']={'query':'is amoxicillin serratiopeptidase prohibited in india',
                                            'answer_text':'This combination is prohibited in India.'}
        self.assertTrue(evaluate(self.data)['explicit_status_contrast'])
        self.data['ai_overview']={}
        self.assertFalse(evaluate(self.data)['explicit_status_contrast'])
    def test_source_kind_mandatory(self):
        del self.data['source_kind']
        with self.assertRaises(ValueError):evaluate(self.data)
    def test_capture_hash_stable(self):
        self.assertEqual(evaluate(self.data)['capture_sha256'],evaluate(copy.deepcopy(self.data))['capture_sha256'])

if __name__=='__main__':unittest.main()
