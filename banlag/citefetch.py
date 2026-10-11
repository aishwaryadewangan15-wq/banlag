"""Fetch and hash the pages an archived or sealed SerpApi run cites. CLI only; the web server never imports this module.

    python -m banlag.citefetch run-20261010T024515Z-9415e2                 # fetch, hash, check; writes evidence/cited_pages/<run>/
    python -m banlag.citefetch run-20261010T024515Z-9415e2 --evaluate      # re-evaluate the run with these local snapshots

What is published (evidence/cited_pages/<run>/CITED_PAGES.json): each cited URL, the final URL after redirects, HTTP status,
content type, byte length, SHA-256 of the exact bytes, fetch time, and what the page text says about the registry, with
matched sentences quoted at most 300 characters. The page bytes and extracted text stay local (captures/cited_pages/<run>/,
git-ignored): they are third-party content.

A fetch is a separate observation made AFTER the capture. Each record states the lag; a page can change between the time
Google cited it and the time it was fetched, so a snapshot says what the page said then, not what Google saw.
"""
import argparse
import datetime as dt
import hashlib
import html.parser
import ipaddress
import json
import re
import socket
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

from . import capture_store
from . import provenance as P
from .claims import restriction_statements, split_sentences
from .engine import _surface
from .legal import find_mentions, notice_numbers, registry

ROOT = Path(__file__).resolve().parent.parent
PUBLISHED = ROOT / 'evidence' / 'cited_pages'
LOCAL = ROOT / 'captures' / 'cited_pages'
MAX_BYTES = 5 * 1024 * 1024
MAX_PAGES = 40
TIMEOUT = 30
QUOTE = 300
UA = 'BANLAG-citefetch/0.1 (+https://github.com/aishwaryadewangan15-wq/banlag; research snapshot of a cited page)'


class Refused(ValueError):
    pass


