# BANLAG — what does Google's AI answer say about India's exact banned drug combinations?

**SerpApi India Hackathon 2026 entry. A local evidence workbench. It does not make regulatory verdicts.**

On 11 June 2026 India prohibited the manufacture, sale and distribution of specific fixed-dose drug combinations (Gazette S.O. 3068(E)–3083(E), Section 26A, Drugs and Cosmetics Act). Each notice covers **one exact composition**. For example, Dicyclomine + Paracetamol + Clidinium Bromide is **S.O. 3078(E)**, while the same three plus Chlordiazepoxide is a *different* notice, **S.O. 3071(E)**.

BANLAG takes captured Google AI answers, either from SerpApi or from a locked browser archive. For each answer it shows:
- what the answer said;
- which references each claim cited, through SerpApi's `reference_indexes`;
- what that citation metadata actually contains;
- which exact Gazette ingredient sets those mentions point to, labelled **as candidates**.

Anything the software would have to *interpret* is labelled experimental, and a human makes the call.

## Run it (Python 3.10+, standard library only, no API key)

```bash
python -m unittest discover -s tests
```

```bash
python -m banlag
```

Open http://127.0.0.1:8765. The server binds to 127.0.0.1 and makes **no outbound requests**. On Windows you can also run `RUN_WINDOWS.bat`.

A fresh clone includes the genuine SerpApi capture, exported to `evidence/serpapi/run-20261010T024515Z-9415e2/` as 3 calls, their raw provider responses and a hash manifest. Without the capture machine's private key it replays as **ARCHIVED SerpApi capture — origin NOT authenticated here**. On the capture machine the HMAC seal verifies. The key is never published.

## The genuine finding (one live capture: 3 SerpApi calls, 10 Oct 2026 08:16 IST)

The query was the preregistered one for Dicyclomine + Paracetamol + Clidinium Bromide (S.O. 3078(E)). In the case file for F08, open the **MECHANICAL OBSERVATIONS** table:

- The AI Overview's "…has prohibited … **certain** fixed-dose combinations…" block cites references **[1, 2]**, exactly as SerpApi captured them.
- **Reference [2]**: its captured title and snippet mention all four ingredients of **F09 (S.O. 3071(E))**. The typed Gazette difference from the target F08 is **+chlordiazepoxide**. This is a **candidate** mapping from name mentions; a mention list is not an exhaustive ingredient list.
- **Reference [1]**: its captured text is cut off, so it stays **unresolved**.
- The cited webpages were **not fetched**. Nothing here says a webpage is wrong, that Google concealed anything, or that the answer was a complete omission. The historical reading of this answer is **F/T0, a partial class-level disclosure**, and it is shown as experimental.

## Earlier preregistered browser study (archive, single coder)

This study was locked before the first query (SHA-256 `C4A8EF16…AFC12E`). It covered 10 exact compositions on signed-out Google India, in two passes.

- In **7 of 10** compositions, the locked single-coder label was "current use, no India status" in both passes (G1_PASS, 4 positives outside the serratiopeptidase family). Asked separately, the same surface said "prohibited".
- One AI status answer cited **S.O. 3080(E)** for Paracetamol + Lignocaine. Its notice is **S.O. 3079(E)**; this is a literal string check.

This is one coder's locked labels. It is not independent or general accuracy, and it is not a SerpApi replication.

## Public-output contract (allowlist)

Every API response passes `banlag/public.py` (see [docs/PUBLIC_CONTRACT.md](docs/PUBLIC_CONTRACT.md)). **Only allowlisted fields are public.** These are:
- **observed** capture data: text, IDs, timestamps, references and organic results;
- **registered** Gazette facts;
- **mechanical** observations: valid index → captured reference, literal ingredient-name and notice-number strings, and typed set differences.

Every other field, including everything the English parser concludes, fails closed into `experimental`. That covers exactness, labels, tiers, citation coherence, status contrast and publication gates. Publication is never decided by software.

## Honest limits

- The English parser is a bounded rule grammar and is **experimental**. Independent audits repeatedly found wordings it misreads; one example is the parenthetical "(it does not contain paracetamol)". An independent 60-case holdout scored an earlier build **39/60**. Its readings are hypotheses, not facts.
- The SerpApi evidence is one live capture, at one time and place. No live omission and no live Tier 2/3 has been observed. AI Mode and the status search's AI Overview were not captured.
- Legal status: no amendment and no stay were found as of 10 Oct 2026, from non-exhaustive searches.

## Why SerpApi

The browser shows source *names* only. SerpApi returns the India AI Overview as structured `text_blocks` with `reference_indexes` into its `references`, plus the same search's organic results, provider IDs and timestamps. That is what lets each claim be bound to its cited metadata.

Engines used: `google` with `gl=in`, and `google_ai_overview` for the `page_token` follow-up. Calls run only through `python -m banlag.collector <plan> --approve <sha256>`. The collector stops on any error and makes no retries. Responses are HMAC-sealed on receipt. Mapping `reference_indexes` to sources is not unique to BANLAG; GRAP Audit does it too. BANLAG's focus is exact Gazette formulations.

## Safety

This is a research tool, **not** a patient medication checker. A notice prohibits the manufacture, sale or distribution of one exact combination. It does not make possession or use by a patient an offence. Never stop or change a medicine because of this tool; speak to a doctor or pharmacist.

## Release identity

The release fingerprint is a SHA-256 over the source files' `SHA256  relpath` lines, **sorted by ordinal (byte) order of the forward-slash relative path**. This order does not depend on the system locale. The value is in [docs/proof/RELEASE_IDENTITY.md](docs/proof/RELEASE_IDENTITY.md), which also explains the earlier `36131892…` / `09b90f4b…` discrepancy: the same bytes gave two hashes because two files sorted differently.

## Disclosures

AI assistance: built with Claude Code (Anthropic), with independent audits by OpenAI Codex. Prior art includes GRAP Audit. Project origin and further details: {{to be confirmed by the author}}. Engineering history: [docs/HARDENING_REPORT.md](docs/HARDENING_REPORT.md), [docs/GATE_STATUS.md](docs/GATE_STATUS.md).

## Official sources

[Gazette S.O. 3068(E)–3083(E)](https://egazette.gov.in/WriteReadData/2026/273649.pdf) · [PIB release, 20 Jun 2026](https://www.pib.gov.in/PressReleasePage.aspx?PRID=2275595) · [CDSCO](https://cdsco.gov.in/opencms/opencms/en/Drugs/FDC/) · [SerpApi AI Overview API](https://serpapi.com/google-ai-overview-api)
