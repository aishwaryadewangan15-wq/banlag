# Public-output contract (final workbench, 10 Oct 2026)

Why: Codex's independent audits showed, four times in a row, that the English parser can call a formulation "exact" when the prose contradicts it (most recently with a parenthetical "(it does not contain paracetamol)"). Those false readings reached labels E/D, tiers T1–T3, QUALIFYING citations, green highlighting and publication eligibility. We did not patch the parser again. Instead, no parser output can reach a public headline any more.

## One enforcement point

`banlag/server.py` calls `banlag.public.public()` from `Handler._json` when constructing JSON responses. That invocation is shared, but the handling is route-dependent.

For assessment and evidence routes such as `GET /api/overview`, `GET /api/case/{id}`, `GET /api/live` and `POST /api/evaluate`, `public()` applies the recursive field allowlist. Keys explicitly designated as observed, registered or mechanical remain available, selected opaque structures are passed through as defined in code, and other interpretation fields are moved into `experimental`.

The code explicitly treats `GET /api/registry`, `POST /api/match` and `GET /api/status` as pass-through routes. These provide typed registry information, typed ingredient-list matching and server status, respectively; they do not undergo the same recursive assessment-output filtering.

Therefore, the contract is not accurately described as identical recursive allowlisting of every JSON endpoint. Its protection applies to the specific routes, fields and opaque structures implemented in `banlag/public.py`.

**Version 2, an allowlist (22:58 IST, after Codex's NO-GO).** For assessment and evidence responses, `public()` applies `ALLOWED` and `OPAQUE` as defined in `banlag/public.py`. Listed public fields and specifically designated opaque structures remain available. Other fields are moved into `experimental`, with `reading_status: EXPERIMENTAL_NOT_VERIFIED`. This is a boundary on public research interpretation, not proof that the underlying English parser is accurate. The typed pass-through routes described above are a separate part of the contract. Codex showed that the version-1 denylist below let `explicit_exact_entity`, `classification`, `registry_match`, `tier_explanation` and `status_answer_label` escape; the allowlist closes that class. The version-1 description follows for history: it moved every machine reading of prose under an `experimental` key, wherever it occurs. The key is marked `reading_status: EXPERIMENTAL_NOT_VERIFIED`. The fields it moves:

- labels: `prereg_label`, `engine_label`;
- tiers: `tier`, `evidence_tier`, `verified_evidence_tier`, `tier_status`, `tier2_hits`;
- citation readings: `restriction`, `restriction_support`;
- contrasts: `explicit_status_contrast`, `paired_prompt_contrast`;
- gates and metrics: `publication_gate`, `release_status`, the agreement and benchmark tables;
- and any field whose value is `SUPPORTED_EXACT`, `QUALIFYING` or `ELIGIBLE_FOR_REVIEW`.

These fields are moved, not deleted: a researcher can still inspect them. Every response also carries `public_contract`, whose `publication` value is always `NOT_DETERMINED_BY_SOFTWARE`. No human review is recorded anywhere.

| Kind | Public as | Examples |
|---|---|---|
| A. Observed | Top-level fields | AI text blocks; search IDs and provider times; references (title, snippet, link, source); organic results; sealed-run provenance. A keyless replay says `ARCHIVED_SERPAPI_CAPTURE`, i.e. origin not authenticated here. |
| B. Registered | Top-level fields | Gazette entries (notice, exact ingredient list, operative text). `/api/match` looks up a typed, complete ingredient list. |
| C. Mechanical | `answers[].observations` | Block → valid `reference_indexes` → captured reference. Malformed, duplicate and missing indexes are listed and never linked. Registry names and notice-number strings are reported only as literally present. A registry entry whose names all appear is a **candidate mapping**: a mention list is not an exhaustive ingredient list. Cut-off text stays unresolved. Typed set differences come from the Gazette sets. |
| D. Experimental | `experimental` | Everything the parser concludes from prose. |

## The browser

`web/app.js` reads parser readings only through `xp()`, which reads the `experimental` namespace, and labels them as experimental. The proof-like green class `c-restrict` no longer exists, and the legend says the highlights are experimental.

What the UI shows as historical results:
- the preregistered single-coder labels (`gold_label`, `g1_locked`);
- G1 7/10;
- notice-number checks, described as string matches.

## Unchanged

The legacy interpreter (`semantics.py`, `claims.py`, `citations.py`, `engine.py`), the collector, the HMAC sealing, the corpus and the registry are all unchanged.

Legacy tests keep their assertion values. Five HTTP-level tests read the response through `public.legacy_view()`, which puts the experimental fields back in place. Two executed-JS tests changed their expectation from `c-restrict` to `c-qualified` because that class was removed. Both changes are marked `CONTRACT CHANGE` in the test source.

## Tests

`tests/test_public_contract.py` runs these surfaces against Codex's RC-3 counterexamples:
- the Python adapter;
- the real HTTP routes;
- `claimClass` executed in Node;
- a dummy-key-sealed run;
- a keyless replay;
- the genuine Q02 run.

The counterexamples are parenthetical denial, parenthetical extra active, a status question naming a fourth drug, missing or unrelated questions, malformed indexes, and truncated references.

These tests check that nothing unsafe appears outside `experimental`, and that the real data is still shown. A detector test makes sure the leak check is not vacuous.
