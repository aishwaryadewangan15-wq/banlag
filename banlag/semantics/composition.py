"""Composition state: which ingredients a text asserts are in (or out of) the target formulation."""

import re
from ..claims import (OTHER_MARK, _ADDITION, _OTHER_PRODUCT, _VARIABILITY, _allowed_word, _canon_set, _classify_items,
    _np_after, _np_items, composition_issues, split_sentences, strip_parentheticals)
from ..legal import find_mentions
from .patterns import (ADDITIVE_MARK, DIFFERENT, EXACT, EXCIPIENT, HOLDER_ANAPHOR, NOT_ESTABLISHED, ORDINAL_COUNT,
    P_ADDS, P_CONTAINING, P_EXIST, P_HAS_AS, P_HAS_TOO, P_IMPLICIT, P_LOADED, P_PASSIVE, P_ROLE, P_VERB, SETREF,
    UNRESOLVED, _CLAUSES, _CNT, _MEMBER_NEG, _ORD, _OTHER_INTRO, _REL_CUT)


def _clause_spans(text):
    spans, last = [], 0
    for m in _CLAUSES.finditer(text):
        spans.append((last, m.start()))
        last = m.end()
    spans.append((last, len(text)))
    return [(s, e) for s, e in spans if text[s:e].strip()]
def _holder_kind(holder, focus, component_label=False):
    """FOCUS / ANAPHOR / IMPLICIT / COMPONENT / OTHER for the noun phrase that holds a membership assertion."""
    h = (holder or '').strip(' ,;:')
    words = re.findall(r"[A-Za-z][\w'-]*", h)
    names = _canon_set(h)
    if names:
        if focus and names == set(focus):
            return 'FOCUS'
        if focus and names < set(focus):
            return 'COMPONENT'
        return 'OTHER'
    if OTHER_MARK.search(h) or _OTHER_PRODUCT.search(h):
        return 'OTHER'
    if HOLDER_ANAPHOR.search(h) or SETREF.search(h):
        return 'COMPONENT' if component_label else 'ANAPHOR'
    content = [w for w in words if not _allowed_word(w) and w.lower() not in ('additionally', 'also', 'further', 'same', 'each', 'every')]
    if not content:
        return 'COMPONENT' if component_label else 'IMPLICIT'
    return 'OTHER'
def _items(text, focus):
    """(unknown, extra_known, count_issue) named in an object / subject phrase of a membership assertion."""
    text = (text or '').strip().replace(':', ',')  # 'a fourth active ingredient: omeprazole' -> two noun phrases
    cut = _REL_CUT.search(text)
    head = text[:cut.start()] if cut else text
    main, _ = strip_parentheticals(head)
    unknown, extra = [], []
    setref = SETREF.search(main)
    if setref:  # 'the three above plus rifaximin': the set reference stands for the focus; read what is added to it
        rest = main[setref.end():]
        m = _ADDITION.match(rest)
        if m and m.end() > 0:
            u, x = _classify_items(_np_items(_np_after(rest[m.end():])), focus)
            unknown += u
            extra += x
        main = main[:setref.start()]
    names = _canon_set(main)
    if names:
        extra += sorted(names - set(focus or names))
        ci = composition_issues(main, focus or names)
        unknown += ci['unknown']
        extra += ci['extra_known']
    elif main.strip():
        for seg in main.split(','):  # each comma segment is its own noun phrase ('a fourth component, omeprazole')
            words = [w for w in _np_after(seg) if w != '|']
            cleaned = [w for w in words if w.lower() not in _ORD and w.lower() not in _CNT and w.lower() not in
                       ('another', 'additional', 'extra', 'further', 'other', 'more', 'same', 'its', 'their', 'his', 'her', 'also')]
            u, x = _classify_items(_np_items(cleaned), focus)
            unknown += u
            extra += x
    return unknown, sorted(set(extra))
def _count_effect(text, n):
    """DIFFERENT if an ordinal/count/'another' says the holder has more actives than n; UNRESOLVED if fewer."""
    for m in ORDINAL_COUNT.finditer(text or ''):
        o, c = (m.group('ord') or '').lower(), (m.group('cnt') or '').lower()
        k = _ORD.get(o) or (int(o[0]) if o[:1].isdigit() else None)
        if k:
            if k > n:
                return DIFFERENT, m.group(0)
            continue
        cnt = _CNT.get(c) or (int(c) if c.isdigit() else None)
        if cnt is not None and n:
            if cnt > n:
                return DIFFERENT, m.group(0)
            if cnt < n:
                return UNRESOLVED, m.group(0)
    if ADDITIVE_MARK.search(text or ''):
        return DIFFERENT, ADDITIVE_MARK.search(text).group(0)
    return None, None
