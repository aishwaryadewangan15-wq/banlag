"""Independent witness verifier. Deliberately shares NO code with core/ (stdlib only, no project imports).

It re-reads the frozen register, independently checks that the register is canonical, validates EVERY
witness field and per-status invariant before any status logic, recomputes the register digest, the
candidate set, the optimal worst-case depth (iterative deepening on a decision predicate, a different method
from the production dynamic programme), the canonical question under the frozen tie rule, and both partitions.
Any mismatch is a FAIL.

    python -I -B verifier/independent.py --registry data/registry_scope.json [--mode strict|tie_valid]
        [--expect-facts '{"present": [...], "absent": [...], "label_completeness": ..., "provenance": {...},
                          "unresolved_inputs": [...]}'] < witness.json
A witness and its own digest cannot certify their own input facts or registry. Without --expect-facts the
verifier proves only that the witness is correct FOR ITS OWN STATED FACTS; binding to the caller's
independent record of the asserted facts (terms, and provenance / unresolved inputs when supplied) is what
detects re-sealed fact edits. The registry is always supplied independently by the caller.
Exit code 0 = PASS / PASS_TIE_VALID, 1 = FAIL, 2 = usage error.
"""
import hashlib
import json
import sys
import unicodedata

VERIFIER_VERSION = 'omf-independent-verifier-1.2.0'
EXPECTED_SCHEMA = 'omf.witness.v1'
EXPECTED_TIE_RULE = 'min_depth>min_worst_branch_size>min_name_codepoint'
EXPECTED_CAVEAT = ('Finite model of 10 of the 16 June-2026 notified FDCs (original BANLAG register). '
                   'FORMULATION-NOTICE SCOPE only: not a product identification, legal status, or medical or legal advice. '
                   'Anything outside the modeled register cannot be matched or cleared.')
KNOWN_SOLVERS = {'omf-minimax-1.0.0'}
ACCEPTABLE_PROVENANCE = {'HYPOTHETICAL', 'USER_ASSERTED', 'SYNTHETIC_TEST'}
UNRESOLVED_REASONS = {'CONTESTED_SYNONYM'}
STATUSES = {'NEXT_QUESTION', 'SINGLE_MODELED_CANDIDATE', 'OUTSIDE_MODELED_REGISTER_OR_CONFLICT',
            'INDISTINGUISHABLE', 'CONFLICT'}
WITNESS_KEYS = {'schema', 'solver_version', 'register_id', 'register_digest', 'tie_rule', 'facts', 'status',
                'candidate_ids', 'question', 'partition', 'unknown_answer_keeps', 'worst_case_depth',
                'indistinguishable_groups', 'caveat', 'witness_digest'}
FACT_KEYS = {'present', 'absent', 'label_completeness', 'unresolved_inputs'}
MAX_WITNESS_BYTES = 65536
MAX_CASES = 32
MAX_FACTS = 24
_HEXDIGITS = set('0123456789abcdef')
_TERM_FIRST = set('abcdefghijklmnopqrstuvwxyz0123456789')
_TERM_REST = _TERM_FIRST | set(" -'().,")
_ID_CHARS = set('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-')


def _hex64(v):
    return isinstance(v, str) and len(v) == 64 and set(v) <= _HEXDIGITS


def _term_chars(t):
    return bool(t) and t[0] in _TERM_FIRST and set(t) <= _TERM_REST


def _id_ok(x):
    """Written contract docs/ID_GRAMMAR.md: ASCII letters/digits/'_'/'-', 1..64 chars, case-sensitive."""
    return isinstance(x, str) and 1 <= len(x) <= 64 and set(x) <= _ID_CHARS


class Reject(Exception):
    pass


def _no_dupes(pairs):
    keys = [k for k, _ in pairs]
    if len(keys) != len(set(keys)):
        raise Reject('duplicate JSON key')
    return dict(pairs)


def _canon(obj):
    return json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')


def _sha(b):
    return hashlib.sha256(b).hexdigest()


def _reg_digest(cases):
    rows = [{'id': c['id'], 'ingredients': sorted(c['ingredients'])} for c in cases]
    rows.sort(key=lambda r: r['id'])
    return _sha(_canon({'schema': 'omf.register.v1', 'cases': rows}))


