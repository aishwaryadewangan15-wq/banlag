"""Collector + sealed store, exercised with a FAKE fetcher. No network, no SerpApi, temp directories only."""
import copy
import datetime as dt
import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from banlag import capture_store, collector
from banlag.engine import evaluate_run

ROOT = Path(__file__).resolve().parent.parent
PLAN = ROOT / 'plans' / 'first_feasibility_probe.json'
KEY = 'sk_test_DO_NOT_LEAK_0123456789'
Q = 'dicyclomine paracetamol clidinium bromide uses'
SQ = 'is dicyclomine paracetamol clidinium bromide prohibited for manufacture sale or distribution in india in 2026'


def md(sid, engine, q=None, token=None):
    out = {'search_metadata': {'id': sid, 'status': 'Success', 'created_at': '2026-10-10 10:00:00 UTC', 'processed_at': '2026-10-10 10:00:02 UTC',
                               'json_endpoint': f'https://serpapi.com/searches/0a1b2c3d/{sid}.json'},
           'search_parameters': {'engine': engine, 'gl': 'in', 'hl': 'en'}}
    if q:
        out['search_parameters']['q'] = q
    if token:
        out['search_parameters']['page_token'] = token
    return out


def fake_responses(inline=False, error_first=False, leak_key=False):
    c1 = {**md('6707a5e0aaaaaaaaaaaaaaa1', 'google', Q),
          'organic_results': [{'position': 1, 'link': 'https://egazette.gov.in/WriteReadData/2026/273649.pdf', 'title': 'Gazette of India',
                               'snippet': 'hereby prohibits the manufacture, sale or distribution of the fixed dose combination of Dicyclomine + Paracetamol + Clidinium Bromide for human use'}]}
    answer = {'text_blocks': [{'type': 'paragraph', 'snippet': 'A combination of dicyclomine, paracetamol and clidinium bromide is used to treat abdominal cramps.', 'reference_indexes': [0]},
                              {'type': 'list', 'list': [{'title': 'Medical supervision:', 'snippet': 'This combination should only be taken as prescribed by a doctor.', 'reference_indexes': [1]}]}],
              'references': [{'index': 0, 'link': 'https://pharmacy.example.invalid/a', 'title': 'A'}, {'index': 1, 'link': 'https://pharmacy.example.invalid/b', 'title': 'B'}]}
    c1['ai_overview'] = answer if inline else {'page_token': 'TOKEN-123'}
    if error_first:
        c1 = {'error': 'Invalid API key.'}
    c2 = {**md('6707a5e1aaaaaaaaaaaaaaa2', 'google_ai_overview', token='TOKEN-123'), 'ai_overview': copy.deepcopy(answer)}
    if leak_key:
        c2['echo'] = 'debug ' + KEY
    c3 = {**md('6707a5e2aaaaaaaaaaaaaaa3', 'google', SQ),
          'ai_overview': {'text_blocks': [{'type': 'paragraph', 'snippet': 'Yes, the fixed-dose combination of Dicyclomine + Paracetamol + Clidinium Bromide is prohibited in India under S.O. 3078(E).'}], 'references': []},
          'organic_results': []}
    return [c1, c2, c3]


class FakeFetch:
    def __init__(self, responses, status=200):
        self.responses, self.calls, self.status = list(responses), [], status

    def __call__(self, params, key):
        assert key == KEY
        self.calls.append(dict(params))
        body = self.responses.pop(0)
        return (401 if 'error' in body else self.status), json.dumps(body).encode('utf-8')


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.store, self.key = self.tmp / 'store', self.tmp / 'key' / 'capture_hmac.key'
        self.sha = hashlib.sha256(PLAN.read_bytes()).hexdigest()
        self.env = {'BANLAG_SERPAPI_APPROVAL': self.sha, 'SERPAPI_API_KEY': KEY}
        self.clock = lambda: dt.datetime(2026, 10, 10, 10, 0, 5, tzinfo=dt.timezone.utc)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_plan(self, fetch, plan=PLAN, approve=None, env=None):
        return collector.run(plan, approve or self.sha, env=self.env if env is None else env, fetch=fetch,
                             store=self.store, key_path=self.key, now=self.clock, out=lambda *a: None)


