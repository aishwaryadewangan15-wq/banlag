# Test suite map

Run all tests with `python -m unittest discover -s tests`. Coverage is `coverage run -m unittest discover -s tests && coverage report`. CI fails below the `fail_under` floor in `pyproject.toml`.

No test touches the network or needs a SerpApi key. Five tests skip unless the machine-local sealing key for the archived run is present.

## By behaviour

| Behaviour | Where it is tested |
|---|---|
| **Exact-composition matching**: subsets, supersets, look-alikes, duplicates and unknown names never inherit a ban | `test_properties.py` (every registry entry, randomised), `test_core.py`, `test_audit2_exact_composition_citations.py` (B) |
| **Restriction status**: negation, revocation, proposals, conditions, other jurisdictions and chronology | `test_semantic_core.py`, `test_properties.py`, `test_audit1_composition_corpus_tiers.py` (P1-4), `test_audit2_exact_composition_citations.py` (D) |
| **Composition in prose**: additions, denials, parentheticals, lead and prior clauses | `test_audit2_exact_composition_citations.py` (B), `test_audit3_gate_bypasses.py`, `test_audit4_lead_clause_binding.py` |
| **Citations**: `reference_indexes`, reconciliation of title, snippet and URL, truncation, malformed indexes | `test_citations.py`, `test_audit2_exact_composition_citations.py` (C), `test_live_run.py` |
| **Import trust**: forged origins, cross-surface joins, asserted page text; every import stays `USER_SUPPLIED_UNVERIFIED` | `test_security_audit_blockers.py`, `test_audit1_composition_corpus_tiers.py` (P1-3) |
| **Collector and sealed store**: double approval, the 3-call cap, no retries, key redaction, key-location safety | `test_capture_store.py`, `test_collector_cli.py` |
| **Corpus integrity**: pinned anchor, fail-closed loading, byte-identical re-ingestion of the locked archive | `test_corpus.py`, `test_evidence_ingest.py`, `test_audit2_exact_composition_citations.py` (A) |
| **Public output contract**: parser readings never reach a public headline | `test_public_contract.py` |
| **Local web server**: loopback only, DNS rebinding, cross-site, CSP, size limits, no outbound modules | `test_http.py`, `test_http_hardening.py`, `test_capture_store.py` (AST import closure) |
| **Static demo**: built from real server responses, local UI unchanged | `test_static_demo.py` |

## Audit regression suites

Four files keep the counterexamples from each independent audit round, each paired with positive controls, so a fix can't pass by refusing everything. They're named for what they cover, and the audit order is in the file name:

| File | Audit round |
|---|---|
| `test_security_audit_blockers.py` | Starter security and evidence audit (3 critical, 1 high) |
| `test_audit1_composition_corpus_tiers.py` | Codex hostile audit 1 (5 P1, 2 P2) |
| `test_audit2_exact_composition_citations.py` | Codex hostile audit 2 (A–E acceptance criteria) |
| `test_audit3_gate_bypasses.py` | RC-1 architecture audit (2 P1 gate bypasses, 5 P2) |
| `test_audit4_lead_clause_binding.py` | RC-2 acceptance audit |

The before-and-after runs are kept on the `engineering-history` branch (see `docs/ENGINEERING_HISTORY.md`). `baseline_v01/` is the frozen, byte-identical V0.1 starter suite; it's excluded from linting and is never edited.
