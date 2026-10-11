"""Claim-level analysis of an AI answer surface: subject binding, restriction statements and per-claim readings."""

import re
from ..legal import match_set, notice_numbers, entry_by_notice
from .patterns import (ANAPHORA, COADMIN, GENERIC_MARK, HEDGE, HISTORICAL, HIST_HEADING, INDIA, NEG_USE,
    NOT_RECOMMENDED, OTHER_FORM, OTHER_MARK, PRONOUN_REVERSAL, RESTRICT, REVOKED_SENTENCE, STRONG, VARIABLE, WEAK)
from .sentences import _valid_index, reference_index_map, split_sentences, strip_parentheticals
from .composition import _canon_set, composition_issues, unknown_list_items


def _bind(main, subject, label_is_component, allow_implicit, sentence=None):
    names = _canon_set(main)
    if names:
        ci = composition_issues(sentence if sentence is not None else main, subject or None)
        if ci['unknown'] or ci['extra_known']:
            return 'OTHER_ENTITY'  # the sentence's formulation has a component beyond (or unidentifiable against) the subject
    if subject and names:
        if names == subject:
            return 'EXPLICIT_EXACT'
        if names < subject:
            if ANAPHORA.search(main):
                return 'SUBJECT_ANAPHORA'
            return 'COMPONENT_ONLY'
        return 'OTHER_ENTITY'
    if names:
        return 'OTHER_ENTITY'
    if OTHER_MARK.search(main):
        return 'OTHER_ENTITY'
    if subject and ANAPHORA.search(main):
        return 'SUBJECT_ANAPHORA'
    if subject and allow_implicit and not label_is_component:
        return 'SUBJECT_IMPLICIT'
    return 'UNBOUND'
def restriction_statements(text, entry, url=None, include_truncated=False, as_of=None):
    """Sentences that establish a current Indian restriction on exactly this entry's ingredient set (organic T2, snapshot
    T3, status capture, legacy fields). Delegates to semantics.restriction_assessment: one qualifying legal event bound to
    the exact named set, a SUPPORTED_EXACT composition for the whole text, no truncation, no hedge."""
    from ..semantics import restriction_assessment
    return restriction_assessment(text, entry, url, include_truncated, as_of)['statements']
def _strong_cues(text):
    return [(k, m.group(0)) for k, rx in STRONG for m in [rx.search(text)] if m]
def status_question_hint(question, entry):
    """Target hint for a separately asked status question: (hint set or None, validation note).
    Only a question that is present AND names exactly the target, with no added component ('… clidinium bromide omeprazole
    prohibited …'), yields a hint. A missing or non-matching question yields no hint: the answer must establish its own
    subject, and no status contrast can be attributed to a target question (RC-3)."""
    target = set(entry['ingredients'])
    if not isinstance(question, str) or not question.strip():
        return None, 'STATUS_QUESTION_NOT_PROVIDED'
    main, _ = strip_parentheticals(question)
    if _canon_set(main) != target or unknown_list_items(main, space_delimited=True) or composition_issues(question, target)['unknown']:
        return None, 'STATUS_QUESTION_DOES_NOT_NAME_EXACTLY_THE_TARGET'
    return target, 'STATUS_QUESTION_NAMES_EXACT_TARGET'
