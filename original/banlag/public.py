"""Public-output contract: the single adapter every HTTP JSON response passes through.

Four kinds of content, kept apart:
  A. OBSERVED      - fields copied from captures (AI text, provider IDs/times, references, organic results, URLs).
  B. REGISTERED    - typed Gazette entries (notice, exact ingredient list, recorded legal text).
  C. MECHANICAL    - deterministic operations over A/B: valid reference_indexes -> captured reference,
                     registry names / notice-number strings literally present, typed set differences.
  D. EXPERIMENTAL  - anything that needs to understand prose (composition, negation, legal events, labels E/D/F,
                     tiers, QUALIFYING, contrast, publication gates). Hypotheses for human review, never facts.

`public()` keeps only ALLOWLISTED A/B/C fields and moves every other field into an `experimental` namespace
(status EXPERIMENTAL_NOT_VERIFIED) wherever it occurs, so no machine verdict can appear as a headline outcome. `legacy_view()` (tests/research only) restores the legacy layout. `observe_answer()` adds the C-kind observations.
Mentions of ingredient names are never treated as an exhaustive ingredient list: registry mappings derived from
them are CANDIDATE mappings; a literal notice-number string is reported as a string match only.
"""
from .claims import _valid_index, reference_index_map
from .legal import find_mentions, notice_numbers, registry

EXP = 'experimental'
EXP_STATUS = 'EXPERIMENTAL_NOT_VERIFIED'
MARK = 'reading_status'

# ALLOWLIST (fail closed). A key is public only if it is listed here; anything else - including every field a future
# change adds - is moved under `experimental`. Allowed keys are A observed capture fields, B typed registry facts,
# C mechanical observations, plus the response envelope. OPAQUE keys hold registry/integrity/provenance data that
# is passed through whole.
ALLOWED = frozenset({
    # envelope / status / plans
    'error', 'public_contract', 'name', 'version', 'serpapi_requests_made', 'capture_mode', 'live_serpapi_enabled',
    'sealed_serpapi_calls_in_store', 'note', 'runs', 'plans', 'store', 'file', 'sha256', 'executed_runs', 'live',
    'sealed_runs', 'project', 'disclaimer', 'engine_version', 'capture_sha256', 'safety_banner', 'spelling_variant_note',
    # A. observed capture: runs, calls, answers, blocks, references, organic results, archived browser records
    'run_id', 'case', 'plan_sha256', 'calls', 'call_id', 'engine', 'origin', 'reasons', 'http_status', 'search_id',
    'provider_created_at', 'raw_sha256', 'query', 'captured_at', 'created_at', 'notice', 'answers', 'surface', 'status',
    'text', 'blocks', 'id', 'type', 'label', 'reference_indexes', 'chips', 'source', 'more', 'unresolved', 'references',
    'index', 'title', 'link', 'snippet', 'url', 'position', 'organic', 'source_cards', 'unknown_block_types',
    'record_id', 'kind', 'pass', 'query_id', 'capture_complete', 'gold_label', 'gold_basis', 'locked_in', 'screenshots',
    'source_file', 'source_sha256', 'uses', 'A', 'B', 'ai_mode', 'controls', 'cases', 'live_runs',
    # B. registry / preregistered human-coded study (single coder)
    'in_family', 'g1_locked', 'g1_positive', 'headline', 'composition', 'pib_item', 'g1',
    # C. mechanical: literal notice-number string checks, reference-index observations, typed set differences
    'notice_checks', 'notice_integrity', 'claim_id', 'cited', 'expected', 'cited_notice_belongs_to', 'cited_notice_composition',
    'observations', 'block_id', 'reference_indexes_as_captured', 'linked_references', 'unlinked_indexes', 'value', 'reason',
    'registry_names_present', 'notice_strings_present', 'string', 'registry_entry', 'text_ends_truncated', 'candidate_entries',
    'all_names_present', 'mapping_status', 'candidate_differences_from_target', 'from_entry', 'from_notice', 'to_entry',
    'to_notice', 'added', 'removed', 'same_set', 'basis', 'target', 'ingredients',
})
OPAQUE = frozenset({'entry', 'corpus', 'legal_source', 'legal_status', 'provenance', 'params', 'plan', 'rule', 'locked',
                    'locked_labels', 'sensitivity', 'summary_table_consistent'})
PASS_ROUTES = frozenset({'/api/registry', '/api/match', '/api/status'})  # typed registry / typed list lookup / server status
UNSAFE_VALUES = frozenset({'SUPPORTED_EXACT', 'QUALIFYING', 'ELIGIBLE_FOR_REVIEW', 'GENERAL_USE_UNWARNED'})

CONTRACT = {
    'version': 2,
    'rule': 'ALLOWLIST: only listed observed, registered and mechanical fields are public; everything else is under "experimental".',
    'observed': 'Copied from captures as stored. A replay without this machine key is ARCHIVED: origin NOT authenticated here.',
    'registered': 'Typed Gazette registry entries (exact ingredient lists, notice numbers); preregistered single-coder study labels.',
    'mechanical': 'Valid reference_indexes -> captured reference; literal registry-name and notice-number strings; typed set differences. '
                  'Name mentions are not an exhaustive ingredient list, so registry mappings from them are CANDIDATE mappings.',
    'experimental_readings': 'Every field under "experimental" is an unverified machine reading of prose (labels, tiers, exactness, '
                             'citation coherence, contrast, publication gate). Not a regulatory conclusion; no human review is recorded.',
    'publication': 'NOT_DETERMINED_BY_SOFTWARE',
}


