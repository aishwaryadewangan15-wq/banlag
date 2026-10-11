"""Evidence engine: normalise a capture, analyse each AI surface at claim level, assign CANDIDATE tiers.

Tier definitions (all candidates; a human reviewer and a legal re-check gate every publication):
  T0  no qualifying omission on this surface
  T1  OBSERVED OMISSION: preregistered label E on this surface (exact FDC established in the AI text, current-use
      claim bound to it, no India restriction bound to it). Strength STRONG/WEAK reported separately.
  T2  SAME-SEARCH DISCOVERABILITY: T1 + an organic result from the SAME search (same response, or a recorded
      page_token parent link) whose own sentence states a restriction on exactly this ingredient set.
  T3  CITED-SOURCE CONTRADICTION: T1 + a page cited by a current-use claim of THIS surface (bound via
      reference_indexes on the same answer) whose independently captured text (local snapshot store only)
      states a restriction on exactly this ingredient set. Imported page text is ASSERTED_UNVERIFIED and never counts.
Organic visibility never proves the model retrieved a page; a cited page never proves why the model wrote its answer.
"""
import datetime as dt
import hashlib
import json
import re

from . import provenance as P
from .citations import coherence
from .claims import CURRENT_YEAR, analyze_surface, restriction_statements, status_question_hint
from .legal import match_formula, registry, find_mentions
from .semantics import EXACT as COMPOSITION_EXACT, restriction_assessment

ENGINE_VERSION = '0.2.0'
DISCLAIMER = ('Research audit only. Each Section 26A notification prohibits the manufacture, sale or distribution of one specific '
              'fixed-dose combination for human use. It does not make it an offence for a patient to have or use a medicine. '
              'This is not medical or legal advice. Do not stop or change any medicine because of this page; speak to your '
              'doctor or pharmacist. Court-order search is non-exhaustive.')
SAFETY_BANNER = {
    'BENZODIAZEPINE': 'Contains a benzodiazepine. Stopping some medicines suddenly can be harmful. Do not stop or change any medicine without advice from your doctor or pharmacist.',
    'DIABETES': 'Diabetes medicine. Do not stop or change any medicine without advice from your doctor or pharmacist.',
    'ANTIBIOTIC': 'Antibiotic. Do not stop a course or change any medicine without advice from your doctor or pharmacist.',
}
PUBLICATION_WINDOW_START = dt.date(2026, 6, 20)
LABEL_IN_TEXT = re.compile(r'^([^:.(][^:.]{1,59}?)\s*:\s+(.+)$', re.S)
MAX_TEXT = 200_000


def _blocks_from_text_blocks(text_blocks, unknown):
    out = []

    def add(kind, label, text, refs):
        if text and str(text).strip():
            text = str(text).strip()
            m = LABEL_IN_TEXT.match(text) if kind != 'heading' else None
            if m and not label:  # 'Dicyclomine : An anticholinergic ...' -> label + text, as in the browser ingest
                label, text = m.group(1).strip(), m.group(2)
            out.append({'id': f'b{len(out)}', 'type': kind, 'label': (label or None), 'text': text[:MAX_TEXT],
                        'reference_indexes': refs if isinstance(refs, list) else None, 'chips': []})

    def walk(items, parent_label=None):
        for tb in items or []:
            if not isinstance(tb, dict):
                continue
            kind = tb.get('type')
            if kind == 'heading':
                add('heading', None, tb.get('snippet'), None)
            elif kind == 'list' or (kind is None and isinstance(tb.get('list'), list) and not tb.get('snippet')):
                list_refs = tb.get('reference_indexes') if isinstance(tb.get('reference_indexes'), list) else []
                for item in tb.get('list') or []:
                    if not isinstance(item, dict):
                        continue
                    title = (item.get('title') or '').strip().rstrip(':') or parent_label
                    own = item.get('reference_indexes') if isinstance(item.get('reference_indexes'), list) else []
                    # A list-level reference_indexes cites the whole list, so each item inherits it. Merge by (type, value):
                    # a malformed False / 0.0 must not collapse into index 0 (banlag.claims validates and refuses it later).
                    merged = list(own) + [x for x in list_refs if not any(type(x) is type(y) and x == y for y in own)]
                    refs = (sorted(merged) if all(type(x) is int for x in merged) else merged) if merged else None
                    add('list_item', title, item.get('snippet'), refs)
                    if isinstance(item.get('list'), list):
                        walk([{'type': 'list', 'list': item['list']}], title)
            elif kind == 'table':
                for row in tb.get('table') or []:
                    if isinstance(row, list) and row:
                        add('table_row', str(row[0]), ' | '.join(str(c) for c in row[1:]), tb.get('reference_indexes'))
            else:
                if kind not in (None, 'paragraph'):
                    unknown.add(str(kind)[:40])
                add('paragraph', parent_label, tb.get('snippet'), tb.get('reference_indexes'))
                if isinstance(tb.get('list'), list):
                    walk([{'type': 'list', 'list': tb['list']}], parent_label)
                if isinstance(tb.get('text_blocks'), list):
                    walk(tb['text_blocks'], parent_label)
    walk(text_blocks)
    return out


