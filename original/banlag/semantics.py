"""Shared semantic core: ONE formulation entity per text unit, ONE legal event per restriction predicate.

Every promotion path reads composition and restriction facts from here: the answer label (D, and E via exactness),
organic Tier 2, cited-snapshot Tier 3, citation metadata views, the status capture, the UI highlight and the
publication gate. Source-specific adapters (claims.analyze_surface, restriction_assessment, citations) keep their own
completeness/truncation semantics and feed the same gates.

Supported input contract (bounded on purpose; outside it the result is UNRESOLVED / not qualifying, never a promotion):

Composition. The focus formulation is the set named by the first sentence that names one (answers), or the target set
where a sentence names it exactly (organic text, page snapshots, snippets). Later sentences change it only through a
membership assertion about it: '<holder> contains / includes / comprises / consists of / is made|formulated with X',
'<holder> has X as (another|its fourth|an additional) (active) ingredient', 'X is (also) in / part of / an ingredient of
<holder>', 'X is included / added' (implicit holder), '<holder's> (fourth|other) (active) ingredient is X', 'the three
above plus X', and ordinal or counted ingredients ('its fourth active ingredient', 'four active ingredients'). The holder
must resolve to the focus: the exact target set, 'it / its / this / the medicine|formulation|tablet|combination|...',
or an implicit passive. Another product, another named drug, a component-labelled bullet, negated membership,
excipients, strengths and food never add to the focus. A holder with two plausible antecedents -> UNRESOLVED.
Verdicts: SUPPORTED_EXACT (no known contradiction in this text - NOT proof of a real product's composition),
DIFFERENT (a stated extra or missing active), UNRESOLVED (antecedent, count or modality cannot be attached safely).

Legal events. One event per restriction predicate, bound to the entity of its own clause (passive subject, active
object, 'ban on X', an anaphor, another named subject, or inheritance from an earlier clause of the same sentence),
with polarity (AFFIRMED / NEGATED / DENIED / REPORTED), condition, proposal, dates (as of the evidence year) and
jurisdiction from that clause. Revocations are events too: they apply only to restrictions on the same entity (the
'ban on X' object, the restrictions of their own sentence, or the most recent restriction for 'that ban' / 'it'), and
a later affirmative restriction on that entity is a reinstatement. An 'earlier / 2016 ban' revocation never cancels a
present-tense current restriction.

Promotion invariant: a definitive D / T2 / T3 needs ONE event that is target-bound, affirmed, unconditional, not
proposed, current, Indian and not revoked, AND a SUPPORTED_EXACT composition for that text. Provenance (HMAC seal,
Indian government host) is orthogonal and never repairs a failed attribute; a host only supplies jurisdiction to an
otherwise unqualified, target-bound statement.
"""
import re

from .claims import (ANAPHORA, CONDITIONAL, CURRENT_YEAR, EARLIER_RESTRICTION, GENERIC_MARK, HEDGE, HIST_RESTRICT, INDIA,
                     INDIAN_GOV_HOST, NEGATED, OTHER_JURIS, OTHER_MARK, PRONOUN_REVERSAL, PROPOSED, PROPOSED_FUTURE, RESTRICT,
                     REVOKED, REVOKED_SENTENCE, _ADDITION, _OTHER_PRODUCT, _TIME, _VARIABILITY, _allowed_word, _canon_set,
                     _classify_items, _jurisdiction_marks, _np_after, _np_items, _predicate_jurisdiction, composition_issues,
                     list_truncated, notice_numbers, split_sentences, strip_parentheticals)
from .legal import find_mentions

EXACT, DIFFERENT, UNRESOLVED = 'SUPPORTED_EXACT', 'DIFFERENT', 'UNRESOLVED'
NOT_ESTABLISHED = 'NOT_ESTABLISHED'  # an evidence text that never names the target formulation (never a pass)
TARGET_BINDINGS = ('EXPLICIT_EXACT', 'SUBJECT_ANAPHORA')

# ----------------------------------------------------------------------------------------------------------------------
# Composition
# ----------------------------------------------------------------------------------------------------------------------
_ORD = {'second': 2, 'third': 3, 'fourth': 4, 'fifth': 5, 'sixth': 6, 'seventh': 7, 'eighth': 8, '2nd': 2, '3rd': 3, '4th': 4,
        '5th': 5, '6th': 6}
