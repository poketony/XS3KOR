"""Battle-label recovery and minigame string-table regression tests."""

import contextlib
import hashlib
import io
import json
import struct
import unittest
from pathlib import Path
from unittest.mock import patch

import build_menu
import build_minigame
from tools import njdbcommon_tool as common, njbtltext, minigame_text as message


HOME = Path(__file__).resolve().parents[1]


def render(entries):
    return ''.join(f'//[{index:04d}]\n{text}\n' for index, text in entries.items())


def raw_slots(data):
    base, _ = common.parse_header(data)
    offsets, _ = common.load_ptrs(data, base)
    return [data[address:data.index(b'\0', address)] for address in offsets]


class RemainingTextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        menu = json.loads((HOME / 'sources.json').read_text(encoding='utf-8'))
        cls.battle_asset = menu['assets']['njBtlText']
        cls.battle = (HOME / cls.battle_asset['original']).read_bytes()
        cls.battle_patch = (HOME / cls.battle_asset['binary_patch_reference']).read_bytes()
        cls.battle_editor = (HOME / cls.battle_asset['edit']).read_text(encoding='utf-8-sig')
        cls.manifest = json.loads((HOME / 'minigame_sources.json').read_text(encoding='utf-8'))
        cls.messages = (HOME / cls.manifest['original']).read_bytes()
        cls.editor = message.extract_text(cls.messages)
        cls.table = json.loads((HOME / 'XENOSAGA KOR-JPN.json').read_text(encoding='utf-8-sig'))['replace-table']

    def test_source_and_binary_patch_hashes(self):
        self.assertEqual(hashlib.sha256(self.battle).hexdigest(), self.battle_asset['original_sha256'])
        self.assertEqual(hashlib.sha256(self.battle_patch).hexdigest(), self.battle_asset['binary_patch_sha256'])
        self.assertEqual(hashlib.sha256(self.messages).hexdigest(), self.manifest['original_sha256'])

    def test_battle_unmodified_roundtrip(self):
        self.assertEqual(njbtltext.rebuild(self.battle, njbtltext.extract_text(self.battle), self.table), self.battle)
        self.assertEqual(len(njbtltext.read_slots(self.battle)[2]), 51)

    def test_battle_recovery_reproduces_existing_binary_exactly(self):
        result = njbtltext.rebuild(self.battle, self.battle_editor, self.table)
        self.assertEqual(result, self.battle_patch)
        self.assertEqual(len(result), 522)
        recovered = self.battle_asset['recovered_translations']
        self.assertEqual([entry['id'] for entry in recovered], [40, 41, 42, 44, 45, 46, 47, 48])
        entries = common.parse_text(self.battle_editor, 51)
        for entry in recovered:
            self.assertEqual(entries[entry['id']], entry['ko'])
        self.assertEqual(sum(a != b for a, b in zip(raw_slots(self.battle), raw_slots(result))), 8)

    def test_battle_shorter_or_empty_changes_only_one_slot(self):
        original_entries = common.parse_text(njbtltext.extract_text(self.battle), 51)
        slot = njbtltext.read_slots(self.battle)[2][40]
        for value in ('', 'TEST'):
            entries = dict(original_entries)
            entries[40] = value
            result = njbtltext.rebuild(self.battle, render(entries), self.table)
            expected = bytearray(self.battle)
            expected[slot['address']:slot['limit']] = value.encode().ljust(slot['limit'] - slot['address'], b'\0')
            self.assertEqual(result, expected)

    def test_battle_growing_label_uses_valid_repacked_container(self):
        entries = common.parse_text(self.battle_editor, 51)
        entries[40] = '<LONG LABEL>' * 100
        result = njbtltext.rebuild(self.battle, render(entries), self.table)
        self.assertGreater(len(result), len(self.battle))
        self.assertEqual(result[:8], self.battle[:8])
        self.assertEqual(result[12:16], self.battle[12:16])
        self.assertEqual(16 + struct.unpack_from('<I', result, 8)[0], len(result))
        for index, raw in enumerate(raw_slots(result)):
            self.assertEqual(raw, ''.join(self.table.get(c, c) for c in entries[index]).encode('euc_jis_2004'))

    def test_battle_reordered_editor_is_equivalent(self):
        entries = common.parse_text(self.battle_editor, 51)
        content = render(dict(reversed(list(entries.items()))))
        self.assertEqual(njbtltext.rebuild(self.battle, content, self.table), self.battle_patch)

    def test_battle_bad_ids_and_unencodable_text_fail(self):
        entries = common.parse_text(self.battle_editor, 51)
        cases = [render({k: v for k, v in entries.items() if k != 0}),
                 self.battle_editor + '//[0]\nBAD\n', self.battle_editor + '//[51]\nBAD\n']
        for value in ('\0', '\U0001f9ea', '\u2014'):
            cases.append(render({**entries, 0: value}))
        for text in cases:
            with self.assertRaises((ValueError, UnicodeError)):
                njbtltext.rebuild(self.battle, text, self.table)

    def test_battle_corrupt_slots_fail(self):
        cases = [self.battle[:10]]
        data = bytearray(self.battle)
        struct.pack_into('<I', data, 20, 205)
        cases.append(data)
        data = bytearray(self.battle_patch)
        data[0x1da] = 65  # Nonzero data after the shortened BOOST label's NUL.
        cases.append(data)
        data = bytearray(self.battle)
        data[0x1c8] = 0xff
        cases.append(data)
        for data in cases:
            with self.assertRaises((ValueError, UnicodeError)):
                njbtltext.read_slots(data)

    def test_message_original_editor_and_roundtrip(self):
        self.assertEqual(message.rebuild(self.messages, self.editor, self.table), self.messages)
        self.assertEqual(len(self.messages), 31483)

    def test_message_independent_pointer_and_string_walk(self):
        slots = struct.unpack_from('<1024H', self.messages)
        self.assertEqual(slots[0], 0)
        self.assertEqual(slots.count(0), 154)
        self.assertEqual(slots[871:], (0,) * 153)
        cursor = 2048
        for relative in slots[:871]:
            self.assertEqual(cursor, 2048 + relative)
            cursor = self.messages.index(b'\0', cursor) + 1
        self.assertEqual(cursor, len(self.messages))
        rows = message.read_rows(self.messages)
        self.assertEqual(len(rows), 871)
        self.assertEqual(sum(len(row['refs']) for row in rows), 1024)
        self.assertEqual(len(rows[0]['refs']), 154)

    def test_message_growing_first_string_preserves_all_zero_refs(self):
        entries = common.parse_text(self.editor, 871)
        entries[0] = 'GROW' * 300
        result = message.rebuild(self.messages, render(entries), self.table)
        refs = struct.unpack_from('<1024H', result)
        self.assertEqual(refs[0], 0)
        self.assertEqual(refs[871:], (0,) * 153)
        self.assertEqual(result[2048:result.index(b'\0', 2048)], entries[0].encode())
        self.assertEqual([row['refs'] for row in message.read_rows(result)],
                         [row['refs'] for row in message.read_rows(self.messages)])

    def test_message_multiple_edits_preserve_every_other_string(self):
        entries = common.parse_text(self.editor, 871)
        entries[0] = ''
        entries[42] = '\uacf5\uaca9'
        entries[800] = 'NEW CONTENT'
        result = message.rebuild(self.messages, render(entries), self.table)
        rows = message.read_rows(result)
        for row in rows:
            expected = ''.join(self.table.get(c, c) for c in entries[row['index']]).encode('euc_jis_2004')
            self.assertEqual(row['raw'], expected)
        for old, new in zip(message.read_rows(self.messages), rows):
            if old['index'] not in (0, 42, 800):
                self.assertEqual(old['raw'], new['raw'])

    def test_message_identical_text_stays_distinct_records(self):
        entries = common.parse_text(self.editor, 871)
        entries[0], entries[1] = 'SAME', 'SAME'
        result = message.rebuild(self.messages, render(entries), self.table)
        rows = message.read_rows(result)
        self.assertEqual(len(rows), 871)
        self.assertEqual(rows[0]['raw'], rows[1]['raw'])
        self.assertNotEqual(rows[0]['relative'], rows[1]['relative'])

    def test_message_controls_spaces_and_physical_lf_preserved(self):
        entries = common.parse_text(self.editor, 871)
        value = '  <R1> $rubyb;A$rubys;B$rubye;\\n[n]\n\n  '
        entries[1] = value
        result = message.rebuild(self.messages, render(entries), self.table)
        self.assertEqual(message.read_rows(result)[1]['raw'], value.encode())
        self.assertEqual(common.parse_text(message.extract_text(result), 871)[1], value)

    def test_message_reordered_editor_is_equivalent(self):
        entries = common.parse_text(self.editor, 871)
        self.assertEqual(message.rebuild(self.messages, render(dict(reversed(list(entries.items())))), self.table), self.messages)

    def test_message_signed_pointer_boundary(self):
        rows = message.read_rows(self.messages)
        entries = common.parse_text(self.editor, 871)
        extra = 32767 - rows[-1]['relative']
        entries[0] = 'X' * (len(rows[0]['raw']) + extra)
        result = message.rebuild(self.messages, render(entries), self.table)
        self.assertEqual(struct.unpack_from('<h', result, 870 * 2)[0], 32767)
        self.assertEqual(message.read_rows(result)[-1]['text'], rows[-1]['text'])
        entries[0] += 'X'
        with self.assertRaisesRegex(ValueError, 'signed int16'):
            message.rebuild(self.messages, render(entries), self.table)

    def test_message_last_string_can_cross_signed_offset_boundary(self):
        entries = common.parse_text(self.editor, 871)
        rows = message.read_rows(self.messages)
        entries[870] = 'X' * (65536 - rows[-1]['relative'] - 1)
        result = message.rebuild(self.messages, render(entries), self.table)
        self.assertEqual(len(result), 2048 + 65536)
        self.assertEqual(message.read_rows(result)[-1]['text'], entries[870])
        entries[870] += 'X'
        with self.assertRaisesRegex(ValueError, 'uint16'):
            message.rebuild(self.messages, render(entries), self.table)

    def test_message_stage_name_copy_buffer_boundary(self):
        entries = common.parse_text(self.editor, 871)
        for index in (99, 178, 179, 188, 189, 198):
            with self.subTest(index=index):
                for value in ('X' * 26, '\uacf5' * 13):
                    result = message.rebuild(self.messages, render({**entries, index: value}), self.table)
                    self.assertEqual(len(message.read_rows(result)[index]['raw']), 26)
                for value in ('X' * 27, '\uacf5' * 14):
                    with self.assertRaisesRegex(ValueError, 'stage name exceeds'):
                        message.rebuild(self.messages, render({**entries, index: value}), self.table)

    def test_message_non_stage_rows_do_not_use_stage_limit(self):
        entries = common.parse_text(self.editor, 871)
        for index in (98, 199):
            result = message.rebuild(self.messages, render({**entries, index: 'X' * 27}), self.table)
            self.assertEqual(message.read_rows(result)[index]['raw'], b'X' * 27)

    def test_message_negative_source_pointer_is_rejected(self):
        data = bytearray(self.messages)
        struct.pack_into('<H', data, 870 * 2, 0x8000)
        with self.assertRaisesRegex(ValueError, 'signed int16'):
            message.read_rows(data)

    def test_message_missing_duplicate_and_unknown_ids_fail(self):
        entries = common.parse_text(self.editor, 871)
        cases = [render({k: v for k, v in entries.items() if k != 870}),
                 self.editor + '//[1]\nBAD\n', self.editor + '//[871]\nBAD\n']
        for content in cases:
            with self.assertRaises(ValueError):
                message.rebuild(self.messages, content, self.table)

    def test_message_unencodable_or_nul_fails(self):
        entries = common.parse_text(self.editor, 871)
        for value in ('\0', '\U0001f9ea', '\u2014'):
            with self.assertRaises((ValueError, UnicodeError)):
                message.rebuild(self.messages, render({**entries, 870: value}), self.table)

    def test_message_corrupt_original_fails(self):
        cases = [self.messages[:2048], self.messages[:-1], self.messages + b'BAD']
        for position, value in ((0, 1), (2, 0), (2, 65535), (1742, 39)):
            data = bytearray(self.messages)
            struct.pack_into('<H', data, position, value)
            cases.append(data)
        data = bytearray(self.messages)
        data[2048] = 0xff
        cases.append(data)
        for data in cases:
            with self.assertRaises((ValueError, UnicodeError)):
                message.read_rows(data)

    def test_builders_check_without_publishing(self):
        for builder, args in ((build_minigame, ['--check']), (build_menu, ['--asset', 'njBtlText', '--check'])):
            with patch.object(builder, 'write_output') as save, contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(builder.main(args), 0)
                save.assert_not_called()

    def test_message_late_bad_input_publishes_nothing(self):
        entries = common.parse_text(self.editor, 871)
        entries[870] = '\U0001f9ea'
        real_read = Path.read_text
        bad_path = (HOME / self.manifest['edit']).resolve()
        def damaged(path, *args, **kwargs):
            return render(entries) if path == bad_path else real_read(path, *args, **kwargs)
        with patch.object(Path, 'read_text', damaged), patch.object(build_minigame, 'write_output') as save:
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(build_minigame.main([]), 1)
            save.assert_not_called()

    def test_message_source_hash_failure_publishes_nothing(self):
        real_read = Path.read_bytes
        bad_path = (HOME / self.manifest['original']).resolve()
        def damaged(path):
            data = real_read(path)
            return data + b'BAD' if path == bad_path else data
        with patch.object(Path, 'read_bytes', damaged), patch.object(build_minigame, 'write_output') as save:
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(build_minigame.main([]), 1)
            save.assert_not_called()

    def test_message_pending_write_failure_returns_failure(self):
        with patch.object(build_minigame, 'write_output', side_effect=FileExistsError('pending')):
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(build_minigame.main([]), 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
