# Engineering history

BANLAG went through several rounds of independent adversarial auditing before its hackathon submission. The full record is preserved, unchanged, on the [`engineering-history`](https://github.com/aishwaryadewangan15-wq/banlag/tree/engineering-history) branch, which points at commit `a84c345`.

## What's there

| Path on `engineering-history` | Contents |
|---|---|
| `docs/HARDENING_REPORT.md` | The V0.1 → V0.2 hardening report, with addenda for each audit round |
| `docs/GATE_STATUS.md` | Status of the project's research gates (G1 browser study, G2 legal, G3 differentiator) |
| `docs/FREEZE_AND_GATES.md` | The frozen project thesis and gate definitions, written before testing |
| `docs/proof/` | Before/after outputs and reproduction scripts for every audit round (blockers, Codex P1, Codex 2, RC-2, RC-3, root-cause) |
| `docs/proof/RELEASE_IDENTITY.md` | The source-fingerprint method for the submitted commit |
| `BUILD_SHA256_MANIFEST.json` | The local V0.2 build manifest (not the release identity) |

## Summary of the audit rounds

1. **V0.1 starter → V0.2.** Blocker reproductions and 28 hostile tests failed on V0.1 and passed on V0.2.
2. **First live SerpApi probe (10 Oct 2026).** One approved 3-call run, coded F / T0. It led to fixes for class-level restrictions, snippet truncation and reference-index normalisation.
3. **Codex audit 1 (5 P1, 2 P2).** Fixed at the root, with 17 regression tests (`tests/test_codex_p1.py`).
4. **Codex audit 2.** Its harness failed 27/48 before the fixes and 0/48 after, with 27 regression tests (`tests/test_codex_p1b.py`).
5. **RC-1 → RC-3 and the root-cause pass.** A shared semantic core (`banlag/semantics.py`) and repairs to the gate-bypass families (`tests/test_rc2_repairs.py`, `tests/test_rc3_repairs.py`).

These are engineering verification results. They are **not** accuracy measurements of the parser on general language.

## Hackathon submission

- Submitted commit: `063a0d1c93ff24e973b4dbacab3d6f439542a653`
- Source fingerprint: `c635055d573cea07146c68b9a9fb89ddd06bdf1a698ca242b63bf02d7d048f73`
