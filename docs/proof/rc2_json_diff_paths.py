"""List every value path that differs between two JSON dumps, ignoring only keys ADDED by a repair. Usage: a b added1,added2"""
import json
import sys

added = set(sys.argv[3].split(',')) if len(sys.argv) > 3 else set()


def walk(a, b, path, out):
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k in added and k not in a:
                continue
            if k not in a or k not in b:
                out.append((path + '.' + k, 'missing in ' + ('before' if k not in a else 'after')))
            else:
                walk(a[k], b[k], path + '.' + k, out)
    elif isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        for i, (x, y) in enumerate(zip(a, b)):
            walk(x, y, f'{path}[{i}]', out)
    elif a != b:
        out.append((path, f'{json.dumps(a)[:80]} -> {json.dumps(b)[:80]}'))


A = json.load(open(sys.argv[1], encoding='utf-8'))
B = json.load(open(sys.argv[2], encoding='utf-8'))
diffs = []
walk(A, B, '$', diffs)
print(f'{len(diffs)} differing paths (ignoring added keys {sorted(added)})')
for p, d in diffs[:40]:
    print(' ', p, '|', d)
