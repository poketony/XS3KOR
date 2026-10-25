import json
from pathlib import Path
import tempfile
import unittest

import subtitles as sub


class CodecTests(unittest.TestCase):
    def test_mapping_and_exact_format_preservation(self):
        text = ';comment\r\n00:01:02\t$col707070;[\uac00/ruby]\\n\u300c\uac00\u300d\u2026\u2015\u2500\r\nend\n'
        result = sub.encode_editor(text.encode('utf-8'), {'\uac00': '\u4e00'})
        self.assertEqual(result.decode(sub.ENCODING), text.replace('\uac00', '\u4e00'))
        self.assertEqual(result.count(b'\r\n'), 2)
        self.assertIn(b'\\n', result)

    def test_utf8_bom_is_not_a_game_character(self):
        self.assertEqual(sub.encode_editor(b'\xef\xbb\xbfend\n', {}), b'end\n')

    def test_game_roundtrip_without_reverse_font_mapping(self):
        text = ';\u5b57\u5e55\n00:00:01\t\u4e00\nend\n'
        game = text.encode(sub.ENCODING)
        editor = sub.decode_game(game)
        self.assertEqual(editor, text.encode('utf-8'))
        self.assertEqual(sub.encode_editor(editor, {'\uac00': '\u4e00'}), game)

    def test_jis2004_extension_is_supported(self):
        text = '00:00:01\t\u4ff1\nend\n'
        with self.assertRaises(UnicodeEncodeError):
            text.encode('euc_jp')
        self.assertEqual(sub.decode_game(text.encode(sub.ENCODING)), text.encode('utf-8'))

    def test_missing_hangul_and_jamo_fail(self):
        for char in ('\uac00', '\u3131', '\u1100'):
            with self.subTest(char=char), self.assertRaisesRegex(ValueError, 'Line 2.*missing'):
                sub.encode_editor(('header\n' + char).encode('utf-8'), {})

    def test_unencodable_punctuation_is_not_replaced(self):
        with self.assertRaisesRegex(ValueError, 'Line 2.*cannot encode'):
            sub.encode_editor('header\n\u2014'.encode('utf-8'), {})

    def test_invalid_editor_and_nul_fail(self):
        with self.assertRaises(UnicodeDecodeError):
            sub.encode_editor(b'\xff', {})
        with self.assertRaisesRegex(ValueError, 'NUL'):
            sub.encode_editor(b'e\0n\0d\0', {})
        with self.assertRaises(ValueError):
            sub.decode_game(b'end\0')


class BatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).parent, prefix='test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'repo'
        self.rom = Path(self.temp.name) / 'rom'
        self.original = ';\u5b57\u5e55\n00:00:01\t\u65e5\u672c\u8a9e\nend\n'.encode(sub.ENCODING)
        self.editor = '00:00:01\t\uac00\nend\n'.encode('utf-8')
        table = {'replace-table': {'\uac00': '\u4e00'}}
        self.put(self.root / sub.TABLE, json.dumps(table).encode('utf-8'))
        for disc in (1, 2):
            rows = []
            for game in sub.game_paths(disc):
                self.put(self.destination(disc, game), self.original)
                self.put(self.root / f'{disc}.X3{disc}' / game, self.original)
                rows.append('00000000|00000000|00000000|\\' + str(game).replace('/', '\\'))
            self.put(self.rom / 'iso-data' / f'LBA{disc}.txt', '\n'.join(rows).encode('utf-8'))

    def put(self, path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def destination(self, disc, game):
        return self.rom / f'X3{disc}_UNPACKED' / game

    def editor_path(self, disc, game):
        return self.root / f'{disc}.X3{disc}' / game.parts[0] / 'kr' / game.name

    def prepare_editors(self, disc):
        for game in sub.game_paths(disc):
            self.put(self.editor_path(disc, game), self.editor)

    def snapshot(self, root):
        return {p.relative_to(root): p.read_bytes() for p in root.rglob('*') if p.is_file()}

    def test_decode_both_discs_and_repeat_preserves_edits(self):
        for disc, count in ((1, 48), (2, 33)):
            stats = sub.decode_batch(self.root, disc)
            self.assertEqual(stats, {'total': count, 'originals_decoded': count,
                                     'editors_created': count, 'kept_utf8': 0})
            for game in sub.game_paths(disc):
                self.assertEqual((self.root / f'{disc}.X3{disc}' / game).read_bytes(),
                                 sub.decode_game(self.original))
            first = sub.game_paths(disc)[0]
            self.put(self.editor_path(disc, first), b'\xef\xbb\xbf' + self.editor)
            before = self.snapshot(self.root)
            stats = sub.decode_batch(self.root, disc)
            self.assertEqual(stats['kept_utf8'], count)
            self.assertEqual(before, self.snapshot(self.root))

    def test_non_utf8_editor_is_not_overwritten(self):
        self.prepare_editors(1)
        path = self.editor_path(1, sub.game_paths(1)[-1])
        self.put(path, self.original)
        before = self.snapshot(self.root)
        with self.assertRaisesRegex(ValueError, 'Existing editor must be UTF-8'):
            sub.decode_batch(self.root, 1)
        self.assertEqual(before, self.snapshot(self.root))

    def test_utf8_original_creates_matching_editor(self):
        game = sub.game_paths(2)[0]
        original = self.root / '2.X32' / game
        utf8 = b'\xef\xbb\xbf' + sub.decode_game(self.original).replace(b'\n', b'\r\n')
        self.put(original, utf8)
        stats = sub.decode_batch(self.root, 2)
        self.assertEqual(stats['originals_decoded'], 32)
        self.assertEqual(original.read_bytes(), utf8)
        self.assertEqual(self.editor_path(2, game).read_bytes(), utf8)

    def test_bad_last_decode_prevents_all_writes(self):
        self.put(self.root / '2.X32' / sub.game_paths(2)[-1], b'\xff')
        before = self.snapshot(self.root)
        with self.assertRaises(ValueError):
            sub.decode_batch(self.root, 2)
        self.assertEqual(before, self.snapshot(self.root))

    def test_check_has_no_side_effects(self):
        before = self.snapshot(Path(self.temp.name))
        sub.decode_batch(self.root, 2, check=True)
        self.assertEqual(before, self.snapshot(Path(self.temp.name)))
        self.prepare_editors(1)
        before = self.snapshot(Path(self.temp.name))
        sub.encode_batch(self.root, 1, self.rom, check=True)
        self.assertEqual(before, self.snapshot(Path(self.temp.name)))

    def test_copy_goes_to_correct_disc_and_jp_with_no_local_outputs(self):
        self.prepare_editors(1)
        before = self.snapshot(self.root)
        other_disc = self.snapshot(self.rom / 'X32_UNPACKED')
        stats = sub.encode_batch(self.root, 1, self.rom)
        self.assertEqual(stats['changed'], 48)
        expected = sub.encode_editor(self.editor, {'\uac00': '\u4e00'})
        for game in sub.game_paths(1):
            self.assertEqual(self.destination(1, game).read_bytes(), expected)
        self.assertEqual(before, self.snapshot(self.root))
        self.assertEqual(other_disc, self.snapshot(self.rom / 'X32_UNPACKED'))
        self.assertFalse(list(self.rom.rglob('*.pending')))
        times = {p: p.stat().st_mtime_ns for p in self.rom.rglob('*.txt')}
        self.assertEqual(sub.encode_batch(self.root, 1, self.rom)['changed'], 0)
        self.assertEqual(times, {p: p.stat().st_mtime_ns for p in self.rom.rglob('*.txt')})

    def test_bad_last_editor_prevents_all_copying(self):
        self.prepare_editors(1)
        self.put(self.editor_path(1, sub.game_paths(1)[-1]), b'\xff')
        before = self.snapshot(self.rom)
        with self.assertRaises(ValueError):
            sub.encode_batch(self.root, 1, self.rom)
        self.assertEqual(before, self.snapshot(self.rom))

    def test_incomplete_editor_set_is_not_silently_skipped(self):
        game = sub.game_paths(1)[0]
        self.put(self.editor_path(1, game), self.editor)
        before = self.snapshot(self.rom)
        with self.assertRaises(FileNotFoundError):
            sub.encode_batch(self.root, 1, self.rom)
        self.assertEqual(before, self.snapshot(self.rom))

    def test_wrong_toc_prevents_all_copying(self):
        self.prepare_editors(1)
        self.put(self.rom / 'iso-data' / 'LBA1.txt', b'wrong index\n')
        before = self.snapshot(self.rom)
        with self.assertRaisesRegex(ValueError, 'not registered'):
            sub.encode_batch(self.root, 1, self.rom)
        self.assertEqual(before, self.snapshot(self.rom))

    def test_pending_file_prevents_all_copying(self):
        self.prepare_editors(2)
        target = self.destination(2, sub.game_paths(2)[-1])
        self.put(target.with_name(target.name + '.pending'), b'interrupted')
        before = self.snapshot(self.rom)
        with self.assertRaises(FileExistsError):
            sub.encode_batch(self.root, 2, self.rom)
        self.assertEqual(before, self.snapshot(self.rom))

    def test_disc2_copies_in_x31_are_rejected_before_copying(self):
        self.prepare_editors(1)
        legacy = self.root / '1.X31/evt/kr/s080600.txt'
        self.put(legacy, self.original)
        before = self.snapshot(self.rom)
        with self.assertRaisesRegex(ValueError, 'Unregistered editor'):
            sub.encode_batch(self.root, 1, self.rom)
        self.assertEqual(before, self.snapshot(self.rom))
        self.assertEqual(legacy.read_bytes(), self.original)

    def test_unknown_editor_is_reported(self):
        self.prepare_editors(2)
        self.put(self.root / '2.X32/evt/kr/s999999.txt', self.editor)
        with self.assertRaisesRegex(ValueError, 'Unregistered editor'):
            sub.encode_batch(self.root, 2, self.rom)

    def test_paths_cannot_escape_root(self):
        with self.assertRaises(ValueError):
            sub.inside(self.root, self.root / '..' / 'rom' / 'wrong.txt')

    def test_font_mapping_cannot_change_ascii_or_punctuation(self):
        for key in (';', 'A', '\u300c'):
            self.put(self.root / sub.TABLE, json.dumps({'replace-table': {key: '\u4e00'}}).encode())
            with self.assertRaises(ValueError):
                sub.load_table(self.root / sub.TABLE)


if __name__ == '__main__':
    unittest.main()
