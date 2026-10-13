"""Canonical, inspectable witness for one solver step. SHA-256 gives integrity comparison only; it is
not a signature and proves nothing about who produced the witness."""
import hashlib

from core import facts as F
from core import minimax as M
from core.register import canonical_json

WITNESS_SCHEMA = 'omf.witness.v1'
CAVEAT = ('Finite model of 10 of the 16 June-2026 notified FDCs (original BANLAG register). '
          'FORMULATION-NOTICE SCOPE only: not a product identification, legal status, or medical or legal advice. '
          'Anything outside the modeled register cannot be matched or cleared.')


def seal(w):
    body = {k: v for k, v in w.items() if k != 'witness_digest'}
    return dict(w, witness_digest=hashlib.sha256(canonical_json(body).encode('utf-8')).hexdigest())


def build(register, accepted, result):
    w = {
        'schema': WITNESS_SCHEMA,
        'solver_version': result['solver_version'],
        'register_id': register['register_id'],
        'register_digest': register['digest'],
        'tie_rule': result['tie_rule'],
        'facts': {
            'present': [{'term': f['term'], 'provenance': f['provenance']} for f in accepted['present']],
            'absent': [{'term': f['term'], 'provenance': f['provenance']} for f in accepted['absent']],
            'label_completeness': accepted['label_completeness'],
            'unresolved_inputs': accepted['unresolved'],
        },
        'status': result['status'],
        'candidate_ids': result['candidate_ids'],
        'question': result['question'],
        'partition': result['partition'],
        'unknown_answer_keeps': result['unknown_answer_keeps'],
        'worst_case_depth': result['worst_case_depth'],
        'indistinguishable_groups': result['indistinguishable_groups'],
        'caveat': CAVEAT,
    }
    return seal(w)


def naming_caveats(register, res):
    """Derived from the register's contested probiotic group: whenever a candidate (or the question) uses a
    probiotic notice term, state which rows use which wording and that synonymy is contested."""
    group = set(register.get('probiotic_group', []))
    involved = [(c['id'], sorted(set(c['ingredients']) & group)) for c in register['cases']
                if c['id'] in res.get('candidate_ids', []) and set(c['ingredients']) & group]
    if not involved and res.get('question') not in group:
        return []
    wording = '; '.join(f"{cid} uses '{', '.join(t)}'" for cid, t in involved)
    return [f'Probiotic naming caveat: {wording}. Whether these notice names denote the same organism is contested; '
            'answers count only for the exact notice wording, and other probiotic names are not accepted as facts.']


def run(register, request):
    """Full pure pipeline: accept facts -> solve -> witness. Raises FactError on invalid input."""
    acc = F.accept(request, register)
    res = M.solve(register['cases'], [f['term'] for f in acc['present']], [f['term'] for f in acc['absent']],
                  complete=acc['label_completeness'] == 'USER_ASSERTED_COMPLETE')
    # A remaining candidate is only CONSISTENT with the facts; list what is still unconfirmed for each.
    present = {f['term'] for f in acc['present']}
    res['unconfirmed_by_candidate'] = {
        c['id']: sorted(set(c['ingredients']) - present) for c in register['cases'] if c['id'] in res['candidate_ids']}
    res['naming_caveats'] = naming_caveats(register, res)
    if res['status'] == 'RESOURCE_LIMIT':
        return {'accepted': acc, 'result': res, 'witness': None}
    return {'accepted': acc, 'result': res, 'witness': build(register, acc, res)}