def public(obj, route=None):
    """Public view of a response: allowlisted fields stay; everything else moves under `experimental`."""
    if route in PASS_ROUTES:
        return obj
    return _filter(obj)


def _filter(obj):
    if isinstance(obj, list):
        return [_filter(v) for v in obj]
    if not isinstance(obj, dict):
        return obj
    out, exp = {}, {}
    for k, v in obj.items():
        if k == EXP and isinstance(v, dict):
            exp.update(v)
        elif k in OPAQUE:
            out[k] = v
        elif k in ALLOWED and not (isinstance(v, str) and v in UNSAFE_VALUES):
            out[k] = _filter(v)
        else:
            exp[k] = v
    if exp:
        exp.pop(MARK, None)
        out[EXP] = {MARK: EXP_STATUS, **exp}
    return out


def legacy_view(obj):
    """Research/test helper (never served): put experimental fields back in their legacy places."""
    if isinstance(obj, list):
        return [legacy_view(v) for v in obj]
    if not isinstance(obj, dict):
        return obj
    exp = obj.get(EXP) if isinstance(obj.get(EXP), dict) else {}
    out = {k: legacy_view(v) for k, v in obj.items() if not (k == EXP and exp)}
    out.update({k: legacy_view(v) for k, v in exp.items() if k != MARK})
    return out


def _entries():
    return registry()['entries']


def _text(r, keys=('title', 'snippet', 'source')):
    return ' '.join(str(r.get(k) or '') for k in keys if isinstance(r.get(k), str))


def _names(text):
    return sorted({m['canonical'] for m in find_mentions(text) if m.get('canonical') and m.get('class') != 'OTHER_ACTIVE'})


def _notices(text):
    by = {e['notice']: e['id'] for e in _entries()}
    return [{'string': n, 'registry_entry': by.get(n)} for n in dict.fromkeys(notice_numbers(text))]


def compare_sets(a, b):
    """Typed comparison of two registry entries (B x B -> C)."""
    sa, sb = set(a['ingredients']), set(b['ingredients'])
    return {'from_entry': a['id'], 'from_notice': a['notice'], 'to_entry': b['id'], 'to_notice': b['notice'],
            'added': sorted(sb - sa), 'removed': sorted(sa - sb), 'same_set': sa == sb, 'basis': 'TYPED_GAZETTE_SETS'}


def observe_reference(r, target=None):
    text = _text(r)
    names = _names(text)
    truncated = any(isinstance(r.get(k), str) and r[k].rstrip().endswith(('...', '…')) for k in ('title', 'snippet'))
    cands = [e for e in _entries() if names and set(e['ingredients']) <= set(names)]
    largest = max((len(e['ingredients']) for e in cands), default=0)
    obs = {'index': r.get('index'), 'title': r.get('title'), 'source': r.get('source'), 'link': r.get('link'), 'snippet': r.get('snippet'),
           'registry_names_present': names, 'notice_strings_present': _notices(text), 'text_ends_truncated': truncated,
           'candidate_entries': [{'entry': e['id'], 'notice': e['notice'], 'all_names_present': True,
                                  'mapping_status': 'CANDIDATE_MAPPING_FROM_NAME_MENTIONS'} for e in cands if len(e['ingredients']) == largest]}
    if target:
        obs['candidate_differences_from_target'] = [dict(compare_sets(target, e), mapping_status='CANDIDATE_MAPPING_FROM_NAME_MENTIONS')
                                                    for e in cands if len(e['ingredients']) == largest and e['id'] != target['id']]
    if truncated or not cands:
        obs['unresolved'] = ('captured text is cut off, so further ingredients may be missing' if truncated
                             else 'captured text names no complete registry set')
    return obs


def observe_answer(blocks, references, target=None):
    """Mechanical observations for one captured answer: block -> valid reference_indexes -> captured reference."""
    refs = [r for r in (references or []) if isinstance(r, dict)]
    unique, dup, _ = reference_index_map(refs)
    ref_obs = {i: observe_reference(r, target) for i, r in unique.items()}
    out = []
    for b in blocks or []:
        if not isinstance(b, dict):
            continue
        idx = b.get('reference_indexes') if isinstance(b.get('reference_indexes'), list) else []
        linked, unlinked = [], []
        for i in idx:
            if not _valid_index(i):
                unlinked.append({'value': repr(i), 'reason': 'MALFORMED_INDEX'})
            elif i in dup:
                unlinked.append({'value': repr(i), 'reason': 'DUPLICATE_REFERENCE_INDEX'})
            elif i not in unique:
                unlinked.append({'value': repr(i), 'reason': 'NO_SUCH_REFERENCE'})
            elif i not in linked:
                linked.append(i)
        text = b.get('text') if isinstance(b.get('text'), str) else ''
        out.append({'block_id': b.get('id'), 'text': text, 'reference_indexes_as_captured': [repr(i) for i in idx],
                    'linked_references': [ref_obs[i] for i in linked], 'unlinked_indexes': unlinked,
                    'registry_names_present': _names(text), 'notice_strings_present': _notices(text)})
    return {'target': ({'entry': target['id'], 'notice': target['notice'], 'ingredients': target['ingredients']} if target else None),
            'blocks': out, 'basis': 'MECHANICAL — string matches and structural index links only; no prose interpretation'}
