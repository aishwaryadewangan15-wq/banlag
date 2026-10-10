"""Citation-formulation coherence: does each AI claim cite sources about the SAME formulation it talks about?

Only possible with provider data that binds claims to references (SerpApi text_blocks.reference_indexes). For each
cited reference we read what the reference itself names — its title, Google-displayed snippet and URL slug, all from
the same sealed response — never the page (pages are not fetched). A snippet cut off by '...' right after an
ingredient list yields only a lower bound (truncated), never an exact match. Nothing here infers why the model cited
what it cited, and nothing judges any publisher or product.
"""
import re
from urllib.parse import unquote, urlparse

from .claims import (INDIA, OTHER_JURIS, RESTRICT, _allowed_word, _canon_set, _valid_index, composition_issues, list_runs, list_truncated,
                     notice_numbers, reference_index_map, restriction_qualifiers, split_sentences, strip_parentheticals)
from .semantics import (DIFFERENT, UNRESOLVED as COMPOSITION_UNRESOLVED, composition_state, event_qualifies, gov_host,
                        resolve_chronology, sentence_events)

# Reference relations that do not establish which formulation the reference is about.
UNRESOLVED = ('EXACT_LOWER_BOUND', 'LOWER_BOUND_SUBSET', 'NO_FORMULATION_NAMED', 'UNRECOGNISED_COMPONENT', 'CONFLICTING_VIEWS',
              'MULTIPLE_FORMULATIONS', 'AMBIGUOUS_INDEX')
# Reconciliation states that override the set relation.
_UNRESOLVED_STATUS = ('CONFLICTING_VIEWS', 'MULTIPLE_FORMULATIONS', 'UNRECOGNISED_COMPONENT')
from .legal import find_mentions, match_set

# Words a URL slug may carry around an ingredient list without naming a component (page furniture, not composition).
_SLUG_WORDS = set('''uses use price prices side effects effect dosage online buy generic generics salt composition information info details
detail review reviews view product products medicine medicines drug drugs html htm php aspx amp faq faqs substitute substitutes alternative
alternatives combination ban banned prohibition prohibited notification news article legal update updates what is how why list india in
overview interactions warnings precautions benefits work works strength pack brand brands manufacturer tablets tablet tab tabs caps capsule
capsules syrup injection suspension cream gel ointment otc rx wiki''' .split())

SUBJECT_BOUND = ('EXPLICIT_EXACT', 'SUBJECT_ANAPHORA', 'SUBJECT_IMPLICIT')


def _slug_text(link):
    try:
        path = unquote(urlparse(link or '').path)
    except ValueError:
        return ''
    return re.sub(r'[-_+/]+', ' ', re.sub(r'\.(?:html?|pdf|php|aspx?)$', '', path, flags=re.I))


def _slug_unknown(text, runs, inner):
    """Unrecognised components in a URL slug: words inside or right after a run of ingredient names that are not page
    furniture, numbers, strengths or dosage forms ('...-clidinium-bromide-activated-charcoal' -> 'activated charcoal').
    A slug is word-delimited only, so this is an ambiguity flag, not a parse: it never makes a reference exact."""
    unknown = list(inner)
    ends = [r[-1]['end'] for r in runs]
    starts = [r[0]['start'] for r in runs[1:]] + [len(text)]
    for end, nxt in zip(ends, starts):
        words, cur = [], []
        for w in re.findall(r'[A-Za-z][A-Za-z0-9]*|\d+', text[end:nxt]):
            if w.isdigit() or _allowed_word(w) or w.lower() in _SLUG_WORDS:
                if cur:
                    words.append(' '.join(cur))
                    cur = []
                if w.isdigit():
                    break  # a trailing page id ends the formulation part of the slug
                continue
            cur.append(w)
        if cur:
            words.append(' '.join(cur))
        unknown += words
    return unknown


