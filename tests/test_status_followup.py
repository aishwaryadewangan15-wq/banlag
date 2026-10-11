"""Status-query AI Overview follow-up: a status search whose AI Overview arrives as a page_token can now be completed in
the same sealed run (role status_ai_overview), and that link never upgrades the uses-search binding."""
import json
from pathlib import Path

from banlag.engine import evaluate_run
from tests.test_capture_store import KEY, Q, SQ, Base, FakeFetch, md

ING = ['dicyclomine', 'paracetamol', 'clidinium bromide']
LOC = {'gl': 'in', 'hl': 'en', 'google_domain': 'google.co.in', 'location': 'Mumbai,Maharashtra,India', 'device': 'desktop', 'no_cache': 'true'}
BAN = ('Yes, the fixed-dose combination of Dicyclomine + Paracetamol + Clidinium Bromide is prohibited in India '
       'under S.O. 3078(E).')


def plan(tmp, with_followup=True):
    calls = [{'call_id': 'C1', 'role': 'uses_search', 'engine': 'google', 'params': {'q': Q, **LOC}},
             {'call_id': 'C2', 'role': 'status_search', 'engine': 'google', 'params': {'q': SQ, **LOC}}]
    if with_followup:
        calls.append({'call_id': 'C3', 'role': 'status_ai_overview', 'engine': 'google_ai_overview', 'page_token_from': 'C2', 'params': {}})
    p = Path(tmp) / 'status_plan.json'
    p.write_text(json.dumps({'schema': 'banlag.plan.v1', 'purpose': 'test', 'case': 'F08', 'ingredients': ING,
                             'max_calls': len(calls), 'calls': calls}), encoding='utf-8')
    return p


def responses():
    c1 = {**md('6707a5e0aaaaaaaaaaaaaab1', 'google', Q), 'ai_overview': {'page_token': 'USES-TOKEN'}, 'organic_results': []}
    c2 = {**md('6707a5e0aaaaaaaaaaaaaab2', 'google', SQ), 'ai_overview': {'page_token': 'STATUS-TOKEN'}, 'organic_results': []}
    c3 = {**md('6707a5e0aaaaaaaaaaaaaab3', 'google_ai_overview', token='STATUS-TOKEN'),
          'ai_overview': {'text_blocks': [{'type': 'paragraph', 'snippet': BAN}], 'references': []}}
    return [c1, c2, c3]


class StatusFollowUp(Base):
    def run_and_evaluate(self, with_followup):
        p = plan(self.tmp, with_followup)
        import hashlib
        sha = hashlib.sha256(p.read_bytes()).hexdigest()
        env = {'BANLAG_SERPAPI_APPROVAL': sha, 'SERPAPI_API_KEY': KEY}
        f = FakeFetch(responses()[:3 if with_followup else 2])
        run_id, n = self.run_plan(f, plan=p, approve=sha, env=env)
        return f, n, evaluate_run(run_id, store=self.store, key_path=self.key, now=self.clock())

    def test_follow_up_uses_the_status_page_token_and_the_answer_is_read(self):
        f, n, r = self.run_and_evaluate(True)
        self.assertEqual(n, 3)
        self.assertEqual(f.calls[2]['page_token'], 'STATUS-TOKEN')
        sc = r['status_capture']
        self.assertEqual(sc['ai_overview_status'], 'PRESENT')
        self.assertEqual(sc['label'], 'D')
        self.assertEqual(sc['notice_checks'][0]['status'], 'MATCH')

    def test_without_follow_up_the_gap_stays_visible(self):
        _, n, r = self.run_and_evaluate(False)
        self.assertEqual(n, 2)
        self.assertEqual(r['status_capture']['ai_overview_status'], 'PAGE_TOKEN_NOT_FETCHED')
        self.assertIsNone(r['status_capture']['label'])

    def test_a_verified_status_link_never_upgrades_the_uses_binding(self):
        _, _, r = self.run_and_evaluate(True)
        self.assertNotEqual(r['organic_binding'].get('status'), 'PAGE_TOKEN_LINK_VERIFIED')
        links = r['provenance']['linkage']
        self.assertEqual([(x['role'], x['page_token_link']) for x in links if 'page_token_link' in x], [('status_ai_overview', 'VERIFIED')])
