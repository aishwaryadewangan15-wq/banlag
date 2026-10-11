"""Regression tests for Codex's second hostile audit (10 Oct 2026) and the acceptance criteria in claudeINS.txt.

A  corpus integrity: pinned trust anchor, verified bytes on every load, fail-closed, recovery.
B  composition: 'exact' means exact - additions in parentheticals, 'as well as', 'including', 'plus', 'the formulation also
   contains', unknown members at the start/middle/end - never promoted; descriptions, strengths and '(with food)' are not.
C  citations: title, snippet and URL are reconciled, not ranked; conflicts, truncation and multiple formulations stay visible.
D  restriction status bound to its predicate: negation window, conditions, proposals, dates, cross-sentence reversal.
E  T2/T3 promotion needs a current Indian restriction on the exact set; a sealed capture is not proof of a legal fact.
Every class keeps positive controls so a fix cannot pass by refusing everything. Before/after runs: engineering-history branch, docs/proof/codex2_*.txt.
"""
import copy
import datetime as dt
import hashlib
import http.client
import json
import shutil
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

from banlag import collector, corpus
from banlag.citations import coherence, reference_formulation, relation_to
from banlag.claims import analyze_surface, composition_issues, restriction_statements, restriction_status
from banlag.engine import evaluate, evaluate_run
from banlag.legal import entry_by_id
from banlag.public import legacy_view

ROOT = Path(__file__).resolve().parent.parent
F08 = entry_by_id('F08')
ING = ['dicyclomine', 'paracetamol', 'clidinium bromide']
LEAD = 'Dicyclomine, Paracetamol and Clidinium Bromide are used to treat abdominal cramps.'
T3 = 'Dicyclomine + Paracetamol + Clidinium Bromide Tablets'
CURRENT_BAN = 'The Central Government has prohibited the fixed dose combination of Dicyclomine, Paracetamol and Clidinium Bromide for human use.'


def payload(text, organic=None, refs=None):
    return {'source_kind': 'SYNTHETIC_TEST', 'query': 'q', 'ingredients': ING,
            'google': {'search_metadata': {'id': 'S1'}, 'search_parameters': {'q': 'q'}, 'organic_results': organic or [],
                       'ai_overview': {'text_blocks': [{'type': 'paragraph', 'snippet': text, 'reference_indexes': [0] if refs else []}],
                                       'references': refs or []}}}


def run(text, organic=None, refs=None, snaps=None):
    r = evaluate(payload(text, organic, refs), verified_snapshots=snaps)
    return r['answers'][0], r


def label_tier(text, organic=None):
    a, r = run(text, organic)
    return a['prereg_label'], r['evidence_tier']


def organic(snippet, link='https://news.example.invalid/notice'):
    return [{'position': 1, 'title': 'Restriction notice', 'link': link, 'snippet': snippet}]


def tier3(statement):
    url = 'https://ref.example.invalid/p'
    return run(LEAD, refs=[{'index': 0, 'link': url}], snaps=[{'url': url, 'text': statement, 'sha256': '0' * 64}])[1]['evidence_tier']


def rel(ref):
    return relation_to(set(ING), reference_formulation(dict(ref, index=0)))


