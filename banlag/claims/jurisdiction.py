"""Restriction status of one sentence (current, revoked, proposed, historical) and its jurisdiction."""

from ..legal import find_mentions
from .patterns import INDIA, OTHER_JURIS, _AFTER_CUT, _NON_PLACE, _PLACE


def restriction_qualifiers(sentence):
    """Boolean status qualifiers of the restriction terms in one sentence (see restriction_status)."""
    st = restriction_status(sentence)
    return {k: st[k] for k in ('negated', 'revoked', 'historical', 'proposed', 'conditional')}
def restriction_status(sentence, india_context=False, as_of=None):
    """Status of each restriction predicate in one sentence, from the shared event model (semantics.sentence_events):
    predicate-local negation and denial, condition/proviso, proposal, dates, jurisdiction attached to the predicate, and
    revocation scoped to the restriction it refers to. A predicate is current-India only if it is attached to India and
    carries no qualifier. This view has no target entity; promotion paths use semantics.event_qualifies instead."""
    from ..semantics import resolve_chronology, sentence_events
    evs = resolve_chronology(sentence_events(sentence, None, 0, india_context, as_of))
    per = []
    for e in evs:
        if e['kind'] != 'RESTRICTION':
            continue
        p = {'term': e['term'], 'negated': e['negated'] or e['denied'], 'denied': e['denied'], 'reported': e['reported'],
             'historical': e['historical'], 'proposed': e['proposed'], 'conditional': e['conditional'],
             'revoked': bool(e['revoked_by']), 'jurisdiction': e['jurisdiction']}
        p['current'] = not (p['revoked'] or p['negated'] or p['historical'] or p['proposed'] or p['conditional'])
        per.append(p)
    st = {k: any(p[k] for p in per) for k in ('negated', 'historical', 'proposed', 'conditional')}
    st['revoked'] = any(p['revoked'] for p in per) or any(e['kind'] == 'REVOCATION' for e in evs)
    js = [p['jurisdiction'] for p in per]
    st['jurisdiction'] = next((j for j in ('INDIA', 'OTHER', 'AMBIGUOUS') if j in js), 'UNSPECIFIED')
    st['current_india'] = any(p['current'] and p['jurisdiction'] == 'INDIA' for p in per)
    st['predicates'] = per
    return st
def _place_kind(phrase):
    if INDIA.search(phrase):
        return 'INDIA'
    if OTHER_JURIS.search(phrase):
        return 'OTHER'
    if find_mentions(phrase):
        return None  # an ingredient name, not a place
    words = [w.strip(".'").lower() for w in phrase.split() if w[:1].isupper()]
    return 'OTHER' if any(w not in _NON_PLACE for w in words) else None
def _jurisdiction_marks(text):
    """(position, kind) of every India / other-jurisdiction mark in text."""
    marks = [(m.start(), 'INDIA') for m in INDIA.finditer(text)] + [(m.start(), 'OTHER') for m in OTHER_JURIS.finditer(text)]
    for m in _PLACE.finditer(text):
        k = _place_kind(m.group(1))
        if k:
            marks.append((m.start(), k))
    return sorted(marks)
def _predicate_jurisdiction(sentence, clause, a, b):
    """Jurisdiction attached to one restriction predicate: the first place/authority after it in its clause, else the
    nearest one before it; otherwise the sentence decides (India only -> INDIA; India and another -> AMBIGUOUS)."""
    after = clause[b:b + 80]
    cut = _AFTER_CUT.search(after)
    marks = _jurisdiction_marks(after[:cut.start()] if cut else after)
    if marks:
        return marks[0][1]
    marks = _jurisdiction_marks(clause[max(0, a - 90):a])
    if marks:
        return marks[-1][1]
    kinds = {k for _, k in _jurisdiction_marks(sentence)}
    if kinds == {'INDIA'}:
        return 'INDIA'
    if 'INDIA' in kinds:
        return 'AMBIGUOUS'
    return 'OTHER' if kinds else 'UNSPECIFIED'
