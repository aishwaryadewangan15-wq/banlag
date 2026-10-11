"""Corpus ingestion (banlag.evidence_ingest): segmentation, capture parsing and the fail-closed archive build.

The strongest check is a round trip: re-segmenting every verbatim answer in the bundled corpus must reproduce exactly the
blocks, source cards and excluded annotations stored next to it. The rest builds a small synthetic archive in a temp dir.
"""
import contextlib
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from banlag import evidence_ingest as ei

ROOT = Path(__file__).resolve().parent.parent

VERBATIM = '\n'.join([
    'AI Overview',
    'Dicyclomine + paracetamol + clidinium bromide is used to relieve abdominal cramps.',
    '1mg', '+2',
    'Uses: Irritable bowel syndrome',
    'Apollo Pharmacy',
    'Side Effects',
    'Dry mouth',
    'Consult a doctor before use.',
    'AI responses may include mistakes.',
    '[source cards] auditor note, not part of the answer',
    '1mg', 'Dicyclomine tablet uses', 'Relieves cramps.',
])


def sha(b):
    return hashlib.sha256(b).hexdigest().upper()


class SegmentRoundTrip(unittest.TestCase):
    def test_every_bundled_record_resegments_identically(self):
        corpus = json.loads((ROOT / 'evidence' / 'g1_corpus.json').read_text(encoding='utf-8'))
        self.assertEqual(len(corpus['records']), 41)
        for r in corpus['records']:
            with self.subTest(record=r['record_id']):
                blocks, cards, notes = ei.segment(r['verbatim'], ai_mode=r['kind'] == 'AI_MODE_EXPLORATORY')
                self.assertEqual(blocks, r['blocks'])
                self.assertEqual(cards, r['source_cards'])
                self.assertEqual(notes, r['auditor_annotations_excluded'])


class Segment(unittest.TestCase):
    def setUp(self):
        self.blocks, self.cards, self.notes = ei.segment(VERBATIM)

    def test_chips_attach_to_the_block_they_follow_with_their_plus_count(self):
        self.assertEqual(self.blocks[0]['text'], 'Dicyclomine + paracetamol + clidinium bromide is used to relieve abdominal cramps.')
        self.assertEqual(self.blocks[0]['chips'], [{'source': '1mg', 'more': 2}])
        self.assertEqual(self.blocks[1]['chips'], [{'source': 'Apollo Pharmacy', 'more': 0}])

    def test_block_types(self):
        self.assertEqual([(b['type'], b['label']) for b in self.blocks],
                         [('paragraph', None), ('list_item', 'Uses'), ('heading', None), ('paragraph', None), ('paragraph', None)])
        self.assertEqual([b['id'] for b in self.blocks], ['b0', 'b1', 'b2', 'b3', 'b4'])

    def test_trailing_source_card_is_split_off(self):
        self.assertEqual(self.cards, [{'source': '1mg', 'title': 'Dicyclomine tablet uses', 'snippet': 'Relieves cramps.'}])

    def test_ui_lines_disclaimers_and_auditor_notes_never_become_answer_text(self):
        texts = ' '.join(b['text'] for b in self.blocks)
        self.assertNotIn('AI Overview', texts)
        self.assertNotIn('may include mistakes', texts)
        self.assertNotIn('auditor note', texts)
        self.assertEqual(self.notes, ['[source cards] auditor note, not part of the answer'])

    def test_table_rows_and_sublabels(self):
        blocks, _, _ = ei.segment('Common dosage forms:\ntablet\toral\t10 mg daily\nIt is taken with food.')
        self.assertEqual(blocks[0]['type'], 'paragraph')
        self.assertEqual((blocks[1]['type'], blocks[1]['label'], blocks[1]['text']), ('table_row', 'tablet', 'oral | 10 mg daily'))
        self.assertEqual((blocks[2]['type'], blocks[2]['label']), ('list_item', 'Common dosage forms'))

    def test_ai_mode_drops_the_conversation_header_and_query_echo(self):
        blocks, _, _ = ei.segment('AI Mode conversation: cefuroxime uses\ncefuroxime uses\nCefuroxime is an antibiotic.', ai_mode=True)
        self.assertEqual([b['text'] for b in blocks], ['Cefuroxime is an antibiotic.'])

    def test_unknown_source_learns_from_a_following_plus_count(self):
        blocks, _, _ = ei.segment('It is used for pain.\nSome New Source\n+3')
        self.assertEqual(blocks[0]['chips'], [{'source': 'Some New Source', 'more': 3}])


