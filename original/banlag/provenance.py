"""Provenance model. Declared origin is never trusted; only the local collector can mint a trusted capture.

Origins (highest to lowest trust):
  TRUSTED_LOCAL_SERPAPI_CAPTURE  raw SerpApi response bytes written by banlag.collector on THIS machine, sealed with a
                                 machine-local HMAC key; request params, provider IDs/timestamps and SHA-256 bound.
                                 Proves what this collector received from serpapi.com and when. Does NOT prove
                                 Google's internal reasons, what any person saw, or the truth of a cited page.
  ARCHIVED_SERPAPI_CAPTURE       the same record without a verifiable seal (e.g. another machine): bytes and hashes
                                 are internally consistent, origin is not authenticated here.
  BROWSER_ARCHIVE_HASH_BOUND     the preregistered public-Google browser archive: transcribed text whose source files
                                 are hash-locked; not a SerpApi capture, no provider IDs.
  USER_SUPPLIED_UNVERIFIED       anything imported through the UI/API, whatever its source_kind label says.
  SYNTHETIC_FIXTURE              conspicuously synthetic test data. Never evidence.
Metadata consistency checks on an import are reported, but never upgrade its origin.
"""
import datetime as dt
import re

DECLARED_KINDS = ('SERPAPI_LIVE_CAPTURE', 'BROWSER_RESEARCH', 'SYNTHETIC_TEST')
TRUSTED = 'TRUSTED_LOCAL_SERPAPI_CAPTURE'
ARCHIVED_SERPAPI = 'ARCHIVED_SERPAPI_CAPTURE'
BROWSER_ARCHIVE = 'BROWSER_ARCHIVE_HASH_BOUND'
USER = 'USER_SUPPLIED_UNVERIFIED'
SYNTHETIC = 'SYNTHETIC_FIXTURE'
ORIGIN_RANK = {SYNTHETIC: 0, USER: 1, BROWSER_ARCHIVE: 2, ARCHIVED_SERPAPI: 2, TRUSTED: 3}
ORIGIN_STATEMENT = {
    TRUSTED: 'Sealed local SerpApi capture: this machine\'s collector received these exact bytes from serpapi.com with these parameters. Not proof of Google\'s reasons or of any cited page\'s truth.',
    ARCHIVED_SERPAPI: 'SerpApi-shaped capture with internally consistent hashes, but its seal cannot be verified on this machine.',
    BROWSER_ARCHIVE: 'Preregistered public-Google browser capture, hash-locked transcription. Not a SerpApi capture.',
    USER: 'Imported file. Its origin, timestamps and IDs are unverified, whatever it declares.',
    SYNTHETIC: 'Synthetic fixture. Not an observation. Never cite.',
}
SERPAPI_ID = re.compile(r'^[0-9a-f]{24}$')
SERPAPI_TIME = '%Y-%m-%d %H:%M:%S UTC'
ENDPOINT = re.compile(r'^https://serpapi\.com/searches/[0-9a-f]+/([0-9a-f]{24})\.json$')
ENGINE_FOR_SURFACE = {'google': 'google', 'ai_overview': 'google_ai_overview', 'ai_mode': 'google_ai_mode'}


def parse_serpapi_time(s):
    try:
        return dt.datetime.strptime(s, SERPAPI_TIME).replace(tzinfo=dt.timezone.utc)
    except (TypeError, ValueError):
        return None


def parse_iso(s):
    if not isinstance(s, str) or not re.match(r'^\d{4}-\d\d-\d\dT\d\d:\d\d(:\d\d(\.\d+)?)?([+-]\d\d:\d\d|Z)$', s):
        return None
    try:
        return dt.datetime.fromisoformat(s.replace('Z', '+00:00'))
    except ValueError:
        return None


def _chk(name, ok, detail='', advisory=False):
    return {'check': name, 'status': 'PASS' if ok else 'FAIL', 'detail': detail, 'advisory': advisory}


