"""RC-3 regressions for Codex's RC-2 acceptance audit (RC2_ACCEPTANCE_AUDIT.md).

P1   the composition validator skipped the sentence that establishes the formulation (and anything before it), so a denial
     of a target ingredient joined by a semicolon / comma, or placed before the lead, kept the formulation exact: false E/T1,
     false D, invalid organic T2 and snapshot T3, and a dummy-sealed 'verified T2, eligible' run.
NOLEAD  a text that never names the target was reported SUPPORTED_EXACT (fail-open default; no full-path exploit was found,
     the default is closed as defence in depth).
P2   a status contrast was accepted without a supplied question, or with a question that names another product.
Every case is paired with a positive control.
"""
import datetime as dt
import hashlib
import shutil
import tempfile
import unittest
from pathlib import Path

from banlag import collector, semantics
from banlag.claims import composition_issues
from banlag.engine import evaluate, evaluate_run

ING = ['dicyclomine', 'paracetamol', 'clidinium bromide']
X = 'Dicyclomine, Paracetamol and Clidinium Bromide'
LEAD = X + ' are used to treat abdominal cramps.'
BAN = 'The Central Government has prohibited the fixed dose combination of ' + X + ' for human use.'
SQ = 'is dicyclomine paracetamol clidinium bromide prohibited for manufacture sale or distribution in india in 2026'
DENY = 'the tablet does not contain paracetamol'


def payload(text, org=None, refs=None, blocks=None, status=None):
    p = {'source_kind': 'SYNTHETIC_TEST', 'query': 'q', 'ingredients': ING,
         'google': {'search_metadata': {'id': 'S1'}, 'search_parameters': {'q': 'q'}, 'organic_results': org or [],
                    'ai_overview': {'text_blocks': blocks or [{'type': 'paragraph', 'snippet': text, 'reference_indexes': [0] if refs else []}],
                                    'references': refs or []}}}
    if status is not None:
        p['explicit_status_query'] = status
    return p


def organic(s):
    return [{'position': 1, 'title': 'Regulatory report', 'link': 'https://news.example.invalid/r', 'snippet': s}]


def lt(text, **kw):
    r = evaluate(payload(text, **kw))
    return r['answers'][0]['prereg_label'], r['evidence_tier']


def t3(statement):
    url = 'https://ref.example.invalid/p'
    p = payload(None, refs=[{'index': 0, 'link': url}], blocks=[{'type': 'paragraph', 'snippet': LEAD, 'reference_indexes': [0]}])
    return evaluate(p, verified_snapshots=[{'url': url, 'text': statement, 'sha256': '0' * 64}])['evidence_tier']


class P1_LeadAndPriorClauses(unittest.TestCase):
    def test_denial_within_or_before_the_lead_is_never_exact(self):
        for t in [LEAD[:-1] + '; ' + DENY + '.', LEAD[:-1] + ', but ' + DENY + '.', 'It does not contain paracetamol. ' + LEAD,
                  X + ' does not contain paracetamol and is used to treat abdominal cramps.']:
            label, tier = lt(t)
            self.assertIn(label, ('B', 'F'), t)
            self.assertEqual(tier, 0, t)
        # A denial in an earlier block: that block names paracetamol, so it is the lead (preregistered rule) -> never exact.
        r = evaluate(payload(None, blocks=[{'type': 'paragraph', 'snippet': 'The tablet does not contain paracetamol.'}, {'type': 'paragraph', 'snippet': LEAD}]))
        self.assertEqual(r['evidence_tier'], 0)
        self.assertNotEqual(r['answers'][0]['analysis']['subject']['composition_verdict'], semantics.EXACT)
        # A pronoun assertion before any ingredient is named has no antecedent yet -> UNRESOLVED (abstain), not exact.
        r = evaluate(payload(None, blocks=[{'type': 'paragraph', 'snippet': 'It also contains caffeine.'}, {'type': 'paragraph', 'snippet': LEAD}]))
        self.assertEqual((r['answers'][0]['prereg_label'], r['evidence_tier']), ('F', 0))
        self.assertEqual(r['answers'][0]['analysis']['subject']['composition_verdict'], semantics.UNRESOLVED)

    def test_no_false_d(self):
        for t in [X + ' does not contain paracetamol. This combination is prohibited in India.',
                  LEAD[:-1] + '; this combination is prohibited in India; ' + DENY + '.']:
            self.assertNotEqual(lt(t)[0], 'D', t)

    def test_no_t2_or_t3_from_contradictory_text(self):
        for s in [BAN[:-1] + '; ' + DENY + '.', 'It does not contain paracetamol. ' + BAN, X + ' does not contain paracetamol. ' + BAN]:
            self.assertEqual(lt(LEAD, org=organic(s)), ('E', 1), s)
            self.assertEqual(t3(s), 1, s)

    def test_controls(self):
        self.assertEqual(lt(LEAD), ('E', 1))
        self.assertEqual(lt(LEAD + ' This combination is prohibited in India.')[0], 'D')
        self.assertEqual(lt(LEAD[:-1] + '; it does not contain omeprazole.'), ('E', 1))
        self.assertEqual(lt(LEAD[:-1] + '; another medicine for reflux does not contain paracetamol.'), ('E', 1))
        self.assertEqual(lt('This combination contains dicyclomine, paracetamol and clidinium bromide; it is used to treat abdominal cramps.'), ('E', 1))
        self.assertEqual(lt(LEAD, org=organic(BAN))[1], 2)
        self.assertEqual(t3(BAN), 3)
        self.assertEqual(composition_issues('It does not contain omeprazole.')['unknown'], [])  # negation is not an addition


