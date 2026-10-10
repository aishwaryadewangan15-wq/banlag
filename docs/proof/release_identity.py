"""Locale-independent release fingerprint: SHA-256 over LF-joined 'SHA256(upper)  relpath' lines for banlag/, web/, tests/
(*.py *.js *.html *.css *.json, excluding __pycache__), relpath with forward slashes, sorted by ordinal (byte) order."""
import hashlib, sys
from pathlib import Path
app = Path(sys.argv[1])
fs = [p for d in ('banlag', 'web', 'tests') for p in (app / d).rglob('*') if p.is_file() and p.suffix in ('.py', '.js', '.html', '.css', '.json') and '__pycache__' not in p.parts]
rows = sorted((p.relative_to(app).as_posix(), hashlib.sha256(p.read_bytes()).hexdigest().upper()) for p in fs)
lines = [h + '  ' + r for r, h in rows]
print(len(lines), hashlib.sha256('\n'.join(lines).encode('utf-8')).hexdigest())
if len(sys.argv) > 2: Path(sys.argv[2]).write_text('\n'.join(lines) + '\n', encoding='utf-8')
