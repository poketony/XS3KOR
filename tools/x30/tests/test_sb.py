"""SB corpus and failure-path regression tests, without writing test outputs."""

import contextlib
import hashlib
import io
import json
import struct
import unittest
from pathlib import Path
from unittest.mock import patch

import build_sb
from tools import sb_text as sb


HOME = Path(__file__).resolve().parents[1]


def u32(data, offset):
    return struct.unpack_from('<I', data, offset)[0]


def nul(data, offset):
    return data[offset:data.index(b'\0', offset)]


def render(entries):
    return ''.join(f'[{address:#x}]\n' + value.replace('\n', '[n]') + '\n\n'
                   for address, value in entries.items())


class SBTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((HOME / 'sb_sources.json').read_text(encoding='utf-8'))
        cls.assets = cls.manifest['assets']
        cls.table = json.loads((HOME / 'XENOSAGA KOR-JPN.json').read_text(encoding='utf-8-sig'))['replace-table']

    def source(self, name='cf/8050'):
        return (HOME / self.assets[name]['original']).read_bytes()

    def editor(self, name='cf/8050'):
        content = (HOME / self.assets[name]['edit']).read_text(encoding='utf-8-sig')
        restored = next((r for r in self.manifest['restored_first_rows'] if r['asset'] == name), None)
        return build_sb.normalize_editor(self.source(name), content, restored)

    def test_verified_originals_and_complete_corpus_roundtrip(self):
        self.assertEqual(len(self.assets), 856)
        count = 0
        for name, asset in self.assets.items():
            with self.subTest(name=name):
                data = self.source(name)
                self.assertEqual(hashlib.sha256(data).hexdigest(), asset['original_sha256'])
                rows = sb.read_rows(data)
                count += len(rows)
                self.assertEqual(len(rows), asset['strings'])
                self.assertEqual(sb.rebuild(data, sb.extract_text(data), self.table), data)
        self.assertEqual(count, 108040)

    def test_independent_pool_walk_matches_all_header_references(self):
        for name in self.assets:
            with self.subTest(name=name):
                data = self.source(name)
                section, end = u32(data, 16), u32(data, 20)
                count = u32(data, section + 4)
                base = section + 8 + 4 * count
                cursor, walked = base, []
                for index in range(count):
                    walked.append(cursor)
                    self.assertEqual(cursor, base + u32(data, section + 8 + 4 * index))
                    cursor = data.index(b'\0', cursor, end) + 1
                self.assertEqual(walked, [row['address'] for row in sb.read_rows(data)])
                self.assertEqual(data[cursor:end], b'\0' * (end - cursor))

    def test_recovered_first_dialogue_in_38_editors(self):
        restored = self.manifest['restored_first_rows']
        self.assertEqual(len(restored), 38)
        for entry in restored:
            with self.subTest(name=entry['asset']):
                first = sb.read_rows(self.source(entry['asset']))[0]
                self.assertTrue(first['editable'])
                self.assertEqual(hex(first['address']), entry['address'])
                self.assertEqual(sb.editor_entries(self.source(entry['asset']),
                                                   self.editor(entry['asset']))[first['address']], first['text'])
                self.assertEqual(first['text'], entry['text'])

    def test_first_zero_offset_is_a_string_not_a_sentinel(self):
        name = self.manifest['restored_first_rows'][0]['asset']
        data = self.source(name)
        first = sb.read_rows(data)[0]
        for value in ('', 'X', 'LONG' * 100):
            entries = sb.parse_text(sb.extract_text(data, bilingual=False))
            entries[first['address']] = value
            result = sb.rebuild(data, render(entries), self.table)
            address = first['base'] + u32(result, first['ptr_pos'])
            self.assertEqual(nul(result, address), value.encode())

    def test_empty_table_and_missing_editor_sources(self):
        data = self.source('cf/3810')
        self.assertEqual(sb.read_rows(data), [])
        self.assertEqual(sb.extract_text(data), '')
        self.assertEqual(sb.rebuild(data, '', self.table), data)
        self.assertEqual(sum('edit' not in asset for asset in self.assets.values()), 41)

    def test_no_marker_search_dependency(self):
        data = bytearray(self.source())
        first = sb.read_rows(data)[0]
        data[first['address']:first['address'] + 7] = b'not_seg'
        self.assertNotIn(b'seg_now', data)
        self.assertEqual(sb.rebuild(data, sb.extract_text(data), self.table), data)

    def test_internal_first_label_is_preserved_and_not_editable(self):
        for name in ('cf/8050', 'bat/REN_B01'):
            data = self.source(name)
            first = sb.read_rows(data)[0]
            self.assertFalse(first['editable'])
            content = sb.extract_text(data)
            self.assertNotIn(first['address'], sb.parse_bilingual(content)[0])
            with self.assertRaisesRegex(ValueError, 'unknown'):
                sb.rebuild(data, content +
                           f'\n[{first["address"]:#x}]\n[JPN]\n{first["text"]}\n[KOR]\nEDIT\n',
                           self.table)

    def test_order_does_not_change_build(self):
        for name in ('cf/8050', 'bat/REN_B01'):
            content = self.editor(name)
            data = self.source(name)
            entries = sb.editor_entries(data, content)
            reverse = sb.render_bilingual(reversed(sb.read_rows(data)), entries)
            self.assertEqual(sb.rebuild(data, reverse, self.table),
                             sb.rebuild(self.source(name), content, self.table))

    def test_shortening_and_empty_change_only_original_slot(self):
        data = self.source()
        row = sb.read_rows(data)[1]
        for value in ('', 'TEST', row['text'][:3]):
            entries = sb.parse_text(sb.extract_text(data, bilingual=False))
            entries[row['address']] = value
            result = sb.rebuild(data, render(entries), self.table)
            expected = bytearray(data)
            expected[row['address']:row['address'] + len(row['raw'])] = value.encode(sb.ENCODING).ljust(len(row['raw']), b'\0')
            self.assertEqual(result, expected)

    def test_growth_updates_only_actual_table_slot(self):
        data = bytearray(self.source())
        row = sb.read_rows(data)[1]
        # A reserved numeric field deliberately equals the old relative pointer.
        struct.pack_into('<I', data, 32, row['address'] - row['base'])
        entries = sb.parse_text(sb.extract_text(data, bilingual=False))
        raw = b'<LONG>' * 100
        entries[row['address']] = raw.decode()
        result = sb.rebuild(data, render(entries), self.table)
        expected = bytearray(data)
        struct.pack_into('<I', expected, row['ptr_pos'], len(data) - row['base'])
        expected.extend(raw + b'\0')
        self.assertEqual(result, expected)
        self.assertEqual(result[32:36], data[32:36])

    def test_whitespace_punctuation_and_newline_conventions(self):
        data = self.source()
        entries = sb.parse_text(sb.extract_text(data, bilingual=False))
        row = sb.read_rows(data)[1]
        value = '  <f> "TEST" \\n\n\n <c>  '
        entries[row['address']] = value
        result = sb.rebuild(data, render(entries), self.table)
        self.assertEqual(nul(result, row['base'] + u32(result, row['ptr_pos'])), value.encode())
        self.assertEqual(sb.parse_text('[0x1]\n  \n\n'), {1: '  '})
        self.assertEqual(sb.parse_text('\ufeff[0x1]\r\nX\r\n[0x2]\r\nY'), {1: 'X', 2: 'Y'})

    def test_bad_or_incomplete_address_sets_are_rejected(self):
        data = self.source()
        entries = sb.parse_text(sb.extract_text(data, bilingual=False))
        first = next(iter(entries))
        missing = dict(entries)
        missing.pop(first)
        wrong = dict(missing)
        wrong[0xffffffff] = 'X'
        cases = [render(missing), render(wrong), render(entries) + f'[{first:#x}]\nX\n',
                 render(entries) + 'unexpected\n', f'[{first:#x}]\n[0x1]\nX\n',
                 render(entries).replace(f'[{first:#x}]', '[not an address]', 1)]
        for content in cases:
            with self.subTest(content=content[:60]), self.assertRaises(ValueError):
                sb.rebuild(data, content, self.table)

    def test_encoding_nul_and_ambiguous_physical_lines_fail(self):
        data = self.source()
        entries = sb.parse_text(sb.extract_text(data, bilingual=False))
        first = next(iter(entries))
        for value in ('\U0001f9ea', '\u2014', '\0', 'X\rY'):
            changed = dict(entries)
            changed[first] = value
            with self.subTest(value=ascii(value)), self.assertRaises(ValueError):
                sb.rebuild(data, render(changed), self.table)
        with self.assertRaises(ValueError):
            sb.parse_text('[0x1]\nfirst\nsecond\n\n')
        with self.assertRaises(ValueError):
            sb.rebuild(data, render({**entries, first: 'X'}), {'X': '\0'})

    def test_bilingual_blank_whitespace_and_missing_kor_preserve_original(self):
        data = self.source()
        content = sb.extract_text(data)
        self.assertTrue(content.startswith(sb.BILINGUAL_HEADER + '\n'))
        self.assertEqual(sb.rebuild(data, content, self.table), data)
        self.assertEqual(sb.rebuild(data, content.replace('[KOR]\n\n', '[KOR]\n   \n', 1),
                                    self.table), data)
        self.assertEqual(sb.rebuild(data, content.replace('[KOR]\n\n', '', 1),
                                    self.table), data)

    def test_bilingual_translation_controls_and_literal_escape(self):
        data = self.source()
        rows = sb.read_rows(data)
        row = next(item for item in rows if item['editable'])
        content = sb.render_bilingual(rows, {row['address']: r'A[n]B\nC'})
        result = sb.rebuild(data, content, self.table)
        address = row['base'] + u32(result, row['ptr_pos'])
        self.assertEqual(nul(result, address), b'A\nB\\nC')

    def test_bilingual_jpn_and_structure_are_strict(self):
        data = self.source()
        content = sb.extract_text(data)
        rows = [row for row in sb.read_rows(data) if row['editable']]
        tag = f'[{rows[0]["address"]:#x}]'
        broken = (
            content.replace('[JPN]\n', '[JPN]\nBROKEN', 1),
            content.replace(tag, '[0xffffffff]', 1),
            content + '\n' + content[content.find(tag):],
            content.replace('[KOR]\n\n', '[KOR]\nline one\nline two\n', 1),
            content.replace(sb.BILINGUAL_HEADER, '# SB-TEXT: JPN-KOR v2', 1),
        )
        for value in broken:
            with self.subTest(value=value[:80]), self.assertRaises(ValueError):
                sb.rebuild(data, value, self.table)

    def test_corrupt_binary_fails_before_rebuild(self):
        source = self.source()
        row = sb.read_rows(source)[1]
        cases = [source[:30], b'BAD!' + source[4:]]
        for offset, value in ((8, 0), (16, len(source)), (u32(source, 16), 9),
                              (u32(source, 16) + 4, 0xffffffff), (row['ptr_pos'], 0xffffffff),
                              (row['ptr_pos'], 1)):
            data = bytearray(source)
            struct.pack_into('<I', data, offset, value)
            cases.append(data)
        data = bytearray(source)
        data[row['address']] = 0xff
        cases.append(data)
        for data in cases:
            with self.subTest(header=bytes(data[:32]).hex()), self.assertRaises((ValueError, UnicodeError)):
                sb.read_rows(data)

    def test_current_build_all_strings_and_untouched_regions(self):
        results = build_sb.prepare()
        self.assertEqual(len(results), 815)
        checked = 0
        for name, _, result, _ in results:
            with self.subTest(name=name):
                data = self.source(name)
                entries = sb.editor_entries(data, self.editor(name))
                allowed = []
                for row in sb.read_rows(data):
                    address = row['base'] + u32(result, row['ptr_pos'])
                    if row['editable']:
                        expected = ''.join(self.table.get(c, c) for c in entries[row['address']]).encode(sb.ENCODING)
                    else:
                        expected = row['raw']
                    self.assertEqual(nul(result, address), expected)
                    checked += 1
                    allowed.extend(((row['address'], row['address'] + len(row['raw'])),
                                    (row['ptr_pos'], row['ptr_pos'] + 4)))
                cursor = 0
                for start, end in sorted(allowed):
                    self.assertEqual(result[cursor:start], data[cursor:start])
                    cursor = end
                self.assertEqual(result[cursor:len(data)], data[cursor:])
        self.assertEqual(checked, 107840)

    def test_selecting_group_or_asset(self):
        self.assertEqual(len(build_sb.prepare(group='bat')), 29)
        self.assertEqual(len(build_sb.prepare(asset_name='cf/8050')), 1)
        for name in ('cf/3810', 'bat/batle_bg', '../8050'):
            with self.assertRaises(ValueError):
                build_sb.prepare(asset_name=name)

    def test_late_invalid_editor_publishes_nothing(self):
        real_read = Path.read_text
        bad_path = (HOME / self.assets['cf/9248']['edit']).resolve()
        def damaged(path, *args, **kwargs):
            text = real_read(path, *args, **kwargs)
            if path == bad_path:
                data = self.source('cf/9248')
                entries = sb.editor_entries(data, text)
                entries[next(iter(entries))] = '\U0001f9ea'
                return sb.render_bilingual(sb.read_rows(data), entries)
            return text
        with patch.object(Path, 'read_text', damaged), patch.object(build_sb, 'write_output') as save:
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(build_sb.main([]), 1)
            save.assert_not_called()

    def test_source_hash_failure_publishes_nothing(self):
        real_read = Path.read_bytes
        bad_path = (HOME / self.assets['cf/8050']['original']).resolve()
        def damaged(path):
            data = real_read(path)
            return data + b'BAD' if path == bad_path else data
        with patch.object(Path, 'read_bytes', damaged), patch.object(build_sb, 'write_output') as save:
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(build_sb.main(['--asset', 'cf/8050']), 1)
            save.assert_not_called()

    def test_check_mode_does_not_publish(self):
        with patch.object(build_sb, 'write_output') as save, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(build_sb.main(['--asset', 'cf/8050', '--check']), 0)
            save.assert_not_called()

    def test_pending_output_blocks_before_any_publication(self):
        results = build_sb.prepare(group='bat')
        pending = results[-1][1].with_name(results[-1][1].name + '.pending')
        real_exists = Path.exists
        def exists(path):
            return path == pending or real_exists(path)
        with patch.object(build_sb, 'prepare', return_value=results), patch.object(Path, 'exists', exists):
            with patch.object(build_sb, 'write_output') as save, contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(build_sb.main(['--group', 'bat']), 1)
                save.assert_not_called()

    def test_duplicate_output_blocks_before_any_publication(self):
        results = build_sb.prepare(group='bat')
        results[-1] = (results[-1][0], results[0][1], results[-1][2], results[-1][3])
        with patch.object(build_sb, 'prepare', return_value=results):
            with patch.object(build_sb, 'write_output') as save, contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(build_sb.main(['--group', 'bat']), 1)
                save.assert_not_called()


if __name__ == '__main__':
    unittest.main(verbosity=2)
