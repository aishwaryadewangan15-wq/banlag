"""Capture README screenshots and the hero GIF from the static demo.

    python scripts/build_static_demo.py --out _site
    pip install playwright && python -m playwright install --with-deps chromium
    python scripts/capture_demo.py --site _site --out docs/assets

Writes case.png, citations.png, verify.png, live.png and demo.gif (needs ffmpeg on PATH for the GIF).
Used by .github/workflows/demo-assets.yml. It is not a test and makes no request outside the loopback server.
"""
import argparse
import functools
import shutil
import subprocess
import tempfile
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import sync_playwright

W, H = 1440, 900


def serve(site):
    handler = functools.partial(SimpleHTTPRequestHandler, directory=str(site))
    handler.log_message = lambda *a, **k: None
    srv = ThreadingHTTPServer(('127.0.0.1', 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f'http://127.0.0.1:{srv.server_address[1]}/'


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--site', default='_site')
    ap.add_argument('--out', default='docs/assets')
    a = ap.parse_args(argv)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    srv, url = serve(Path(a.site).resolve())
    frames = Path(tempfile.mkdtemp())
    n = 0

    def frame(page, repeat=1):
        nonlocal n
        shot = page.screenshot()
        for _ in range(repeat):
            (frames / f'f{n:03d}.png').write_bytes(shot)
            n += 1

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={'width': W, 'height': H}, device_scale_factor=1)
            page.goto(url)
            page.wait_for_function("document.getElementById('caseTitle').textContent.trim() !== '—'")
            page.wait_for_timeout(800)
            page.screenshot(path=str(out / 'case.png'))
            frame(page, 3)
            # the archived SerpApi capture: the prohibition statement's citations name a different notified set
            page.add_style_tag(content='.topbar{position:static!important}')
            finding = page.locator('#caseLive .finding.amber').first
            finding.wait_for()
            page.evaluate("document.querySelector('#caseLive .finding.amber').scrollIntoView({block: 'start'}); window.scrollBy(0, -40)")
            page.wait_for_timeout(500)
            frame(page, 6)
            box = page.evaluate("""() => {
                const f = document.querySelector('#caseLive .finding.amber');
                const tables = f.parentElement.querySelectorAll('.tablewrap');
                const t = tables[tables.length - 1];
                const a = f.getBoundingClientRect(), b = t.getBoundingClientRect();
                return {x: a.left - 12, y: a.top + window.scrollY - 12, width: a.width + 24, height: b.bottom - a.top + 24};
            }""")
            page.screenshot(path=str(out / 'citations.png'), full_page=True, clip=box)
            page.evaluate('window.scrollTo(0, 0)')
            # integrity view
            page.click('button[data-view="integrity"]')
            page.wait_for_timeout(500)
            frame(page, 2)
            # verify: hostile sample stays USER_SUPPLIED_UNVERIFIED
            page.click('button[data-view="verify"]')
            page.locator('#sampleButtons button.hostile').first.click()
            page.wait_for_timeout(700)
            page.screenshot(path=str(out / 'verify.png'))
            frame(page, 3)
            page.click('button[data-view="live"]')
            page.wait_for_timeout(900)
            page.screenshot(path=str(out / 'live.png'))
            frame(page, 3)
            browser.close()
    finally:
        srv.shutdown()

    ffmpeg = shutil.which('ffmpeg')
    if ffmpeg:
        vf = 'fps=1,scale=1100:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=128[p];[b][p]paletteuse=dither=bayer:bayer_scale=4'
        subprocess.run([ffmpeg, '-y', '-loglevel', 'error', '-framerate', '1', '-i', str(frames / 'f%03d.png'), '-vf', vf, '-loop', '0',
                        str(out / 'demo.gif')], check=True)
    print('wrote', ', '.join(sorted(x.name for x in out.iterdir())))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