def _is_norm(t):
    if not isinstance(t, str) or not t or len(t) > 80:
        return False
    n = ' '.join(unicodedata.normalize('NFKC', t).casefold().split())
    return n == t and '+' not in t and _term_chars(t)


def _is_int(v, expected):
    return type(v) is int and v == expected


def _ids(v, what):
    if not isinstance(v, list) or any(not _id_ok(x) for x in v):
        raise Reject(f'{what} must be a list of ids')
    if len(set(v)) != len(v):
        raise Reject(f'{what} contains duplicate ids')
    if v != sorted(v):
        raise Reject(f'{what} not in canonical order')
    return v


def _sorted_unique_ids(v, universe, what):
    _ids(v, what)
    if not set(v) <= universe:
        raise Reject(f'{what} contains ids outside the register')
    return set(v)


def check_registry(registry):
    """Independent canonical-register check (does not trust any solver or loader)."""
    if not isinstance(registry, dict):
        raise Reject('registry unusable')
    cases = registry.get('cases')
    if not isinstance(cases, list) or not cases or len(cases) > MAX_CASES:
        raise Reject('registry unusable')
    aliases = registry.get('aliases', {})
    other = registry.get('other_actives', {})
    if not isinstance(aliases, dict) or not isinstance(other, dict):
        raise Reject('registry alias tables malformed')
    rows, vocab = {}, set()
    for c in cases:
        if not isinstance(c, dict) or not _id_ok(c.get('id')) or c['id'] in rows:
            raise Reject('registry row id invalid or duplicated')
        ing = c.get('ingredients')
        if not isinstance(ing, list) or not ing or len(ing) > 16 or len(set(ing)) != len(ing):
            raise Reject('registry row ingredients invalid')
        for i in ing:
            if not _is_norm(i):
                raise Reject('registry is not canonical: non-normalized ingredient')
            if i in aliases:
                raise Reject('registry is not canonical: an alias name is used as a row ingredient')
        rows[c['id']] = frozenset(ing)
        vocab |= set(ing)
    for k, v in aliases.items():
        if not isinstance(v, dict) or v.get('class') not in ('SPELLING_VARIANT', 'CONTESTED_PROBIOTIC'):
            raise Reject('registry alias entry malformed')
        if v['class'] == 'SPELLING_VARIANT' and v.get('canonical') not in vocab:
            raise Reject('registry is not canonical: spelling variant points outside the vocabulary')
    outside = set(other) | {a for vs in other.values() if isinstance(vs, list) for a in vs}
    if outside & vocab or outside & set(aliases):
        raise Reject('registry is not canonical: outside-register actives collide with register names')
    return rows


