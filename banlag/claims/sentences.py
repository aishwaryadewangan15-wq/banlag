"""Sentence splitting, parenthetical stripping, truncation and reference-index helpers."""

import re
from ..legal import find_mentions
from .patterns import _DOT, _PROTECT, _SPLIT, _TRUNC_AFTER


def split_sentences(text):
    t = _PROTECT.sub(lambda m: m.group(0).replace('.', _DOT), text or '')
    t = re.sub(r'(?<=\d)\.(?=\d)', _DOT, t)
    return [s.replace(_DOT, '.').strip() for s in _SPLIT.split(t) if s.strip()]
def strip_parentheticals(text):
    """Main text without (...) asides, plus the asides. Nested parentheses are flattened."""
    asides, out, depth, buf = [], [], 0, []
    for ch in text:
        if ch == '(':
            depth += 1
            if depth == 1:
                buf = []
                continue
        elif ch == ')' and depth:
            depth -= 1
            if depth == 0:
                asides.append(''.join(buf))
                out.append(' ')
                continue
        (buf if depth else out).append(ch)
    if depth:
        asides.append(''.join(buf))
    return re.sub(r'\s+', ' ', ''.join(out)).strip(), asides
def list_truncated(text):
    """True if the text's last ingredient mention runs straight into a '...'/'…' cut-off (snippet truncation), so more
    ingredients may follow and the named set is only a lower bound. Seen in live SerpApi reference snippets."""
    ms = find_mentions(text or '')
    if not ms:
        return False
    rest = text[ms[-1]['end']:]
    return bool(_TRUNC_AFTER.match(rest)) or bool(re.match(r'^\s*[+,]\s*$', rest))
def _valid_index(i):
    """A reference index is a plain non-negative int: True, 0.0, '0' and None are malformed (never equal to 0 here)."""
    return type(i) is int and i >= 0
def reference_index_map(references):
    """index -> reference for well-formed, unique indexes; duplicate and malformed indexes are never resolved
    (no last-write-wins): ({index: ref}, sorted duplicate indexes, count of malformed indexes)."""
    refs = [r for r in references or [] if isinstance(r, dict)]
    ok = [r for r in refs if _valid_index(r.get('index'))]
    counts = {}
    for r in ok:
        counts[r['index']] = counts.get(r['index'], 0) + 1
    dup = sorted(i for i, n in counts.items() if n > 1)
    return {r['index']: r for r in ok if counts[r['index']] == 1}, dup, len(refs) - len(ok)
