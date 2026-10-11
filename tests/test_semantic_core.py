"""Structural regression tests for the shared semantic core (banlag/semantics/) and every promotion path that uses it.

Codex's final acceptance audit (10 Oct 2026) found three P1 families: (1) cross-sentence composition additions left an
answer, organic result, snapshot or citation 'exact'; (2) an Indian restriction on another drug was joined to the target
named elsewhere in the sentence; (3) indirect denials and provisos were read as active bans. These cases are REGRESSIONS
(known examples), not held-out evidence. Each class keeps positive controls so a fix cannot pass by abstaining on everything.
"""
import datetime as dt
import hashlib
import http.client
import json
import re
import shutil
import subprocess
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

from banlag import collector, semantics
from banlag.public import legacy_view, public
from banlag.citations import coherence, reference_formulation, relation_to
from banlag.claims import analyze_surface, restriction_statements
from banlag.core import text_identifies_exact
from banlag.engine import evaluate, evaluate_run
from banlag.legal import entry_by_id

ROOT = Path(__file__).resolve().parent.parent
F08 = entry_by_id('F08')
ING = ['dicyclomine', 'paracetamol', 'clidinium bromide']
X = 'Dicyclomine, Paracetamol and Clidinium Bromide'
LEAD = X + ' are used to treat abdominal cramps.'
BAN = 'The Central Government has prohibited the fixed dose combination of ' + X + ' for human use.'
T = 'Dicyclomine + Paracetamol + Clidinium Bromide Tablets'


def payload(text, org=None, refs=None, blocks=None):
    return {'source_kind': 'SYNTHETIC_TEST', 'query': 'q', 'ingredients': ING,
            'google': {'search_metadata': {'id': 'S1'}, 'search_parameters': {'q': 'q'}, 'organic_results': org or [],
                       'ai_overview': {'text_blocks': blocks or [{'type': 'paragraph', 'snippet': text, 'reference_indexes': [0] if refs else []}],
                                       'references': refs or []}}}


def run(text, org=None, refs=None, snaps=None, blocks=None):
    r = evaluate(payload(text, org, refs, blocks), verified_snapshots=snaps)
    return r['answers'][0]['prereg_label'], r['evidence_tier'], r


def organic(s, url='https://news.example.invalid/r'):
    return [{'position': 1, 'title': 'Regulatory report', 'link': url, 'snippet': s}]


def tiers(statement):
    """(T2 tier from a same-search organic result, T3 tier from a verified snapshot cited by the use claim)."""
    url = 'https://ref.example.invalid/p'
    return (run(LEAD, organic(statement))[1],
            run(LEAD, refs=[{'index': 0, 'link': url}], snaps=[{'url': url, 'text': statement, 'sha256': '0' * 64}])[1])


ADDITIONS = ['Omeprazole is also in it.', 'This medicine has omeprazole as another active ingredient.', 'A fourth component, omeprazole, is included.',
             'Its fourth active ingredient is omeprazole.', 'The same tablet has activated charcoal as its fourth ingredient.',
             'Each tablet additionally comprises light magnesium oxide.', 'The active ingredients are the three above plus rifaximin.',
             'It contains a fourth active ingredient: omeprazole.', 'The formulation additionally contains omeprazole.', 'It also contains omeprazole.',
             'The medicine contains paracetamol and omeprazole.', 'This medicine contains dicyclomine and omeprazole.',
             'Omeprazole is added to this tablet.', 'Its composition also includes omeprazole.', 'The tablet is also formulated with simethicone.',
             'Each capsule contains these three drugs plus domperidone.', 'This FDC also includes a fourth drug, rifaximin.',
             'The product contains four active ingredients.', 'In addition, each tablet carries 20 mg of omeprazole.',
             'Its full composition is dicyclomine, paracetamol, clidinium bromide and simethicone.', 'There is also omeprazole in each tablet.',
             'Apart from the three listed, the tablet holds omeprazole.', 'This particular brand adds caffeine to the three.']