def _surface(obj, name):
    """Normalise one AI surface. obj may be a provider response ({'ai_overview': {...}, 'search_metadata'}),
    a bare answer ({'text_blocks', 'references'}), or an AI Mode response."""
    base = {'surface': name, 'status': 'ABSENT', 'blocks': [], 'references': [], 'search_id': None, 'created_at': None,
            'citation_binding': 'UNBOUND', 'unknown_block_types': [], 'page_token': None, 'query': None}
    if not isinstance(obj, dict) or not obj:
        return base
    body = obj.get('ai_overview') if isinstance(obj.get('ai_overview'), dict) else obj
    md = obj.get('search_metadata') if isinstance(obj.get('search_metadata'), dict) else {}
    sp = obj.get('search_parameters') if isinstance(obj.get('search_parameters'), dict) else {}
    base.update(search_id=md.get('id') if isinstance(md.get('id'), str) else None, created_at=md.get('created_at'),
                page_token=sp.get('page_token'), query=sp.get('q'))
    refs = [r for r in (body.get('references') or []) if isinstance(r, dict)]
    base['references'] = [{'index': r.get('index'), 'title': str(r.get('title') or '')[:300], 'link': r.get('link'),
                           'snippet': str(r.get('snippet') or '')[:600], 'source': r.get('source')} for r in refs]
    unknown = set()
    if isinstance(body.get('text_blocks'), list):
        base['blocks'] = _blocks_from_text_blocks(body['text_blocks'], unknown)
    elif isinstance(body.get('reconstructed_markdown'), str):
        lines = [l.strip(' #*-') for l in body['reconstructed_markdown'][:MAX_TEXT].split('\n') if l.strip(' #*-')]
        base['blocks'] = [{'id': f'b{i}', 'type': 'paragraph', 'label': None, 'text': l, 'reference_indexes': None, 'chips': []}
                          for i, l in enumerate(lines)]
    if body.get('error') and not base['blocks']:
        base['status'] = 'PROVIDER_ERROR'
        base['error'] = str(body['error'])[:200]
        return base
    base['unknown_block_types'] = sorted(unknown)
    if base['blocks']:
        base['status'] = 'PRESENT'
        bound = any(b.get('reference_indexes') is not None for b in base['blocks'])
        base['citation_binding'] = 'REFERENCE_INDEX_BOUND' if bound and refs else 'UNBOUND'
    return base


def legacy_classification(analysis, target_known):
    label, strength = analysis['prereg_label'], analysis['current_use_strength']
    if label == 'A':
        return 'NO_AI_ANSWER'
    if not target_known:
        return 'ENTITY_OR_SCOPE_UNKNOWN'
    return {'B': 'ENTITY_MENTION_UNVERIFIED', 'D': 'RESTRICTION_MENTIONED', 'F': 'UNCERTAIN_REVIEW',
            'E': 'STRONG_CURRENT_USE_UNWARNED' if strength == 'STRONG' else 'GENERAL_USE_UNWARNED',
            'C': 'HISTORICAL_DESCRIPTION' if any('HISTORICAL' in c['types'] for c in analysis['claims']) else 'INSUFFICIENT_EVIDENCE'}[label]