def membership_assertions(clause, focus, component_label=False):
    """Membership assertions in one clause: [{'holder','holder_kind','unknown','extra','count','negated','variable','marker'}]."""
    out = []
    text, asides = strip_parentheticals(clause)
    pieces = [(text, None)] + [(a, 'IMPLICIT') for a in asides if re.search(r'\b(?:contain|include|ingredient|component|active|plus|also)', a, re.I)]
    n = len(focus or ())
    for piece, forced in pieces:
        for rx, kind in ((P_HAS_AS, 'HAS_AS'), (P_ROLE, 'ROLE'), (P_ADDS, 'ADDS'), (P_EXIST, 'EXIST'), (P_VERB, 'VERB'), (P_CONTAINING, 'VERB'),
                         (P_LOADED, 'VERB'), (P_HAS_TOO, 'HAS_TOO'), (P_PASSIVE, 'PASSIVE'), (P_IMPLICIT, 'IMPLICIT')):
            m = rx.match(piece)
            if not m:
                continue
            g = m.groupdict()
            holder = g.get('holder') if kind != 'IMPLICIT' else ''
            if kind == 'ROLE':
                holder = (g.get('holder') or '') + ' ' + (g.get('det') or '')
            if kind == 'ADDS':  # the formulation the items are added to decides the holder ('adds X to the three')
                if _holder_kind(g.get('target'), focus, component_label) not in ('FOCUS', 'ANAPHOR'):
                    continue
                holder = g.get('target')
            hk = forced or _holder_kind(holder, focus, component_label)
            if kind in ('VERB', 'HAS_TOO') and hk == 'IMPLICIT':
                continue  # a bare '... contains ...' with no holder is not about a formulation
            items_text = g.get('obj') if kind in ('VERB', 'HAS_TOO') else g.get('items')
            neg = bool(g.get('neg'))
            if kind == 'HAS_AS' and _MEMBER_NEG.search(piece[:m.start('items')]):
                neg = True  # 'it does not have X as an ingredient'
            if kind == 'VERB' and (re.match(r'\s*(?:no|none\s+of)\b', items_text or '', re.I) or _MEMBER_NEG.search(holder or '')):
                neg = True  # 'it contains no X', 'it never contains X'
            unknown, extra = _items(items_text, focus)
            object_names = _object_names(items_text)
            effect, marker = _count_effect(piece, n)
            if kind == 'PASSIVE' and not (unknown or extra or (neg and object_names)) and effect is None:
                continue  # 'X is in India', 'it is part of the treatment': nothing composition-bearing was parsed
            out.append({'kind': kind, 'holder': (holder or '').strip(), 'holder_kind': hk, 'unknown': unknown, 'extra': extra,
                        'object_names': object_names,
                        'count': effect, 'marker': marker, 'negated': neg, 'excipient': bool(EXCIPIENT.search(piece)),
                        'variable': bool(_VARIABILITY.search(piece)),
                        'additive': bool(g.get('add') or g.get('add2') or re.search(r'\b(?:also|additionally|too|as\s+well|plus|another|extra|additional)\b', piece, re.I)),
                        'text': piece.strip()})
            break
    return out
def _object_names(items_text):
    """Recognised ingredient names in the parsed object of a membership assertion only (never the holder or the rest of the
    sentence): 'X, Y and Z does not contain omeprazole' -> {} ; 'it does not contain paracetamol' -> {'paracetamol'}."""
    main = strip_parentheticals((items_text or '').replace(':', ','))[0]
    cut = _REL_CUT.search(main)
    return sorted(_canon_set(main[:cut.start()] if cut else main))
def _introduces_other(sentence, focus):
    main, _ = strip_parentheticals(sentence)
    names = _canon_set(main)
    if names and focus and not names <= set(focus):
        return True
    return bool(OTHER_MARK.search(main) or _OTHER_INTRO.search(main))
