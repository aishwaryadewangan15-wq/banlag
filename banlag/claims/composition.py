"""Ingredient-list reading: list runs, unknown list items and composition issues next to a named set."""

import re
from ..legal import find_mentions
from .patterns import (_ADDITION, _CLASS_WORDS, _CONTAINS, _DOSAGE_FORMS, _LIST_DELIMS, _LIST_FILLER, _LIST_TOKEN,
    _NOT_INGREDIENT, _NP_STOP, _OTHER_PRODUCT, _RUN_BREAK, _VARIABILITY)
from .sentences import strip_parentheticals


def _allowed_word(w):
    t = w.lower().strip("'")
    return (t in _NOT_INGREDIENT or t in _LIST_FILLER or t in _CLASS_WORDS or t in _DOSAGE_FORMS or t in _LIST_DELIMS
            or bool(re.fullmatch(r'\d+(?:\.\d+)?(?:mg|mcg|ml|g|iu|%)?', t)))
def _np_after(text):
    """Words of the noun phrase at the start of text, up to punctuation, a verb/preposition or 6 words."""
    words = []
    for t in _LIST_TOKEN.findall(text):
        if t in (',', ';', ':', ')', '(') or t.lower() in _NP_STOP or len(words) >= 6:
            break
        if t in ('+', '&', '/') or t.lower() in ('and', 'with', 'plus'):
            words.append('|')  # item separator inside an addition phrase
            continue
        words.append(t)
    return words
def _np_items(words):
    items, cur = [], []
    for w in words + ['|']:
        if w == '|':
            if cur:
                items.append(cur)
            cur = []
        else:
            cur.append(w)
    return items
def _classify_items(items, subject):
    """Unknown / extra-known members among noun-phrase items (each item: list of words)."""
    unknown, extra = [], []
    for item in items:
        phrase = ' '.join(item)
        names = {m['canonical'] for m in find_mentions(phrase)}
        if names:
            extra += sorted(names - set(subject or names))
            continue
        if any(not _allowed_word(w) for w in item):
            unknown.append(phrase)
    return unknown, extra
def _paren_issues(sentence, subject):
    """Composition-bearing parentheticals: '(plus omeprazole)' adds a component; '(lidocaine)' is a synonym; '(often with X)'
    is a variability aside; '(as well as the version including X)' is another product; '(with food)' adds nothing."""
    unknown, extra, variable, other = [], [], [], []
    _, asides = strip_parentheticals(sentence)
    for a in asides:
        if _VARIABILITY.search(a):
            variable.append(a)
            continue
        if _OTHER_PRODUCT.search(a):
            other.append(a)
            continue
        m = _ADDITION.match(a)
        c = _CONTAINS.search('this ' + a) if not m else None
        if m or (c and re.match(r'^\s*(?:also\s+)?(?:contains?|containing|includes?|including)\b', a, re.I)):
            rest = a[m.end():] if m else a[c.end() - len('this '):]
            u, x = _classify_items(_np_items(_np_after(rest)), subject)
            unknown += u
            extra += x
            continue
        names = {mm['canonical'] for mm in find_mentions(a)}
        if names and subject and names - set(subject):
            extra += sorted(names - set(subject))
    return unknown, extra, variable, other
def composition_issues(sentence, subject=None, space_delimited=False):
    """Everything in a sentence that makes its named ingredient set incomplete or different from what was named:
    unrecognised list members (start, middle or end), additions after the list ('plus', 'as well as', 'including', 'with', ...),
    composition-bearing parentheticals, and explicit 'the formulation also contains X' clauses. Descriptive appositives built
    from class words, dosage forms, strengths and '(with food)' are not components."""
    main, _ = strip_parentheticals(sentence or '')
    names = {m['canonical'] for m in find_mentions(main)}
    subject = set(subject) if subject else names
    unknown = list(unknown_list_items(main, space_delimited=space_delimited))
    extra = []
    if not space_delimited:
        pu, px, variable, other = _paren_issues(sentence or '', subject)
        unknown += pu
        extra += px
        for m in _CONTAINS.finditer(main):
            if _VARIABILITY.search(main[max(0, m.start() - 25):m.end()]):
                continue
            if re.search(r"\b(?:not|never|no|without)\b|n['’]t\b", main[m.start():m.end()], re.I):
                continue  # 'it does not contain X' is negated membership: semantics.composition_state decides it (RC-3)
            u, x = _classify_items(_np_items(_np_after(main[m.end():])), subject)
            unknown += u
            extra += x
    else:
        variable, other = [], []
    extra += sorted(names - subject) if subject != names else []
    return {'unknown': unknown, 'extra_known': sorted(set(extra)), 'variable_asides': variable, 'other_product_asides': other}
