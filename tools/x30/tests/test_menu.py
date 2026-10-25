"""Regression tests against local Japanese originals and existing Korean editors."""

import contextlib
import hashlib
import io
import json
import re
import struct
import unittest
from pathlib import Path
from unittest.mock import patch

import build_menu
from tools import njdatatexttool as nj, njdbcommon_tool as common
from tools import output
from tools.txd_tool import TXDTool


HOME = Path(__file__).resolve().parents[1]


def u32(data, offset):
    return struct.unpack_from('<I', data, offset)[0]


def nul(data, offset):
    return data[offset:data.index(b'\0', offset)]


class MenuTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((HOME / 'sources.json').read_text(encoding='utf-8'))
        cls.table = json.loads((HOME / 'XENOSAGA KOR-JPN.json').read_text(encoding='utf-8-sig'))['replace-table']
        cls.nj_data = (HOME.parents[1] / '0.X30/mnu/kr/njDataText.bin').read_bytes()
        cls.nj_text = nj.extract_text(cls.nj_data)
        cls.parser = TXDTool()

    def source(self, name):
        return (HOME / self.manifest['assets'][name]['original']).read_bytes()

    def replace_nj(self, text, address, replacement):
        lines = text.split('\n')
        matches = 0
        for i, line in enumerate(lines):
            match = nj.META_RE.fullmatch(line)
            if match and int(match[2], 16) == address:
                lines[i] = line.split('>>>', 1)[0] + '>>> ' + replacement
                matches += 1
        self.assertEqual(matches, 1)
        return '\n'.join(lines)

    def test_sources_and_editor_snapshots(self):
        for name in build_menu.NAMES:
            asset = self.manifest['assets'][name]
            with self.subTest(name=name):
                self.assertEqual(hashlib.sha256(self.source(name)).hexdigest(), asset['original_sha256'])
                # Deliberately do not freeze editors: they are the user's working inputs.
                self.assertTrue((HOME / asset['edit']).is_file())

    def test_txd_uses_canonical_editors_and_immutable_originals(self):
        filenames = ('devchk.txd_kor.txt', 'discchg.txd.kor.txt',
                     'menutext.txd_kor.txt', 'synopsis.txd_kor.txt')
        for name, filename in zip(build_menu.TXD_NAMES, filenames):
            with self.subTest(name=name):
                expected = HOME.parents[1] / '0.X30/mnu/kr' / filename
                self.assertEqual((HOME / self.manifest['assets'][name]['edit']).resolve(), expected)
                self.assertFalse((HOME / 'edit' / filename).exists())
                _, _, _, protected = build_menu.prepare((name,))[0]
                self.assertEqual(protected[1], expected)
                suffix = '.JPN.txd' if name == 'menutext' else '.txd'
                self.assertEqual(protected[0], HOME.parents[1] / '0.X30/mnu/kr' / (name + suffix))

    def test_txd_canonical_edit_changes_conversion(self):
        target = HOME.parents[1] / '0.X30/mnu/kr/devchk.txd_kor.txt'
        original_read = Path.read_text
        baseline = build_menu.prepare(('devchk',))[0][2]
        reads = []
        def read_edited(path, *args, **kwargs):
            reads.append(path.resolve())
            content = original_read(path, *args, **kwargs)
            if path.resolve() == target:
                # Simulate a user edit without writing to the real translation.
                content = re.sub(r'(?m)^(\[\d+\]).*$', r'\1CANONICAL TEST', content, count=1)
            return content
        with patch.object(Path, 'read_text', read_edited):
            changed = build_menu.prepare(('devchk',))[0][2]
        self.assertIn(target, reads)
        self.assertNotEqual(changed, baseline)
        self.assertIn(b'CANONICAL TEST', changed)

    def test_txd_missing_canonical_editor_fails_without_fallback(self):
        target = HOME.parents[1] / '0.X30/mnu/kr/devchk.txd_kor.txt'
        original_read = Path.read_text
        def missing_editor(path, *args, **kwargs):
            if path.resolve() == target:
                raise FileNotFoundError(target)
            return original_read(path, *args, **kwargs)
        with patch.object(Path, 'read_text', missing_editor), self.assertRaises(FileNotFoundError):
            build_menu.prepare(('devchk',))

    def test_editor_path_allowlist_does_not_expand_output_paths(self):
        for filename in build_menu.MENU_EDIT_FILES:
            relative = '../../0.X30/mnu/kr/' + filename
            self.assertEqual(build_menu.input_path(relative), (HOME / relative).resolve())
            with self.assertRaises(ValueError):
                build_menu.local_path(relative)
        for filename in ('devchk.txd', 'njDataText.bin', 'DBC.bin', 'menutext.JPN.txd', 'njBtlText.JPN.bin'):
            relative = '../../0.X30/mnu/kr/'+filename
            self.assertEqual(build_menu.input_path(relative), (HOME / relative).resolve())
            with self.assertRaises(ValueError):
                build_menu.local_path(relative)
        for relative in ('../../codex-lab/editor.txt',
                         '../../0.X30/mnu/kr/devchk/devchk.txd_kor.txt',
                         '../../0.X30/mnu/kr/devchk.txd.new', '../../0.X30/mnu/kr/unknown.bin',
                         '../../0.X30/mnu/kr/database/DBC.bin.KOR.txt',
                         '../../0.X30/mnu/kr/unknown.txt', '../../../outside.txt'):
            with self.subTest(path=relative), self.assertRaises(ValueError):
                build_menu.input_path(relative)

    def test_txd_menu_sita_preserves_legacy_space_rule(self):
        self.assertEqual(self.parser.encode_text('[menu_sita]A B@C', self.table),
                         'A、B@C'.encode('euc_jis_2004'))

    def test_discchg_loader_capacity_boundary_and_no_partial_output(self):
        source = self.source('discchg')
        content = re.sub(r'(?m)^\[1\].*$', '[1]', self.parser.extract_text(source))
        base_size = len(self.parser.rebuild(source, content, self.table))
        target = build_menu.input_path(self.manifest['assets']['discchg']['edit'])
        read = Path.read_text
        for extra in (0, 1):
            edited = content.replace('[1]\n', '[1]'+'A'*(1024-base_size+extra)+'\n')
            def read_edited(path, *args, **kwargs):
                return edited if path.resolve() == target else read(path, *args, **kwargs)
            with self.subTest(extra=extra), patch.object(Path, 'read_text', read_edited):
                if extra == 0:
                    self.assertEqual(len(build_menu.prepare(('discchg',))[0][2]), 1024)
                else:
                    with self.assertRaisesRegex(ValueError, '1024-byte'):
                        build_menu.prepare(('discchg',))
                    with patch.object(build_menu, 'write_output') as write, contextlib.redirect_stderr(io.StringIO()):
                        self.assertEqual(build_menu.main(['--asset', 'discchg']), 1)
                    write.assert_not_called()

    def test_bin_uses_canonical_editors_and_immutable_originals(self):
        for name in build_menu.DATASET_NAMES + ('njDBcommon', 'njBtlText'):
            with self.subTest(name=name):
                expected = HOME.parents[1] / '0.X30/mnu/kr' / (name + '.KOR.txt')
                self.assertEqual((HOME / self.manifest['assets'][name]['edit']).resolve(), expected)
                self.assertFalse((HOME / 'edit' / expected.name).exists())
                _, _, _, protected = build_menu.prepare((name,))[0]
                self.assertEqual(protected[1], expected)
                suffix = '.JPN.bin' if name == 'njBtlText' else '.bin'
                self.assertEqual(protected[0], HOME.parents[1] / '0.X30/mnu/kr' / (name + suffix))

    def test_menutext_resident_boundary_and_no_partial_output(self):
        source = self.source('menutext')
        content = self.parser.extract_text(source)
        base_size = len(self.parser.rebuild(source, content.replace('[1]', '[1]X', 1), self.table)) - 1
        target = build_menu.input_path(self.manifest['assets']['menutext']['edit'])
        read = Path.read_text
        for extra in (0, 1):
            edited = content.replace('[1]', '[1]'+'X'*(16384-base_size+extra), 1)
            def read_edited(path, *args, **kwargs):
                return edited if path.resolve() == target else read(path, *args, **kwargs)
            with self.subTest(extra=extra), patch.object(Path, 'read_text', read_edited):
                if extra == 0:
                    self.assertEqual(len(build_menu.prepare(('menutext',))[0][2]), 16384)
                else:
                    with self.assertRaisesRegex(ValueError, '16384-byte'):
                        build_menu.prepare(('menutext',))
                    with patch.object(build_menu, 'write_output') as write, contextlib.redirect_stderr(io.StringIO()):
                        self.assertEqual(build_menu.main([]), 1)
                    write.assert_not_called()

    def test_bin_canonical_edit_changes_conversion(self):
        original_read = Path.read_text
        for name in build_menu.DATASET_NAMES + ('njDBcommon', 'njBtlText'):
            target = HOME.parents[1] / '0.X30/mnu/kr' / (name + '.KOR.txt')
            baseline = build_menu.prepare((name,))[0][2]
            def read_edited(path, *args, **kwargs):
                content = original_read(path, *args, **kwargs)
                if path.resolve() == target:
                    if name in build_menu.DATASET_NAMES:
                        content = re.sub(r'(?m)(>>> ).*$', r'\g<1>CANONICAL TEST', content, count=1)
                    else:
                        content = re.sub(r'(//\[\d+\]\n)[^\n]*', r'\g<1>CANONICAL TEST', content, count=1)
                return content
            with self.subTest(name=name), patch.object(Path, 'read_text', read_edited):
                changed = build_menu.prepare((name,))[0][2]
                self.assertNotEqual(changed, baseline)
                self.assertIn(b'CANONICAL TEST', changed)

    def test_bin_missing_canonical_editor_fails_without_fallback(self):
        original_read = Path.read_text
        for name in build_menu.DATASET_NAMES + ('njDBcommon', 'njBtlText'):
            target = HOME.parents[1] / '0.X30/mnu/kr' / (name + '.KOR.txt')
            def missing_editor(path, *args, **kwargs):
                if path.resolve() == target:
                    raise FileNotFoundError(target)
                return original_read(path, *args, **kwargs)
            with self.subTest(name=name), patch.object(Path, 'read_text', missing_editor):
                with self.assertRaises(FileNotFoundError):
                    build_menu.prepare((name,))

    def test_nj_roundtrip_and_addresses(self):
        self.assertEqual(nj.rebuild(self.nj_data, self.nj_text, self.table), self.nj_data)
        records = nj.collect_strings(self.nj_data)
        self.assertEqual(len(records), 444)
        addresses = {r['abs_pos'] for r in records}
        self.assertFalse(addresses & {0x39d, 0x42d, 0x3f7})
        content = (HOME / self.manifest['assets']['njDataText']['edit']).read_text(encoding='utf-8-sig')
        editor_addresses = {int(nj.META_RE.fullmatch(line)[2], 16) for line in content.splitlines() if line}
        self.assertEqual(editor_addresses, addresses)

    def test_nj_short_edit_preserves_all_other_bytes(self):
        edited = self.replace_nj(self.nj_text, 0x124, 'TEST')
        result = nj.rebuild(self.nj_data, edited, self.table)
        expected = bytearray(self.nj_data)
        end = expected.index(b'\0', 0x124)
        expected[0x124:end] = b'TEST' + b'\0' * (end - 0x124 - 4)
        self.assertEqual(result, expected)

    def test_nj_empty_clears_string(self):
        result = nj.rebuild(self.nj_data, self.replace_nj(self.nj_text, 0x124, ''), self.table)
        self.assertEqual(nul(result, 0x124), b'')
        self.assertEqual(result[:0x124], self.nj_data[:0x124])

    def test_nj_growth_changes_only_known_refs(self):
        source = bytearray(self.nj_data)
        # A CHA scalar deliberately equals a relocated string's old relative pointer.
        struct.pack_into('<I', source, 0x2f8, 0xa0)
        text = nj.extract_text(source)
        long_text = 'LONG ' * 80
        result = nj.rebuild(source, self.replace_nj(text, 0x390, long_text), self.table)
        target = 0x2f0 + u32(result, 0x2f4)
        self.assertGreaterEqual(target, len(source))
        self.assertEqual(nul(result, target), long_text.encode())
        self.assertEqual(u32(result, 0x2f8), 0xa0)
        allowed = set(range(0x2f4, 0x2f8)) | set(range(0x390, 0x39c))
        self.assertTrue(all(a == b or i in allowed for i, (a, b) in enumerate(zip(source, result))))

    def test_nj_array_growth_updates_only_array_slot(self):
        record = next(r for r in nj.collect_strings(self.nj_data) if r['ds_idx'] == 12)
        long_text = 'ARRAY' * 80
        result = nj.rebuild(self.nj_data, self.replace_nj(self.nj_text, record['abs_pos'], long_text), self.table)
        ptr_pos = record['refs'][0]
        self.assertEqual(nul(result, record['ds_off'] + u32(result, ptr_pos)), long_text.encode())
        allowed = set(range(ptr_pos, ptr_pos+4)) | set(range(record['abs_pos'], record['abs_pos']+record['raw_size']))
        self.assertTrue(all(a == b or i in allowed for i, (a, b) in enumerate(zip(self.nj_data, result))))

    def test_nj_bad_input_rejected(self):
        first, rest = self.nj_text.split('\n', 1)
        cases = [rest, self.nj_text + first + '\n', self.nj_text.replace(':000124>>>', ':ffffff>>>', 1),
                 self.nj_text.replace('<<<0:', '<<<999:', 1), self.nj_text + 'bad line\n',
                 self.replace_nj(self.nj_text, 0x124, '\U0001f9ea'),
                 self.replace_nj(self.nj_text, 0x124, 'X\0Y')]
        for text in cases:
            with self.subTest(input=text[:70]):
                with self.assertRaises((ValueError, UnicodeError)):
                    nj.rebuild(self.nj_data, text, self.table)

    def test_nj_whitespace_punctuation_and_mapping(self):
        value = ' \uac00 <TEST> \\n '
        result = nj.rebuild(self.nj_data, self.replace_nj(self.nj_text, 0x124, value), self.table)
        target = 0x70 + u32(result, 0x74)
        expected = ''.join(self.table.get(c, c) for c in value).encode('euc_jis_2004')
        self.assertEqual(nul(result, target), expected)

    def test_nj_menu_sita_rule(self):
        self.assertEqual(nj.process_menu_sita('A B@C[menu_sita]'), 'A\u3001B C')

    def test_more_dataset_addresses_match_existing_editors(self):
        for name, count in (('MVtext', 276), ('SegmentFileData', 88)):
            with self.subTest(name=name):
                source = self.source(name)
                records = nj.collect_strings(source)
                self.assertEqual(len(records), count)
                self.assertEqual(nj.rebuild(source, nj.extract_text(source), self.table), source)
                content = (HOME / self.manifest['assets'][name]['edit']).read_text(encoding='utf-8-sig')
                addresses = {int(nj.META_RE.fullmatch(line)[2], 16) for line in content.splitlines() if line}
                self.assertEqual(addresses, {r['abs_pos'] for r in records})

    def test_more_dataset_growth_preserves_scalar_collision(self):
        for name, scalar_offset in (('MVtext', 4), ('SegmentFileData', 12)):
            with self.subTest(name=name):
                source = bytearray(self.source(name))
                record = nj.collect_strings(source)[0]
                scalar_pos = record['ds_off'] + scalar_offset
                original_pointer = record['abs_pos'] - record['ds_off']
                struct.pack_into('<I', source, scalar_pos, original_pointer)
                text = nj.extract_text(source)
                value = 'GROW' * (record['raw_size'] + 10)
                result = nj.rebuild(source, self.replace_nj(text, record['abs_pos'], value), self.table)
                self.assertEqual(u32(result, scalar_pos), original_pointer)
                allowed = set(range(record['abs_pos'], record['abs_pos']+record['raw_size']))
                for pointer in record['refs']:
                    allowed.update(range(pointer, pointer+4))
                    self.assertEqual(nul(result, record['ds_off']+u32(result, pointer)), value.encode())
                self.assertTrue(all(a == b or i in allowed for i, (a, b) in enumerate(zip(source, result))))

    def test_more_dataset_empty_and_invalid_input(self):
        for name in ('MVtext', 'SegmentFileData'):
            with self.subTest(name=name):
                source = self.source(name)
                text = nj.extract_text(source)
                record = nj.collect_strings(source)[0]
                result = nj.rebuild(source, self.replace_nj(text, record['abs_pos'], ''), self.table)
                self.assertEqual(nul(result, record['abs_pos']), b'')
                for bad in (self.replace_nj(text, record['abs_pos'], '\U0001f9ea'), text.split('\n', 1)[1]):
                    with self.assertRaises((UnicodeError, ValueError)):
                        nj.rebuild(source, bad, self.table)

    def test_common_roundtrip_and_shared_ids(self):
        source = self.source('njDBcommon')
        text = common.extract_text(source)
        entries = common.parse_text(text, 58)
        self.assertEqual(len(entries), 58)
        self.assertEqual(common.rebuild(source, text, self.table), source)
        reversed_text = ''.join(f'//[{i:02d}]\n{entries[i]}\n' for i in reversed(range(58)))
        self.assertEqual(common.rebuild(source, reversed_text, self.table), source)

    def test_common_growth_empty_and_prefix_shortening(self):
        source = self.source('njDBcommon')
        entries = common.parse_text(common.extract_text(source), 58)
        entries[0], entries[1], entries[2] = 'DETAIL' * 500, '', 'LI'
        text = ''.join(f'//[{i:02d}]\n{entries[i]}\n' for i in range(58))
        result = common.rebuild(source, text, self.table)
        self.assertEqual(result[:8], source[:8])
        self.assertEqual(result[12:16], source[12:16])
        self.assertEqual(16+u32(result, 8), len(result))
        for i in range(58):
            self.assertEqual(nul(result, 16+u32(result, 16+i*4)), entries[i].encode('euc_jis_2004'))

    def test_common_bad_records_and_encoding(self):
        source = self.source('njDBcommon')
        text = common.extract_text(source)
        for bad in (text.replace('//[01]', '//[00]'), text.replace('//[01]', '//[99]'),
                    text[:text.index('//[57]')], text.replace('DETAIL', '\U0001f9ea', 1),
                    text.replace('DETAIL', 'A\0B', 1)):
            with self.subTest(input=bad[:100]):
                with self.assertRaises((ValueError, UnicodeError)):
                    common.rebuild(source, bad, self.table)

    def test_common_preserves_literal_and_physical_newlines(self):
        source = self.source('njDBcommon')
        entries = common.parse_text(common.extract_text(source), 58)
        entries[0] = ' <TEXT> \\n\n\n'
        text = ''.join(f'//[{i:02d}]\n{entries[i]}\n' for i in range(58))
        result = common.rebuild(source, text, self.table)
        self.assertEqual(nul(result, 16+u32(result, 16)), entries[0].encode())

    def test_txd_roundtrip_all(self):
        for name in build_menu.TXD_NAMES:
            with self.subTest(name=name):
                source = self.source(name)
                self.assertEqual(self.parser.rebuild(source, self.parser.extract_text(source), self.table), source)

    def test_txd_count_header_and_legacy_editor(self):
        source = self.source('menutext')
        self.assertEqual(u32(source, 0), 909)
        text = self.parser.extract_text(source).replace('[1]', '[1]X', 1)
        result = self.parser.rebuild(source, text, self.table)
        self.assertEqual(u32(result, 0), 909)
        self.assertEqual(u32(result, 4), 3640)
        legacy = text.replace('[0]\n', '[0]\x15\n', 1)
        self.assertEqual(self.parser.rebuild(source, legacy, self.table), result)
        with self.assertRaises(ValueError):
            self.parser.rebuild(source, text.replace('[0]\n', '[0]WRONG\n', 1), self.table)

    def test_txd_count_divisible_by_four_is_not_a_pointer(self):
        for count in (4, 920):
            start = (count+1)*4
            source = struct.pack('<'+'I'*(count+1), count, *([start]*count)) + b'TEXT\0'
            with self.subTest(count=count):
                self.assertEqual(self.parser.get_data_start(source), start)
                self.assertEqual(self.parser.read_slots(source), [None]+[b'TEXT']*count)
                text = self.parser.extract_text(source)
                self.assertEqual(self.parser.rebuild(source, text), source)
                changed = self.parser.rebuild(source, text.replace('[1]TEXT', '[1]EDIT', 1))
                self.assertEqual(u32(changed, 0), count)
                self.assertEqual(self.parser.read_slots(changed)[1], b'EDIT')

    def test_txd_pointer_layout_with_count_like_second_pointer(self):
        source = struct.pack('<2I', 8, 36) + b'A'*27+b'\0B\0'
        self.assertEqual(self.parser.get_data_start(source), 8)
        self.assertEqual(self.parser.read_slots(source), [b'A'*27, b'B'])
        self.assertEqual(self.parser.rebuild(source, self.parser.extract_text(source)), source)

    def test_txd_empty_and_null_remain_distinct(self):
        for name, empty_count in (('devchk', 10), ('discchg', 4), ('menutext', 355)):
            with self.subTest(name=name):
                source = self.source(name)
                slots = self.parser.read_slots(source)
                index = next(i for i, raw in enumerate(slots) if raw)
                text = self.parser.extract_text(source).replace(f'[{index}]', f'[{index}]X', 1)
                result = self.parser.rebuild(source, text, self.table)
                new_slots = self.parser.read_slots(result)
                self.assertEqual(new_slots.count(b''), empty_count)
                self.assertEqual(new_slots.count(None), slots.count(None))
                for i in range(len(slots)):
                    if i != index:
                        self.assertEqual(new_slots[i], slots[i])

    def test_txd_explicit_empty_and_new_text_in_null_slot(self):
        source = bytearray(self.source('devchk'))
        struct.pack_into('<I', source, 4, 0)
        text = self.parser.extract_text(source)
        texts = self.parser.parse_text(text, 20)
        texts[0], texts[1] = '', 'NEW'
        result = self.parser.rebuild(source, ''.join(f'[{i}]{texts[i]}\n' for i in range(20)), self.table)
        self.assertNotEqual(u32(result, 0), 0)
        self.assertEqual(nul(result, u32(result, 0)), b'')
        self.assertEqual(nul(result, u32(result, 4)), b'NEW')

    def test_txd_bad_ids_and_encoding(self):
        source = self.source('discchg')
        text = self.parser.extract_text(source)
        cases = [text.replace('[1]', '[0]', 1), text.replace('[1]', '[999]', 1),
                 text[:text.index('[12]')], text.replace('[1]', '[1]\U0001f9ea', 1),
                 text.replace('[1]', '[1][0x00]', 1)]
        for content in cases:
            with self.subTest(input=content[:80]):
                with self.assertRaises((ValueError, UnicodeError)):
                    self.parser.rebuild(source, content, self.table)

    def test_txd_ids_not_position_and_preserve_line_endings(self):
        source = self.source('devchk')
        texts = self.parser.parse_text(self.parser.extract_text(source), 20)
        reordered = ''.join(f'[{i}]{texts[i]}\n' for i in reversed(range(20)))
        self.assertEqual(self.parser.rebuild(source, reordered, self.table), source)
        texts[0] = ' <TEST>\n\n'
        result = self.parser.rebuild(source, ''.join(f'[{i}]{texts[i]}\n' for i in range(20)), self.table)
        self.assertEqual(nul(result, u32(result, 0)), b' <TEST>\r\n\r\n')

    def test_txd_more_than_64k(self):
        source = self.source('devchk')
        text = self.parser.extract_text(source).replace('[0]', '[0]' + 'X'*70000, 1)
        result = self.parser.rebuild(source, text, self.table)
        self.assertEqual(len(self.parser.read_slots(result)), 20)
        self.assertGreater(u32(result, 4), 65535)

    def test_current_translation_all_references(self):
        for name, _, result, _ in build_menu.prepare(build_menu.NAMES):
            with self.subTest(name=name):
                asset = self.manifest['assets'][name]
                content = (HOME / asset['edit']).read_text(encoding='utf-8-sig')
                source = self.source(name)
                if name in build_menu.DATASET_NAMES:
                    records = {r['abs_pos']: r for r in nj.collect_strings(source)}
                    for line in content.splitlines():
                        if not line:
                            continue
                        match = nj.META_RE.fullmatch(line)
                        record = records[int(match[2], 16)]
                        value = nj.process_menu_sita(match[3])
                        expected = ''.join(self.table.get(c, c) for c in value).encode('euc_jis_2004')
                        for ptr_pos in record['refs']:
                            self.assertEqual(nul(result, record['ds_off'] + u32(result, ptr_pos)), expected)
                elif name in ('njDBcommon', 'njBtlText'):
                    count = 58 if name == 'njDBcommon' else 51
                    entries = common.parse_text(content, count)
                    base = u32(result, 4)
                    self.assertEqual(base + u32(result, 8), len(result))
                    for i in range(count):
                        expected = ''.join(self.table.get(c, c) for c in entries[i]).encode('euc_jis_2004')
                        self.assertEqual(nul(result, base + u32(result, base + i*4)), expected)
                else:
                    slots = self.parser.read_slots(source)
                    texts = self.parser.parse_text(content, len(slots))
                    for i, original in enumerate(slots):
                        if name == 'menutext' and i == 0:
                            continue
                        value = texts[i]
                        if value == (self.parser.safe_decode(original) if original is not None else ''):
                            expected = original
                        else:
                            if '[menu_sita]' in value:
                                value = value.replace('[menu_sita]', '').replace(' ', '\u3001')
                            value = ''.join(self.table.get(c, c) for c in value).replace('\n', '\r\n')
                            parts = bytearray()
                            cursor = 0
                            for marker in re.finditer(r'\[0x([0-9A-Fa-f]+)\]', value):
                                parts.extend(value[cursor:marker.start()].encode('euc_jis_2004'))
                                digits = marker[1]
                                parts.extend(bytes.fromhex(digits.zfill(len(digits) + len(digits) % 2)))
                                cursor = marker.end()
                            parts.extend(value[cursor:].encode('euc_jis_2004'))
                            expected = bytes(parts)
                        ptr = u32(result, i*4)
                        self.assertEqual(None if ptr == 0 else nul(result, ptr), expected)

    def test_failed_later_asset_publishes_nothing(self):
        real_read = Path.read_text
        bad_path = (HOME / self.manifest['assets']['synopsis']['edit']).resolve()
        def damaged(path, *args, **kwargs):
            text = real_read(path, *args, **kwargs)
            return text.replace('[0]', '[0]\U0001f9ea', 1) if path == bad_path else text
        with patch.object(Path, 'read_text', damaged), patch.object(build_menu, 'write_output') as save:
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(build_menu.main([]), 1)
            save.assert_not_called()

    def test_source_hash_failure_publishes_nothing(self):
        real_read = Path.read_bytes
        bad_path = HOME.parents[1] / '0.X30/mnu/kr/njDataText.bin'
        def damaged(path):
            value = real_read(path)
            return value + b'BAD' if path == bad_path else value
        with patch.object(Path, 'read_bytes', damaged), patch.object(build_menu, 'write_output') as save:
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(build_menu.main([]), 1)
            save.assert_not_called()

    def test_output_cannot_replace_input(self):
        source = HOME.parents[1] / '0.X30/mnu/kr/njDataText.bin'
        with self.assertRaises(ValueError):
            output.write_output(source, b'BAD', (source,))

    def test_atomic_write_uses_pending_before_replace(self):
        calls = []
        class Stream(io.BytesIO):
            def fileno(self):
                return 0
            def close(self):
                calls.append(('data', self.getvalue()))
                super().close()
        def fake_open(path, mode):
            calls.append(('open', path.name, mode))
            return Stream()
        with patch.object(Path, 'open', fake_open), patch.object(output.os, 'fsync') as sync:
            with patch.object(output.os, 'replace', side_effect=lambda a, b: calls.append(('replace', a.name, b.name))):
                output.write_output(HOME / 'atomic-test.bin', b'COMPLETE')
            sync.assert_called_once()
        self.assertEqual(calls, [('open', 'atomic-test.bin.pending', 'xb'), ('data', b'COMPLETE'),
                                 ('replace', 'atomic-test.bin.pending', 'atomic-test.bin')])

    def test_pending_failure_does_not_replace_output(self):
        with patch.object(Path, 'open', side_effect=FileExistsError('pending')):
            with patch.object(output.os, 'replace') as replace:
                with self.assertRaises(FileExistsError):
                    output.write_output(HOME / 'atomic-test.bin', b'BAD')
                replace.assert_not_called()

    def test_reverting_translation_returns_original(self):
        for name in build_menu.NAMES:
            with self.subTest(name=name):
                source = self.source(name)
                if name in build_menu.DATASET_NAMES:
                    rebuilt = nj.rebuild(source, nj.extract_text(source), self.table)
                elif name in ('njDBcommon', 'njBtlText'):
                    rebuilt = common.rebuild(source, common.extract_text(source), self.table)
                else:
                    rebuilt = self.parser.rebuild(source, self.parser.extract_text(source), self.table)
                self.assertEqual(rebuilt, source)


if __name__ == '__main__':
    unittest.main(verbosity=2)