def composition_state(sentences, focus, lead_index=0, labels=None):
    """Composition verdict for the focus formulation over a sequence of sentences (one text unit).
    sentences: [str]; focus: the focus ingredient set; lead_index: index of the sentence that established the focus (its
    own composition is judged by claims.composition_issues). labels: optional per-sentence component-label flags."""
    focus = set(focus or ())
    unknown, extra, missing, assertions, blockers = [], [], [], [], []
    verdict = EXACT
    others_since_focus = False
    labels = labels or [False] * len(sentences)

    def worsen(v):
        nonlocal verdict
        if v == DIFFERENT or verdict == DIFFERENT:
            verdict = DIFFERENT
        elif v == UNRESOLVED:
            verdict = UNRESOLVED

    for i, s in enumerate(sentences):
        # Every clause is assessed: BEFORE, WITHIN and AFTER the sentence that names the focus. Punctuation and order grant no
        # exception ('X are used …; the tablet does not contain paracetamol', 'It does not contain paracetamol. X is …').
        # The lead's own ingredient list cannot read as an addition: its names ARE the focus.
        pre_lead = i < lead_index
        main, _ = strip_parentheticals(s)
        names = _canon_set(main)
        if names and names == focus:
            others_since_focus = False  # the focus is named again: pronouns resolve to it
        for cs, ce in _clause_spans(s):
            clause = s[cs:ce]
            found = membership_assertions(clause, focus, labels[i])
            if not found and not labels[i]:
                # Count semantics need no membership verb: '<it / its / the tablet> ... a third active / its fourth ingredient'
                # states more actives than the focus has, whatever the verb.
                cm = strip_parentheticals(clause)[0]
                effect, marker = _count_effect(cm, len(focus))
                if effect and HOLDER_ANAPHOR.search(cm) and not (OTHER_MARK.search(cm) or _OTHER_PRODUCT.search(cm)) \
                        and not _MEMBER_NEG.search(cm[:max(0, cm.lower().find(marker.lower()))]):
                    if others_since_focus or pre_lead:
                        effect = UNRESOLVED
                    assertions.append({'kind': 'COUNT', 'text': clause.strip(), 'sentence_index': i, 'holder_kind': 'ANAPHOR', 'unknown': [],
                                       'extra': [], 'effect': effect, 'marker': marker})
                    worsen(effect)
                    blockers.append(f'sentence {i}: {marker} ({clause.strip()})')
            for a in found:
                if a['holder_kind'] in ('OTHER', 'COMPONENT') or a['excipient']:
                    continue
                rec = dict(a, sentence_index=i)
                # Negated membership is examined BEFORE the additions-only shortcut, against the parsed object only:
                # 'it does not contain paracetamol' denies a focus active (the formulation is not the target);
                # 'X, Y and Z does not contain omeprazole' / 'it contains no omeprazole' deny a non-member and change nothing.
                # A pronoun / implicit holder before the focus is named has no antecedent yet: material -> UNRESOLVED.
                unattached = a['holder_kind'] in ('ANAPHOR', 'IMPLICIT') and (others_since_focus or pre_lead)
                if a['negated']:
                    denied = set(a.get('object_names') or ()) & focus
                    if denied:
                        effect = UNRESOLVED if unattached else DIFFERENT
                        rec.update(effect=effect, missing=sorted(denied))
                        if effect == DIFFERENT:
                            missing += sorted(denied)
                        worsen(effect)
                        blockers.append(f"sentence {i}: a focus ingredient is stated as absent ({', '.join(sorted(denied))}: {a['text']})")
                        assertions.append(rec)
                    continue
                adds = a['unknown'] or a['extra'] or a['count'] or (a['additive'] and a['kind'] in ('HAS_AS', 'IMPLICIT', 'ROLE', 'ADDS', 'EXIST'))
                if not adds:
                    continue
                if unattached:
                    rec['effect'] = UNRESOLVED
                    worsen(UNRESOLVED)
                    blockers.append(f"sentence {i}: composition assertion whose holder " + ('comes before the formulation is named'
                                    if pre_lead else 'has two plausible antecedents') + f" ({a['text']})")
                    assertions.append(rec)
                    continue
                if a['variable']:
                    rec['effect'] = UNRESOLVED
                    worsen(UNRESOLVED)
                    blockers.append(f"sentence {i}: optional / variable composition ({a['text']})")
                    assertions.append(rec)
                    continue
                effect = a['count'] or (DIFFERENT if (a['unknown'] or a['extra'] or a['additive']) else None)
                if a['count'] == UNRESOLVED and not (a['unknown'] or a['extra']):
                    effect = UNRESOLVED
                if a['kind'] == 'HAS_TOO' and not a['extra'] and a['count'] != DIFFERENT:
                    effect = UNRESOLVED  # 'it has X too': X may be a property, not an active -> cannot keep exactness, cannot assert B
                rec['effect'] = effect
                if effect == DIFFERENT:  # only a definite difference names components; UNRESOLVED stays an abstention
                    unknown += a['unknown']
                    extra += a['extra']
                worsen(effect)
                blockers.append(f"sentence {i}: {a['text']}")
                assertions.append(rec)
        if _introduces_other(s, focus):
            others_since_focus = True
    return {'verdict': verdict, 'focus': sorted(focus), 'extra_known': sorted(set(extra)), 'unknown': unknown,
            'missing': sorted(set(missing)), 'assertions': assertions, 'blockers': blockers}