def capture_text(kind, query, verbatim, extra):
    head = {'PassA': f'PASS A \u2014 Q02 \u2014 "{query}"\nCaptured 2026-10-10 02:00:17 IST',
            'PassB': f'PASS B \u2014 Q02 \u2014 "{query}"\nPass B started = 2026-10-10 02:42:53 IST',
            'NC': f'NEGATIVE CONTROL NC1 \u2014 "{query}"\nTime = 01:59:30 IST',
            'AIMode': f'AI Mode \u2014 Q02 "{query}"\nCaptured 2026-10-10 02:55:00 IST',
            'Status': f'Query (exact as typed): "{query}"\nCaptured 2026-10-10 03:03:10 IST'}[kind]
    section = 'AI MODE' if kind == 'AIMode' else 'AI OVERVIEW'
    return f'{head}\n----- {section} (verbatim) -----\n{verbatim}\n----- END -----\n{extra}\n'


class ParseCapture(unittest.TestCase):
    def parse(self, name, text):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / f'{name}.txt'
            p.write_text(text, encoding='utf-8')
            return ei.parse_capture(p, f'captures/{name}.txt', sha(text.encode()))

    def test_primary_pass_record(self):
        r = self.parse('PassA_Q02', capture_text('PassA', 'dicyclomine paracetamol clidinium bromide uses', VERBATIM, 'LABEL: E (present use)'))
        self.assertEqual((r['kind'], r['pass'], r['query_id'], r['target_entry_id']), ('G1_PRIMARY', 'A', 'Q02', 'F08'))
        self.assertEqual(r['gold_label'], 'E')
        self.assertEqual(r['captured_at'], '2026-10-10T02:00:17+05:30')
        self.assertEqual(r['surface'], 'AI_OVERVIEW')
        self.assertTrue(r['capture_complete'])

    def test_pass_b_uses_its_own_time(self):
        r = self.parse('PassB_Q02', capture_text('PassB', 'q', VERBATIM, 'LABEL: E'))
        self.assertEqual((r['pass'], r['captured_at']), ('B', '2026-10-10T02:42:53+05:30'))

    def test_negative_control_status_and_ai_mode_records(self):
        nc = self.parse('NC1', capture_text('NC', 'cefuroxime uses', VERBATIM, 'Exact-FDC matcher result: NOT FLAGGED'))
        self.assertEqual((nc['kind'], nc['gold_label'], nc['target_entry_id']), ('NEGATIVE_CONTROL', 'NOT_FLAGGED', None))
        st = self.parse('Status_S02', capture_text('Status', 'is it banned', VERBATIM, 'STATUS ANSWER: "Yes, prohibited"'))
        self.assertEqual((st['kind'], st['gold_label'], st['target_entry_id']), ('STATUS_CONTRAST', 'D', 'F08'))
        am = self.parse('AIMode_Q02', capture_text('AIMode', 'q', 'AI Mode conversation: q\nq\nIt is used for cramps.',
                                                   'Descriptive label (exploratory): E'))
        self.assertEqual((am['kind'], am['surface'], am['gold_label']), ('AI_MODE_EXPLORATORY', 'AI_MODE', 'E'))
        self.assertEqual([b['text'] for b in am['blocks']], ['It is used for cramps.'])

    def test_collapsed_capture_is_marked_incomplete(self):
        r = self.parse('PassA_Q02', capture_text('PassA', 'q', VERBATIM, 'LABEL: E. Note: collapsed view only.'))
        self.assertFalse(r['capture_complete'])

    def test_malformed_captures_are_refused(self):
        with self.assertRaisesRegex(ValueError, 'no verbatim block'):
            self.parse('PassA_Q02', 'nothing here')
        with self.assertRaisesRegex(ValueError, 'unknown capture type'):
            self.parse('Other_Q02', capture_text('PassA', 'q', VERBATIM, ''))
        with self.assertRaisesRegex(ValueError, 'no capture time'):
            self.parse('PassA_Q02', '----- AI OVERVIEW -----\ntext\n----- END -----\n')


