"""One bounded sanitizer for every outbound string, plus a recursive output gate.

Token-like material is detected in a bounded set of DECODED VIEWS of each whitespace-separated word:
raw, percent-decoding (up to 3 rounds), HTML-entity unescaping, \\uXXXX / \\xXX unescaping, and their
compositions (max 4 rounds, max 4096 chars per word). A word whose any view contains a secret-style
assignment (page_token=, api_key=, token=, ...) or a token-like run is replaced as a whole. This is
defence for display text; structural allowlisting in the projection is the primary boundary.
It does not claim to recognise every possible secret encoding (e.g. base64 of an arbitrary token).

G4 v2: NAMED secret assignments (page_token: <value>, "api_key" = '<value>', next_page_token=..., in JSON, query
strings, across whitespace/newlines, in percent / HTML-entity / \\u-escaped forms) are detected on the WHOLE
string in bounded decoded views BEFORE any word splitting. The value is private regardless of its length,
alphabet or entropy, so the whole field is withheld. Generic words such as "key" or "token" are not secret names.
Unlabelled opaque strings (e.g. arbitrary Base64) are NOT claimed to be detectable; untrusted text is protected by
the fail-closed release policy in archived_aio.public_view(), not by this heuristic.
"""
import html
import re
import unicodedata
from urllib.parse import unquote

MAX_TEXT = 4000
MAX_WORD = 4096
MAX_ROUNDS = 4
MAX_DEPTH = 16
REDACTED = '[REDACTED]'
WITHHELD = '[WITHHELD]'
_SECRET_ASSIGN = re.compile(
    r'(?i)(?<![A-Za-z])(page_?token|api_?key|access_?token|refresh_?token|token|signature|sig|auth|hmac|secret|session|sid|key)\s*[=:]\s*\S')
_RUN = re.compile(r'[A-Za-z0-9_\-]{20,}')
_HEX = re.compile(r'(?i)\b[0-9a-f]{32,}\b')
_U = re.compile(r'\\u([0-9a-fA-F]{4})')
_X = re.compile(r'\\x([0-9a-fA-F]{2})')
HASH_VALUE = re.compile(r'^[0-9a-f]{64}$')
SECRET_NAME = (r'(?:next_?page_?token|page_?token|continuation(?:_?token)?|api_?key|apikey|x-api-key|access_?token|'
               r'refresh_?token|auth_?token|id_?token|bearer|client_?secret|secret_?key|secret|hmac(?:_?sha256)?|'
               r'password|passwd|session_?id|sessionid|serpapi_?key)')
_NAMED_ASSIGN = re.compile(r'(?i)(?<![a-z0-9])["\']?' + SECRET_NAME + r'["\']?\s*[:=]')
_SECRET_KEY = re.compile(r'(?i)^["\']?' + SECRET_NAME + r'["\']?$')
MAX_WHOLE = 8192
MAX_VIEWS = 256
WITHHELD_SECRET = '[WITHHELD: secret-like assignment]'


def unsafe_char(c):
    return unicodedata.category(c) in ('Cc', 'Cf') and c not in '\n\t'


def decoded_views(word, cap=MAX_WORD):
    """Bounded decoded views: <= MAX_ROUNDS rounds, <= MAX_VIEWS views, each truncated to `cap` chars."""
    word = word[:cap]
    seen = {word}
    frontier = [word]
    for _ in range(MAX_ROUNDS):
        nxt = []
        for t in frontier:
            for f in (unquote, lambda s: unquote(s.replace('+', ' ')), html.unescape,
                      lambda s: _U.sub(lambda m: chr(int(m.group(1), 16)), s),
                      lambda s: _X.sub(lambda m: chr(int(m.group(1), 16)), s)):
                v = f(t)[:cap]
                if v not in seen and len(seen) < MAX_VIEWS:
                    seen.add(v)
                    nxt.append(v)
        frontier = nxt
        if not frontier:
            break
    return seen


def has_named_secret(s):
    """Whole-string check (before any tokenisation) for a named secret assignment in any bounded decoded view."""
    if not isinstance(s, str):
        return False
    return any(_NAMED_ASSIGN.search(v) for v in decoded_views(s[:MAX_WHOLE], MAX_WHOLE))


def is_secret_name(k):
    return isinstance(k, str) and any(_SECRET_KEY.match(v.strip()) for v in decoded_views(k[:200], 200))


def _tokenlike_run(s):
    for m in _RUN.finditer(s):
        t = m.group(0)
        if any(c.isdigit() for c in t) and any(c.isupper() for c in t) and any(c.islower() for c in t):
            return True
    return bool(_HEX.search(s))


def word_is_secretish(word):
    for v in decoded_views(word):
        if _SECRET_ASSIGN.search(v) or _tokenlike_run(v):
            return True
    return False


def sanitize_text(s, max_len=MAX_TEXT):
    """Display-safe text: control/format chars shown as [U+XXXX]; secret-ish words replaced whole."""
    if not isinstance(s, str):
        return None
    s = s[:max_len]
    if has_named_secret(s):
        return WITHHELD_SECRET
    s = ''.join(f'[U+{ord(c):04X}]' if unsafe_char(c) else c for c in s)
    parts = re.split(r'(\s+)', s)
    return ''.join(REDACTED if (p and not p.isspace() and word_is_secretish(p)) else p for p in parts)


def text_is_clean(s):
    return not has_named_secret(s) and all(not word_is_secretish(p) for p in s.split())


def gate(obj, path='', hash_keys=('sha256', 'digest'), _depth=0, _report=None):
    """Recursive output gate: every string (keys included) is checked in all decoded views.
    Values under keys ending in sha256/digest are allowed only as 64-hex digests. Offending strings are
    replaced by [WITHHELD]; offending keys are dropped. Returns (clean, report)."""
    report = _report if _report is not None else []
    if _depth > MAX_DEPTH:
        report.append(path or '/')
        return None, report
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if not isinstance(k, str) or is_secret_name(k) or not text_is_clean(k) or any(unsafe_char(c) for c in k):
                report.append(f'{path}/<key>')
                continue
            if isinstance(v, str) and k.endswith(hash_keys):
                if HASH_VALUE.match(v):
                    out[k] = v
                else:
                    out[k] = WITHHELD
                    report.append(f'{path}/{k}')
                continue
            out[k], _ = gate(v, f'{path}/{k}', hash_keys, _depth + 1, report)
        return out, report
    if isinstance(obj, list):
        return [gate(v, f'{path}/{i}', hash_keys, _depth + 1, report)[0] for i, v in enumerate(obj)], report
    if isinstance(obj, str):
        if not text_is_clean(obj):
            report.append(path or '/')
            return WITHHELD, report
        return obj, report
    if obj is None or isinstance(obj, (bool, int, float)):
        return obj, report
    report.append(path or '/')
    return None, report