def validate_schema(w):
    """Every field, every status: types, domains and per-status invariants, before any recomputation."""
    if not isinstance(w, dict) or set(w) != WITNESS_KEYS:
        raise Reject('witness fields differ from schema')
    if w['schema'] != EXPECTED_SCHEMA:
        raise Reject('unexpected witness schema')
    if w['solver_version'] not in KNOWN_SOLVERS:
        raise Reject('unknown solver version')
    if w['tie_rule'] != EXPECTED_TIE_RULE:
        raise Reject('tie rule differs from the frozen rule')
    if w['caveat'] != EXPECTED_CAVEAT:
        raise Reject('outside-model caveat missing or altered')
    for k in ('register_digest', 'witness_digest'):
        if not _hex64(w[k]):
            raise Reject(f'{k} malformed')
    if not _id_ok(w['register_id']):
        raise Reject('register_id malformed')
    if w['status'] not in STATUSES:
        raise Reject('unknown status')
    f = w['facts']
    if not isinstance(f, dict) or set(f) != FACT_KEYS:
        raise Reject('facts fields differ from schema')
    if f['label_completeness'] not in ('NOT_ESTABLISHED', 'USER_ASSERTED_COMPLETE'):
        raise Reject('unknown completeness label')
    for side in ('present', 'absent'):
        if not isinstance(f[side], list) or len(f[side]) > MAX_FACTS:
            raise Reject(f'{side} must be a short list')
        for it in f[side]:
            if not isinstance(it, dict) or set(it) != {'term', 'provenance'}:
                raise Reject('fact entry malformed')
            if it['provenance'] not in ACCEPTABLE_PROVENANCE:
                raise Reject('provenance is not an acceptable product-fact source')
            if not _is_norm(it['term']):
                raise Reject('fact term not canonical')
        terms = [it['term'] for it in f[side]]
        if terms != sorted(terms) or len(set(terms)) != len(terms):
            raise Reject(f'{side} facts not canonical (order or duplicates)')
    u = f['unresolved_inputs']
    if not isinstance(u, list) or len(u) > 2 * MAX_FACTS:
        raise Reject('unresolved_inputs must be a short list')
    for it in u:
        if not isinstance(it, dict) or set(it) != {'input', 'side', 'reason'}:
            raise Reject('unresolved input entry malformed')
        if it['side'] not in ('present', 'absent') or it['reason'] not in UNRESOLVED_REASONS or not _is_norm(it['input']):
            raise Reject('unresolved input entry has invalid side, reason or text')
    _ids(w['candidate_ids'], 'candidate_ids')
    g = w['indistinguishable_groups']
    if not isinstance(g, list) or any(not isinstance(x, list) or len(x) < 2 for x in g):
        raise Reject('indistinguishable_groups malformed')
    for x in g:
        _ids(x, 'indistinguishable group')
    q, part, unk, depth = w['question'], w['partition'], w['unknown_answer_keeps'], w['worst_case_depth']
    if q is not None and not _is_norm(q):
        raise Reject('question malformed')
    if part is not None:
        if not isinstance(part, dict) or set(part) != {'yes', 'no'}:
            raise Reject('partition malformed')
        _ids(part['yes'], 'yes')
        _ids(part['no'], 'no')
    if unk is not None:
        _ids(unk, 'unknown_answer_keeps')
    if depth is not None and (type(depth) is not int or depth < 0):
        raise Reject('worst_case_depth malformed')
    st, n = w['status'], len(w['candidate_ids'])
    none4 = (q is None and part is None and unk is None)
    rules = {
        'CONFLICT': n == 0 and none4 and depth is None and g == [],
        'OUTSIDE_MODELED_REGISTER_OR_CONFLICT': n == 0 and none4 and depth is None and g == [],
        'SINGLE_MODELED_CANDIDATE': n == 1 and none4 and _is_int(depth, 0) and g == [],
        'INDISTINGUISHABLE': n >= 2 and none4 and depth is None and g != [],
        'NEXT_QUESTION': n >= 2 and q is not None and part is not None and unk is not None and
                         type(depth) is int and depth >= 1 and g == [],
    }
    if not rules[st]:
        raise Reject(f'fields inconsistent with status {st}')


def _bind_facts(f, expected):
    """Compare the witness's facts with the caller's own independent record of what was asserted."""
    if not isinstance(expected, dict) or set(expected) - {'present', 'absent', 'label_completeness',
                                                         'provenance', 'unresolved_inputs'}:
        raise Reject('expected_facts malformed')
    for side in ('present', 'absent'):
        exp = expected.get(side, [])
        if not isinstance(exp, list) or any(not isinstance(t, str) for t in exp):
            raise Reject('expected_facts malformed')
        if sorted(exp) != [it['term'] for it in f[side]]:
            raise Reject(f'witness {side} facts differ from the caller-asserted facts')
    if expected.get('label_completeness', 'NOT_ESTABLISHED') != f['label_completeness']:
        raise Reject('witness completeness differs from the caller-asserted value')
    if 'provenance' in expected:
        prov = expected['provenance']
        if not isinstance(prov, dict):
            raise Reject('expected_facts malformed')
        got = {f'{side}:{it["term"]}': it['provenance'] for side in ('present', 'absent') for it in f[side]}
        if prov != got:
            raise Reject('witness fact provenance differs from the caller record')
    if 'unresolved_inputs' in expected:
        exp_u = expected['unresolved_inputs']
        if not isinstance(exp_u, list):
            raise Reject('expected_facts malformed')
        key = lambda it: (it.get('side'), it.get('input'), it.get('reason')) if isinstance(it, dict) else ('', '', '')  # noqa: E731
        if sorted(map(key, exp_u)) != sorted(map(key, f['unresolved_inputs'])):
            raise Reject('witness unresolved inputs differ from the caller record')


