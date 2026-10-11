"""Budgeted multi-day, multi-location capture batches. Writes plan files only; never calls SerpApi.

    python -m banlag.batch --days 3 --locations mumbai,delhi,bengaluru               # print the budget, write nothing
    python -m banlag.batch --days 3 --locations mumbai,delhi --out plans/batches/b1 --max-total-calls 200

Every combination gets two plans per location per day:
  uses    C1 google search (uses query), C2 google_ai_overview follow-up (only if C1 returned a page_token),
          C3 google_ai_mode (same uses query)                                                     <= 3 calls
  status  C1 google search (status query), C2 google_ai_overview follow-up (only if needed)        <= 2 calls
Query wording follows the preregistered templates exactly ('<ingredients> uses' and 'is <ingredients> prohibited for
manufacture sale or distribution in india in 2026'), so the ten study combinations get their preregistered strings back.
Each plan carries its schedule day, so every plan file (and its SHA-256 approval) is unique; each one is still run and
approved one at a time with `python -m banlag.collector`. Notices that name a component only generically (F07) are
skipped: no capture could be scored against them.
"""
import argparse
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path

from . import collector
from .legal import registry

LOCATIONS = {  # SerpApi canonical location names (serpapi.com/locations.json), all target_type City
    'mumbai': 'Mumbai,Maharashtra,India', 'delhi': 'Delhi,Delhi,India', 'bengaluru': 'Bengaluru,Karnataka,India',
    'kolkata': 'Kolkata,West Bengal,India', 'chennai': 'Chennai,Tamil Nadu,India', 'hyderabad': 'Hyderabad,Telangana,India',
    'jabalpur': 'Jabalpur,Madhya Pradesh,India', 'lucknow': 'Lucknow,Uttar Pradesh,India',
}
USES = '{} uses'
STATUS = 'is {} prohibited for manufacture sale or distribution in india in 2026'
COMMON = {'gl': 'in', 'hl': 'en', 'google_domain': 'google.co.in', 'device': 'desktop', 'no_cache': 'true'}


def capturable_entries(ids=None):
    out = [e for e in registry()['entries'] if not e.get('underspecified_terms')]
    if ids:
        wanted = set(ids)
        unknown = wanted - {e['id'] for e in registry()['entries']}
        if unknown:
            raise ValueError('unknown registry ids: ' + ', '.join(sorted(unknown)))
        skipped = wanted - {e['id'] for e in out}
        if skipped:
            raise ValueError('cannot capture an underspecified notice: ' + ', '.join(sorted(skipped)))
        out = [e for e in out if e['id'] in wanted]
    return out


def query_words(entry):
    return ' '.join(entry['ingredients'])


def plans_for(entry, location_key, day, start):
    loc = LOCATIONS[location_key]
    when = (start + dt.timedelta(days=day - 1)).isoformat()
    scope = 'preregistered study combination' if entry.get('query_id') else 'outside the preregistered study (templated wording)'
    base = {'schema': 'banlag.plan.v1', 'case': entry['id'], 'ingredients': entry['ingredients'],
            'schedule': {'day': day, 'date': when, 'location': loc}}
    params = {**COMMON, 'location': loc}
    uses = {**base, 'purpose': f"Batch capture, day {day} ({when}), {loc}: uses query, AI Overview and AI Mode for {entry['id']} "
                                f"({entry['notice']}), {scope}.", 'max_calls': 3,
            'notes': ['C2 runs only if C1 returns ai_overview.page_token without inline text_blocks.',
                      'Any HTTP error, provider error or non-Success status stops the run; there are no retries.'],
            'calls': [{'call_id': 'C1', 'role': 'uses_search', 'engine': 'google', 'params': {'q': USES.format(query_words(entry)), **params}},
                      {'call_id': 'C2', 'role': 'uses_ai_overview', 'engine': 'google_ai_overview', 'page_token_from': 'C1', 'params': {}},
                      {'call_id': 'C3', 'role': 'uses_ai_mode', 'engine': 'google_ai_mode',
                       'params': {'q': USES.format(query_words(entry)), **{k: v for k, v in params.items() if k != 'google_domain'}}}]}
    status = {**base, 'purpose': f"Batch capture, day {day} ({when}), {loc}: status query and its AI Overview for {entry['id']} "
                                  f"({entry['notice']}), {scope}.", 'max_calls': 2,
              'notes': ['C2 runs only if C1 returns ai_overview.page_token without inline text_blocks.',
                        'Any HTTP error, provider error or non-Success status stops the run; there are no retries.'],
              'calls': [{'call_id': 'C1', 'role': 'status_search', 'engine': 'google', 'params': {'q': STATUS.format(query_words(entry)), **params}},
                        {'call_id': 'C2', 'role': 'status_ai_overview', 'engine': 'google_ai_overview', 'page_token_from': 'C1', 'params': {}}]}
    return {'uses': uses, 'status': status}


