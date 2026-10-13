"""Archived SerpApi google_ai_overview capture -> allowlisted public projection + ONE trust decision.

Trust architecture (G4 repair)
- Trust anchors live in CODE (adapters/trust_anchor.py), never beside the mutable derivative.
- The public projection is constructed field by field from a fixed schema (enums for structural fields,
  sanitized text, display-only links with no query). Unknown fields, stored "mentions", raw fragments and
  provider metadata never enter it.
- decide() is the single attribution decision. The served projection is authentic only if it is
  field-for-field equal to the projection re-derived from raw bytes that hash to RAW_SHA256 (state
  RAW_REVERIFIED), or, when the private raw archive is absent, if its content digest equals the code-pinned
  PROJECTION_SHA256 (state PROJECTION_PINNED). Anything else is UNVERIFIED (RAW_MISMATCH /
  PROJECTION_MISMATCH / RAW_UNVERIFIABLE): every paragraph is UNVERIFIED and no cited-scope comparison exists.
- Scope mentions are recomputed from authenticated reference text only; they are never stored or trusted.
- SHA-256 equality is agreement with pinned bytes, not provider authentication.
- G4 v2 RELEASE POLICY: a non-authentic decision (any state other than RAW_REVERIFIED / PROJECTION_PINNED) and any
  unverified export yield ONLY safe_diagnostic(): fixed state/reason codes, no title, source, snippet, path, URL,
  capture, query or comparison text from the archive or the derivative. Applied before serialization, so every
  API route, export and the UI receive the same withheld projection.
"""
import copy
import hashlib
import json
import os
import re
import stat
from datetime import datetime, timezone
from urllib.parse import unquote, urlsplit

from adapters import sanitize as S
from adapters import trust_anchor as T
from core import facts as F

