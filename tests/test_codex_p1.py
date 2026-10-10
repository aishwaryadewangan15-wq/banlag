"""Regression tests for the independent Codex hostile audit (10 Oct 2026): five P1 defects and two P2 issues.

Each P1 class contains the original counterexample, broader edge cases, and controls that must keep working, so a fix
cannot pass by over-correcting. Before/after runs of the original counterexamples: docs/proof/codex_p1_*.txt.
"""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from banlag import capture_store, corpus
from banlag.citations import coherence, reference_formulation, relation_to
from banlag.claims import analyze_surface, restriction_statements, unknown_list_items
from banlag.core import classify, match_formula, text_identifies_exact
from banlag.engine import evaluate, evaluate_run
from banlag.legal import entry_by_id

ROOT = Path(__file__).resolve().parent.parent
F08 = entry_by_id('F08')
ING = ['dicyclomine', 'paracetamol', 'clidinium bromide']


def answer(text, organic=None, ingredients=ING):
    g = {'search_metadata': {'id': 'S1'}, 'search_parameters': {'q': 'q'}, 'organic_results': organic or [],
         'ai_overview': {'text_blocks': [{'type': 'paragraph', 'snippet': text}], 'references': []}}
    r = evaluate({'source_kind': 'SYNTHETIC_TEST', 'query': 'q', 'ingredients': list(ingredients), 'google': g})
    return r['answers'][0]['prereg_label'], r['evidence_tier']


class P1_1_UnknownExtraIngredient(unittest.TestCase):
    def test_original_counterexample(self):
        self.assertEqual(answer('The combination of dicyclomine, paracetamol, clidinium bromide and omeprazole is commonly prescribed for cramps.'), ('B', 0))

    def test_unknown_member_in_any_list_position(self):
        for t in ['Omeprazole + dicyclomine + paracetamol + clidinium bromide is commonly prescribed.',
                  'Dicyclomine, omeprazole, paracetamol and clidinium bromide combination is commonly prescribed.',
                  'Dicyclomine/Paracetamol/Clidinium Bromide/Rifaximin tablets are commonly prescribed.',
                  'Dicyclomine + Paracetamol + Clidinium Bromide + Simethicone-free Omeprazole 20 mg is commonly prescribed.',
                  'The combination of dicyclomine, paracetamol and clidinium bromide with omeprazole is commonly prescribed.']:
            self.assertEqual(answer(t)[0], 'B', t)

    def test_controls_stay_exact(self):
        for t in ['A combination of dicyclomine, paracetamol, and clidinium bromide is commonly prescribed.',
                  'Dicyclomine 10 mg + Paracetamol 325 mg + Clidinium Bromide 2.5 mg tablets are commonly prescribed.',
                  'Dicyclomine, an antispasmodic, paracetamol and clidinium bromide are combined in a tablet that is commonly prescribed.',
                  'Dicyclomine, paracetamol and clidinium bromide, typically taken with food, is commonly prescribed.']:
            self.assertEqual(answer(t)[0], 'E', t)
        self.assertEqual(answer('Gliclazide and chromium picolinate, declaring nothing else, is commonly prescribed.', ingredients=['gliclazide', 'chromium picolinate'])[0], 'E')

    def test_every_consumer_of_ingredient_lists_rejects_unknown_members(self):
        self.assertEqual(match_formula(ING + ['omeprazole'])['status'], 'UNKNOWN_FORMULATION')
        self.assertFalse(text_identifies_exact('Section 26A prohibits the fixed dose combination of Dicyclomine + Paracetamol + Clidinium Bromide + Omeprazole in India.', F08))
        for ref in [{'title': 'Dicyclomine + Paracetamol + Clidinium Bromide + Omeprazole Tablets', 'link': 'https://x.invalid/p', 'snippet': ''},
                    {'title': 'Prohibition notice', 'snippet': '', 'link': 'https://x.invalid/fixed-dose-combination-of-dicyclomine-paracetamol-clidinium-bromide-omeprazole-123/'}]:
            self.assertEqual(relation_to(set(ING), reference_formulation(ref)), 'UNRECOGNISED_COMPONENT', ref)
        self.assertEqual(unknown_list_items('dicyclomine, paracetamol and clidinium bromide is used'), [])