class ApprovalGates(Base):
    def test_refuses_without_both_signals(self):
        f = FakeFetch(fake_responses())
        with self.assertRaises(collector.Stop):
            self.run_plan(f, env={'SERPAPI_API_KEY': KEY})
        with self.assertRaises(collector.Stop):
            self.run_plan(f, approve='0' * 64)
        self.assertEqual(f.calls, [])

    def test_refuses_edited_plan(self):
        edited = self.tmp / 'plan.json'
        edited.write_text(PLAN.read_text(encoding='utf-8').replace('"max_calls": 3', '"max_calls": 2'), encoding='utf-8')
        f = FakeFetch(fake_responses())
        with self.assertRaises(collector.Stop):
            self.run_plan(f, plan=edited)
        self.assertEqual(f.calls, [])

    def test_refuses_without_key(self):
        f = FakeFetch(fake_responses())
        with self.assertRaises(collector.Stop):
            self.run_plan(f, env={'BANLAG_SERPAPI_APPROVAL': self.sha})
        self.assertEqual(f.calls, [])

    def test_plan_over_hard_cap_rejected(self):
        p = json.loads(PLAN.read_text(encoding='utf-8'))
        p['max_calls'] = 4
        p['calls'].append(dict(p['calls'][0], call_id='C4'))
        bad = self.tmp / 'big.json'
        bad.write_text(json.dumps(p), encoding='utf-8')
        with self.assertRaises(collector.Stop):
            collector.load_plan(bad)

    def test_web_server_cannot_reach_the_network(self):
        """AST closure of every banlag module the server imports: none may import the collector or a network client."""
        import ast
        forbidden = {'banlag.collector', 'urllib.request', 'http.client', 'socket', 'requests', 'ssl'}
        seen, todo = set(), ['server']
        while todo:
            name = todo.pop()
            if name in seen:
                continue
            seen.add(name)
            tree = ast.parse((ROOT / 'banlag' / f'{name}.py').read_text(encoding='utf-8'))
            for node in ast.walk(tree):
                mods = []
                if isinstance(node, ast.Import):
                    mods = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom):
                    base = ('banlag.' + (node.module or '')) if node.level else (node.module or '')
                    mods = [base.rstrip('.')] + ([f'banlag.{a.name}' for a in node.names] if node.level and not node.module else [])
                for m in mods:
                    self.assertNotIn(m, forbidden, f'{name}.py imports {m}')
                    if m.startswith('banlag.') and (ROOT / 'banlag' / (m.split('.', 1)[1].split('.')[0] + '.py')).exists():
                        todo.append(m.split('.', 1)[1].split('.')[0])
        self.assertIn('engine', seen)
        self.assertNotIn('collector', seen)


class SealedRun(Base):
    def test_three_call_run_is_trusted_and_reaches_tier2_with_status_contrast(self):
        f = FakeFetch(fake_responses())
        run_id, n = self.run_plan(f)
        self.assertEqual(n, 3)
        self.assertEqual(f.calls[1]['page_token'], 'TOKEN-123')
        for p in self.store.glob('*.json'):
            self.assertEqual(capture_store.verify(p, self.key)['origin'], 'TRUSTED_LOCAL_SERPAPI_CAPTURE')
        r = evaluate_run(run_id, self.store, self.key, now=self.clock())
        self.assertEqual(r['origin'], 'TRUSTED_LOCAL_SERPAPI_CAPTURE')
        self.assertEqual(r['answers'][0]['prereg_label'], 'E')
        self.assertEqual(r['answers'][0]['citation_binding'], 'REFERENCE_INDEX_BOUND')
        self.assertEqual(r['organic_binding']['status'], 'PAGE_TOKEN_LINK_VERIFIED')
        self.assertEqual((r['evidence_tier'], r['verified_evidence_tier'], r['tier_status']), (2, 2, 'PROVENANCE_VERIFIED'))
        self.assertEqual(r['status_capture']['label'], 'D')
        self.assertEqual(r['status_capture']['notice_checks'][0]['status'], 'MATCH')
        self.assertTrue(r['explicit_status_contrast'])
        self.assertEqual(r['publication_gate']['decision'], 'ELIGIBLE_FOR_REVIEW')

    def test_inline_overview_skips_follow_up_call(self):
        responses = fake_responses(inline=True)
        f = FakeFetch([responses[0], responses[2]])
        run_id, n = self.run_plan(f)
        self.assertEqual(n, 2)
        r = evaluate_run(run_id, self.store, self.key, now=self.clock())
        self.assertEqual(r['organic_binding']['status'], 'SAME_RESPONSE')
        self.assertEqual(r['verified_evidence_tier'], 2)

    def test_provider_error_stops_without_retry(self):
        f = FakeFetch(fake_responses(error_first=True))
        _, n = self.run_plan(f)
        self.assertEqual(n, 1)

    def test_key_never_written(self):
        f = FakeFetch(fake_responses(leak_key=True))
        self.run_plan(f)
        for p in self.store.rglob('*'):
            if p.is_file():
                self.assertNotIn(KEY.encode(), p.read_bytes(), p.name)
        recs = [json.loads(p.read_text(encoding='utf-8'))['record'] for p in self.store.glob('*.json')]
        self.assertTrue(any(r['key_redacted_from_raw'] for r in recs))


