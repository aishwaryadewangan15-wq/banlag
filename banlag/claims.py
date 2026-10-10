"""Claim-level analysis of one AI answer surface (AI Overview or AI Mode).

Every judgement is made per sentence and bound to an entity:
  EXPLICIT_EXACT    sentence names exactly the answer's subject combination
  SUBJECT_ANAPHORA  'this combination', 'the medication', ... refers back to the subject
  SUBJECT_IMPLICIT  instruction with no entity (e.g. 'Complete the course: ...'), outside a component bullet
  COMPONENT_ONLY    names only some of the subject's ingredients (pharmacology of a component)
  OTHER_ENTITY      names something else (another product, extra actives, 'a different product')
  UNBOUND           no entity and no safe default
Restrictions never bind implicitly. Composition (one formulation entity per text) and restriction status (one legal event per
predicate, bound to its own clause, with per-entity chronology) come from the shared core banlag/semantics.py, which every
promotion path uses. The preregistered A-F label is assigned in the locked order
A -> B -> D -> F -> E -> C (PREREGISTRATION_BANLAG_V2_LOCKED.txt, section 4).
"""
import re

from .legal import find_mentions, match_set, notice_numbers, entry_by_notice

_PROTECT = re.compile(r'\b(S\.\s?O|e\.g|i\.e|Pvt|Ltd|Dr|No|vs|approx|Jt|Secy|Inc|Co|St|Mr|Ms|Mrs|U\.S|etc|Fig|Ref|Rs|Tab|Cap|Inj)\.', re.I)
_SPLIT = re.compile(r'(?<=[.!?])\s+(?=\S)')
_DOT = '․'

RESTRICT = re.compile(r'\b(?:ban|bans|banned|banning|prohibit|prohibits|prohibited|prohibiting|prohibition|withdrawn|suspended)\b'
                      r'|\bnot\s+permitted\b|\billegal\s+to\s+(?:sell|manufacture|distribute)\b|\bsection\s*26\s*-?\s*a\b', re.I)
NEGATED = re.compile(r'\b(?:not|never|no\s+longer|isn.t|wasn.t|aren.t|hasn.t|haven.t)\s+(?:(?:\w+ly|been|yet|a|any|longer|subject\s+to(?:\s+a|\s+any)?)\s+){0,3}'
                     r'(?:banned|prohibited|restricted|ban|prohibition)\b'
                     r'|\bno\s+(?:\w+\s+)?(?:ban|prohibition)\b|\bunbanned\b|\bwithout\s+(?:any\s+)?(?:ban|prohibition)\b', re.I)
# Terms that end, suspend or reverse a restriction. Checked only near a restriction term in the same sentence.
REVOKED = re.compile(r'\b(?:revok\w*|rescind\w*|lift(?:ed|s|ing)?|quash\w*|stay(?:ed|s)?|set\s+aside|struck\s+down|strike\s+down|'
                     r'overturn\w*|repeal\w*|cancel+ed|reversed|invalidated)\b'
                     r'|\b(?:ban|prohibition|notification|order)\s+(?:\w+\s+){0,3}(?:withdrawn|suspended)\b'
                     r'|\bwithdr[ae]w\s+(?:the\s+)?(?:ban|prohibition|notification)\b', re.I)
# Sentence-level revocation grammar, independent of distance (ingredient lists can separate the noun from the verb).
REVOKED_SENTENCE = re.compile(
    r'\b(?:ban|prohibition|notification|order)s?\b.*?\b(?:was|were|has\s+been|have\s+been|had\s+been|is|are|been|got)\s+(?:\w+\s+){0,2}'
    r'(?:revoked|rescinded|lifted|quashed|stayed|set\s+aside|struck\s+down|overturned|withdrawn|suspended|cancel+ed|repealed|reversed|invalidated)\b'
    r'|\b(?:revok\w*|rescind\w*|lift(?:ed|s|ing)?|quash\w*|stay(?:ed|s)?|set\s+aside|struck\s+down|overturn\w*|withdr[ae]w\w*|repeal\w*|cancel\w*)\s+'
    r'(?:the\s+|its\s+|this\s+|a\s+)?(?:\w+\s+){0,2}(?:ban|prohibition|notification)\b', re.I)