def check_metadata(obj, surface, query, now):
    """Consistency checks for one SerpApi-shaped response object. Returns (checks, search_id, created_at)."""
    md = obj.get('search_metadata') if isinstance(obj, dict) else None
    sp = obj.get('search_parameters') if isinstance(obj, dict) else None
    if not isinstance(md, dict):
        return [{'check': f'{surface}.search_metadata', 'status': 'ABSENT', 'detail': 'no provider metadata', 'advisory': False}], None, None
    out = []
    sid = md.get('id')
    out.append(_chk(f'{surface}.id_format', isinstance(sid, str) and bool(SERPAPI_ID.match(sid)), repr(sid)[:40]))
    out.append(_chk(f'{surface}.status', md.get('status') == 'Success', repr(md.get('status'))[:40]))
    created, processed = parse_serpapi_time(md.get('created_at')), parse_serpapi_time(md.get('processed_at'))
    out.append(_chk(f'{surface}.created_at_format', created is not None, repr(md.get('created_at'))[:40]))
    out.append(_chk(f'{surface}.processed_after_created', bool(created and processed and processed >= created)))
    out.append(_chk(f'{surface}.not_in_future', bool(created and created <= now + dt.timedelta(minutes=5))))
    em = ENDPOINT.match(md.get('json_endpoint') or '')
    out.append(_chk(f'{surface}.json_endpoint_binds_id', bool(em and em.group(1) == sid)))
    if isinstance(sid, str) and SERPAPI_ID.match(sid) and created:
        # Advisory only: SerpApi IDs look like MongoDB ObjectIds (leading 4 bytes = seconds). Unconfirmed until a real capture.
        embedded = dt.datetime.fromtimestamp(int(sid[:8], 16), dt.timezone.utc)
        out.append(_chk(f'{surface}.id_time_consistent', abs((embedded - created).total_seconds()) <= 600,
                        f'id time {embedded:%Y-%m-%d %H:%M:%S}Z', advisory=True))
    if isinstance(sp, dict):
        out.append(_chk(f'{surface}.engine', sp.get('engine') == ENGINE_FOR_SURFACE[surface], repr(sp.get('engine'))[:40]))
        if surface in ('google', 'ai_mode'):
            out.append(_chk(f'{surface}.q_matches_query', isinstance(query, str) and sp.get('q') == query, repr(sp.get('q'))[:80]))
    else:
        out.append({'check': f'{surface}.search_parameters', 'status': 'ABSENT', 'detail': '', 'advisory': False})
    return out, sid if isinstance(sid, str) else None, created


def assess_import(payload, now=None):
    """Origin + consistency report for an imported capture. Never returns a trusted origin."""
    now = now or dt.datetime.now(dt.timezone.utc)
    declared = payload.get('source_kind')
    origin = SYNTHETIC if declared == 'SYNTHETIC_TEST' else USER
    checks, ids = [], {}
    query = payload.get('query')
    for surface in ('google', 'ai_overview', 'ai_mode'):
        obj = payload.get(surface)
        if isinstance(obj, dict) and obj:
            c, sid, created = check_metadata(obj, surface, query, now)
            checks += c
            ids[surface] = {'search_id': sid, 'created_at': created.isoformat() if created else None}
    cap = parse_iso(payload.get('captured_at'))
    if declared == 'SERPAPI_LIVE_CAPTURE' or payload.get('captured_at') not in (None, '', 'SYNTHETIC'):
        checks.append(_chk('captured_at_iso8601_with_zone', cap is not None, repr(payload.get('captured_at'))[:40]))
        if cap:
            checks.append(_chk('captured_at_not_in_future', cap <= now + dt.timedelta(minutes=5)))
            created = [dt.datetime.fromisoformat(v['created_at']) for v in ids.values() if v.get('created_at')]
            if created:
                checks.append(_chk('captured_after_provider_created', all(cap >= c for c in created)))
    if declared == 'SERPAPI_LIVE_CAPTURE' and not any(v.get('search_id') for v in ids.values()):
        checks.append(_chk('serpapi_metadata_present', False, 'declared SerpApi capture carries no provider metadata'))
    g, a = payload.get('google') or {}, payload.get('ai_mode') or {}
    gp, ap = (g.get('search_parameters') or {}) if isinstance(g, dict) else {}, (a.get('search_parameters') or {}) if isinstance(a, dict) else {}
    if gp and ap:
        for k in ('gl', 'hl', 'location_requested'):
            if k in gp or k in ap:
                checks.append(_chk(f'locale_{k}_consistent', gp.get(k) == ap.get(k), f'{gp.get(k)!r} vs {ap.get(k)!r}'))
    gating = [c for c in checks if not c['advisory']]
    if any(c['status'] == 'FAIL' for c in gating):
        consistency = 'INCONSISTENT'
    elif not gating or all(c['status'] == 'ABSENT' for c in gating):
        consistency = 'ABSENT'
    elif any(c['status'] == 'ABSENT' for c in gating):
        consistency = 'INCOMPLETE'
    else:
        consistency = 'CONSISTENT'
    return {'origin': origin, 'declared_source_kind': declared, 'live_verified': False,
            'metadata_consistency': consistency, 'checks': checks, 'provider_ids': ids,
            'statement': ORIGIN_STATEMENT[origin] + (f' Declared as {declared}; that declaration is not verified.' if declared == 'SERPAPI_LIVE_CAPTURE' else '')}
