# Release identity

**Release fingerprint:** `c635055d573cea07146c68b9a9fb89ddd06bdf1a698ca242b63bf02d7d048f73`

It covers 39 source files and was computed at 22:56 IST on 10 Oct 2026 with `python docs/proof/release_identity.py .`. The method:
1. Take the files under `banlag/`, `web/` and `tests/` with the extensions `*.py *.js *.html *.css *.json`, excluding `__pycache__`.
2. For each file, write a line: the file's SHA-256 in uppercase, two spaces, then its relative path with forward slashes.
3. Sort the lines by **ordinal (byte) order** of the path. This order does not depend on the system locale.
4. Join the lines with LF and take the SHA-256 of their UTF-8 bytes, in lowercase hex.

## Hash history (why there were two numbers for the same bytes)

| Fingerprint | Method | Content |
|---|---|---|
| `98cf3380…5cb2` | PowerShell `Sort-Object FullName` (culture-aware), `docs/proof/rc3_final_verify.ps1` | RC-3 |
| `36131892…488a` | Python, ordinal sort on lowercased Windows paths (a different helper) | provisional workbench, 21:53 IST |
| `09b90f4b…d81b` | PowerShell `Sort-Object FullName` | **the same bytes** as `36131892…`. Codex verified it independently. |
| `c635055d…8f73` | this ordinal, forward-slash method | release (allowlist schema, archived Q02 replay, corrected tests) |

`36131892…` and `09b90f4b…` came from identical file contents. A culture-aware sort puts `_` before `.`, so `tests/test_http_hardening.py` and `tests/test_http.py` swapped places; an ordinal sort orders them the other way. `docs/proof/wb_after.txt` records `36131892…` and wrongly says the method was the same as RC-3's. It is kept unchanged as a historical record and is corrected here.
