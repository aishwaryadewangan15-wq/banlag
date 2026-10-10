import http.client
import json
import threading
import unittest
from http.server import ThreadingHTTPServer

from banlag.server import Handler
from banlag.public import legacy_view


class HardenedHTTP(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        cls.t = threading.Thread(target=cls.s.serve_forever, daemon=True)
        cls.t.start()
        cls.port = cls.s.server_port

    @classmethod
    def tearDownClass(cls):
        cls.s.shutdown()
        cls.s.server_close()
        cls.t.join(timeout=3)

    def req(self, method, path, body=None, headers=None, raw=None):
        c = http.client.HTTPConnection('127.0.0.1', self.port, timeout=10)
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        h = {'Content-Type': 'application/json'} if data is not None else {}
        h.update(headers or {})
        c.request(method, path, body=data, headers=h)
        r = c.getresponse()
        out = (r.status, r.getheader('Content-Security-Policy'), r.read())
        c.close()
        return out

    def test_dns_rebinding_host_refused(self):
        self.assertEqual(self.req('GET', '/api/registry', headers={'Host': 'evil.example:80'})[0], 421)
        self.assertEqual(self.req('POST', '/api/match', {'ingredients': ['cefuroxime']}, headers={'Host': 'attacker.test'})[0], 421)

    def test_cross_site_post_refused(self):
        self.assertEqual(self.req('POST', '/api/evaluate', {'source_kind': 'SYNTHETIC_TEST'}, headers={'Origin': 'https://evil.example'})[0], 403)
        self.assertEqual(self.req('POST', '/api/evaluate', {'source_kind': 'SYNTHETIC_TEST'}, headers={'Sec-Fetch-Site': 'cross-site'})[0], 403)
        ok = self.req('POST', '/api/match', {'ingredients': ['cefuroxime']}, headers={'Origin': f'http://127.0.0.1:{self.port}'})
        self.assertEqual(ok[0], 200)

    def test_body_limits(self):
        self.assertEqual(self.req('POST', '/api/match', raw=b'x' * (2 * 1024 * 1024 + 1))[0], 413)
        self.assertEqual(self.req('POST', '/api/match', raw=b'{"a":1}', headers={'Content-Type': 'text/plain'})[0], 415)
        deep = '{"source_kind":"SYNTHETIC_TEST","x":' + '[' * 200 + ']' * 200 + '}'
        self.assertEqual(self.req('POST', '/api/evaluate', raw=deep.encode())[0], 400)
        self.assertEqual(self.req('POST', '/api/evaluate', raw=b'[1,2]')[0], 400)
        self.assertEqual(self.req('POST', '/api/evaluate', raw=b'{not json')[0], 400)

    def test_screenshot_allowlist(self):
        status, _, body = self.req('GET', '/evidence/screenshots/PassA_Q02_expanded.jpg')
        self.assertEqual(status, 200)
        self.assertTrue(body.startswith(b'\xff\xd8'))
        for bad in ('/evidence/screenshots/..%2Fg1_corpus.json', '/evidence/screenshots/notlisted.jpg', '/evidence/g1_corpus.json'):
            self.assertEqual(self.req('GET', bad)[0], 404, bad)

    def test_methods_and_csp(self):
        self.assertEqual(self.req('DELETE', '/api/registry')[0], 405)
        status, csp, _ = self.req('GET', '/')
        self.assertEqual(status, 200)
        self.assertIn("script-src 'self'", csp)
        self.assertIn("frame-ancestors 'none'", csp)

    def test_overview_and_case_endpoints(self):
        status, _, body = self.req('GET', '/api/overview')
        o = json.loads(body)
        self.assertEqual((status, o['g1']['locked']['verdict'], o['live']['sealed_runs'] >= 0), (200, 'G1_PASS', True))
        status, _, body = self.req('GET', '/api/case/F08')
        self.assertEqual(json.loads(body)['entry']['notice'], 'S.O. 3078(E)')
        self.assertEqual(self.req('GET', '/api/case/F99')[0], 404)

    def test_import_is_never_trusted_over_http(self):
        status, _, body = self.req('POST', '/api/evaluate', {'source_kind': 'SERPAPI_LIVE_CAPTURE', 'captured_at': 'tomorrow',
                                                             'ingredients': ['amoxicillin', 'serratiopeptidase'],
                                                             'ai_overview': {'text_blocks': [{'snippet': 'Amoxicillin + serratiopeptidase is commonly prescribed.'}]}})
        r = legacy_view(json.loads(body))  # public contract: legacy fields are served under "experimental"; legacy_view restores them (values unchanged)
        self.assertEqual((status, r['origin'], r['verified_evidence_tier']), (200, 'USER_SUPPLIED_UNVERIFIED', 0))


if __name__ == '__main__':
    unittest.main()
