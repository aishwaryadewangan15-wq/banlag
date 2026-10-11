"""Batch capture planning (banlag.batch): preregistered wording, budgets, collector-valid plans, nothing sent."""
import contextlib
import datetime as dt
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from banlag import batch, collector

ROOT = Path(__file__).resolve().parent.parent
START = dt.date(2026, 11, 2)


class Wording(unittest.TestCase):
    def test_study_combinations_get_their_preregistered_query_strings_back(self):
        corpus = json.loads((ROOT / 'evidence' / 'g1_corpus.json').read_text(encoding='utf-8'))
        prereg = {}
        for r in corpus['records']:
            if r['kind'] == 'G1_PRIMARY':
                prereg.setdefault(r['target_entry_id'], {})['uses'] = r['query']
            elif r['kind'] == 'STATUS_CONTRAST':
                prereg.setdefault(r['target_entry_id'], {})['status'] = r['query']
        files = batch.build_batch(sorted(prereg), ['mumbai'], 1, START)
        for name, plan in files.items():
            kind = 'uses' if name.endswith('_uses.json') else 'status'
            want = prereg[plan['case']].get(kind)
            if want:
                with self.subTest(name=name):
                    self.assertEqual(plan['calls'][0]['params']['q'], want)

    def test_underspecified_notice_is_never_planned(self):
        files = batch.build_batch(None, ['mumbai'], 1, START)
        self.assertNotIn('F07', {p['case'] for p in files.values()})
        self.assertEqual(len({p['case'] for p in files.values()}), 15)
        with self.assertRaisesRegex(ValueError, 'underspecified'):
            batch.build_batch(['F07'], ['mumbai'], 1, START)
        with self.assertRaisesRegex(ValueError, 'unknown registry ids'):
            batch.build_batch(['F99'], ['mumbai'], 1, START)


class Plans(unittest.TestCase):
    def test_every_plan_passes_the_collector_and_is_unique(self):
        files = batch.build_batch(['F08', 'F04'], ['mumbai', 'delhi'], 2, START)
        self.assertEqual(len(files), 2 * 2 * 2 * 2)
        shas = set()
        with tempfile.TemporaryDirectory() as d:
            for name, plan in files.items():
                p = Path(d) / name
                p.write_text(json.dumps(plan), encoding='utf-8')
                loaded, sha = collector.load_plan(p)
                shas.add(sha)
                self.assertLessEqual(loaded['max_calls'], collector.HARD_CAP)
                self.assertEqual(len(loaded['calls']), loaded['max_calls'])
        self.assertEqual(len(shas), len(files))  # day and location are inside the plan, so no approval is reusable

    def test_follow_ups_point_at_their_own_search(self):
        p = batch.plans_for(batch.capturable_entries(['F08'])[0], 'delhi', 1, START)
        self.assertEqual([(c['role'], c.get('page_token_from')) for c in p['uses']['calls']],
                         [('uses_search', None), ('uses_ai_overview', 'C1'), ('uses_ai_mode', None)])
        self.assertEqual([(c['role'], c.get('page_token_from')) for c in p['status']['calls']],
                         [('status_search', None), ('status_ai_overview', 'C1')])
        self.assertEqual(p['uses']['calls'][0]['params']['location'], 'Delhi,Delhi,India')
        self.assertEqual(p['status']['schedule'], {'day': 1, 'date': '2026-11-02', 'location': 'Delhi,Delhi,India'})

    def test_budget(self):
        b = batch.budget(batch.build_batch(None, ['mumbai', 'delhi'], 3, START))
        self.assertEqual(b['plans'], 15 * 2 * 2 * 3)
        self.assertEqual(b['max_calls'], 15 * 2 * 3 * (3 + 2))
        self.assertEqual(b['min_calls'], 15 * 2 * 3 * (2 + 1))
        self.assertEqual(sorted(b['max_calls_per_day']), ['2026-11-02', '2026-11-03', '2026-11-04'])

    def test_bad_inputs(self):
        with self.assertRaisesRegex(ValueError, 'unknown location'):
            batch.build_batch(None, ['paris'], 1, START)
        with self.assertRaisesRegex(ValueError, 'days must be'):
            batch.build_batch(None, ['mumbai'], 0, START)


class Cli(unittest.TestCase):
    def run_cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = batch.main(list(args))
        return code, out.getvalue(), err.getvalue()

    def test_without_out_nothing_is_written(self):
        code, out, _ = self.run_cli('--locations', 'mumbai')
        self.assertEqual(code, 0)
        self.assertIn('30 plans; SerpApi calls: at most 75, at least 45', out)
        self.assertIn('nothing written', out)

    def test_over_budget_refuses(self):
        with tempfile.TemporaryDirectory() as d:
            code, _, err = self.run_cli('--locations', 'mumbai', '--max-total-calls', '10', '--out', str(Path(d) / 'b'))
            self.assertEqual(code, 2)
            self.assertIn('Over budget', err)
            self.assertFalse((Path(d) / 'b').exists())

    def test_written_batch_manifest_hashes_match_files(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / 'b'
            code, _, _ = self.run_cli('--entries', 'F08,F10', '--locations', 'mumbai,chennai', '--days', '2',
                                      '--start', '2026-11-02', '--out', str(out))
            self.assertEqual(code, 0)
            m = json.loads((out / 'BATCH_MANIFEST.json').read_text(encoding='utf-8'))
            self.assertEqual(len(m['plans']), 16)
            for row in m['plans']:
                self.assertEqual(hashlib.sha256((out / row['file']).read_bytes()).hexdigest(), row['sha256'])
            with self.assertRaises(FileExistsError):  # never overwrites an approved batch
                batch.write_batch({}, out)


if __name__ == '__main__':
    unittest.main()