COMPOSITION_CONTROLS = ['Omeprazole is a separate medicine used for acid reflux.', 'The three ingredients are combined in one tablet.',
                        'Dicyclomine relaxes muscles; paracetamol relieves pain.',
                        'Each tablet contains Dicyclomine 10 mg, Paracetamol 325 mg and Clidinium Bromide 2.5 mg.', 'A different product contains omeprazole.',
                        'Omeprazole is also discussed in the article, but it is not an ingredient in this formulation.', 'Omeprazole was prescribed separately.',
                        'The tablet also contains lactose as an excipient.', 'It does not contain omeprazole.', 'It should be taken with food.',
                        'Each tablet holds the three ingredients in fixed doses.', 'Doctors sometimes add omeprazole as a separate tablet.',
                        'The combination contains three active ingredients that work together.']


class CompositionContinuity(unittest.TestCase):
    def test_answer_additions_are_never_exact(self):
        for t in ADDITIONS:
            label, tier, r = run(LEAD + ' ' + t)
            self.assertIn(label, ('B', 'F'), t)
            self.assertEqual(tier, 0, t)
            self.assertNotEqual(r['answers'][0]['analysis']['subject']['composition_verdict'], semantics.EXACT, t)

    def test_ambiguous_holder_abstains_as_f(self):
        label, tier, r = run(LEAD + ' Another medicine is used for reflux. It also contains omeprazole.')
        self.assertEqual((label, tier), ('F', 0))
        self.assertEqual(r['answers'][0]['analysis']['subject']['composition_verdict'], semantics.UNRESOLVED)

    def test_controls_stay_exact(self):
        for t in COMPOSITION_CONTROLS:
            self.assertEqual(run(LEAD + ' ' + t)[:2], ('E', 1), t)
        self.assertEqual(run(X + ' (an antispasmodic combination) are used to treat abdominal cramps.')[:2], ('E', 1))

    def test_addition_across_blocks(self):
        blocks = [{'type': 'paragraph', 'snippet': LEAD}, {'type': 'paragraph', 'snippet': 'The formulation also contains chlordiazepoxide.'}]
        label, tier, r = run(None, blocks=blocks)
        self.assertEqual((label, tier), ('B', 0))
        self.assertIn('chlordiazepoxide', r['answers'][0]['analysis']['subject']['ingredients'])

    def test_organic_and_snapshot_share_composition_state(self):
        for s in [X + ' is prohibited in India. Omeprazole is also in it.', X + ' is prohibited in India. This formulation also contains Chlordiazepoxide.',
                  BAN + ' Each tablet also has 20 mg of omeprazole.']:
            self.assertEqual(tiers(s), (1, 1), s)
            self.assertEqual(restriction_statements(s, F08), [], s)
            self.assertFalse(text_identifies_exact(s, F08), s)
        # an addition stated before the formulation is named cannot be attached safely either
        self.assertEqual(tiers('This formulation also contains chlordiazepoxide. ' + X + ' is prohibited in India.'), (1, 1))

    def test_citation_views_carry_cross_sentence_additions(self):
        for ref, want in [({'title': T, 'snippet': LEAD + ' Omeprazole is also in it.'}, ('UNRECOGNISED_COMPONENT',)),
                          ({'title': T, 'snippet': LEAD + ' This formulation also contains Chlordiazepoxide.'}, ('CONFLICTING_VIEWS',)),
                          ({'title': T, 'snippet': '', 'link': 'https://x.invalid/dicyclomine-paracetamol-clidinium-bromide-activated-charcoal'},
                           ('UNRECOGNISED_COMPONENT',)),
                          ({'title': T, 'snippet': '', 'link': 'https://x.invalid/dicyclomine-paracetamol-clidinium-bromide-tablets-uses-price'}, ('EXACT',)),
                          ({'title': T, 'snippet': LEAD + ' Dicyclomine relaxes gut muscle.'}, ('EXACT',))]:
            f = reference_formulation(dict({'link': 'https://x.invalid/p'}, **ref, index=0))
            self.assertIn(relation_to(set(ING), f), want, ref)


