"""Restriction events per clause, their chronology and whether an event qualifies for the target."""

import re
from ..claims import (ANAPHORA, CONDITIONAL, CURRENT_YEAR, EARLIER_RESTRICTION, GENERIC_MARK, HEDGE, HIST_RESTRICT,
    INDIA, INDIAN_GOV_HOST, NEGATED, OTHER_JURIS, OTHER_MARK, PRONOUN_REVERSAL, PROPOSED, PROPOSED_FUTURE, RESTRICT,
    REVOKED, REVOKED_SENTENCE, _TIME, _allowed_word, _canon_set, _predicate_jurisdiction, composition_issues,
    list_truncated, notice_numbers, split_sentences, strip_parentheticals)
from .patterns import (BAN_SCOPE, DENIAL, EXACT, FALSITY_AFTER, IF_BEFORE, PROVISO_AFTER, REPORTED, REPORT_THAT,
    SCOPE_LIMIT, _AUX, _ENTITY_STOP, _NEG_STOP, _NEG_WORD, _REVOKE, _TOK)
from .composition import _clause_spans, text_composition


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
