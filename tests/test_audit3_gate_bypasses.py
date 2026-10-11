"""RC-2 regressions for Codex's RC-1 architecture audit (RC1_ARCHITECTURE_AUDIT.md): two P1 gate bypasses and five P2
integration gaps. Each case is paired with a positive control so the repair cannot pass by refusing everything.

P1-1  a denied TARGET ingredient ('It does not contain paracetamol') was skipped by the additions-only shortcut, and the
      negation compared every name in the sentence (so 'X, Y and Z does not contain omeprazole' wrongly became non-exact).
P1-2  a status answer with a query hint was never composition-checked ('This formulation also contains omeprazole. This
      combination is prohibited in India.' -> D and a false status contrast).
P2    strict claim-side index validation; citation restriction support bound to one formulation and one qualifying
      predicate; green highlight needs the formulation-level verdict; source chips disclose duplicate/malformed indexes;
      the publication gate fails closed without composition input.
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

from banlag import collector, provenance as P
from banlag.public import legacy_view, public
from banlag.citations import coherence
from banlag.claims import analyze_surface, status_question_hint
from banlag.engine import evaluate, evaluate_run, publication_gate
from banlag.legal import entry_by_id, registry

ROOT = Path(__file__).resolve().parent.parent
F08 = entry_by_id('F08')
ING = ['dicyclomine', 'paracetamol', 'clidinium bromide']
X = 'Dicyclomine, Paracetamol and Clidinium Bromide'
LEAD = X + ' are used to treat abdominal cramps.'
BAN = 'The Central Government has prohibited the fixed dose combination of ' + X + ' for human use.'
NEG = 'It does not contain paracetamol.'
BAD_STATUS = 'This formulation also contains omeprazole. This combination is prohibited in India.'
STATUS_Q = 'is dicyclomine paracetamol clidinium bromide prohibited for manufacture sale or distribution in india in 2026'


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


def t3(statement, idx=(0,)):
    url = 'https://ref.example.invalid/p'
    p = payload(None, refs=[{'index': 0, 'link': url}], blocks=[{'type': 'paragraph', 'snippet': LEAD, 'reference_indexes': list(idx)}])
    return evaluate(p, verified_snapshots=[{'url': url, 'text': statement, 'sha256': '0' * 64}])['evidence_tier']


class P1_1_DeniedTargetIngredient(unittest.TestCase):
    def test_denied_target_active_is_never_exact(self):
        self.assertEqual(lt(LEAD + ' ' + NEG), ('B', 0))
        self.assertEqual(lt(LEAD + ' Paracetamol is not in it.')[1], 0)
        r = evaluate(payload(LEAD + ' ' + NEG))
        self.assertEqual(r['answers'][0]['analysis']['subject']['composition_verdict'], 'DIFFERENT')

    def test_no_t2_or_t3_from_a_text_that_denies_a_target_active(self):
        self.assertEqual(lt(LEAD, org=organic(BAN + ' ' + NEG))[1], 1)
        self.assertEqual(t3(BAN + ' ' + NEG), 1)

    def test_denied_non_member_changes_nothing(self):
        for t in [X + ' does not contain omeprazole.', 'It does not contain omeprazole.', 'It contains no omeprazole.',
                  'Another medicine, used for reflux, does not contain paracetamol.']:
            self.assertEqual(lt(LEAD + ' ' + t), ('E', 1), t)

    def test_positive_controls(self):
        self.assertEqual(lt(LEAD), ('E', 1))
        self.assertEqual(lt(LEAD, org=organic(BAN))[1], 2)
        self.assertEqual(t3(BAN), 3)


class P1_2_QueryHintedStatus(unittest.TestCase):
    def test_contradictory_status_answer_is_not_d(self):
        for status in ({'query': STATUS_Q, 'answer_text': BAD_STATUS}, {'answer_text': BAD_STATUS}):
            r = evaluate(payload(LEAD, status=status))
            self.assertNotEqual(r['status_answer_label'], 'D', status)
            self.assertFalse(r['explicit_status_contrast'], status)

    def test_status_question_must_name_exactly_the_target(self):
        self.assertEqual(status_question_hint(STATUS_Q, F08)[1], 'STATUS_QUESTION_NAMES_EXACT_TARGET')
        self.assertIsNone(status_question_hint(STATUS_Q.replace('bromide', 'bromide omeprazole'), F08)[0])
        self.assertIsNone(status_question_hint('is dicyclomine paracetamol prohibited in india', F08)[0])
        r = evaluate(payload(LEAD, status={'query': STATUS_Q.replace('bromide', 'bromide omeprazole'), 'answer_text': 'This combination is prohibited in India.'}))
        self.assertFalse(r['explicit_status_contrast'])
        self.assertEqual(r['status_question_validation'], 'STATUS_QUESTION_DOES_NOT_NAME_EXACTLY_THE_TARGET')

    def test_status_capture_path(self):
        p = payload(LEAD)
        p['status_capture'] = {'search_metadata': {'id': 'S2'}, 'search_parameters': {'q': STATUS_Q},
                               'ai_overview': {'text_blocks': [{'type': 'paragraph', 'snippet': BAD_STATUS}], 'references': []}, 'organic_results': []}
        r = evaluate(p)
        self.assertEqual((r['status_capture']['label'], r['status_capture']['composition_verdict']), ('B', 'DIFFERENT'))
        self.assertFalse(r['explicit_status_contrast'])

    def test_hint_resolves_subject_but_is_checked(self):
        a = analyze_surface([{'id': 'b0', 'type': 'paragraph', 'label': None, 'text': BAD_STATUS, 'chips': []}], target_entry=F08, subject_hint=set(ING))
        self.assertEqual((a['subject']['source'], a['subject']['composition_verdict']), ('QUERY_HINT', 'DIFFERENT'))
        self.assertNotEqual(a['prereg_label'], 'D')

    def test_positive_controls(self):
        # RC-3: the question-absent variant was removed from this positive control because the owner's RC-3 instruction
        # forbids a contrast without a supplied, validated question; it is asserted as rejected in tests/test_audit4_lead_clause_binding.py.
        for status in ({'query': STATUS_Q, 'answer_text': 'This combination is prohibited in India.'},):
            r = evaluate(payload(LEAD, status=status))
            self.assertEqual((r['status_answer_label'], r['explicit_status_contrast']), ('D', True), status)


class P2_Integration(unittest.TestCase):
    def test_malformed_claim_indexes_never_bind(self):
        for bad in (False, 0.0, '0', None):
            self.assertEqual(t3(BAN, idx=(bad,)), 1, repr(bad))
        r = evaluate(payload(None, refs=[{'index': 0, 'link': 'https://x.invalid/a'}], blocks=[{'type': 'paragraph', 'snippet': LEAD, 'reference_indexes': [False]}]))
        self.assertEqual(r['answers'][0]['analysis']['claims'][0]['citations']['malformed_indexes'], ['False'])

    def test_list_level_indexes_keep_types(self):
        blocks = [{'type': 'list', 'reference_indexes': [0], 'list': [{'snippet': LEAD, 'reference_indexes': [False]}]}]
        r = evaluate(payload(None, refs=[{'index': 0, 'link': 'https://x.invalid/a', 'source': 'S'}], blocks=blocks))
        self.assertEqual(r['answers'][0]['blocks'][0]['reference_indexes'], [False, 0])

    def test_citation_restriction_support_binds_one_formulation(self):
        blocks = [{'id': 'b0', 'type': 'paragraph', 'label': None, 'text': LEAD, 'reference_indexes': [], 'chips': []},
                  {'id': 'b1', 'type': 'paragraph', 'label': None, 'text': 'This combination is prohibited in India.', 'reference_indexes': [0], 'chips': []}]
        split = {'index': 0, 'title': X + ' tablets', 'snippet': 'Chlordiazepoxide is prohibited in India.', 'link': 'https://x.invalid/p', 'source': 'S'}
        coh = coherence(analyze_surface(blocks, [split], 'REFERENCE_INDEX_BOUND', F08), [split])
        self.assertEqual(coh['status'], 'MISMATCH_DETECTED')
        self.assertEqual(coh['references'][0]['restriction_support'], 'MENTION_ONLY')
        good = {'index': 0, 'title': 'Prohibition of ' + X, 'snippet': BAN, 'link': 'https://x.invalid/q', 'source': 'S'}
        coh = coherence(analyze_surface(blocks, [good], 'REFERENCE_INDEX_BOUND', F08), [good])
        self.assertEqual((coh['status'], coh['references'][0]['restriction_support']), ('NO_MISMATCH_DETECTED', 'QUALIFYING'))

    def test_green_highlight_needs_the_formulation_verdict(self):
        node = shutil.which('node')
        if not node:
            self.skipTest('node not installed: UI class logic not executed')
        js = (ROOT / 'web' / 'app.js').read_text(encoding='utf-8')
        fn = re.search(r'const QUALIFIERS = .*?\nfunction claimClass\(c\) \{.*?\n\}', js, re.S).group(0)
        sb = re.search(r'const SUBJECT_BINDINGS = [^;]+;', js).group(0)
        claims = {}
        for k, s in (('rejected', LEAD + ' This combination is prohibited in India. Omeprazole is also in it.'),
                     ('denied', LEAD + ' This combination is prohibited in India. ' + NEG), ('exact', LEAD + ' This combination is prohibited in India.')):
            an = evaluate(payload(s))['answers'][0]['analysis']
            claims[k] = next(c for c in an['claims'] if c.get('restriction'))
        claims = {k: public(v) for k, v in claims.items()}  # what the browser actually receives (per claim)
        script = sb + '\nconst xp = o => (o && o.experimental) || {};\n' + fn + '\nconst C=' + json.dumps(claims) + ';console.log(JSON.stringify(Object.fromEntries(Object.entries(C).map(([k,c])=>[k,claimClass(c)]))))'
        out = json.loads(subprocess.run([node, '-e', script], capture_output=True, text=True, timeout=30, check=True).stdout)
        # CONTRACT CHANGE (final workbench): the proof-like green class 'c-restrict' was removed from the public UI; the parser's
        # 'exact' reading is now shown like every other restriction reading (experimental). Was: 'exact': 'c-restrict'.
        self.assertEqual(out, {'rejected': 'c-qualified', 'denied': 'c-qualified', 'exact': 'c-qualified'})

    def test_source_chips_disclose_duplicate_and_malformed_indexes(self):
        from banlag.server import _answer_view
        refs = [{'index': 0, 'title': 'A', 'link': 'https://x.invalid/1', 'source': 'First source'},
                {'index': 0, 'title': 'B', 'link': 'https://x.invalid/2', 'source': 'Second source'},
                {'index': 1, 'title': 'C', 'link': 'https://x.invalid/3', 'source': 'Third source'}]
        blocks = [{'type': 'paragraph', 'snippet': LEAD, 'reference_indexes': [0, 1, False]}]
        chips = [c['source'] for c in _answer_view(evaluate(payload(None, refs=refs, blocks=blocks))['answers'][0])['blocks'][0]['chips']]
        self.assertEqual(chips, ['[0] ambiguous — 2 references share this index', '[1] Third source', '[False] malformed index — not linked'])

    def test_publication_gate_fails_closed_without_composition(self):
        args = (P.TRUSTED, {'status': 'EXACT_NOTIFICATION_MATCH', 'match_strength': 'LITERAL'}, '2026-10-10T10:00:00+00:00', True, registry()['legal_status'])
        self.assertEqual(publication_gate(*args)['withhold_reasons'], ['COMPOSITION_VALIDATION_MISSING'])
        self.assertIn('NO_AI_TEXT_COMPOSITION_ESTABLISHED', publication_gate(*args, text_composition=[])['withhold_reasons'])
        self.assertIn('TEXT_COMPOSITION_NOT_SUPPORTED_EXACT (DIFFERENT)', publication_gate(*args, text_composition=['DIFFERENT'])['withhold_reasons'])
        self.assertEqual(publication_gate(*args, text_composition=['SUPPORTED_EXACT'])['decision'], 'ELIGIBLE_FOR_REVIEW')


class EndToEnd(unittest.TestCase):
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

    def test_dummy_key_sealed_runs(self):
        r = self.sealed(LEAD + ' ' + NEG, BAN)
        self.assertEqual((r['origin'], r['answers'][0]['prereg_label'], r['verified_evidence_tier'], r['publication_gate']['decision']),
                         ('TRUSTED_LOCAL_SERPAPI_CAPTURE', 'B', 0, 'WITHHOLD'))
        r = self.sealed(LEAD, BAN, BAD_STATUS)
        self.assertEqual((r['status_capture']['label'], r['explicit_status_contrast']), ('B', False))
        r = self.sealed(LEAD, BAN, 'This combination is prohibited in India.')  # positive control
        self.assertEqual((r['verified_evidence_tier'], r['status_capture']['label'], r['explicit_status_contrast'], r['publication_gate']['decision']),
                         (2, 'D', True, 'ELIGIBLE_FOR_REVIEW'))

    def test_http_api(self):
        from banlag.server import Handler
        srv = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        th = threading.Thread(target=srv.serve_forever, daemon=True)
        th.start()
        try:
            def post(obj):
                c = http.client.HTTPConnection('127.0.0.1', srv.server_port, timeout=10)
                c.request('POST', '/api/evaluate', body=json.dumps(obj).encode(), headers={'Content-Type': 'application/json'})
                d = legacy_view(json.loads(c.getresponse().read().decode()))  # public contract: legacy fields are served under "experimental"; legacy_view restores them (values unchanged)
                c.close()
                return d
            self.assertEqual(post(payload(LEAD + ' ' + NEG))['evidence_tier'], 0)
            self.assertFalse(post(payload(LEAD, status={'answer_text': BAD_STATUS}))['explicit_status_contrast'])
            self.assertEqual(post(payload(LEAD, org=organic(BAN)))['evidence_tier'], 2)
        finally:
            srv.shutdown()
            srv.server_close()
            th.join(timeout=3)


if __name__ == '__main__':
    unittest.main()
