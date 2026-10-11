# Capture formats

## 1. Sealed SerpApi capture (the only trusted live origin)

Created only by `python -m banlag.collector <plan> --approve <plan sha256>` after the user approves that exact plan. Each call writes:

- `captures/store/raw/<sha256>.json` — the response bytes exactly as received (the API key is redacted if it ever appears; the record says so)
- `captures/store/<run>-<call>.json` — `{"record": {...}, "hmac_sha256": "..."}` where `record` binds `request.engine`, `request.params` (no key), `http_status`, `received_at`, `elapsed_ms`, `provider` (`search_metadata.id`, `created_at`, `processed_at`, `status`, `json_endpoint`), `raw_sha256`, `run_id`, `call_id`, `parent_call_id` (page_token follow-up), `plan_sha256`.

`capture_store.verify()` re-hashes the raw bytes, checks the recorded provider metadata against them and checks the seal with the machine-local key (default `%LOCALAPPDATA%\BANLAG\capture_hmac.key`; `BANLAG_KEY_DIR` overrides). The store refuses to create or trust a key inside the project, a Dropbox or OneDrive root, or any folder with a `.dropbox` marker, and the collector checks this before its first call. Without the key a record verifies only as `ARCHIVED_SERPAPI_CAPTURE`.

`captures/` is git-ignored. To publish a run deliberately: `python -m banlag.capture_store export <run_id>` copies its records and raw responses (never the key) to `evidence/serpapi/<run_id>/` with an `EXPORT_MANIFEST.json`; only runs that verify locally can be exported, and exports are immutable. `engine.evaluate_run(run_id)` assembles a run: the `google` response (organic results + `ai_overview` or its `page_token`), the `google_ai_overview` follow-up, and an optional separately worded status search.

Call roles a plan may use: `uses_search`, `uses_ai_overview` (page_token follow-up of the uses search), `uses_ai_mode`, `status_search` and `status_ai_overview` (page_token follow-up of the status search). A status follow-up is merged only when its `page_token` matches the status search's, and that link never upgrades the uses-search binding. `python -m banlag.batch` writes budgeted plans across days and cities. Each plan carries a `schedule` (day, date, location), so no approval hash can be reused for another day.

## 1b. Cited-page snapshots (`evidence/cited_pages/<run>/CITED_PAGES.json`)

`python -m banlag.citefetch <run_id>` fetches each URL the run's AI surfaces cite. It refuses non-public hosts, including on redirects, and caps responses at 5 MB. It records the final URL, HTTP status, content type, byte length, the SHA-256 of the exact bytes, `fetched_at` and `lag_after_capture_hours`, plus text checks: registry names present, notice numbers present, and sentence-level exact-restriction statements per registry entry, quoted at most 300 characters. The bytes and extracted text stay in git-ignored `captures/cited_pages/<run>/`. `--evaluate` passes only snapshots whose local bytes still match the published hash to the engine as `LOCAL_SNAPSHOT_VERIFIED` pages. A snapshot shows what a URL returned at `fetched_at`, not what Google saw.

## 2. Imported capture (always `USER_SUPPLIED_UNVERIFIED`)

```json
{
  "source_kind": "SERPAPI_LIVE_CAPTURE | BROWSER_RESEARCH | SYNTHETIC_TEST",
  "captured_at": "2026-10-10T02:00:00+05:30",
  "query": "dicyclomine paracetamol clidinium bromide uses",
  "ingredients": ["dicyclomine", "paracetamol", "clidinium bromide"],
  "google": {"search_metadata": {}, "search_parameters": {}, "organic_results": [], "ai_overview": {}},
  "ai_overview": {"search_metadata": {}, "search_parameters": {"page_token": "..."}, "ai_overview": {"text_blocks": [], "references": []}},
  "ai_mode": {"search_metadata": {}, "search_parameters": {}, "text_blocks": [], "references": []},
  "cited_page_captures": [{"url": "", "capture_time": "", "capture_method": "", "source_text": ""}],
  "explicit_status_query": {"query": "", "answer_text": ""}
}
```

`source_kind` must be declared but is never trusted. Provider metadata is checked for internal consistency (24-hex ID, `Success`, timestamp formats and order, not in the future, `json_endpoint` bound to the ID, engine and `q` consistent, locale consistent across surfaces) and the result is reported as `CONSISTENT / INCOMPLETE / INCONSISTENT / ABSENT`; even `CONSISTENT` leaves the origin unverified and `verified_evidence_tier` at 0.

