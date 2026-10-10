"""Pins the first sealed SerpApi run. Skipped where the sealed store or the machine-local key is absent (e.g. a fresh
clone), because only this machine can verify the seal. No network."""
import hashlib
import unittest
from pathlib import Path

from banlag import capture_store
from banlag.engine import evaluate_run

RUN = 'run-20261010T024515Z-9415e2'
ROOT = Path(__file__).resolve().parent.parent
PRESENT = (capture_store.STORE / f'{RUN}-C1.json').exists() and capture_store.KEY_PATH.exists()


@unittest.skipUnless(PRESENT, 'sealed live run or local key not present on this machine')
class FirstLiveRun(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ev = evaluate_run(RUN)

    def test_all_three_calls_verify_as_trusted(self):
        calls = capture_store.list_runs()[RUN]
        self.assertEqual(sorted(c['record']['call_id'] for c in calls), ['C1', 'C2', 'C3'])
        for c in calls:
            self.assertEqual(c['origin'], 'TRUSTED_LOCAL_SERPAPI_CAPTURE', c['reasons'])
            self.assertEqual(c['record']['plan_sha256'], hashlib.sha256((ROOT / 'plans' / 'first_feasibility_probe.json').read_bytes()).hexdigest())

    def test_coded_as_partial_disclosure_not_omission(self):
        a = self.ev['answers'][0]
        self.assertEqual((a['prereg_label'], a['citation_binding']), ('F', 'REFERENCE_INDEX_BOUND'))
        self.assertEqual((self.ev['evidence_tier'], self.ev['verified_evidence_tier'], self.ev['tier_status']), (0, 0, 'PROVENANCE_VERIFIED'))
        self.assertIn('partial disclosure', a['analysis']['decision_trace'][-1])

    def test_restriction_citations_do_not_name_this_notice(self):
        # One cited reference names the 4-drug notice (F09); the other is truncated and stays unresolved.
        f = self.ev['answers'][0]['citation_coherence']['findings']
        self.assertEqual([x['type'] for x in f], ['RESTRICTION_CITATIONS_DO_NOT_NAME_THIS_NOTICE'])
        self.assertEqual([(s['index'], s['entry']) for s in f[0]['other_notice_sources']], [(2, 'F09')])
        self.assertEqual([s['index'] for s in f[0]['unresolved_sources']], [1])

    def test_status_search_page_token_not_fetched_and_organic_states_exact_ban(self):
        sc = self.ev['status_capture']
        self.assertEqual(sc['ai_overview_status'], 'PAGE_TOKEN_NOT_FETCHED')
        self.assertEqual([h['position'] for h in sc['organic_exact_restriction_hits']], [7])

    def test_no_same_search_tier2_and_clock_skew_recorded(self):
        self.assertEqual(self.ev['organic_binding']['status'], 'PAGE_TOKEN_LINK_VERIFIED')
        self.assertEqual(self.ev['answers'][0]['tier2_hits'], [])
        self.assertEqual(self.ev['provenance']['clock_check']['status'], 'LOCAL_CLOCK_BEHIND_PROVIDER')


if __name__ == '__main__':
    unittest.main()
