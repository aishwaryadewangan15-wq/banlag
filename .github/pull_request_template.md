## What and why

<!-- One topic per PR. Link the issue if there is one. -->

## Checklist

- [ ] Tests added or updated (parser changes include a positive control)
- [ ] `python -m unittest discover -s tests` passes locally
- [ ] `ruff check .` passes
- [ ] `CHANGELOG.md` updated under **Unreleased**
- [ ] No new runtime dependencies
- [ ] Provenance is not weakened, and parser readings stay under `experimental`
