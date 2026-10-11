"""Study metrics with 95% Wilson score intervals and Cohen's kappa. Stdlib only; reads the replay corpus, never the network.

    python -m banlag.stats            # table
    python -m banlag.stats --json

Scope: one signed-out India session, one night (10 Oct 2026), ten purposively chosen combinations, one coder. An interval
here describes sampling noise inside that design only. It is not an estimate of how often Google's answers behave this way
in general, and the engine-coder agreement is agreement with one person's labels, not measured accuracy.
"""
import argparse
import json
import math
import sys

Z95 = 1.959963984540054
SCOPE = ('One signed-out India session on one night, ten purposively chosen combinations, one coder. Intervals describe '
         'sampling noise inside this design only, not how often Google behaves this way in general.')


def wilson(k, n, z=Z95):
    """95% Wilson score interval for k successes in n trials, as (low, high) proportions. n == 0 gives (0.0, 1.0)."""
    if n <= 0:
        return 0.0, 1.0
    if not 0 <= k <= n:
        raise ValueError('need 0 <= k <= n')
    p = k / n
    den = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return max(0.0, centre - half), min(1.0, centre + half)


def cohen_kappa(pairs):
    """Cohen's kappa for (a, b) label pairs. Returns None when chance agreement is 1 (a single shared label)."""
    pairs = list(pairs)
    n = len(pairs)
    if not n:
        return None
    po = sum(a == b for a, b in pairs) / n
    labels = {x for p in pairs for x in p}
    pe = sum((sum(a == lab for a, _ in pairs) / n) * (sum(b == lab for _, b in pairs) / n) for lab in labels)
    return None if pe == 1 else (po - pe) / (1 - pe)


def metric(name, k, n, meaning):
    lo, hi = wilson(k, n)
    return {'metric': name, 'k': k, 'n': n, 'rate': round(k / n, 3) if n else None, 'ci95': [round(lo, 3), round(hi, 3)], 'meaning': meaning}


def study_metrics(built=None):
    if built is None:
        from .corpus import build_cases
        built = build_cases()
    cases = [c for c in built['cases'] if c.get('uses')]
    uses = [c['uses'][p] for c in cases for p in ('A', 'B') if c['uses'].get(p)]
    both_e = [c for c in cases if c['g1_locked'] == {'A': 'E', 'B': 'E'}]
    stable = [c for c in cases if c['g1_locked']['A'] is not None and c['g1_locked']['A'] == c['g1_locked']['B']]
    with_status = [c for c in cases if c.get('status')]
    contrast = [c for c in with_status if c['status']['gold_label'] == 'D' and c['g1_locked'] == {'A': 'E', 'B': 'E'}]
    modes = [c['ai_mode'] for c in cases if c.get('ai_mode')]
    records = uses + [c['status'] for c in with_status] + modes + list(built.get('controls') or [])
    primary_pairs = [(r['gold_label'], r['engine_label']) for r in uses]
    all_pairs = [(r['gold_label'], r['engine_label']) for r in records if r.get('gold_label') is not None]
    rows = [
        metric('uses_answers_present_use_unwarned', sum(r['gold_label'] == 'E' for r in uses), len(uses),
               "Uses-query AI Overviews labelled E: present use, no India restriction stated (both passes)."),
        metric('combinations_E_in_both_passes', len(both_e), len(cases),
               'Combinations whose uses answer was labelled E in Pass A and Pass B (the preregistered G1 count).'),
        metric('label_stable_across_passes', len(stable), len(cases), 'Same label in Pass A and Pass B (two passes on the same night).'),
        metric('status_query_states_prohibition', sum(c['status']['gold_label'] == 'D' for c in with_status), len(with_status),
               'Status-query AI Overviews that state the India prohibition (label D).'),
        metric('prompt_dependent_disclosure', len(contrast), len(with_status),
               'Of the combinations with a status capture: E for uses in both passes, yet D when asked about status.'),
        metric('ai_mode_present_use_unwarned', sum(m['gold_label'] == 'E' for m in modes), len(modes),
               'AI Mode answers labelled E (exploratory; labels not locked before capture).'),
        metric('engine_coder_agreement_primary', sum(a == b for a, b in primary_pairs), len(primary_pairs),
               "Engine label equals the coder's locked label on the 20 primary captures (agreement with one coder, not accuracy)."),
        metric('engine_coder_agreement_all', sum(a == b for a, b in all_pairs), len(all_pairs),
               "Engine label equals the coder's label on every labelled record, including exploratory and control records."),
    ]
    k1, k2 = cohen_kappa(primary_pairs), cohen_kappa(all_pairs)
    return {'scope': SCOPE, 'metrics': rows,
            'kappa': {'engine_vs_coder_primary': None if k1 is None else round(k1, 3), 'engine_vs_coder_all': None if k2 is None else round(k2, 3)}}


def table(m):
    lines = ['| Metric | k / n | Rate | 95% CI (Wilson) |', '|---|---|---|---|']
    for r in m['metrics']:
        lines.append(f"| {r['meaning']} | {r['k']} / {r['n']} | {r['rate']:.0%} | {r['ci95'][0]:.0%} to {r['ci95'][1]:.0%} |")
    k = m['kappa']
    lines.append('')
    lines.append(f"Cohen's kappa, engine vs coder: {k['engine_vs_coder_primary']} on the primary captures, {k['engine_vs_coder_all']} on all labelled records.")
    lines.append('')
    lines.append(m['scope'])
    return '\n'.join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description='Study metrics with 95% Wilson intervals (no network).')
    ap.add_argument('--json', action='store_true')
    a = ap.parse_args(argv)
    m = study_metrics()
    print(json.dumps(m, indent=1) if a.json else table(m))
    return 0


if __name__ == '__main__':
    sys.exit(main())