def _difference_markers(st):
    """Readable markers for a DIFFERENT verdict that named no extra component (missing active, count, 'another active')."""
    if st['verdict'] != DIFFERENT or st['unknown'] or st['extra_known']:
        return []
    if st.get('missing'):
        return ['(stated as absent: ' + ', '.join(st['missing']) + ')']
    return ['(an additional active ingredient is stated: ' + '; '.join(a.get('marker') or a['text'] for a in st['assertions']
                                                                      if a.get('effect') == DIFFERENT)[:120] + ')']
def _worst(*verdicts):
    vs = [v for v in verdicts if v]
    return DIFFERENT if DIFFERENT in vs else UNRESOLVED if UNRESOLVED in vs else EXACT
def answer_composition(blocks, hint=None):
    """Answer adapter: the subject is the set named by the lead sentence (first sentence naming ingredients), widened by
    what the lead itself adds, then checked against every later sentence and block (one composition state per answer).

    hint: the target set of a separately asked status question. A hint may resolve WHAT an answer is about when the answer
    names nothing, but it is never confirmation of composition: every answer sentence - including sentences before an
    explicit restriction - is checked against the hinted target ('This formulation also contains omeprazole. This
    combination is prohibited in India.' -> DIFFERENT). Returns None when there is neither a named subject nor a hint."""
    sents, labels, lead_i, lead = [], [], None, None
    for b in blocks:
        if b.get('type') == 'heading':
            continue
        label = (b.get('label') or '').strip()
        comp_label = bool(_canon_set(strip_parentheticals(label)[0]))
        for s in split_sentences(b.get('text') or ''):
            sents.append(s)
            labels.append(comp_label)
            if lead is None:
                main, _ = strip_parentheticals(s)
                names = _canon_set(main)
                if names:
                    ci = composition_issues(s)
                    lead = {'names': names, 'sentence': s, 'classes': {m['canonical']: m['class'] for m in find_mentions(main)},
                            'extra': set(ci['extra_known']), 'unknown': list(ci['unknown'])}
                    lead_i = len(sents) - 1
    hint = set(hint) if hint else None
    hst = composition_state(sents, hint, -1, labels) if hint else None  # every sentence against the hinted target
    if lead is None:
        if not hint:
            return None
        return {'subject': hint | set(hst['extra_known']), 'lead': None, 'classes': {}, 'unknown': hst['unknown'] + _difference_markers(hst),
                'verdict': hst['verdict'], 'blockers': hst['blockers'], 'assertions': hst['assertions'], 'source': 'QUERY_HINT'}
    focus = lead['names'] | lead['extra']
    st = composition_state(sents, focus, lead_i, labels)
    unknown = list(dict.fromkeys(lead['unknown'] + st['unknown'] + _difference_markers(st)))  # lead clauses may be read twice
    verdict = DIFFERENT if (lead['extra'] or lead['unknown']) else st['verdict']
    blockers, assertions, extra = list(st['blockers']), list(st['assertions']), set(st['extra_known'])
    if hst is not None and lead['names'] == hint:  # status answer that names the target: sentences before the lead count too
        verdict = _worst(verdict, hst['verdict'])
        unknown += [u for u in hst['unknown'] + _difference_markers(hst) if u not in unknown]
        blockers += [b for b in hst['blockers'] if b not in blockers]
        assertions += hst['assertions']
        extra |= set(hst['extra_known'])
    return {'subject': focus | extra, 'lead': lead['sentence'], 'classes': lead['classes'], 'unknown': unknown,
            'verdict': verdict, 'blockers': blockers, 'assertions': assertions, 'source': 'LEAD_SENTENCE'}
def text_composition(text, target):
    """Composition state of one text unit (organic snippet, page snapshot, citation snippet) for a known target set:
    the focus is established by the first sentence that names exactly the target, and every clause of the text - before,
    within and after that sentence - is assessed by composition_state. A text that never names the target is NOT_ESTABLISHED
    (missing evidence of the formulation is never treated as proof of exactness)."""
    sents = split_sentences(text or '')
    target = set(target)
    lead = next((i for i, s in enumerate(sents) if _canon_set(strip_parentheticals(s)[0]) == target), None)
    if lead is None:
        return {'verdict': NOT_ESTABLISHED, 'focus': sorted(target), 'extra_known': [], 'unknown': [], 'missing': [], 'assertions': [],
                'blockers': ['no sentence names exactly the target formulation'], 'lead_index': None}
    st = composition_state(sents, target, lead_index=lead)
    st['lead_index'] = lead
    return st
