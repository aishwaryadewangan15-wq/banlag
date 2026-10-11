# BANLAG — Auditing AI Search Against India's Drug Regulations

[![CI](https://github.com/aishwaryadewangan15-wq/banlag/actions/workflows/ci.yml/badge.svg)](https://github.com/aishwaryadewangan15-wq/banlag/actions/workflows/ci.yml) ![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue) ![Dependencies: none](https://img.shields.io/badge/runtime%20dependencies-none-brightgreen) [![License: MIT](https://img.shields.io/badge/code-MIT-yellow)](LICENSE)

**When AI cites a regulation, does the evidence actually match the drug formulation?**

*SerpApi India Hackathon 2026 | Local research workbench | Reproducible evidence exploration*

## The problem

A single additional ingredient can change which drug regulation applies.

In June 2026, India published sixteen notifications prohibiting the manufacture, sale or distribution of specific fixed-dose drug combinations for human use under Section 26A of the Drugs and Cosmetics Act. Each notification identifies a particular formulation.

For example:

* **F08 — S.O. 3078(E):** Dicyclomine + Paracetamol + Clidinium Bromide.
* **F09 — S.O. 3071(E):** Dicyclomine + Paracetamol + Clidinium Bromide + Chlordiazepoxide.

These are different combinations covered by different notifications.

When Google's AI Overview describes a formulation and cites supporting sources, a researcher needs to know whether the captured citation metadata actually names the same combination.

That is the problem BANLAG investigates.

## What BANLAG does

BANLAG is a local-first research workbench that connects captured Google AI answers to their citation metadata and India's exact Gazette formulations.

It provides:

1. **Structured SerpApi evidence:** Google AI Overview text blocks, `reference_indexes`, references, organic results, search identifiers and provider timestamps.
2. **Statement-to-citation tracing:** Each captured AI answer block can be inspected alongside the references indexed by that block.
3. **Exact Gazette comparisons:** Registered ingredient sets can be compared to expose additions, removals and formulation differences.
4. **Evidence provenance:** Genuine collector captures use locally sealed records; published keyless archives are clearly distinguished from authenticated local captures.
5. **Experimental interpretation boundaries:** Language-parser readings are separated from direct observations and are not presented as verified regulatory decisions.
6. **Adversarial import checks:** User-supplied evidence is never promoted to authenticated SerpApi evidence merely because its metadata looks convincing.

BANLAG does not determine why an AI model produced an answer, and it does not automatically decide whether a regulation has been violated.

## The real SerpApi finding: one ingredient changes the citation context

### Case F08 — Dicyclomine + Paracetamol + Clidinium Bromide

Gazette notification: **S.O. 3078(E)**.

BANLAG includes an actual SerpApi capture run from 10 October 2026. The approved run made three successful SerpApi calls: a Google Search request for the formulation's uses, its Google AI Overview `page_token` follow-up, and a separate Google Search request asking about the formulation's status.

The captured AI Overview included a statement noting that India had prohibited certain fixed-dose combinations involving anticholinergic ingredients. This was a partial, class-level disclosure, not a demonstrated complete omission of the restriction.

The key observation is in the **MECHANICAL OBSERVATIONS** table:

* The captured prohibition-related block cites references **[1]** and **[2]** through SerpApi's `reference_indexes`.
* Reference **[2]** contains the names of four ingredients, including Chlordiazepoxide.
* Those names produce a **candidate** match to **F09**, whose Gazette notice is **S.O. 3071(E)**.
* Compared with the target F08 formulation, the typed ingredient-set difference is **+chlordiazepoxide**.
* Reference **[1]** is truncated. BANLAG therefore leaves its formulation interpretation **unresolved**.

This is a difference in the captured citation metadata, not proof that the underlying webpage is incorrect. The cited webpages were not independently fetched. An ingredient-name match is also not proof that a snippet contains an exhaustive ingredient list.

**What the evidence establishes:** BANLAG can make a meaningful formulation difference visible at the level of a specific AI statement and its captured citations.

**What it does not establish:** That Google concealed a restriction, that both references are wrong, that the source webpages contain false information, or that a verified live omission was observed.

## Earlier preregistered browser research

Before the SerpApi capture, a separate browser-based investigation examined ten exact formulations using signed-out Google India. Its query design and coding rules were locked before the first query, and the archive was retained for review.

In 7 of 10 investigated compositions, the preregistered single-coder labels recorded present-use descriptions without India-specific regulatory context in both passes. When separately asked about status, the same search surface described those restrictions.

This is a single-coder historical browser observation. It is not a representative estimate of Google's overall accuracy, not independently recoded, and not a replication of the SerpApi capture.

BANLAG also preserves a literal notice-number discrepancy from that browser archive:

* AI-cited notice: **S.O. 3080(E)**.
* Gazette notice for Paracetamol + Lignocaine: **S.O. 3079(E)**.

This is a notice-number string comparison, not a claim about the AI's intentions.

The investigated registry contains ten case formulations from the broader set of sixteen notifications. BANLAG does not claim to have investigated all sixteen.

## Why SerpApi is essential

SerpApi provides a structured interface to the captured Google results rather than requiring BANLAG to infer citation relationships from visual source chips.

In particular, the AI Overview response includes `text_blocks` and `reference_indexes` linked to the response's `references`. This lets a researcher inspect which captured reference metadata belongs to which AI statement.

The project uses:

* `google` with `gl=in` for India-targeted search results.
* `google_ai_overview` for the AI Overview `page_token` follow-up.

The genuine capture run is preserved at [`evidence/serpapi/run-20261010T024515Z-9415e2/`](evidence/serpapi/run-20261010T024515Z-9415e2/). Its exported archive contains three collector records, their raw provider responses and a SHA-256 manifest.

BANLAG is not the first tool to connect AI claims to citations. Prior work such as GRAP Audit also investigates citation relationships. BANLAG's specific research focus is the exact ingredient-level distinction between Indian Gazette notifications.

## Evidence integrity and engineering

The project's security and evidence-handling mechanisms include:

* A locally stored HMAC sealing key, excluded from the public repository.
* SHA-256 binding of recorded capture bytes and research artifacts.
* Clear differentiation between authenticated local captures, hash-consistent archives, user-supplied imports and synthetic test fixtures.
* A local HTTP application bound to `127.0.0.1`.
* Restrictions on cross-origin requests, unsupported methods and oversized input bodies.
* Explicit separation of mechanical citation observations from experimental language-parser interpretations.

The final release underwent extensive regression and adversarial testing. A fresh-clone, keyless verification of the submitted commit ran 225 tests: 220 passed and five key-dependent tests were skipped. These are engineering verification results, not a measured general-language classification accuracy rate.

The output contract is described in [docs/PUBLIC_CONTRACT.md](docs/PUBLIC_CONTRACT.md). Historical engineering decisions, audit rounds and before/after proofs are summarised in [docs/ENGINEERING_HISTORY.md](docs/ENGINEERING_HISTORY.md).

## Run BANLAG locally

Requirements: Python 3.10 or newer. The application uses the Python standard library and requires no API key for offline exploration.

From the repository root, run the tests:

```bash
python -m unittest discover -s tests
```

Start the application:

```bash
python -m banlag
```

Or install it as a command (editable install, so the bundled web UI and evidence stay in place):

```bash
pip install -e .
banlag
```

Then open `http://127.0.0.1:8765`. On Windows, you can also run `RUN_WINDOWS.bat`.

The local web server makes no outbound requests. New SerpApi captures are performed only through the separate, explicitly approved collector CLI; ordinary use of the local application does not trigger SerpApi calls.

A public fresh clone replays the exported SerpApi data as `ARCHIVED_SERPAPI_CAPTURE`, because the private sealing key is deliberately not published. The source machine can authenticate its original local seal. The public archive's hashes support integrity checks but do not independently authenticate its origin on another machine.

## Suggested demonstration

1. Open case F08 and inspect Gazette notice S.O. 3078(E).
2. Find the archived SerpApi AI Overview in the case file.
3. Inspect the prohibition-related block and references [1] and [2] in **MECHANICAL OBSERVATIONS**.
4. Compare the F09 candidate and its additional chlordiazepoxide ingredient.
5. Inspect the G1 browser experiment and its single-coder limitations.
6. Open **Integrity** to inspect the S.O. 3080(E) versus S.O. 3079(E) string discrepancy.
7. Open **Verify an import** to see how unverified and synthetic inputs are handled.

## Interpretation boundaries and limitations

BANLAG is an evidence exploration instrument, not an automated legal or medical decision-maker.

The English language parser uses bounded rules and retains known failure modes. It has no independently established general accuracy score for the submitted release. Its interpretations, labels, evidence tiers and publication-related readings are clearly marked experimental for human review.

The public response contract recursively filters assessment and evidence outputs, retaining allowlisted observations and separating unverified parser conclusions under `experimental`. Typed registry, exact-list matching and server-status endpoints have separately defined handling; they are not all subjected to identical recursive filtering.

The genuine SerpApi investigation consists of one capture run at one time and location. No verified live omission or live Tier 2/3 finding was established. AI Mode was not captured, and the separately asked status search's AI Overview was not fetched.

Legal checks found no amendment or stay as of 10 October 2026, but those searches were not exhaustive. Legal status should be rechecked before subsequent regulatory use.

BANLAG does not make accusations about Google, source publishers, pharmacies, manufacturers or individual products.

**Medical safety:** Do not start, stop or change medication based on BANLAG. A Gazette restriction on manufacture, sale or distribution does not by itself establish an offence involving a patient's possession or use. Consult an appropriate medical professional for personal health decisions.

## Reproducibility and release identity

The commit submitted to the SerpApi India Hackathon 2026 is `063a0d1c93ff24e973b4dbacab3d6f439542a653`. It stays permanently reachable, together with its source fingerprint (`c635055d573cea07146c68b9a9fb89ddd06bdf1a698ca242b63bf02d7d048f73`) and the method behind it, on the [`engineering-history`](https://github.com/aishwaryadewangan15-wq/banlag/tree/engineering-history) branch.

Every change since is tested in CI on Python 3.10–3.13 across Linux, Windows and macOS. See [CHANGELOG.md](CHANGELOG.md).

Earlier benchmark results and failed acceptance tests remain in the engineering history. They should not be read as accuracy measurements of any release.

## Development and prior art

BANLAG was developed with AI assistance, including Claude Code for implementation, ChatGPT for planning and review, and OpenAI Codex for adversarial engineering audits.

Prior art includes GRAP Audit, which also examines citation relationships. BANLAG's research emphasis is exact ingredient-level comparison against Indian Gazette notifications.

The source archive, tests, engineering reports and documented limitations are provided so the work can be examined critically.

## Official sources

* [Indian Gazette — S.O. 3068(E)–3083(E)](https://egazette.gov.in/WriteReadData/2026/273649.pdf)
* [Press Information Bureau release](https://www.pib.gov.in/PressReleasePage.aspx?PRID=2275595)
* [Central Drugs Standard Control Organisation](https://cdsco.gov.in/opencms/opencms/en/Drugs/FDC/)
* [SerpApi Google AI Overview API](https://serpapi.com/google-ai-overview-api)

## License

Code is released under the [MIT License](LICENSE). BANLAG's own annotations, registry and corpus coding are released under [CC BY 4.0](LICENSE-DATA.md). Third-party material in `evidence/` (captured search results, screenshots and quoted source text) remains the property of its respective owners and is included for research and verification only.

## Citing BANLAG

See [CITATION.cff](CITATION.cff), or use GitHub's "Cite this repository" button.
