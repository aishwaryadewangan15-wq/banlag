"""Shared semantic core: ONE formulation entity per text unit, ONE legal event per restriction predicate.

Every promotion path reads composition and restriction facts from here: the answer label (D, and E via exactness),
organic Tier 2, cited-snapshot Tier 3, citation metadata views, the status capture, the UI highlight and the
publication gate. Source-specific adapters (claims.analyze_surface, restriction_assessment, citations) keep their own
completeness/truncation semantics and feed the same gates.

Supported input contract (bounded on purpose; outside it the result is UNRESOLVED / not qualifying, never a promotion):

Composition. The focus formulation is the set named by the first sentence that names one (answers), or the target set
where a sentence names it exactly (organic text, page snapshots, snippets). Later sentences change it only through a
membership assertion about it: '<holder> contains / includes / comprises / consists of / is made|formulated with X',
'<holder> has X as (another|its fourth|an additional) (active) ingredient', 'X is (also) in / part of / an ingredient of
<holder>', 'X is included / added' (implicit holder), '<holder's> (fourth|other) (active) ingredient is X', 'the three
above plus X', and ordinal or counted ingredients ('its fourth active ingredient', 'four active ingredients'). The holder
must resolve to the focus: the exact target set, 'it / its / this / the medicine|formulation|tablet|combination|...',
or an implicit passive. Another product, another named drug, a component-labelled bullet, negated membership,
excipients, strengths and food never add to the focus. A holder with two plausible antecedents -> UNRESOLVED.
Verdicts: SUPPORTED_EXACT (no known contradiction in this text - NOT proof of a real product's composition),
DIFFERENT (a stated extra or missing active), UNRESOLVED (antecedent, count or modality cannot be attached safely).

Legal events. One event per restriction predicate, bound to the entity of its own clause (passive subject, active
object, 'ban on X', an anaphor, another named subject, or inheritance from an earlier clause of the same sentence),
with polarity (AFFIRMED / NEGATED / DENIED / REPORTED), condition, proposal, dates (as of the evidence year) and
jurisdiction from that clause. Revocations are events too: they apply only to restrictions on the same entity (the
'ban on X' object, the restrictions of their own sentence, or the most recent restriction for 'that ban' / 'it'), and
a later affirmative restriction on that entity is a reinstatement. An 'earlier / 2016 ban' revocation never cancels a
present-tense current restriction.

Promotion invariant: a definitive D / T2 / T3 needs ONE event that is target-bound, affirmed, unconditional, not
proposed, current, Indian and not revoked, AND a SUPPORTED_EXACT composition for that text. Provenance (HMAC seal,
Indian government host) is orthogonal and never repairs a failed attribute; a host only supplies jurisdiction to an
otherwise unqualified, target-bound statement.

Package layout: patterns.py, composition.py, events.py.
Every name is re-exported here, so `from banlag.semantics import name` keeps working.
"""

from .patterns import (ADDITIVE_MARK, BAN_SCOPE, DENIAL, DIFFERENT, EXACT, EXCIPIENT, FALSITY_AFTER, HOLDER_ANAPHOR,
    IF_BEFORE, NOT_ESTABLISHED, ORDINAL_COUNT, PROVISO_AFTER, P_ADDS, P_CONTAINING, P_EXIST, P_HAS_AS, P_HAS_TOO,
    P_IMPLICIT, P_LOADED, P_PASSIVE, P_ROLE, P_VERB, REPORTED, REPORT_THAT, SCOPE_LIMIT, SETREF, TARGET_BINDINGS,
    UNRESOLVED, _AUX, _CLAUSES, _CNT, _COMP_NOUN, _ENTITY_STOP, _HOLDER_NOUN, _MEMBER_NEG, _NEG_STOP, _NEG_WORD, _ORD,
    _OTHER_INTRO, _REL_CUT, _REVOKE, _TOK)  # noqa: F401
from .composition import (_clause_spans, _count_effect, _difference_markers, _holder_kind, _introduces_other, _items,
    _object_names, _worst, answer_composition, composition_state, membership_assertions, text_composition)  # noqa: F401
from .events import (_content_words, _entity, _event_entity, _jurisdiction, _neg_before, event_qualifies, gov_host,
    resolve_chronology, restriction_assessment, sentence_events, text_events)  # noqa: F401
from ..claims import (ANAPHORA, CONDITIONAL, CURRENT_YEAR, EARLIER_RESTRICTION, GENERIC_MARK, HEDGE, HIST_RESTRICT, INDIA,
                     INDIAN_GOV_HOST, NEGATED, OTHER_JURIS, OTHER_MARK, PRONOUN_REVERSAL, PROPOSED, PROPOSED_FUTURE, RESTRICT,
                     REVOKED, REVOKED_SENTENCE, _ADDITION, _OTHER_PRODUCT, _TIME, _VARIABILITY, _allowed_word, _canon_set,
                     _classify_items, _jurisdiction_marks, _np_after, _np_items, _predicate_jurisdiction, composition_issues,
                     list_truncated, notice_numbers, split_sentences, strip_parentheticals)  # noqa: F401  (historical re-export)
from ..legal import find_mentions  # noqa: F401  (historical re-export)