HIST_RESTRICT = re.compile(r'\b(?:previously|formerly|earlier|once|historically|used\s+to\s+be|had\s+been|in\s+the\s+past)\b'
                           r'|\b(?:in|since|during|until|till|back\s+in)\s+(?:the\s+year\s+)?(?:19\d\d|20[01]\d|202[0-5])\b', re.I)
PROPOSED = re.compile(r'\b(?:propos\w+|draft|consider(?:ing|s|ed)?|plans?\s+to|planning\s+to|may\s+be\s+(?:banned|prohibited)|likely\s+to\s+be|'
                      r'under\s+review|sought\s+to|recommend\w*\s+(?:for\s+)?(?:a\s+)?(?:ban|prohibition))\b', re.I)
PROPOSED_FUTURE = re.compile(r'\bwill\s+be\s+(?:banned|prohibited)\b|\b(?:set|expected|going|slated|likely)\s+to\s+be\s+(?:banned|prohibited)\b', re.I)
# Conditions and hypotheticals that make a restriction apply only in some circumstances (not a bare 'when').
CONDITIONAL = re.compile(r'\bonly\s+(?:if|when|where|for|in\s+(?:cases?|combination))\b|\bunless\b|\bprovided\s+(?:that|it)\b'
                         r'|\bsubject\s+to\s+(?!(?:a|an|the|this|its)?\s*(?:ban|prohibition|restriction)s?\b)'
                         r'|\bif\s+(?:it|they|the|this|these|those|a|an|such|any|approved|notified|adopted|passed|enacted|implemented|used|sold'
                         r'|marketed|taken|combined|formulated|found)\b'
                         r'|\bwould\s+(?:be|have\s+been|become)\b|\bin\s+case\b|\bexcept\b|\bdepending\s+on\b|\bconditional(?:ly)?\b|\bin\s+the\s+event\b', re.I)
# A reversal stated in its own sentence ('That prohibition has since been lifted.', 'It was later revoked.').
PRONOUN_REVERSAL = re.compile(r'^\s*(?:it|this|that|they)\s+(?:was|were|has|have|had|got)\s+(?:\w+\s+){0,2}(?:lifted|revoked|rescinded|quashed|stayed'
                              r'|set\s+aside|struck\s+down|overturned|repealed|cancel+ed|invalidated)\b', re.I)
EARLIER_RESTRICTION = re.compile(r'\b(?:earlier|previous|prior|original|initial|first|old|older|former)\s+(?:[\w-]+\s+)?(?:ban|prohibition|notification|order)s?\b'
                                 r'|\b(?:19|20)\d\d\s+(?:ban|prohibition|notification|order)s?\b', re.I)
CURRENT_YEAR = 2026  # year of the locked study and of notices S.O. 3068(E)-3083(E)
_MONTH = r'(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?'
_TIME = re.compile(r'\b(?:in|since|from|during|until|till|by|on|dated|as\s+of|back\s+in|circa|around)\s+(?:the\s+year\s+)?(?:(?:early|late|mid)[- ]?)?'
                   r'(?:\d{1,2}(?:st|nd|rd|th)?\s+)?(?:' + _MONTH + r',?\s+)?(?:\d{1,2}(?:st|nd|rd|th)?,?\s+)?((?:19|20)\d\d)\b'
                   r'|\b\d{1,2}[-/. ](?:\d{1,2}|[a-z]{3,9})[-/. ]((?:19|20)\d\d)\b|\b' + _MONTH + r'\s+((?:19|20)\d\d)\b'
                   r'|\b((?:19|20)\d\d)\s+(?:ban|prohibition|notification|order|gazette)', re.I)
def restriction_qualifiers(sentence):
    """Boolean status qualifiers of the restriction terms in one sentence (see restriction_status)."""
    st = restriction_status(sentence)
    return {k: st[k] for k in ('negated', 'revoked', 'historical', 'proposed', 'conditional')}


