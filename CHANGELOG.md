# Changelog

All notable changes to BANLAG are recorded here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- MIT `LICENSE` for code and `LICENSE-DATA.md` (CC BY 4.0 for BANLAG's own data, with third-party material excluded).
- `pyproject.toml`: the `banlag` and `banlag-collector` console scripts. Runtime dependencies stay at none.
- GitHub Actions CI: tests on Python 3.10–3.13 across Ubuntu, Windows and macOS, plus ruff, a coverage report and a packaging check.
- `CONTRIBUTING.md`, `SECURITY.md`, `CITATION.cff`, issue and pull-request templates.
- `docs/ENGINEERING_HISTORY.md`: a summary of the audit rounds, linking to the preserved history.

### Changed
- Internal audit artifacts (`docs/proof/`, `HARDENING_REPORT.md`, `GATE_STATUS.md`, `FREEZE_AND_GATES.md`) moved to the `engineering-history` branch.
- README: badges, install instructions, license and citation sections, and a simpler release-identity section.

### Removed
- The stale root `BUILD_SHA256_MANIFEST.json` (status `v0.2_local_build_not_published`). It remains on the `engineering-history` branch.

## [0.2.0] — 2026-10-10

Submitted to the SerpApi India Hackathon 2026 as commit `063a0d1c93ff24e973b4dbacab3d6f439542a653`.

- Approval-gated SerpApi collector with HMAC-sealed local capture store, plus one archived 3-call capture run (case F08).
- Exact-set Gazette matcher for ten Section 26A notifications.
- Claim-level parser with an experimental, allowlisted public output contract.
- Hardened local web workbench: 225 tests (220 passed, 5 key-dependent skipped).
