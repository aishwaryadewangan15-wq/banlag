# Contributing to BANLAG

Thanks for helping. BANLAG is a research instrument, so correctness and honest limits matter more than features.

## Ground rules

1. **No runtime dependencies.** BANLAG runs on the Python standard library. Dev tools go under `[project.optional-dependencies].dev`.
2. **Never weaken provenance.** Imported data must never be promoted to a trusted origin, and archived captures must never be shown as authenticated.
3. **Observations and interpretations stay separate.** Parser readings belong under `experimental` in the public contract.
4. **No live SerpApi calls in tests or the web server.** Captures happen only through the approval-gated `banlag.collector`.
5. **Medical and legal language stays careful.** Don't word anything as advice, an accusation, or a regulatory decision.

## Development setup

```bash
git clone https://github.com/aishwaryadewangan15-wq/banlag.git
cd banlag
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
python -m unittest discover -s tests
ruff check .
mypy
coverage run -m unittest discover -s tests && coverage report   # fails below the floor
```

Where things live: the claim reader is `banlag/claims/` (regex vocabulary in `patterns.py`), and the shared composition and restriction-event core is `banlag/semantics/`. `tests/README.md` maps each behaviour to its tests.

## Pull requests

- Keep each PR to one topic, and use conventional commit messages (`feat:`, `fix:`, `test:`, `docs:`, `refactor:`, `chore:`).
- Add or update tests for any behaviour change. A parser fix needs a positive control, so it can't pass by refusing everything.
- Update `CHANGELOG.md` under **Unreleased**.
- CI must pass on every OS and Python version in the matrix.

## Reporting parser mistakes

Open a **Parser misreading** issue with the exact sentence, the formulation, what BANLAG said, and what it should have said. These become regression tests.