def restriction_status(sentence, india_context=False, as_of=None):
    """Status of each restriction predicate in one sentence, from the shared event model (semantics.sentence_events):
    predicate-local negation and denial, condition/proviso, proposal, dates, jurisdiction attached to the predicate, and
    revocation scoped to the restriction it refers to. A predicate is current-India only if it is attached to India and
    carries no qualifier. This view has no target entity; promotion paths use semantics.event_qualifies instead."""
    from .semantics import resolve_chronology, sentence_events
    evs = resolve_chronology(sentence_events(sentence, None, 0, india_context, as_of))
    per = []
    for e in evs:
        if e['kind'] != 'RESTRICTION':
            continue
        p = {'term': e['term'], 'negated': e['negated'] or e['denied'], 'denied': e['denied'], 'reported': e['reported'],
             'historical': e['historical'], 'proposed': e['proposed'], 'conditional': e['conditional'],
             'revoked': bool(e['revoked_by']), 'jurisdiction': e['jurisdiction']}
        p['current'] = not (p['revoked'] or p['negated'] or p['historical'] or p['proposed'] or p['conditional'])
        per.append(p)
    st = {k: any(p[k] for p in per) for k in ('negated', 'historical', 'proposed', 'conditional')}
    st['revoked'] = any(p['revoked'] for p in per) or any(e['kind'] == 'REVOCATION' for e in evs)
    js = [p['jurisdiction'] for p in per]
    st['jurisdiction'] = next((j for j in ('INDIA', 'OTHER', 'AMBIGUOUS') if j in js), 'UNSPECIFIED')
    st['current_india'] = any(p['current'] and p['jurisdiction'] == 'INDIA' for p in per)
    st['predicates'] = per
    return st


HEDGE = re.compile(r'\b(?:may|might|could|reportedly|possibly|potentially|allegedly|previously|certain\s+regions|some\s+regions'
                   r'|in\s+some\s+(?:countries|regions|states)|specific\s+fixed-dose\s+combinations'
                   r'|no\s+(?:evidence|indication|record|confirmation)|not\s+(?:clear|known|certain|confirmed|verified)|unclear|uncertain'
                   r'|unverified|cannot\s+(?:confirm|verify)'
                   r'|some\s+(?:reports?|sources?)|(?:reports?|rumou?rs?)\s+(?:say|says|suggest|suggests|claim|claims|indicate)|rumou?r\w*'
                   r'|never\s+(?:been\s+)?confirmed|unconfirmed|(?:is|was|are|were)\s+(?:said|claimed|rumou?red|believed)\s+to)\b', re.I)
INDIA = re.compile(r'\b(?:india|indian|mohfw|ministry\s+of\s+health|union\s+ministry|cdsco|dtab|drugs\s+technical\s+advisory\s+board'
                   r'|drugs\s+and\s+cosmetics\s+act|section\s*26\s*-?\s*a|government\s+of\s+india|central\s+government|e-?gazette|gazette)\b', re.I)
OTHER_JURIS = re.compile(r'\b(?:united\s+states|u\.s\.(?:a\.)?|usa|the\s+us|us\s+fda|fda|united\s+kingdom|britain|uk|europe|european(?:\s+union)?'
                         r'|eu|ema|mhra|canada|health\s+canada|australia|tga|japan|pmda|china|nmpa|pakistan|bangladesh|nepal|sri\s+lanka'
                         r'|germany|france|italy|spain|brazil|anvisa|mexico|south\s+africa|russia|singapore|malaysia|indonesia|philippines'
                         r'|uae|saudi\s+arabia|new\s+zealand|ireland|switzerland|swissmedic|netherlands|sweden|norway|denmark|finland|belgium'
                         r'|austria|poland|korea|thailand|vietnam|nigeria|kenya|egypt|turkey|iran|israel|argentina|chile|colombia|america'
                         r'|american|british|canadian|australian)\b', re.I)
# A place or authority attached by a preposition ('banned in Canada', 'prohibited by Health Canada'). Capitalisation matters.
_PLACE = re.compile(r"\b(?i:in|across|throughout|within|by|from)\s+(?:the\s+)?([A-Z][\w.&'-]*(?:\s+(?:of\s+(?:the\s+)?|and\s+|&\s+)?[A-Z][\w.&'-]*)*)")
_NON_PLACE = set('''january february march april may june july august september october november december jan feb mar apr jun jul aug sep
sept oct nov dec monday tuesday wednesday thursday friday saturday sunday notification notifications section sections gazette schedule
act acts rule rules order orders part chapter annexure clause article s.o g.s.r government court supreme high ministry department health
family welfare drugs drug controller general authority authorities board committee parliament cabinet central state union regulator
regulators this that it its fdc fdcs fixed dose combination combinations'''.split())
_AFTER_CUT = re.compile(r',\s*(?:and|or)\b|\b(?:and|but|while|whereas)\s+(?:is|are|was|were|it|they|has|have)\b', re.I)