class Tree:
    """Decision predicate: can the candidate set be separated within k worst-case questions?"""

    def __init__(self, rows):
        self.rows = rows
        self.vocab = sorted({i for s in rows.values() for i in s})
        self.memo = {}

    def splits(self, C):
        out = []
        for a in self.vocab:
            yes = frozenset(r for r in C if a in self.rows[r])
            no = C - yes
            if yes and no:
                out.append((a, yes, no))
        return out

    def can(self, C, k):
        if len(C) <= 1:
            return True
        if k == 0:
            return False
        key = (C, k)
        if key not in self.memo:
            self.memo[key] = any(self.can(y, k - 1) and self.can(n, k - 1) for _a, y, n in self.splits(C))
        return self.memo[key]

    def optimum(self, C):
        if len({self.rows[r] for r in C}) < len(C):
            return None
        k = 0
        while not self.can(C, k):
            k += 1
            if k > len(C):
                raise Reject('internal: depth bound exceeded')
        return k


def verify(witness, registry, mode='strict', expected_facts=None):
    checks = []

    def ok(name):
        checks.append(name)

    if mode not in ('strict', 'tie_valid'):
        raise Reject('unknown mode')
    validate_schema(witness)
    ok('full witness schema and per-status invariants')
    body = {k: v for k, v in witness.items() if k != 'witness_digest'}
    if _sha(_canon(body)) != witness['witness_digest']:
        raise Reject('witness digest mismatch')
    ok('witness digest')

    rows = check_registry(registry)
    ok('registry canonical (independent check)')
    if not _id_ok(registry.get('register_id')) or witness['register_id'] != registry.get('register_id'):
        raise Reject('register id mismatch')
    if witness['register_digest'] != _reg_digest(registry['cases']):
        raise Reject('register digest mismatch')
    ok('register digest')

    f = witness['facts']
    P = [it['term'] for it in f['present']]
    N = [it['term'] for it in f['absent']]
    if f['label_completeness'] == 'USER_ASSERTED_COMPLETE' and any(
            it['provenance'] != 'USER_ASSERTED' for it in f['present']):
        raise Reject('complete-label claim without user assertion')
    ok('facts and provenance')
    if expected_facts is not None:
        _bind_facts(f, expected_facts)
        ok('facts bound to caller record')

    status = witness['status']
    universe = set(rows)
    cand = _sorted_unique_ids(witness['candidate_ids'], universe, 'candidate_ids')
    for grp in witness['indistinguishable_groups']:
        _sorted_unique_ids(grp, universe, 'indistinguishable group')
    conflict = set(P) & set(N)

    if conflict:
        if status != 'CONFLICT':
            raise Reject('conflicting facts must yield CONFLICT with nothing else')
        ok('conflict recomputed')
        return {'verdict': 'PASS', 'checks': checks}
    if status == 'CONFLICT':
        raise Reject('CONFLICT claimed without conflicting facts')

    complete = f['label_completeness'] == 'USER_ASSERTED_COMPLETE'
    Ps, Ns = set(P), set(N)
    expect = {r for r, s in rows.items() if (s == Ps if complete else (Ps <= s and not (Ns & s)))}
    if cand != expect:
        raise Reject('candidate set differs from recomputation')
    ok('candidate set recomputed')

    if not expect:
        if status != 'OUTSIDE_MODELED_REGISTER_OR_CONFLICT':
            raise Reject('empty candidate set must be OUTSIDE_MODELED_REGISTER_OR_CONFLICT')
        return {'verdict': 'PASS', 'checks': checks}
    if len(expect) == 1:
        if status != 'SINGLE_MODELED_CANDIDATE':
            raise Reject('one candidate must be SINGLE_MODELED_CANDIDATE with depth 0')
        return {'verdict': 'PASS', 'checks': checks}

    t = Tree({r: rows[r] for r in expect})
    C = frozenset(expect)
    groups = {}
    for r in sorted(expect):
        groups.setdefault(rows[r], []).append(r)
    dups = sorted(g for g in groups.values() if len(g) > 1)
    if dups:
        if status != 'INDISTINGUISHABLE' or witness['indistinguishable_groups'] != dups:
            raise Reject('identical signatures must be reported INDISTINGUISHABLE with the exact groups')
        ok('indistinguishable groups recomputed')
        return {'verdict': 'PASS', 'checks': checks}
    if status != 'NEXT_QUESTION':
        raise Reject('separable candidates must yield NEXT_QUESTION')

    opt = t.optimum(C)
    if not _is_int(witness['worst_case_depth'], opt):
        raise Reject('claimed depth is not the recomputed optimum')
    ok('optimal depth recomputed')

    q = witness['question']
    if q in Ps or q in Ns:
        raise Reject('question missing or already answered')
    split = {a: (y, n) for a, y, n in t.splits(C)}
    if q not in split:
        raise Reject('question does not split the candidate set')
    y, n = split[q]
    part = witness['partition']
    if _sorted_unique_ids(part['yes'], universe, 'yes') != y or _sorted_unique_ids(part['no'], universe, 'no') != n:
        raise Reject('partition differs from recomputation')
    if witness['unknown_answer_keeps'] != sorted(expect):
        raise Reject('UNKNOWN branch must keep every candidate')
    ok('partitions recomputed')
    if not (t.can(y, opt - 1) and t.can(n, opt - 1)):
        raise Reject('question does not achieve the optimal depth')
    ok('question achieves optimum')

    optimal = [(max(len(yy), len(nn)), a) for a, (yy, nn) in split.items()
               if t.can(yy, opt - 1) and t.can(nn, opt - 1)]
    canonical = min(optimal)[1]
    if q != canonical:
        if mode == 'tie_valid':
            return {'verdict': 'PASS_TIE_VALID', 'checks': checks,
                    'note': 'optimal but not the frozen tie-rule choice'}
        raise Reject('question is optimal-depth but violates the frozen tie rule')
    ok('frozen tie rule')
    return {'verdict': 'PASS', 'checks': checks}