PINNED_RAW_SHA256 = T.RAW_SHA256
RUN_ID = T.RUN_ID
MAX_RAW_BYTES = 2 * 1024 * 1024
MAX_TEXT = S.MAX_TEXT
MAX_BLOCKS = 64
MAX_REFS = 64
MAX_INDEXES = 32
BLOCK_TYPES = ('paragraph', 'list', 'list_item', 'heading', 'table', 'expandable', 'other')
LINK_STATES = ('LINKED', 'UNLINKED', 'UNVERIFIED')
CONTENT_KEYS = ('schema', 'raw_sha256', 'capture', 'query_terms_observed', 'query_target_rows', 'blocks', 'references')
SCHEMA = 'omf.aio_projection.v2'
_REPARSE = getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400)
_ISO = re.compile(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+00:00$')
_PROV_TS = re.compile(r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} UTC$')


class EvidenceError(ValueError):
    pass


POINTER = re.compile(r'^/ai_overview/text_blocks/\d{1,2}(/list/\d{1,2})?$')
STATE_CODES = ('RAW_REVERIFIED', 'PROJECTION_PINNED', 'RAW_MISMATCH', 'PROJECTION_MISMATCH', 'RAW_UNVERIFIABLE',
               'PROJECTION_MALFORMED', 'RAW_ABSENT', 'UNVERIFIED_EXPORT')


def safe_diagnostic(state, mismatch_count=0):
    """The ONLY evidence object released when evidence is not authentic. Contains no input-derived strings."""
    state = state if state in STATE_CODES else 'PROJECTION_MALFORMED'
    return {'schema': SCHEMA, 'origin': 'UNVERIFIED_ORIGIN',
            'provenance_label': 'UNVERIFIED - evidence withheld', 'raw_sha256': None, 'capture': {},
            'query_terms_observed': [], 'query_target_rows': [], 'blocks': [], 'references': [],
            'trust': {'state': state, 'authentic': False, 'withheld': True,
                      'mismatch_count': int(mismatch_count) if isinstance(mismatch_count, int) else 0,
                      'anchor': {'raw_sha256': T.RAW_SHA256, 'projection_sha256': T.PROJECTION_SHA256},
                      'note': 'Evidence did not match the code-pinned archive. No archive- or derivative-supplied '
                              'text, link, capture field or citation comparison is released in this state.'}}


def _no_dupe_keys(pairs):
    seen = set()
    for k, _v in pairs:
        if k in seen:
            raise EvidenceError('duplicate JSON key')
        seen.add(k)
    return dict(pairs)


def safe_read(path, allowed_root, max_bytes=MAX_RAW_BYTES):
    """Read a file only if it is a regular, non-link, non-reparse file inside allowed_root."""
    ap = os.path.abspath(path)
    root = os.path.abspath(allowed_root)
    if os.path.commonpath([ap, root]) != root:
        raise EvidenceError('path escapes the allowed evidence directory')
    if os.path.realpath(ap) != os.path.realpath(root) and \
            os.path.commonpath([os.path.realpath(ap), os.path.realpath(root)]) != os.path.realpath(root):
        raise EvidenceError('resolved path escapes the allowed evidence directory')
    st = os.lstat(ap)
    if stat.S_ISLNK(st.st_mode) or (getattr(st, 'st_file_attributes', 0) & _REPARSE):
        raise EvidenceError('symlinks / reparse points are refused')
    if not stat.S_ISREG(st.st_mode):
        raise EvidenceError('not a regular file')
    if st.st_size > max_bytes:
        raise EvidenceError('file exceeds size cap')
    with open(ap, 'rb') as fh:
        data = fh.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise EvidenceError('file exceeds size cap')
    return data


def parse_json(data, max_bytes=MAX_RAW_BYTES):
    if len(data) > max_bytes:
        raise EvidenceError('JSON exceeds size cap')
    try:
        return json.loads(data.decode('utf-8'), object_pairs_hook=_no_dupe_keys)
    except EvidenceError:
        raise
    except (ValueError, RecursionError, UnicodeDecodeError) as e:
        raise EvidenceError(f'malformed JSON ({type(e).__name__})')


def redact_text(s):
    """Backward-compatible name for the single display sanitizer."""
    return S.sanitize_text(s)


def safe_link(u):
    """Display-only host+path for https URLs without credentials; query and fragment are always dropped.
    A path segment whose any decoded view is token-like refuses the whole link. Never clickable."""
    if not isinstance(u, str) or len(u) > 2048:
        return None, 'MISSING_OR_OVERLONG'
    if any(S.unsafe_char(c) or c.isspace() for c in u):
        return None, 'UNSAFE_CHARACTERS'
    try:
        p = urlsplit(u)
    except ValueError:
        return None, 'UNPARSEABLE'
    if p.scheme != 'https' or not p.hostname or p.username or p.password:
        return None, 'UNSAFE_SCHEME_OR_CREDENTIALS'
    if not re.fullmatch(r'[a-z0-9.\-]+', p.hostname):
        return None, 'UNSAFE_HOST'
    path = p.path[:200]
    for seg in path.split('/'):
        if seg and S.word_is_secretish(seg):
            return None, 'TOKENLIKE_PATH_REFUSED'
    if any(S.unsafe_char(c) for c in unquote(path)):
        return None, 'UNSAFE_CHARACTERS'
    return p.hostname + path, ('QUERY_REMOVED' if (p.query or p.fragment) else 'OK')


def index_status(refidx, ref_by_index):
    """Return (status, resolved_indexes, reason)."""
    if refidx is None:
        return 'UNLINKED', [], 'no reference_indexes on this block'
    if not isinstance(refidx, list):
        return 'UNVERIFIED', [], 'reference_indexes is not a list'
    if not refidx:
        return 'UNLINKED', [], 'empty reference_indexes'
    if len(refidx) > MAX_INDEXES:
        return 'UNVERIFIED', [], 'too many indexes'
    if any(type(i) is not int for i in refidx):
        return 'UNVERIFIED', [], 'non-integer or nested index'
    if any(i < 0 for i in refidx):
        return 'UNVERIFIED', [], 'negative index'
    if len(set(refidx)) != len(refidx):
        return 'UNVERIFIED', [], 'duplicate index'
    if any(i not in ref_by_index for i in refidx):
        return 'UNVERIFIED', [], 'index does not resolve to exactly one reference'
    return 'LINKED', list(refidx), ''


def _index_refs(refs):
    by, bad = {}, set()
    for pos, r in enumerate(refs):
        i = r.get('index') if isinstance(r, dict) else None
        if type(i) is not int or i != pos or i in by:
            bad.add(i if type(i) is int else pos)
            continue
        by[i] = r
    for b in bad:
        by.pop(b, None)
    return by


# ---- mention analysis (observations about text, never product facts) ----------------------------

def _resolve_phrase(words, register):
    t = ' '.join(words).casefold()
    try:
        t = F.normalize(t)
    except F.FactError:
        return None
    canon, klass = F.resolve(t, register)
    if klass in ('UNREGISTERED_TERM',):
        return None
    if canon is None:
        return (t, klass)
    return (canon, klass)


def _wordspans(s):
    return [(m.group(0), m.end()) for m in re.finditer(r"[A-Za-z][A-Za-z\-']*", s)]


def _words(s):
    return [w for w, _e in _wordspans(s)]


_ELLIPSIS = re.compile(r'^\s*(\.\.\.|…)')


def extract_chains(text, register):
    """Find 'A + B + C' ingredient chains (one per '|'/newline/bullet-separated part).

    Returns [{terms, truncated, unresolved_count}]. Unresolved segment TEXT is never returned.
    """
    out = []
    if not isinstance(text, str) or '+' not in text:
        return out
    parts = re.split(r'[|\n*•]', text)
    for pi, part in enumerate(parts):
        if '+' not in part:
            continue
        segs = re.split(r'\s*\+\s*', part)
        terms, unresolved, truncated = [], 0, False
        for k, seg in enumerate(segs):
            ws = _wordspans(seg)
            w = [x for x, _e in ws]
            found = None
            if k == 0:
                for j in range(max(0, len(w) - 4), len(w)):
                    found = _resolve_phrase(w[j:], register)
                    if found:
                        break
            else:
                for j in range(min(4, len(w)), 0, -1):
                    found = _resolve_phrase(w[:j], register)
                    if found:
                        if k == len(segs) - 1:
                            tail = seg[ws[j - 1][1]:]
                            at_end = pi == len(parts) - 1 and not tail.strip()
                            truncated = bool(_ELLIPSIS.match(tail)) or at_end
                        break
            if found:
                if found[0] not in terms:
                    terms.append(found[0])
            else:
                unresolved += 1
        if len(terms) >= 2:
            out.append({'terms': terms, 'truncated': truncated, 'unresolved_count': unresolved})
    return out


def classify_chain(chain, register):
    rows = {c['id']: set(c['ingredients']) for c in register['cases']}
    s = set(chain['terms'])
    vocab = F.vocabulary(register)
    if chain.get('unresolved_count'):
        return {'kind': 'UNRESOLVED_TERMS', 'rows': []}
    if chain['truncated']:
        return {'kind': 'TRUNCATED_CONSISTENT_WITH', 'rows': sorted(r for r, ing in rows.items() if s <= ing)}
    exact = sorted(r for r, ing in rows.items() if ing == s)
    if exact:
        return {'kind': 'EXACT_MODELED_COMPOSITION', 'rows': exact}
    if s - vocab:
        return {'kind': 'OUTSIDE_MODELED_REGISTER', 'rows': [], 'outside_terms': sorted(s - vocab)}
    return {'kind': 'NO_MODELED_COMPOSITION_MATCH', 'rows': []}


def query_terms(q, register):
    """Greedy longest-match scan of plain text for known ingredient names (contested names excluded)."""
    w = _words(q or '')
    i, terms = 0, []
    while i < len(w):
        for j in range(min(len(w), i + 4), i, -1):
            f = _resolve_phrase(w[i:j], register)
            if f and f[1] != 'CONTESTED_SYNONYM':
                terms.append(f[0])
                i = j
                break
        else:
            i += 1
    return sorted(set(terms))


def reference_mentions(ref, register):
    """Recompute scope observations from (authenticated) reference text."""
    mentions = []
    for field in ('title', 'snippet'):
        for ch in extract_chains(ref.get(field) or '', register):
            mentions.append({'field': field, 'terms': ch['terms'], 'truncated': ch['truncated'],
                             'unresolved_count': ch['unresolved_count'], 'scope': classify_chain(ch, register)})
    if not mentions:
        names = query_terms(' '.join(x for x in (ref.get('title'), ref.get('snippet')) if x), register)
        if len(names) >= 2:
            mentions.append({'field': 'title+snippet', 'terms': names, 'truncated': None, 'unresolved_count': 0,
                             'scope': {'kind': 'UNPARSED_INGREDIENT_LIST', 'rows': []}})
    return mentions


# ---- projection -------------------------------------------------------------------------------

def _ts_note(collector, provider):
    try:
        a = datetime.fromisoformat(collector)
        b = datetime.strptime(provider, '%Y-%m-%d %H:%M:%S UTC').replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return 'Collector and provider timestamps could not both be read; ordering unresolved.'
    d = round((b - a).total_seconds())
    rel = 'later' if d > 0 else 'earlier' if d < 0 else 'equal to'
    return (f'Provider timestamp is {abs(d)} s {rel} than the collector receipt time. A response cannot be created '
            'after it was received, so the two clocks disagree; this clock skew is unresolved and neither clock is '
            'treated as authoritative.') if d > 0 else f'Provider timestamp is {abs(d)} s {rel} the collector receipt time.'


def _capture(c1, c2):
    req2 = c2.get('request') if isinstance(c2.get('request'), dict) else {}
    req1 = c1.get('request') if isinstance(c1.get('request'), dict) else {}
    params1 = req1.get('params') if isinstance(req1.get('params'), dict) else {}
    prov = c2.get('provider') if isinstance(c2.get('provider'), dict) else {}
    recv = c2.get('received_at') if isinstance(c2.get('received_at'), str) and _ISO.match(c2.get('received_at')) else None
    pc = prov.get('created_at') if isinstance(prov.get('created_at'), str) and _PROV_TS.match(prov.get('created_at')) else None
    pp = prov.get('processed_at') if isinstance(prov.get('processed_at'), str) and _PROV_TS.match(prov.get('processed_at')) else None
    return {
        'engine': req2.get('engine') if req2.get('engine') in ('google_ai_overview',) else None,
        'role': c2.get('role') if c2.get('role') in ('uses_ai_overview', 'status_ai_overview') else None,
        'collector_received_at_utc': recv,
        'provider_created_at_utc': pc,
        'provider_processed_at_utc': pp,
        'clock_note': _ts_note(recv, pc) if recv and pc else 'timestamps unavailable',
        'parent_query': S.sanitize_text(params1.get('q'), 300) if isinstance(params1.get('q'), str) else None,
        'parent_engine': req1.get('engine') if req1.get('engine') in ('google',) else None,
        'gl': params1.get('gl') if isinstance(params1.get('gl'), str) and re.fullmatch(r'[a-z]{2}', params1.get('gl')) else None,
        'provider_status': prov.get('status') if prov.get('status') in ('Success',) else None,
        'note': 'Collector HMAC seal not verifiable here (collector key never exported). '
                'SHA-256 agreement with pinned bytes only; not a provider signature.',
    }


def _block_type(t, default):
    return t if t in BLOCK_TYPES else ('other' if t is not None else default)


def project(raw_obj, c1, c2, register, raw_sha):
    """Build the allowlisted public projection from parsed provider JSON."""
    aio = raw_obj.get('ai_overview') if isinstance(raw_obj, dict) else None
    if not isinstance(aio, dict):
        raise EvidenceError('no ai_overview object')
    blocks_in = aio.get('text_blocks') if isinstance(aio.get('text_blocks'), list) else []
    refs_in = aio.get('references') if isinstance(aio.get('references'), list) else []
    if len(blocks_in) > MAX_BLOCKS or len(refs_in) > MAX_REFS:
        raise EvidenceError('too many blocks/references')
    by_index = _index_refs(refs_in)
    refs = []
    for pos, r in enumerate(refs_in):
        if not isinstance(r, dict):
            refs.append({'position': pos, 'index': None, 'resolvable': False, 'source': None, 'title': None,
                         'snippet': None, 'link_display': None, 'link_note': 'MALFORMED',
                         'pointer': f'/ai_overview/references/{pos}', 'snippet_truncated_in_capture': False})
            continue
        link, note = safe_link(r.get('link'))
        snip = r.get('snippet') if isinstance(r.get('snippet'), str) else None
        refs.append({
            'position': pos, 'index': r.get('index') if type(r.get('index')) is int else None,
            'resolvable': pos in by_index and by_index[pos] is r,
            'source': S.sanitize_text(r.get('source'), 200), 'title': S.sanitize_text(r.get('title'), 400),
            'snippet': S.sanitize_text(snip), 'link_display': link, 'link_note': note,
            'pointer': f'/ai_overview/references/{pos}',
            'snippet_truncated_in_capture': bool(snip and re.search(r'(\.\.\.|…)\s*$', snip)),
        })
    blocks = []
    for bi, tb in enumerate(blocks_in):
        if not isinstance(tb, dict):
            continue
        items = [('', tb, 'paragraph')]
        if isinstance(tb.get('list'), list):
            items += [(f'/list/{li}', it, 'list_item') for li, it in enumerate(tb['list'][:MAX_BLOCKS]) if isinstance(it, dict)]
        for suffix, it, default in items:
            st, resolved, why = index_status(it.get('reference_indexes'), by_index)
            blocks.append({
                'block': bi, 'pointer': f'/ai_overview/text_blocks/{bi}{suffix}',
                'type': _block_type(it.get('type'), default),
                'snippet': S.sanitize_text(it.get('snippet')) if isinstance(it.get('snippet'), str) else None,
                'reference_indexes': resolved if st == 'LINKED' else None,
                'link_status': st, 'link_reason': why,
            })
    cap = _capture(c1, c2)
    qterms = query_terms(cap['parent_query'], register) if cap['parent_query'] else []
    target = [c['id'] for c in register['cases'] if qterms and set(c['ingredients']) == set(qterms)]
    return {'schema': SCHEMA, 'raw_sha256': raw_sha, 'capture': cap, 'query_terms_observed': qterms,
            'query_target_rows': target, 'blocks': blocks, 'references': refs}


def _records_ok(records, raw_sha):
    """Capture-record chain: pinned record hashes, manifest -> C2 -> raw, parent/engine consistency."""
    try:
        for k in ('manifest', 'c1', 'c2'):
            if hashlib.sha256(records[k]).hexdigest() != T.RECORD_SHA256[k]:
                raise EvidenceError(f'{k} record differs from pinned hash')
        man = parse_json(records['manifest'], 65536)
        c1 = parse_json(records['c1'], 65536)['record']
        c2 = parse_json(records['c2'], 65536)['record']
        fs = man['files_sha256']
        if fs.get(f'raw/{raw_sha}.json') != raw_sha or c2.get('raw_sha256') != raw_sha:
            raise EvidenceError('record chain does not reference these raw bytes')
        if c2.get('parent_call_id') != c1.get('call_id') or c2['request']['engine'] != 'google_ai_overview':
            raise EvidenceError('capture parent/engine chain inconsistent')
        return c1, c2, None
    except (EvidenceError, KeyError, TypeError) as e:
        return {}, {}, str(e)


def build(raw_bytes, records, register, pinned_raw_sha=PINNED_RAW_SHA256):
    """Export path: project raw bytes. Origin is ARCHIVED only for pinned raw + pinned record chain.
    The result always passes the output gate before it is returned."""
    raw_sha = hashlib.sha256(raw_bytes).hexdigest()
    reasons = []
    if raw_sha != pinned_raw_sha:
        reasons.append('raw bytes do not match the pinned capture hash')
    c1, c2, why = _records_ok(records, raw_sha)
    if why:
        reasons.append(f'capture record chain: {why}')
    raw = parse_json(raw_bytes)
    p = project(raw, c1, c2, register, raw_sha)   # validates structure (malformed input still raises)
    if reasons:
        codes = (['RAW_HASH_MISMATCH'] if raw_sha != pinned_raw_sha else []) + (['RECORD_CHAIN_INVALID'] if why else [])
        d = safe_diagnostic('UNVERIFIED_EXPORT')
        d.update(origin_reasons=codes, provenance_label='UNVERIFIED / SYNTHETIC', output_gate_withheld=0)
        return d
    p = dict(p, origin='ARCHIVED_SERPAPI_CAPTURE', origin_reasons=[], provenance_label='REAL ARCHIVED')
    clean, report = S.gate(p)
    clean['output_gate_withheld'] = len(report)
    return clean


def content(p):
    return {k: p.get(k) for k in CONTENT_KEYS}


def derivative_digest(d):
    return hashlib.sha256(json.dumps(content(d), sort_keys=True, separators=(',', ':'), ensure_ascii=False)
                          .encode('utf-8')).hexdigest()


def reproject(served):
    """Re-derive a schema-conformant projection from an UNTRUSTED served derivative: only schema fields,
    enums enforced, all text re-sanitized, links re-validated. Unknown keys are dropped."""
    if not isinstance(served, dict):
        raise EvidenceError('derivative is not an object')
    for key, typ in (('blocks', list), ('references', list), ('capture', dict), ('query_terms_observed', list),
                     ('query_target_rows', list)):
        if key in served and not isinstance(served[key], typ):
            raise EvidenceError(f'{key} has the wrong container type')
    if len(served.get('blocks') or []) > 4 * MAX_BLOCKS or len(served.get('references') or []) > MAX_REFS:
        raise EvidenceError('too many blocks/references')
    for key in ('blocks', 'references'):
        for el in served.get(key) or []:
            if not isinstance(el, dict):
                raise EvidenceError(f'{key} element is not an object')
            if 'index' in el and el['index'] is not None and type(el['index']) is not int:
                raise EvidenceError('index must be an integer')
            ri = el.get('reference_indexes')
            if ri is not None and (not isinstance(ri, list) or any(type(i) is not int for i in ri)):
                raise EvidenceError('reference_indexes must be a list of integers')

    def txt(v, n=MAX_TEXT):
        return S.sanitize_text(v, n) if isinstance(v, str) else None

    def link(v):
        if not isinstance(v, str):
            return None
        out, _ = safe_link('https://' + v)
        return out

    blocks = []
    for b in served.get('blocks') or []:
        if not isinstance(b, dict) or not isinstance(b.get('pointer'), str) or \
                not re.fullmatch(r'/ai_overview/text_blocks/\d{1,2}(/list/\d{1,2})?', b['pointer']):
            continue
        ri = b.get('reference_indexes')
        blocks.append({'block': b.get('block') if type(b.get('block')) is int else None, 'pointer': b['pointer'],
                       'type': _block_type(b.get('type'), 'other'), 'snippet': txt(b.get('snippet')),
                       'reference_indexes': ri if isinstance(ri, list) and all(type(i) is int for i in ri) else None,
                       'link_status': b.get('link_status') if b.get('link_status') in LINK_STATES else 'UNVERIFIED',
                       'link_reason': txt(b.get('link_reason'), 120) or ''})
    refs = []
    for pos, r in enumerate(served.get('references') or []):
        if not isinstance(r, dict):
            continue
        refs.append({'position': pos, 'index': r.get('index') if type(r.get('index')) is int else None,
                     'resolvable': r.get('resolvable') is True, 'source': txt(r.get('source'), 200),
                     'title': txt(r.get('title'), 400), 'snippet': txt(r.get('snippet')),
                     'link_display': link(r.get('link_display')),
                     'link_note': r.get('link_note') if r.get('link_note') in (
                         'OK', 'QUERY_REMOVED', 'MISSING_OR_OVERLONG', 'UNSAFE_CHARACTERS', 'UNPARSEABLE',
                         'UNSAFE_SCHEME_OR_CREDENTIALS', 'UNSAFE_HOST', 'TOKENLIKE_PATH_REFUSED', 'MALFORMED') else None,
                     'pointer': f'/ai_overview/references/{pos}',
                     'snippet_truncated_in_capture': r.get('snippet_truncated_in_capture') is True})
    cap_in = served.get('capture') if isinstance(served.get('capture'), dict) else {}
    cap = {k: txt(cap_in.get(k), 600) for k in ('engine', 'role', 'collector_received_at_utc', 'provider_created_at_utc',
                                                'provider_processed_at_utc', 'clock_note', 'parent_query',
                                                'parent_engine', 'gl', 'provider_status', 'note')}
    raw_sha = served.get('raw_sha256') if isinstance(served.get('raw_sha256'), str) and \
        S.HASH_VALUE.match(served.get('raw_sha256')) else None

    def strlist(v, pat):
        return [x for x in v if isinstance(x, str) and re.fullmatch(pat, x)] if isinstance(v, list) else []

    return {'schema': served.get('schema') if served.get('schema') == SCHEMA else None, 'raw_sha256': raw_sha,
            'capture': cap, 'query_terms_observed': strlist(served.get('query_terms_observed'), r"[a-z0-9 \-'().,]{1,80}"),
            'query_target_rows': strlist(served.get('query_target_rows'), r'[A-Z]\d{2}'),
            'blocks': blocks, 'references': refs}


def load_verified_raw(run_dir, register):
    """Return (expected_projection, None) from raw bytes that hash to the code-pinned anchor, or
    (None, reason). Read-only; the raw object never leaves this function."""
    try:
        raw = safe_read(os.path.join(run_dir, 'raw', T.RAW_SHA256 + '.json'), run_dir)
        recs = {'manifest': safe_read(os.path.join(run_dir, 'EXPORT_MANIFEST.json'), run_dir, 65536),
                'c1': safe_read(os.path.join(run_dir, f'{T.RUN_ID}-C1.json'), run_dir, 65536),
                'c2': safe_read(os.path.join(run_dir, f'{T.RUN_ID}-C2.json'), run_dir, 65536)}
    except (OSError, EvidenceError) as e:
        return None, f'RAW_ABSENT ({type(e).__name__})'
    sha = hashlib.sha256(raw).hexdigest()
    if sha != T.RAW_SHA256:
        return None, 'RAW_MISMATCH (archive bytes differ from the pinned hash)'
    c1, c2, why = _records_ok(recs, sha)
    if why:
        return None, f'RAW_MISMATCH (capture records: {why})'
    exp = project(parse_json(raw), c1, c2, register, sha)
    clean, report = S.gate(exp)
    if report:
        return None, 'RAW_UNVERIFIABLE (verified projection would need withheld fields)'
    return clean, None


def _diff_paths(a, b, path='', out=None, limit=20):
    out = [] if out is None else out
    if len(out) >= limit:
        return out
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            _diff_paths(a.get(k), b.get(k), f'{path}/{k}', out, limit)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            out.append(f'{path} (length)')
        for i, (x, y) in enumerate(zip(a, b)):
            _diff_paths(x, y, f'{path}/{i}', out, limit)
    elif a != b:
        out.append(path or '/')
    return out


def decide(served, expected=None, raw_problem=None):
    """THE single fail-closed attribution decision, consumed by every API, export and UI surface."""
    try:
        proj = reproject(served)
    except (EvidenceError, TypeError, ValueError, AttributeError, KeyError, RecursionError):
        return {'state': 'PROJECTION_MALFORMED', 'authentic': False, 'mismatches': ['malformed projection']}, None
    if raw_problem and raw_problem.startswith(('RAW_MISMATCH', 'RAW_UNVERIFIABLE')):
        return {'state': raw_problem.split(' ')[0], 'authentic': False, 'mismatches': [raw_problem]}, proj
    if expected is not None:
        diffs = _diff_paths(content(expected), content(proj))
        return ({'state': 'RAW_REVERIFIED', 'authentic': True, 'mismatches': []} if not diffs else
                {'state': 'RAW_MISMATCH', 'authentic': False, 'mismatches': diffs}), proj
    if T.PROJECTION_SHA256 and derivative_digest(proj) == T.PROJECTION_SHA256:
        return {'state': 'PROJECTION_PINNED', 'authentic': True, 'mismatches': []}, proj
    return {'state': 'PROJECTION_MISMATCH', 'authentic': False,
            'mismatches': ['projection digest differs from the code-pinned value']}, proj


def public_view(proj, decision):
    """Apply the decision to every field that could imply authenticity, then pass the output gate."""
    if decision.get('authentic') is not True or proj is None:
        return safe_diagnostic(decision.get('state'), len(decision.get('mismatches') or []))
    v = copy.deepcopy(proj)
    auth = decision['authentic']
    v['origin'] = 'ARCHIVED_SERPAPI_CAPTURE' if auth else 'UNVERIFIED_ORIGIN'
    v['provenance_label'] = 'REAL ARCHIVED' if auth else 'UNVERIFIED (does not match the pinned archive)'
    v['trust'] = {'state': decision['state'], 'authentic': auth, 'mismatch_count': len(decision['mismatches']),
                  'mismatch_paths': [m for m in decision['mismatches'] if m.startswith('/')][:20],
                  'anchor': {'raw_sha256': T.RAW_SHA256, 'projection_sha256': T.PROJECTION_SHA256},
                  'note': 'SHA-256 agreement with code-pinned bytes; not provider authentication.'}
    if not auth:
        for b in v['blocks']:
            b['link_status'] = 'UNVERIFIED'
            b['link_reason'] = f'evidence does not match the pinned archive ({decision["state"]})'
            b['reference_indexes'] = None
    clean, report = S.gate(v)
    clean['trust']['output_gate_withheld'] = len(report)
    return clean


def corrupt_block(proj, pointer, value, delete=False):
    """Demo helper: structurally re-evaluate one block's indexes in a COPY of the projection. The caller
    must pass the result through decide() again; it can never be authentic."""
    d = copy.deepcopy(proj)
    by_index = {r['position']: r for r in d['references'] if r.get('resolvable')}
    for b in d['blocks']:
        if b.get('pointer') == pointer:
            st, resolved, why = index_status(None if delete else value, by_index)
            b['link_status'], b['link_reason'] = st, why
            b['reference_indexes'] = resolved if st == 'LINKED' else None
    return d


def scope_analysis(view, register, block_pointer):
    """Statement-level scope comparison for one block of a PUBLIC VIEW. Only an authentic view yields
    links or comparisons; mentions are recomputed from its reference text. Observations only."""
    rows = {c['id']: c for c in register['cases']}
    trust = view.get('trust') or {}
    block_pointer = block_pointer if isinstance(block_pointer, str) and POINTER.match(block_pointer) else None
    res = {'block_pointer': block_pointer, 'query_target_rows': view.get('query_target_rows') or [], 'links': [],
           'diffs': [], 'attribution': 'UNVERIFIED', 'evidence_state': trust.get('state'), 'notes': []}
    if trust.get('authentic') is not True:
        res['notes'].append('Evidence does not match the pinned archive, so no paragraph is attributed and no '
                            'cited-scope comparison is shown.')
        return res
    blk = next((b for b in view['blocks'] if b.get('pointer') == block_pointer), None)
    if blk is None:
        res['notes'].append('block not found')
        return res
    res['attribution'] = blk['link_status']
    if blk['link_status'] != 'LINKED':
        res['notes'].append('Source-to-sentence attribution is not verified, so no cited-scope comparison is shown.')
        return res
    target = res['query_target_rows']
    for i in blk['reference_indexes']:
        ref = view['references'][i]
        mentions = reference_mentions(ref, register)
        scopes = [m['scope'] for m in mentions]
        kinds = sorted({s['kind'] for s in scopes}) or ['NO_INGREDIENT_CHAIN_IN_SNIPPET']
        res['links'].append({'index': i, 'source': ref['source'], 'title': ref['title'], 'snippet': ref['snippet'],
                             'scope_kinds': kinds, 'rows': sorted({r for s in scopes for r in s['rows']}),
                             'names_seen': sorted({t for m in mentions for t in m['terms']})})
        for s in scopes:
            if s['kind'] == 'EXACT_MODELED_COMPOSITION' and len(target) == 1:
                for r in s['rows']:
                    if r == target[0]:
                        continue
                    a, b = set(rows[target[0]]['ingredients']), set(rows[r]['ingredients'])
                    res['diffs'].append({'reference_index': i, 'cited_row': r, 'cited_notice': rows[r]['notice'],
                                         'target_row': target[0], 'target_notice': rows[target[0]]['notice'],
                                         'cited_has_extra': sorted(b - a), 'cited_lacks': sorted(a - b)})
    return res