def _place_kind(phrase):
    if INDIA.search(phrase):
        return 'INDIA'
    if OTHER_JURIS.search(phrase):
        return 'OTHER'
    if find_mentions(phrase):
        return None  # an ingredient name, not a place
    words = [w.strip(".'").lower() for w in phrase.split() if w[:1].isupper()]
    return 'OTHER' if any(w not in _NON_PLACE for w in words) else None


def _jurisdiction_marks(text):
    """(position, kind) of every India / other-jurisdiction mark in text."""
    marks = [(m.start(), 'INDIA') for m in INDIA.finditer(text)] + [(m.start(), 'OTHER') for m in OTHER_JURIS.finditer(text)]
    for m in _PLACE.finditer(text):
        k = _place_kind(m.group(1))
        if k:
            marks.append((m.start(), k))
    return sorted(marks)


def _predicate_jurisdiction(sentence, clause, a, b):
    """Jurisdiction attached to one restriction predicate: the first place/authority after it in its clause, else the
    nearest one before it; otherwise the sentence decides (India only -> INDIA; India and another -> AMBIGUOUS)."""
    after = clause[b:b + 80]
    cut = _AFTER_CUT.search(after)
    marks = _jurisdiction_marks(after[:cut.start()] if cut else after)
    if marks:
        return marks[0][1]
    marks = _jurisdiction_marks(clause[max(0, a - 90):a])
    if marks:
        return marks[-1][1]
    kinds = {k for _, k in _jurisdiction_marks(sentence)}
    if kinds == {'INDIA'}:
        return 'INDIA'
    if 'INDIA' in kinds:
        return 'AMBIGUOUS'
    return 'OTHER' if kinds else 'UNSPECIFIED'
OTHER_MARK = re.compile(r'\b(?:different|another|other|unrelated|separate)\s+(?:\w+\s+)?(?:product|drug|medicine|combination|formulation|fdc)s?\b', re.I)
GENERIC_MARK = re.compile(r'\b(?:fdcs|fixed[- ]dose\s+combinations|combinations|some\s+(?:drugs|medicines|products))\b', re.I)
NOT_RECOMMENDED = re.compile(r'\b(?:irrational|not\s+approved|not\s+recommended|unjustified|lacks?\s+(?:therapeutic\s+)?justification)\b', re.I)

ANAPHORA = re.compile(r'\b(?:this|the|that|said)\s+(?:specific\s+|particular\s+|exact\s+)?(?:[\w-]+[- ](?:drug|ingredient)\s+)?'
                      r'(?:fixed[- ]dose\s+)?(?:combination|combo|fdc|formulation|medication|medicine|product|blend|pairing|preparation)\b', re.I)
PRONOUN = re.compile(r'\b(?:it|this)\b', re.I)

