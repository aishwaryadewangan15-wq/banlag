"""Machine-local sealed capture store. Only banlag.collector writes records; everything else reads and verifies.

A record binds: the exact raw response bytes (SHA-256), the request (engine + params, never the key), the provider's
search_metadata (id, created_at, processed_at, status, json_endpoint), the local receipt time, the run/plan it belongs
to and any parent call (page_token follow-up). The record is sealed with HMAC-SHA256 under a key that exists only on
this machine, stored OUTSIDE the project and outside any cloud-synced folder (default %LOCALAPPDATA%\\BANLAG\\
capture_hmac.key on Windows, $XDG_DATA_HOME/banlag elsewhere; override with BANLAG_KEY_DIR). The store refuses to
create, read or trust a key inside the project folder (mirrored for review), a Dropbox root, a OneDrive root, or any
folder carrying a .dropbox marker: anyone who can read the key could forge seals.

What a valid seal proves: this machine's collector wrote this record and these bytes have not changed since.
What it does not prove: anything about Google's internal reasons, what any person saw, or that a cited page is true.
A copied record without the key verifies only as ARCHIVED_SERPAPI_CAPTURE (hashes consistent, origin unauthenticated).
"""
import hashlib
import hmac
import json
import os
import secrets
from pathlib import Path

from . import provenance as P

ROOT = Path(__file__).resolve().parent.parent
STORE = ROOT / 'captures' / 'store'
SCHEMA = 'banlag.capture.v1'


class UnsafeKeyLocation(RuntimeError):
    pass


def default_key_path():
    if os.environ.get('BANLAG_KEY_DIR'):
        base = Path(os.environ['BANLAG_KEY_DIR'])
    elif os.name == 'nt':
        base = Path(os.environ.get('LOCALAPPDATA') or (Path.home() / 'AppData' / 'Local')) / 'BANLAG'
    else:
        base = Path(os.environ.get('XDG_DATA_HOME') or (Path.home() / '.local' / 'share')) / 'banlag'
    return base / 'capture_hmac.key'


KEY_PATH = default_key_path()


def synced_roots():
    """Folders whose contents may leave this machine: the project (mirrored for review), Dropbox and OneDrive roots."""
    roots = {('project folder (mirrored for review)', ROOT.resolve())}
    for info in (Path(os.environ.get('LOCALAPPDATA', '')) / 'Dropbox' / 'info.json', Path(os.environ.get('APPDATA', '')) / 'Dropbox' / 'info.json'):
        try:
            for account in json.loads(info.read_text(encoding='utf-8')).values():
                if isinstance(account, dict) and account.get('path'):
                    roots.add(('Dropbox root', Path(account['path']).resolve()))
        except (OSError, ValueError):
            pass
    for name in ('Dropbox', 'OneDrive'):
        p = Path.home() / name
        if p.exists():
            roots.add((f'{name} root', p.resolve()))
    for var in ('OneDrive', 'OneDriveConsumer', 'OneDriveCommercial'):
        if os.environ.get(var):
            roots.add(('OneDrive root', Path(os.environ[var]).resolve()))
    return roots


def unsafe_key_reason(key_path):
    p = Path(key_path).resolve()
    for label, root in synced_roots():
        if p == root or root in p.parents:
            return f'inside {label}: {root}'
    for anc in p.parents:
        if (anc / '.dropbox').exists() or (anc / '.dropbox.cache').exists():
            return f'inside a folder with a Dropbox marker: {anc}'
        if anc.name.lower().startswith(('dropbox', 'onedrive')):
            return f'inside a folder named like a sync root: {anc}'
    return None