def _claim_restriction(events, main, full):
    """Claim-level view of a sentence's legal events. Only events bound to the subject decide current_india."""
    from ..semantics import event_qualifies
    rs = [e for e in events if e['kind'] == 'RESTRICTION']
    tb = [e for e in rs if e['entity'] == 'TARGET']
    base = tb or rs
    if tb:
        bind = 'EXPLICIT_EXACT' if any(e['binding'] == 'EXPLICIT_EXACT' for e in tb) else 'SUBJECT_ANAPHORA'
    elif any(e['entity'] == 'COMPONENT' for e in rs):
        bind = 'COMPONENT_ONLY'
    elif any(e['entity'] == 'GENERIC' for e in rs):
        bind = 'GENERIC'
    elif any(e['entity'] == 'OTHER' for e in rs):
        bind = 'OTHER_ENTITY'
    elif rs:
        bind = 'UNBOUND'
    else:
        bind = 'REVOCATION'
    if bind == 'UNBOUND' and GENERIC_MARK.search(full):
        bind = 'GENERIC'
    js = [e['jurisdiction'] for e in base]
    view = []
    for e in events:
        ok, why = event_qualifies(e) if e['kind'] == 'RESTRICTION' else (False, [])
        view.append({k: e.get(k) for k in ('id', 'kind', 'term', 'entity', 'binding', 'jurisdiction', 'negated', 'denied', 'reported',
                                          'conditional', 'proposed', 'historical', 'years', 'revoked_by', 'reinstates')}
                    | {'qualifies': ok, 'why_not': why, 'clause': (e.get('clause') or '')[:240]})
    qualifying = [v for v in view if v['qualifies']]
    hedged = bool(HEDGE.search(main)) or any(e['reported'] for e in base)
    r = {'binding': bind, 'jurisdiction': next((j for j in ('INDIA', 'OTHER', 'AMBIGUOUS') if j in js), 'UNSPECIFIED'),
         'hedged': hedged, 'negated': any(e['negated'] or e['denied'] for e in base), 'denied': any(e['denied'] for e in base),
         'reported': any(e['reported'] for e in base), 'revoked': any(e['revoked_by'] for e in base),
         'historical': any(e['historical'] for e in base), 'proposed': any(e['proposed'] for e in base),
         'conditional': any(e['conditional'] for e in base), 'current_india': bool(qualifying),
         'notices': notice_numbers(full), 'events': view}
    r['active_target_india'] = r['current_india'] and not hedged
    r['why_not'] = [] if r['active_target_india'] else sorted({w for v in view if v['entity'] == 'TARGET' for w in v['why_not']}
                                                              | ({'hedged / reported'} if hedged and tb else set()))
    return r
