"""batdat structural, migration and failed-write regression tests."""

import contextlib
import copy
import hashlib
import io
import json
import struct
import unittest
from pathlib import Path
from unittest.mock import patch

import build_batdat
from tools import batdat_text as batdat


HOME = Path(__file__).resolve().parents[1]


def u16(data, offset):
    return struct.unpack_from('<H', data, offset)[0]


def nul(data, offset):
    return data[offset:data.index(b'\0', offset)]


class BatdatTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((HOME / 'batdat_sources.json').read_text(encoding='utf-8'))
        cls.source = (HOME / cls.manifest['original']).read_bytes()
        cls.table = json.loads((HOME / 'XENOSAGA KOR-JPN.json').read_text(encoding='utf-8-sig'))['replace-table']
        cls.editor = batdat.parse_json((HOME / 'reference/editor-snapshots-20261024/batdat.json').read_text(encoding='utf-8-sig'))
        cls.legacy = batdat.parse_json((HOME / cls.manifest['legacy_editor']).read_text(encoding='utf-8-sig'))
        cls.sections = batdat.read_sections(cls.source)

    def fresh(self):
        return batdat.extract_document(self.source)

    def test_original_hash_and_unmodified_roundtrip(self):
        self.assertEqual(hashlib.sha256(self.source).hexdigest(), self.manifest['original_sha256'])
        result, details = batdat.rebuild(self.source, self.fresh(), self.table)
        self.assertEqual(result, self.source)
        self.assertEqual(len(result), 127836)
        self.assertEqual(sum(section['changed_fields'] for section in details), 0)

    def test_all_record_counts_and_pool_coverage(self):
        counts = (17, 177, 98, 612, 88, 88, 54, 64, 16, 32, 120, 128, 174, 80, 32, 16, 16, 46, 55, 59)
        self.assertEqual(tuple(len(section['records']) for section in self.sections), counts)
        self.assertEqual(sum(counts), 1972)
        total = 0
        for section in self.sections:
            cursor = section['pool_start']
            for record in section['records']:
                for field in record:
                    self.assertEqual(cursor, section['base'] + u16(self.source, field['ptr_pos']))
                    cursor = self.source.index(b'\0', cursor, section['end']) + 1
                    total += 1
            self.assertLessEqual(section['end'] - cursor, 3)
            self.assertEqual(self.source[cursor:section['end']], b'\0' * (section['end'] - cursor))
        self.assertEqual(total, 3040)

    def test_all_legacy_translations_preserved_by_real_field(self):
        current = {}
        for label, section in self.editor.items():
            for entry in section['entries']:
                fields = ('name',) if section['sec_type'] == 'name_only' else ('name', 'desc')
                for field in fields:
                    key = 'ko' if len(fields) == 1 else 'ko_' + field
                    current[(label, entry['ptr_pos'] + (2 if field == 'desc' else 0))] = entry[key]
        changed = 0
        bogus = 0
        for label, section in self.legacy.items():
            for entry in section['entries']:
                fields = ('name',) if section['sec_type'] == 'name_only' else ('name', 'desc')
                for field in fields:
                    key = 'ko' if len(fields) == 1 else 'ko_' + field
                    jp = key.replace('ko', 'jp', 1)
                    address = (label, entry['ptr_pos'] + (2 if field == 'desc' else 0))
                    if address in current:
                        self.assertEqual(current[address], entry[key])
                        changed += entry[key] != entry[jp]
                    else:
                        self.assertEqual(entry[key], entry[jp])
                        self.assertEqual(label, 'TEC 1')
                        bogus += 1
        self.assertEqual(changed, 1005)
        self.assertEqual(bogus, 144)
        migration = json.loads((HOME / 'batdat_migration.json').read_text(encoding='utf-8'))
        self.assertEqual(len(migration['restored_original_fields']), 268)
        for item in migration['restored_original_fields']:
            entry = self.editor[item['section']]['entries'][item['idx']]
            self.assertEqual(entry[item['field']], item['jp'])

    def test_missing_final_names_restored(self):
        for index, expected in ((0, '\u4e88\u5099'), (1, 'SKJ_008')):
            label = self.sections[index]['label']
            self.assertEqual(len(self.editor[label]['entries']), len(self.legacy[label]['entries']) + 1)
            self.assertEqual(self.editor[label]['entries'][-1]['ko'], expected)

    def test_tec1_stride_and_all_untranslated_names_recovered(self):
        section = self.editor['TEC 1']
        self.assertEqual(section['stride'], 20)
        self.assertEqual(len(section['entries']), 128)
        for index, entry in enumerate(section['entries']):
            self.assertEqual(entry['ptr_pos'], section['base'] + index * 20)
            self.assertEqual(entry['ko_name'], entry['jp_name'])
            self.assertEqual(entry['ko_desc'], entry['jp_desc'])
            self.assertNotIn('\ufffd', entry['jp_name'] + entry['jp_desc'])

    def test_current_build_all_references_and_pair_adjacency(self):
        result, details = batdat.rebuild(self.source, self.editor, self.table)
        self.assertEqual(sum(item['changed_fields'] for item in details), 1005)
        for section in self.sections:
            entries = self.editor[section['label']]['entries']
            for index, record in enumerate(section['records']):
                cursor = None
                for field in record:
                    key = 'ko' if len(record) == 1 else 'ko_' + field['field']
                    text = entries[index][key]
                    if text.endswith('[menu_sita]'):
                        text = text[:-11].replace(' ', '\u3001').replace('@', ' ')
                    expected = ''.join(self.table.get(char, char) for char in text).encode(batdat.ENCODING)
                    address = section['base'] + u16(result, field['ptr_pos'])
                    self.assertEqual(nul(result, address), expected)
                    if cursor is not None:
                        self.assertEqual(address, cursor)
                    cursor = address + len(expected) + 1

    def test_header_stats_and_nontext_sections_unchanged(self):
        result, _ = batdat.rebuild(self.source, self.editor, self.table)
        allowed = []
        for section in self.sections:
            allowed.append((section['pool_start'], section['end']))
            allowed.extend((field['ptr_pos'], field['ptr_pos'] + 2)
                           for record in section['records'] for field in record)
        cursor = 0
        for start, end in sorted(allowed):
            self.assertEqual(result[cursor:start], self.source[cursor:start])
            cursor = end
        self.assertEqual(result[cursor:], self.source[cursor:])
        self.assertEqual(result[:120], self.source[:120])
        self.assertEqual(len(result), len(self.source))

    def test_combo_and_description_empty_refs_follow_repacked_names(self):
        result, _ = batdat.rebuild(self.source, self.editor, self.table)
        checked = 0
        moved = 0
        for section in (self.sections[8], self.sections[9]):
            for name, desc in section['records']:
                self.assertEqual(desc['raw'], b'')
                name_addr = section['base'] + u16(result, name['ptr_pos'])
                desc_addr = section['base'] + u16(result, desc['ptr_pos'])
                self.assertEqual(desc_addr, result.index(b'\0', name_addr) + 1)
                self.assertEqual(nul(result, desc_addr), b'')
                moved += u16(result, desc['ptr_pos']) != desc['relative']
                checked += 1
        self.assertEqual(checked, 48)
        self.assertGreater(moved, 0)

    def test_tec2_overflow_is_resolved_without_text_changes(self):
        result, details = batdat.rebuild(self.source, self.editor, self.table)
        info = next(item for item in details if item['section'] == 'TEC 2')
        self.assertEqual((info['pool_capacity'], info['pool_bytes'], info['free_bytes']), (8708, 8700, 8))
        self.assertEqual((info['sharing_saved_bytes'], info['shared_records']), (9, 3))
        entry = self.editor['TEC 2']['entries'][22]
        expected = batdat.encode_text(entry['ko_name'], self.table)
        self.assertEqual(nul(result, self.editor['TEC 2']['base'] + u16(result, entry['ptr_pos'])), expected)

    def test_pool_sharing_only_complete_identical_records(self):
        records = [[b'A', b'B'], [b'A', b'C'], [b'A', b'B']]
        pool, offsets, shared = batdat.pack_pool(records, 10, True)
        self.assertEqual(pool, b'A\0B\0A\0C\0')
        self.assertEqual(offsets, [[10, 12], [14, 16], [10, 12]])
        self.assertEqual(shared, 1)

    def test_sharing_not_enabled_when_pool_already_fits(self):
        _, details = batdat.rebuild(self.source, self.editor, self.table)
        self.assertTrue(all(item['shared_records'] == 0 for item in details if item['section'] != 'TEC 2'))

    def test_unmodified_sections_are_byte_identical(self):
        result, details = batdat.rebuild(self.source, self.editor, self.table)
        for section, info in zip(self.sections, details):
            if info['changed_fields'] == 0:
                self.assertEqual(result[section['base']:section['end']], self.source[section['base']:section['end']])

    def test_reordered_sections_and_entries_are_equivalent(self):
        edited = copy.deepcopy(dict(reversed(list(self.editor.items()))))
        for section in edited.values():
            section['entries'].reverse()
        self.assertEqual(batdat.rebuild(self.source, edited, self.table), batdat.rebuild(self.source, self.editor, self.table))

    def test_empty_string_and_shorter_prefix_are_real_edits(self):
        label = self.sections[0]['label']
        for value in ('', 'KOS'):
            document = self.fresh()
            entry = document[label]['entries'][4]
            entry['ko'] = value
            result, details = batdat.rebuild(self.source, document, self.table)
            self.assertEqual(nul(result, document[label]['base'] + u16(result, entry['ptr_pos'])), value.encode())
            self.assertEqual(sum(item['changed_fields'] for item in details), 1)

    def test_scalar_equal_to_pointer_is_not_rewritten(self):
        data = bytearray(self.source)
        field = self.sections[0]['records'][0][0]
        scalar = field['ptr_pos'] + 2
        struct.pack_into('<H', data, scalar, field['relative'])
        document = batdat.extract_document(data)
        document[self.sections[0]['label']]['entries'][0]['ko'] = 'A'
        result, _ = batdat.rebuild(data, document, self.table)
        self.assertEqual(result[scalar:scalar + 2], data[scalar:scalar + 2])

    def test_menu_sita_and_punctuation_preservation(self):
        self.assertEqual(batdat.encode_text(' <A> "B"\\n@C[menu_sita]', {}),
                         '\u3001<A>\u3001"B"\\n C'.encode(batdat.ENCODING))
        self.assertEqual(batdat.encode_text(' A @ B[menu_sita]X ', {}), b' A @ B[menu_sita]X ')
        self.assertEqual(batdat.encode_text(' A\n\nB\\n ', {}), b' A\n\nB\\n ')

    def test_bad_characters_and_embedded_nul_fail(self):
        for value in ('\U0001f9ea', '\u2014', '\ufffd', '\0'):
            document = self.fresh()
            document[self.sections[0]['label']]['entries'][0]['ko'] = value
            with self.subTest(value=ascii(value)), self.assertRaises(ValueError):
                batdat.rebuild(self.source, document, self.table)

    def test_overflow_cannot_silently_skip_one_section(self):
        document = self.fresh()
        document[self.sections[-1]['label']]['entries'][0]['ko_desc'] = 'X' * 12000
        with self.assertRaisesRegex(ValueError, 'pool overflow'):
            batdat.rebuild(self.source, document, self.table)

    def test_uint16_pointer_overflow_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'uint16'):
            batdat.pack_pool([[b'A', b'B']], 65535, False)

    def test_missing_duplicate_and_unknown_entries_fail(self):
        label = self.sections[0]['label']
        documents = []
        for action in ('missing', 'duplicate', 'unknown', 'boolean'):
            document = self.fresh()
            entries = document[label]['entries']
            if action == 'missing':
                entries.pop()
            elif action == 'duplicate':
                entries.append(copy.deepcopy(entries[0]))
            else:
                entries[0]['idx'] = 999 if action == 'unknown' else False
            documents.append(document)
        for document in documents:
            with self.assertRaises(ValueError):
                batdat.rebuild(self.source, document, self.table)

    def test_source_metadata_and_original_text_are_read_only(self):
        label = self.sections[0]['label']
        mutations = [('base', 0), ('stride', 28), ('hdr_off', 0), ('end_sec', 0), ('sec_type', 'name_desc')]
        for key, value in mutations:
            document = self.fresh()
            document[label][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                batdat.rebuild(self.source, document, self.table)
        for key, value in (('ptr_pos', 0), ('name_ptr', 0), ('end_ptr', 999), ('jp', 'bad'), ('ko', None)):
            document = self.fresh()
            document[label]['entries'][0][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                batdat.rebuild(self.source, document, self.table)

    def test_json_structure_and_duplicate_keys_fail(self):
        with self.assertRaisesRegex(ValueError, 'Duplicate JSON'):
            batdat.parse_json('{"key":1,"key":2}')
        with self.assertRaises(ValueError):
            batdat.parse_json('{bad}')
        label = self.sections[0]['label']
        for variant in ('root', 'missing_section', 'unknown_section', 'missing_field', 'unknown_field'):
            document = self.fresh()
            if variant == 'root':
                document = []
            elif variant == 'missing_section':
                document.pop(label)
            elif variant == 'unknown_section':
                document['unknown'] = {}
            elif variant == 'missing_field':
                document[label]['entries'][0].pop('ko')
            else:
                document[label]['entries'][0]['unknown'] = ''
            with self.subTest(variant=variant), self.assertRaises(ValueError):
                batdat.rebuild(self.source, document, self.table)

    def test_corrupt_original_fails(self):
        cases = [self.source[:80]]
        for offset, fmt, value in ((0, '<I', 20), (4, '<I', 1), (8, '<I', 0),
                                   (12, '<I', 120), (self.sections[0]['records'][0][0]['ptr_pos'], '<H', 953)):
            data = bytearray(self.source)
            struct.pack_into(fmt, data, offset, value)
            cases.append(data)
        data = bytearray(self.source)
        data[self.sections[0]['pool_start']] = 0xff
        cases.append(data)
        for data in cases:
            with self.assertRaises((ValueError, UnicodeError)):
                batdat.read_sections(data)

    def test_bad_late_translation_publishes_nothing(self):
        document = self.fresh()
        document[self.sections[-1]['label']]['entries'][0]['ko_desc'] = 'X' * 12000
        bad_path = (HOME / self.manifest['edit']).resolve()
        real_read = Path.read_text
        def damaged(path, *args, **kwargs):
            return json.dumps(document) if path == bad_path else real_read(path, *args, **kwargs)
        with patch.object(Path, 'read_text', damaged), patch.object(build_batdat, 'write_output') as save:
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(build_batdat.main([]), 1)
            save.assert_not_called()

    def test_source_or_charmap_hash_failure_publishes_nothing(self):
        real_read = Path.read_bytes
        for relative in (self.manifest['original'], self.manifest['charmap']):
            bad_path = (HOME / relative).resolve()
            def damaged(path):
                data = real_read(path)
                return data + b'BAD' if path == bad_path else data
            with patch.object(Path, 'read_bytes', damaged), patch.object(build_batdat, 'write_output') as save:
                with contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(build_batdat.main([]), 1)
                save.assert_not_called()

    def test_check_mode_does_not_publish(self):
        with patch.object(build_batdat, 'write_output') as save, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(build_batdat.main(['--check']), 0)
            save.assert_not_called()

    def test_pending_write_failure_returns_failure(self):
        with patch.object(build_batdat, 'write_output', side_effect=FileExistsError('pending')):
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(build_batdat.main([]), 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
