"""Claim-level analysis of one AI answer surface (AI Overview or AI Mode).

Every judgement is made per sentence and bound to an entity:
  EXPLICIT_EXACT    sentence names exactly the answer's subject combination
  SUBJECT_ANAPHORA  'this combination', 'the medication', ... refers back to the subject
  SUBJECT_IMPLICIT  instruction with no entity (e.g. 'Complete the course: ...'), outside a component bullet
  COMPONENT_ONLY    names only some of the subject's ingredients (pharmacology of a component)
  OTHER_ENTITY      names something else (another product, extra actives, 'a different product')
  UNBOUND           no entity and no safe default
Restrictions never bind implicitly. Composition (one formulation entity per text) and restriction status (one legal event per
predicate, bound to its own clause, with per-entity chronology) come from the shared core banlag/semantics/, which every
promotion path uses. The preregistered A-F label is assigned in the locked order
A -> B -> D -> F -> E -> C (PREREGISTRATION_BANLAG_V2_LOCKED.txt, section 4).

Package layout: patterns.py, sentences.py, jurisdiction.py, composition.py, analysis.py.
Every name is re-exported here, so `from banlag.claims import name` keeps working.
"""

from .patterns import (ANAPHORA, COADMIN, CONDITIONAL, CURRENT_YEAR, EARLIER_RESTRICTION, GENERIC_MARK, HEDGE,
    HISTORICAL, HIST_HEADING, HIST_RESTRICT, INDIA, INDIAN_GOV_HOST, NEGATED, NEG_USE, NOT_RECOMMENDED, OTHER_FORM,
    OTHER_JURIS, OTHER_MARK, PRONOUN, PRONOUN_REVERSAL, PROPOSED, PROPOSED_FUTURE, QUESTION_OFFER, RESTRICT, REVOKED,
    REVOKED_SENTENCE, STRONG, VARIABLE, WEAK, _ADDITION, _ADD_WORDS, _AFTER_CUT, _CLASS_WORDS, _CONTAINS,
    _DOSAGE_FORMS, _DOT, _LIST_DELIMS, _LIST_FILLER, _LIST_TOKEN, _MONTH, _NON_PLACE, _NOT_INGREDIENT, _NP_STOP,
    _OTHER_PRODUCT, _PLACE, _PROTECT, _RUN_BREAK, _SPLIT, _TIME, _TRUNC_AFTER, _VARIABILITY)  # noqa: F401
from .sentences import _valid_index, list_truncated, reference_index_map, split_sentences, strip_parentheticals  # noqa: F401
from .jurisdiction import (_jurisdiction_marks, _place_kind, _predicate_jurisdiction, restriction_qualifiers,
    restriction_status)  # noqa: F401
from .composition import (_allowed_word, _canon_set, _classes, _classify_items, _clause_word, _is_filler, _np_after,
    _np_items, _paren_issues, composition_issues, list_runs, unknown_list_items)  # noqa: F401
from .analysis import (_bind, _claim_restriction, _strong_cues, analyze_surface, restriction_statements,
    status_question_hint)  # noqa: F401
from ..legal import entry_by_notice, find_mentions, match_set, notice_numbers  # noqa: F401  (historical re-export)