_CNT = {'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6, 'seven': 7, 'eight': 8}
_COMP_NOUN = (r'(?:active\s+)?(?:ingredients?|components?|constituents?|actives|active\s+(?:drugs?|substances?|agents?)|drugs?|medicines?'
              r'|active(?=\s*(?:[,:;.)]|$)))')
ORDINAL_COUNT = re.compile(r'\b(?:(?P<ord>second|third|fourth|fifth|sixth|seventh|eighth|[2-6](?:nd|rd|th))|(?P<cnt>one|two|three|four|five|six|seven|'
                           r'eight|[1-8]))[\s-]+(?:(?:additional|extra|other|more|separate|different|distinct)\s+)?' + _COMP_NOUN + r'\b', re.I)
ADDITIVE_MARK = re.compile(r'\b(?:another|an\s+additional|additional|an\s+extra|extra|one\s+more|a\s+further|further)\s+(?:active\s+)?'
                           r'(?:ingredient|component|constituent|active|drug|medicine|substance|agent)s?\b', re.I)
EXCIPIENT = re.compile(r'\b(?:excipients?|inactive|fillers?|binders?|coating|flavou?r\w*|colou?r(?:ant|ing)s?|preservatives?|sweeteners?|'
                       r'base|vehicle|carrier|lubricants?|disintegrants?)\b', re.I)
_HOLDER_NOUN = (r'(?:medicine|medication|formulation|combination|combo|product|tablet|capsule|pill|preparation|fdc|drug|blend|mixture|'
                r'dose|strip|syrup|suspension|brand)')
HOLDER_ANAPHOR = re.compile(r'\b(?:it|its|they|their|them|this|these|' r'(?:the|this|that|said|same|each|every|one|its|their)\s+(?:same\s+)?'
                            r'(?:[\w-]+\s+){0,2}?' + _HOLDER_NOUN + r's?)\b', re.I)
SETREF = re.compile(r'\b(?:the|these|those|all|its|their)\s+(?:(?:three|two|four|\d+)\s+)?(?:above|aforementioned|mentioned|listed|named|'
                    r'ingredients?|components?|drugs?|actives|medicines?)\b(?:\s+(?:above|mentioned|listed|named))?'
                    r'|\b(?:the|these|those|all)\s+(?:three|two|four)\b', re.I)
_MEMBER_NEG = re.compile(r"\b(?:not|never|no|n['’]t|without|free\s+of|free\s+from)\b", re.I)
# '<holder> [also] contains X' (finite verbs; 'containing' only after a holder noun, never bare 'including').
P_VERB = re.compile(r'^(?P<holder>.*?)\b(?P<add>(?:also|additionally|further|too)\s+)?(?P<neg>(?:does|do|did)\s+not\s+|doesn[\'’]t\s+|don[\'’]t\s+)?'
                    r'(?P<verb>contains?|comprises?|consists?\s+of|includes?|holds?|incorporates?|'
                    r'(?:is|are)\s+(?:also\s+|additionally\s+)?(?:made|formulated|compounded|prepared)\s+(?:with|from|using)|'
                    r'(?:is|are)\s+(?:also\s+)?combined\s+with|'
                    # a strength statement is a membership statement: 'each tablet carries / has 20 mg of X'
                    r'(?:has|have|carries|carry|delivers|deliver|packs|provides|provide)(?=\s+(?:about\s+|around\s+)?\d+(?:\.\d+)?\s*(?:mg|mcg|g|ml|iu)\b))\b'
                    r'(?P<obj>.*)$', re.I)
# '<holder> adds X to <the three / it / the combination>'
P_ADDS = re.compile(r'^(?P<holder>.*?)\b(?:adds?|added)\s+(?P<items>.+?)\s+(?:to|into)\s+(?P<target>.+)$', re.I)
# 'There is (also) X in <holder>'
P_EXIST = re.compile(r'^(?P<pre>.*?)\bthere\s+(?:is|are)\s+(?P<add>(?:also|additionally)\s+)?(?P<items>.+?)\s+(?:in|inside|within)\s+(?P<holder>.+)$', re.I)
# '<holder> has X too / as well': additive possession; X may be a property rather than an ingredient -> UNRESOLVED
P_HAS_TOO = re.compile(r'^(?P<holder>.*?)\b(?:also\s+)?(?:has|have)\s+(?P<obj>.+?)\s+(?:too|as\s+well)\s*[.!]?\s*$', re.I)
P_CONTAINING = re.compile(r'^(?P<holder>.*?\b' + _HOLDER_NOUN + r's?)\s+(?P<add>(?:also|additionally)\s+)?containing\b(?P<obj>.*)$', re.I)
# '<holder> has X as (another / its fourth / an additional) (active) ingredient'
P_HAS_AS = re.compile(r'^(?P<holder>.*?)\b(?:has|have|having|uses?|with)\s+(?P<items>.+?)\s+as\s+(?:its|an?|another|the|their|one\s+of\s+its)?\s*'
                      r'(?:(?P<ord>\w+)\s+)?(?:(?:additional|extra|other|further)\s+)?(?:active\s+)?(?:ingredient|component|constituent|active)s?\b', re.I)
# 'X is (also) in / part of / an ingredient of <holder>'; 'X is (also) included / added' (implicit holder)
P_PASSIVE = re.compile(r'^(?P<items>.*?)\b(?:is|are)\s+(?P<add>(?:also|additionally|further)\s+)?(?P<neg>not\s+|never\s+)?(?P<add2>(?:also|additionally)\s+)?'
                       r'(?:(?:present|found|included|contained|added|incorporated|blended|mixed)\s+(?:in|into|to|within|with)|in|inside|within|'
                       r'part\s+of|(?:an?|another|the|one)\s+(?:(?:\w+)\s+)?(?:active\s+)?(?:ingredient|component|constituent)s?\s+(?:of|in))\s+(?P<holder>.*)$', re.I)
P_LOADED = re.compile(r'^(?P<holder>.*?)\b(?:is|are)\s+(?P<add>(?:also|additionally)\s+)?(?:loaded|fortified|enriched|mixed|blended|combined|'
                      r'co-?formulated|supplemented)\s+with\s+(?P<obj>.+)$', re.I)
P_IMPLICIT = re.compile(r'^(?P<items>.*?)\b(?:is|are)\s+(?P<add>(?:also|additionally)\s+)?(?:included|added|incorporated|present)\s*[.!]?\s*$', re.I)
# '<det> (fourth|other) (active) ingredient(s) is/are X'
P_ROLE = re.compile(r'^(?P<holder>.*?)\b(?P<det>its|their|the|this|that)\s+(?:(?P<ord>\w+)\s+)?(?:(?:additional|extra|other|remaining|full|complete|exact)\s+)?'
                    r'(?:active\s+)?(?:ingredients?|components?|constituents?|actives|composition|formula)\s+(?:is|are|include|includes|comprise|comprises|'
                    r'consist\s+of)\s+(?P<items>.+)$', re.I)
_REL_CUT = re.compile(r'\b(?:which|that|who|whom|whose|where|because|so\s+that|to\s+(?:treat|relieve|help|reduce|provide)|for\s+(?:the|treating|relief))\b', re.I)
_CLAUSES = re.compile(r';|,?\s+\b(?:but|however|whereas|although|though|while|whilst)\b', re.I)
_OTHER_INTRO = re.compile(r'^\s*(?:[A-Z][\w-]+(?:\s+[A-Za-z][\w-]+)?)\s+(?:is|are|was|were)\s+(?:a|an|the|also\s+a)\s+(?:[\w-]+\s+){0,3}?'
                          r'(?:medicine|drug|medication|product|tablet|antacid|antibiotic|inhibitor|ppi|supplement|treatment)\b')


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


# ----------------------------------------------------------------------------------------------------------------------
# Legal events
# ----------------------------------------------------------------------------------------------------------------------
_REVOKE = re.compile(r'\b(?:revok\w*|rescind\w*|lift(?:ed|s|ing)?|quash\w*|stay(?:ed|s)?|set\s+aside|struck\s+down|strike\s+down|overturn\w*|repeal\w*|'
                     r'cancel+(?:ed|led|s)?|reversed|invalidated|withdr[ae]wn?)\b', re.I)
_AUX = re.compile(r'\b(?:is|are|was|were|be|been|being|remains?|remained|stays?|stayed|got|gets|become|became)\b', re.I)
_NEG_WORD = re.compile(r"^(?:not|never|neither|nor|cannot|no|none|nobody|nothing|\w+n['’]t)$", re.I)
_NEG_STOP = {'because', 'since', 'as', 'after', 'which', 'that', 'who', 'so', 'and', 'but', 'although', 'though', 'while', 'whereas',
             'if', 'when', 'unless', 'whether'}
_TOK = re.compile(r"[A-Za-z]+(?:['’][A-Za-z]+)?|[,;:]")
DENIAL = re.compile(r"\b(?:not|never|no|n['’]t)\b[^.;]{0,40}?\b(?:true|correct|accurate|case|right|so|evidence|proof|record|basis|truth)\s+(?:that|whether|of)\b"
                    r"|\b(?:den(?:y|ies|ied|ying)|refut\w*|reject(?:s|ed|ing)?|disput\w*|dismiss(?:es|ed|ing)?|rebut\w*|contradict(?:s|ed|ing)?)\b"
                    r"|\b(?:false|untrue|incorrect|inaccurate|wrong|a\s+myth|misconception|misinformation|baseless|unfounded|hoax|fake)\b[^.;]{0,20}?\b(?:that|to\s+(?:say|claim))\b"
                    r"|\bcontrary\s+to\s+(?:claims?|reports?|rumou?rs?|popular\s+belief)", re.I)
# 'Reports / claims that <restriction> are false': the restriction is the content of a report that is then denied.
REPORT_THAT = re.compile(r"\b(?:reports?|claims?|suggestions?|rumou?rs?|statements?|news|posts?|idea|notion|belief|assertions?)\s+that\b", re.I)
FALSITY_AFTER = re.compile(r"\b(?:is|are|was|were|has\s+been|have\s+been)\s+(?:\w+\s+)?(?:false|untrue|incorrect|wrong|baseless|unfounded|misleading|"
                           r"inaccurate|a\s+myth|fake|denied|refuted|debunked)\b", re.I)
REPORTED = re.compile(r"\b(?:uncorroborated|unsubstantiated|unofficial|anecdotal|unconfirmed|unverified|alleged(?:ly)?|purported(?:ly)?|rumou?r\w*|speculat\w*)\b"
                      r"|\b(?:reports?|rumou?rs?|claims?|posts?|articles?|sources?|people|users|some|many|others)\s+(?:\w+\s+)?"
                      r"(?:say|says|said|claim\w*|suggest\w*|allege\w*|stated?|states|indicated?|indicates)\b"
                      r"|\b(?:some|unnamed|anonymous|social[\s-]+media|online|media)\s+(?:\w+\s+)?(?:say|says|claim\w*|report\w*|post\w*|sources?)\b"
                      r"|\b(?:it\s+is|it['’]s)\s+(?:said|claimed|rumou?red|alleged|reported|believed|thought)\s+that\b"
                      r"|\b(?:claims?|alleges?|suggests?)\s+that\b"
                      r"|\baccording\s+to\s+(?!(?:the\s+)?(?:gazette|notification|government|central|ministry|mohfw|cdsco|dcgi|dtab|section|official|law|"
                      r"act|rules|order|india|indian|drugs\s+and\s+cosmetics|s\.\s?o\.?|notice))", re.I)
PROVISO_AFTER = re.compile(r"\b(?:if(?!\s+(?:you|your|a\s+patient|patients?|someone|anyone|one|we|i)\b)|unless|provided|providing|on\s+(?:the\s+)?condition|subject\s+to(?!\s+(?:a|an|the|this|its)?\s*(?:ban|prohibition|restriction))|"
                           r"only\s+(?:if|when|where|for|in)|in\s+case|except|depending\s+on|conditional|where\s+(?:applicable|appropriate|clinically|medically|"
                           r"necessary|required)|when\s+(?:used|sold|combined|taken|given|prescribed|marketed|formulated|administered))\b", re.I)
# A restriction limited to a population or age group is not the notice's unconditional ban ('for human use' is the notice's
# own scope and stays affirmative).
SCOPE_LIMIT = re.compile(r"\b(?:for|in|among|to)\s+(?:use\s+in\s+)?(?:children|kids|infants|minors|adolescents|adults|the\s+elderly|elderly|"
                         r"pregnant|women|men|paediatric|pediatric|geriatric|(?:patients|people|persons|those)\s+(?:with|under|over|below|above|aged))\b"
                         r"|\b(?:under|below|above|over)\s+(?:the\s+)?age\b|\b(?:under|below|over|above)\s+\d+\s*(?:years?)?\b|\baged\s+\d+"
                         r"|\bfor\s+(?!human\b)[\w-]+\s+use\b|\b(?:use|uses|purposes?)\s+only\b", re.I)
# 'The ban covers / applies to <X>': a later statement of what a restriction is about. If X is another entity, the
# restriction it refers to is not shown to be about the exact formulation.
BAN_SCOPE = re.compile(r'\b(?:the|this|that|its|such\s+a)\s+(?:ban|prohibition|notification|restriction|order)\s+(?:only\s+)?'
                       r'(?:covers?|applies\s+(?:only\s+)?to|concerns?|relates\s+to|is\s+(?:about|for|limited\s+to)|targets?|extends\s+to)\s+(?P<obj>.+)', re.I)
IF_BEFORE = re.compile(r"\bif\s+(?!you\b|your\b|a\s+patient|patients?\b|someone|anyone|one\b|we\b|i\b)", re.I)
_ENTITY_STOP = set('''manufacture manufacturing sale sales sell selling distribution distribute import imports export exports marketing
production stocking stock use usage human humans consumption prescription prescribing government governments authority authorities regulator
regulators regulatory court courts tribunal ministry department health family welfare drug drugs controller general board committee
parliament cabinet central state union notification notifications gazette section act rule rules order orders law laws ban bans prohibition
prohibitions restriction restrictions country countries market markets nation nationwide officials official cdsco dcgi dtab mohfw fda ema mhra
who regulators agency agencies supreme high delhi bench judge judges also now again currently presently still already officially formally legally
completely totally fully entirely partially immediately effectively hereby further therefore january february march april may june
july august september october november december jan feb mar apr jun jul aug sep sept oct nov dec'''.split())


def _neg_before(prefix):
    toks = _TOK.findall(prefix)
    n = 0
    for i in range(len(toks) - 1, -1, -1):
        t = toks[i].lower()
        if t in (',', ';', ':') or t in _NEG_STOP:
            return False
        n += 1
        if n > 6:
            return False
        if t == 'longer' and i and toks[i - 1].lower() == 'no':
            return True
        if _NEG_WORD.match(t) and not (t == 'not' and i + 1 < len(toks) and toks[i + 1].lower() == 'only'):
            return True
    return False


def _content_words(text):
    """Words that could name an entity: not function/legal/jurisdiction vocabulary, places or verbs."""
    t = INDIA.sub(' ', OTHER_JURIS.sub(' ', text))
    t = re.sub(r"\b(?i:in|across|throughout|within|by|from)\s+(?:the\s+)?[A-Z][\w.&'-]*(?:\s+[A-Z][\w.&'-]*)*", ' ', t)
    words = re.findall(r"[A-Za-z][\w'-]*", t)
    return [w for w in words if not _allowed_word(w) and w.lower() not in _ENTITY_STOP and not RESTRICT.fullmatch(w)
            and not _REVOKE.fullmatch(w) and not re.fullmatch(r'(?i)(?:has|have|had|does|did|do|will|shall|been|got|it|its|ever|yet|'
                                                              r'reportedly|allegedly|subsequently|later|since|once|earlier|recently)', w)]


def _entity(region, focus, sentence_names_ok=True, named_only=False):
    """(entity, binding) for the text that names what a predicate governs. named_only: only explicit ingredient names,
    'another product' marks and anaphors count (for the agent side of an active verb / the adjunct side of a passive)."""
    main, _ = strip_parentheticals(region)
    names = _canon_set(main)
    if names:
        if focus and names == set(focus):
            return ('TARGET', 'EXPLICIT_EXACT') if sentence_names_ok else ('OTHER', 'OTHER_ENTITY')
        if focus and names < set(focus):
            return ('TARGET', 'SUBJECT_ANAPHORA') if ANAPHORA.search(main) else ('COMPONENT', 'COMPONENT_ONLY')
        return 'OTHER', 'OTHER_ENTITY'
    if OTHER_MARK.search(main) or re.search(r'\b(?:versions?|variants?)\b', main, re.I):
        return 'OTHER', 'OTHER_ENTITY'
    if focus and ANAPHORA.search(main):
        return 'TARGET', 'SUBJECT_ANAPHORA'
    if named_only:
        return None, None
    if GENERIC_MARK.search(main):
        return 'GENERIC', 'GENERIC'
    if _content_words(main):
        return 'OTHER', 'OTHER_ENTITY'
    return None, None


def _event_entity(sentence, clause, cs, pred_start, pred_end, prev_end, focus, composition_ok):
    """Bind one restriction predicate to the entity of its own clause."""
    a, b = pred_start - cs, pred_end - cs
    term = clause[a:b].lower()
    nxt = RESTRICT.search(clause, b)
    obj = clause[b:nxt.start() if nxt else len(clause)]
    subj = clause[max(0, prev_end - cs):a]
    if term in ('ban', 'bans', 'prohibition'):  # 'a ban on X', 'the prohibition of X'
        m = re.match(r'\s*(?:imposed\s+)?(?:on|of|against|for)\s+(.+)', obj, re.I)
        if m:
            e = _entity(m.group(1), focus, composition_ok)
            if e[0]:
                return e
    passive = bool(_AUX.search(' '.join(_TOK.findall(subj)[-4:]))) or term in ('withdrawn', 'suspended')
    # Passive ('X is banned in India'): the governed entity is the subject; the rest of the clause can only contribute
    # explicit names or an anaphor. Active ('Health Canada has banned X'): the object is governed; the subject is the agent.
    governed, other_side = (subj, obj) if passive else (obj, subj)
    e = _entity(governed, focus, composition_ok)
    if e[0]:
        return e
    return _entity(other_side, focus, composition_ok, named_only=True)


def _jurisdiction(sentence, clause, a, b, single_clause):
    j = _predicate_jurisdiction(sentence if single_clause else clause, clause, a, b)
    return j


def sentence_events(sentence, focus=None, sentence_index=0, india_context=False, as_of=None, sentence_names_ok=True, id_prefix=None):
    """Restriction and revocation events of one sentence (chronology is applied by resolve_chronology)."""
    as_of = as_of or CURRENT_YEAR
    pfx = id_prefix or f's{sentence_index}'
    events = []
    revocation_spans = [m.span() for m in REVOKED.finditer(sentence)] + [m.span() for m in REVOKED_SENTENCE.finditer(sentence)]
    spans = _clause_spans(sentence) or [(0, len(sentence))]
    single = len(spans) == 1
    hedged_sentence = bool(HEDGE.search(strip_parentheticals(sentence)[0]))
    prev_entity, prev_end = (None, None), 0
    preds = [m for m in RESTRICT.finditer(sentence) if not m.group(0).lower().startswith('section')] or list(RESTRICT.finditer(sentence))
    for m in preds:
        if m.group(0).lower() in ('withdrawn', 'suspended') and any(s <= m.start() < e for s, e in revocation_spans):
            continue  # 'the ban was withdrawn' is a revocation, not a restriction
        cs, ce = next(((s, e) for s, e in spans if s <= m.start() < e), (0, len(sentence)))
        clause, a, b = sentence[cs:ce], m.start() - cs, m.end() - cs
        ent = _event_entity(sentence, clause, cs, m.start(), m.end(), max(prev_end, cs), focus, sentence_names_ok)
        if not ent[0] and prev_entity[0]:
            ent = prev_entity  # 'X is prohibited in India and is not prohibited in Canada'
        if not ent[0]:
            whole = _entity(sentence, focus, sentence_names_ok)
            if whole[0] in ('TARGET', 'COMPONENT'):
                ent = whole  # 'X is used for cramps, but it is banned in India': the sentence's own named entity
        if not ent[0]:
            ent = ('UNBOUND', 'UNBOUND')
        near = clause[max(0, a - 30):b + 45]
        hist_near = [h for h in HIST_RESTRICT.finditer(near) if not re.match(r'once\s+again', near[h.start():h.start() + 10], re.I)]
        years = [int(y) for t in _TIME.finditer(clause) for y in t.groups() if y]
        neg = any(n.start() <= a and n.end() >= b and not re.match(r'not\s+only\b', n.group(0), re.I)
                  for n in NEGATED.finditer(clause)) or _neg_before(clause[:a])
        report_complement = bool(REPORT_THAT.search(sentence[:m.start()]))
        denied = bool(DENIAL.search(sentence[:m.start()])) or (report_complement and bool(FALSITY_AFTER.search(sentence[m.end():])))
        reported = bool(REPORTED.search(clause)) or bool(REPORTED.search(sentence[:m.start()])) or report_complement
        cond = (bool(PROVISO_AFTER.search(clause[b:])) or bool(IF_BEFORE.search(clause[:a])) or bool(CONDITIONAL.search(clause))
                or bool(SCOPE_LIMIT.search(clause[b:])))
        ev = {'id': f'{pfx}.e{len(events)}', 'kind': 'RESTRICTION', 'sentence_index': sentence_index, 'term': m.group(0),
              'span': [m.start(), m.end()], 'clause': clause.strip(), 'entity': ent[0], 'binding': ent[1],
              'negated': neg, 'denied': denied, 'reported': reported or hedged_sentence, 'conditional': cond,
              'proposed': bool(PROPOSED.search(near)) or bool(PROPOSED_FUTURE.search(clause)),
              'historical': bool(hist_near) or (bool(years) and max(years) < as_of), 'years': sorted(set(years)),
              'jurisdiction': _jurisdiction(sentence, clause, a, b, single), 'revoked_by': None, 'reinstates': False}
        if ev['jurisdiction'] == 'UNSPECIFIED' and india_context:
            ev['jurisdiction'] = 'INDIA'
        events.append(ev)
        prev_entity, prev_end = ent, m.end()
    # Scope statements about a restriction ('The ban covers the version that also contains X').
    sm = BAN_SCOPE.search(sentence)
    if sm:  # only an explicitly NAMED other entity disputes scope; 'human use', 'the entire country', '16 FDCs' do not
        ent = _entity(sm.group('obj'), focus, True, named_only=True)
        events.append({'id': f'{pfx}.c{len(events)}', 'kind': 'SCOPE', 'sentence_index': sentence_index, 'term': sm.group(0)[:60],
                       'span': [sm.start(), sm.end()], 'entity': ent[0] or 'UNBOUND', 'binding': ent[1], 'clause': sentence.strip()})
    # Revocations in this sentence.
    for m in _REVOKE.finditer(sentence):
        if not (REVOKED_SENTENCE.search(sentence) or REVOKED.search(sentence[max(0, m.start() - 70):m.end() + 70]) or PRONOUN_REVERSAL.match(sentence)):
            continue
        if m.group(0).lower().startswith('withdr') and not any(s <= m.start() < e for s, e in revocation_spans):
            continue
        if _neg_before(sentence[:m.start()]):
            continue  # 'the ban has not been lifted' affirms the restriction
        obj = re.search(r'\b(?:ban|bans|prohibition|restriction|notification|order)\s+(?:imposed\s+)?(?:on|of|against|for)\s+(.+?)(?:\s+(?:was|were|has|have|had|is|are)\b|[,;.]|$)',
                        sentence, re.I)
        ent = _entity(obj.group(1), focus, True) if obj else (None, None)
        events.append({'id': f'{pfx}.r{len(events)}', 'kind': 'REVOCATION', 'sentence_index': sentence_index, 'term': m.group(0),
                       'span': [m.start(), m.end()], 'entity': ent[0], 'binding': ent[1],
                       'earlier_only': bool(EARLIER_RESTRICTION.search(sentence)), 'clause': sentence.strip()})
        break  # one revocation per sentence is enough to scope it
    return events


def resolve_chronology(events):
    """Apply revocations to the restrictions they refer to, in text order. Mutates and returns events."""
    restrictions = []
    unbound = (None, 'UNBOUND')
    for ev in events:
        if ev['kind'] == 'RESTRICTION':
            if ev['entity'] == 'TARGET' and any(r['revoked_by'] and r['entity'] == 'TARGET' for r in restrictions):
                ev['reinstates'] = True  # a later affirmative restriction on the same entity after a revocation
            restrictions.append(ev)
            continue
        if ev['kind'] == 'SCOPE':  # 'the ban covers <named other entity>': disputes the scope of the restriction it refers to
            if ev['entity'] in ('OTHER', 'COMPONENT'):
                for r in restrictions:
                    if r['sentence_index'] < ev['sentence_index'] and r['entity'] == 'TARGET' and not r.get('scope_disputed'):
                        r['scope_disputed'] = ev['id']
            continue
        # Within its own sentence a revocation reaches only what precedes it, or the ban noun it governs ('lifted the ban
        # on X'); 'The ban was lifted, but X is now banned again' leaves the later restriction active.
        same = [r for r in restrictions if r['sentence_index'] == ev['sentence_index']
                and (r['span'][0] < ev['span'][0] or (r['term'].lower() in ('ban', 'bans', 'prohibition') and 0 <= r['span'][0] - ev['span'][1] < 30))]
        later_same = [r for r in restrictions if r['sentence_index'] == ev['sentence_index'] and r not in same]
        bound_same = {r['entity'] for r in same if r['entity'] not in unbound}
        prior = [r for r in restrictions if r not in later_same]
        if ev['entity']:  # 'a ban on X was lifted': only X's restrictions (another drug's only within this sentence)
            ents = {ev['entity']}
            scope = [r for r in prior if r['entity'] == ev['entity'] and (ev['entity'] != 'OTHER' or r in same)]
        elif bound_same:  # 'X was banned in India, but the ban was revoked'
            ents = bound_same
            scope = [r for r in prior if r['entity'] in ents]
        else:  # 'That prohibition has since been lifted.' / 'It was later revoked.': the most recent bound restriction
            last = next((r for r in reversed(prior) if r['entity'] not in unbound), None)
            ents = {last['entity']} if last else set()
            scope = [r for r in prior if r['entity'] in ents and (last['entity'] != 'OTHER' or r is last)] if last else []
        if len(ents) == 1:  # an anaphoric 'that ban' in the revoking sentence refers to the restriction it revokes
            ent = next(iter(ents))
            for r in same:
                if r['entity'] in unbound:
                    r['entity'], r['binding'] = ent, {'TARGET': 'SUBJECT_ANAPHORA', 'COMPONENT': 'COMPONENT_ONLY'}.get(ent, 'OTHER_ENTITY')
                    scope.append(r)
        for r in scope:
            if ev.get('earlier_only') and not r['historical']:
                continue  # 'an earlier / the 2016 ban was quashed' cancels only historical restrictions, never a current one
            if r['revoked_by'] is None:
                r['revoked_by'] = ev['id']
    return events


def event_qualifies(ev, gov_host=False):
    """All attributes of ONE event for a current Indian restriction on the target. Returns (bool, why_not)."""
    why = []
    if ev['kind'] != 'RESTRICTION':
        return False, ['not a restriction']
    if ev['entity'] != 'TARGET':
        why.append(f"governs {ev['entity'].lower()} entity, not the target")
    for k, msg in (('negated', 'negated'), ('denied', 'denied'), ('reported', 'reported / hedged'), ('conditional', 'conditional'),
                   ('proposed', 'proposed'), ('historical', 'historical or dated before the evidence year')):
        if ev.get(k):
            why.append(msg)
    if ev.get('revoked_by'):
        why.append(f"revoked by {ev['revoked_by']}")
    if ev.get('scope_disputed'):
        why.append(f"scope re-stated as another entity by {ev['scope_disputed']}")
    j = ev['jurisdiction']
    if j != 'INDIA' and not (gov_host and j == 'UNSPECIFIED'):
        why.append(f'jurisdiction {j.lower()}')
    return (not why), why


def text_events(sentences, focus, as_of=None, india_context=None, names_ok=None):
    events = []
    for i, s in enumerate(sentences):
        events += sentence_events(s, focus, i, bool(india_context and india_context[i]), as_of,
                                  True if names_ok is None else names_ok[i])
    return resolve_chronology(events)


# ----------------------------------------------------------------------------------------------------------------------
# Source adapter: restriction statements in organic results and page snapshots (T2 / T3, status capture, legacy fields)
# ----------------------------------------------------------------------------------------------------------------------
def restriction_assessment(text, entry, url=None, include_truncated=False, as_of=None):
    """Statements in one evidence text that establish a current Indian restriction on exactly entry's set, with a trace.
    Requires: the clause names exactly the target (no composition issue in its sentence), one qualifying event, a
    SUPPORTED_EXACT composition for the whole text, no hedge, no truncation (unless include_truncated)."""
    target = set(entry['ingredients'])
    sents = split_sentences(text or '')
    gov_host = bool(url and INDIAN_GOV_HOST.match(url))
    comp = text_composition(text, target)
    names_ok = []
    for s in sents:
        main, _ = strip_parentheticals(s)
        ci = composition_issues(s, target)
        names_ok.append(not (ci['unknown'] or ci['extra_known'] or ci['variable_asides']) and not OTHER_MARK.search(s))
    events = text_events(sents, target, as_of, names_ok=names_ok)
    statements, why_not = [], []
    for ev in events:
        if ev['kind'] != 'RESTRICTION':
            continue
        ok, why = event_qualifies(ev, gov_host)
        sent = sents[ev['sentence_index']]
        main, _ = strip_parentheticals(sent)
        if ok and ev['binding'] != 'EXPLICIT_EXACT':
            ok, why = False, ['target only by anaphora; evidence text must name the exact set']
        truncated = list_truncated(main)
        if ok and truncated and not include_truncated:
            ok, why = False, ['ingredient list cut off ("...")']
        if ok and comp['verdict'] != EXACT:
            ok, why = False, [f"text composition {comp['verdict'].lower()}: " + '; '.join(comp['blockers'][:2])]
        if ok:
            statements.append({'sentence': sent, 'jurisdiction': 'INDIA' if ev['jurisdiction'] == 'INDIA' else 'INDIA_GOV_HOST',
                               'notices': notice_numbers(sent), 'scope_truncated': truncated, 'event_id': ev['id'],
                               'reinstatement': ev['reinstates']})
        else:
            why_not.append({'event_id': ev['id'], 'sentence': sent, 'term': ev['term'], 'why_not': why})
    # one statement per sentence
    seen, uniq = set(), []
    for st in statements:
        if st['sentence'] not in seen:
            seen.add(st['sentence'])
            uniq.append(st)
    return {'statements': uniq, 'events': events, 'composition': comp, 'why_not': why_not}


def gov_host(url):
    return bool(url and INDIAN_GOV_HOST.match(url))