class A_CorpusIntegrity(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.good = (ROOT / 'evidence' / 'g1_corpus.json').read_bytes()
        self.man = json.loads((ROOT / 'evidence' / 'CORPUS_MANIFEST.json').read_text(encoding='utf-8'))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write(self, corpus_bytes, manifest_text):
        (self.tmp / 'g1_corpus.json').write_bytes(corpus_bytes)
        (self.tmp / 'CORPUS_MANIFEST.json').write_text(manifest_text, encoding='utf-8')
        return corpus.build_cases(str(self.tmp / 'g1_corpus.json'), str(self.tmp / 'CORPUS_MANIFEST.json'))

    def assert_failed_closed(self, r):
        self.assertEqual(r['corpus']['integrity']['status'], 'FAILED')
        self.assertEqual(r['g1']['locked']['verdict'], 'INTEGRITY_FAILED')
        self.assertEqual(r['corpus'].get('screenshots'), {})
        for c in r['cases']:
            self.assertFalse(c['g1_positive'])
            self.assertEqual(c['publication_gate']['decision'], 'WITHHOLD')

    def test_null_list_and_incomplete_manifests_fail_closed(self):
        for text in ('null', '[]', '"x"', json.dumps({'corpus_sha256': hashlib.sha256(self.good).hexdigest()}),
                     json.dumps(dict(self.man, schema='other')), json.dumps(dict(self.man, records=40)),
                     json.dumps(dict(self.man, lock_records={})), json.dumps({k: v for k, v in self.man.items() if k != 'built_by'})):
            self.assert_failed_closed(self.write(self.good, text))

    def test_rehashed_replacement_corpus_fails_against_the_pinned_anchor(self):
        c = json.loads(self.good)
        c['records'][0]['gold_label'] = 'E' if c['records'][0]['gold_label'] != 'E' else 'D'  # same record count, changed content
        data = json.dumps(c, ensure_ascii=False, indent=1).encode('utf-8')
        r = self.write(data, json.dumps(dict(self.man, corpus_sha256=hashlib.sha256(data).hexdigest())))
        self.assert_failed_closed(r)
        self.assertEqual(r['corpus']['integrity']['anchor'], corpus.EXPECTED_CORPUS_SHA256)

    def test_cached_verification_cannot_hide_a_later_tamper_and_recovery_works(self):
        r = self.write(self.good, json.dumps(self.man))
        self.assertEqual((r['corpus']['integrity']['status'], r['g1']['locked']['verdict']), ('VERIFIED', 'G1_PASS'))
        bad = self.good.replace(b'is used to treat abdominal cramps', b'is used to treat abdominal crampz', 1)
        self.assert_failed_closed(self.write(bad, json.dumps(dict(self.man, corpus_sha256=hashlib.sha256(bad).hexdigest()))))
        r = self.write(self.good, json.dumps(self.man))
        self.assertEqual((r['corpus']['integrity']['status'], r['g1']['locked']['verdict'], r['g1']['locked']['n_positive']), ('VERIFIED', 'G1_PASS', 7))

    def test_load_corpus_rereads_bytes(self):
        self.write(self.good, json.dumps(self.man))
        self.assertEqual(len(corpus.load_corpus(str(self.tmp / 'g1_corpus.json'), str(self.tmp / 'CORPUS_MANIFEST.json'))['records']), 41)
        (self.tmp / 'g1_corpus.json').write_bytes(self.good + b' ')
        with self.assertRaises(corpus.CorpusIntegrityError):
            corpus.load_corpus(str(self.tmp / 'g1_corpus.json'), str(self.tmp / 'CORPUS_MANIFEST.json'))

    def test_trust_boundary_is_stated(self):
        integ = corpus.build_cases()['corpus']['integrity']
        self.assertEqual(integ['status'], 'VERIFIED')
        self.assertIn('not', integ['trust_boundary'].lower())


class B_Composition(unittest.TestCase):
    ATTACKS = [
        'Dicyclomine, Paracetamol and Clidinium Bromide (plus omeprazole) are used to treat abdominal cramps.',
        'Dicyclomine, Paracetamol and Clidinium Bromide, including omeprazole, are used to treat abdominal cramps.',
        'Dicyclomine, Paracetamol and Clidinium Bromide plus activated charcoal are used to treat abdominal cramps.',
        'Dicyclomine, an omeprazole capsule, Paracetamol and Clidinium Bromide are used to treat abdominal cramps.',
        'Dicyclomine, Paracetamol and Clidinium Bromide plus light magnesium oxide are used to treat abdominal cramps.',
        'Dicyclomine, Paracetamol and Clidinium Bromide and zinc sulfate monohydrate are used to treat abdominal cramps.',
        'Dicyclomine, Paracetamol and Clidinium Bromide as well as omeprazole are used to treat abdominal cramps.',
        'Dicyclomine, Paracetamol and Clidinium Bromide; the formulation also contains omeprazole and is used to treat abdominal cramps.',
        # variants beyond the audit
        'Omeprazole, Dicyclomine, Paracetamol and Clidinium Bromide are used to treat abdominal cramps.',
        'Dicyclomine, Paracetamol, Clidinium Bromide, Omeprazole tablets are used to treat abdominal cramps.',
        'Dicyclomine, Paracetamol and Clidinium Bromide along with simvastatin are used to treat abdominal cramps.',
        'Dicyclomine, Paracetamol and Clidinium Bromide (and also omeprazole) are used to treat abdominal cramps.',
        LEAD + ' The formulation also contains omeprazole.',
        LEAD + ' This combination additionally contains zinc sulfate monohydrate.',
        'Dicyclomine, Paracetamol and Clidinium Bromide alongside omeprazole are used to treat abdominal cramps.',
        'Dicyclomine, Paracetamol and Clidinium Bromide co-formulated with omeprazole are used to treat abdominal cramps.',
        'Dicyclomine, Paracetamol and Clidinium Bromide combined with omeprazole are used to treat abdominal cramps.',
        LEAD + ' It also contains omeprazole.',
    ]
    CONTROLS = [
        LEAD,
        'Dicyclomine, Paracetamol and Clidinium Bromide (taken with food) are used to treat abdominal cramps.',
        'Dicyclomine, Paracetamol and Clidinium Bromide (with food) are used to treat abdominal cramps.',
        'Dicyclomine 10 mg, Paracetamol 325 mg and Clidinium Bromide 2.5 mg tablets are used to treat abdominal cramps.',
        'Dicyclomine, an antispasmodic, Paracetamol and Clidinium Bromide are used to treat abdominal cramps.',
        'For abdominal cramps, dicyclomine, paracetamol and clidinium bromide are commonly prescribed.',
        LEAD + ' This combination contains three active ingredients.',
        LEAD + ' Take it with a glass of water.',
        'Dicyclomine, Paracetamol and Clidinium Bromide, combined with plenty of fluids, are used to treat abdominal cramps.',
    ]

    def test_altered_compositions_are_never_exact(self):
        for t in self.ATTACKS:
            a, r = run(t)
            self.assertEqual((a['prereg_label'], r['evidence_tier']), ('B', 0), t)
            self.assertIn(a['analysis']['subject']['entity_vs_target'], ('UNKNOWN_COMPONENT', 'SUPERSET_OF_TARGET'), t)

    def test_known_addition_widens_the_subject(self):
        a, _ = run('Dicyclomine, Paracetamol and Clidinium Bromide (plus chlordiazepoxide) are used to treat abdominal cramps.')
        self.assertEqual((a['prereg_label'], a['analysis']['subject']['entity_vs_target']), ('B', 'SUPERSET_OF_TARGET'))
        self.assertIn('chlordiazepoxide', a['analysis']['subject']['ingredients'])

    def test_controls_stay_exact(self):
        for t in self.CONTROLS:
            self.assertEqual(label_tier(t), ('E', 1), t)

    def test_unknown_components_are_reported_not_discarded(self):
        self.assertEqual(composition_issues(self.ATTACKS[0])['unknown'], ['omeprazole'])
        self.assertEqual(composition_issues(self.ATTACKS[4])['unknown'], ['light magnesium oxide'])
        a, _ = run(self.ATTACKS[5])
        self.assertEqual(a['analysis']['subject']['unrecognised_components'], ['zinc sulfate monohydrate'])

    def test_asides_about_other_products_are_classified(self):
        ci = composition_issues('Yes, the fixed-dose combination (FDC) of Dicyclomine + Paracetamol + Clidinium Bromide '
                                '(as well as the version including Chlordiazepoxide) is prohibited in India.')
        self.assertEqual((ci['unknown'], ci['extra_known'], len(ci['other_product_asides'])), ([], [], 1))
        ci = composition_issues('The combination of amoxicillin, serratiopeptidase, and lactobacillus sporogenes '
                                '(often grouped with cloxacillin or related penicillins) is a multi-action prescription medication.')
        self.assertEqual((ci['unknown'], len(ci['variable_asides'])), ([], 1))

    def test_altered_composition_never_supports_t2_or_t3(self):
        s = 'Dicyclomine, Paracetamol and Clidinium Bromide (plus omeprazole) is prohibited in India.'
        self.assertEqual(label_tier(LEAD, organic(s)), ('E', 1))
        self.assertEqual(tier3(s), 1)
        self.assertEqual(restriction_statements(s, F08), [])


class C_CitationViews(unittest.TestCase):
    def test_title_exact_snippet_adds_component(self):
        self.assertEqual(rel({'title': T3, 'snippet': 'Dicyclomine + Paracetamol + Clidinium Bromide + Omeprazole Tablets', 'link': 'https://x.invalid/p'}),
                         'UNRECOGNISED_COMPONENT')

    def test_conflicting_views(self):
        for ref in [{'title': T3, 'snippet': 'Dicyclomine + Paracetamol + Chlordiazepoxide tablets.', 'link': 'https://x.invalid/p'},
                    {'title': T3, 'snippet': '', 'link': 'https://x.invalid/dicyclomine-paracetamol-clidinium-bromide-chlordiazepoxide'},
                    {'title': T3, 'snippet': 'Dicyclomine + Paracetamol + Clidinium Bromide + Simethicone Tablets', 'link': 'https://x.invalid/p'},
                    {'title': T3, 'snippet': 'Dicyclomine + Chlordiazepoxide ...', 'link': 'https://x.invalid/p'}]:
            f = reference_formulation(dict(ref, index=0))
            self.assertEqual(relation_to(set(ING), f), 'CONFLICTING_VIEWS', ref)
            self.assertIsNone(f['registry_entry'])
            self.assertTrue(f['conflict'])

    def test_multiple_formulations_in_one_view(self):
        self.assertEqual(rel({'title': 'Antispasmodics', 'link': 'https://x.invalid/p',
                              'snippet': 'Dicyclomine + Paracetamol and Dicyclomine + Paracetamol + Clidinium Bromide are both sold.'}), 'MULTIPLE_FORMULATIONS')

    def test_truncation_is_recorded_not_hidden(self):
        f = reference_formulation({'index': 0, 'title': T3, 'snippet': 'Dicyclomine + Paracetamol + Clidinium Bromide ...', 'link': 'https://x.invalid/p'})
        self.assertEqual((relation_to(set(ING), f), f['truncated_views'], f['truncated']), ('EXACT', ['snippet'], False))
        f = reference_formulation({'index': 0, 'title': 'Notice', 'snippet': 'Dicyclomine + Paracetamol + Clidinium Bromide ...', 'link': 'https://x.invalid/p'})
        self.assertEqual((relation_to(set(ING), f), f['truncated']), ('EXACT_LOWER_BOUND', True))

    def test_no_formulation_and_single_names(self):
        self.assertEqual(rel({'title': 'Overview', 'snippet': 'Antispasmodic medicines.', 'link': 'https://x.invalid/p'}), 'NO_FORMULATION_NAMED')
        self.assertEqual(rel({'title': 'What Is Dicyclomine?', 'snippet': 'Dicyclomine is an anticholinergic.', 'link': 'https://x.invalid/dicyclomine/what-is'}),
                         'SINGLE_COMPONENT')

    def test_positive_controls(self):
        self.assertEqual(rel({'title': T3, 'snippet': 'A combination of dicyclomine, paracetamol and clidinium bromide for cramps.',
                              'link': 'https://x.invalid/dicyclomine-paracetamol-clidinium-bromide'}), 'EXACT')
        # '*' and 'Uses.' separate repeated listings of one formulation (pattern seen on live pharmacy references).
        self.assertEqual(rel({'title': 'Dicyclomine + Paracetamol + Clidinium: View Uses', 'link': 'https://x.invalid/generics/dicyclomine-paracetamol-clidinium-401',
                              'snippet': 'Dicyclomine + Paracetamol + Clidinium * Dicyclomine + Paracetamol + Clidinium Uses. Dicyclomine+Paracetamol+Clidinium is us...'}), 'EXACT')

    def test_foreign_or_negated_snippet_is_not_a_restriction_mention(self):
        for s in ['Dicyclomine + Paracetamol + Clidinium Bromide is banned in the United States.',
                  'Dicyclomine + Paracetamol + Clidinium Bromide is not banned in India.']:
            self.assertFalse(reference_formulation({'index': 0, 'title': T3, 'snippet': s, 'link': 'https://x.invalid/p'})['mentions_restriction'], s)

    def test_conflicting_reference_is_reported_as_unresolved_for_a_restriction_claim(self):
        refs = [{'index': 0, 'title': 'Prohibition of ' + T3, 'snippet': 'Prohibition of Dicyclomine + Paracetamol + Chlordiazepoxide in India.',
                 'link': 'https://x.invalid/p', 'source': 'S'}]
        blocks = [{'id': 'b0', 'type': 'paragraph', 'label': None, 'text': LEAD, 'reference_indexes': [], 'chips': []},
                  {'id': 'b1', 'type': 'paragraph', 'label': None, 'text': 'This combination is prohibited in India.', 'reference_indexes': [0], 'chips': []}]
        coh = coherence(analyze_surface(blocks, refs, 'REFERENCE_INDEX_BOUND', F08), refs)
        f = [x for x in coh['findings'] if x['type'] == 'RESTRICTION_CITATIONS_DO_NOT_NAME_THIS_NOTICE']
        self.assertEqual(len(f), 1)
        self.assertEqual(f[0]['unresolved_sources'][0]['relation'], 'CONFLICTING_VIEWS')
        self.assertIn('different formulations', f[0]['unresolved_sources'][0]['why'])


class D_RestrictionStatus(unittest.TestCase):
    NOT_D = ['This combination is not under any circumstances banned in India.',
             'This combination is prohibited in India only if it contains an additional benzodiazepine.',
             'This combination would be prohibited in India if the draft were approved.',
             'This combination was banned in India in 2016. The ban was subsequently revoked.',
             'This combination was banned in India. That prohibition has since been lifted.',
             'This combination was banned in India. It was later revoked by the High Court.',
             'This combination was banned in India, but the ban was revoked.',
             'This combination is prohibited in India unless prescribed by a specialist.',
             'This combination will be banned in India next year.',
             'In 2016, this combination was prohibited in India.',
             'There is no evidence that this combination is banned in India.',
             'This combination is banned in Canada.',
             'This combination, which is sold in India, is banned in the United States.',
             'Some reports say this combination is banned in India.',
             'This combination is banned in India, according to a 2019 rumour that was never confirmed.']
    IS_D = ['Dicyclomine, Paracetamol and Clidinium Bromide are prohibited in India.',
            'This combination is prohibited in India.',
            'No, this combination is banned in India.',
            'This combination is not only banned in India but also withdrawn from pharmacies.',
            'This combination is not banned in the United States, but it is prohibited in India.',
            'This combination was banned in 2016, but it is now prohibited again in India under the June 2026 notification.',
            'This combination is prohibited in India. An earlier 2016 ban on it was quashed by the Delhi High Court.',
            'According to the Gazette notification, this combination is prohibited in India.']

    def test_qualified_restrictions_are_not_d(self):
        for s in self.NOT_D:
            self.assertNotEqual(label_tier(LEAD + ' ' + s)[0], 'D', s)

    def test_current_indian_restrictions_stay_d(self):
        for s in self.IS_D:
            self.assertEqual(label_tier(LEAD + ' ' + s)[0], 'D', s)

    def test_status_is_bound_to_each_predicate(self):
        st = restriction_status('This combination is not banned in the United States, but it is prohibited in India.')
        self.assertEqual([(p['term'], p['negated'], p['jurisdiction'], p['current']) for p in st['predicates']],
                         [('banned', True, 'OTHER', False), ('prohibited', False, 'INDIA', True)])
        st = restriction_status('Dicyclomine, Paracetamol and Clidinium Bromide, a combination sold in India, is banned in the United States.')
        self.assertEqual((st['jurisdiction'], st['current_india']), ('OTHER', False))
        self.assertTrue(restriction_status('This combination is prohibited in India only if it contains a benzodiazepine.')['conditional'])

    def test_cross_sentence_reversal_is_recorded_on_the_earlier_claim(self):
        a = analyze_surface([{'id': 'b0', 'type': 'paragraph', 'text': LEAD + ' This combination was banned in India. That prohibition has since been lifted.'}],
                            target_entry=F08)
        r = next(c['restriction'] for c in a['claims'] if c['text'].startswith('This combination was banned'))
        self.assertEqual((r['revoked'], r['reversed_by'], a['prereg_label']), (True, 'b0.s2', 'F'))


class E_TierPromotion(unittest.TestCase):
    NOT_PROMOTED = ['Dicyclomine, Paracetamol and Clidinium Bromide, a combination sold in India, is banned in the United States.',
                    'Dicyclomine, Paracetamol and Clidinium Bromide, a combination sold in India, is banned in Canada.',
                    'Dicyclomine, Paracetamol and Clidinium Bromide is prohibited in India only if it contains an additional benzodiazepine.',
                    'Dicyclomine, Paracetamol and Clidinium Bromide would be prohibited in India if the draft were approved.',
                    'Dicyclomine, Paracetamol and Clidinium Bromide was banned in India. That prohibition has since been lifted.',
                    'In 2016, the fixed dose combination of Dicyclomine, Paracetamol and Clidinium Bromide was prohibited in India.',
                    'Dicyclomine, Paracetamol and Clidinium Bromide (plus omeprazole) is prohibited in India.',
                    'Dicyclomine, Paracetamol and Clidinium Bromide is not under any circumstances banned in India.',
                    'Dicyclomine, Paracetamol and Clidinium Bromide is banned by Health Canada.']
    PROMOTED = [CURRENT_BAN, 'Dicyclomine, Paracetamol and Clidinium Bromide is prohibited in India.',
                'Dicyclomine, Paracetamol and Clidinium Bromide is not banned in the US, but it is prohibited in India.']

    def test_same_gate_for_t2_and_t3(self):
        for s in self.NOT_PROMOTED:
            self.assertEqual(label_tier(LEAD, organic(s)), ('E', 1), s)
            self.assertEqual(tier3(s), 1, s)
        for s in self.PROMOTED:
            self.assertEqual(label_tier(LEAD, organic(s)), ('E', 2), s)
            self.assertEqual(tier3(s), 3, s)

    def test_official_domain_alone_is_not_an_operative_restriction(self):
        gov = 'https://egazette.gov.in/x.pdf'
        self.assertEqual(label_tier(LEAD, organic('The fixed dose combination of Dicyclomine, Paracetamol and Clidinium Bromide is hereby prohibited.', gov))[1], 2)
        for s in ['Dicyclomine, Paracetamol and Clidinium Bromide is banned in the United States.',
                  'Dicyclomine, Paracetamol and Clidinium Bromide was prohibited, but the prohibition was stayed.',
                  'Dicyclomine, Paracetamol and Clidinium Bromide is proposed to be prohibited.',
                  'Dicyclomine, Paracetamol and Clidinium Bromide would be prohibited if the draft were approved.']:
            self.assertEqual(label_tier(LEAD, organic(s, gov))[1], 1, s)

    def sealed(self, organic_snippet, ai_text, organic_link='https://egazette.gov.in/x.pdf'):
        from tests.test_capture_store import PLAN, KEY, FakeFetch, fake_responses
        tmp = Path(tempfile.mkdtemp())
        try:
            resp = fake_responses()
            resp[0]['organic_results'] = [{'position': 1, 'link': organic_link, 'title': 'x', 'snippet': organic_snippet}]
            resp[1]['ai_overview']['text_blocks'][0]['snippet'] = ai_text
            sha = hashlib.sha256(PLAN.read_bytes()).hexdigest()
            run_id, _ = collector.run(PLAN, sha, env={'BANLAG_SERPAPI_APPROVAL': sha, 'SERPAPI_API_KEY': KEY}, fetch=FakeFetch(resp),
                                      store=tmp / 's', key_path=tmp / 'k' / 'key', out=lambda *a: None,
                                      now=lambda: dt.datetime(2026, 10, 10, 10, 0, 5, tzinfo=dt.timezone.utc))
            return evaluate_run(run_id, tmp / 's', tmp / 'k' / 'key')
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_authenticated_capture_of_a_false_statement_is_not_promoted(self):
        us_ban = 'Dicyclomine, Paracetamol and Clidinium Bromide, a combination sold in India, is banned in the United States.'
        r = self.sealed(us_ban, 'Dicyclomine, Paracetamol and Clidinium Bromide (plus omeprazole) are used to treat abdominal cramps.')
        self.assertEqual((r['origin'], r['answers'][0]['prereg_label'], r['verified_evidence_tier']), ('TRUSTED_LOCAL_SERPAPI_CAPTURE', 'B', 0))
        r = self.sealed(us_ban, 'A combination of dicyclomine, paracetamol and clidinium bromide is used to treat abdominal cramps.')
        self.assertEqual((r['answers'][0]['prereg_label'], r['verified_evidence_tier']), ('E', 1))
        r = self.sealed('hereby prohibits the manufacture, sale or distribution of the fixed dose combination of Dicyclomine + Paracetamol + '
                        'Clidinium Bromide for human use', 'A combination of dicyclomine, paracetamol and clidinium bromide is used to treat abdominal cramps.')
        self.assertEqual(r['verified_evidence_tier'], 2)  # positive control: the sealed path still promotes a genuine current restriction


class EndToEndHTTP(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from banlag.server import Handler
        cls.s = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        cls.t = threading.Thread(target=cls.s.serve_forever, daemon=True)
        cls.t.start()

    @classmethod
    def tearDownClass(cls):
        cls.s.shutdown()
        cls.s.server_close()
        cls.t.join(timeout=3)

    def post(self, obj):
        c = http.client.HTTPConnection('127.0.0.1', self.s.server_port, timeout=10)
        c.request('POST', '/api/evaluate', body=json.dumps(obj).encode(), headers={'Content-Type': 'application/json'})
        r = c.getresponse()
        data = legacy_view(json.loads(r.read().decode()))  # public contract: legacy fields are served under "experimental"; legacy_view restores them (values unchanged)
        c.close()
        return r.status, data

    def test_api_applies_the_same_gates(self):
        s, r = self.post(payload(B_Composition.ATTACKS[0]))
        self.assertEqual((s, r['answers'][0]['prereg_label'], r['evidence_tier']), (200, 'B', 0))
        s, r = self.post(payload(LEAD, organic(E_TierPromotion.NOT_PROMOTED[0])))
        self.assertEqual((s, r['evidence_tier']), (200, 1))
        s, r = self.post(payload(LEAD + ' This combination was banned in India. That prohibition has since been lifted.'))
        self.assertNotEqual(r['answers'][0]['prereg_label'], 'D')
        s, r = self.post(payload(LEAD, organic(CURRENT_BAN)))
        self.assertEqual((s, r['evidence_tier']), (200, 2))
        s, r = self.post(payload(LEAD, refs=[{'index': 0, 'title': T3, 'snippet': 'Dicyclomine + Paracetamol + Chlordiazepoxide tablets.', 'link': 'https://x.invalid/p'}]))
        self.assertEqual(r['answers'][0]['citation_coherence']['references'][0]['relation'], 'CONFLICTING_VIEWS')


if __name__ == '__main__':
    unittest.main()
