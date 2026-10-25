"""Offline regression checks with disposable filesystem fixtures."""
import unittest
from unittest.mock import patch
import tempfile
from pathlib import Path

import elf_text_tool as t


class TextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.originals, cls.table = t.load_inputs()
        temporary = tempfile.TemporaryDirectory(dir=t.HERE, prefix='test-elf-')
        cls.addClassCleanup(temporary.cleanup)
        cls.root = Path(temporary.name)

    def text(self, name='SLPS'):
        return t.export_text(name, self.originals[name])

    def change(self, name, offset, value):
        rows = t.catalog(name, self.originals[name])
        old = rows[offset]['text']
        return self.text(name).replace('|' + old + '\n', '|' + value + '\n')

    def rebuild(self, name, text):
        return t.build_blob(name, self.originals[name], text, self.table)

    def reject(self, name, offset, value):
        with self.assertRaises(ValueError):
            self.rebuild(name, self.change(name, offset, value))

    def test_japanese_roundtrip(self):
        for name, original in self.originals.items():
            with self.subTest(name=name):
                self.assertEqual(self.rebuild(name, self.text(name)), original)

    def test_desktop_exact_roundtrip(self):
        result = self.rebuild('SLPS', t.export_text('SLPS', self.originals['SLPS'], True))
        self.assertEqual(t.sha(result), t.DESKTOP_HASH)
        self.assertEqual(sum(a != b for a, b in zip(result, self.originals['SLPS'])), 42)

    def test_all_reviewed_slots_editable(self):
        for name, original in self.originals.items():
            for offset, row in t.catalog(name, original).items():
                with self.subTest(name=name, offset=hex(offset)):
                    character = next(c for c in row['text'] if ord(c) > 127)
                    changed = row['text'].replace(character, '\uac00', 1)
                    result = self.rebuild(name, self.change(name, offset, changed))
                    self.assertNotEqual(result, original)

    def test_capacity_boundary(self):
        result = self.rebuild('OV04', self.change('OV04', 0x3F0A8, 'ABCDEFG'))
        self.assertEqual(result[0x3F0A8:0x3F0B0], b'ABCDEFG\0')
        self.reject('OV04', 0x3F0A8, 'ABCDEFGH')

    def test_hangul_mapping(self):
        self.assertEqual(t.encode_text('\ubc29\uc5b4\uad6c', self.table),
                         ''.join(self.table[c] for c in '\ubc29\uc5b4\uad6c').encode('euc_jis_2004'))

    def test_euc_2004_extension(self):
        char = '\u4ff1'
        self.assertEqual(t.encode_text(char, {}), char.encode('euc_jis_2004'))

    def test_unmapped_hangul(self):
        self.reject('OV04', 0x3F0A8, '\uac02')

    def test_unencodable_character(self):
        self.reject('OV04', 0x3F0A8, '\U0001f600')

    def test_control_preservation(self):
        for old, new in (('{0CC0C0C0}', ''), ('{0CC0C0C0}', '{0C808080}')):
            with self.subTest(new=new):
                row = t.catalog('SLPS', self.originals['SLPS'])[0x410780]
                self.reject('SLPS', 0x410780, row['text'].replace(old, new))

    def test_printf_order_and_count(self):
        row = t.catalog('SLPS', self.originals['SLPS'])[0x4107C8]
        for value in (row['text'].replace('%d', '%s'), row['text'].replace('%s', '', 1),
                      row['text'].replace('%d', '%n'), row['text'].replace('%d', '%02d')):
            self.reject('SLPS', 0x4107C8, value)

    def test_markup_preservation(self):
        row = t.catalog('SLPS', self.originals['SLPS'])[0x410780]
        self.reject('SLPS', 0x410780, row['text'].replace('<s0>', '<s1>'))
        self.reject('SLPS', 0x410780, row['text'].replace(r'\\n', r'\n'))

    def test_button_symbols(self):
        row = t.catalog('SLPS', self.originals['SLPS'])[0x41EE70]
        self.reject('SLPS', 0x41EE70, row['text'].replace('\u25cb', '\u25a1'))

    def test_newline_preservation(self):
        row = t.catalog('SLPS', self.originals['SLPS'])[0x41EE70]
        self.reject('SLPS', 0x41EE70, row['text'].replace(r'\n', '', 1))

    def test_count_fixed_position(self):
        result = self.rebuild('OV04', self.change('OV04', 0x3DDA8, '0\uc5f0\uc18d \uace8'))
        self.assertEqual(result[0x3DDA8], ord('0'))
        for value in ('\uc5f0\uc18d0', '00\uace8', '1\uace8', '0' + 'A' * 11, ''):
            self.reject('OV04', 0x3DDA8, value)

    def test_embedded_nul(self):
        for text in ('A{00}B', '{0C00}', '{0C0000}', '{0C000000}{00}'):
            self.reject('OV04', 0x3F0A8, text)

    def test_malformed_escapes(self):
        for text in ('{GG}', '{0}', '{', '}', '\\x', '\\', 'A\tB'):
            self.reject('OV04', 0x3F0A8, text)

    def test_hex_cannot_smuggle_controls(self):
        self.reject('OV04', 0x3F0A8, '{0B}A')
        self.reject('OV04', 0x3F0A8, '{2564}')

    def test_literal_punctuation_not_normalized(self):
        text = '\u300c\uc774\ub984\u300d'
        self.assertEqual(t.encode_text(text, self.table),
                         ''.join(self.table.get(c, c) for c in text).encode('euc_jis_2004'))

    def test_pipe_in_text(self):
        result = self.rebuild('OV04', self.change('OV04', 0x3F0A8, 'A|B'))
        self.assertEqual(result[0x3F0A8:0x3F0AC], b'A|B\0')

    def test_missing_row_restores_original(self):
        text = t.export_text('SLPS', self.originals['SLPS'], True)
        text = '\n'.join(line for line in text.splitlines() if not line.startswith('004107'))
        self.assertEqual(self.rebuild('SLPS', text), self.originals['SLPS'])

    def test_bom_and_crlf(self):
        self.assertEqual(self.rebuild('SLPS', '\ufeff' + self.text().replace('\n', '\r\n')),
                         self.originals['SLPS'])

    def test_duplicate_unknown_offset(self):
        text = self.text()
        line = next(line for line in text.splitlines() if line.startswith('00410780'))
        for changed in (text + line + '\n', text.replace('00410780|', '00410781|')):
            with self.assertRaises(ValueError): self.rebuild('SLPS', changed)

    def test_header_and_limits_locked(self):
        text = self.text()
        for changed in (text.replace('33/39', '33/99'), text.replace('# asset: SLPS', '# asset: OV04'),
                        text.replace('# origin-sha256:', '# removed:'),
                        text + '# origin-sha256: ' + t.ASSETS['SLPS']['sha256'] + '\n'):
            with self.assertRaises(ValueError): self.rebuild('SLPS', changed)

    def test_patched_original_rejected(self):
        original = bytearray(self.originals['SLPS'])
        original[0x1000] ^= 1
        with self.assertRaises(ValueError): t.catalog('SLPS', original)

    def test_output_corruption(self):
        original = self.originals['SLPS']
        for offset in (0x1000, 0x410780, 0x4107A6, len(original)-1):
            output = bytearray(original)
            output[offset] ^= 1
            with self.assertRaises(ValueError): t.verify_output('SLPS', original, output, {})

    def test_roundtrip_repeated_build(self):
        text = t.export_text('SLPS', self.originals['SLPS'], True)
        self.assertEqual(self.rebuild('SLPS', text), self.rebuild('SLPS', text))

    def test_path_escape(self):
        with self.assertRaises(ValueError): t.local('../outside.new')

    def test_mapping_hash_rejected(self):
        root = self.root / 'mapping'
        root.mkdir()
        (root / 'XENOSAGA KOR-JPN.json').write_bytes(b'{}')
        with patch.object(t, 'HERE', root), self.assertRaises(ValueError): t.load_inputs()

    def test_publish_replaces_new_only(self):
        root = self.root / 'publish'
        root.mkdir()
        with patch.object(t, 'HERE', root):
            t.publish('output/test.new', b'first')
            t.publish('output/test.new', b'second')
        self.assertEqual((root / 'output/test.new').read_bytes(), b'second')
        self.assertFalse((root / 'output/test.new.pending').exists())

    def test_publish_failure_preserves_final(self):
        root = self.root / 'failed'
        root.mkdir()
        (root / 'test.new').write_bytes(b'previous')
        with patch.object(t, 'HERE', root), patch.object(t.os, 'replace', side_effect=OSError('test')):
            with self.assertRaises(OSError): t.publish('test.new', b'next')
        self.assertEqual((root / 'test.new').read_bytes(), b'previous')
        self.assertEqual((root / 'test.new.pending').read_bytes(), b'next')
        with patch.object(t, 'HERE', root), self.assertRaises(ValueError): t.publish('test.new', b'again')

    def test_invalid_second_asset_publishes_nothing(self):
        root = self.root / 'invalid-second'
        (root / 'edit').mkdir(parents=True)
        (root / 'edit/SLPS.txt').write_text(self.text(), encoding='utf-8')
        (root / 'edit/OV04.txt').write_text('invalid', encoding='utf-8')
        with patch.object(t, 'HERE', root), patch.object(t, 'EDITOR', root / 'edit'), \
                patch.object(t, 'load_inputs', return_value=(self.originals, self.table)):
            with self.assertRaises(ValueError): t.run('build')
        self.assertFalse((root / 'output').exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
