"""Build the replay corpus from the locked G1 browser-evidence archive (READ-ONLY input).

    python -m banlag.evidence_ingest --evidence <banlag_v2_audit> [--out evidence/g1_corpus.json] [--copy-screenshots]

Every source file is hash-checked against EVIDENCE_MANIFEST.txt and, where applicable, the Pass A / Pass B
lock records before it is parsed. The archive is never written to. Parsed records keep the verbatim AI text,
a structural segmentation (AI-authored blocks, the source chip shown after each block, trailing source cards)
and the coder's locked label, which the engine is later compared against (never trained on at runtime).
"""
import argparse
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

PREREG_SHA256 = 'C4A8EF1672584D52EF9943DEF18CAC1B46B57C8BBA9D331727EB15BD42AFC12E'
QUERY_TO_ENTRY = {'Q01': 'F01', 'Q02': 'F08', 'Q03': 'F09', 'Q04': 'F10', 'Q05': 'F11',
                  'Q06': 'F12', 'Q07': 'F13', 'Q08': 'F14', 'Q09': 'F15', 'Q10': 'F16'}
# Source names Google displays as citation chips / card headers in this archive. Lines followed by '+N'
# are added per file; this list covers card-only sources and single-occurrence chips.
KNOWN_SOURCES = {
    '1mg', 'Apollo Pharmacy', 'Truemeds', 'TeamLease RegTech', 'CARE Hospitals', 'National Institutes of Health (NIH) | (.gov)',
    'ScienceDirect.com', 'Zeelab Pharmacy', 'PharmEasy', 'myUpchar', 'Nordic Formulations', 'Cleveland Clinic', 'Mayo Clinic',
    'Drugcarts', 'Diabetes UK', 'eGazette', 'PIB', 'Wikipedia', 'Medindia', 'DrugBank', 'MedlinePlus (.gov)', 'nhs.uk',
    'Plenum Biotech', 'Patsnap Synapse', 'CliniExperts', 'Healthline', 'Academia.edu', 'Nexwin Pharma Pvt. Ltd.', 'Vinmec',
    'PlatinumRx', 'DavaIndia', 'Arlak Biotech', 'Drugs.com', 'Cafoli', 'Medanta', 'Study.com', 'PACE Hospitals',
    'Genericart Medicine Pvt. Ltd. | Wahi Kaam, Sahi Daam', 'Trumac Healthcare', 'Healio', 'Practo', 'Complinity',
    'The New Indian Express', 'LinkedIn', 'Instagram', 'WebMD', 'Zynapte Technologies', 'MedPath Trial', 'GoodRx',
    'LinkedIn\u00b7Dr Abhishek Tripathi', 'YouTube', 'PMC', 'Times of India', 'Hindustan Times',
}
UI_LINES = {'AI Overview', 'Show all', 'Skip to previous prompt', 'AI Mode response is ready'}
DISCLAIMER = re.compile(r'^(?:This is for informational purposes only|AI responses may include mistakes|\[closing disclaimer)', re.I)
PLUS = re.compile(r'^\+\d+$')


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest().upper()


def read_manifest(ev):
    hashes = {}
    for line in (ev / 'EVIDENCE_MANIFEST.txt').read_text(encoding='utf-8').splitlines():
        m = re.match(r'^([0-9A-F]{64})\s+(\d+)\s+(.+)$', line)
        if m:
            hashes[m.group(3).strip().replace('\\', '/')] = m.group(1)
    return hashes


def read_lock(ev, name):
    out = {}
    for line in (ev / name).read_text(encoding='utf-8').splitlines():
        m = re.match(r'^([0-9A-F]{64})\s+(\S+)$', line)
        if m:
            out[m.group(2)] = m.group(1)
    return out


def _title_case(s):
    words = [w for w in re.findall(r'[A-Za-z][A-Za-z\-]*', s) if len(w) >= 4]
    return bool(words) and sum(w[0].isupper() for w in words) / len(words) >= 0.6