class KeyLocationSafety(Base):
    def test_default_key_path_is_outside_project_and_sync_roots(self):
        kp = capture_store.KEY_PATH.resolve()
        self.assertNotIn(ROOT.resolve(), kp.parents)
        self.assertIsNone(capture_store.unsafe_key_reason(kp))
        for label, root in capture_store.synced_roots():
            self.assertNotIn(root, kp.parents, label)

    def assert_refused_before_any_call(self, key_path):
        f = FakeFetch(fake_responses())
        with self.assertRaises(collector.Stop) as cm:
            collector.run(PLAN, self.sha, env=self.env, fetch=f, store=self.store, key_path=key_path, now=self.clock, out=lambda *a: None)
        self.assertEqual(f.calls, [], 'no request may be sent when the key location is unsafe')
        self.assertFalse(Path(key_path).exists())
        self.assertFalse(self.store.exists())
        return str(cm.exception)

    def test_key_refused_inside_project_folder(self):
        self.assertIn('project folder', self.assert_refused_before_any_call(ROOT / '.banlag' / 'capture_hmac.key'))

    def test_key_refused_under_dropbox_marker(self):
        synced = self.tmp / 'synced'
        synced.mkdir()
        (synced / '.dropbox').write_text('{}', encoding='utf-8')
        self.assertIn('Dropbox marker', self.assert_refused_before_any_call(synced / 'k' / 'capture_hmac.key'))

    def test_home_sync_roots_refused(self):
        for name in ('Dropbox', 'OneDrive'):
            self.assertIsNotNone(capture_store.unsafe_key_reason(Path.home() / name / 'BANLAG' / 'capture_hmac.key'), name)

    def test_seal_not_trusted_when_key_sits_in_synced_folder(self):
        run_id, _ = self.run_plan(FakeFetch(fake_responses()))
        synced = self.tmp / 'synced2'
        (synced / 'k').mkdir(parents=True)
        (synced / '.dropbox').write_text('{}', encoding='utf-8')
        shutil.copyfile(self.key, synced / 'k' / 'capture_hmac.key')
        rec = sorted(self.store.glob('*.json'))[0]
        v = capture_store.verify(rec, synced / 'k' / 'capture_hmac.key')
        self.assertEqual(v['origin'], 'ARCHIVED_SERPAPI_CAPTURE')
        self.assertIn('seal not trusted', v['reasons'][0])


class ProviderStatusStops(Base):
    def run_with_status(self, index, status):
        responses = fake_responses()
        responses[index]['search_metadata']['status'] = status
        return self.run_plan(FakeFetch(responses))[1]

    def test_http_200_with_error_status_stops_after_first_call(self):
        self.assertEqual(self.run_with_status(0, 'Error'), 1)

    def test_http_200_still_processing_stops(self):
        self.assertEqual(self.run_with_status(0, 'Processing'), 1)

    def test_unsuccessful_follow_up_stops_before_status_search(self):
        self.assertEqual(self.run_with_status(1, 'Error'), 2)

    def test_missing_metadata_on_http_200_stops(self):
        responses = fake_responses()
        del responses[0]['search_metadata']
        self.assertEqual(self.run_plan(FakeFetch(responses))[1], 1)