def _organic(google, query, aio_surface, inline):
    """Organic results and whether they are bound to the same search as the AI Overview."""
    if not isinstance(google, dict):
        return [], {'status': 'NO_ORGANIC_CAPTURE'}
    rows = [{'position': r.get('position'), 'title': str(r.get('title') or '')[:300], 'snippet': str(r.get('snippet') or '')[:800],
             'url': r.get('link') or ''} for r in (google.get('organic_results') or []) if isinstance(r, dict)]
    md = google.get('search_metadata') if isinstance(google.get('search_metadata'), dict) else {}
    sp = google.get('search_parameters') if isinstance(google.get('search_parameters'), dict) else {}
    gid, gq = md.get('id'), sp.get('q')
    if gq is not None and query is not None and gq != query:
        return rows, {'status': 'MIXED_QUERY', 'detail': f'organic results are for {gq!r}, capture query is {query!r}'}
    if inline:
        return rows, {'status': 'SAME_RESPONSE', 'search_id': gid}
    if aio_surface['status'] != 'PRESENT':
        return rows, {'status': 'NO_AI_OVERVIEW'}
    gtoken = ((google.get('ai_overview') or {}) if isinstance(google.get('ai_overview'), dict) else {}).get('page_token')
    if gtoken and aio_surface.get('page_token') == gtoken:
        return rows, {'status': 'PAGE_TOKEN_LINK_DECLARED', 'search_id': gid}
    if gid and aio_surface.get('search_id') == gid:
        return rows, {'status': 'SAME_SEARCH_ID_DECLARED', 'search_id': gid}
    return rows, {'status': 'BINDING_UNKNOWN', 'detail': 'organic results are not provably from the same search as the AI answer'}


def _cited_pages(payload, verified_snapshots):
    pages = []
    for src in payload.get('cited_page_captures') or []:
        if isinstance(src, dict):
            pages.append({'url': src.get('url'), 'text': str(src.get('source_text') or '')[:MAX_TEXT], 'verification': 'ASSERTED_UNVERIFIED',
                          'declared_capture_time': src.get('capture_time'), 'declared_method': src.get('capture_method')})
    for snap in verified_snapshots or []:
        pages.append({'url': snap['url'], 'text': snap['text'], 'verification': 'LOCAL_SNAPSHOT_VERIFIED',
                      'snapshot_sha256': snap.get('sha256'), 'fetched_at': snap.get('fetched_at')})
    return pages


def _why_not(assessment):
    """Short WHY-NOT trace of one evidence text's restriction events (no confidence scores)."""
    comp = assessment['composition']
    out = [f"{w['event_id']} '{w['term']}': " + '; '.join(w['why_not']) for w in assessment['why_not']][:6]
    if comp['verdict'] != COMPOSITION_EXACT:
        out.insert(0, f"text composition {comp['verdict']}: " + '; '.join(comp['blockers'][:2]))
    return out