def segment(verbatim, ai_mode=False):
    """Split a verbatim innerText block into AI-authored blocks (with chips) and trailing source cards."""
    lines = [l.strip() for l in verbatim.split('\n')]
    lines = [l for l in lines if l]
    if ai_mode and lines and lines[0].lower().startswith('ai mode conversation'):
        query_echo = lines[0].split(':', 1)[-1].strip().lower()
        lines = lines[1:]
        if lines and lines[0].lower() == query_echo:
            lines = lines[1:]
    vocab = set(KNOWN_SOURCES)
    for i, l in enumerate(lines[1:], 1):
        if PLUS.match(l):
            vocab.add(lines[i - 1])
    annotations = [l for l in lines if l.startswith('[source cards')]
    lines = [l for l in lines if l not in UI_LINES and not DISCLAIMER.match(l) and l not in annotations]
    cards = []

    def title_like(s):
        return not re.search(r'[.?!]$', s) or s.endswith('...') or s.endswith('…')

    while (len(lines) >= 3 and lines[-3] in vocab and lines[-2] not in vocab and lines[-1] not in vocab
           and not PLUS.match(lines[-2]) and not PLUS.match(lines[-1]) and title_like(lines[-2])):
        cards.insert(0, {'source': lines[-3], 'title': lines[-2], 'snippet': lines[-1]})
        lines = lines[:-3]
    blocks, sublabel = [], None
    for l in lines:
        if PLUS.match(l):
            if blocks and blocks[-1]['chips']:
                blocks[-1]['chips'][-1]['more'] = int(l[1:])
            continue
        if l in vocab or l.startswith('\u00b7'):
            if blocks:
                if l.startswith('\u00b7') and blocks[-1]['chips']:
                    blocks[-1]['chips'][-1]['source'] += l
                else:
                    blocks[-1]['chips'].append({'source': l, 'more': 0})
            continue
        bid = f'b{len(blocks)}'
        m = re.match(r'^([^:.(][^:.]{1,59}):\s+(.+)$', l)
        if m:
            blocks.append({'id': bid, 'type': 'list_item', 'label': m.group(1).strip(), 'text': m.group(2).strip(), 'chips': []})
        elif l.endswith(':') and len(l) <= 80:
            sublabel = l[:-1].strip()
            blocks.append({'id': bid, 'type': 'paragraph', 'label': None, 'text': l, 'chips': []})
        elif len(l) <= 70 and not re.search(r'[.?!]$', l) and not l.startswith('•') and _title_case(l):
            sublabel = None
            blocks.append({'id': bid, 'type': 'heading', 'label': None, 'text': l, 'chips': []})
        elif '\t' in l:
            first, _, rest = l.partition('\t')
            blocks.append({'id': bid, 'type': 'table_row', 'label': first.strip(), 'text': rest.replace('\t', ' | '), 'chips': []})
        else:
            blocks.append({'id': bid, 'type': 'list_item' if sublabel else 'paragraph', 'label': sublabel, 'text': l, 'chips': []})
    return blocks, cards, annotations


def _first(pattern, text, group=1, flags=re.M):
    m = re.search(pattern, text, flags)
    return m.group(group).strip() if m else None