def verify_bytes(witness_bytes, registry, mode='strict', expected_facts=None):
    try:
        if len(witness_bytes) > MAX_WITNESS_BYTES:
            raise Reject('witness too large')
        w = json.loads(witness_bytes.decode('utf-8'), object_pairs_hook=_no_dupes)
        out = verify(w, registry, mode, expected_facts)
    except Reject as e:
        return {'verdict': 'FAIL', 'reason': str(e), 'verifier_version': VERIFIER_VERSION}
    except (ValueError, KeyError, TypeError, RecursionError, AttributeError) as e:
        return {'verdict': 'FAIL', 'reason': f'malformed witness ({type(e).__name__})', 'verifier_version': VERIFIER_VERSION}
    out['verifier_version'] = VERIFIER_VERSION
    return out


def main(argv):
    args = dict(zip(argv[1::2], argv[2::2]))
    if '--registry' not in args or len(argv) % 2 == 0:
        print(__doc__, file=sys.stderr)
        return 2
    try:
        with open(args['--registry'], 'r', encoding='utf-8') as fh:
            registry = json.loads(fh.read(4 * 1024 * 1024), object_pairs_hook=_no_dupes)
    except (OSError, ValueError, Reject):
        print(json.dumps({'verdict': 'FAIL', 'reason': 'registry unreadable', 'verifier_version': VERIFIER_VERSION}))
        return 1
    expected = None
    if '--expect-facts' in args:
        try:
            expected = json.loads(args['--expect-facts'], object_pairs_hook=_no_dupes)
        except (ValueError, Reject):
            expected = 'malformed'
    out = verify_bytes(sys.stdin.buffer.read(MAX_WITNESS_BYTES + 1), registry, args.get('--mode', 'strict'), expected)
    print(json.dumps(out, sort_keys=True))
    return 0 if out['verdict'].startswith('PASS') else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv))