- `text_blocks` follow SerpApi: `paragraph`, `heading`, `list` (items with `title`, `snippet`, `reference_indexes`, nested `list`), `table`. Citations bind per block through `reference_indexes` into the same answer's `references`. Missing `reference_indexes` → citation link UNKNOWN (abstain).
- Organic results count toward Tier 2 only if bound to the same search: inline AI Overview in the same `google` response, or a `google_ai_overview` response whose `page_token` equals the parent's, or the same `search_metadata.id`; a different `q` is a mixed-query SERP and never counts.
- `cited_page_captures` are `ASSERTED_UNVERIFIED`: shown, evaluated, never counted for Tier 3.
- Each answer's `analysis.subject` carries `composition_verdict` (`SUPPORTED_EXACT` / `DIFFERENT` / `UNRESOLVED`) and `composition_blockers` (the sentence and construction that changed it). Each restriction claim's `restriction` carries one entry per predicate in `events` (`id`, `kind` RESTRICTION / REVOCATION / SCOPE, `term`, `entity` TARGET / COMPONENT / OTHER / GENERIC / UNBOUND, `binding`, `jurisdiction`, `negated`, `denied`, `reported`, `conditional`, `proposed`, `historical`, `years`, `revoked_by`, `reinstates`, `qualifies`, `why_not`, `clause`), plus the claim-level `active_target_india` that alone drives label D and the UI's green highlight. Non-qualifying organic results are listed in `organic_not_qualifying` and pages in `cited_page_assessment[].why_not`. `analysis.reference_index_problems` and `citation_coherence.index_problems` report duplicate or malformed reference indexes (never resolved to one reference). The publication gate adds `TEXT_COMPOSITION_NOT_SUPPORTED_EXACT` when no AI surface with text has a SUPPORTED_EXACT composition.
- RC-2 fields: each restriction claim carries `formulation_supported` (the answer's formulation is established as exactly the target; required, with `active_target_india`, for label D and the green highlight); each claim's `citations.malformed_indexes` lists claim-side indexes that are not plain non-negative integers (never bound); each reference carries `restriction_support` (QUALIFYING / BOUND / MENTION_ONLY / NONE); status answers report `status_question_validation` and the status capture its `question_validation` and `composition_verdict`; the publication gate adds `COMPOSITION_VALIDATION_MISSING` or `NO_AI_TEXT_COMPOSITION_ESTABLISHED` when the composition input is absent or empty.
- Each cited reference is reported by `citations.reference_formulation` with `views` (title / snippet / url_slug, each with its own `ingredients`, `combinations`, `unrecognised`, `truncated`), a `reconciliation` (`RESOLVED`, `LOWER_BOUND`, `SINGLE_NAME_ONLY`, `NO_FORMULATION_NAMED`, `CONFLICTING_VIEWS`, `MULTIPLE_FORMULATIONS`, `UNRECOGNISED_COMPONENT`), `conflict` (which views disagree), `truncated_views`, `basis` (views supporting the set), `registry_entry` (only when resolved and complete) and `restriction_views` (views stating an unqualified, non-foreign restriction). Only the provider-captured metadata is read; cited pages are never fetched.

## 3. Browser archive record (`evidence/g1_corpus.json`)

Built read-only by `python -m banlag.evidence_ingest --evidence <banlag_v2_audit> --copy-screenshots`. Each record keeps the verbatim AI text, a segmentation into AI-authored blocks (with the source chip Google showed after each block), the trailing source cards (titles only; not AI text), the capture time, the source file's SHA-256 as locked in the archive manifest, and the locked coder label. `evidence/CORPUS_MANIFEST.json` (schema `banlag.corpus_manifest.v1`) binds the corpus SHA-256, record count, preregistration, archive-manifest and lock-record hashes and screenshot hashes; `banlag/corpus.py` additionally pins the corpus SHA-256 (`EXPECTED_CORPUS_SHA256`), so a replaced corpus with a rehashed manifest fails. `--verify` rebuilds the corpus in memory from the locked archive and compares it with the bundled file and the pin, writing nothing. Synthetic samples (`web/samples.js`) use `.invalid` URLs and are never evidence.
