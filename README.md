# BANLAG — One Missing Fact (rights-conscious public release)

A local, offline demonstration combining BANLAG's Gazette-based factual registry and fail-closed evidence-audit interface with the One Missing Fact (OMF) deterministic finite-model solver and independent witness verifier.

> **Hackathon demonstration and public-release limitation**
>
> The hackathon demonstration video includes archived Google/SerpApi evidence that is not distributed in this public source release. This release preserves the BANLAG investigation interface and One Missing Fact solver using clearly labelled hypothetical facts. Historical search observations and citation comparisons shown in the demonstration cannot be independently reproduced from this reduced package. G5 and G6 remain incomplete and have not passed.

> **Evidence disclosure:** this public release omits the historical Google screenshots, the G1 search corpus and its manifest, detached evidence pins, and the captured F08 Google AI Overview derivative. The BANLAG historical G1 results and the OMF captured-search comparison are therefore **unavailable**. The package does not claim that omitted evidence was verified. BANLAG fails closed, suppressing historical labels/findings and setting publication gates to WITHHOLD. OMF reports an evidence mismatch/unavailable state and shows no captured answer text or citations.

## Official-source attribution

The included factual notice/ingredient registries reproduce factual material published in Government of India Official Gazette notifications and identify the relevant notification. Source: [Official Gazette, notifications S.O. 3068(E)–3083(E), dated 11 June 2026; the Gazette masthead is dated 15 June 2026 and the e-publication record is 19 June 2026](https://egazette.gov.in/WriteReadData/2026/273649.pdf). The included explanatory government-basis text is attributed to the Department of Health and Family Welfare / PIB source record: [PIB press release](https://www.pib.gov.in/PressReleasePage.aspx?PRID=2275595). Verify current legal status against official sources before relying on it; this demonstration is not legal or medical advice. The registry includes source references in each case.

## Requirements and run

- Python 3.14.x (tested with Python 3.14.6).
- Python standard library only; no package installation, API key, browser extension, or external asset download is required.

On Windows, double-click `RUN_INTEGRATED_WINDOWS.bat`, or run from this folder:

```powershell
python -I -B run_integrated.py
```

The launcher binds to `127.0.0.1` and prints a local URL. BANLAG opens at `/`; OMF opens at `/omf/`. Keep the terminal open and press `Ctrl+C` to stop it. The application does not make outbound requests or load remote assets. Clicking the official-source links in BANLAG opens those government sites in the user's browser.

## OMF demonstration and evidence limits

OMF models 10 of 16 June-2026 notified fixed-dose combinations. Its F08 starter facts are clearly labelled **hypothetical** and taken from the included factual register solely to seed the exercise. They are not presented as a product label or as facts observed in a Google/SerpApi answer. YES and NO add hypothetical assertions; UNKNOWN leaves the state open. The minimax solver, independent subprocess witness verifier, and tamper rejection remain active.

The public release contains no historical F08 capture, search blocks, citation links, or evidence pins. Accordingly, SerpApi integration is described as the method used by the separate approval-gated BANLAG collector: it can request Google search/AI Overview structured output and reference indexes when explicitly invoked with a SerpApi key and approval. This release's integrated launcher never invokes that collector, makes no SerpApi request, and includes no historical captured output. It cannot reproduce or authenticate the archived search comparison from this package.

## BANLAG evidence limits

BANLAG retains its original routes, UI, rules, factual registry, and plan examples. Its historical G1 corpus and screenshots are excluded. On startup the integrity checks fail closed: there are no historical G1 labels/results, no screenshot links, and all publication gates are WITHHOLD. The G1 and integrity views remain available to explain this state; they are not a report of the historical experiment.

## Scope and limitations

The registry models a subset of notices and is a research demonstration, not product identification, medical advice, legal advice, or clearance of combinations outside its finite register. Gazette-derived facts do not replace checking the official notice and its current status. OMF's sample facts are hypothetical. Historical BANLAG benchmark and search-capture claims are unavailable in this release.

No new license grant is made by this package. The project owner may choose licensing terms for project-authored code; attribution alone does not grant redistribution rights to third-party material.

## Offline smoke test

With Python 3.14.x installed, run:

```powershell
python -I -B smoke_test.py
python -I -B f08_preset_regression_test.py
```

The smoke test launches this exact folder, calls only loopback endpoints, requires historical evidence to be unavailable/fail-closed, exercises BANLAG routes and OMF navigation, tests deterministic solving and YES/NO/UNKNOWN semantics, independently verifies a witness, rejects a tampered witness, rejects malformed input, and scans package contents for excluded artifacts and local paths. It makes no external network requests.

## Layout

- `original/banlag/`, `original/web/`: BANLAG application, factual registry, and interface.
- `original/plans/`: example query plans.
- `original/evidence/`: empty of excluded historical search artifacts in this release.
- `omf/`: OMF server, deterministic minimax model, factual register, interface, and independent verifier.
- `run_integrated.py`, `RUN_INTEGRATED_WINDOWS.bat`: single-origin loopback launcher.
- `smoke_test.py`: offline release smoke test.
- `f08_preset_regression_test.py`: regression for the fail-closed empty-array F08 fallback.
- `PACKAGE_SHA256_MANIFEST.json`: SHA-256 inventory of all release payload files except the manifest itself.

This public release preserves existing Git history. Excluded historical captures and audit materials may remain reachable in earlier commits; this release does not sanitize repository history.
