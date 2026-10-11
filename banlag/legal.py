"""Legal registry and strict exact-set matcher for the sixteen Section 26A notices (S.O. 3068(E)-3083(E)).

Design rules (from the independent legal audit):
- A notice names one exact fixed-dose combination; only the complete ingredient set matches.
- Subsets, supersets and look-alikes never inherit a prohibition.
- Spelling/salt variants are reported (SPELLING_VARIANT); probiotic name swaps are contested
  and produce an abstention, never a match.
- A notice that names a component only generically (F07: 'Herbal') can never be matched exactly; a list that
  equals its specified part plus that generic word is reported as a candidate for review, never as a match.
"""
import copy
import json
import re
from functools import lru_cache
from pathlib import Path

REGISTRY_PATH = Path(__file__).with_name('registry.json')
NOTICE_RE = re.compile(r'S\s*\.?\s*O\s*\.?\s*(\d{3,4})\s*\(\s*E\s*\)', re.I)
MAX_INGREDIENTS = 12
MAX_NAME_LEN = 80


def norm(s):
    return ' '.join(re.findall(r'[a-z0-9]+', str(s).lower()))


@lru_cache(maxsize=1)
def _db():
    return json.loads(REGISTRY_PATH.read_text(encoding='utf-8'))


def registry():
    """A private copy, so callers can never mutate the cached registry."""
    return copy.deepcopy(_db())


def entry_by_id(entry_id):
    return next((e for e in _db()['entries'] if e['id'] == entry_id), None)


def entry_by_notice(number):
    """'3079' -> F11 entry, or None for a notice outside this registry."""
    return next((e for e in _db()['entries'] if e['notice'] == f'S.O. {number}(E)'), None)


@lru_cache(maxsize=1)
def lexicon():
    """norm(name) -> (canonical or None, class). Classes: LITERAL, SPELLING_VARIANT,
    CONTESTED_PROBIOTIC, OTHER_ACTIVE."""
    db = _db()
    lex = {}
    for other, aliases in db['other_actives'].items():
        for name in [other] + aliases:
            lex[norm(name)] = (other, 'OTHER_ACTIVE')
    for alias, spec in db['aliases'].items():
        lex[norm(alias)] = (spec['canonical'] or norm(alias), spec['class'])
    for entry in db['entries']:
        vague = set(entry.get('underspecified_terms', ()))
        for ing in entry['ingredients']:
            if ing not in vague:
                lex[norm(ing)] = (ing, 'LITERAL')
    return lex


def _underspecified_candidate(names, unknown):
    """F07-style notices: the recognised names equal an entry's specified part and every unknown word is its generic term."""
    words = {norm(u) for u in unknown}
    for row in _db()['entries']:
        vague = {norm(t) for t in row.get('underspecified_terms', ())}
        if vague and words == vague and set(names) == set(row['ingredients']) - set(row['underspecified_terms']):
            return {'status': 'UNDERSPECIFIED_NOTIFICATION_CANDIDATE', 'candidate_entry_id': row['id'], 'notice': row['notice'],
                    'reason': f"{row['notice']} names a component only as '{row['underspecified_terms'][0].title()}'. "
                              'No list can be shown to equal it, so BANLAG abstains; review the product against the notice text.'}
    return None


@lru_cache(maxsize=1)
def _mention_re():
    names = sorted(lexicon(), key=len, reverse=True)
    parts = [r'[\s\-]+'.join(re.escape(w) for w in n.split()) for n in names]
    return re.compile(r'(?<![a-z0-9])(' + '|'.join(parts) + r')(?![a-z0-9])', re.I)


def find_mentions(text):
    """Ingredient mentions in text, longest-name-first. Returns dicts with span and lexicon class."""
    out = []
    for m in _mention_re().finditer(text or ''):
        canonical, kind = lexicon()[norm(m.group(1))]
        out.append({'start': m.start(), 'end': m.end(), 'surface': m.group(1), 'canonical': canonical, 'class': kind})
    return out


def canonical(name, db=None):
    """Legacy helper: canonical name for a recognised ingredient, else None."""
    hit = lexicon().get(norm(name))
    return hit[0] if hit else None


def _group(name):
    return 'probiotic' if name in _db()['probiotic_group'] else name


def relation(found, entry_set):
    if found == entry_set:
        return 'EXACT'
    if found < entry_set:
        return 'SUBSET'
    if found > entry_set:
        return 'SUPERSET'
    return 'OVERLAP' if found & entry_set else 'DISJOINT'


def match_set(found, classes=None):
    """Match a set of canonical names against the registry. classes: canonical -> lexicon class."""
    classes = classes or {}
    db = _db()
    for row in db['entries']:
        if found == set(row['ingredients']):
            variants = sorted(n for n in found if classes.get(n) == 'SPELLING_VARIANT')
            return {'status': 'EXACT_NOTIFICATION_MATCH', 'entry': copy.deepcopy(row),
                    'match_strength': 'SPELLING_VARIANT' if variants else 'LITERAL', 'variant_terms': variants,
                    'reason': 'Complete normalised ingredient set equals one notified FDC.'}
    grouped = {_group(n) for n in found}
    if 'probiotic' in grouped:
        for row in db['entries']:
            if grouped == {_group(n) for n in row['ingredients']}:
                return {'status': 'CONTESTED_SYNONYM_CANDIDATE', 'candidate_entry_id': row['id'],
                        'reason': 'Matches only if a probiotic name is treated as a synonym; legal audit requires abstention.'}
    near = [{'id': row['id'], 'relation': relation(found, set(row['ingredients']))} for row in db['entries']]
    near = [n for n in near if n['relation'] in ('SUBSET', 'SUPERSET')]
    return {'status': 'NO_EXACT_MATCH', 'nearby_notices': [n['id'] for n in near], 'relations': near,
            'reason': 'Full ingredient set differs from every listed exact FDC. No inferred ban.'}


def match_formula(ingredients, db=None):
    """Strict matcher for an explicit, complete ingredient list. Abstains on anything unrecognised."""
    if not isinstance(ingredients, list) or not ingredients:
        return {'status': 'UNKNOWN_FORMULATION', 'reason': 'Provide complete, explicit ingredient list.'}
    if len(ingredients) > MAX_INGREDIENTS or any(not isinstance(v, str) or not v.strip() or len(v) > MAX_NAME_LEN for v in ingredients):
        return {'status': 'UNKNOWN_FORMULATION', 'reason': 'Ingredient list must be 1-12 non-empty names of at most 80 characters.'}
    hits = [lexicon().get(norm(v)) for v in ingredients]
    unknown = [ingredients[i] for i, h in enumerate(hits) if h is None]
    if unknown:
        known = [h[0] for h in hits if h is not None]
        cand = _underspecified_candidate(known, unknown) if len(set(known)) == len(known) else None
        if cand:
            return cand
        return {'status': 'UNKNOWN_FORMULATION', 'reason': 'Unrecognized or ambiguous ingredient; abstain.', 'unrecognized': unknown}
    names = [h[0] for h in hits]
    if len(set(names)) != len(names):
        return {'status': 'UNKNOWN_FORMULATION', 'reason': 'Duplicate ingredient; abstain.'}
    return match_set(set(names), {h[0]: h[1] for h in hits})


def notice_numbers(text):
    return [f'S.O. {m.group(1)}(E)' for m in NOTICE_RE.finditer(text or '')]
