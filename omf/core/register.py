"""Frozen finite candidate register: loading and canonical digest."""
import hashlib
import json
import os
import re

DEFAULT_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'registry_scope.json')
MAX_CASES = 32
# Shared WRITTEN contract (docs/ID_GRAMMAR.md): ASCII letters (case-sensitive, never case-folded), digits, '_' and '-',
# length 1..64. Applies to case ids and register_id. The independent verifier implements it separately.
ID_GRAMMAR = re.compile(r'^[A-Za-z0-9_-]{1,64}$')
MAX_INGREDIENTS_PER_CASE = 16


class RegisterError(ValueError):
    pass


def canonical_json(obj):
    return json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def register_digest(cases):
    """SHA-256 over the minimax-relevant content only: ids and their ingredient sets."""
    body = {'schema': 'omf.register.v1',
            'cases': sorted(({'id': c['id'], 'ingredients': sorted(c['ingredients'])} for c in cases),
                            key=lambda c: c['id'])}
    return hashlib.sha256(canonical_json(body).encode('utf-8')).hexdigest()


def validate_cases(cases):
    if not isinstance(cases, list) or not cases:
        raise RegisterError('register must be a non-empty list')
    if len(cases) > MAX_CASES:
        raise RegisterError(f'register exceeds {MAX_CASES} cases')
    seen = set()
    for c in cases:
        if not isinstance(c, dict) or not isinstance(c.get('id'), str) or not ID_GRAMMAR.fullmatch(c['id']):
            raise RegisterError('case id missing or outside the ID grammar')
        if c['id'] in seen:
            raise RegisterError(f'duplicate case id {c["id"]}')
        seen.add(c['id'])
        ing = c.get('ingredients')
        if not isinstance(ing, list) or not ing or len(ing) > MAX_INGREDIENTS_PER_CASE:
            raise RegisterError(f'case {c["id"]} has invalid ingredient list')
        if any(not isinstance(i, str) or not i for i in ing) or len(set(ing)) != len(ing):
            raise RegisterError(f'case {c["id"]} has invalid or repeated ingredients')
    return cases


def validate_canonical(reg):
    """Every row ingredient must already be a canonical name: normalized, never an alias key (of any
    class, contested or not), never a known outside-register active. Spelling-variant targets must exist
    in the vocabulary. Violations raise NONCANONICAL_REGISTER; nothing is guessed or collapsed."""
    from core.facts import FactError, normalize
    aliases = reg.get('aliases') or {}
    if not isinstance(aliases, dict):
        raise RegisterError('NONCANONICAL_REGISTER: aliases must be an object')
    vocab = set()
    for c in reg['cases']:
        for i in c['ingredients']:
            try:
                n = normalize(i)
            except FactError:
                raise RegisterError(f'NONCANONICAL_REGISTER: {c["id"]} has an invalid ingredient name')
            if n != i:
                raise RegisterError(f'NONCANONICAL_REGISTER: {c["id"]} has a non-normalized ingredient name')
            vocab.add(i)
    clash = sorted(vocab & set(aliases))
    if clash:
        raise RegisterError(f'NONCANONICAL_REGISTER: alias names used as row ingredients: {clash}')
    for k, v in aliases.items():
        if not isinstance(v, dict) or v.get('class') not in ('SPELLING_VARIANT', 'CONTESTED_PROBIOTIC'):
            raise RegisterError('NONCANONICAL_REGISTER: alias entry malformed')
        if v['class'] == 'SPELLING_VARIANT' and v.get('canonical') not in vocab:
            raise RegisterError('NONCANONICAL_REGISTER: spelling variant points outside the vocabulary')
    other = reg.get('other_actives') or {}
    if not isinstance(other, dict):
        raise RegisterError('NONCANONICAL_REGISTER: other_actives must be an object')
    names = set(other) | {a for vs in other.values() for a in vs}
    if names & vocab or names & set(aliases):
        raise RegisterError('NONCANONICAL_REGISTER: outside-register actives collide with register names')
    return reg


def load(path=DEFAULT_PATH):
    with open(path, 'r', encoding='utf-8') as f:
        reg = json.load(f)
    if reg.get('schema') != 'omf.register.v1':
        raise RegisterError('unexpected register schema')
    if not isinstance(reg.get('register_id'), str) or not ID_GRAMMAR.fullmatch(reg['register_id']):
        raise RegisterError('register_id missing or outside the ID grammar')
    validate_cases(reg['cases'])
    validate_canonical(reg)
    reg['digest'] = register_digest(reg['cases'])
    return reg