def parse_capture(path, rel, digest):
    t = path.read_text(encoding='utf-8')
    name = path.stem
    m = re.search(r'-{5} (?:AI OVERVIEW|AI MODE)[^\n]*-{5}\n(.*?)\n-{5} END', t, re.S)
    if not m:
        raise ValueError(f'{rel}: no verbatim block')
    verbatim = m.group(1)
    if name.startswith('Pass'):
        kind, pass_, qid = 'G1_PRIMARY', name[4], name.split('_')[1]
        query = _first(r'^PASS [AB] \u2014 Q\d\d \u2014 "([^"]+)"', t)
        gold = _first(r'^LABEL:\s*([A-F])\b', t)
    elif name.startswith('NC'):
        kind, pass_, qid = 'NEGATIVE_CONTROL', None, name
        query = _first(r'^NEGATIVE CONTROL NC\d \u2014 "([^"]+)"', t)
        gold = 'NOT_FLAGGED' if re.search(r'Exact-FDC matcher[^\n]*NOT FLAGGED', t) else None
    elif name.startswith('AIMode'):
        kind, pass_, qid = 'AI_MODE_EXPLORATORY', None, name.split('_')[1]
        query = _first(r'\u2014 Q\d\d "([^"]+)"', t)
        gold = _first(r'Descriptive label \(exploratory\):\s*([A-F])\b', t)
    elif name.startswith('Status'):
        kind, pass_, qid = 'STATUS_CONTRAST', None, name.split('_')[1]
        query = _first(r'^Query \(exact[^)]*\):\s*"([^"]+)"', t)
        gold = 'D' if re.search(r'^STATUS ANSWER:\s*"Yes', t, re.M) else None
    else:
        raise ValueError(f'{rel}: unknown capture type')
    ai_mode = kind == 'AI_MODE_EXPLORATORY'
    blocks, cards, annotations = segment(verbatim, ai_mode=ai_mode)
    hms = (_first(r'Pass B[^\n]*?=\s*(?:2026-10-10\s+)?(\d\d:\d\d:\d\d) IST', t) if pass_ == 'B' else None) \
        or _first(r'2026-10-10\s+(\d\d:\d\d:\d\d) IST', t) or _first(r'=\s*(\d\d:\d\d:\d\d) IST', t)
    if not hms:
        raise ValueError(f'{rel}: no capture time found')
    ist = '2026-10-10 ' + hms
    target_q = qid if qid.startswith('Q') else ('Q' + qid[1:] if qid.startswith('S') else None)
    return {
        'record_id': name, 'kind': kind, 'pass': pass_, 'query_id': qid, 'query': query,
        'target_entry_id': QUERY_TO_ENTRY.get(target_q) if target_q else None,
        'surface': 'AI_MODE' if ai_mode else 'AI_OVERVIEW',
        'captured_at': (ist.replace(' ', 'T') + '+05:30') if ist else None,
        'source_file': rel, 'source_sha256': digest,
        'capture_complete': not re.search(r'collapsed view|closing disclaimer not present', t, re.I),
        'verbatim': verbatim, 'blocks': blocks, 'source_cards': cards, 'auditor_annotations_excluded': annotations,
        'gold_label': gold,
        'gold_basis': {'G1_PRIMARY': 'locked single-coder label (Pass lock record)', 'NEGATIVE_CONTROL': 'preregistered expectation: not one of the ten sets',
                       'AI_MODE_EXPLORATORY': 'coder descriptive label (exploratory, not locked before capture)',
                       'STATUS_CONTRAST': "derived from coder's STATUS ANSWER line ('Yes ... prohibited')"}[kind],
        'coder_notes': t[m.end():].strip()[:4000],
        'screenshots': [],
    }