STRONG = [
    ('PRESCRIBING', r'\b(?:is|are)\s+(?:\w+ly\s+)?prescribed\b'),
    ('PRESCRIBING', r'\bdoctors?\s+(?:\w+ly\s+|may\s+|can\s+|will\s+|often\s+)?prescribe\b'),
    ('PRESCRIBING', r'\bprescription[- ]only\b'),
    ('PRESCRIBING', r'\bprescription\s+(?:antibiotic\s+)?(?:combination|medication|medicine|drug)\b'),
    ('PRESCRIBING', r'\brequires?\s+a\s+(?:valid\s+)?prescription\b'),
    ('PRESCRIBING', r'\bavailable\s+(?:only\s+)?(?:via|by|on)\s+prescription\b'),
    ('INSTRUCTION', r'\bcomplete\s+the\s+(?:full\s+|entire\s+)?course\b'),
    ('INSTRUCTION', r'\bfinish\s+the\s+(?:full\s+|entire\s+)?(?:prescribed\s+)?(?:course|prescription|treatment|duration)\b'),
    ('INSTRUCTION', r'\b(?:should|must)\s+(?:only\s+|strictly\s+)?be\s+(?:taken|administered|used)\b'),
    ('INSTRUCTION', r'\btake\s+(?:it|this|the\s+(?:medication|medicine|tablet|capsule)|this\s+(?:medication|medicine|combination))\b'),
    ('INSTRUCTION', r'\btaken\s+(?:as\s+directed|as\s+prescribed|exactly\s+as|with\s+food|with\s+or)\b'),
    ('INSTRUCTION', r'\bdo\s+not\s+(?:take|use)\s+(?:this|it)\b'),
    ('INSTRUCTION', r'(?<!fixed-)(?<!fixed )\b(?:dose|dosage|dosing)\b'),
    ('AVAILABILITY', r'\bcheck\s+availability\b'),
    ('AVAILABILITY', r'\bonline\s+(?:platforms|pharmacies|pharmacy)\b'),
    ('AVAILABILITY', r'\b(?:view|compare)\s+products\b|\bpricing\b'),
    ('AVAILABILITY', r'\bavailable\s+(?:in\s+india|at\s+pharmacies|online|as\s+(?:a\s+)?(?:tablets?|capsules?|injections?))\b'),
    ('AVAILABILITY', r'\bbuy\b'),
    ('PATIENT_ADDRESSED', r'\b(?:prescribed\s+(?:this|it)|been\s+taking|were\s+prescribed|has\s+a\s+doctor\s+(?:recently\s+)?prescribed'
                          r'|your\s+doctor\s+is\s+treating|doctor\s+prescribed|currently\s+taking\s+this)\b'),
    ('PRESCRIBING_LEGACY', r'\bcommonly\s+prescribed\b'),
]
STRONG = [(k, re.compile(p, re.I)) for k, p in STRONG]
WEAK = re.compile(r'\b(?:is|are)\s+(?:\w+ly\s+)?used\s+(?:to|for|in)\b|\bused\s+(?:in|for)\s+(?:the\s+)?(?:treatment|management)\b'
                  r'|\bhelps?\s+(?:to\s+)?(?:treat|relieve|manage)\b|\btreats?\b|\bindicated\s+(?:for|in)\b'
                  r'|\bprovides?\s+(?:[\w-]+\s+)?relief\b|\bmedication\s+for\b', re.I)
HISTORICAL = re.compile(r'\b(?:historically|formerly|previously\s+(?:used|marketed|prescribed|available)'
                        r'|was\s+(?:once\s+|previously\s+|historically\s+)?(?:used|marketed|prescribed|sold|available)'
                        r'|were\s+(?:once\s+)?(?:used|marketed|prescribed)|has\s+historically\s+been|used\s+to\s+be'
                        r'|when\s+it\s+was\s+(?:actively\s+)?(?:prescribed|used|marketed)|before\s+(?:its|the)\s+(?:ban|restriction|prohibition)'
                        r'|no\s+longer\s+(?:approved|marketed|available|sold|used))\b', re.I)
HIST_HEADING = re.compile(r'\b(?:historical|history|historically|previously|before\s+(?:its|the)\s+(?:ban|restriction))\b', re.I)
NEG_USE = re.compile(r'\b(?:not|no\s+longer|never)\s+(?:be\s+)?(?:used|prescribed|available|marketed|approved)\b', re.I)
VARIABLE = re.compile(r'\b(?:often|frequently|sometimes|usually|commonly)\s+(?:also\s+)?(?:grouped|paired|combined|formulated|included|added)\s+with\b'
                      r'|\bwhen\s+included\b|\bin\s+this\s+blend\b|\boften\s+with\s+an\s+additional\b', re.I)
COADMIN = re.compile(r'\b(?:intravenous\s+regional\s+an(?:a)?esthesia|ivra|co-?administ\w*|adjuvant|when\s+combined\s+with|pre-procedure)\b', re.I)
OTHER_FORM = re.compile(r'\b(?:gels?|creams?|patch(?:es)?|ointments?|topical)\b', re.I)
QUESTION_OFFER = re.compile(r'\?\s*$|^(?:if\s+you|let\s+me\s+know|would\s+you|are\s+you)', re.I)


_LIST_DELIMS = {',', '+', '&', '/', ';', 'and', 'with', 'plus'}
_LIST_FILLER = {'combined', 'combination', 'of', 'the', 'a', 'an', 'fixed', 'dose', 'fixed-dose', 'fdc', 'hcl', 'hydrochloride', 'sodium',
                'potassium', 'trihydrate', 'axetil', 'citrate', 'ip', 'bp', 'usp', 'mg', 'mcg', 'ml', 'g', 'iu', 'also', 'known', 'as'}