class PredicateEntityBinding(unittest.TestCase):
    WRONG_ENTITY = [X + ' is banned in Canada, but omeprazole is prohibited in India.', X + ' is banned in Canada, whereas rifaximin is prohibited in India.',
                    X + ' is prescribed for cramps, while omeprazole is prohibited in India.',
                    X + ' is legal in India, but chlordiazepoxide combinations are banned in India.', 'Omeprazole is banned in India, unlike ' + X + '.',
                    'India has banned omeprazole, while ' + X + ' remains available.', X + ' is banned in Bhutan and sold in India.']

    def test_answer_never_d_from_another_entity(self):
        for s in self.WRONG_ENTITY + ['This combination is banned in Canada, but omeprazole is prohibited in India.']:
            self.assertNotEqual(run(LEAD + ' ' + s)[0], 'D', s)

    def test_t2_t3_never_from_another_entity(self):
        for s in self.WRONG_ENTITY:
            self.assertEqual(tiers(s), (1, 1), s)

    def test_one_event_per_predicate(self):
        evs = semantics.resolve_chronology(semantics.sentence_events(X + ' is banned in Canada, but omeprazole is prohibited in India.', set(ING)))
        self.assertEqual([(e['term'], e['entity'], e['jurisdiction'], semantics.event_qualifies(e)[0]) for e in evs],
                         [('banned', 'TARGET', 'OTHER', False), ('prohibited', 'OTHER', 'INDIA', False)])

    def test_positive_controls(self):
        for s in ['India has banned this combination.', X + ' is now prohibited in India.', 'This combination is prohibited in India and is not prohibited in Canada.',
                  'This combination is prohibited in India. Omeprazole is not banned in India.',
                  'This combination is not only prohibited in India; manufacture, sale and distribution are banned.']:
            self.assertEqual(run(LEAD + ' ' + s)[0], 'D', s)
        for s in [BAN, 'India has banned ' + X + '.', X + ' is prohibited in India.']:
            self.assertEqual(tiers(s), (2, 3), s)


class PolarityAndProvisos(unittest.TestCase):
    NOT_ACTIVE = ['No authority has prohibited this combination in India.', 'It is not true that this combination is banned in India.',
                  'The regulator denies that this combination is prohibited in India.', 'This combination is banned in India if clinically inappropriate.',
                  'This combination is banned in India on condition that a fourth active is added.',
                  'This combination is banned in India, according to an uncorroborated report.', 'There is no ban on this combination in India.',
                  'Reports that this combination is banned in India are false.', 'This combination is banned in India only for paediatric use.',
                  'This combination is banned in India except for export.', 'Nobody has banned this combination in India.',
                  'This combination is prohibited in India for veterinary use only.', 'It is a myth that this combination is banned in India.',
                  'This combination is prohibited in India for children under 12.', 'Earlier reports said this combination was banned in India.']

    def test_not_d(self):
        for s in self.NOT_ACTIVE:
            label = run(LEAD + ' ' + s)[0]
            self.assertNotEqual(label, 'D', s)

    def test_not_promoted(self):
        for s in ['It is not true that ' + X + ' is banned in India.', X + ' is banned in India if clinically inappropriate.',
                  X + ' is prohibited in India for children under 12.', 'Earlier reports said ' + X + ' was banned in India, but that was wrong.',
                  'The regulator denies that ' + X + ' is prohibited in India.']:
            self.assertEqual(tiers(s), (1, 1), s)

    def test_affirmative_controls(self):
        for s in ['No, this combination is banned in India.', 'Yes, this combination is banned in India.',
                  'This combination is banned in India, according to the Gazette notification.', 'The Government of India has prohibited this combination.']:
            self.assertEqual(run(LEAD + ' ' + s)[0], 'D', s)
        self.assertEqual(tiers(BAN), (2, 3))  # 'for human use' is the notice's own scope, not a proviso


class Chronology(unittest.TestCase):
    def test_revocation_is_scoped_to_its_entity_and_position(self):
        cases = {'This combination was banned in India. That prohibition has since been lifted.': 'NOT_D',
                 'This combination was banned in India in 2016. The ban was subsequently revoked.': 'NOT_D',
                 'This combination is prohibited in India. A ban on omeprazole was lifted.': 'D',
                 'This combination was banned in India in 2016. That ban was lifted. This combination is now prohibited again in India.': 'D',
                 'The ban on this combination in India was lifted, but it is now banned again in India.': 'D',
                 'This combination is prohibited in India. An earlier 2016 ban on it was quashed by the Delhi High Court.': 'D',
                 'This combination was prohibited in India. It was later revoked.': 'NOT_D'}
        for s, want in cases.items():
            self.assertEqual(run(LEAD + ' ' + s)[0] == 'D', want == 'D', s)

    def test_organic_chronology(self):
        self.assertEqual(tiers('In 2016, ' + X + ' was banned in India. That prohibition was lifted. In June 2026, ' + X + ' was prohibited again in India.'), (2, 3))
        self.assertEqual(tiers(BAN + ' A ban on omeprazole was lifted.'), (2, 3))
        self.assertEqual(tiers(X + ' was banned in India. That prohibition has since been lifted.'), (1, 1))

    def test_ban_scope_restated_as_another_entity(self):
        self.assertEqual(tiers(X + ' is banned in India. The ban covers the version that also contains chlordiazepoxide.'), (1, 1))
        self.assertEqual(tiers(BAN + ' The ban applies to human use across the entire country.'), (2, 3))