def analyze_surface(blocks, references=None, binding='UNBOUND', target_entry=None, capture_complete=True, subject_hint=None,
                    as_of=None):
    """blocks: [{'id','type','label','text','reference_indexes','chips'}]. Returns claims, subject resolution and A-F label.

    subject_hint is used ONLY for a separately asked status prompt whose answer names nothing (the question named the
    combination); uses-answers must establish the exact set in their own text (preregistration section 4).
    """
    from ..semantics import EXACT, UNRESOLVED, answer_composition, resolve_chronology, sentence_events
    references = references or []
    ref_by_index, dup_indexes, malformed_indexes = reference_index_map(references)
    text_present = any((b.get('text') or '').strip() for b in blocks)
    # One composition assessment per answer. A status-question hint can resolve the subject of an answer that names
    # nothing, but the answer's own sentences are always checked against it (never an unexamined default to exact).
    comp = answer_composition(blocks, hint=subject_hint)
    subject, lead, lead_classes, subject_unknown = (comp['subject'], comp['lead'], comp['classes'], comp['unknown']) if comp else (set(), None, {}, [])
    composition_verdict = comp['verdict'] if comp else None
    subject_source = comp['source'] if comp else 'LEAD_SENTENCE'
    subj_match = match_set(subject, lead_classes) if subject else {'status': 'NO_SUBJECT'}
    claims, flags = [], []
    section_hist = False
    variable_hits, extra_components = [], []
    for b in blocks:
        label = (b.get('label') or '').strip()
        if b.get('type') == 'heading':
            section_hist = bool(HIST_HEADING.search(b['text']))
            continue
        label_main, _ = strip_parentheticals(label)
        label_names = _canon_set(label_main)
        label_is_component = bool(label_names)
        if label_names and subject and not label_names <= subject:
            extra_components.append({'block_id': b['id'], 'label': label, 'extra': sorted(label_names - subject)})
        if label and HIST_HEADING.search(label):
            label_hist = True
        else:
            label_hist = False
        block_india = bool(INDIA.search(label))
        # Claim-side indexes are validated as strictly as reference-side ones: False / 0.0 / '0' never equal index 0.
        raw_idx = b.get('reference_indexes') if isinstance(b.get('reference_indexes'), list) else []
        claim_idx = [i for i in raw_idx if _valid_index(i)]
        malformed_cites = [repr(i) for i in raw_idx if not _valid_index(i)]
        cites = [ref_by_index[i] for i in claim_idx if i in ref_by_index]
        ambiguous_cites = sorted({i for i in claim_idx if i in dup_indexes})
        for k, sent in enumerate(split_sentences(b['text'])):
            full = (label + ': ' + sent) if label and k == 0 else sent
            main, asides = strip_parentheticals(sent)
            claim = {'id': f"{b['id']}.s{k}", 'block_id': b['id'], 'label': label, 'text': sent, 'types': [], 'cues': []}
            for aside in asides:
                if VARIABLE.search('(' + aside + ')') or VARIABLE.search(aside):
                    variable_hits.append({'claim_id': claim['id'], 'text': aside})
            if VARIABLE.search(main):
                variable_hits.append({'claim_id': claim['id'], 'text': main})
            if label and VARIABLE.search(label):
                variable_hits.append({'claim_id': claim['id'], 'text': label})
            historical = bool(HISTORICAL.search(full)) or section_hist or label_hist
            if RESTRICT.search(full) or REVOKED_SENTENCE.search(full) or PRONOUN_REVERSAL.match(sent):
                # One legal event per predicate, bound to its own clause; chronology is resolved across the answer below.
                ci = composition_issues(sent, subject or None) if _canon_set(main) else None
                names_ok = not (ci and (ci['unknown'] or ci['extra_known']))
                claim['_events'] = sentence_events(full, subject or None, len(claims), block_india, as_of, names_ok,
                                                   id_prefix=claim['id'])
                for e in claim['_events']:
                    e['claim_id'] = claim['id']
                if RESTRICT.search(full):
                    claim['types'].append('RESTRICTION')
            if NOT_RECOMMENDED.search(full):
                claim['types'].append('NOT_RECOMMENDED_LANGUAGE')
            if historical:
                claim['types'].append('HISTORICAL')
            strong = _strong_cues(full)
            weak = WEAK.search(full)
            if (strong or weak) and not historical and not NEG_USE.search(full) and 'RESTRICTION' not in claim['types']:
                bind = _bind(main, subject, label_is_component, allow_implicit=True, sentence=sent)
                claim['types'].append('CURRENT_USE_STRONG' if strong else 'CURRENT_USE_WEAK')
                claim['cues'] = [c for _, c in strong] or [weak.group(0)]
                claim['cue_kinds'] = sorted({k for k, _ in strong})
                claim['use_binding'] = bind
            if COADMIN.search(full):
                claim['types'].append('CO_ADMINISTRATION_SCOPE')
            if OTHER_FORM.search(full):
                claim['types'].append('OTHER_DOSAGE_FORM_SCOPE')
            claim['citations'] = {'binding': binding if (b.get('reference_indexes') is not None or b.get('chips')) else 'UNBOUND',
                                  'references': [{'index': r.get('index'), 'link': r.get('link'), 'title': r.get('title'), 'source': r.get('source')} for r in cites],
                                  'ambiguous_indexes': ambiguous_cites, 'malformed_indexes': malformed_cites,
                                  'chips': list(b.get('chips') or [])}
            claims.append(claim)

    def bound_to_subject(c):
        return c in ('EXPLICIT_EXACT', 'SUBJECT_ANAPHORA', 'SUBJECT_IMPLICIT')

    # Chronology across the whole answer: a revocation applies only to the restriction(s) it refers to (same entity), and a
    # later affirmative restriction on the same entity is a reinstatement.
    events = [e for c in claims for e in c.get('_events', [])]
    resolve_chronology(events)
    owner = {e['id']: e['claim_id'] for e in events}
    for c in claims:
        evs = c.pop('_events', None)
        if evs is None:
            continue
        if any(e['kind'] == 'REVOCATION' for e in evs):
            c['reverses_earlier_restriction'] = True
        if 'RESTRICTION' in c['types']:
            main, _ = strip_parentheticals(c['text'])
            full = (c['label'] + ': ' + c['text']) if c['label'] and c['id'].endswith('.s0') else c['text']
            c['restriction'] = _claim_restriction(evs, main, full)
            rev = next((owner.get(e['revoked_by']) for e in evs if e['kind'] == 'RESTRICTION' and e.get('revoked_by')), None)
            if rev:
                c['restriction']['reversed_by'] = rev
    restr = [c for c in claims if 'RESTRICTION' in c['types']]
    subj_restr = [c for c in restr if c['restriction']['binding'] in ('EXPLICIT_EXACT', 'SUBJECT_ANAPHORA')]
    def active(r):  # ONE event bound to the subject that is affirmed, unconditional, current, Indian and not revoked; no hedge
        return r['active_target_india']

    clean_d = [c for c in subj_restr if active(c['restriction'])]
    use = [c for c in claims if c.get('use_binding') and bound_to_subject(c['use_binding'])]
    strong_use = [c for c in use if 'CURRENT_USE_STRONG' in c['types']]
    scope_mixed = bool(extra_components) or len(variable_hits) >= 2 or any('when included' in v['text'].lower() for v in variable_hits)
    if variable_hits and not scope_mixed:
        flags.append('VARIABLE_COMPOSITION_ASIDE')
    if any('CO_ADMINISTRATION_SCOPE' in c['types'] for c in claims):
        flags.append('CO_ADMINISTRATION_SCOPE')
    if any('OTHER_DOSAGE_FORM_SCOPE' in c['types'] for c in claims):
        flags.append('OTHER_DOSAGE_FORM_SCOPE')
    if any('NOT_RECOMMENDED_LANGUAGE' in c['types'] for c in claims):
        flags.append('NOT_RECOMMENDED_LANGUAGE')
    if any(c['restriction']['binding'] == 'OTHER_ENTITY' for c in restr):
        flags.append('OTHER_ENTITY_RESTRICTION_NOTED')

    # Entity resolution against the declared target (if any) or against the registry.
    if target_entry is not None:
        tset = set(target_entry['ingredients'])
        if subj_match.get('status') == 'EXACT_NOTIFICATION_MATCH' and subj_match['entry']['id'] == target_entry['id']:
            entity = 'EXACT'
        elif subj_match.get('status') == 'CONTESTED_SYNONYM_CANDIDATE' and subj_match['candidate_entry_id'] == target_entry['id']:
            entity = 'CONTESTED'
        elif subject:
            entity = {'SUBSET': 'SUBSET_OF_TARGET', 'SUPERSET': 'SUPERSET_OF_TARGET'}.get(
                'SUBSET' if subject < tset else 'SUPERSET' if subject > tset else '', 'OTHER_ENTITY')
        else:
            entity = 'NO_SUBJECT'
    else:
        entity = {'EXACT_NOTIFICATION_MATCH': 'EXACT', 'CONTESTED_SYNONYM_CANDIDATE': 'CONTESTED'}.get(subj_match.get('status'), 'NOT_LISTED' if subject else 'NO_SUBJECT')
    if subject_unknown:
        entity = 'UNKNOWN_COMPONENT'  # the answer lists or asserts something we cannot identify: never exact

    # Formulation-level applicability is part of the final verdict of every restriction claim: an event that qualifies on
    # its own cannot make a restriction 'current, Indian, on this formulation' when the answer's formulation is not the
    # exact target (drives label D and the UI's green highlight alike).
    formulation_ok = entity == 'EXACT' and composition_verdict == EXACT
    for c in restr:
        r = c['restriction']
        r['formulation_supported'] = formulation_ok
        if r['active_target_india'] and not formulation_ok:
            r['active_target_india'] = False
            r['why_not'] = sorted(set(r['why_not']) | {f'answer formulation is {entity.lower()} / composition {str(composition_verdict).lower()}'})
    clean_d = [c for c in subj_restr if active(c['restriction'])]

    trace = []

    def decide():
        if not text_present:
            trace.append('A: no AI answer text in this surface')
            return 'A'
        trace.append('A: answer text present')
        if entity in ('CONTESTED',):
            trace.append('B/F: subject matches only through a contested probiotic synonym -> abstain (F)')
            return 'F'
        if entity != 'EXACT':
            extra = f' (unrecognised list member(s): {", ".join(subject_unknown)})' if subject_unknown else ''
            trace.append(f'B: lead-sentence subject {sorted(subject)} is {entity}, not the exact notified set{extra}')
            return 'B'
        if composition_verdict == UNRESOLVED:
            trace.append('B/F: the exact set is named or hinted, but a composition statement cannot be attached safely -> abstain (F): '
                         + '; '.join((comp or {}).get('blockers', [])[:2]))
            return 'F'
        trace.append('B: exact notified ingredient set established ' + ('in lead sentence: ' + lead if lead else
                                                                         'by the status question, and no answer sentence contradicts it'))
        if clean_d:
            trace.append('D: India restriction bound to this exact FDC: ' + clean_d[0]['text'])
            return 'D'
        trace.append('D: no unhedged India restriction bound to this exact FDC')
        reasons = []
        if not capture_complete:
            reasons.append('capture incomplete/truncated')
        if scope_mixed:
            reasons.append('entity scope mixed (variable composition or extra-active component)')
        if [c for c in subj_restr if c not in clean_d]:
            reasons.append('restriction about this FDC is hedged, negated, revoked, historical, proposed, conditional, foreign or jurisdiction-unspecified')
        if [c for c in restr if c['restriction']['binding'] in ('GENERIC', 'UNBOUND')]:
            reasons.append('generic/unbound restriction makes this FDC\'s status unclear')
        if [c for c in restr if c['restriction']['binding'] == 'COMPONENT_ONLY' and c['restriction']['jurisdiction'] == 'INDIA'
                and not c['restriction']['negated']]:
            reasons.append('India restriction stated only for a class of FDCs containing some of this FDC\'s components '
                           '(partial disclosure; exact status unclear)')
        if reasons:
            trace.append('F: ' + '; '.join(reasons))
            return 'F'
        if use:
            trace.append('E: current-use claim bound to this FDC: ' + (strong_use or use)[0]['text'])
            return 'E'
        trace.append('C: no current-use claim bound to this FDC')
        return 'C'

    label = decide()
    expected = target_entry['notice'] if target_entry else (subj_match.get('entry') or {}).get('notice')
    notice_checks = []
    for c in claims:
        for n in notice_numbers(c['text']):
            num = re.search(r'\d+', n).group(0)
            owner = entry_by_notice(num)
            notice_checks.append({'claim_id': c['id'], 'cited': n, 'expected': expected,
                                  'status': 'MATCH' if n == expected else ('MISMATCH' if expected else 'UNVERIFIABLE'),
                                  'cited_notice_belongs_to': owner['id'] if owner else None,
                                  'cited_notice_composition': owner['composition'] if owner else None})
    return {
        'subject': {'ingredients': sorted(subject), 'unrecognised_components': list(subject_unknown), 'lead_sentence': lead,
                    'source': subject_source, 'registry_match': subj_match.get('status'),
                    'entry_id': (subj_match.get('entry') or {}).get('id') or subj_match.get('candidate_entry_id'),
                    'match_strength': subj_match.get('match_strength'), 'variant_terms': subj_match.get('variant_terms', []),
                    'entity_vs_target': entity, 'composition_verdict': composition_verdict,
                    'composition_blockers': (comp or {}).get('blockers', [])},
        'reference_index_problems': {'duplicate_indexes': dup_indexes, 'malformed_indexes': malformed_indexes},
        'claims': claims, 'flags': flags, 'scope_mixed': scope_mixed, 'variable_composition': variable_hits,
        'extra_components': extra_components, 'prereg_label': label, 'decision_trace': trace,
        'current_use_strength': 'STRONG' if strong_use else ('WEAK' if use else None),
        'current_use_claim_ids': [c['id'] for c in use], 'restriction_claim_ids': [c['id'] for c in clean_d],
        'notice_checks': notice_checks,
    }
