import sys, json; sys.stdout.reconfigure(encoding='utf-8'); sys.path.insert(0, '.')
from banlag import corpus
r = corpus.build_cases()
print(sorted(r.keys()), file=sys.stderr)
keep = {k: r[k] for k in r if k not in ('cases', 'corpus', 'g1')}
print(json.dumps(keep, ensure_ascii=False, indent=1, sort_keys=True, default=str))