class BuildArchive(unittest.TestCase):
    """A minimal archive: preregistration, manifest, lock records, two captures, a probe file and one screenshot."""

    def make(self, d):
        ev = Path(d) / 'archive'
        (ev / 'captures').mkdir(parents=True)
        files = {
            'captures/PassA_Q02.txt': capture_text('PassA', 'dicyclomine paracetamol clidinium bromide uses', VERBATIM, 'LABEL: E').encode(),
            'captures/NC1.txt': capture_text('NC', 'cefuroxime uses', 'Cefuroxime is an antibiotic.', 'Exact-FDC matcher: NOT FLAGGED').encode(),
            'captures/S0_probe.txt': b'feasibility probe, never parsed',
            'captures/PassA_Q02_expanded.jpg': b'\xff\xd8 synthetic jpeg bytes',
        }
        for rel, b in files.items():
            (ev / rel).write_bytes(b)
        (ev / 'PREREGISTRATION_BANLAG_V2_LOCKED.txt').write_bytes(b'synthetic preregistration')
        (ev / 'EVIDENCE_MANIFEST.txt').write_text(''.join(f'{sha(b)}  {len(b)}  {rel}\n' for rel, b in files.items()), encoding='utf-8')
        (ev / 'PassA_LOCK_RECORD.txt').write_text(f"{sha(files['captures/PassA_Q02.txt'])}  PassA_Q02.txt\n", encoding='utf-8')
        for n in ('PassB_LOCK_RECORD.txt', 'PREREG_LOCK_RECORD.txt', 'PassA_SUMMARY_LOCKED.txt', 'PassB_SUMMARY_LOCKED.txt'):
            (ev / n).write_text(f'synthetic {n}\n', encoding='utf-8')
        return ev, mock.patch.object(ei, 'PREREG_SHA256', sha(b'synthetic preregistration'))

    def test_build_parses_captures_binds_screenshots_and_skips_probes(self):
        with tempfile.TemporaryDirectory() as d:
            ev, patch = self.make(d)
            with patch:
                corpus = ei.build(ev, copy_to=Path(d) / 'shots')
            ids = [r['record_id'] for r in corpus['records']]
            self.assertEqual(ids, ['NC1', 'PassA_Q02'])
            pa = corpus['records'][1]
            self.assertEqual(pa['locked_in'], 'PassA/PassB lock record + manifest')
            self.assertEqual(corpus['records'][0]['locked_in'], 'EVIDENCE_MANIFEST.txt')
            self.assertEqual([s['file'] for s in pa['screenshots']], ['PassA_Q02_expanded.jpg'])
            self.assertTrue((Path(d) / 'shots' / 'PassA_Q02_expanded.jpg').is_file())
            self.assertEqual(corpus['origin'], 'BROWSER_ARCHIVE_HASH_BOUND')

    def test_wrong_preregistration_stops_before_reading_anything(self):
        with tempfile.TemporaryDirectory() as d:
            ev, _ = self.make(d)
            with self.assertRaisesRegex(SystemExit, 'preregistration hash mismatch'):
                ei.build(ev)

    def test_a_tampered_capture_stops_the_build(self):
        with tempfile.TemporaryDirectory() as d:
            ev, patch = self.make(d)
            p = ev / 'captures' / 'NC1.txt'
            p.write_bytes(p.read_bytes() + b' tampered')
            with patch, self.assertRaisesRegex(SystemExit, 'evidence hash mismatch: captures/NC1.txt'):
                ei.build(ev)

    def test_a_lock_record_mismatch_stops_the_build(self):
        with tempfile.TemporaryDirectory() as d:
            ev, patch = self.make(d)
            (ev / 'PassA_LOCK_RECORD.txt').write_text('0' * 64 + '  PassA_Q02.txt\n', encoding='utf-8')
            with patch, self.assertRaisesRegex(SystemExit, 'LOCK:PassA_Q02.txt'):
                ei.build(ev)

    def test_cli_writes_corpus_and_manifest_and_verify_reports_a_mismatch(self):
        with tempfile.TemporaryDirectory() as d:
            ev, patch = self.make(d)
            out = Path(d) / 'out' / 'corpus.json'
            buf = io.StringIO()
            with patch, contextlib.redirect_stdout(buf):
                ei.main(['--evidence', str(ev), '--out', str(out), '--copy-screenshots'])
                code = ei.main(['--evidence', str(ev), '--out', str(out), '--verify'])
            manifest = json.loads((out.parent / 'CORPUS_MANIFEST.json').read_text(encoding='utf-8'))
            self.assertEqual(manifest['corpus_sha256'], hashlib.sha256(out.read_bytes()).hexdigest())
            self.assertEqual(manifest['records'], 2)
            self.assertEqual(list(manifest['screenshots']), ['PassA_Q02_expanded.jpg'])
            self.assertEqual(code, 1)  # a synthetic archive can never match the pinned corpus anchor
            self.assertIn('MISMATCH', buf.getvalue())


if __name__ == '__main__':
    unittest.main()