def assess_surface(surface, entry, organic_rows, organic_binding, pages, origin, capture_complete=True, subject_hint=None, as_of=None):
    analysis = analyze_surface(surface['blocks'], surface['references'], surface['citation_binding'], entry, capture_complete, as_of=as_of)
    tier, basis = 0, []
    t2, t3, pages_out, organic_checked = [], [], [], []
    if entry and analysis['prereg_label'] == 'E':
        tier = 1
        basis.append(f"T1: label E, {analysis['current_use_strength']} current-use claim(s) {analysis['current_use_claim_ids']} bound to the exact FDC; no India restriction bound to it.")
        if surface['surface'] == 'AI_OVERVIEW' and organic_binding.get('status') in ('SAME_RESPONSE', 'PAGE_TOKEN_LINK_DECLARED', 'PAGE_TOKEN_LINK_VERIFIED', 'SAME_SEARCH_ID_DECLARED'):
            for r in organic_rows:
                a = restriction_assessment(r['title'] + '. ' + r['snippet'], entry, r['url'], as_of=as_of)
                if a['statements']:
                    t2.append({'position': r['position'], 'url': r['url'], 'statements': a['statements']})
                elif a['events'] or a['composition']['verdict'] not in (COMPOSITION_EXACT, 'NOT_ESTABLISHED'):
                    organic_checked.append({'position': r['position'], 'url': r['url'], 'why_not': _why_not(a)})
            if t2:
                tier = 2
                basis.append(f"T2: {len(t2)} same-search organic result(s) state the exact restriction ({organic_binding['status']}).")
        use_ids = set(analysis['current_use_claim_ids'])
        bound_urls = {ref['link'] for c in analysis['claims'] if c['id'] in use_ids
                      for ref in c['citations']['references'] if ref.get('link')}
        for p in pages:
            a = restriction_assessment(p['text'], entry, p['url'], as_of=as_of)
            hits = a['statements']
            rec = {'url': p['url'], 'verification': p['verification'], 'bound_to_current_use_claim_on_this_surface': p['url'] in bound_urls,
                   'states_exact_restriction': bool(hits), 'statements': hits[:3], 'why_not': [] if hits else _why_not(a)}
            pages_out.append(rec)
            if rec['bound_to_current_use_claim_on_this_surface'] and hits and p['verification'] == 'LOCAL_SNAPSHOT_VERIFIED':
                t3.append(rec)
        if t3:
            tier = 3
            basis.append(f'T3: {len(t3)} independently snapshotted page(s) cited by this surface\'s current-use claim state the exact restriction.')
    coh = coherence(analysis, surface['references']) if surface['citation_binding'] == 'REFERENCE_INDEX_BOUND' else None
    return {'analysis': analysis, 'tier': tier, 'tier_basis': basis, 'tier2_hits': t2, 'tier3_hits': t3, 'cited_page_assessment': pages_out,
            'citation_coherence': coh, 'organic_not_qualifying': organic_checked}


def publication_gate(origin, formula, captured_at, capture_complete, legal_status, now=None, text_composition=None):
    """text_composition: composition verdicts of the AI surfaces that have text. If none of them is SUPPORTED_EXACT the
    capture is withheld: a declared target and an authentic seal never make an altered or unresolved formulation reviewable."""
    now = now or dt.datetime.now(dt.timezone.utc)
    reasons, conditions = [], ['HUMAN_REVIEW_REQUIRED']
    # Fail closed: every caller must supply the composition verdicts it checked. Missing or empty input is not a pass.
    if text_composition is None:
        reasons.append('COMPOSITION_VALIDATION_MISSING')
    elif not text_composition:
        reasons.append('NO_AI_TEXT_COMPOSITION_ESTABLISHED')
    elif COMPOSITION_EXACT not in text_composition:
        reasons.append('TEXT_COMPOSITION_NOT_SUPPORTED_EXACT (' + ', '.join(sorted({str(v) for v in text_composition})) + ')')
    if origin in (P.SYNTHETIC, P.USER):
        reasons.append('UNVERIFIED_ORIGIN')
    elif origin == P.ARCHIVED_SERPAPI:
        reasons.append('ORIGIN_UNAUTHENTICATED_HERE (seal needs the collector machine key)')
    elif origin == P.BROWSER_ARCHIVE:
        conditions.append('ORIGIN_NOT_CRYPTOGRAPHICALLY_AUTHENTICATED: reviewer must accept the preregistered archive chain of custody '
                          '(locked preregistration, lock records, archive manifest)')
    elif origin != P.TRUSTED:
        reasons.append('UNKNOWN_ORIGIN')
    if formula.get('status') == 'CONTESTED_SYNONYM_CANDIDATE':
        reasons.append('CONTESTED_SYNONYM')
    elif formula.get('status') != 'EXACT_NOTIFICATION_MATCH':
        reasons.append('NOT_EXACT_COMPOSITION')
    cap = P.parse_iso(captured_at) if isinstance(captured_at, str) else None
    if cap is None:
        reasons.append('CAPTURE_TIME_UNVERIFIED')
    elif cap.date() < PUBLICATION_WINDOW_START:
        reasons.append('PRE_PUBLICATION_WINDOW')
    if not capture_complete:
        reasons.append('CAPTURE_INCOMPLETE')
    as_of = dt.date.fromisoformat(legal_status['as_of'])
    age = (now.date() - as_of).days
    if age > legal_status['recheck_max_age_days']:
        reasons.append(f'LEGAL_RECHECK_REQUIRED (status is {age} days old)')
    if formula.get('match_strength') == 'SPELLING_VARIANT':
        conditions.append('REVIEWER_CONFIRMS_SPELLING_VARIANT: ' + ', '.join(formula.get('variant_terms', [])))
    return {'decision': 'WITHHOLD' if reasons else 'ELIGIBLE_FOR_REVIEW', 'withhold_reasons': reasons, 'conditions': conditions,
            'legal_status_age_days': age}


