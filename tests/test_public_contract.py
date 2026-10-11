"""Public-output contract (banlag/public.py): observed / registered / mechanical facts are public; every machine reading
of prose (labels, tiers, QUALIFYING, contrast, publication gate, SUPPORTED_EXACT) is only under `experimental`.

The legacy interpreter and its tests are untouched; these tests check the public surfaces separately: the Python adapter,
the real HTTP routes, and the executed browser JavaScript. Useful data must stay visible (no pass-by-hiding).
"""
import http.client
import json
import shutil
import subprocess
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

from banlag.capture_store import run_sources
from banlag.engine import evaluate, evaluate_run
from banlag.legal import entry_by_id, match_formula
from banlag.public import EXP, compare_sets, observe_answer, public
from banlag.server import Handler, _evaluate_view
from tests.test_audit4_lead_clause_binding import BAN, LEAD, SQ, X, SealedEndToEnd, organic, payload

ROOT = Path(__file__).resolve().parent.parent
RUN = 'run-20261010T024515Z-9415e2'
PAREN = [X + ' are used to treat abdominal cramps (it does not contain paracetamol).',
         X + ' are used to treat abdominal cramps (it contains omeprazole).']


# Independent of banlag/public.py: parser conclusions Codex reproduced (or listed) as escaping, and their values.
FORBIDDEN_KEYS = {'explicit_exact_entity', 'classification', 'registry_match', 'tier_explanation', 'status_answer_label',
                  'citation_coherence', 'prereg_label', 'engine_label', 'evidence_tier', 'tier', 'verified_evidence_tier',
                  'tier_status', 'tier_basis', 'publication_gate', 'release_status', 'explicit_status_contrast', 'restriction',
                  'types', 'use_binding', 'tier2_hits', 'tier3_hits', 'cited_pages', 'subject', 'flags', 'analysis',
                  'status_capture', 'composition_verdict', 'formulation_supported', 'active_target_india', 'decision_trace',
                  'paired_prompt_contrast', 'contrast', 'g1_engine', 'organic_binding', 'claims'}
FORBIDDEN_VALUES = {'SUPPORTED_EXACT', 'QUALIFYING', 'ELIGIBLE_FOR_REVIEW', 'GENERAL_USE_UNWARNED', 'EXACT_NOTIFICATION_MATCH'}
# Explicit per-route public schemas (top level and the nested objects a judge reads).
EVAL_TOP = {'answers', 'capture_sha256', 'captured_at', 'disclaimer', 'engine_version', 'legal_source', 'legal_status',
            'notice_integrity', 'organic', 'origin', 'project', 'provenance', 'query', 'safety_banner', 'experimental', 'public_contract'}
ANSWER = {'blocks', 'created_at', 'engine', 'references', 'search_id', 'status', 'surface', 'text', 'unknown_block_types',
          'observations', 'source_cards', 'experimental'}
BLOCK = {'chips', 'id', 'label', 'reference_indexes', 'text', 'type', 'experimental'}
RUN_KEYS = {'run_id', 'case', 'plan_sha256', 'calls', 'origin', 'query', 'captured_at', 'safety_banner', 'organic', 'provenance',
       'notice', 'answers', 'experimental', 'error'}


def leaks(obj, path='$'):
    """Forbidden parser conclusions anywhere outside an `experimental` subtree."""
    out = []
    if isinstance(obj, list):
        for i, v in enumerate(obj):
            out += leaks(v, f'{path}[{i}]')
    elif isinstance(obj, dict):
        for k, v in obj.items():
            if k == EXP:
                continue
            if k in FORBIDDEN_KEYS:
                out.append(f'{path}.{k}')
            out += leaks(v, f'{path}.{k}')
    elif isinstance(obj, str) and obj in FORBIDDEN_VALUES:
        out.append(f'{path}={obj}')
    return out


def schema_ok(tc, d, keys, where):
    tc.assertLessEqual(set(d) - {'public_contract'}, keys | {'public_contract'}, where)


def pub_eval(p, **kw):
    return public(_evaluate_view(evaluate(p, **kw)))