def build(ev, copy_to=None):
    ev = Path(ev)
    prereg = ev / 'PREREGISTRATION_BANLAG_V2_LOCKED.txt'
    if sha256_file(prereg) != PREREG_SHA256:
        raise SystemExit('STOP: preregistration hash mismatch; refusing to ingest.')
    manifest = read_manifest(ev)
    locks = {**read_lock(ev, 'PassA_LOCK_RECORD.txt'), **read_lock(ev, 'PassB_LOCK_RECORD.txt')}
    problems = []
    for rel, h in manifest.items():
        p = ev / rel
        if not p.exists() or sha256_file(p) != h:
            problems.append(rel)
    for fname, h in locks.items():
        p = ev / fname if (ev / fname).exists() else ev / 'captures' / fname
        if sha256_file(p) != h:
            problems.append('LOCK:' + fname)
    if problems:
        raise SystemExit('STOP: evidence hash mismatch: ' + ', '.join(problems))
    records = []
    for rel in sorted(manifest):
        if not rel.startswith('captures/') or not rel.endswith('.txt') or Path(rel).name.startswith('S0_'):
            continue
        rec = parse_capture(ev / rel, rel, manifest[rel])
        rec['locked_in'] = 'PassA/PassB lock record + manifest' if Path(rel).name in locks else 'EVIDENCE_MANIFEST.txt'
        shots = sorted(r for r in manifest if r.endswith('.jpg') and Path(r).stem.split('_collapsed')[0].split('_expanded')[0] == rec['record_id'])
        rec['screenshots'] = [{'file': Path(r).name, 'sha256': manifest[r]} for r in shots]
        records.append(rec)
    summaries = {n: (ev / n).read_text(encoding='utf-8') for n in ('PassA_SUMMARY_LOCKED.txt', 'PassB_SUMMARY_LOCKED.txt')}
    corpus = {
        'schema': 'banlag.g1_corpus.v1',
        'origin': 'BROWSER_ARCHIVE_HASH_BOUND',
        'origin_statement': ('Signed-out public Google captures made in a Chromium-based app browser (UA contains a Claude token), '
                             'India region, 10 Oct 2026 01:59-03:08 IST, transcribed from DOM innerText by the capturing agent. '
                             'NOT SerpApi captures; no provider search IDs exist. Citation links were opaque google.com/goto tokens; '
                             'cited pages were not opened.'),
        'prereg_sha256': PREREG_SHA256,
        'manifest_sha256': sha256_file(ev / 'EVIDENCE_MANIFEST.txt'),
        'lock_records': {n: sha256_file(ev / n) for n in ('PREREG_LOCK_RECORD.txt', 'PassA_LOCK_RECORD.txt', 'PassB_LOCK_RECORD.txt')},
        'g1_rule': {'threshold_positives': 3, 'min_outside_family': 1, 'denominator': 10,
                    'family': ['Q06', 'Q07', 'Q08', 'Q10'], 'positive': 'label E in BOTH Pass A and Pass B'},
        'query_to_entry': QUERY_TO_ENTRY,
        'locked_summaries': summaries,
        'records': records,
    }
    if copy_to:
        dst = Path(copy_to)
        dst.mkdir(parents=True, exist_ok=True)
        for rel, h in manifest.items():
            if rel.endswith('.jpg'):
                target = dst / Path(rel).name
                shutil.copyfile(ev / rel, target)
                if sha256_file(target) != h:
                    raise SystemExit('STOP: screenshot copy hash mismatch ' + rel)
    return corpus


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--evidence', required=True)
    ap.add_argument('--out', default=str(Path(__file__).resolve().parent.parent / 'evidence' / 'g1_corpus.json'))
    ap.add_argument('--copy-screenshots', action='store_true')
    ap.add_argument('--verify', action='store_true',
                    help='read-only: rebuild the corpus in memory from the locked archive and compare it with the bundled corpus and the pinned anchor; writes nothing')
    a = ap.parse_args(argv)
    if a.verify:
        from .corpus import EXPECTED_CORPUS_SHA256
        rebuilt = json.dumps(build(a.evidence), ensure_ascii=False, indent=1, sort_keys=False).encode('utf-8')
        bundled = Path(a.out).read_bytes() if Path(a.out).is_file() else b''
        r_sha, b_sha = hashlib.sha256(rebuilt).hexdigest(), hashlib.sha256(bundled).hexdigest()
        ok = rebuilt == bundled and r_sha == EXPECTED_CORPUS_SHA256
        print(f'reconstructed={r_sha}\nbundled      ={b_sha}\nanchor       ={EXPECTED_CORPUS_SHA256}\n'
              f'{"VERIFIED: bundled corpus is the byte-identical reconstruction of the locked archive" if ok else "MISMATCH"}')
        return 0 if ok else 1
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    corpus = build(a.evidence, out.parent / 'screenshots' if a.copy_screenshots else None)
    data = json.dumps(corpus, ensure_ascii=False, indent=1, sort_keys=False).encode('utf-8')
    out.write_bytes(data)
    digest = hashlib.sha256(data).hexdigest()
    shots = sorted((out.parent / 'screenshots').glob('*.jpg')) if a.copy_screenshots else []
    manifest = {'schema': 'banlag.corpus_manifest.v1', 'corpus_file': out.name, 'corpus_sha256': digest,
                'records': len(corpus['records']), 'prereg_sha256': corpus['prereg_sha256'],
                'archive_manifest_sha256': corpus['manifest_sha256'], 'lock_records': corpus['lock_records'],
                'screenshots': {p.name: sha256_file(p) for p in shots},
                'built_by': 'python -m banlag.evidence_ingest --evidence <banlag_v2_audit> --copy-screenshots'}
    (out.parent / 'CORPUS_MANIFEST.json').write_text(json.dumps(manifest, indent=1), encoding='utf-8')
    print(f'records={len(corpus["records"])} sha256={digest} screenshots={len(shots)} -> {out}')


if __name__ == '__main__':
    sys.exit(main())
