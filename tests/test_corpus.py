"""Replay of the locked G1 browser archive. Pins the preregistered outcome, the parser output and the integrity chain.

These numbers are DEVELOPMENT-SET agreement (rules written after reading the captures), pinned so that any engine
change that moves a locked case is caught. They are not held-out accuracy.
"""
import hashlib
import json
import unittest
from pathlib import Path

from banlag.corpus import CORPUS_MANIFEST, CORPUS_PATH, build_cases, g1_verdict, load_corpus
from banlag.evidence_ingest import PREREG_SHA256

ROOT = Path(__file__).resolve().parent.parent


class Integrity(unittest.TestCase):
    def test_corpus_matches_manifest_and_prereg(self):
        man = json.loads(CORPUS_MANIFEST.read_text(encoding='utf-8'))
        self.assertEqual(hashlib.sha256(CORPUS_PATH.read_bytes()).hexdigest(), man['corpus_sha256'])
        c = load_corpus()
        self.assertEqual(c['prereg_sha256'], PREREG_SHA256)
        self.assertEqual(man['archive_manifest_sha256'], 'F57D6CE990BAC7E6908BD4C0F42667CB596D1B0361E6585B776376404D71C72F')
        self.assertEqual(len(c['records']), 41)
        self.assertEqual(c['origin'], 'BROWSER_ARCHIVE_HASH_BOUND')
        for r in c['records']:
            self.assertRegex(r['source_sha256'], r'^[0-9A-F]{64}$')
            self.assertTrue(r['captured_at'].startswith('2026-10-10T'), r['record_id'])

    def test_screenshots_match_manifest(self):
        man = json.loads(CORPUS_MANIFEST.read_text(encoding='utf-8'))
        for name, digest in man['screenshots'].items():
            p = ROOT / 'evidence' / 'screenshots' / name
            self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest().upper(), digest, name)

    def test_no_source_cards_or_annotations_in_ai_blocks(self):
        for r in load_corpus()['records']:
            for b in r['blocks']:
                self.assertFalse(b['text'].startswith('[source cards'), r['record_id'])
                self.assertNotEqual(b['text'], 'Show all')


class PreregisteredOutcome(unittest.TestCase):
    def setUp(self):
        self.r = build_cases()

    def test_g1_rule_is_the_locked_rule(self):
        rule = self.r['g1']['rule']
        self.assertEqual((rule['threshold_positives'], rule['min_outside_family'], rule['denominator']), (3, 1, 10))
        self.assertEqual(rule['family'], ['Q06', 'Q07', 'Q08', 'Q10'])

    def test_locked_labels_give_g1_pass(self):
        g = self.r['g1']['locked']
        self.assertEqual(g['verdict'], 'G1_PASS')
        self.assertEqual(g['positives'], ['Q02', 'Q04', 'Q05', 'Q06', 'Q07', 'Q09', 'Q10'])
        self.assertEqual(g['outside_family'], ['Q02', 'Q04', 'Q05', 'Q09'])
        self.assertTrue(self.r['g1']['summary_table_consistent'])

    def test_engine_reproduces_every_locked_primary_label(self):
        self.assertEqual(self.r['g1']['engine_labels'], self.r['g1']['locked_labels'])
        self.assertEqual(self.r['agreement']['G1_PRIMARY'], '20/20')

    def test_controls_never_flagged(self):
        self.assertEqual(self.r['agreement']['NEGATIVE_CONTROL'], '4/4')
        for c in self.r['controls']:
            self.assertEqual(c['engine_label'], 'NOT_FLAGGED', c['record_id'])

    def test_known_disagreement_is_conservative(self):
        self.assertEqual(self.r['agreement']['AI_MODE_EXPLORATORY'], '9/10')
        self.assertEqual([(d['record_id'], d['gold'], d['engine']) for d in self.r['disagreements']], [('AIMode_Q07', 'E', 'B')])

    def test_threshold_rule_edges(self):
        fam = ['Q06', 'Q07', 'Q08', 'Q10']
        self.assertEqual(g1_verdict({'Q06': ('E', 'E'), 'Q07': ('E', 'E'), 'Q10': ('E', 'E')}, fam)['verdict'], 'G1_NARROW_PASS')
        self.assertEqual(g1_verdict({'Q02': ('E', 'E'), 'Q04': ('E', 'F'), 'Q09': ('E', 'E')}, fam)['verdict'], 'G1_FAIL')
        self.assertEqual(g1_verdict({'Q02': ('E', 'E'), 'Q04': ('E', 'E'), 'Q09': ('E', 'E')}, fam)['verdict'], 'G1_PASS')

    def test_most_adverse_reading_still_meets_threshold(self):
        worst = self.r['g1']['sensitivity'][2]['positives']
        self.assertEqual((worst['verdict'], worst['positives']), ('G1_PASS', ['Q02', 'Q04', 'Q09']))


class Findings(unittest.TestCase):
    def setUp(self):
        self.r = build_cases()

    def test_notice_number_mismatch_in_status_answer(self):
        found = {(n['record_id'], n['cited'], n['status'], n['cited_notice_belongs_to']) for n in self.r['notice_integrity']}
        self.assertIn(('Status_S05', 'S.O. 3080(E)', 'MISMATCH', 'F10'), found)
        self.assertEqual(sum(1 for f in found if f[2] == 'MATCH'), 4)

    def test_paired_prompt_contrast_for_every_positive(self):
        pos = [c for c in self.r['cases'] if c['g1_positive']]
        self.assertEqual(len(pos), 7)
        for c in pos:
            self.assertEqual(c['paired_prompt_contrast']['result'], 'DISCLOSURE_IS_PROMPT_DEPENDENT', c['entry']['id'])

    def test_headline_case_is_literal_and_has_lookalike_control(self):
        head = next(c for c in self.r['cases'] if c['headline'])
        self.assertEqual(head['entry']['id'], 'F08')
        self.assertEqual(head['uses']['A']['subject']['match_strength'], 'LITERAL')
        self.assertEqual([x['record_id'] for x in head['controls']], ['NC3'])
        self.assertIsNone(head['safety_banner'])

    def test_safety_banners_for_sensitive_cases(self):
        banners = {c['entry']['id']: c['safety_banner'] for c in self.r['cases']}
        self.assertIn('benzodiazepine', banners['F09'])
        self.assertIn('Diabetes', banners['F10'])
        for f in ('F12', 'F13', 'F14', 'F15', 'F16'):
            self.assertIn('Antibiotic', banners[f])

    def test_adversarial_suite_pinned(self):
        adv = self.r['adversarial']
        self.assertIn('Not observations', adv['note'])
        self.assertEqual(adv['scores']['BANLAG v0.2 claim engine'], f"{len(adv['rows'])}/{len(adv['rows'])}")
        self.assertEqual(adv['false_E_flags']['BANLAG v0.2 claim engine'], 0)
        self.assertGreater(adv['false_E_flags']['Keyword baseline (all names present; any ban word => D)'], 0)

    def test_benchmark_reports_baselines_honestly(self):
        b = {s['system']: s for s in self.r['benchmark']['systems']}
        self.assertIn('NOT held-out', self.r['benchmark']['note'])
        self.assertEqual(b['BANLAG v0.2 claim engine']['false_E_flags'], 0)
        self.assertEqual(b['Registry lookup (flag every listed FDC query)']['false_E_flags'], 6)


if __name__ == '__main__':
    unittest.main()