# Descriptive class nouns allowed in an appositive ('dicyclomine, an antispasmodic, ...'); anything else there is a list member.
_CLASS_WORDS = set('''antispasmodic antispasmodics anticholinergic anticholinergics analgesic analgesics antipyretic antipyretics antibiotic
antibiotics antibacterial enzyme enzymes probiotic probiotics sulfonylurea supplement supplements mineral minerals cephalosporin
cephalosporins penicillin penicillins benzodiazepine benzodiazepines painkiller painkillers anaesthetic anesthetic anaesthetics anesthetics
uricosuric agent agents compound compounds ingredient ingredients component components antidiabetic anti-inflammatory nsaid proteolytic
local muscle relaxant relaxants trace beneficial hardy synthetic mild potent oral active actives key main primary following two three four
five several multiple'''.split())
_DOSAGE_FORMS = {'tablet', 'tablets', 'tab', 'tabs', 'capsule', 'capsules', 'cap', 'caps', 'injection', 'injections', 'syrup', 'suspension',
                 'gel', 'cream', 'ointment', 'sachet', 'sachets', 'strip', 'strips', 'form', 'forms', 'preparation', 'preparations'}
# Where a noun phrase stops: verbs, prepositions and clause openers.
_NP_STOP = set('''is are was were be been being has have had can may might must should will would helps help provides provide treats treat
relieves relieve works work acts act reduces reduce used prescribed taken given marketed sold banned prohibited contains contain to for in on
at by from which that who while because as but or if when so than then there'''.split())
# Composition-bearing additions after an ingredient list (or inside a parenthetical).
_ADD_WORDS = (r'(?:and\s+also|as\s+well\s+as|along\s+with|together\s+with|in\s+addition\s+to|in\s+combination\s+with|alongside|besides|including'
              r'|(?:[a-z]+-)?(?:combined|formulated|mixed|paired|coupled|blended|compounded)\s+with|plus|with|and|\+|&|/)')
_ADDITION = re.compile(r'^\s*(?:,\s*' + _ADD_WORDS + r'?|' + _ADD_WORDS + r')\s*', re.I)
_CONTAINS = re.compile(r'\b(?:formulation|combination|product|tablets?|capsules?|medicine|medication|fdc|preparation|it|this|which)\b[^.;:]{0,40}?'
                       r'\b(?:also\s+)?(?:contains?|containing|includes?|including|(?:is\s+)?formulated\s+with)\s+', re.I)
_VARIABILITY = re.compile(r'\b(?:often|sometimes|frequently|usually|commonly|typically|occasionally|generally|may|might|can|could|some|'
                          r'when\s+included|if\s+included|depending|varies|optional(?:ly)?)\b', re.I)
_OTHER_PRODUCT = re.compile(r'\b(?:versions?|variants?|other\s+(?:formulations?|products?|brands?|combinations?|medicines?|drugs?)|'
                            r'such\s+as|e\.g|for\s+example|like|i\.e)\b', re.I)


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
# Words that may legitimately follow or precede a delimiter next to an ingredient list without being an ingredient.
_NOT_INGREDIENT = set('''which that who whose while whereas where when as is are was were be been being has have had may might can could
should will would its it their they them this these those both each also often sometimes usually other others etc in on at for from to by
not but so such including includes include or then there here combined combination combinations fixed fdc fdcs tablet tablets tab tabs
capsule capsules cap caps injection injections syrup suspension gel cream ointment medicine medicines medication medications drug drugs
formulation formulations product products brand brands dose doses dosage use uses used using help helps works work reduces relieves treats
provides acts protects blocks restores relaxes eases prevents i you we he she your our his her more less very much many some any all no only
just even still however therefore thus like due because since if unless although though after before during until within without against
between among about above below under over per via every either neither nor yes mainly mostly primarily typically generally commonly
frequently mild severe common rare side effects effect risk risks pain relief infection infections symptoms conditions patients doctors
doctor india indian government ministry central the a an of food foods meal meals water milk alcohol juice breakfast lunch dinner
empty stomach care caution glass plenty fluids liquid liquids snack'''.split())
_LIST_TOKEN = re.compile(r",|\+|&|/|;|[A-Za-z][A-Za-z0-9\-']*|\d+(?:\.\d+)?")


