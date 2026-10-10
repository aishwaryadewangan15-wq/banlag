"""Read-only: recompute every SHA-256 in EVIDENCE_MANIFEST.txt. Usage: check_evidence.py <evidence_dir>"""
import hashlib, re, sys, pathlib
root = pathlib.Path(sys.argv[1])
ok = bad = sizes_bad = 0; unresolved = []
for ln in (root / 'EVIDENCE_MANIFEST.txt').read_text(encoding='utf-8', errors='replace').splitlines():
    m = re.match(r'^([0-9A-Fa-f]{64})\s+(\d+)\s+(.+?)\s*$', ln)
    if not m:
        continue
    p = root.joinpath(*re.split(r'[\/]', m.group(3)))
    if not p.is_file():
        unresolved.append(m.group(3)); continue
    b = p.read_bytes()
    if hashlib.sha256(b).hexdigest().lower() == m.group(1).lower():
        ok += 1
    else:
        bad += 1; print('MISMATCH', p)
    sizes_bad += len(b) != int(m.group(2))
files = sum(1 for q in root.rglob('*') if q.is_file())
print(f'EVIDENCE_MANIFEST: match={ok} mismatch={bad} size_mismatch={sizes_bad} unresolved={unresolved} files_on_disk={files} (manifest itself not self-listed)')