class P1_2_CorpusIntegrity(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def variant(self, name, corpus_bytes=None, manifest=None, drop_manifest=False):
        d = self.tmp / name
        d.mkdir()
        (d / 'g1_corpus.json').write_bytes(corpus_bytes if corpus_bytes is not None else (ROOT / 'evidence' / 'g1_corpus.json').read_bytes())
        if not drop_manifest:
            m = manifest if manifest is not None else json.loads((ROOT / 'evidence' / 'CORPUS_MANIFEST.json').read_text(encoding='utf-8'))
            (d / 'CORPUS_MANIFEST.json').write_text(json.dumps(m), encoding='utf-8')
        return corpus.build_cases(str(d / 'g1_corpus.json'), str(d / 'CORPUS_MANIFEST.json'))

    def assert_failed_closed(self, r):
        self.assertEqual(r['corpus']['integrity']['status'], 'FAILED')
        self.assertEqual(r['g1']['locked']['verdict'], 'INTEGRITY_FAILED')
        self.assertEqual((r['g1']['locked']['positives'], r['notice_integrity'], r['controls']), ([], [], []))
        for c in r['cases']:
            self.assertEqual(c['publication_gate']['decision'], 'WITHHOLD')
            self.assertIsNone(c['uses']['A'])
            self.assertFalse(c['g1_positive'])

    def test_original_counterexamples(self):
        raw = (ROOT / 'evidence' / 'g1_corpus.json').read_bytes()
        self.assert_failed_closed(self.variant('tampered', raw.replace(b'is used to treat abdominal cramps', b'is used to treat abdominal crampz', 1)))
        self.assert_failed_closed(self.variant('nomanifest', drop_manifest=True))

    def test_broader_integrity_failures(self):
        man = json.loads((ROOT / 'evidence' / 'CORPUS_MANIFEST.json').read_text(encoding='utf-8'))
        self.assert_failed_closed(self.variant('wrongprereg', manifest=dict(man, prereg_sha256='0' * 64)))
        self.assert_failed_closed(self.variant('wrongarchive', manifest=dict(man, archive_manifest_sha256='0' * 64)))
        self.assert_failed_closed(self.variant('notjson', corpus_bytes=b'{not json'))
        c = json.loads((ROOT / 'evidence' / 'g1_corpus.json').read_text(encoding='utf-8'))
        c['records'] = c['records'][:40]
        data = json.dumps(c).encode('utf-8')
        import hashlib
        self.assert_failed_closed(self.variant('dropped', corpus_bytes=data, manifest=dict(man, corpus_sha256=hashlib.sha256(data).hexdigest())))

    def test_pristine_corpus_verifies(self):
        r = corpus.build_cases()
        self.assertEqual((r['corpus']['integrity']['status'], r['g1']['locked']['verdict']), ('VERIFIED', 'G1_PASS'))


class P1_3_ArchiveProvenance(unittest.TestCase):
    def test_keyless_replay_is_never_provenance_verified(self):
        from tests.test_capture_store import PLAN, KEY, FakeFetch, fake_responses
        from banlag import collector
        import datetime as dt
        import hashlib
        tmp = Path(tempfile.mkdtemp())
        try:
            sha = hashlib.sha256(PLAN.read_bytes()).hexdigest()
            run_id, _ = collector.run(PLAN, sha, env={'BANLAG_SERPAPI_APPROVAL': sha, 'SERPAPI_API_KEY': KEY}, fetch=FakeFetch(fake_responses()),
                                      store=tmp / 's', key_path=tmp / 'k' / 'key', now=lambda: dt.datetime(2026, 10, 10, 10, 0, 5, tzinfo=dt.timezone.utc),
                                      out=lambda *a: None)
            trusted = evaluate_run(run_id, tmp / 's', tmp / 'k' / 'key')
            replay = evaluate_run(run_id, tmp / 's', tmp / 'nokey' / 'key')
            self.assertEqual((trusted['verified_evidence_tier'], trusted['tier_status']), (2, 'PROVENANCE_VERIFIED'))
            self.assertEqual((replay['evidence_tier'], replay['replay_evidence_tier'], replay['verified_evidence_tier']), (2, 2, 0))
            self.assertEqual(replay['tier_status'], 'ARCHIVE_REPLAY_ORIGIN_UNAUTHENTICATED')
            self.assertEqual(replay['publication_gate']['decision'], 'WITHHOLD')
            for p in (tmp / 's').rglob('*'):
                if p.is_file():
                    self.assertNotIn((tmp / 'k' / 'key').read_bytes(), p.read_bytes())
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_browser_archive_is_replay_not_verified(self):
        from banlag import provenance as P
        r = evaluate({'source_kind': 'BROWSER_RESEARCH', 'ingredients': ING, 'captured_at': '2026-10-10T02:00:00+05:30',
                      'ai_overview': {'ai_overview': {'text_blocks': [{'snippet': 'A combination of dicyclomine, paracetamol and clidinium bromide is commonly prescribed.'}]}}},
                     origin_override={'origin': P.BROWSER_ARCHIVE, 'live_verified': False, 'statement': ''})
        self.assertEqual((r['evidence_tier'], r['verified_evidence_tier'], r['replay_evidence_tier']), (1, 0, 1))
        self.assertTrue(any('NOT_CRYPTOGRAPHICALLY_AUTHENTICATED' in c for c in r['publication_gate']['conditions']))
        case = next(c for c in corpus.build_cases()['cases'] if c['entry']['id'] == 'F08')
        self.assertTrue(any('NOT_CRYPTOGRAPHICALLY_AUTHENTICATED' in c for c in case['publication_gate']['conditions']))


class P1_4_RestrictionNegation(unittest.TestCase):
    def test_original_counterexamples(self):
        for t in ['Dicyclomine + paracetamol + clidinium bromide is not currently banned in India and is commonly prescribed.',
                  'Dicyclomine + paracetamol + clidinium bromide is not legally prohibited in India; it is commonly prescribed.',
                  'The ban on dicyclomine + paracetamol + clidinium bromide in India was revoked, and it is commonly prescribed.']:
            self.assertEqual(answer(t)[0], 'F', t)

    def test_broader_negation_and_reversal(self):
        for t in ['Dicyclomine + paracetamol + clidinium bromide is no longer prohibited in India.',
                  'Dicyclomine + paracetamol + clidinium bromide has never been banned in India.',
                  'A court stayed the ban on dicyclomine + paracetamol + clidinium bromide in India.',
                  'The Delhi High Court set aside the prohibition of dicyclomine + paracetamol + clidinium bromide in India.',
                  'India lifted the ban on dicyclomine + paracetamol + clidinium bromide.',
                  'The prohibition of the fixed dose combination of Dicyclomine + Paracetamol + Clidinium Bromide in India was later withdrawn.']:
            self.assertNotEqual(answer(t)[0], 'D', t)
            self.assertFalse(text_identifies_exact(t, F08), t)
        self.assertEqual(classify('The ban on this combination was revoked in India.'), 'LEGAL_STATUS_CONFLICT_REVIEW')

    def test_active_bans_still_detected(self):
        self.assertEqual(answer('Dicyclomine + paracetamol + clidinium bromide is prohibited in India.')[0], 'D')
        f09 = ['dicyclomine', 'paracetamol', 'clidinium bromide', 'chlordiazepoxide']
        # 'historically marketed ... though it has been prohibited': history of USE, current restriction (archive Q03 pattern, shorter).
        self.assertEqual(answer('The combination of dicyclomine, paracetamol, clidinium bromide and chlordiazepoxide was historically marketed for IBS, '
                                'though it has been officially prohibited in India.', ingredients=f09)[0], 'D')


class P1_5_TierRestrictions(unittest.TestCase):
    E = 'A combination of dicyclomine, paracetamol, and clidinium bromide is commonly prescribed.'

    def organic(self, snippet, link='https://news.example.invalid/a'):
        return answer(self.E, [{'position': 1, 'title': 'r', 'link': link, 'snippet': snippet}])[1]

    def test_original_counterexamples_never_give_tier2(self):
        for s in ['The US FDA banned the combination of Dicyclomine + Paracetamol + Clidinium Bromide.',
                  'The prohibition on Dicyclomine + Paracetamol + Clidinium Bromide was revoked by the Central Government.',
                  'Dicyclomine + Paracetamol + Clidinium Bromide was banned in India in 2016.',
                  'The Central Government has proposed to prohibit Dicyclomine + Paracetamol + Clidinium Bromide.',
                  'Dicyclomine + Paracetamol + Clidinium Bromide is banned.']:
            self.assertEqual(self.organic(s), 1, s)

    def test_broader_cases(self):
        for s in ['Dicyclomine + Paracetamol + Clidinium Bromide was previously prohibited in India.',
                  'A draft notification would prohibit Dicyclomine + Paracetamol + Clidinium Bromide in India.',
                  'Dicyclomine + Paracetamol + Clidinium Bromide may be banned in India soon.',
                  'Dicyclomine + Paracetamol + Clidinium Bromide is not banned in India.']:
            self.assertEqual(self.organic(s), 1, s)

    def test_current_indian_restrictions_still_count(self):
        self.assertEqual(self.organic('The Central Government has prohibited the fixed dose combination Dicyclomine + Paracetamol + Clidinium Bromide for human use.'), 2)
        self.assertEqual(self.organic('hereby prohibits the manufacture, sale or distribution of the fixed dose combination of Dicyclomine + Paracetamol + Clidinium Bromide for human use',
                                      link='https://egazette.gov.in/WriteReadData/2026/273649.pdf'), 2)

    def test_tier3_needs_a_current_indian_restriction_too(self):
        url = 'https://ref.example.invalid/p'
        for text in ['The US FDA banned Dicyclomine + Paracetamol + Clidinium Bromide.', 'The ban on Dicyclomine + Paracetamol + Clidinium Bromide in India was revoked.']:
            p = {'source_kind': 'SYNTHETIC_TEST', 'ingredients': ING,
                 'ai_overview': {'ai_overview': {'text_blocks': [{'type': 'paragraph', 'snippet': self.E, 'reference_indexes': [0]}], 'references': [{'index': 0, 'link': url}]}}}
            r = evaluate(p, verified_snapshots=[{'url': url, 'text': text, 'sha256': '0' * 64}])
            self.assertNotEqual(r['evidence_tier'], 3, text)


class P2_CitationUncertainty(unittest.TestCase):
    def test_no_detected_mismatch_is_not_reported_as_coherent(self):
        blocks = [{'id': 'b0', 'type': 'paragraph', 'label': None, 'text': 'A combination of dicyclomine, paracetamol and clidinium bromide is commonly prescribed.',
                   'reference_indexes': [0], 'chips': []}]
        refs = [{'index': 0, 'title': 'Overview', 'link': 'https://x.invalid/a', 'snippet': 'A page.'}]
        a = analyze_surface(blocks, refs, 'REFERENCE_INDEX_BOUND', F08)
        coh = coherence(a, refs)
        self.assertEqual(coh['findings'], [])
        self.assertEqual(coh['status'], 'NO_MISMATCH_DETECTED_PARTIAL_COVERAGE')
        self.assertIn('not proof', coh['note'])
        self.assertNotIn('COHERENT', coh['status'])


if __name__ == '__main__':
    unittest.main()
