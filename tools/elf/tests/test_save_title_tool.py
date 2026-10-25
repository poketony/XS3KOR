"""Boundary, preservation and publication tests for the optional paired patch."""

import contextlib
import io
import json
from pathlib import Path
import struct
import unittest
from unittest.mock import patch
import uuid
import tempfile

import save_title_tool as t


class SaveTitleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.menu = (t.HERE / 'original/menutext.txd').read_bytes()
        cls.slps = (t.HERE / 'original/SLPS.original').read_bytes()
        cls.names_text = t.export_original_names(cls.menu)
        cls.names = t.parse_names(cls.names_text)
        temporary = tempfile.TemporaryDirectory(dir=t.HERE, prefix='test-save-title-')
        cls.addClassCleanup(temporary.cleanup)
        cls.root = Path(temporary.name)

    def setUp(self):
        local = t.elf.local
        def test_output(relative):
            if relative.startswith('output/save-title/'):
                return self.root / relative
            return local(relative)
        redirect = patch.object(t.elf, 'local', side_effect=test_output)
        redirect.start()
        self.addCleanup(redirect.stop)

    def inputs(self):
        root = self.root / uuid.uuid4().hex
        root.mkdir()
        menu, names = root / 'menu input.txd', root / 'names input.txt'
        menu.write_bytes(self.menu)
        names.write_text(self.names_text, encoding='utf-8')
        return menu, names

    def test_originals_match_the_expected_sources(self):
        self.assertEqual(t.sha(self.menu), t.MENU_HASH)
        self.assertEqual(t.sha(self.slps), t.elf.ASSETS['SLPS']['sha256'])

    def test_names_roundtrip_and_id_order(self):
        lines = self.names_text.splitlines()
        reordered = '\n'.join([t.HEADER]+[line for line in reversed(lines) if not line.startswith('#')])
        self.assertEqual(t.parse_names(reordered), self.names)
        slots = t.slots(self.menu)
        for index, name in enumerate(self.names, 1):
            self.assertEqual(name, slots[t.NAME_BASE+index+1])

    def test_invalid_name_files_fail(self):
        lines = self.names_text.splitlines()
        for content in (self.names_text.replace(t.HEADER, '# wrong'),
                        '\n'.join(lines[:-1]), self.names_text+lines[-1]+'\n',
                        self.names_text.replace('16|', '17|'), self.names_text.replace('01|', 'XX|')):
            with self.subTest(content=content[-50:]), self.assertRaises(ValueError):
                t.parse_names(content)

    def test_ascii_controls_korean_overlong_names_are_not_silently_changed(self):
        for value in ('KOS-MOS', '', '\0', '\uac00', '\uff21'*11, '\u2160'):
            with self.subTest(value=repr(value)), self.assertRaises((ValueError, UnicodeError)):
                t.encode_name(value)

    def test_explicit_fullwidth_latin_and_punctuation(self):
        text = '\uff2b\uff2f\uff33\u2212\uff2d\uff2f\uff33'
        encoded = t.encode_name(text)
        self.assertEqual(encoded.decode('euc_jis_2004'), text)
        self.assertEqual(b''.join(t.convert_pair(*encoded[i:i+2]) for i in range(0, len(encoded), 2)),
                         text.encode('cp932'))

    def test_old_slots_and_pool_bytes_unchanged(self):
        result = t.append_names(self.menu, self.names, self.menu)
        self.assertEqual(t.slots(result, 926), [*t.slots(self.menu), b'', *self.names])
        self.assertEqual(result[3708:len(self.menu)+68], self.menu[3640:])

    def test_all_original_title_combinations_match_system_encoding(self):
        result = t.append_names(self.menu, self.names, self.menu)
        def get(data, index):
            offset = struct.unpack_from('<I', data, (index+1)*4)[0]
            return data[offset:data.index(b'\0', offset)]
        cases = 0
        for character in range(1, 17):
            for level in range(1, 100):
                for star in (False, True):
                    suffix = (get(self.menu, 0x277+level//10) if level > 9 else b'',
                              get(self.menu, 0x277+level % 10), get(self.menu, 0x281) if star else b'')
                    before = get(self.menu, 0x276) % (get(self.menu, t.NAME_BASE+character), *suffix)
                    after = get(result, 0x276) % (get(result, t.MENU_COUNT+character), *suffix)
                    self.assertEqual(after, before)
                    self.assertLessEqual(len(after), 32)
                    converted = b''.join(t.convert_pair(*after[i:i+2]) for i in range(0, len(after), 2))
                    self.assertEqual(converted, before.decode('euc_jis_2004').encode('cp932'))
                    cases += 1
        self.assertEqual(cases, 3168)

    def test_bad_menu_layouts_and_repeated_patch_fail(self):
        bad = bytearray(self.menu)
        struct.pack_into('<I', bad, 4, 8)
        repeated = t.append_names(self.menu, self.names, self.menu)
        for data in (b'', bytes(bad), repeated):
            with self.assertRaises(ValueError):
                t.append_names(data, self.names, self.menu)

    def test_release_english_names_and_all_title_combinations(self):
        names = t.parse_names((t.HERE / 'edit/save_title.names.txt').read_text(encoding='utf-8-sig'))
        expected = ('Shion', 'Jin', 'MOMO', 'Ziggy', 'KOS-MOS', 'chaos', 'Jr.',
                    'Miyuki', 'Canaan', 'Allen', 'Unused', 'Unused',
                    'ES Asher', 'ES Zebulun', 'ES Dinah', 'ES Reuben')
        import unicodedata
        self.assertEqual(tuple(unicodedata.normalize('NFKC', n.decode('euc_jis_2004'))
                               .replace('\u2212', '-') for n in names), expected)
        result = t.append_names(self.menu, names, self.menu)
        values = t.slots(result, 926)[1:]
        for character in range(1, 17):
            for level in range(1, 100):
                for star in (False, True):
                    title = values[0x276] % (
                        values[t.MENU_COUNT+character],
                        values[0x277+level//10] if level > 9 else b'',
                        values[0x277+level % 10], values[0x281] if star else b'')
                    self.assertLessEqual(len(title), 32)
                    converted = b''.join(t.convert_pair(*title[i:i+2])
                                         for i in range(0, len(title), 2))
                    self.assertEqual(converted, title.decode('euc_jis_2004').encode('cp932'))
        self.assertEqual(t.slots(result, 926)[:910], t.slots(self.menu))

    def test_exact_resident_boundary_and_one_byte_over(self):
        result = t.append_names(self.menu, self.names, self.menu)
        padding = t.MENU_LIMIT-len(result)
        self.assertEqual(len(t.append_names(self.menu+bytes(padding), self.names, self.menu)), t.MENU_LIMIT)
        with self.assertRaisesRegex(ValueError, '16384-byte'):
            t.append_names(self.menu+bytes(padding+1), self.names, self.menu)

    def test_format_digits_and_star_cannot_be_changed_implicitly(self):
        for index in (0x276, 0x277, 0x281):
            data = bytearray(self.menu)
            pointer = struct.unpack_from('<I', data, (index+1)*4)[0]
            data[pointer] = 0x58
            with self.subTest(index=index), self.assertRaisesRegex(ValueError, 'format, digits or star'):
                t.append_names(data, self.names, self.menu)

    def test_slps_only_two_immediate_bytes_change(self):
        result, offset = t.patch_slps(self.slps, self.slps)
        self.assertEqual(offset, 0x11330c)
        self.assertEqual([i for i, (a, b) in enumerate(zip(self.slps, result)) if a != b], [offset, offset+1])
        self.assertEqual(struct.unpack_from('<I', result, offset)[0], 0x2444038d)
        with self.assertRaises(ValueError):
            t.patch_slps(result, self.slps)

    def test_prepare_keeps_current_elf_translation_and_all_inputs(self):
        menu, names = self.inputs()
        outputs, report, hashes = t.prepare([menu, names])
        mapping = json.loads((t.HERE / 'XENOSAGA KOR-JPN.json').read_text(encoding='utf-8-sig'))['replace-table']
        current = t.elf.build_blob('SLPS', self.slps, t.elf.editor_path('SLPS').read_text(encoding='utf-8-sig'), mapping)
        expected, _ = t.patch_slps(current, self.slps)
        self.assertEqual(outputs['SLPS_256.40.new'], expected)
        self.assertEqual(outputs['SLPS_256.41.new'], expected)
        self.assertEqual(outputs['menutext.txd.new'], t.append_names(self.menu, self.names, self.menu))
        self.assertFalse(report['game_runtime_verified'])
        t.check_inputs(hashes)

    def test_bad_missing_duplicate_inputs_do_not_fall_back(self):
        menu, names = self.inputs()
        for values in ([], [names], [menu, menu], [menu, names, names], [menu.with_name('missing.txd')]):
            with self.subTest(values=values), self.assertRaises((ValueError, OSError)):
                t.prepare(values)

    def test_check_does_not_publish_and_supports_interleaved_options(self):
        menu, names = self.inputs()
        with patch.object(t, 'publish') as publish, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(t.main([str(menu), '--check', str(names)]), 0)
        publish.assert_not_called()

    def test_invalid_name_stops_before_publication(self):
        menu, names = self.inputs()
        names.write_text(self.names_text.replace('01|', '01|ASCII'), encoding='utf-8')
        with patch.object(t, 'publish') as publish, contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(t.main([str(menu), str(names)]), 1)
        publish.assert_not_called()

    def test_input_change_blocks_publication(self):
        menu, names = self.inputs()
        outputs, report, hashes = t.prepare([menu, names])
        menu.write_bytes(self.menu+b'\0')
        with self.assertRaisesRegex(ValueError, 'Input changed'):
            t.publish(outputs, report, hashes, 'changed-'+uuid.uuid4().hex)

    def test_bundle_published_together_and_collision_is_not_overwritten(self):
        menu, names = self.inputs()
        outputs, report, hashes = t.prepare([menu, names])
        name = 'test-'+uuid.uuid4().hex
        target = t.publish(outputs, report, hashes, name)
        self.assertFalse(target.with_name(name+'.pending').exists())
        self.assertEqual({path.name for path in target.iterdir()}, {*outputs, 'VERIFIED.json'})
        for filename, data in outputs.items():
            self.assertEqual((target / filename).read_bytes(), data)
        self.assertEqual(json.loads((target / 'VERIFIED.json').read_text(encoding='utf-8')), report)
        with self.assertRaises(FileExistsError):
            t.publish(outputs, report, hashes, name)

    def test_interrupted_bundle_is_not_published_or_cleaned_up(self):
        menu, names = self.inputs()
        outputs, report, hashes = t.prepare([menu, names])
        name = 'interrupted-'+uuid.uuid4().hex
        with patch.object(t.os, 'fsync', side_effect=OSError('simulated interruption')), self.assertRaises(OSError):
            t.publish(outputs, report, hashes, name)
        base = self.root / 'output/save-title'
        self.assertFalse((base / name).exists())
        self.assertTrue((base / (name+'.pending')).is_dir())
        with self.assertRaises(FileExistsError):
            t.publish(outputs, report, hashes, name)


if __name__ == '__main__':
    unittest.main()