class CitationIndexIntegrity(unittest.TestCase):
    def test_duplicate_index_never_resolves_to_one_reference(self):
        refs = [{'index': 0, 'title': T, 'link': 'https://x.invalid/one'}, {'index': 0, 'title': 'Dicyclomine + Paracetamol + Chlordiazepoxide', 'link': 'https://x.invalid/two'}]
        outcomes = []
        for order in (refs, refs[::-1]):
            coh = run(LEAD, refs=order)[2]['answers'][0]['citation_coherence']
            self.assertEqual(coh['status'], 'NO_MISMATCH_DETECTED_PARTIAL_COVERAGE')
            self.assertTrue(all(x['relation'] == 'AMBIGUOUS_INDEX' for x in coh['references']))
            self.assertEqual(coh['index_problems'][0]['status'], 'DUPLICATE_INDEX')
            outcomes.append(sorted(x['relation'] for c in coh['claims'] for x in c['cited']))
        self.assertEqual(outcomes[0], outcomes[1])  # order-independent

    def test_duplicate_index_cannot_bind_a_t3_snapshot(self):
        url = 'https://ref.example.invalid/p'
        refs = [{'index': 0, 'link': url}, {'index': 0, 'link': 'https://ref.example.invalid/q'}]
        self.assertEqual(run(LEAD, refs=refs, snaps=[{'url': url, 'text': BAN, 'sha256': '0' * 64}])[1], 1)

    def test_malformed_index_is_reported(self):
        refs = [{'index': '0', 'title': T, 'link': 'https://x.invalid/one'}, {'index': 1, 'title': T, 'link': 'https://x.invalid/two'}]
        blocks = [{'id': 'b0', 'type': 'paragraph', 'label': None, 'text': LEAD, 'reference_indexes': [1], 'chips': []}]
        coh = coherence(analyze_surface(blocks, refs, 'REFERENCE_INDEX_BOUND', F08), refs)
        self.assertEqual([p['status'] for p in coh['index_problems']], ['MALFORMED_INDEX'])
        self.assertEqual(coh['status'], 'NO_MISMATCH_DETECTED_PARTIAL_COVERAGE')