def _clause_word(tok):
    """Participles and adverbs ('declaring', 'improved', 'typically') start clauses, not ingredient names."""
    t = tok.lower()
    return len(t) > 4 and (t.endswith('ing') or t.endswith('ed') or t.endswith('ly'))
def _is_filler(tok):
    t = tok.lower()
    return t in _LIST_FILLER or bool(re.fullmatch(r'\d+(?:\.\d+)?', t)) or bool(re.fullmatch(r'\d+(?:mg|mcg|ml|g|iu)', t))
def list_runs(text, space_delimited=False):
    """Group a text's ingredient mentions into lists: mentions joined only by delimiters/filler (or by a delimited
    descriptive item) form one list; ordinary clause text or a separator such as '*', '|', '.' or ':' starts a new one.
    Returns (runs, unrecognised inner members)."""
    ms = find_mentions(text or '')
    if not ms:
        return [], []
    unknown, runs = [], [[ms[0]]]
    for a, b in zip(ms, ms[1:]):
        gap = text[a['end']:b['start']]
        toks = _LIST_TOKEN.findall(gap)
        sig = [t for t in toks if t.lower() not in _LIST_DELIMS and not _is_filler(t)]
        opens = bool(toks) and toks[0].lower() in _LIST_DELIMS
        closes = bool(toks) and toks[-1].lower() in _LIST_DELIMS
        if not sig and not toks and _RUN_BREAK.search(gap) and not space_delimited:
            runs.append([b])  # 'A + B * A + B Uses' / 'A + B | C': a separator, not a list delimiter
        elif not sig:
            runs[-1].append(b)
        elif opens and closes and len(sig) <= 4:
            # A delimited item between two ingredients: a description only if built from class words/dosage forms
            # ('dicyclomine, an antispasmodic, ...'); otherwise an unrecognised member ('dicyclomine, an omeprazole capsule, ...').
            if any(not _allowed_word(s) for s in sig):
                unknown.append(' '.join(sig))
            runs[-1].append(b)
        elif space_delimited and len(sig) <= 2 and not any(s.lower() in _NOT_INGREDIENT for s in sig):
            unknown.append(' '.join(sig))
            runs[-1].append(b)
        else:
            runs.append([b])
    return runs, unknown
def unknown_list_items(text, space_delimited=False):
    """Unrecognised members of an ingredient list: words joined by ',', '+', '&', '/', 'and', 'with' or 'plus' to a recognised
    ingredient but not themselves recognised (e.g. 'omeprazole' in 'dicyclomine, paracetamol, clidinium bromide and omeprazole').
    Mentions separated by ordinary clause text are separate lists, not unknown items. For URL slugs (space_delimited) the word
    right after a run of ingredient names counts as a list member."""
    runs, unknown = list_runs(text, space_delimited)
    if not runs:
        return []
    bounds = [r[0]['start'] for r in runs[1:]] + [len(text)]
    for run, nxt in zip(runs, bounds):
        rest = text[run[-1]['end']:nxt]
        if space_delimited:
            toks = _LIST_TOKEN.findall(rest)
            cand = next((t for t in toks[:3] if not _is_filler(t)), None)
            if cand and cand.lower() not in _NOT_INGREDIENT and len(cand) > 2 and not _clause_word(cand):
                unknown.append(cand)
            continue
        m = _ADDITION.match(rest)
        if m and m.end() > 0:
            words = _np_after(rest[m.end():])
            if words and (words[0].lower() in ('a', 'an', 'the')) and rest[:m.end()].strip() == ',':
                words = []  # ', a combination sold in India, ...' is an appositive description
            if words and rest[:m.end()].strip() == ',' and (_clause_word(words[0]) or words[0].lower() in _NOT_INGREDIENT):
                words = []  # ', declaring them ...' / ', which ...' open a clause, not a list member
            u, x = _classify_items(_np_items(words), None)
            unknown += u + x
    for run, prev_end in zip(runs, [0] + [r[-1]['end'] for r in runs[:-1]]):
        before = _LIST_TOKEN.findall(text[prev_end:run[0]['start']])
        if len(before) < 2 or before[-1].lower() not in _LIST_DELIMS - {'with'}:
            continue
        delim, item, stopper = before[-1], [], None
        for t in reversed(before[:-1]):  # walk back to the previous delimiter or a clause word
            if t.lower() in _LIST_DELIMS or t.lower() in _NOT_INGREDIENT:
                stopper = t
                break
            item.insert(0, t)
        if delim in (',', ';') and stopper is not None and stopper.lower() not in _LIST_DELIMS:
            continue  # 'For abdominal cramps, X ...' / 'In India, X ...': an introductory clause, not a list member
        if item and any(not _allowed_word(w) for w in item):
            unknown.append(' '.join(item))
    return unknown
def _canon_set(text):
    return {m['canonical'] for m in find_mentions(text)}
def _classes(text):
    return {m['canonical']: m['class'] for m in find_mentions(text)}