def _clause_word(tok):
    """Participles and adverbs ('declaring', 'improved', 'typically') start clauses, not ingredient names."""
    t = tok.lower()
    return len(t) > 4 and (t.endswith('ing') or t.endswith('ed') or t.endswith('ly'))


def _is_filler(tok):
    t = tok.lower()
    return t in _LIST_FILLER or bool(re.fullmatch(r'\d+(?:\.\d+)?', t)) or bool(re.fullmatch(r'\d+(?:mg|mcg|ml|g|iu)', t))


_RUN_BREAK = re.compile(r'[*|•·.:!?]')


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


def split_sentences(text):
    t = _PROTECT.sub(lambda m: m.group(0).replace('.', _DOT), text or '')
    t = re.sub(r'(?<=\d)\.(?=\d)', _DOT, t)
    return [s.replace(_DOT, '.').strip() for s in _SPLIT.split(t) if s.strip()]


def strip_parentheticals(text):
    """Main text without (...) asides, plus the asides. Nested parentheses are flattened."""
    asides, out, depth, buf = [], [], 0, []
    for ch in text:
        if ch == '(':
            depth += 1
            if depth == 1:
                buf = []
                continue
        elif ch == ')' and depth:
            depth -= 1
            if depth == 0:
                asides.append(''.join(buf))
                out.append(' ')
                continue
        (buf if depth else out).append(ch)
    if depth:
        asides.append(''.join(buf))
    return re.sub(r'\s+', ' ', ''.join(out)).strip(), asides


def _canon_set(text):
    return {m['canonical'] for m in find_mentions(text)}


def _classes(text):
    return {m['canonical']: m['class'] for m in find_mentions(text)}


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


INDIAN_GOV_HOST = re.compile(r'^https?://(?:[\w-]+\.)*(?:gov\.in|nic\.in)(?:[/:?#]|$)', re.I)
_TRUNC_AFTER = re.compile(r'^[\s.]*(?:[+,&]|and)?\s*(?:\.\.\.|…)')


def list_truncated(text):
    """True if the text's last ingredient mention runs straight into a '...'/'…' cut-off (snippet truncation), so more
    ingredients may follow and the named set is only a lower bound. Seen in live SerpApi reference snippets."""
    ms = find_mentions(text or '')
    if not ms:
        return False
    rest = text[ms[-1]['end']:]
    return bool(_TRUNC_AFTER.match(rest)) or bool(re.match(r'^\s*[+,]\s*$', rest))


def restriction_statements(text, entry, url=None, include_truncated=False, as_of=None):
    """Sentences that establish a current Indian restriction on exactly this entry's ingredient set (organic T2, snapshot
    T3, status capture, legacy fields). Delegates to semantics.restriction_assessment: one qualifying legal event bound to
    the exact named set, a SUPPORTED_EXACT composition for the whole text, no truncation, no hedge."""
    from .semantics import restriction_assessment
    return restriction_assessment(text, entry, url, include_truncated, as_of)['statements']


def _strong_cues(text):
    return [(k, m.group(0)) for k, rx in STRONG for m in [rx.search(text)] if m]


def _valid_index(i):
    """A reference index is a plain non-negative int: True, 0.0, '0' and None are malformed (never equal to 0 here)."""
    return type(i) is int and i >= 0


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


def reference_index_map(references):
    """index -> reference for well-formed, unique indexes; duplicate and malformed indexes are never resolved
    (no last-write-wins): ({index: ref}, sorted duplicate indexes, count of malformed indexes)."""
    refs = [r for r in references or [] if isinstance(r, dict)]
    ok = [r for r in refs if _valid_index(r.get('index'))]
    counts = {}
    for r in ok:
        counts[r['index']] = counts.get(r['index'], 0) + 1
    dup = sorted(i for i, n in counts.items() if n > 1)
    return {r['index']: r for r in ok if counts[r['index']] == 1}, dup, len(refs) - len(ok)


def _claim_restriction(events, main, full):
    """Claim-level view of a sentence's legal events. Only events bound to the subject decide current_india."""
    from .semantics import event_qualifies
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
    from .semantics import EXACT, UNRESOLVED, answer_composition, resolve_chronology, sentence_events
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