class SealedAndGatePaths(unittest.TestCase):
    """End-to-end through the collector with a fake fetcher and a scratch DUMMY key (never a real key or API call)."""

    def sealed(self, ai_text, organic_text):
        from tests.test_capture_store import PLAN, KEY, FakeFetch, fake_responses
        tmp = Path(tempfile.mkdtemp())
        try:
            resp = fake_responses()
            resp[1]['ai_overview']['text_blocks'][0]['snippet'] = ai_text
            resp[0]['organic_results'] = organic(organic_text)
            sha = hashlib.sha256(PLAN.read_bytes()).hexdigest()
            run_id, _ = collector.run(PLAN, sha, env={'BANLAG_SERPAPI_APPROVAL': sha, 'SERPAPI_API_KEY': KEY}, fetch=FakeFetch(resp),
                                      store=tmp / 'store', key_path=tmp / 'private' / 'key', out=lambda *a: None,
                                      now=lambda: dt.datetime(2026, 10, 10, 10, 0, 5, tzinfo=dt.timezone.utc))
            return evaluate_run(run_id, tmp / 'store', tmp / 'private' / 'key')
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_authentic_seal_never_repairs_a_semantic_failure(self):
        r = self.sealed(LEAD + ' Omeprazole is also in it.', BAN)
        self.assertEqual((r['origin'], r['answers'][0]['prereg_label'], r['verified_evidence_tier']), ('TRUSTED_LOCAL_SERPAPI_CAPTURE', 'B', 0))
        self.assertEqual(r['publication_gate']['decision'], 'WITHHOLD')
        self.assertTrue(any(w.startswith('TEXT_COMPOSITION_NOT_SUPPORTED_EXACT') for w in r['publication_gate']['withhold_reasons']))
        r = self.sealed(LEAD, X + ' is banned in Canada, but omeprazole is prohibited in India.')
        self.assertEqual((r['answers'][0]['prereg_label'], r['verified_evidence_tier']), ('E', 1))
        self.assertTrue(r['answers'][0]['organic_not_qualifying'])

    def test_sealed_positive_control_still_verifies(self):
        r = self.sealed(LEAD, BAN)
        self.assertEqual((r['verified_evidence_tier'], r['publication_gate']['decision']), (2, 'ELIGIBLE_FOR_REVIEW'))
        self.assertIn('HUMAN_REVIEW_REQUIRED', r['publication_gate']['conditions'])

    def test_status_capture_uses_the_same_gate(self):
        p = payload(LEAD)
        p['status_capture'] = {'search_metadata': {'id': 'S2'}, 'search_parameters': {'q': 'is it banned'},
                               'organic_results': organic(X + ' is banned in Canada, but omeprazole is prohibited in India.') +
                               [{'position': 2, 'title': 'Gazette', 'link': 'https://egazette.gov.in/x.pdf', 'snippet': BAN}]}
        hits = evaluate(p)['status_capture']['organic_exact_restriction_hits']
        self.assertEqual([h['position'] for h in hits], [2])


class HTTPAndUI(unittest.TestCase):
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
        return data

    def test_api_applies_the_semantic_gates(self):
        self.assertEqual(self.post(payload(LEAD + ' Omeprazole is also in it.'))['evidence_tier'], 0)
        self.assertEqual(self.post(payload(LEAD, organic(X + ' is banned in Canada, but omeprazole is prohibited in India.')))['evidence_tier'], 1)
        self.assertNotEqual(self.post(payload(LEAD + ' No authority has prohibited this combination in India.'))['answers'][0]['prereg_label'], 'D')
        self.assertEqual(self.post(payload(LEAD, organic(BAN)))['evidence_tier'], 2)

    def test_green_highlight_follows_the_final_event_status(self):
        node = shutil.which('node')
        if not node:
            self.skipTest('node not installed: UI class logic not executed')
        js = (ROOT / 'web' / 'app.js').read_text(encoding='utf-8')
        fn = re.search(r'const QUALIFIERS = .*?\nfunction claimClass\(c\) \{.*?\n\}', js, re.S).group(0)
        sb = re.search(r'const SUBJECT_BINDINGS = [^;]+;', js).group(0)
        claims = {}
        for s in ['This combination is prohibited in India.', 'This combination was banned in India, but the ban was revoked.',
                  'This combination is banned in India if clinically inappropriate.', 'This combination is banned in Canada.',
                  'It is not true that this combination is banned in India.']:
            a = run(LEAD + ' ' + s)[2]['answers'][0]['analysis']
            claims[s] = next(c for c in a['claims'] if c.get('restriction'))
        claims = {k: public(v) for k, v in claims.items()}  # what the browser actually receives (per claim)
        script = sb + '\nconst xp = o => (o && o.experimental) || {};\n' + fn + '\nconst C = ' + json.dumps(claims) + ';\nconsole.log(JSON.stringify(Object.fromEntries(Object.entries(C).map(([k, c]) => [k, claimClass(c)]))));'
        out = json.loads(subprocess.run([node, '-e', script], capture_output=True, text=True, timeout=30, check=True).stdout)
        # CONTRACT CHANGE (final workbench): no proof-like green class exists in the public UI, so no reading gets 'c-restrict'
        # (was: the affirmed current Indian reading got 'c-restrict'; every other reading must not - still asserted).
        for k, v in out.items():
            self.assertNotEqual(v, 'c-restrict', k)
        self.assertEqual(out['This combination is prohibited in India.'], 'c-qualified')


if __name__ == '__main__':
    unittest.main()
