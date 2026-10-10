"""Compare two JSON dumps ignoring keys ADDED by the repair (never ignoring changed or removed values). Usage: a b key1,key2"""
import json
import sys

added = set(sys.argv[3].split(','))


def strip(x):
    if isinstance(x, dict):
        return {k: strip(v) for k, v in x.items() if k not in added}
    if isinstance(x, list):
        return [strip(v) for v in x]
    return x


a = json.load(open(sys.argv[1], encoding='utf-8'))
b = json.load(open(sys.argv[2], encoding='utf-8'))
print('IDENTICAL apart from added keys' if strip(a) == strip(b) else 'DIFFERENT beyond added keys')
