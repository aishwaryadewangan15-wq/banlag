"""Regex vocabulary for the claim-level reader: restriction, negation, revocation, jurisdiction, use and list cues."""

import re


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
OTHER_MARK = re.compile(r'\b(?:different|another|other|unrelated|separate)\s+(?:\w+\s+)?(?:product|drug|medicine|combination|formulation|fdc)s?\b', re.I)
GENERIC_MARK = re.compile(r'\b(?:fdcs|fixed[- ]dose\s+combinations|combinations|some\s+(?:drugs|medicines|products))\b', re.I)
NOT_RECOMMENDED = re.compile(r'\b(?:irrational|not\s+approved|not\s+recommended|unjustified|lacks?\s+(?:therapeutic\s+)?justification)\b', re.I)
ANAPHORA = re.compile(r'\b(?:this|the|that|said)\s+(?:specific\s+|particular\s+|exact\s+)?(?:[\w-]+[- ](?:drug|ingredient)\s+)?'
                      r'(?:fixed[- ]dose\s+)?(?:combination|combo|fdc|formulation|medication|medicine|product|blend|pairing|preparation)\b', re.I)
PRONOUN = re.compile(r'\b(?:it|this)\b', re.I)
_STRONG_SOURCES = [
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
STRONG: list[tuple[str, re.Pattern[str]]] = [(k, re.compile(p, re.I)) for k, p in _STRONG_SOURCES]
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
_RUN_BREAK = re.compile(r'[*|•·.:!?]')
INDIAN_GOV_HOST = re.compile(r'^https?://(?:[\w-]+\.)*(?:gov\.in|nic\.in)(?:[/:?#]|$)', re.I)
_TRUNC_AFTER = re.compile(r'^[\s.]*(?:[+,&]|and)?\s*(?:\.\.\.|…)')