def _query_consistency(query, ingredients):
    if not isinstance(query, str) or not query.strip():
        return {'status': 'NO_QUERY'}
    named = {m['canonical'] for m in find_mentions(query)}
    hits = [h for h in (match_formula(ingredients).get('entry') or {}).get('ingredients', [])]
    if not hits:
        return {'status': 'NOT_ASSESSED', 'query_mentions': sorted(named)}
    return {'status': 'CONSISTENT' if named == set(hits) else 'MISMATCH', 'query_mentions': sorted(named), 'declared': sorted(hits)}


def evaluate_run(run_id, store=None, key_path=None, now=None):
    """Evaluate one sealed collector run. Only a fully verified run is TRUSTED; any invalid call fails closed."""
    from . import capture_store
    payload, prov = capture_store.bundle_payload(run_id, store or capture_store.STORE, key_path or capture_store.KEY_PATH)
    if prov['origin'] == 'INVALID':
        return {'project': 'BANLAG', 'run_id': run_id, 'origin': 'INVALID', 'provenance': prov, 'evidence_tier': 0,
                'verified_evidence_tier': 0, 'release_status': 'INVALID_CAPTURE - NOT EVIDENCE'}
    if not payload.get('ingredients'):
        raise ValueError('run has no declared ingredient set')
    r = evaluate(payload, now=now, origin_override=prov)
    if r['organic_binding'].get('status') == 'PAGE_TOKEN_LINK_DECLARED' and any(l.get('page_token_link') == 'VERIFIED' for l in prov['linkage']):
        r['organic_binding']['status'] = 'PAGE_TOKEN_LINK_VERIFIED'
    r['run_id'] = run_id
    return r