def texts(obj):
    if isinstance(obj, dict):
        return ' '.join(texts(v) for v in obj.values())
    if isinstance(obj, list):
        return ' '.join(texts(v) for v in obj)
    return obj if isinstance(obj, str) else ''


class Adapter(unittest.TestCase):
    def test_detector_is_not_vacuous(self):
        raw = _evaluate_view(evaluate(payload(PAREN[0], org=organic(BAN))))
        self.assertTrue(any(x.endswith('.prereg_label') for x in leaks(raw)))
        self.assertTrue(any('SUPPORTED_EXACT' in x for x in leaks(raw)))  # the legacy parser's false exactness, now quarantined

    def test_parenthetical_contradictions_never_reach_public_verdicts(self):
        for t in PAREN:
            for kw in ({}, {'org': organic(BAN)}, {'org': organic(BAN[:-1] + ' (it does not contain paracetamol).')}):
                r = pub_eval(payload(t, **kw))
                self.assertEqual(leaks(r), [], t)
                a = r['answers'][0]
                self.assertIn('prereg_label', a[EXP])           # the legacy reading is kept, quarantined
                self.assertIn(t, texts(a))                      # the authentic text is still shown
                self.assertEqual(a['observations']['blocks'][0]['registry_names_present'], ['clidinium bromide', 'dicyclomine', 'paracetamol'])
        url = 'https://ref.example.invalid/p'
        p = payload(None, refs=[{'index': 0, 'link': url}], blocks=[{'type': 'paragraph', 'snippet': PAREN[0], 'reference_indexes': [0]}])
        r = pub_eval(p, verified_snapshots=[{'url': url, 'text': BAN[:-1] + ' (it contains omeprazole).', 'sha256': '0' * 64}])
        self.assertEqual(leaks(r), [])

    def test_status_question_scope_with_the_engines_object_shape(self):
        ans = 'This combination is prohibited in India.'
        for q in [SQ + ' when combined with omeprazole', 'is metformin prohibited in india', None, SQ]:
            raw = evaluate(payload(LEAD, org=organic(BAN), status={'query': q, 'answer_text': ans}))
            r = public(_evaluate_view(raw))
            self.assertEqual(leaks(r), [], q)
            for k in ('explicit_status_contrast', 'status_answer_label', 'status_question_validation'):
                self.assertNotIn(k, r)
                self.assertEqual(r[EXP].get(k), raw.get(k), k)            # retained, but only as experimental
        raw = evaluate(payload(LEAD, org=organic(BAN), status={'query': SQ + ' when combined with omeprazole', 'answer_text': ans}))
        self.assertEqual(raw['status_answer_label'], 'D')                # Codex's reproduction still holds in the legacy engine...
        self.assertNotIn('status_answer_label', public(raw))             # ...and is no longer public

    def test_codex_p0_payload_and_variants(self):
        base = X + ' are used to treat abdominal cramps'
        for t in PAREN + [base + ': paracetamol is absent.', base + ' — without paracetamol.',
                          LEAD + ' The dispensed formulation contains only dicyclomine and clidinium bromide.']:
            raw = _evaluate_view(evaluate(payload(t, org=organic(BAN))))
            r = public(raw)
            self.assertEqual(leaks(r), [], t)
            schema_ok(self, r, EVAL_TOP, 'evaluate')
            a = r['answers'][0]
            schema_ok(self, a, ANSWER, 'answer')
            for b in a['blocks']:
                schema_ok(self, b, BLOCK, 'block')
            for k in ('explicit_exact_entity', 'classification', 'tier_explanation'):
                self.assertNotIn(k, a); self.assertNotIn(k, r)
            self.assertIn(t, texts(a))                                   # authentic text still public

    def test_structural_indexes(self):
        refs = [{'index': 0, 'title': 'A'}, {'index': 1, 'title': 'B'}, {'index': 1, 'title': 'C'}]
        o = observe_answer([{'id': 'b0', 'text': 't', 'reference_indexes': [True, 1.0, -1, 0, 0, 5, 1]}], refs)
        b = o['blocks'][0]
        self.assertEqual([r['index'] for r in b['linked_references']], [0])
        self.assertEqual([(u['value'], u['reason']) for u in b['unlinked_indexes']],
                         [('True', 'MALFORMED_INDEX'), ('1.0', 'MALFORMED_INDEX'), ('-1', 'MALFORMED_INDEX'),
                          ('5', 'NO_SUCH_REFERENCE'), ('1', 'DUPLICATE_REFERENCE_INDEX')])
        o = observe_answer([{'id': 'b0', 'text': 't', 'reference_indexes': [3]}], [])
        self.assertEqual(o['blocks'][0]['unlinked_indexes'], [{'value': '3', 'reason': 'NO_SUCH_REFERENCE'}])

    def test_truncated_reference_stays_unresolved_and_mentions_are_candidates(self):
        f08 = entry_by_id('F08')
        r = observe_answer([{'id': 'b', 'text': 't', 'reference_indexes': [0, 1]}],
                           [{'index': 0, 'title': 'Dicyclomine, Paracetamol, Clidinium ...'},
                            {'index': 1, 'title': 'Ban on Chlordiazepoxide + Clidinium Bromide + Dicyclomine + Paracetamol', 'snippet': 'S.O. 3071(E) ...'}], f08)
        r0, r1 = r['blocks'][0]['linked_references']
        self.assertIn('cut off', r0['unresolved'])
        self.assertEqual([c['mapping_status'] for c in r1['candidate_entries']], ['CANDIDATE_MAPPING_FROM_NAME_MENTIONS'])
        d = r1['candidate_differences_from_target'][0]
        self.assertEqual((d['to_entry'], d['added'], d['removed']), ('F09', ['chlordiazepoxide'], []))
        self.assertEqual(r1['notice_strings_present'], [{'string': 'S.O. 3071(E)', 'registry_entry': 'F09'}])

    def test_typed_registry_controls(self):
        m = match_formula(['Dicyclomine', 'Paracetamol', 'Clidinium Bromide'])
        self.assertEqual((m['status'], m['entry']['notice']), ('EXACT_NOTIFICATION_MATCH', 'S.O. 3078(E)'))
        c = compare_sets(entry_by_id('F08'), entry_by_id('F09'))
        self.assertEqual((c['added'], c['removed'], c['same_set']), (['chlordiazepoxide'], [], False))

    def test_dummy_sealed_positive_control_is_quarantined_not_hidden(self):
        r = SealedEndToEnd.sealed(None, LEAD, BAN, 'This combination is prohibited in India.')
        self.assertEqual(r['publication_gate']['decision'], 'ELIGIBLE_FOR_REVIEW')  # legacy behaviour unchanged
        p = public(r)
        self.assertEqual(leaks(p), [])
        self.assertEqual(p[EXP]['publication_gate']['decision'], 'ELIGIBLE_FOR_REVIEW')
        self.assertEqual(p['origin'], 'TRUSTED_LOCAL_SERPAPI_CAPTURE')  # provenance stays public
        r = SealedEndToEnd.sealed(None, PAREN[0], BAN)
        self.assertEqual(leaks(public(r)), [])

    @unittest.skipUnless(RUN in run_sources(), 'genuine sealed run not present on this machine')
    def test_keyless_replay_says_origin_not_authenticated(self):
        store_dir, _ = run_sources()[RUN]
        tmp = Path(tempfile.mkdtemp())
        try:
            p = public(evaluate_run(RUN, store=store_dir, key_path=tmp / 'no-key'))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        self.assertNotEqual(p['origin'], 'TRUSTED_LOCAL_SERPAPI_CAPTURE')
        self.assertEqual(leaks(p), [])


