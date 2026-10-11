"""Cited-page snapshots (banlag.citefetch): URL safety, text checks, the published report and T3 wiring. No network."""
import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from banlag import citefetch as cf
from banlag.legal import entry_by_id

RUN = 'run-20261010T024515Z-9415e2'
F08_BAN = (b'<html><head><title>Notice</title><script>var x = "banned";</script></head><body><p>Pursuant to S.O. 3078(E), the Central '
           b'Government has prohibited the manufacture, sale and distribution of the fixed dose combination of Dicyclomine + '
           b'Paracetamol + Clidinium Bromide for human use.</p></body></html>')
F09_BAN = (b'<html><body><p>The fixed dose combination of Dicyclomine + Paracetamol + Clidinium Bromide + Chlordiazepoxide is '
           b'prohibited in India under S.O. 3071(E).</p></body></html>')
SHOP = b'<html><body><p>Dicyclomine + Paracetamol + Clidinium Bromide tablets are used for abdominal pain.</p></body></html>'


class UrlSafety(unittest.TestCase):
    def test_refuses_non_http_credentials_and_private_hosts(self):
        for url in ('file:///etc/passwd', 'ftp://example.com/x', 'https://user:pw@example.com/', 'http://127.0.0.1/', 'http://localhost:8765/',
                    'http://10.0.0.5/', 'http://169.254.169.254/latest/meta-data', 'http://[::1]/'):
            with self.subTest(url=url), self.assertRaises(cf.Refused):
                cf.check_url(url)

    def test_redirect_to_a_private_host_is_refused(self):
        h = cf._SafeRedirect()
        with self.assertRaises(cf.Refused):
            h.redirect_request(None, None, 302, 'Found', {}, 'http://127.0.0.1/admin')


class TextChecks(unittest.TestCase):
    def test_html_text_drops_scripts_and_reads_the_title(self):
        title, text = cf.html_text(F08_BAN, 'text/html; charset=utf-8')
        self.assertEqual(title, 'Notice')
        self.assertNotIn('var x', text)
        self.assertIn('Clidinium Bromide for human use', text)

    def test_exact_restriction_is_attributed_to_the_right_notice(self):
        f08 = entry_by_id('F08')
        c = cf.page_checks(cf.html_text(F08_BAN)[1], f08)
        self.assertEqual(sorted(c['exact_restriction_statements']), ['F08'])
        self.assertTrue(c['states_target_restriction'])
        c9 = cf.page_checks(cf.html_text(F09_BAN)[1], f08)
        self.assertEqual(sorted(c9['exact_restriction_statements']), ['F09'])  # the +chlordiazepoxide notice, not the target
        self.assertFalse(c9['states_target_restriction'])
        self.assertEqual(c9['notice_numbers_present'], ['S.O. 3071(E)'])
        shop = cf.page_checks(cf.html_text(SHOP)[1], f08)
        self.assertEqual(shop['exact_restriction_statements'], {})


class FetchRun(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def fake_get(self, url):
        if 'teamlease' in url:
            return 200, url, 'text/html', F09_BAN
        if 'complinity' in url:
            return 200, url, 'text/html', F08_BAN
        if 'goodrx' in url:
            return 403, url, 'text/html', b'denied'
        if 'wikipedia' in url:
            raise cf.Refused('host resolves to a non-public address')
        return 200, url, 'text/html', SHOP

    def run_fetch(self):
        return cf.fetch_run(RUN, get=self.fake_get, published=self.tmp / 'pub', local=self.tmp / 'local')

    def test_report_records_hashes_lag_and_outcomes(self):
        r = self.run_fetch()
        self.assertEqual(r['target'], {'id': 'F08', 'notice': 'S.O. 3078(E)'})
        self.assertEqual(len(r['pages']), 8)
        by = {p['url'].split('/')[2]: p for p in r['pages']}
        self.assertEqual(by['www.goodrx.com']['outcome'], 'HTTP_ERROR')
        self.assertEqual(by['en.wikipedia.org']['outcome'], 'REFUSED')
        tl = by['teamleaseregtech.com']
        self.assertEqual(tl['sha256'], hashlib.sha256(F09_BAN).hexdigest())
        self.assertEqual(sorted(tl['text']['exact_restriction_statements']), ['F09'])
        self.assertIsNotNone(tl['lag_after_capture_hours'])
        self.assertTrue(all(p['cited_by'] for p in r['pages']))
        published = json.loads((self.tmp / 'pub' / RUN / 'CITED_PAGES.json').read_text(encoding='utf-8'))
        self.assertEqual(published['pages'][1]['sha256'], tl['sha256'])
        self.assertNotIn('Clidinium Bromide + Chlordiazepoxide is prohibited in India under', json.dumps({k: v for k, v in tl.items() if k != 'text'}))

    def test_snapshots_only_from_bytes_that_still_hash(self):
        r = self.run_fetch()
        snaps = cf.snapshots(r, local=self.tmp / 'local')
        self.assertEqual(len(snaps), 6)  # 8 cited pages, minus the 403 and the refused URL
        (self.tmp / 'local' / RUN / f'{hashlib.sha256(F09_BAN).hexdigest()}.bin').write_bytes(b'changed')
        self.assertEqual(len(cf.snapshots(r, local=self.tmp / 'local')), 5)

    def test_web_server_never_reaches_this_module(self):
        import ast
        src = (Path(cf.__file__).parent / 'server.py').read_text(encoding='utf-8')
        mods = {n.module for n in ast.walk(ast.parse(src)) if isinstance(n, ast.ImportFrom)}
        self.assertNotIn('citefetch', mods)

    def test_a_run_that_fails_verification_is_refused(self):
        with mock.patch.object(cf.capture_store, 'bundle_payload', return_value=({}, {'origin': 'INVALID'})), \
                self.assertRaisesRegex(ValueError, 'fails verification'):
            self.run_fetch()


if __name__ == '__main__':
    unittest.main()
