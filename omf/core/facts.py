"""Typed accepted ingredient facts: P (present), N (explicitly absent); everything else is UNKNOWN.

A search snippet, citation title or official notice text is an OBSERVATION about some text, never an
accepted fact about a real product's complete composition. Only reviewer/hypothetical assertions are
accepted, and each keeps its provenance.
"""
import re
import unicodedata

ACCEPTED_PROVENANCE = ('HYPOTHETICAL', 'USER_ASSERTED', 'SYNTHETIC_TEST')
REJECTED_PROVENANCE = ('ARCHIVED_PROVIDER', 'SEARCH_OBSERVATION', 'OFFICIAL_TEXT')
COMPLETENESS = ('NOT_ESTABLISHED', 'USER_ASSERTED_COMPLETE')
MAX_FACTS = 24
MAX_TERM_LEN = 80
MAX_NOTE_LEN = 200
_TERM_OK = re.compile(r"^[a-z0-9][a-z0-9 \-'().,]*$")
# A run of 20+ letters/digits containing a digit (e.g. a lower-cased token or hash) is not an ingredient name.
_TOKENLIKE = re.compile(r'(?<![a-z0-9])(?=[a-z0-9]{20,})[a-z]*\d|(?<![a-z0-9])[0-9a-f]{32,}(?![a-z0-9])')


class FactError(ValueError):
    def __init__(self, code, detail):
        super().__init__(f'{code}: {detail}')
        self.code = code
        self.detail = detail


def normalize(term):
    if not isinstance(term, str):
        raise FactError('INVALID_TERM', 'ingredient must be a string')
    t = unicodedata.normalize('NFKC', term).casefold()
    t = ' '.join(t.split())
    if not t or len(t) > MAX_TERM_LEN:
        raise FactError('INVALID_TERM', 'empty or overlong ingredient')
    if '+' in t:
        raise FactError('INVALID_TERM', 'one fact per ingredient; split combinations')
    if not _TERM_OK.match(t):
        raise FactError('INVALID_TERM', 'unsupported characters in ingredient')
    if _TOKENLIKE.search(t):
        raise FactError('INVALID_TERM', 'ingredient looks like an identifier or token, not a name')
    return t


def vocabulary(register):
    return {i for c in register['cases'] for i in c['ingredients']}


def resolve(term, register):
    """Map a normalized input to a canonical name, or report why it cannot be accepted.

    Returns (canonical or None, resolution_class).
    """
    vocab = vocabulary(register)
    group = set(register.get('probiotic_group', []))
    if term in vocab:
        # Exact notice wording. Probiotic notice terms carry a naming caveat (contested synonymy).
        return term, ('EXACT_NOTICE_TERM_NAMING_CONTESTED' if term in group else 'EXACT_NOTICE_TERM')
    alias = register.get('aliases', {}).get(term)
    if alias:
        if alias['class'] == 'SPELLING_VARIANT' and alias['canonical'] in vocab:
            return alias['canonical'], 'SPELLING_VARIANT'
        return None, 'CONTESTED_SYNONYM'
    if term in group:
        return None, 'CONTESTED_SYNONYM'
    for name, variants in register.get('other_actives', {}).items():
        if term == name or term in variants:
            return name, 'KNOWN_OUTSIDE_REGISTER_ACTIVE'
    return term, 'UNREGISTERED_TERM'


def accept(request, register):
    """Validate a fact request. Returns dict(present, absent, completeness, unresolved, notes).

    request = {'present': [{'term', 'provenance', 'note'?}], 'absent': [...], 'label_completeness'?}
    """
    if not isinstance(request, dict):
        raise FactError('INVALID_REQUEST', 'request must be an object')
    extra = set(request) - {'present', 'absent', 'label_completeness'}
    if extra:
        raise FactError('INVALID_REQUEST', f'unexpected fields {sorted(extra)}')
    completeness = request.get('label_completeness', 'NOT_ESTABLISHED')
    if completeness not in COMPLETENESS:
        raise FactError('INVALID_REQUEST', 'unknown label_completeness')
    out = {'present': [], 'absent': [], 'unresolved': [], 'label_completeness': completeness}
    seen = {}
    for side in ('present', 'absent'):
        items = request.get(side, [])
        if not isinstance(items, list) or len(items) > MAX_FACTS:
            raise FactError('INVALID_REQUEST', f'{side} must be a list of at most {MAX_FACTS} facts')
        for it in items:
            if not isinstance(it, dict) or set(it) - {'term', 'provenance', 'note'}:
                raise FactError('INVALID_REQUEST', 'fact must be {term, provenance, note?}')
            prov = it.get('provenance')
            if prov in REJECTED_PROVENANCE:
                raise FactError('FACT_PROVENANCE_NOT_ACCEPTABLE',
                                f'{prov} is an observation about text, not an accepted product fact')
            if prov not in ACCEPTED_PROVENANCE:
                raise FactError('FACT_PROVENANCE_NOT_ACCEPTABLE', 'provenance missing or unknown')
            note = it.get('note', '')
            if not isinstance(note, str) or len(note) > MAX_NOTE_LEN:
                raise FactError('INVALID_REQUEST', 'note must be a short string')
            term = normalize(it.get('term'))
            canon, klass = resolve(term, register)
            if canon is None:
                out['unresolved'].append({'input': term, 'side': side, 'reason': klass})
                continue
            if canon in seen:
                if seen[canon] == side:
                    raise FactError('DUPLICATE_FACT', 'the same ingredient was asserted twice on one side')
                # P and N both claim it: keep both so the conflict is reported, not silently resolved.
            seen.setdefault(canon, side)
            out[side].append({'term': canon, 'provenance': prov, 'resolution': klass})
    if completeness == 'USER_ASSERTED_COMPLETE' and not all(
            f['provenance'] == 'USER_ASSERTED' for f in out['present']):
        raise FactError('INVALID_REQUEST', 'a complete-label claim must be USER_ASSERTED for every present fact')
    if completeness == 'USER_ASSERTED_COMPLETE' and out['unresolved']:
        raise FactError('INVALID_REQUEST', 'a complete-label claim cannot contain unresolved names')
    out['present'].sort(key=lambda f: f['term'])
    out['absent'].sort(key=lambda f: f['term'])
    return out