def canonical(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')


def load_key(key_path=KEY_PATH, create=False):
    key_path = Path(key_path)
    reason = unsafe_key_reason(key_path)
    if reason:
        raise UnsafeKeyLocation(f'refusing HMAC key at {key_path}: {reason}')
    if key_path.exists():
        return key_path.read_bytes()
    if not create:
        return None
    key_path.parent.mkdir(parents=True, exist_ok=True)
    key = secrets.token_bytes(32)
    fd = os.open(str(key_path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'wb') as f:
        f.write(key)
    return key


def seal(record, raw_bytes, store=STORE, key_path=KEY_PATH):
    """Write raw bytes + sealed record. Returns the record path. Collector-only."""
    store = Path(store)
    key = load_key(key_path, create=True)
    (store / 'raw').mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(raw_bytes).hexdigest()
    raw_path = store / 'raw' / f'{digest}.json'
    if not raw_path.exists():
        raw_path.write_bytes(raw_bytes)
    rec = dict(record, schema=SCHEMA, raw_sha256=digest, raw_file=f'raw/{digest}.json', raw_bytes=len(raw_bytes))
    mac = hmac.new(key, canonical(rec), hashlib.sha256).hexdigest()
    path = store / f"{rec['capture_id']}.json"
    if path.exists():
        raise FileExistsError(f'capture {rec["capture_id"]} already sealed; records are immutable')
    path.write_text(json.dumps({'record': rec, 'hmac_sha256': mac}, ensure_ascii=False, indent=1), encoding='utf-8')
    return path


def verify(path, key_path=KEY_PATH):
    """-> {'origin': TRUSTED | ARCHIVED_SERPAPI | 'INVALID', 'reasons': [...], 'record', 'response'}"""
    path = Path(path)
    reasons = []
    try:
        doc = json.loads(path.read_text(encoding='utf-8'))
        rec, mac = doc['record'], doc['hmac_sha256']
    except (OSError, ValueError, KeyError, TypeError):
        return {'origin': 'INVALID', 'reasons': ['unreadable record'], 'record': None, 'response': None}
    if rec.get('schema') != SCHEMA:
        reasons.append('unknown schema')
    raw_path = path.parent / str(rec.get('raw_file', ''))
    raw = raw_path.read_bytes() if raw_path.is_file() and raw_path.parent.name == 'raw' else None
    if raw is None:
        return {'origin': 'INVALID', 'reasons': ['raw response bytes missing'], 'record': rec, 'response': None}
    if hashlib.sha256(raw).hexdigest() != rec.get('raw_sha256'):
        return {'origin': 'INVALID', 'reasons': ['raw response bytes altered (SHA-256 mismatch)'], 'record': rec, 'response': None}
    response = None
    if rec.get('http_status') == 200:
        try:
            response = json.loads(raw.decode('utf-8'))
        except (UnicodeDecodeError, ValueError):
            return {'origin': 'INVALID', 'reasons': ['raw bytes are not JSON'], 'record': rec, 'response': None}
        md = response.get('search_metadata') or {}
        prov = rec.get('provider') or {}
        for k in ('id', 'created_at', 'processed_at', 'status', 'json_endpoint'):
            if md.get(k) != prov.get(k):
                reasons.append(f'provider {k} in record does not match raw response')
        params = (response.get('search_parameters') or {})
        if params.get('engine') != (rec.get('request') or {}).get('engine'):
            reasons.append('engine in raw response differs from recorded request')
    if reasons:
        return {'origin': 'INVALID', 'reasons': reasons, 'record': rec, 'response': response}
    try:
        key = load_key(key_path)
    except UnsafeKeyLocation as ex:
        return {'origin': P.ARCHIVED_SERPAPI, 'reasons': [str(ex) + ' (seal not trusted)'], 'record': rec, 'response': response}
    if key is None:
        return {'origin': P.ARCHIVED_SERPAPI, 'reasons': ['seal not verifiable on this machine (no local key)'], 'record': rec, 'response': response}
    good = hmac.compare_digest(hmac.new(key, canonical(rec), hashlib.sha256).hexdigest(), str(mac))
    if not good:
        return {'origin': 'INVALID', 'reasons': ['seal mismatch: record altered or sealed elsewhere'], 'record': rec, 'response': response}
    return {'origin': P.TRUSTED, 'reasons': [], 'record': rec, 'response': response}


PUBLISHED = ROOT / 'evidence' / 'serpapi'


def _rel(p):
    try:
        return Path(p).resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return Path(p).name


def export_run(run_id, store=STORE, dest_root=PUBLISHED, key_path=KEY_PATH):
    """Deliberately copy one sealed run (records + raw bytes, never the key) for publication. Elsewhere it verifies only
    as ARCHIVED_SERPAPI_CAPTURE (hashes consistent, seal not checkable). Refuses runs that do not verify here."""
    calls = list_runs(store, key_path).get(run_id)
    if not calls:
        raise KeyError(f'no sealed calls for run {run_id}')
    bad = [c for c in calls if c['origin'] != P.TRUSTED]
    if bad:
        raise ValueError('refusing to export a run whose seal does not verify on this machine: ' + '; '.join(r for c in bad for r in c['reasons']))
    dest = Path(dest_root) / run_id
    if dest.exists():
        raise FileExistsError(f'{dest} already exists; exports are immutable')
    (dest / 'raw').mkdir(parents=True)
    files = {}
    for c in calls:
        rec_path, raw_rel = c['path'], c['record']['raw_file']
        for src, rel in ((rec_path, rec_path.name), (Path(store) / raw_rel, raw_rel)):
            data = Path(src).read_bytes()
            (dest / rel).write_bytes(data)
            files[rel] = hashlib.sha256(data).hexdigest()
    manifest = {'schema': 'banlag.capture_export.v1', 'run_id': run_id, 'files_sha256': files,
                'verification': 'Seal (HMAC) needs the collector machine key, which is never exported; elsewhere these files verify as ARCHIVED_SERPAPI_CAPTURE.'}
    (dest / 'EXPORT_MANIFEST.json').write_text(json.dumps(manifest, indent=1), encoding='utf-8')
    return dest


def run_sources(key_path=KEY_PATH, store=STORE, published=PUBLISHED):
    """All runs with the directory they live in; the local store wins over an exported copy of the same run."""
    found = {}
    for d in [Path(store)] + sorted(p for p in Path(published).glob('*') if p.is_dir()):
        for run_id, calls in list_runs(d, key_path).items():
            if run_id != 'UNKNOWN' and run_id not in found:
                found[run_id] = (d, calls)
    return found


def list_runs(store=STORE, key_path=KEY_PATH):
    store = Path(store)
    runs = {}
    for p in sorted(store.glob('*.json')):
        v = verify(p, key_path)
        rec = v['record'] or {}
        runs.setdefault(rec.get('run_id', 'UNKNOWN'), []).append({'path': p, **v})
    return runs


def bundle_payload(run_id, store=STORE, key_path=KEY_PATH):
    """Assemble one run's verified calls into an engine payload + origin. Any invalid call downgrades the bundle."""
    calls = list_runs(store, key_path).get(run_id, [])
    if not calls:
        raise KeyError(f'no sealed calls for run {run_id}')
    origins = {c['origin'] for c in calls}
    origin = 'INVALID' if 'INVALID' in origins else (P.TRUSTED if origins == {P.TRUSTED} else P.ARCHIVED_SERPAPI)
    by_call = {c['record']['call_id']: c for c in calls}
    plan = calls[0]['record'].get('plan') or {}
    payload = {'source_kind': 'SERPAPI_LIVE_CAPTURE', 'ingredients': plan.get('ingredients'), 'query': None,
               'captured_at': None, 'capture_complete': True}
    linkage = []
    for c in sorted(calls, key=lambda c: c['record']['call_index']):
        rec, resp = c['record'], c['response']
        role = rec.get('role')
        if resp is None:
            linkage.append({'call_id': rec['call_id'], 'role': role, 'http_status': rec.get('http_status'), 'note': 'no JSON response'})
            continue
        if role == 'uses_search':
            payload['google'] = resp
            payload['query'] = rec['request']['params'].get('q')
            payload['captured_at'] = rec['received_at']
        elif role == 'uses_ai_overview':
            parent = by_call.get(rec.get('parent_call_id'))
            ok = bool(parent and parent['response'] and ((parent['response'].get('ai_overview') or {}).get('page_token') == rec['request']['params'].get('page_token')))
            payload['ai_overview'] = resp
            linkage.append({'call_id': rec['call_id'], 'parent': rec.get('parent_call_id'), 'page_token_link': 'VERIFIED' if ok else 'BROKEN'})
        elif role == 'uses_ai_mode':
            payload['ai_mode'] = resp
        elif role == 'status_search':
            payload['status_capture'] = resp
    skews = []
    for c in calls:
        rec = c['record']
        created = P.parse_serpapi_time((rec.get('provider') or {}).get('created_at'))
        received = P.parse_iso(rec.get('received_at'))
        if created and received:
            skews.append({'call_id': rec['call_id'], 'received_minus_provider_created_s': round((received - created).total_seconds(), 1)})
    behind = [s for s in skews if s['received_minus_provider_created_s'] < -5]
    clock = {'status': 'LOCAL_CLOCK_BEHIND_PROVIDER' if behind else ('CONSISTENT' if skews else 'UNKNOWN'), 'calls': skews,
             'note': ('A local receipt time earlier than the provider\'s creation time means this machine\'s clock is behind; '
                      'provider timestamps (which match the IDs\' embedded time) are used for chronology.') if behind else ''}
    prov = {'origin': origin, 'declared_source_kind': 'SERPAPI_LIVE_CAPTURE', 'live_verified': origin == P.TRUSTED, 'clock_check': clock,
            'store': _rel(store),
            'metadata_consistency': 'SEALED' if origin == P.TRUSTED else 'UNVERIFIED', 'checks': [],
            'statement': P.ORIGIN_STATEMENT.get(origin, 'Invalid capture: ' + '; '.join(r for c in calls for r in c['reasons'])),
            'run_id': run_id, 'calls': [{'call_id': c['record']['call_id'], 'role': c['record'].get('role'), 'origin': c['origin'],
                                        'search_id': (c['record'].get('provider') or {}).get('id'), 'received_at': c['record'].get('received_at'),
                                        'raw_sha256': c['record'].get('raw_sha256'), 'reasons': c['reasons']} for c in calls],
            'linkage': linkage}
    return payload, prov


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description='Sealed capture store: list runs, or deliberately export one for publication (never the key).')
    sub = ap.add_subparsers(dest='cmd', required=True)
    sub.add_parser('list')
    ex = sub.add_parser('export')
    ex.add_argument('run_id')
    a = ap.parse_args(argv)
    if a.cmd == 'list':
        for run_id, (d, calls) in run_sources().items():
            print(run_id, _rel(d), ', '.join(f"{c['record']['call_id']}={c['origin']}" for c in calls if c['record']))
        return 0
    print('exported to', _rel(export_run(a.run_id)))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