class Http(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        threading.Thread(target=cls.s.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.s.shutdown()
        cls.s.server_close()

    def call(self, method, path, body=None):
        c = http.client.HTTPConnection('127.0.0.1', self.s.server_port, timeout=30)
        h = {'Host': f'127.0.0.1:{self.s.server_port}'}
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            h.update({'Content-Type': 'application/json', 'Content-Length': str(len(data))})
        c.request(method, path, body=data, headers=h)
        r = c.getresponse()
        return r.status, json.loads(r.read())

    def test_every_route_honours_the_contract_and_keeps_data(self):
        st, ov = self.call('GET', '/api/overview')
        self.assertEqual((st, leaks(ov)), (200, []))
        self.assertEqual(len(ov['cases']), 10)
        self.assertEqual(ov['g1']['locked']['verdict'], 'G1_PASS')            # preregistered human-coded result stays public
        self.assertIn('benchmark', ov[EXP])
        for c in ov['cases']:
            st, case = self.call('GET', '/api/case/' + c['id'])
            self.assertEqual((st, leaks(case)), (200, []), c['id'])
            self.assertTrue(case['uses']['A']['blocks'])                       # AI text still served
        for path in ('/api/live', '/api/registry', '/api/status'):
            st, d = self.call('GET', path)
            self.assertEqual((st, leaks(d)), (200, []), path)
            self.assertEqual(d['public_contract']['publication'], 'NOT_DETERMINED_BY_SOFTWARE')
        for t in PAREN:
            st, d = self.call('POST', '/api/evaluate', payload(t, org=organic(BAN), status=SQ + ' when combined with omeprazole'))
            self.assertEqual((st, leaks(d)), (200, []))
        st, d = self.call('POST', '/api/match', {'ingredients': ['dicyclomine', 'paracetamol', 'clidinium bromide']})
        # /api/match is a lookup of a TYPED, complete ingredient list in the registry (mechanical), so an exact match is a fact here
        self.assertEqual((st, d['entry']['id'], d['status']), (200, 'F08', 'EXACT_NOTIFICATION_MATCH'))

    @unittest.skipUnless(RUN in run_sources(), 'genuine sealed run not present on this machine')
    def test_genuine_q02_through_http(self):
        st, d = self.call('GET', '/api/case/F08')
        self.assertEqual((st, leaks(d)), (200, []))
        run = next(r for r in d['live_runs'] if r['run_id'] == RUN)
        schema_ok(self, run, RUN_KEYS, 'live run')
        a = run['answers'][0]
        schema_ok(self, a, ANSWER, 'live answer')
        self.assertEqual(a[EXP]['prereg_label'], 'F')                           # historical reading, quarantined
        obs = a['observations']
        self.assertEqual(obs['target']['notice'], 'S.O. 3078(E)')
        ban = next(b for b in obs['blocks'] if 'prohibited' in b['text'])
        self.assertEqual(ban['reference_indexes_as_captured'], ['1', '2'])
        r1, r2 = ban['linked_references']
        self.assertEqual(r2['candidate_differences_from_target'][0]['to_notice'], 'S.O. 3071(E)')
        self.assertEqual(r2['candidate_differences_from_target'][0]['added'], ['chlordiazepoxide'])
        self.assertEqual(r1['candidate_differences_from_target'], [])
        self.assertTrue(r1['unresolved'])
        self.assertTrue(r1['title'] and r2['title'] and r2['link'])


class ExecutedJs(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'node not installed')
    def test_claim_class_has_no_proof_like_class(self):
        src = (ROOT / 'web' / 'app.js').read_text(encoding='utf-8')
        self.assertNotIn('c-restrict', src)
        start = src.index('const QUALIFIERS')
        fn = src[start:src.index('function claimTitle')]
        claim = {'types': [], 'use_binding': 'EXPLICIT_EXACT', 'cues': [],
                 'experimental': {'restriction': {'active_target_india': True, 'formulation_supported': True, 'binding': 'EXPLICIT_EXACT'}}}
        prog = ("const SUBJECT_BINDINGS=['EXPLICIT_EXACT','SUBJECT_ANAPHORA','SUBJECT_IMPLICIT'];const xp=o=>(o&&o.experimental)||{};"
                + fn + f';console.log(claimClass({json.dumps(claim)}));')
        out = subprocess.run(['node', '-e', prog], capture_output=True, text=True, timeout=30)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(out.stdout.strip(), 'c-qualified')


if __name__ == '__main__':
    unittest.main()