def evaluate(payload, now=None, verified_snapshots=None, origin_override=None):
    """Assess one capture. Imports are always USER_SUPPLIED_UNVERIFIED (or SYNTHETIC_FIXTURE); see provenance.py."""
    if not isinstance(payload, dict):
        raise ValueError('Expected a JSON object.')
    kind = payload.get('source_kind')
    if kind not in P.DECLARED_KINDS:
        raise ValueError('Explicit source_kind required (SYNTHETIC_TEST, BROWSER_RESEARCH or SERPAPI_LIVE_CAPTURE).')
    now = now or dt.datetime.now(dt.timezone.utc)
    prov = origin_override or P.assess_import(payload, now)
    origin = prov['origin']
    db = registry()
    formula = match_formula(payload.get('ingredients'))
    entry = formula.get('entry')
    query = payload.get('query') if isinstance(payload.get('query'), str) else None
    google = payload.get('google') if isinstance(payload.get('google'), dict) else None
    inline = google is not None and isinstance(google.get('ai_overview'), dict) and isinstance(google['ai_overview'].get('text_blocks'), list) \
        and not (isinstance(payload.get('ai_overview'), dict) and payload.get('ai_overview'))
    aio = _surface(google if inline else payload.get('ai_overview'), 'AI_OVERVIEW')
    mode = _surface(payload.get('ai_mode'), 'AI_MODE')
    organic_rows, organic_binding = _organic(google, query, aio, inline)
    pages = _cited_pages(payload, verified_snapshots)
    complete = payload.get('capture_complete', True) is not False
    cap_time = P.parse_iso(payload.get('captured_at')) if isinstance(payload.get('captured_at'), str) else None
    as_of = cap_time.year if cap_time else CURRENT_YEAR  # dates are judged as of the evidence, not the clock
    answers, best = [], None
    for surf, engine_name in ((aio, 'ai_overview'), (mode, 'ai_mode')):
        res = assess_surface(surf, entry, organic_rows, organic_binding, pages, origin, complete, as_of=as_of)
        a = res['analysis']
        text = '\n'.join(((b['label'] + ': ') if b.get('label') else '') + b['text'] for b in surf['blocks'] if b['type'] != 'heading')
        answers.append({'surface': 'AI Overview' if engine_name == 'ai_overview' else 'AI Mode', 'engine': engine_name,
                        'status': surf['status'], 'classification': legacy_classification(a, bool(entry)),
                        'prereg_label': a['prereg_label'], 'current_use_strength': a['current_use_strength'],
                        'explicit_exact_entity': a['subject']['entity_vs_target'] == 'EXACT',
                        'text': text, 'references': surf['references'], 'search_id': surf['search_id'], 'created_at': surf['created_at'],
                        'citation_binding': surf['citation_binding'], 'unknown_block_types': surf['unknown_block_types'],
                        'analysis': a, 'tier': res['tier'], 'tier_basis': res['tier_basis'], 'tier2_hits': res['tier2_hits'],
                        'tier3_hits': res['tier3_hits'], 'cited_page_assessment': res['cited_page_assessment'],
                        'organic_not_qualifying': res['organic_not_qualifying'],
                        'citation_coherence': res['citation_coherence'], 'blocks': surf['blocks']})
        if best is None or res['tier'] > best['tier']:
            best = answers[-1]
    tier = best['tier'] if best else 0
    # Explicit status prompt (separate question): only a separately captured answer; never merged into tiers.
    status_q = payload.get('explicit_status_query') if isinstance(payload.get('explicit_status_query'), dict) else {}
    status_text = status_q.get('answer_text') if isinstance(status_q.get('answer_text'), str) else ''
    status_label, status_hint_note = None, None
    if status_text.strip() and entry:
        blocks = [{'id': 'b0', 'type': 'paragraph', 'label': None, 'text': status_text[:MAX_TEXT], 'chips': []}]
        hint, status_hint_note = status_question_hint(status_q.get('query'), entry)
        sa = analyze_surface(blocks, target_entry=entry, subject_hint=hint, as_of=as_of)
        status_label = sa['prereg_label']
    status_capture = None
    sc = payload.get('status_capture') if isinstance(payload.get('status_capture'), dict) else None
    if sc and entry:
        ss = _surface(sc, 'AI_OVERVIEW')
        s_rows, _ = _organic(sc, None, ss, True)
        organic_hits = [{'position': r['position'], 'url': r['url'], 'statements': h} for r in s_rows
                        for h in [restriction_statements(r['title'] + '. ' + r['snippet'], entry, r['url'], as_of=as_of)] if h]
        hint, status_hint_note = status_question_hint((sc.get('search_parameters') or {}).get('q'), entry)
        sa = analyze_surface(ss['blocks'], ss['references'], ss['citation_binding'], entry, True, hint,
                             as_of=as_of) if ss['status'] == 'PRESENT' else None
        status_label = sa['prereg_label'] if sa else None
        status_capture = {'query': (sc.get('search_parameters') or {}).get('q'), 'search_id': ss['search_id'],
                          'ai_overview_status': ss['status'] if ss['status'] != 'ABSENT' else
                          ('PAGE_TOKEN_NOT_FETCHED' if (sc.get('ai_overview') or {}).get('page_token') else 'NO_AI_OVERVIEW'),
                          'label': status_label, 'question_validation': status_hint_note,
                          'composition_verdict': sa['subject']['composition_verdict'] if sa else None,
                          'notice_checks': sa['notice_checks'] if sa else [],
                          'organic_exact_restriction_hits': organic_hits}
    # A status contrast needs (a) a qualifying uses-answer observation, (b) a separately asked question that was supplied and
    # names exactly the target, and (c) a definitive D on that answer. It never changes any tier.
    contrast_why_not = [w for w, bad in (('no qualifying uses-answer observation (tier 0)', not tier),
                                         (f'status question not validated ({status_hint_note})', status_hint_note != 'STATUS_QUESTION_NAMES_EXACT_TARGET'),
                                         (f'status answer is not a definitive current Indian restriction (label {status_label})', status_label != 'D'))
                        if bad] if (status_label is not None or status_hint_note) else ['no separate status answer']
    contrast = not contrast_why_not
    sha = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    explanations = {0: 'No qualifying omission established on any surface from the supplied record.',
                    1: 'Observed omission: the AI text establishes the exact FDC and describes current use without any India restriction bound to it.',
                    2: 'T1 plus a same-search organic result that itself states the exact restriction. Organic visibility does not prove AI retrieval.',
                    3: 'T1 plus an independently snapshotted page, cited by the same claim, that states the exact restriction. Does not prove model reasoning.'}
    # Only an authenticated origin (a seal verified with this machine's key) is provenance-verified. Hash-consistent archives
    # replay honestly but stay unauthenticated: their tier is reported separately as replay_evidence_tier.
    provenance_backed = origin == P.TRUSTED
    replay = origin in (P.BROWSER_ARCHIVE, P.ARCHIVED_SERPAPI)
    notices = [dict(n, surface=a['surface']) for a in answers for n in a['analysis']['notice_checks']]
    cited_legacy = [{'url': c['url'], 'has_documented_capture': c['verification'] == 'LOCAL_SNAPSHOT_VERIFIED',
                     'verification': c['verification'],
                     'exact_restriction_explicitly_present': c['states_exact_restriction'] and c['verification'] == 'LOCAL_SNAPSHOT_VERIFIED',
                     'asserted_text_states_exact_restriction': c['states_exact_restriction'] and c['verification'] != 'LOCAL_SNAPSHOT_VERIFIED',
                     'bound_to_current_use_claim': c['bound_to_current_use_claim_on_this_surface']}
                    for c in (best['cited_page_assessment'] if best and best['cited_page_assessment'] else
                              [{'url': p['url'], 'verification': p['verification'],
                                'states_exact_restriction': bool(entry and restriction_statements(p['text'], entry, p['url'], as_of=as_of)),
                                'bound_to_current_use_claim_on_this_surface': False} for p in pages])]
    verdicts = [a['analysis']['subject'].get('composition_verdict') for a in answers
                if a['status'] == 'PRESENT' and a['analysis']['subject'].get('composition_verdict')]
    gate = publication_gate(origin, formula, payload.get('captured_at'), complete, db['legal_status'], now, text_composition=verdicts)
    return {
        'project': 'BANLAG', 'engine_version': ENGINE_VERSION,
        'provenance': prov, 'origin': origin, 'source_kind': kind, 'captured_at': payload.get('captured_at'),
        'query': query or '', 'query_consistency': _query_consistency(query, payload.get('ingredients')),
        'capture_sha256': sha, 'formulation': formula, 'answers': answers,
        'organic': organic_rows, 'organic_binding': organic_binding, 'cited_pages': cited_legacy,
        'evidence_tier': tier, 'tier_basis': best['tier_basis'] if best else [],
        'tier_status': {P.SYNTHETIC: 'SYNTHETIC_FIXTURE', P.USER: 'UNVERIFIED_INPUT', P.BROWSER_ARCHIVE: 'ARCHIVE_REPLAY_ORIGIN_UNAUTHENTICATED',
                        P.ARCHIVED_SERPAPI: 'ARCHIVE_REPLAY_ORIGIN_UNAUTHENTICATED', P.TRUSTED: 'PROVENANCE_VERIFIED'}[origin],
        'verified_evidence_tier': tier if provenance_backed else 0,
        'replay_evidence_tier': tier if replay else 0,
        'tier_explanation': explanations[tier],
        'explicit_status_contrast': contrast, 'status_contrast_why_not': contrast_why_not,
        'status_answer_label': status_label, 'status_question_validation': status_hint_note,
        'status_capture': status_capture,
        'notice_integrity': notices,
        'legal_source': db['source'], 'legal_status': db['legal_status'], 'publication_gate': gate,
        'safety_banner': SAFETY_BANNER.get((entry or {}).get('safety_banner')),
        'release_status': ('SYNTHETIC - NOT EVIDENCE' if origin == P.SYNTHETIC else
                           'CANDIDATE - HUMAN_REVIEW_REQUIRED' if tier else 'NOT_A_QUALIFYING_FINDING'),
        'disclaimer': DISCLAIMER,
    }
