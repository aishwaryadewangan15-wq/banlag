"""Verdict constants and regex vocabulary for composition membership and restriction events."""

import re


EXACT, DIFFERENT, UNRESOLVED = 'SUPPORTED_EXACT', 'DIFFERENT', 'UNRESOLVED'
NOT_ESTABLISHED = 'NOT_ESTABLISHED'  # an evidence text that never names the target formulation (never a pass)
TARGET_BINDINGS = ('EXPLICIT_EXACT', 'SUBJECT_ANAPHORA')
# ----------------------------------------------------------------------------------------------------------------------
# Composition
# ----------------------------------------------------------------------------------------------------------------------
_ORD = {'second': 2, 'third': 3, 'fourth': 4, 'fifth': 5, 'sixth': 6, 'seventh': 7, 'eighth': 8, '2nd': 2, '3rd': 3, '4th': 4,
        '5th': 5, '6th': 6}
_CNT = {'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6, 'seven': 7, 'eight': 8}
_COMP_NOUN = (r'(?:active\s+)?(?:ingredients?|components?|constituents?|actives|active\s+(?:drugs?|substances?|agents?)|drugs?|medicines?'
              r'|active(?=\s*(?:[,:;.)]|$)))')
ORDINAL_COUNT = re.compile(r'\b(?:(?P<ord>second|third|fourth|fifth|sixth|seventh|eighth|[2-6](?:nd|rd|th))|(?P<cnt>one|two|three|four|five|six|seven|'
                           r'eight|[1-8]))[\s-]+(?:(?:additional|extra|other|more|separate|different|distinct)\s+)?' + _COMP_NOUN + r'\b', re.I)
ADDITIVE_MARK = re.compile(r'\b(?:another|an\s+additional|additional|an\s+extra|extra|one\s+more|a\s+further|further)\s+(?:active\s+)?'
                           r'(?:ingredient|component|constituent|active|drug|medicine|substance|agent)s?\b', re.I)
EXCIPIENT = re.compile(r'\b(?:excipients?|inactive|fillers?|binders?|coating|flavou?r\w*|colou?r(?:ant|ing)s?|preservatives?|sweeteners?|'
                       r'base|vehicle|carrier|lubricants?|disintegrants?)\b', re.I)
_HOLDER_NOUN = (r'(?:medicine|medication|formulation|combination|combo|product|tablet|capsule|pill|preparation|fdc|drug|blend|mixture|'
                r'dose|strip|syrup|suspension|brand)')
HOLDER_ANAPHOR = re.compile(r'\b(?:it|its|they|their|them|this|these|' r'(?:the|this|that|said|same|each|every|one|its|their)\s+(?:same\s+)?'
                            r'(?:[\w-]+\s+){0,2}?' + _HOLDER_NOUN + r's?)\b', re.I)
SETREF = re.compile(r'\b(?:the|these|those|all|its|their)\s+(?:(?:three|two|four|\d+)\s+)?(?:above|aforementioned|mentioned|listed|named|'
                    r'ingredients?|components?|drugs?|actives|medicines?)\b(?:\s+(?:above|mentioned|listed|named))?'
                    r'|\b(?:the|these|those|all)\s+(?:three|two|four)\b', re.I)
_MEMBER_NEG = re.compile(r"\b(?:not|never|no|n['’]t|without|free\s+of|free\s+from)\b", re.I)
# '<holder> [also] contains X' (finite verbs; 'containing' only after a holder noun, never bare 'including').
P_VERB = re.compile(r'^(?P<holder>.*?)\b(?P<add>(?:also|additionally|further|too)\s+)?(?P<neg>(?:does|do|did)\s+not\s+|doesn[\'’]t\s+|don[\'’]t\s+)?'
                    r'(?P<verb>contains?|comprises?|consists?\s+of|includes?|holds?|incorporates?|'
                    r'(?:is|are)\s+(?:also\s+|additionally\s+)?(?:made|formulated|compounded|prepared)\s+(?:with|from|using)|'
                    r'(?:is|are)\s+(?:also\s+)?combined\s+with|'
                    # a strength statement is a membership statement: 'each tablet carries / has 20 mg of X'
                    r'(?:has|have|carries|carry|delivers|deliver|packs|provides|provide)(?=\s+(?:about\s+|around\s+)?\d+(?:\.\d+)?\s*(?:mg|mcg|g|ml|iu)\b))\b'
                    r'(?P<obj>.*)$', re.I)
# '<holder> adds X to <the three / it / the combination>'
P_ADDS = re.compile(r'^(?P<holder>.*?)\b(?:adds?|added)\s+(?P<items>.+?)\s+(?:to|into)\s+(?P<target>.+)$', re.I)
# 'There is (also) X in <holder>'
P_EXIST = re.compile(r'^(?P<pre>.*?)\bthere\s+(?:is|are)\s+(?P<add>(?:also|additionally)\s+)?(?P<items>.+?)\s+(?:in|inside|within)\s+(?P<holder>.+)$', re.I)
# '<holder> has X too / as well': additive possession; X may be a property rather than an ingredient -> UNRESOLVED
P_HAS_TOO = re.compile(r'^(?P<holder>.*?)\b(?:also\s+)?(?:has|have)\s+(?P<obj>.+?)\s+(?:too|as\s+well)\s*[.!]?\s*$', re.I)
P_CONTAINING = re.compile(r'^(?P<holder>.*?\b' + _HOLDER_NOUN + r's?)\s+(?P<add>(?:also|additionally)\s+)?containing\b(?P<obj>.*)$', re.I)
# '<holder> has X as (another / its fourth / an additional) (active) ingredient'
P_HAS_AS = re.compile(r'^(?P<holder>.*?)\b(?:has|have|having|uses?|with)\s+(?P<items>.+?)\s+as\s+(?:its|an?|another|the|their|one\s+of\s+its)?\s*'
                      r'(?:(?P<ord>\w+)\s+)?(?:(?:additional|extra|other|further)\s+)?(?:active\s+)?(?:ingredient|component|constituent|active)s?\b', re.I)
# 'X is (also) in / part of / an ingredient of <holder>'; 'X is (also) included / added' (implicit holder)
P_PASSIVE = re.compile(r'^(?P<items>.*?)\b(?:is|are)\s+(?P<add>(?:also|additionally|further)\s+)?(?P<neg>not\s+|never\s+)?(?P<add2>(?:also|additionally)\s+)?'
                       r'(?:(?:present|found|included|contained|added|incorporated|blended|mixed)\s+(?:in|into|to|within|with)|in|inside|within|'
                       r'part\s+of|(?:an?|another|the|one)\s+(?:(?:\w+)\s+)?(?:active\s+)?(?:ingredient|component|constituent)s?\s+(?:of|in))\s+(?P<holder>.*)$', re.I)
P_LOADED = re.compile(r'^(?P<holder>.*?)\b(?:is|are)\s+(?P<add>(?:also|additionally)\s+)?(?:loaded|fortified|enriched|mixed|blended|combined|'
                      r'co-?formulated|supplemented)\s+with\s+(?P<obj>.+)$', re.I)
P_IMPLICIT = re.compile(r'^(?P<items>.*?)\b(?:is|are)\s+(?P<add>(?:also|additionally)\s+)?(?:included|added|incorporated|present)\s*[.!]?\s*$', re.I)
# '<det> (fourth|other) (active) ingredient(s) is/are X'
P_ROLE = re.compile(r'^(?P<holder>.*?)\b(?P<det>its|their|the|this|that)\s+(?:(?P<ord>\w+)\s+)?(?:(?:additional|extra|other|remaining|full|complete|exact)\s+)?'
                    r'(?:active\s+)?(?:ingredients?|components?|constituents?|actives|composition|formula)\s+(?:is|are|include|includes|comprise|comprises|'
                    r'consist\s+of)\s+(?P<items>.+)$', re.I)
_REL_CUT = re.compile(r'\b(?:which|that|who|whom|whose|where|because|so\s+that|to\s+(?:treat|relieve|help|reduce|provide)|for\s+(?:the|treating|relief))\b', re.I)
_CLAUSES = re.compile(r';|,?\s+\b(?:but|however|whereas|although|though|while|whilst)\b', re.I)
_OTHER_INTRO = re.compile(r'^\s*(?:[A-Z][\w-]+(?:\s+[A-Za-z][\w-]+)?)\s+(?:is|are|was|were)\s+(?:a|an|the|also\s+a)\s+(?:[\w-]+\s+){0,3}?'
                          r'(?:medicine|drug|medication|product|tablet|antacid|antibiotic|inhibitor|ppi|supplement|treatment)\b')
# ----------------------------------------------------------------------------------------------------------------------
# Legal events
# ----------------------------------------------------------------------------------------------------------------------
_REVOKE = re.compile(r'\b(?:revok\w*|rescind\w*|lift(?:ed|s|ing)?|quash\w*|stay(?:ed|s)?|set\s+aside|struck\s+down|strike\s+down|overturn\w*|repeal\w*|'
                     r'cancel+(?:ed|led|s)?|reversed|invalidated|withdr[ae]wn?)\b', re.I)
_AUX = re.compile(r'\b(?:is|are|was|were|be|been|being|remains?|remained|stays?|stayed|got|gets|become|became)\b', re.I)
_NEG_WORD = re.compile(r"^(?:not|never|neither|nor|cannot|no|none|nobody|nothing|\w+n['’]t)$", re.I)
_NEG_STOP = {'because', 'since', 'as', 'after', 'which', 'that', 'who', 'so', 'and', 'but', 'although', 'though', 'while', 'whereas',
             'if', 'when', 'unless', 'whether'}
_TOK = re.compile(r"[A-Za-z]+(?:['’][A-Za-z]+)?|[,;:]")
DENIAL = re.compile(r"\b(?:not|never|no|n['’]t)\b[^.;]{0,40}?\b(?:true|correct|accurate|case|right|so|evidence|proof|record|basis|truth)\s+(?:that|whether|of)\b"
                    r"|\b(?:den(?:y|ies|ied|ying)|refut\w*|reject(?:s|ed|ing)?|disput\w*|dismiss(?:es|ed|ing)?|rebut\w*|contradict(?:s|ed|ing)?)\b"
                    r"|\b(?:false|untrue|incorrect|inaccurate|wrong|a\s+myth|misconception|misinformation|baseless|unfounded|hoax|fake)\b[^.;]{0,20}?\b(?:that|to\s+(?:say|claim))\b"
                    r"|\bcontrary\s+to\s+(?:claims?|reports?|rumou?rs?|popular\s+belief)", re.I)
# 'Reports / claims that <restriction> are false': the restriction is the content of a report that is then denied.
REPORT_THAT = re.compile(r"\b(?:reports?|claims?|suggestions?|rumou?rs?|statements?|news|posts?|idea|notion|belief|assertions?)\s+that\b", re.I)
FALSITY_AFTER = re.compile(r"\b(?:is|are|was|were|has\s+been|have\s+been)\s+(?:\w+\s+)?(?:false|untrue|incorrect|wrong|baseless|unfounded|misleading|"
                           r"inaccurate|a\s+myth|fake|denied|refuted|debunked)\b", re.I)
REPORTED = re.compile(r"\b(?:uncorroborated|unsubstantiated|unofficial|anecdotal|unconfirmed|unverified|alleged(?:ly)?|purported(?:ly)?|rumou?r\w*|speculat\w*)\b"
                      r"|\b(?:reports?|rumou?rs?|claims?|posts?|articles?|sources?|people|users|some|many|others)\s+(?:\w+\s+)?"
                      r"(?:say|says|said|claim\w*|suggest\w*|allege\w*|stated?|states|indicated?|indicates)\b"
                      r"|\b(?:some|unnamed|anonymous|social[\s-]+media|online|media)\s+(?:\w+\s+)?(?:say|says|claim\w*|report\w*|post\w*|sources?)\b"
                      r"|\b(?:it\s+is|it['’]s)\s+(?:said|claimed|rumou?red|alleged|reported|believed|thought)\s+that\b"
                      r"|\b(?:claims?|alleges?|suggests?)\s+that\b"
                      r"|\baccording\s+to\s+(?!(?:the\s+)?(?:gazette|notification|government|central|ministry|mohfw|cdsco|dcgi|dtab|section|official|law|"
                      r"act|rules|order|india|indian|drugs\s+and\s+cosmetics|s\.\s?o\.?|notice))", re.I)
PROVISO_AFTER = re.compile(r"\b(?:if(?!\s+(?:you|your|a\s+patient|patients?|someone|anyone|one|we|i)\b)|unless|provided|providing|on\s+(?:the\s+)?condition|subject\s+to(?!\s+(?:a|an|the|this|its)?\s*(?:ban|prohibition|restriction))|"
                           r"only\s+(?:if|when|where|for|in)|in\s+case|except|depending\s+on|conditional|where\s+(?:applicable|appropriate|clinically|medically|"
                           r"necessary|required)|when\s+(?:used|sold|combined|taken|given|prescribed|marketed|formulated|administered))\b", re.I)
# A restriction limited to a population or age group is not the notice's unconditional ban ('for human use' is the notice's
# own scope and stays affirmative).
SCOPE_LIMIT = re.compile(r"\b(?:for|in|among|to)\s+(?:use\s+in\s+)?(?:children|kids|infants|minors|adolescents|adults|the\s+elderly|elderly|"
                         r"pregnant|women|men|paediatric|pediatric|geriatric|(?:patients|people|persons|those)\s+(?:with|under|over|below|above|aged))\b"
                         r"|\b(?:under|below|above|over)\s+(?:the\s+)?age\b|\b(?:under|below|over|above)\s+\d+\s*(?:years?)?\b|\baged\s+\d+"
                         r"|\bfor\s+(?!human\b)[\w-]+\s+use\b|\b(?:use|uses|purposes?)\s+only\b", re.I)
# 'The ban covers / applies to <X>': a later statement of what a restriction is about. If X is another entity, the
# restriction it refers to is not shown to be about the exact formulation.
BAN_SCOPE = re.compile(r'\b(?:the|this|that|its|such\s+a)\s+(?:ban|prohibition|notification|restriction|order)\s+(?:only\s+)?'
                       r'(?:covers?|applies\s+(?:only\s+)?to|concerns?|relates\s+to|is\s+(?:about|for|limited\s+to)|targets?|extends\s+to)\s+(?P<obj>.+)', re.I)
IF_BEFORE = re.compile(r"\bif\s+(?!you\b|your\b|a\s+patient|patients?\b|someone|anyone|one\b|we\b|i\b)", re.I)
_ENTITY_STOP = set('''manufacture manufacturing sale sales sell selling distribution distribute import imports export exports marketing
production stocking stock use usage human humans consumption prescription prescribing government governments authority authorities regulator
regulators regulatory court courts tribunal ministry department health family welfare drug drugs controller general board committee
parliament cabinet central state union notification notifications gazette section act rule rules order orders law laws ban bans prohibition
prohibitions restriction restrictions country countries market markets nation nationwide officials official cdsco dcgi dtab mohfw fda ema mhra
who regulators agency agencies supreme high delhi bench judge judges also now again currently presently still already officially formally legally
completely totally fully entirely partially immediately effectively hereby further therefore january february march april may june
july august september october november december jan feb mar apr jun jul aug sep sept oct nov dec'''.split())