def check_url(url):
    """Only public http(s) hosts. Refuses credentials in URLs, non-default schemes and private, loopback or reserved addresses."""
    parts = urlsplit(url or '')
    if parts.scheme not in ('http', 'https') or not parts.hostname:
        raise Refused('not an http(s) URL')
    if parts.username or parts.password:
        raise Refused('credentials in URL')
    try:
        infos = socket.getaddrinfo(parts.hostname, parts.port or (443 if parts.scheme == 'https' else 80), proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        raise Refused('host does not resolve') from None
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global:
            raise Refused('host resolves to a non-public address')
    return url


class _SafeRedirect(urllib.request.HTTPRedirectHandler):
    max_redirections = 5

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        check_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _default_get(url):
    """(status, final_url, content_type, bytes). Raises Refused before any request to an unsafe host."""
    check_url(url)
    opener = urllib.request.build_opener(_SafeRedirect)
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': 'text/html,application/xhtml+xml,application/pdf;q=0.9,*/*;q=0.5'})
    try:
        with opener.open(req, timeout=TIMEOUT) as r:
            return r.status, r.geturl(), r.headers.get('Content-Type', ''), r.read(MAX_BYTES + 1)
    except urllib.error.HTTPError as e:
        return e.code, e.geturl() or url, e.headers.get('Content-Type', '') if e.headers else '', e.read(MAX_BYTES + 1)


class _Text(html.parser.HTMLParser):
    SKIP = {'script', 'style', 'noscript', 'svg', 'template', 'head'}
    BLOCK = {'p', 'div', 'li', 'br', 'tr', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'section', 'article', 'td', 'th', 'title'}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.skip, self.title, self._in_title = [], 0, '', False

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip += 1
        if tag == 'title':
            self._in_title = True
        if tag in self.BLOCK:
            self.out.append('\n')

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.skip:
            self.skip -= 1
        if tag == 'title':
            self._in_title = False
        if tag in self.BLOCK:
            self.out.append('\n')

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        if not self.skip:
            self.out.append(data)


def html_text(raw, content_type=''):
    m = re.search(r'charset=([\w-]+)', content_type or '', re.I) or re.search(rb'<meta[^>]+charset=["\']?([\w-]+)', raw[:4096], re.I)
    enc = (m.group(1).decode() if isinstance(m.group(1), bytes) else m.group(1)) if m else 'utf-8'
    try:
        doc = raw.decode(enc, errors='replace')
    except LookupError:
        doc = raw.decode('utf-8', errors='replace')
    p = _Text()
    p.feed(doc)
    lines = [re.sub(r'[ \t\u00a0]+', ' ', x).strip() for x in ''.join(p.out).split('\n')]
    return re.sub(r'\s+', ' ', p.title).strip(), '\n'.join(x for x in lines if x)


def page_checks(text, target_entry=None):
    """What the page text says about the registry. Observations only: string matches and sentence-level restriction reads."""
    db = registry()
    names = sorted({m['canonical'] for m in find_mentions(text) if m['class'] in ('LITERAL', 'SPELLING_VARIANT')})
    sentences = [s for s in split_sentences(text.replace('\n', '. ')) if len(s) < 2000]
    hits = {}
    for e in db['entries']:
        if e.get('underspecified_terms') or not set(e['ingredients']) <= set(names):
            continue  # a page can only state an exact restriction on a set whose every member it names
        quotes = []
        for s in sentences:
            if restriction_statements(s, e) and s[:QUOTE] not in quotes:
                quotes.append(s[:QUOTE])
            if len(quotes) >= 3:
                break
        if quotes:
            hits[e['id']] = {'notice': e['notice'], 'sentences': quotes}
    return {'registry_names_present': names, 'notice_numbers_present': sorted(set(notice_numbers(text))),
            'exact_restriction_statements': hits,
            'states_target_restriction': bool(target_entry and target_entry['id'] in hits)}


def cited_urls(payload):
    """Every reference URL on every AI surface in a run, in surface order, de-duplicated."""
    surfaces = [('AI Overview', _surface(payload.get('google') if not payload.get('ai_overview') else payload.get('ai_overview'), 'AI_OVERVIEW')),
                ('AI Mode', _surface(payload.get('ai_mode'), 'AI_MODE')),
                ('Status AI Overview', _surface(payload.get('status_capture'), 'AI_OVERVIEW'))]
    seen, out = {}, []
    for name, s in surfaces:
        for r in s['references']:
            link = r.get('link')
            if not isinstance(link, str) or not link:
                continue
            if link not in seen:
                seen[link] = {'url': link, 'cited_by': [], 'titles': []}
                out.append(seen[link])
            seen[link]['cited_by'].append(f"{name} [{r.get('index')}]")
            if r.get('title') and r['title'] not in seen[link]['titles']:
                seen[link]['titles'].append(r['title'])
    return out


def fetch_run(run_id, get=None, now=None, published=PUBLISHED, local=LOCAL, sources=None):
    get = get or _default_get
    now = now or (lambda: dt.datetime.now(dt.timezone.utc))
    found = (sources or capture_store.run_sources()).get(run_id)
    if not found:
        raise KeyError(f'no sealed or exported run {run_id}')
    store_dir, calls = found
    payload, prov = capture_store.bundle_payload(run_id, store_dir)
    if prov['origin'] == 'INVALID':
        raise ValueError('refusing to fetch pages for a run that fails verification')
    entry = next((e for e in registry()['entries'] if set(e['ingredients']) == set(payload.get('ingredients') or [])), None)
    captured = P.parse_iso(payload.get('captured_at')) if payload.get('captured_at') else None
    urls = cited_urls(payload)[:MAX_PAGES]
    out_local = Path(local) / run_id
    out_local.mkdir(parents=True, exist_ok=True)
    pages = []
    for u in urls:
        t = now()
        rec = {**u, 'fetched_at': t.isoformat(timespec='seconds'),
               'lag_after_capture_hours': round((t - captured).total_seconds() / 3600, 1) if captured else None}
        try:
            status, final, ctype, raw = get(u['url'])
        except Refused as ex:
            pages.append({**rec, 'outcome': 'REFUSED', 'reason': str(ex)})
            continue
        except (urllib.error.URLError, OSError, ValueError) as ex:
            pages.append({**rec, 'outcome': 'FETCH_FAILED', 'reason': type(ex).__name__ + ': ' + str(getattr(ex, 'reason', ex))[:160]})
            continue
        truncated = len(raw) > MAX_BYTES
        raw = raw[:MAX_BYTES]
        sha = hashlib.sha256(raw).hexdigest()
        (out_local / f'{sha}.bin').write_bytes(raw)
        rec.update(outcome='FETCHED' if status == 200 and not truncated else ('TRUNCATED' if truncated else 'HTTP_ERROR'),
                   http_status=status, final_url=final, content_type=ctype.split(';')[0].strip(), bytes=len(raw), sha256=sha)
        if 'pdf' in ctype.lower() or raw[:5] == b'%PDF-':
            rec['text'] = {'status': 'NOT_EXTRACTED_PDF'}
        elif status == 200:
            title, text = html_text(raw, ctype)
            (out_local / f'{sha}.txt').write_text(text, encoding='utf-8')
            rec['page_title'] = title[:300]
            rec['text'] = {'status': 'EXTRACTED', 'chars': len(text), 'sha256': hashlib.sha256(text.encode('utf-8')).hexdigest(),
                           **page_checks(text, entry)}
        pages.append(rec)
    report = {'schema': 'banlag.cited_pages.v1', 'run_id': run_id, 'run_origin': prov['origin'],
              'target': {'id': entry['id'], 'notice': entry['notice']} if entry else None,
              'captured_at': payload.get('captured_at'), 'fetcher': UA,
              'statement': ('Pages were fetched after the capture. Each record is what that URL returned at fetched_at, not what '
                            'Google saw when it cited it. Text checks are string matches and sentence-level reads, not a legal finding.'),
              'pages': pages}
    pub = Path(published) / run_id
    pub.mkdir(parents=True, exist_ok=True)
    (pub / 'CITED_PAGES.json').write_text(json.dumps(report, indent=1, ensure_ascii=False) + '\n', encoding='utf-8')
    return report


def snapshots(report, local=LOCAL):
    """Local snapshots whose bytes still hash to the published record, in the form engine.evaluate() accepts."""
    out = []
    for p in report['pages']:
        if p.get('outcome') != 'FETCHED' or (p.get('text') or {}).get('status') != 'EXTRACTED':
            continue
        raw = Path(local) / report['run_id'] / f"{p['sha256']}.bin"
        if not raw.is_file() or hashlib.sha256(raw.read_bytes()).hexdigest() != p['sha256']:
            continue
        _, text = html_text(raw.read_bytes(), p.get('content_type', ''))
        out.append({'url': p['url'], 'text': text, 'sha256': p['sha256'], 'fetched_at': p['fetched_at']})
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description='Fetch, hash and check the pages a SerpApi run cites (no SerpApi calls).')
    ap.add_argument('run_id')
    ap.add_argument('--evaluate', action='store_true', help='after fetching, re-evaluate the run with the local snapshots')
    a = ap.parse_args(argv)
    try:
        report = fetch_run(a.run_id)
    except (KeyError, ValueError) as ex:
        print(str(ex), file=sys.stderr)
        return 2
    for p in report['pages']:
        t = p.get('text') or {}
        print(f"{p['outcome']:<12} {p.get('http_status', '-')!s:<4} {p['url'][:90]}  states-target={t.get('states_target_restriction')}"
              f"  restrictions={sorted(t.get('exact_restriction_statements', {}))}")
    if a.evaluate:
        from .engine import evaluate_run
        store_dir, _ = capture_store.run_sources()[a.run_id]
        r = evaluate_run(a.run_id, store=store_dir, verified_snapshots=snapshots(report))
        print(f"evidence tier with snapshots: T{r['evidence_tier']} ({r.get('tier_status')})")
        for b in r.get('tier_basis', []) or []:
            print('  ' + b)
    return 0


if __name__ == '__main__':
    sys.exit(main())
