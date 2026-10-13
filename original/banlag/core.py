"""Compatibility surface for the V0.1 starter API (inherited names, hardened behaviour).

V0.1 -> V0.2 changes (see docs/HARDENING_REPORT.md):
- evaluate(): delegates to engine.evaluate(); imports are USER_SUPPLIED_UNVERIFIED whatever source_kind they declare,
  citations bind per claim and per surface, imported cited-page text never counts as verified evidence.
- text_identifies_exact(): sentence-level; a ban in a neighbouring sentence on another product no longer counts.
- answer_identifies_exact(): the lead sentence must name exactly the ingredient set (claim-level), not words anywhere.
- classify(): text-only legacy helper; the engine itself never uses it to assign tiers.
"""
from .claims import (HISTORICAL, NEGATED, OTHER_MARK, RESTRICT, REVOKED_SENTENCE, WEAK, _strong_cues, analyze_surface,
                     restriction_statements, split_sentences)
from .engine import _surface, evaluate  # noqa: F401  (re-exported)
from .legal import canonical, match_formula, norm, registry  # noqa: F401  (re-exported)


def classify(text, exact=True, entry=None):
    """Legacy label for a text with no structure. With an entry, delegates to the claim-level analyser."""
    if not exact:
        return 'ENTITY_OR_SCOPE_UNKNOWN'
    if not isinstance(text, str) or not text.strip():
        return 'NO_AI_ANSWER'
    if entry is not None:
        from .engine import legacy_classification
        a = analyze_surface([{'id': 'b0', 'type': 'paragraph', 'label': None, 'text': text, 'chips': []}], target_entry=entry)
        return legacy_classification(a, True)
    if NEGATED.search(text) or REVOKED_SENTENCE.search(text):
        return 'LEGAL_STATUS_CONFLICT_REVIEW'
    if any(RESTRICT.search(s) and not OTHER_MARK.search(s) for s in split_sentences(text)):
        return 'RESTRICTION_MENTIONED'
    if HISTORICAL.search(text):
        return 'HISTORICAL_DESCRIPTION'
    if _strong_cues(text):
        return 'STRONG_CURRENT_USE_UNWARNED'
    if WEAK.search(text):
        return 'GENERAL_USE_UNWARNED'
    return 'INSUFFICIENT_EVIDENCE'


def extract_ai(raw):
    s = _surface(raw, 'AI')
    text = '\n'.join(((b['label'] + ': ') if b.get('label') else '') + b['text'] for b in s['blocks'] if b['type'] != 'heading')
    return {'text': text, 'references': s['references'], 'search_id': s['search_id'], 'created_at': s['created_at']}


def text_identifies_exact(text, row, db=None):
    """True only if one sentence states a restriction on exactly this ingredient set."""
    return bool(isinstance(text, str) and restriction_statements(text, row))


def answer_identifies_exact(text, row, db=None):
    if not isinstance(text, str):
        return False
    a = analyze_surface([{'id': 'b0', 'type': 'paragraph', 'label': None, 'text': text, 'chips': []}], target_entry=row)
    return a['subject']['entity_vs_target'] == 'EXACT'
