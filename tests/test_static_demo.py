"""The static GitHub Pages replay is built from the same server responses and keeps the local UI unchanged."""
import importlib.util
import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_builder():
    spec = importlib.util.spec_from_file_location('build_static_demo', ROOT / 'scripts' / 'build_static_demo.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class StaticDemo(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'node not installed')
    def test_build_replays_every_ui_route(self):
        with tempfile.TemporaryDirectory() as d:
            out, n = _load_builder().build(Path(d) / 'site')
            api = out / 'api'
            overview = json.loads((api / 'overview.json').read_text(encoding='utf-8'))
            for c in overview['cases']:
                self.assertTrue((api / f"case_{c['id']}.json").is_file(), c['id'])
            for f in ('registry.json', 'status.json', 'live.json', '_post_index.json'):
                self.assertTrue((api / f).is_file(), f)
            index = json.loads((api / '_post_index.json').read_text(encoding='utf-8'))
            self.assertTrue(any(k.startswith('evaluate:') for k in index))
            self.assertIn('match:clidinium bromide|dicyclomine|paracetamol', index)
            f08 = json.loads((api / index['match:clidinium bromide|dicyclomine|paracetamol']).read_text(encoding='utf-8'))
            self.assertEqual(f08['status'], 'EXACT_NOTIFICATION_MATCH')
            self.assertEqual(f08['entry']['id'], 'F08')
            html = (out / 'index.html').read_text(encoding='utf-8')
            self.assertIn('<script src="static-config.js"></script>', html)
            self.assertNotRegex(html, r'(src|href)="/(app|samples)\.js|href="/style\.css"')
            self.assertGreater(n, 10)

    def test_local_ui_is_not_in_static_mode(self):
        html = (ROOT / 'web' / 'index.html').read_text(encoding='utf-8')
        self.assertNotIn('static-config.js', html)
        js = (ROOT / 'web' / 'app.js').read_text(encoding='utf-8')
        self.assertIn('const STATIC = window.BANLAG_STATIC === true;', js)
        self.assertIsNotNone(re.search(r"async function post\(path, body\) \{\n  if \(STATIC\) return staticPost\(path, body\);", js))


if __name__ == '__main__':
    unittest.main()