class NoLeadDefault(unittest.TestCase):
    def test_text_without_the_target_is_not_established(self):
        self.assertEqual(semantics.text_composition('Antispasmodic combinations are prohibited in India.', ING)['verdict'], semantics.NOT_ESTABLISHED)
        self.assertEqual(semantics.text_composition(BAN, ING)['verdict'], semantics.EXACT)

    def test_no_promotion_without_the_exact_named_target(self):
        for s in ['Dicyclomine and Paracetamol are prohibited in India. Clidinium Bromide too.', X + ' is prohibited in India; chlordiazepoxide is also in it.',
                  'It is prohibited in India.', 'Dicyclomine + Paracetamol is prohibited in India. Clidinium bromide is sold.']:
            self.assertEqual(lt(LEAD, org=organic(s))[1], 1, s)
            self.assertEqual(t3(s), 1, s)


class P2_StatusQuestionBinding(unittest.TestCase):
    def test_contrast_needs_a_supplied_validated_question(self):
        for status in ({'answer_text': 'This combination is prohibited in India.'},
                       {'query': 'is omeprazole prohibited in india', 'answer_text': X + ' is prohibited in India.'}):
            r = evaluate(payload(LEAD, status=status))
            self.assertFalse(r['explicit_status_contrast'], status)
            self.assertTrue(r['status_contrast_why_not'], status)
            self.assertEqual(r['evidence_tier'], 1)  # the uses observation is never changed by the status answer

    def test_status_capture_adapter(self):
        for q, ans, want in ((None, 'This combination is prohibited in India.', False), ('is omeprazole prohibited in india', X + ' is prohibited in India.', False),
                             (SQ, 'This combination is prohibited in India.', True)):
            p = payload(LEAD)
            p['status_capture'] = {'search_metadata': {'id': 'S2'}, 'search_parameters': {'q': q} if q else {},
                                   'ai_overview': {'text_blocks': [{'type': 'paragraph', 'snippet': ans}], 'references': []}, 'organic_results': []}
            self.assertIs(evaluate(p)['explicit_status_contrast'], want, (q, ans))

    def test_validated_question_positive_control(self):
        r = evaluate(payload(LEAD, status={'query': SQ, 'answer_text': 'This combination is prohibited in India.'}))
        self.assertEqual((r['status_answer_label'], r['explicit_status_contrast'], r['status_contrast_why_not']), ('D', True, []))


class SealedEndToEnd(unittest.TestCase):
    def sealed(self, ai_text, org_text, status_text=None):
        from tests.test_capture_store import PLAN, KEY, FakeFetch, fake_responses
        tmp = Path(tempfile.mkdtemp())
        try:
            resp = fake_responses()
            resp[1]['ai_overview']['text_blocks'][0]['snippet'] = ai_text
            resp[0]['organic_results'] = organic(org_text)
            if status_text:
                resp[2]['ai_overview']['text_blocks'][0]['snippet'] = status_text
            sha = hashlib.sha256(PLAN.read_bytes()).hexdigest()
            run_id, _ = collector.run(PLAN, sha, env={'BANLAG_SERPAPI_APPROVAL': sha, 'SERPAPI_API_KEY': KEY}, fetch=FakeFetch(resp),
                                      store=tmp / 'store', key_path=tmp / 'private' / 'key', out=lambda *a: None,
                                      now=lambda: dt.datetime(2026, 10, 10, 10, 0, 5, tzinfo=dt.timezone.utc))
            return evaluate_run(run_id, tmp / 'store', tmp / 'private' / 'key')
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_seal_never_repairs_semantic_invalidity(self):
        r = self.sealed(LEAD[:-1] + '; ' + DENY + '.', BAN)
        self.assertEqual((r['origin'], r['verified_evidence_tier'], r['publication_gate']['decision'], r['explicit_status_contrast']),
                         ('TRUSTED_LOCAL_SERPAPI_CAPTURE', 0, 'WITHHOLD', False))
        r = self.sealed(LEAD, BAN[:-1] + '; ' + DENY + '.')
        self.assertEqual(r['verified_evidence_tier'], 1)

    def test_sealed_positive_control(self):
        r = self.sealed(LEAD, BAN, 'This combination is prohibited in India.')
        self.assertEqual((r['verified_evidence_tier'], r['explicit_status_contrast'], r['publication_gate']['decision']), (2, True, 'ELIGIBLE_FOR_REVIEW'))


if __name__ == '__main__':
    unittest.main()