def _view(name, text):
    """What one metadata view (title, snippet or URL slug) names, assessed on its own. A snippet is a short text unit:
    later sentences that add to its formulation ('... Omeprazole is also in it.') are read with the shared composition
    state, so a cross-sentence addition cannot leave the view looking exact."""
    slug = name == 'url_slug'
    runs, inner = list_runs(text, space_delimited=slug)
    sets = [frozenset(m['canonical'] for m in r) for r in runs]
    combos = sorted({s for s in sets if len(s) >= 2}, key=sorted)
    repeated = any(len({m['canonical'] for m in r}) < len(r) for r in runs)  # 'A + B and A + B + C': two formulations in one list
    names = {m['canonical'] for m in find_mentions(text)}
    composition = None
    if slug:
        # A slug has no punctuation, so neighbouring words are list members only when the slug names a combination
        # ('...-clidinium-bromide-omeprazole-123'), not in '/dicyclomine/what-is'.
        unknown = _slug_unknown(text, runs, inner) if len(names) >= 2 else []
    else:
        unknown = composition_issues(text)['unknown']
        sents = split_sentences(text)
        lead = next((i for i, s in enumerate(sents) if len(_canon_set(strip_parentheticals(s)[0])) >= 2), None)
        if lead is not None:  # every clause, including a single-sentence view's own clauses (RC-3)
            focus = _canon_set(strip_parentheticals(sents[lead])[0])
            st = composition_state(sents, focus, lead)
            composition = st['verdict']
            names |= set(st['extra_known'])
            unknown += st['unknown']
            if st['verdict'] == COMPOSITION_UNRESOLVED:
                unknown.append('(composition statement that cannot be attached: ' + '; '.join(st['blockers'][:1])[:120] + ')')
            elif st['verdict'] == DIFFERENT and not (st['unknown'] or st['extra_known']):
                unknown.append('(stated as absent: ' + ', '.join(st['missing']) + ')' if st.get('missing')
                               else '(an additional active ingredient is stated)')
    return {'ingredients': sorted(names), 'combinations': [sorted(s) for s in combos],
            'multiple': len(combos) > 1 or repeated, 'unrecognised': unknown, 'composition': composition,
            'truncated': list_truncated(text) or (slug and text.rstrip().endswith(' of'))}


def _active_restriction_view(text):
    """A view that states a restriction which is not negated, revoked, historical or proposed, and not only foreign."""
    if not RESTRICT.search(text):
        return False
    if any(restriction_qualifiers(text).values()):
        return False
    return not (OTHER_JURIS.search(text) and not INDIA.search(text))


def _restriction_support(texts, views, names, link):
    """How strongly ONE metadata view states a restriction on the reference's resolved formulation:
    QUALIFYING  one event bound to exactly that set, affirmed, unconditional, current and Indian (or an Indian government host)
    BOUND       the same, except the metadata states no jurisdiction (not foreign, not ambiguous)
    MENTION_ONLY a restriction term appears, but no view binds it to that set ('… tablets' title + 'Chlordiazepoxide is prohibited')
    NONE        no restriction term."""
    mention = any(_active_restriction_view(t) for t in texts.values())
    best = 'NONE'
    if names:
        for k in ('title', 'snippet'):  # a slug is a word list, not a sentence
            if views[k].get('composition') == DIFFERENT:
                continue
            sents = split_sentences(texts[k])
            evs = resolve_chronology([e for i, s in enumerate(sents) for e in sentence_events(s, set(names), i)])
            for e in evs:
                if e['kind'] != 'RESTRICTION' or e['entity'] != 'TARGET' or e['binding'] != 'EXPLICIT_EXACT':
                    continue
                if any(e.get(q) for q in ('negated', 'denied', 'reported', 'conditional', 'proposed', 'historical', 'revoked_by', 'scope_disputed')) \
                        or e['jurisdiction'] in ('OTHER', 'AMBIGUOUS'):
                    continue
                best = 'QUALIFYING' if event_qualifies(e, gov_host(link))[0] else ('BOUND' if best != 'QUALIFYING' else best)
    return best if best != 'NONE' else ('MENTION_ONLY' if mention else 'NONE')


