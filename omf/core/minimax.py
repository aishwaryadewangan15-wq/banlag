"""Exact worst-case-optimal YES/NO ingredient question over a frozen finite register.

C(P,N) = {r : P subset ingr(r) and N disjoint ingr(r)}            (label completeness NOT established)
C(P,N) = {r : ingr(r) == P}                                       (USER_ASSERTED_COMPLETE label)
D(C)   = 0 if |C| <= 1; INF if C holds two identical signatures;
         else 1 + min over splitting a of max(D(C_yes), D(C_no)).
Tie rule: smallest depth, then smallest worst branch size, then smallest canonical name (code point order).
An UNKNOWN answer takes neither branch.
"""
import time

SOLVER_VERSION = 'omf-minimax-1.0.0'
TIE_RULE = 'min_depth>min_worst_branch_size>min_name_codepoint'
INF = float('inf')
MAX_STATES = 200_000
MAX_SECONDS = 3.0
MAX_VOCAB = 128


class ResourceLimit(Exception):
    pass


def candidates(cases, present, absent, complete=False):
    P, N = set(present), set(absent)
    out = []
    for c in cases:
        ing = set(c['ingredients'])
        if complete:
            if ing == P:
                out.append(c['id'])
        elif P <= ing and not (N & ing):
            out.append(c['id'])
    return sorted(out)


class Solver:
    def __init__(self, cases):
        self.ids = [c['id'] for c in cases]
        self.sig = {c['id']: frozenset(c['ingredients']) for c in cases}
        vocab = sorted({i for c in cases for i in c['ingredients']})
        if len(vocab) > MAX_VOCAB:
            raise ResourceLimit('vocabulary too large')
        self.vocab = vocab
        self.memo = {}
        self.deadline = None

    def _split(self, C, a):
        yes = frozenset(r for r in C if a in self.sig[r])
        return yes, C - yes

    def _questions(self, C):
        for a in self.vocab:
            yes, no = self._split(C, a)
            if yes and no:
                yield a, yes, no

    def depth(self, C):
        if len(C) <= 1:
            return 0
        hit = self.memo.get(C)
        if hit is not None:
            return hit
        if len(self.memo) >= MAX_STATES or time.monotonic() > self.deadline:
            raise ResourceLimit('state or time budget exceeded')
        if len({self.sig[r] for r in C}) < len(C):
            d = INF
        else:
            d = INF
            for _a, yes, no in self._questions(C):
                d = min(d, 1 + max(self.depth(yes), self.depth(no)))
        self.memo[C] = d
        return d

    def best(self, C):
        """Return (question, yes, no, depth) under the frozen tie rule, or None if no split exists."""
        best_key, best = None, None
        for a, yes, no in self._questions(C):
            d = 1 + max(self.depth(yes), self.depth(no))
            key = (d, max(len(yes), len(no)), a)
            if best_key is None or key < best_key:
                best_key, best = key, (a, yes, no, d)
        return best

    def duplicate_groups(self, C):
        groups = {}
        for r in sorted(C):
            groups.setdefault(self.sig[r], []).append(r)
        return sorted(g for g in groups.values() if len(g) > 1)


def solve(cases, present, absent, complete=False):
    """Pure solver. `present`/`absent` are canonical names. Returns a plain dict."""
    P, N = sorted(set(present)), sorted(set(absent))
    conflict = sorted(set(P) & set(N))
    base = {'solver_version': SOLVER_VERSION, 'tie_rule': TIE_RULE, 'question': None,
            'partition': None, 'unknown_answer_keeps': None, 'worst_case_depth': None,
            'indistinguishable_groups': []}
    if conflict:
        return dict(base, status='CONFLICT', candidate_ids=[], conflict_terms=conflict)
    C = candidates(cases, P, N, complete)
    if not C:
        return dict(base, status='OUTSIDE_MODELED_REGISTER_OR_CONFLICT', candidate_ids=[])
    if len(C) == 1:
        return dict(base, status='SINGLE_MODELED_CANDIDATE', candidate_ids=C, worst_case_depth=0)
    s = Solver(cases)
    s.deadline = time.monotonic() + MAX_SECONDS
    Cf = frozenset(C)
    try:
        dups = s.duplicate_groups(Cf)
        if dups:
            return dict(base, status='INDISTINGUISHABLE', candidate_ids=C, indistinguishable_groups=dups)
        q = s.best(Cf)
    except ResourceLimit as e:
        return dict(base, status='RESOURCE_LIMIT', candidate_ids=C, detail=str(e))
    a, yes, no, d = q
    return dict(base, status='NEXT_QUESTION', candidate_ids=C, question=a,
                partition={'yes': sorted(yes), 'no': sorted(no)}, unknown_answer_keeps=C,
                worst_case_depth=d)
