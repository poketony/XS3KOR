"""Database layout, editor preservation and paired-build regression tests."""

import collections
import contextlib
import io
import json
import struct
import unittest
from pathlib import Path
from unittest.mock import patch

import build_database
from tools import database_text as db


HOME = Path(__file__).resolve().parents[1]


def u32(data, position):
    return struct.unpack_from('<I', data, position)[0]


def read_field(data, row):
    address = row['ds_off'] + u32(data, row['ptr_pos'])
    return data[address:data.index(b'\0', address)]


class DatabaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sources = {name: (HOME.parents[1] / f'0.X30/mnu/kr/{name}.bin').read_bytes() for name in ('DBC', 'DBC2')}
        cls.table = json.loads((HOME / 'XENOSAGA KOR-JPN.json').read_text(encoding='utf-8-sig'))['replace-table']
        manifest = json.loads((HOME / 'sources.json').read_text(encoding='utf-8'))
        cls.editor_path = (HOME / manifest['assets']['DBC']['edit']).resolve()
        cls.editor = cls.editor_path.read_text(encoding='utf-8-sig')

    def replace_address(self, text, address, value):
        result = []
        found = 0
        for line in text.split('\n'):
            token, sep, _ = line.partition('|')
            if sep and int(token, 16) == address:
                line = f'{token}|{value}'
                found += 1
            result.append(line)
        self.assertGreater(found, 0)
        return '\n'.join(result)

    def test_records_match_independent_pointer_scan(self):
        for name, data in self.sources.items():
            with self.subTest(name=name):
                rows = db.read_rows(data)
                self.assertEqual(len(rows), 3624)
                self.assertEqual(len({row['id'] for row in rows}), 453)
                scanned = []
                for i in range(u32(data, 0)):
                    base, size = struct.unpack_from('<2I', data, 4+i*8)
                    pool = base + u32(data, base+12)
                    starts = set()
                    address = pool
                    while address < base+size:
                        if data[address] == 0:
                            address += 1
                            continue
                        starts.add(address)
                        address = data.index(b'\0', address)+1
                    for pointer in range(base, pool, 4):
                        if base+u32(data, pointer) in starts:
                            scanned.append((pointer, base+u32(data, pointer)))
                self.assertEqual(scanned, [(r['ptr_pos'], r['address']) for r in rows])

    def test_unmodified_roundtrip_both_sources(self):
        for name, data in self.sources.items():
            with self.subTest(name=name):
                self.assertEqual(db.rebuild(data, db.extract_text(data), self.table), data)
        primary, secondary, details = db.rebuild_pair(self.sources['DBC'], self.sources['DBC2'],
                                                     db.extract_text(self.sources['DBC']), self.table)
        self.assertEqual(primary, self.sources['DBC'])
        self.assertEqual(secondary, self.sources['DBC2'])
        self.assertEqual(details['secondary_reading_groups_preserved'], 401)

    def test_approved_duplicate_choices(self):
        values = db.parse_text(self.editor, db.read_rows(self.sources['DBC']))
        self.assertEqual(values[0xa125], '\ud2b9\uc218 \uc7ac\ub2e8 \ucfe0\uce74\uc774 \ud30c\uc6b4\ub370\uc774\uc158 \ub300\ud45c \uc774\uc0ac')
        self.assertEqual(values[0x14929], '\ubc29\uc6b8 \uc18c\ub9ac\uc640 \ud568\uaed8 \uc885\uc885 \uc2dc\uc628\uc758 \uc55e\uc5d0 \ud658\uc601\uc73c\ub85c \ub098\ud0c0\ub098\ub294 \uc18c\ub140')
        self.assertIn('\u2015\u2015', values[0x29590])
        self.assertNotIn('\u2014', values[0x29590])

    def test_all_translated_fields_and_secondary_reading_groups(self):
        first, second, _ = db.rebuild_pair(self.sources['DBC'], self.sources['DBC2'], self.editor, self.table)
        rows = db.read_rows(self.sources['DBC'])
        values = db.parse_text(self.editor, rows)
        primary_by_id = {(r['id'], r['field']): r for r in rows}
        for row in rows:
            expected = ''.join(self.table.get(c, c) for c in values[row['address']]).encode('euc_jis_2004')
            self.assertEqual(read_field(first, row), expected)
        for row in db.read_rows(self.sources['DBC2']):
            primary = primary_by_id[row['id'], row['field']]
            if row['raw'] != primary['raw']:
                self.assertEqual(row['field'], 12)
                self.assertEqual(read_field(second, row), row['raw'])
            else:
                expected = ''.join(self.table.get(c, c) for c in values[primary['address']]).encode('euc_jis_2004')
                self.assertEqual(read_field(second, row), expected)

    def test_growth_preserves_scalar_collision_and_unedited_bytes(self):
        source = bytearray(self.sources['DBC'])
        rows = db.read_rows(source)
        first = rows[0]
        scalar = first['ptr_pos'] + 4
        old_pointer = first['address'] - first['ds_off']
        struct.pack_into('<I', source, scalar, old_pointer)
        value = 'LONG ' * 100
        content = self.replace_address(db.extract_text(source), first['address'], value)
        result = db.rebuild(source, content, self.table)
        self.assertEqual(u32(result, scalar), old_pointer)
        allowed = set(range(first['address'], first['address']+len(first['raw'])+1))
        for row in rows:
            if row['address'] == first['address']:
                allowed.update(range(row['ptr_pos'], row['ptr_pos']+4))
                self.assertEqual(read_field(result, row), value.encode())
            else:
                self.assertEqual(read_field(result, row), row['raw'])
        self.assertTrue(all(a == b or i in allowed for i, (a, b) in enumerate(zip(source, result))))

    def test_prefix_shortening_and_empty_are_real_edits(self):
        source = self.sources['DBC']
        rows = db.read_rows(source)
        first = rows[0]
        for text in (first['text'][:1], ''):
            with self.subTest(text=text):
                content = self.replace_address(db.extract_text(source), first['address'], text)
                result = db.rebuild(source, content, self.table)
                self.assertEqual(read_field(result, first), text.encode('euc_jis_2004'))
                self.assertEqual(len(result), len(source))

    def test_shared_source_can_split_distinct_target_references(self):
        source = self.sources['DBC2']
        rows = db.read_rows(source)
        counts = collections.Counter(row['address'] for row in rows)
        index = next(i for i, row in enumerate(rows) if counts[row['address']] > 1)
        expected = [row['raw'] for row in rows]
        expected[index] = b'ONE REFERENCE ONLY' * 30
        result = db.patch_rows(source, rows, expected)
        for row, wanted in zip(rows, expected):
            self.assertEqual(read_field(result, row), wanted)
        self.assertEqual(source[rows[index]['address']:rows[index]['address']+len(rows[index]['raw'])+1],
                         result[rows[index]['address']:rows[index]['address']+len(rows[index]['raw'])+1])

    def test_conflicts_missing_extra_and_unknown_addresses_rejected(self):
        source = self.sources['DBC']
        text = db.extract_text(source)
        first, rest = text.split('\n', 1)
        for bad in (rest, text+first+'\n', text.replace('0x4f28|', '0xffffff|', 1),
                    text.replace(first, first+'CONFLICT', 1), text+'bad line\n'):
            with self.subTest(input=bad[:70]):
                with self.assertRaises(ValueError):
                    db.rebuild(source, bad, self.table)

    def test_reordered_rows_preserve_identity(self):
        source = self.sources['DBC']
        text = '\n'.join(reversed(db.extract_text(source).splitlines()))+'\n'
        self.assertEqual(db.rebuild(source, text, self.table), source)

    def test_punctuation_whitespace_literal_escapes_and_encoding_errors(self):
        source = self.sources['DBC']
        text = db.extract_text(source)
        address = 0x4f35
        value = ' <TEXT> \\n \\r \uac00 '
        result = db.rebuild(source, self.replace_address(text, address, value), self.table)
        row = next(r for r in db.read_rows(source) if r['address'] == address)
        expected = ''.join(self.table.get(c, c) for c in value).encode('euc_jis_2004')
        self.assertEqual(read_field(result, row), expected)
        for value in ('\U0001f9ea', '\u2014', 'A\0B'):
            with self.assertRaises((UnicodeError, ValueError)):
                db.rebuild(source, self.replace_address(text, address, value), self.table)

    def test_bad_structure_and_noncategory_pair_mismatch_rejected(self):
        source = self.sources['DBC']
        for position in (0, 4, 96):
            bad = bytearray(source)
            struct.pack_into('<I', bad, position, 0xffffffff)
            with self.assertRaises(ValueError):
                db.read_rows(bad)
        secondary = bytearray(self.sources['DBC2'])
        row = next(r for r in db.read_rows(secondary) if r['field'] == 20)
        secondary[row['address']:row['address']+2] = b'ZZ'
        with self.assertRaises(ValueError):
            db.rebuild_pair(source, secondary, db.extract_text(source), self.table)

    def test_failed_editor_publishes_neither_output(self):
        real_read = Path.read_text
        editor = self.editor_path
        def damaged(path, *args, **kwargs):
            value = real_read(path, *args, **kwargs)
            return value.replace('0x4f35|', '0x4f35|\U0001f9ea', 1) if path == editor else value
        with patch.object(Path, 'read_text', damaged), patch.object(build_database, 'write_output') as save:
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(build_database.main([]), 1)
            save.assert_not_called()

    def test_changed_secondary_source_publishes_neither_output(self):
        real_read = Path.read_bytes
        source = HOME.parents[1] / '0.X30/mnu/kr/DBC2.bin'
        def damaged(path):
            value = real_read(path)
            return value + b'BAD' if path == source else value
        with patch.object(Path, 'read_bytes', damaged), patch.object(build_database, 'write_output') as save:
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(build_database.main([]), 1)
            save.assert_not_called()

    def test_canonical_editor_builds_both_databases(self):
        expected = HOME.parents[1] / '0.X30/mnu/kr/DBC.bin.KOR.txt'
        self.assertEqual(self.editor_path, expected)
        self.assertFalse((HOME / 'edit/DBC.bin.KOR.txt').exists())
        outputs, protected, _ = build_database.prepare()
        self.assertEqual([name for name, _, _ in outputs], ['DBC', 'DBC2'])
        folder = HOME.parents[1] / '0.X30/mnu/kr'
        self.assertEqual(protected[:3], (folder / 'DBC.bin', folder / 'DBC2.bin', expected))

    def test_canonical_edit_changes_both_outputs(self):
        target = HOME.parents[1] / '0.X30/mnu/kr/DBC.bin.KOR.txt'
        original_read = Path.read_text
        baseline = build_database.prepare()[0]
        def read_edited(path, *args, **kwargs):
            content = original_read(path, *args, **kwargs)
            if path.resolve() == target:
                content = self.replace_address(content, 0x4f35, 'CANONICAL TEST')
            return content
        with patch.object(Path, 'read_text', read_edited):
            changed = build_database.prepare()[0]
        for (name, _, data), (_, _, old) in zip(changed, baseline):
            with self.subTest(name=name):
                self.assertNotEqual(data, old)
                self.assertIn(b'CANONICAL TEST', data)

    def test_missing_canonical_editor_fails_without_fallback(self):
        target = HOME.parents[1] / '0.X30/mnu/kr/DBC.bin.KOR.txt'
        original_read = Path.read_text
        def missing_editor(path, *args, **kwargs):
            if path.resolve() == target:
                raise FileNotFoundError(target)
            return original_read(path, *args, **kwargs)
        with patch.object(Path, 'read_text', missing_editor), self.assertRaises(FileNotFoundError):
            build_database.prepare()


if __name__ == '__main__':
    unittest.main(verbosity=2)