def reference_formulation(ref):
    """What formulation a reference names. Title, snippet and URL slug are assessed separately and then reconciled:
    complete views must agree; a view cut off by '...' must be consistent with (a subset of) the complete views; a view
    that names two different combinations, or a component BANLAG cannot identify, leaves the reference unresolved.
    Nothing is inferred about the cited page itself, which is never fetched."""
    texts = {'title': ref.get('title') or '', 'snippet': ref.get('snippet') or '', 'url_slug': _slug_text(ref.get('link'))}
    views = {k: _view(k, v) for k, v in texts.items()}
    combo = {k: v for k, v in views.items() if len(v['ingredients']) >= 2}
    complete = {k: v for k, v in combo.items() if not v['truncated']}
    trunc = {k: v for k, v in combo.items() if v['truncated']}
    unknown = [u for v in views.values() for u in v['unrecognised']]
    status, conflict, names, basis, lower_bound = None, None, set(), [], False
    multi = [k for k, v in combo.items() if v['multiple']]
    complete_sets = {k: frozenset(v['ingredients']) for k, v in complete.items()}
    if multi:
        status, conflict = 'MULTIPLE_FORMULATIONS', f"{' and '.join(multi)} name(s) more than one ingredient combination"
    elif len(set(complete_sets.values())) > 1:
        status = 'CONFLICTING_VIEWS'
        conflict = '; '.join(f"{k} names {' + '.join(sorted(s))}" for k, s in complete_sets.items())
    elif complete_sets:
        names = set(next(iter(complete_sets.values())))
        basis = sorted(complete_sets)
        bad = [k for k, v in trunc.items() if not set(v['ingredients']) <= names]
        if bad:
            status = 'CONFLICTING_VIEWS'
            conflict = f"truncated {' and '.join(bad)} name(s) ingredients absent from the complete {' and '.join(basis)}"
    elif trunc:
        names = set().union(*(set(v['ingredients']) for v in trunc.values()))
        basis, lower_bound = sorted(trunc), True
    else:  # no view names a combination: fall back to a single named ingredient (title, then slug, then snippet)
        for k in ('title', 'url_slug', 'snippet'):
            if views[k]['ingredients']:
                names, basis = set(views[k]['ingredients']), [k]
                lower_bound = views[k]['truncated']
                break
    if status is None and unknown:
        status = 'UNRECOGNISED_COMPONENT'
    if status is None:
        status = ('NO_FORMULATION_NAMED' if not names else 'LOWER_BOUND' if lower_bound else
                  'SINGLE_NAME_ONLY' if len(names) == 1 else 'RESOLVED')
    resolved = status == 'RESOLVED'
    match = match_set(names) if resolved else {'status': 'NONE'}
    if status in _UNRESOLVED_STATUS:  # no view establishes the set: report everything named, attribute it to no view
        names_out, basis = sorted(set().union(*(set(v['ingredients']) for v in views.values()))), []
    else:
        names_out = sorted(names)
    restriction_views = [k for k, t in texts.items() if _active_restriction_view(t)]
    return {'index': ref.get('index'), 'source': ref.get('source'), 'title': ref.get('title'), 'link': ref.get('link'),
            'ingredients': names_out, 'unrecognised_components': unknown, 'basis': ' + '.join(basis) or None,
            'truncated': lower_bound, 'truncated_views': sorted(k for k, v in views.items() if v['truncated']),
            'reconciliation': status, 'conflict': conflict,
            'views': {k: {'ingredients': v['ingredients'], 'combinations': v['combinations'], 'unrecognised': v['unrecognised'],
                          'truncated': v['truncated']} for k, v in views.items()},
            'registry_entry': (match.get('entry') or {}).get('id') if match.get('status') == 'EXACT_NOTIFICATION_MATCH' else None,
            'mentions_restriction': bool(restriction_views), 'restriction_views': restriction_views,
            'restriction_support': _restriction_support(texts, views, names if status not in _UNRESOLVED_STATUS else set(), ref.get('link')),
            'notices': sorted({n for v in texts.values() for n in notice_numbers(v)})}


def relation_to(subject, ref_form):
    if ref_form.get('reconciliation') in _UNRESOLVED_STATUS:
        return ref_form['reconciliation']
    names = set(ref_form['ingredients'])
    if not names:
        return 'NO_FORMULATION_NAMED'
    if ref_form.get('unrecognised_components'):
        return 'UNRECOGNISED_COMPONENT'
    if names == subject:
        return 'EXACT_LOWER_BOUND' if ref_form['truncated'] else 'EXACT'
    if names < subject:
        return 'SINGLE_COMPONENT' if len(names) == 1 else ('LOWER_BOUND_SUBSET' if ref_form['truncated'] else 'SUBSET')
    if names > subject:
        return 'SUPERSET'
    return 'OTHER_FORMULATION'


