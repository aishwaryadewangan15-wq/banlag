import copy,unittest
from banlag.core import registry,canonical,match_formula,classify,extract_ai,evaluate,text_identifies_exact

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
        data['google']['organic_results']=[{'snippet':'Government prohibits amoxicillin + serratiopeptidase'}]
        self.assertEqual(evaluate(data)['evidence_tier'],2)
        data['google']['organic_results']=[{'snippet':'Another drug banned'}]
        self.assertEqual(evaluate(data)['evidence_tier'],1)
    def test_tier3_requires_actual_citation_and_capture(self):
        data=copy.deepcopy(self.data)
        data['cited_page_captures']=[{'url':'https://example.invalid/page','source_text':'Section 26A prohibits amoxicillin + serratiopeptidase',
                                     'capture_time':'SYNTHETIC','capture_method':'SYNTHETIC'}]
        self.assertEqual(evaluate(data)['evidence_tier'],3)
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
        self.data['explicit_status_query']={'answer_text':'This combination is prohibited in India.'}
        self.assertTrue(evaluate(self.data)['explicit_status_contrast'])
        self.data['ai_overview']={}
        self.assertFalse(evaluate(self.data)['explicit_status_contrast'])
    def test_source_kind_mandatory(self):
        del self.data['source_kind']
        with self.assertRaises(ValueError):evaluate(self.data)
    def test_capture_hash_stable(self):
        self.assertEqual(evaluate(self.data)['capture_sha256'],evaluate(copy.deepcopy(self.data))['capture_sha256'])

if __name__=='__main__':unittest.main()