def build_batch(entry_ids=None, locations=('mumbai',), days=1, start=None):
    start = start or dt.date.today()
    for k in locations:
        if k not in LOCATIONS:
            raise ValueError(f'unknown location {k!r}; choose from {", ".join(LOCATIONS)}')
    if not 1 <= days <= 30:
        raise ValueError('days must be 1..30')
    files = {}
    for day in range(1, days + 1):
        for loc in locations:
            for e in capturable_entries(entry_ids):
                for kind, plan in plans_for(e, loc, day, start).items():
                    files[f'day{day:02d}_{loc}_{e["id"]}_{kind}.json'] = plan
    return files


def budget(files):
    per_day = {}
    for plan in files.values():
        per_day[plan['schedule']['date']] = per_day.get(plan['schedule']['date'], 0) + plan['max_calls']
    return {'plans': len(files), 'max_calls': sum(p['max_calls'] for p in files.values()),
            'min_calls': sum(2 if any(c['engine'] == 'google_ai_mode' for c in p['calls']) else 1 for p in files.values()),
            'max_calls_per_day': per_day}


def write_batch(files, out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    rows = []
    for name, plan in files.items():
        data = (json.dumps(plan, indent=1, ensure_ascii=False) + '\n').encode('utf-8')
        (out / name).write_bytes(data)
        _, sha = collector.load_plan(out / name)  # every plan must pass the collector's own validation
        assert sha == hashlib.sha256(data).hexdigest()
        rows.append({'file': name, 'sha256': sha, 'case': plan['case'], 'date': plan['schedule']['date'],
                     'location': plan['schedule']['location'], 'max_calls': plan['max_calls']})
    manifest = {'schema': 'banlag.batch_manifest.v1', 'budget': budget(files), 'plans': rows,
                'run_each_with': 'BANLAG_SERPAPI_APPROVAL=<sha256> python -m banlag.collector <plan> --approve <sha256>'}
    (out / 'BATCH_MANIFEST.json').write_text(json.dumps(manifest, indent=1), encoding='utf-8')
    return manifest


def main(argv=None):
    ap = argparse.ArgumentParser(description='Write a budgeted multi-day, multi-location batch of capture plans (no network).')
    ap.add_argument('--entries', help='comma-separated registry ids (default: every capturable notice)')
    ap.add_argument('--locations', default='mumbai', help='comma-separated keys: ' + ', '.join(LOCATIONS))
    ap.add_argument('--days', type=int, default=1)
    ap.add_argument('--start', help='first capture date, YYYY-MM-DD (default: today)')
    ap.add_argument('--max-total-calls', type=int, help='refuse to write a batch whose worst case exceeds this')
    ap.add_argument('--out', help='directory to create; without it nothing is written')
    a = ap.parse_args(argv)
    try:
        files = build_batch(a.entries.split(',') if a.entries else None, [x.strip() for x in a.locations.split(',')], a.days,
                            dt.date.fromisoformat(a.start) if a.start else None)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2
    b = budget(files)
    print(f"{b['plans']} plans; SerpApi calls: at most {b['max_calls']}, at least {b['min_calls']} (follow-ups only run when needed).")
    if a.max_total_calls is not None and b['max_calls'] > a.max_total_calls:
        print(f'Over budget: {b["max_calls"]} > {a.max_total_calls}. Nothing written.', file=sys.stderr)
        return 2
    if not a.out:
        print('No --out given: nothing written.')
        return 0
    write_batch(files, a.out)
    print(f'Wrote {b["plans"]} plans and BATCH_MANIFEST.json to {a.out}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