def coherence(analysis, references):
    """Per-claim citation coherence for one surface. analysis = claims.analyze_surface(...) output."""
    subject = set(analysis['subject']['ingredients'])
    by_index, dup, _ = reference_index_map(references)
    forms, ordered, ambiguous = {}, [], []
    for r in references or []:
        if not isinstance(r, dict):
            continue
        f = reference_formulation(r)
        i = r.get('index')
        if i in by_index and by_index[i] is r:
            f['relation'], f['index_status'] = relation_to(subject, f), 'UNIQUE'
            forms[i] = f
        else:  # duplicate or malformed index: never resolved to one reference (no last-write-wins)
            valid = _valid_index(i)
            f.update(relation='AMBIGUOUS_INDEX', registry_entry=None, index_status='DUPLICATE_INDEX' if valid else 'MALFORMED_INDEX',
                     conflict=(f'index {i} is used by more than one reference, so a claim citing it cannot be bound to one of them'
                               if valid else f'malformed reference index {i!r}'))
            ambiguous.append(f)
        ordered.append(f)
    subject_entry = analysis['subject'].get('entry_id') if analysis['subject'].get('registry_match') == 'EXACT_NOTIFICATION_MATCH' else None
    rows, findings = [], []
    for c in analysis['claims']:
        idx = [r['index'] for r in c['citations']['references']]
        amb = c['citations'].get('ambiguous_indexes') or []
        if not idx and not amb:
            continue
        restr = c.get('restriction')
        kind = ('RESTRICTION' if restr else 'CURRENT_USE' if c.get('use_binding') in SUBJECT_BOUND else 'OTHER')
        cited = []
        for i in idx:
            f = forms.get(i)
            if not f:
                continue
            rel = relation_to(subject, f)
            cited.append({**f, 'relation': rel})
        cited += [dict(f) for f in ambiguous if f.get('index') in amb]
        rows.append({'claim_id': c['id'], 'kind': kind, 'text': c['text'], 'label': c['label'], 'cited': cited})
        if kind == 'RESTRICTION' and restr and restr['jurisdiction'] == 'INDIA':
            # Support needs the SAME formulation and a qualifying legal predicate in one metadata view (restriction_support),
            # not a reconciled ingredient set from one view plus a restriction word from another.
            bound = ('BOUND', 'QUALIFYING')
            exact = [x for x in cited if x['relation'] == 'EXACT' and x.get('restriction_support') in bound]
            other_notice = [x for x in cited if x.get('restriction_support') in bound and x['registry_entry'] and x['registry_entry'] != subject_entry]
            unresolved = [x for x in cited if x['mentions_restriction'] and (x['relation'] in UNRESOLVED or
                                                                             (x['relation'] == 'EXACT' and x.get('restriction_support') not in bound))]
            if not exact:
                findings.append({'type': 'RESTRICTION_CITATIONS_DO_NOT_NAME_THIS_NOTICE', 'claim_id': c['id'],
                                 'statement': ('None of this restriction sentence\'s cited references, as captured (title, snippet, URL), '
                                               'names this exact composition as prohibited. Unresolved references could still concern it.'),
                                 'other_notice_sources': [{'index': x['index'], 'source': x['source'], 'entry': x['registry_entry'],
                                                           'notice': (entry_by_id_safe(x['registry_entry']) or {}).get('notice')} for x in other_notice],
                                 'unresolved_sources': [{'index': x['index'], 'source': x['source'], 'relation': x['relation'],
                                                         'why': _WHY.get(x['relation'], x['relation']) + (f" ({x['conflict']})" if x.get('conflict') else '')}
                                                        for x in unresolved]})
        if kind == 'CURRENT_USE':
            off = [x for x in cited if x['relation'] in ('SUBSET', 'SUPERSET', 'OTHER_FORMULATION')]
            if off:
                findings.append({'type': 'CURRENT_USE_CLAIM_CITES_OTHER_FORMULATION', 'claim_id': c['id'],
                                 'statement': 'This current-use claim about the exact combination cites references that name a different ingredient set.',
                                 'sources': [{'index': x['index'], 'source': x['source'], 'relation': x['relation'], 'ingredients': x['ingredients']} for x in off]})
    cited_idx = {x['index'] for r in rows for x in r['cited']}
    unresolved_refs = sorted({x['index'] for r in rows for x in r['cited'] if x['relation'] in UNRESOLVED}, key=repr)
    status = ('MISMATCH_DETECTED' if findings else
              'NO_MISMATCH_DETECTED_PARTIAL_COVERAGE' if unresolved_refs or ambiguous else 'NO_MISMATCH_DETECTED')
    return {'references': ordered, 'claims': rows, 'findings': findings, 'status': status,
            'index_problems': [{'index': f.get('index'), 'status': f['index_status'], 'conflict': f['conflict']} for f in ambiguous],
            'coverage': {'cited_references': len(cited_idx), 'unresolved_references': unresolved_refs,
                         'uncited_claims_with_text': sum(1 for c in analysis['claims'] if not c['citations']['references'])},
            'note': ('Reference formulations are read from the provider-captured title, snippet and URL of each reference; cited pages were '
                     'not fetched. Absence of a detected mismatch is not proof that every citation is coherent.')}


_WHY = {'EXACT_LOWER_BOUND': 'the ingredient list is cut off by "..." right after this set, so it could be a larger combination',
        'LOWER_BOUND_SUBSET': 'the ingredient list is cut off by "..." after only part of this set',
        'NO_FORMULATION_NAMED': 'title, snippet and URL name no formulation',
        'UNRECOGNISED_COMPONENT': 'a listed component is not one BANLAG can identify',
        'CONFLICTING_VIEWS': 'title, snippet and URL name different formulations',
        'MULTIPLE_FORMULATIONS': 'the captured text names more than one combination',
        'AMBIGUOUS_INDEX': 'the reference index is duplicated or malformed, so the citation cannot be bound to one reference',
        'EXACT': 'its metadata names this set, but the restriction it mentions is not bound to this set in the same view'}


def entry_by_id_safe(entry_id):
    from .legal import entry_by_id
    return entry_by_id(entry_id) if entry_id else None
