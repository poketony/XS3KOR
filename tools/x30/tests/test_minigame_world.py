"""Fixed World.Dat names, canonical editor selection and output safety."""

import contextlib
import hashlib
import io
import json
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import build_minigame
from build_menu import HOME
from tools import minigame_world as world, njdbcommon_tool as common


def render(entries):
    return ''.join(f'//[{index:04d}]\n{text}\n' for index, text in entries.items())


class MinigameWorldTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((HOME / 'world_sources.json').read_text(encoding='utf-8'))
        cls.original = (HOME / cls.manifest['original']).read_bytes()
        cls.editor = world.extract_text(cls.original)
        cls.table = json.loads((HOME / 'XENOSAGA KOR-JPN.json').read_text(encoding='utf-8-sig'))['replace-table']
        cls.entries = common.parse_text(cls.editor, 10)
        cls.working = (HOME / cls.manifest['edit']).resolve()

    def test_source_hash_and_roundtrip(self):
        self.assertEqual(hashlib.sha256(self.original).hexdigest(), self.manifest['original_sha256'])
        self.assertEqual(len(self.original), 1656)
        self.assertEqual(len(world.read_rows(self.original)), 10)
        self.assertEqual(world.rebuild(self.original, self.editor, self.table), self.original)

    def test_slot_offsets_are_independently_walked(self):
        for index, row in enumerate(world.read_rows(self.original)):
            offset = 56 + index * 32
            stop = self.original.index(b'\0', offset, offset + 32)
            self.assertEqual(row['address'], offset)
            self.assertEqual(row['raw'], self.original[offset:stop])

    def test_only_selected_name_slot_changes(self):
        value = '\uacf5\uaca9[TEST]'
        for index in range(10):
            result = world.rebuild(self.original, render({**self.entries, index: value}), self.table)
            expected = bytearray(self.original)
            offset = 56 + 32 * index
            raw = ''.join(self.table.get(c, c) for c in value).encode('euc_jis_2004')
            expected[offset:offset + 32] = raw.ljust(32, b'\0')
            self.assertEqual(result, expected)
            self.assertEqual(result[:56], self.original[:56])
            self.assertEqual(result[0x178:], self.original[0x178:])

    def test_encoded_name_length_boundary(self):
        for value in ('X' * 31, '\uacf5' * 15 + 'X'):
            result = world.rebuild(self.original, render({**self.entries, 0: value}), self.table)
            self.assertEqual(len(world.read_rows(result)[0]['raw']), 31)
        for value in ('X' * 32, '\uacf5' * 16, ''):
            with self.assertRaisesRegex(ValueError, '1-31 encoded bytes'):
                world.rebuild(self.original, render({**self.entries, 0: value}), self.table)

    def test_bad_ids_and_encoding_fail(self):
        cases = [render({k: v for k, v in self.entries.items() if k != 9}),
                 self.editor + '//[0]\nBAD\n', self.editor + '//[10]\nBAD\n']
        cases += [render({**self.entries, 0: value}) for value in ('\0', '\U0001f9ea', '\u2014')]
        for content in cases:
            with self.assertRaises((ValueError, UnicodeError)):
                world.rebuild(self.original, content, self.table)

    def test_reordered_ids_preserve_original(self):
        content = render(dict(reversed(list(self.entries.items()))))
        self.assertEqual(world.rebuild(self.original, content, self.table), self.original)

    def test_bad_source_fails(self):
        cases = [self.original[:-1], self.original + b'X', b'']
        data = bytearray(self.original)
        struct.pack_into('<H', data, 0, 9)
        cases.append(data)
        for slot in (b'X' * 32, b'\0' * 32, b'\xff\0' + b'\0' * 30):
            data = bytearray(self.original)
            data[56:88] = slot
            cases.append(data)
        for data in cases:
            with self.assertRaises((ValueError, UnicodeError)):
                world.read_rows(data)

    def test_unchanged_slot_preserves_bytes_after_nul(self):
        data = bytearray(self.original)
        data[87] = 0x55
        self.assertEqual(world.rebuild(data, world.extract_text(data), self.table), data)

    def test_default_and_explicit_use_same_canonical_editor(self):
        result = build_minigame.prepare(asset='World.Dat')
        self.assertEqual(result[2][1], self.working)
        self.assertEqual(result, build_minigame.prepare(self.working, 'World.Dat'))
        self.assertFalse((HOME / 'edit/World.Dat.txt').exists())
        with self.assertRaises(FileNotFoundError):
            build_minigame.prepare(HOME / '__missing_world__.txt', 'World.Dat')

    def test_dropped_edit_is_used_without_modifying_input(self):
        with tempfile.TemporaryDirectory(dir=HOME) as folder:
            path = Path(folder) / 'world with spaces & \uD55C\uAE00.txt'
            path.write_text(render({**self.entries, 4: 'DROP WORLD'}), encoding='utf-8')
            before = path.read_bytes()
            result = build_minigame.prepare(path, 'World.Dat')
            self.assertEqual(world.read_rows(result[1])[4]['text'], 'DROP WORLD')
            self.assertEqual(path.read_bytes(), before)

    def test_check_does_not_publish(self):
        with patch.object(build_minigame, 'write_output') as write, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(build_minigame.main(['--asset', 'World.Dat', '--check']), 0)
        write.assert_not_called()

    def test_bad_late_name_does_not_publish(self):
        read = Path.read_text
        def damaged(path, *args, **kwargs):
            return render({**self.entries, 9: 'X' * 32}) if path == self.working else read(path, *args, **kwargs)
        with patch.object(Path, 'read_text', damaged), patch.object(build_minigame, 'write_output') as write:
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(build_minigame.main(['--asset', 'World.Dat']), 1)
        write.assert_not_called()


if __name__ == '__main__':
    unittest.main()
