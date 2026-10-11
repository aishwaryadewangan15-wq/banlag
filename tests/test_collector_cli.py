"""Collector plan validation, the HTTPS fetcher's failure handling and the CLI's no-network modes (no real network)."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from urllib.error import HTTPError, URLError

from banlag import collector
from tests.test_capture_store import KEY, PLAN, Base, FakeFetch, fake_responses


def write_plan(d, **over):
    plan = {'schema': 'banlag.plan.v1', 'max_calls': 1, 'calls': [{'call_id': 'C1', 'engine': 'google', 'params': {'q': 'x', 'gl': 'in'}}]}
    plan.update(over)
    p = Path(d) / 'plan.json'
    p.write_text(json.dumps(plan), encoding='utf-8')
    return p


class PlanValidation(unittest.TestCase):
    def assert_refused(self, msg, **over):
        with tempfile.TemporaryDirectory() as d, self.assertRaisesRegex(collector.Stop, msg):
            collector.load_plan(write_plan(d, **over))

    def test_unknown_schema(self):
        self.assert_refused('unknown plan schema', schema='banlag.plan.v0')

    def test_call_count_bounds(self):
        self.assert_refused('1..3 calls', max_calls=0)
        self.assert_refused('1..3 calls', max_calls=4)
        self.assert_refused('no more than max_calls', max_calls=1, calls=[{'engine': 'google'}, {'engine': 'google'}])

    def test_engine_allowlist(self):
        self.assert_refused("engine 'bing' not allowed", calls=[{'engine': 'bing', 'params': {}}])

    def test_forbidden_params(self):
        self.assert_refused('may not set api_key, async', calls=[{'engine': 'google', 'params': {'api_key': 'k', 'async': True}}])

    def test_valid_plan_returns_its_sha256(self):
        plan, sha = collector.load_plan(PLAN)
        self.assertEqual(plan['schema'], 'banlag.plan.v1')
        self.assertRegex(sha, r'^[0-9a-f]{64}$')


class DefaultFetch(unittest.TestCase):
    def test_http_error_returns_status_and_body(self):
        err = HTTPError(collector.ENDPOINT, 401, 'Unauthorized', {}, io.BytesIO(b'{"error": "Invalid API key."}'))
        with mock.patch.object(collector, 'urlopen', side_effect=err):
            self.assertEqual(collector._default_fetch({'q': 'x'}, KEY), (401, b'{"error": "Invalid API key."}'))

    def test_network_failure_never_leaks_the_url_or_key(self):
        with mock.patch.object(collector, 'urlopen', side_effect=URLError('https://serpapi.com/search?api_key=' + KEY)):
            with self.assertRaises(collector.Stop) as cm:
                collector._default_fetch({'q': 'x'}, KEY)
        self.assertEqual(str(cm.exception), 'network failure: URLError')
        self.assertIsNone(cm.exception.__cause__)

    def test_success_reads_at_most_the_byte_cap_plus_one(self):
        resp = mock.MagicMock(status=200)
        resp.read.return_value = b'{}'
        resp.__enter__.return_value = resp
        with mock.patch.object(collector, 'urlopen', return_value=resp) as u:
            self.assertEqual(collector._default_fetch({'q': 'x'}, KEY), (200, b'{}'))
        resp.read.assert_called_once_with(collector.MAX_BYTES + 1)
        self.assertIn('api_key=', u.call_args[0][0].full_url)  # the key travels only in the request itself


class Cli(unittest.TestCase):
    def run_cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), \
                mock.patch.object(collector, '_default_fetch', side_effect=AssertionError('network used')):
            code = collector.main(list(args))
        return code, out.getvalue(), err.getvalue()

    def test_show_and_no_approval_send_nothing(self):
        for args in ([str(PLAN), '--show'], [str(PLAN)]):
            code, out, _ = self.run_cli(*args)
            self.assertEqual(code, 0)
            self.assertIn('PLAN SHA-256:', out)
            self.assertIn('nothing was sent', out)

    def test_dry_run_prints_each_request_without_a_key(self):
        code, out, _ = self.run_cli(str(PLAN), '--dry-run')
        self.assertEqual(code, 0)
        self.assertGreaterEqual(out.count('WOULD CALL'), 1)
        self.assertNotIn('api_key', out)

    def test_wrong_approval_hash_exits_2_before_any_call(self):
        with mock.patch.dict('os.environ', {'SERPAPI_API_KEY': KEY, 'BANLAG_SERPAPI_APPROVAL': '0' * 64}):
            code, _, err = self.run_cli(str(PLAN), '--approve', '0' * 64)
        self.assertEqual(code, 2)
        self.assertIn('has not been approved', err)


class FailureStops(Base):
    def test_http_500_is_sealed_and_stops_the_run(self):
        f = FakeFetch(fake_responses(), status=500)
        _, n = self.run_plan(f)
        self.assertEqual(n, 1)
        self.assertEqual(len(f.calls), 1)

    def test_oversized_response_is_marked_truncated_and_stops(self):
        big = lambda params, key: (200, b'{' + b' ' * (collector.MAX_BYTES + 10) + b'}')  # noqa: E731
        _, n = self.run_plan(big)
        self.assertEqual(n, 1)
        recs = [json.loads(p.read_text(encoding='utf-8'))['record'] for p in self.store.glob('*.json')]
        self.assertEqual([r['truncated'] for r in recs], [True])


if __name__ == '__main__':
    unittest.main()
