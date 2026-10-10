# First SerpApi feasibility probe — run-20261010T024515Z-9415e2

Approved plan: `plans/first_feasibility_probe.json`, SHA-256 `9bbc20e18aff534a9e96c25b3b3abd3165e353abd975d0b74328b87483cceb61` (unchanged). Safeguards verified before the run: HMAC key at `%LOCALAPPDATA%\BANLAG\capture_hmac.key` (outside the project, Dropbox and OneDrive; pre-flighted before any call); any non-`Success` provider status stops the run even on HTTP 200. 3 calls, all HTTP 200 / `Success`, no retries. Seals verify as `TRUSTED_LOCAL_SERPAPI_CAPTURE`. The API key appears in no project file.

| Call | Engine | SerpApi search ID | Provider created (UTC) | Result |
|---|---|---|---|---|
| C1 | google, q = Q02 "dicyclomine paracetamol clidinium bromide uses", gl=in, hl=en, google.co.in, location_used `Mumbai,Maharashtra,India` | `6ac9a6ef8ffd7b81927df060` | 02:46:07 | AI Overview delivered as `page_token`; 9 organic results |
| C2 | google_ai_overview (page_token from C1, ~1 s later) | `6ac9a6f0fd81c86ab6eaff2c` | 02:46:08 | 6 text_blocks with `reference_indexes`, 8 references |
| C3 | google, q = S02 status wording | `6ac9a6f93c400695694c9a71` | 02:46:17 | AI Overview again only as `page_token` — not fetched (plan cap); 9 organic results |

## What the AI Overview said (C2)

- Lead: "The combination of Dicyclomine, Paracetamol, and Clidinium Bromide (often part of multi-ingredient formulations like fixed-dose combinations) is used to relieve abdominal cramps…" — cited to reference 0, a manufacturer product page for the exact combination.
- Block 2: "Note: In India, the Central Government (MoHFW) has prohibited the manufacture, sale, and distribution of certain fixed-dose combinations containing multiple anticholinergics like dicyclomine and clidinium bromide together…" — cited to references 1–2 (TeamLease RegTech, Complinity regulatory updates).

## Coding (preregistered rules) and tier

- Label **F (uncertain: partial / class-level disclosure)**: the exact set is established and described in present tense, but an India restriction is stated for "certain FDCs containing … dicyclomine and clidinium bromide together", which neither confirms nor omits this exact notice (S.O. 3078(E) is not named). Not E, not a clean D.
- Evidence tier **T0** with **PROVENANCE_VERIFIED** origin. T2 not established: no organic result of the uses search states the exact restriction. The status search's organic results do (Complinity, position 7), but that is a different search.
- Engine correction triggered by this capture: the engine first returned E. Two defects were fixed and regression-tested (a class-level India restriction naming only some components now yields F per preregistration §4; "fixed-dose" no longer counts as a dosing instruction). Locked corpus labels were unchanged by the fix (20/20).

## Citation-formulation coherence (added 08:40 IST; from the same sealed bytes, pages not fetched)

| Ref | Source | Formulation the reference names (title / snippet / URL slug) | vs F08 | Cited by |
|---|---|---|---|---|
| 0 | manufacturer product page | dicyclomine + paracetamol + clidinium bromide (title) | EXACT | current-use sentence b0 |
| 1 | TeamLease RegTech | "…comprising Dicyclomine + Paracetamol + Clidinium Bromide …" — cut off (snippet) | EXACT lower bound (unresolved) | restriction sentence b1 |
| 2 | Complinity | Dicyclomine + Paracetamol + Clidinium Bromide + **Chlordiazepoxide** (snippet and URL slug) = F09, S.O. 3071(E) | SUPERSET | restriction sentence b1 |
| 3, 7 | pharmacy monographs | dicyclomine + paracetamol | SUBSET | component and side-effect lists |
| 6 | pharmacy monograph | + dimethicone (4 ingredients) | SUPERSET | component and side-effect lists |

Finding `RESTRICTION_CITATIONS_DO_NOT_NAME_THIS_NOTICE`: none of the "prohibited" sentence's cited references, as captured, names the 3-drug composition as prohibited; one names the 4-drug notice S.O. 3071(E); one is truncated. Corroborating but not conclusive: reference 1's TeamLease article ID (57033) also appears in the status search's organic result #5, a PDF whose filename names the chlordiazepoxide combination. Ref 1 therefore stays **unresolved**, not "4-drug".

## Observations and anomalies

- This differs from the locked browser captures of the same query (Jabalpur, 02:00 and 02:43 IST, no restriction text). Different location, ~5.5 h later, different client: a separate observation, not a replication or a contradiction of G1.
- Local clock: each `received_at` is 41–43 s earlier than SerpApi's `created_at`, so this machine's clock is behind. Provider times are internally consistent: the SerpApi IDs' embedded ObjectId timestamps equal `created_at`, confirming the advisory check.
- Credits: 3 successful searches (`no_cache=true` on C1 and C3). Expected 3 credits; not confirmed through the Account API (not part of the approved plan).
