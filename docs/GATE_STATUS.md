# Gate status — 10 Oct 2026, ~19:30 IST (deadline 23:59 IST)

**HISTORICAL ENGINEERING SNAPSHOT — NOT THE CURRENT SUBMITTED RELEASE STATUS**

This document records intermediate engineering and acceptance decisions made during development on 10 October 2026. Its NO-GO findings, references to unverified candidate builds, and statement that the submission was not started describe those earlier checkpoints. They must not be read as the final status of the later submitted public release.

The submitted public source commit is `063a0d1c93ff24e973b4dbacab3d6f439542a653`, with authoritative source fingerprint `c635055d573cea07146c68b9a9fb89ddd06bdf1a698ca242b63bf02d7d048f73`, documented in `docs/proof/RELEASE_IDENTITY.md`.

The release introduced a stricter public-output contract that separates direct observations and mechanical comparisons from unverified language-parser interpretations. The historical NO-GO results remain relevant evidence of the parser's limitations. They are not erased by successful regression testing or by the public-output quarantine.

The project author reports that the hackathon submission was completed. This file is not independent confirmation of organizer acceptance, video accessibility or judging outcome.

For the final public-output boundary, refer to `docs/PUBLIC_CONTRACT.md`. For the judge-facing summary and honest limitations, refer to `README.md`.

> **Update, ~22:00 IST — final workbench.** Codex's RC-3 acceptance audit was **NO-GO**. The causes were a parenthetical denial or extra active that stayed "exact", and a status question that names a fourth drug.
>
> We did not repair the parser again. Every public output now passes through one contract, described in [PUBLIC_CONTRACT.md](PUBLIC_CONTRACT.md): parser readings appear only under `experimental`, and publication is never decided by software. The parser itself is unchanged and still has those defects, as experimental readings.
>
> Developer suite: 224 tests OK with the local key. Independent acceptance of the frozen identity is UNVERIFIED. The tables below describe RC-3; for G5, read "experimental parser".

Status values are PASS / FAIL / UNVERIFIED. A gate is PASS only on evidence, never because it is implemented or because BANLAG's own suite is green.

Codex's final acceptance audit of build `a95597e2…` was **NO-GO** (three P1 families). The structural repair RC-1 (`5658183e…`, shared semantic core `banlag/semantics.py`) then received a focused architecture audit: two P1 gate bypasses (a denied target ingredient; unchecked query-hinted status answers) and five P2 integration gaps. RC-2 repaired those; Codex's RC-2 acceptance audit was **NO-GO** (the validator skipped the sentence that names the formulation, so a semicolon-joined or earlier denial of a target active stayed exact; plus a status contrast without a validated question). **RC-3** repairs that family and is frozen as the current candidate (identity in `docs/proof/rc3_after.txt`). Its acceptance by an independent evaluation of the same identity is UNVERIFIED.

| Gate | Status | Basis | Open risk |
|---|---|---|---|
| G1 preregistered browser test | **PASS** | Locked rule on locked labels: 7/10 both-pass positives, 4 outside family; engine reproduces 20/20; corpus bound to a pinned trust anchor and fails closed otherwise. Unchanged by the repair (before/after G1 summary byte-identical). | single coder; positives need independent re-review before external use; archive origin not cryptographically authenticated; the anchor resists file tampering, not code edits |
| G2 legal | **PASS (notice-level, conditional wording)** | Independent legal audit; S.O. mapping re-verified from the Gazette text (also independently confirmed by Codex) | court search non-exhaustive; re-check if status > 7 days old at publication; F01/F15 spelling variants need reviewer confirmation |
| G3 differentiator | **PASS on real data, narrower than hoped** | prompt-dependent disclosure (archive, 7/7); a wrong notice number (S05); live SerpApi restriction sentence whose cited metadata names the 4-drug S.O. 3071(E) and an unresolved reference, not the asked 3-drug notice (pages not fetched) | no live Tier 2/3 omission; live headline answer is a partial disclosure (F/T0); structured citation handling is shared with GRAP Audit; no head-to-head |
| G4 SerpApi | **PASS (feasibility)** | 3 sealed calls; India AI Overview, `reference_indexes`, references, organic results, IDs/timestamps | status-search AI Overview not fetched; AI Mode not captured; local clock ~42 s behind provider |
| G5a engineering — known cases | **PASS (developer-run, RC-3)** | 211 tests with the sealing key (0 skipped), 211 keyless (5 live-run tests skipped); Codex RC-2 acceptance findings reproduced and closed (RC-3 reproduction 20/42 on RC-2 → 42/42); Codex fresh probes 64/64 (38 failed on `a95597e2`), original 48/48, extra 12/12; developer metamorphic sets pass after fixes | these are known cases; passing them is not evidence of generalisation |
| G5b engineering — unseen phrasing | **UNVERIFIED / known FAIL rate** | two developer batches run once before their fixes: 22/28 and 14/19 met the safe outcome (false exact matches and false T2 included) | rule grammar, not language understanding; independent blind holdout not yet run on the frozen identity |
| G6 submission | **NOT STARTED — needs approval** | — | public repo, video, form; incognito link check |

## Verdict: NO-GO for broad automated claims; CONDITIONAL GO for a downscoped release, pending independent blind evaluation

Truthful release mode: an **audited capture explorer** — every tier is a *candidate* with `HUMAN_REVIEW_REQUIRED`, composition and restriction decisions show their evidence spans and why-not reasons, and nothing is described as automated precision. Story: *a preregistered test found 7/10 omissions; asked separately, the same surface stated the prohibition; a live SerpApi capture of the headline query found only a class-level note whose cited metadata names a different notice — and BANLAG shows exactly which formulation each claim and citation names, abstaining where it cannot tell.* No claim of a live Tier 2/3 omission, of model knowledge or intent, of superiority over prior work, or of any control's legal status.

## Decisions needed from you

1. **Independent blind evaluation** of the frozen candidate (identity in `docs/proof/rootcause_after.txt`).
2. **Q04 SerpApi probe (≤2 calls)** — `plans/q04_probe.json`, SHA-256 `276508550d3f9d4b11b2bb05e6b4b84eff557d3d8f84d3725987912deae42ac5`. Sync the Windows clock first.
3. **Publish the sealed live capture?** `python -m banlag.capture_store export run-20261010T024515Z-9415e2` (records + raw responses, never the key) → `evidence/serpapi/`.
4. `git init` + commit, public GitHub repository, video recording/upload, submission form — each on your explicit go-ahead.
5. Confirm the project start date for the README disclosure.