class Tamper(Base):
    def setUp(self):
        super().setUp()
        self.run_id, _ = self.run_plan(FakeFetch(fake_responses()))
        self.rec = sorted(self.store.glob('*.json'))[0]

    def test_raw_byte_change_invalidates(self):
        doc = json.loads(self.rec.read_text(encoding='utf-8'))
        raw = self.store / doc['record']['raw_file']
        raw.write_bytes(raw.read_bytes().replace(b'Success', b'Succesz'))
        self.assertEqual(capture_store.verify(self.rec, self.key)['origin'], 'INVALID')
        self.assertEqual(evaluate_run(self.run_id, self.store, self.key)['origin'], 'INVALID')

    def test_record_edit_breaks_seal(self):
        doc = json.loads(self.rec.read_text(encoding='utf-8'))
        doc['record']['received_at'] = '2026-01-01T00:00:00+00:00'
        self.rec.write_text(json.dumps(doc), encoding='utf-8')
        v = capture_store.verify(self.rec, self.key)
        self.assertEqual(v['origin'], 'INVALID')
        self.assertIn('seal mismatch', v['reasons'][0])

    def test_copied_record_without_key_is_only_archived(self):
        v = capture_store.verify(self.rec, self.tmp / 'no' / 'key')
        self.assertEqual(v['origin'], 'ARCHIVED_SERPAPI_CAPTURE')
        r = evaluate_run(self.run_id, self.store, self.tmp / 'no' / 'key')
        self.assertFalse(r['provenance']['live_verified'])
        # Codex P1-3: hash-consistent but unauthenticated replay is never provenance-verified (stricter than before).
        self.assertEqual(r['tier_status'], 'ARCHIVE_REPLAY_ORIGIN_UNAUTHENTICATED')
        self.assertEqual((r['evidence_tier'], r['replay_evidence_tier'], r['verified_evidence_tier']), (2, 2, 0))
        self.assertEqual(r['publication_gate']['decision'], 'WITHHOLD')

    def test_export_for_publication(self):
        dest = capture_store.export_run(self.run_id, store=self.store, dest_root=self.tmp / 'published', key_path=self.key)
        exported = sorted(dest.glob('*.json'))
        self.assertEqual(len([p for p in exported if p.name != 'EXPORT_MANIFEST.json']), 3)
        for p in dest.rglob('*'):
            if p.is_file():
                self.assertNotIn(KEY.encode(), p.read_bytes())
                self.assertNotIn(self.key.read_bytes(), p.read_bytes())
        rec = next(p for p in exported if p.name.endswith('-C1.json'))
        self.assertEqual(capture_store.verify(rec, self.key)['origin'], 'TRUSTED_LOCAL_SERPAPI_CAPTURE')
        self.assertEqual(capture_store.verify(rec, self.tmp / 'nokey' / 'k')['origin'], 'ARCHIVED_SERPAPI_CAPTURE')
        r = evaluate_run(self.run_id, dest, self.tmp / 'nokey' / 'k')
        self.assertEqual((r['origin'], r['verified_evidence_tier'], r['provenance']['live_verified']), ('ARCHIVED_SERPAPI_CAPTURE', 0, False))
        with self.assertRaises(FileExistsError):
            capture_store.export_run(self.run_id, store=self.store, dest_root=self.tmp / 'published', key_path=self.key)

    def test_tampered_run_is_not_exportable(self):
        doc = json.loads(self.rec.read_text(encoding='utf-8'))
        doc['record']['http_status'] = 201
        self.rec.write_text(json.dumps(doc), encoding='utf-8')
        with self.assertRaises(ValueError):
            capture_store.export_run(self.run_id, store=self.store, dest_root=self.tmp / 'published', key_path=self.key)

    def test_records_are_immutable(self):
        doc = json.loads(self.rec.read_text(encoding='utf-8'))
        with self.assertRaises(FileExistsError):
            capture_store.seal(doc['record'], b'{}', store=self.store, key_path=self.key)


if __name__ == '__main__':
    unittest.main()
