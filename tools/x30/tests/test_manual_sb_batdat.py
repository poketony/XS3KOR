"""Canonical working inputs, explicit drops and strict legacy-format compatibility."""

import copy
import json
from pathlib import Path
import tempfile
import unittest

import build_sb
import build_batdat
from build_menu import HOME, input_path
from tools import sb_text, batdat_text, batdat_legacy


class ManualSBTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((HOME / 'sb_sources.json').read_text(encoding='utf-8'))
        cls.table = json.loads((HOME / 'XENOSAGA KOR-JPN.json').read_text(encoding='utf-8-sig'))['replace-table']

    def test_canonical_group_inputs_are_used(self):
        for name, _, _, protected in build_sb.prepare(group='bat'):
            self.assertEqual(protected[1], HOME.parents[1] / '0.X30/bat/kr' / (name.split('/')[1]+'.txt'))

    def test_all_38_known_omissions_restore_original_first_row(self):
        for item in self.manifest['restored_first_rows']:
            name = item['asset']
            asset = self.manifest['assets'][name]
            original = (HOME / asset['original']).read_bytes()
            fixture = sb_text.extract_text(original)
            entries = sb_text.parse_text(fixture)
            del entries[int(item['address'], 16)]
            legacy = ''.join(f'[{address:#x}]\n'+text.replace('\n', '[n]')+'\n\n' for address, text in entries.items())
            normalized = build_sb.normalize_editor(original, legacy, item)
            self.assertEqual(sb_text.parse_text(normalized), sb_text.parse_text(fixture))

    def test_explicit_first_translation_is_not_overwritten(self):
        item = self.manifest['restored_first_rows'][0]
        source = (HOME / self.manifest['assets'][item['asset']]['original']).read_bytes()
        text = sb_text.extract_text(source)
        text = text.replace(item['text'], 'TEST', 1)
        self.assertEqual(build_sb.normalize_editor(source, text, item), text)
        self.assertNotEqual(sb_text.rebuild(source, text, self.table), source)

    def test_other_missing_rows_still_fail(self):
        item = self.manifest['restored_first_rows'][0]
        source = (HOME / self.manifest['assets'][item['asset']]['original']).read_bytes()
        entries = sb_text.parse_text(sb_text.extract_text(source))
        del entries[list(entries)[1]]
        text = ''.join(f'[{address:#x}]\n'+value.replace('\n', '[n]')+'\n\n' for address, value in entries.items())
        with self.assertRaises(ValueError):
            sb_text.rebuild(source, build_sb.normalize_editor(source, text, item), self.table)

    def test_drop_uses_edited_text_not_a_snapshot(self):
        asset = self.manifest['assets']['cf/8050']
        original = (HOME / asset['original']).read_bytes()
        entries = sb_text.parse_text(sb_text.extract_text(original))
        entries[next(iter(entries))] = 'TEST'
        content = ''.join(f'[{address:#x}]\n'+value.replace('\n', '[n]')+'\n\n' for address, value in entries.items())
        with tempfile.TemporaryDirectory(dir=HOME) as directory:
            path = Path(directory) / '8050.txt'
            path.write_text(content, encoding='utf-8')
            result = build_sb.prepare(group='cf', editors=[path])[0]
            self.assertEqual(result[2], sb_text.rebuild(original, content, self.table))
            self.assertEqual(result[3][1], path)
            self.assertEqual(path.read_text(encoding='utf-8'), content)

    def test_multiple_drops_select_only_the_supplied_assets(self):
        paths = [input_path(self.manifest['assets']['cf/'+name]['edit']) for name in ('8050', '8065')]
        self.assertEqual([r[0] for r in build_sb.prepare(group='cf', editors=paths)], ['cf/8050', 'cf/8065'])

    def test_bad_missing_duplicate_and_wrong_group_drops_fail(self):
        path = input_path(self.manifest['assets']['cf/8050']['edit'])
        with self.assertRaises(FileNotFoundError):
            build_sb.prepare(editors=[HOME / '__missing__/8050.txt'])
        with self.assertRaises(ValueError):
            build_sb.prepare(editors=[path, path])
        with self.assertRaises(ValueError):
            build_sb.prepare(group='bat', editors=[path])

    def test_unconfigured_sb_files_have_only_empty_or_known_script_labels(self):
        labels = {'--- Battle Start ---', '--- default ---', '--- default dmg ---',
                  '--- main ---', '--- sol003 ---', '--- sol005 ---', '--- top012 ---',
                  'B01', 'B02', 'B03', 'B08'}
        for name, asset in self.manifest['assets'].items():
            if 'edit' not in asset:
                rows = sb_text.read_rows((HOME / asset['original']).read_bytes())
                self.assertTrue({row['text'] for row in rows} <= labels, name)

    def test_new_battle_editors_are_registered_and_original_extraction_is_lossless(self):
        assets = {name: asset for name, asset in self.manifest['assets'].items()
                  if asset.get('editor_origin') == 'japanese-original-extraction'}
        self.assertEqual(len(assets), 24)
        for name, asset in assets.items():
            data = (HOME / asset['original']).read_bytes()
            self.assertTrue(input_path(asset['edit']).is_file(), name)
            self.assertEqual(sb_text.rebuild(data, sb_text.extract_text(data), self.table), data)

    def test_new_battle_dialogue_translation_is_used_without_editor_rewrite(self):
        name = 'bat/MIK_B12'
        data = (HOME / self.manifest['assets'][name]['original']).read_bytes()
        rows = sb_text.read_rows(data)
        entries = sb_text.parse_text(sb_text.extract_text(data))
        dialogue = next(row for row in rows if row['editable'] and any(ord(c) > 127 for c in row['text']))
        entries[dialogue['address']] = '\uc2dc\uc628 TEST'
        content = ''.join(f'[{address:#x}]\n'+value.replace('\n', '[n]')+'\n\n' for address, value in entries.items())
        with tempfile.TemporaryDirectory(dir=HOME) as directory:
            path = Path(directory) / 'MIK_B12.txt'
            path.write_text(content, encoding='utf-8')
            result = build_sb.prepare(group='bat', editors=[path])[0]
            self.assertEqual(result[0], name)
            self.assertEqual(result[2], sb_text.rebuild(data, content, self.table))
            self.assertNotEqual(result[2], data)
            self.assertEqual(path.read_text(encoding='utf-8'), content)


class ManualBatdatTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((HOME / 'batdat_sources.json').read_text(encoding='utf-8'))
        cls.source = (HOME / cls.manifest['original']).read_bytes()
        cls.legacy = batdat_text.parse_json((HOME / cls.manifest['legacy_editor']).read_text(encoding='utf-8-sig'))
        cls.corrected = batdat_text.parse_json((HOME / 'reference/editor-snapshots-20261024/batdat.json').read_text(encoding='utf-8-sig'))
        cls.table = json.loads((HOME / 'XENOSAGA KOR-JPN.json').read_text(encoding='utf-8-sig'))['replace-table']

    def test_canonical_json_is_used_without_modification(self):
        path = input_path(self.manifest['edit'])
        before = path.read_bytes()
        _, _, protected, _ = build_batdat.prepare()
        self.assertEqual(protected[1], HOME.parents[1] / '0.X30/bat/kr/batdatEdit/batdat.json')
        self.assertEqual(path.read_bytes(), before)

    def test_legacy_normalization_matches_full_verified_document(self):
        before = copy.deepcopy(self.legacy)
        self.assertEqual(batdat_legacy.normalize(self.source, self.legacy, self.legacy), self.corrected)
        self.assertEqual(self.legacy, before)

    def test_reordered_legacy_entries_preserve_every_translation(self):
        reordered = copy.deepcopy(self.legacy)
        for section in reordered.values():
            section['entries'].reverse()
        self.assertEqual(batdat_legacy.normalize(self.source, reordered, self.legacy), self.corrected)

    def test_translated_false_legacy_field_is_rejected(self):
        migration = json.loads((HOME / 'batdat_migration.json').read_text(encoding='utf-8'))
        item = migration['discarded_untranslated_false_fields'][0]
        document = copy.deepcopy(self.legacy)
        entry = next(e for e in document[item['section']]['entries'] if e['idx'] == item['old_idx'])
        entry[item['field']] = 'TEST'
        with self.assertRaisesRegex(ValueError, 'no real target'):
            batdat_legacy.normalize(self.source, document, self.legacy)

    def test_changed_metadata_is_not_silently_repaired(self):
        document = copy.deepcopy(self.legacy)
        label = next(iter(document))
        document[label]['base'] += 1
        normalized = batdat_legacy.normalize(self.source, document, self.legacy)
        with self.assertRaises(ValueError):
            batdat_text.rebuild(self.source, normalized, self.table)

    def test_duplicate_legacy_ids_rejected(self):
        document = copy.deepcopy(self.legacy)
        section = next(iter(document.values()))
        section['entries'].append(copy.deepcopy(section['entries'][0]))
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            batdat_legacy.normalize(self.source, document, self.legacy)

    def test_new_translation_in_both_formats_is_used(self):
        for document in (self.legacy, self.corrected):
            edited = copy.deepcopy(document)
            section = next(iter(edited.values()))
            section['entries'][0]['ko'] = 'TEST'
            expected_document = batdat_legacy.normalize(self.source, edited, self.legacy)
            expected, _ = batdat_text.rebuild(self.source, expected_document, self.table)
            with tempfile.TemporaryDirectory(dir=HOME) as directory:
                path = Path(directory) / 'edited.json'
                content = json.dumps(edited, ensure_ascii=False)
                path.write_text(content, encoding='utf-8')
                _, data, protected, _ = build_batdat.prepare(path)
                self.assertEqual(data, expected)
                self.assertEqual(protected[1], path)
                self.assertEqual(path.read_text(encoding='utf-8'), content)

    def test_missing_drop_fails(self):
        with self.assertRaises(FileNotFoundError):
            build_batdat.prepare(HOME / '__missing_editor__.json')

    def test_export_preserves_current_translations_and_restores_all_fields(self):
        editor = input_path(self.manifest['edit'])
        before = editor.read_bytes()
        (HOME / 'output').mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=HOME / 'output') as directory:
            path, source = build_batdat.export_editor(Path(directory) / 'expanded.json')
            self.assertEqual(source, editor)
            self.assertEqual(editor.read_bytes(), before)
            document = batdat_text.parse_json(path.read_text(encoding='utf-8'))
            expected = batdat_legacy.normalize(self.source, batdat_text.parse_json(before.decode('utf-8-sig')), self.legacy)
            self.assertEqual(document, expected)
            self.assertEqual(build_batdat.prepare(path)[1], build_batdat.prepare()[1])

    def test_export_refuses_existing_files_and_working_editor_paths(self):
        (HOME / 'output').mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=HOME / 'output') as directory:
            path = Path(directory) / 'existing.json'
            path.write_bytes(b'preserve this')
            with self.assertRaises(FileExistsError):
                build_batdat.export_editor(path)
            self.assertEqual(path.read_bytes(), b'preserve this')
        with self.assertRaises(ValueError):
            build_batdat.export_editor(input_path(self.manifest['edit']))

    def test_export_does_not_publish_invalid_legacy_translation(self):
        migration = json.loads((HOME / 'batdat_migration.json').read_text(encoding='utf-8'))
        item = migration['discarded_untranslated_false_fields'][0]
        document = copy.deepcopy(self.legacy)
        entry = next(e for e in document[item['section']]['entries'] if e['idx'] == item['old_idx'])
        entry[item['field']] = 'TEST'
        (HOME / 'output').mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=HOME / 'output') as directory:
            source = Path(directory) / 'invalid.json'
            source.write_text(json.dumps(document, ensure_ascii=False), encoding='utf-8')
            destination = Path(directory) / 'expanded.json'
            with self.assertRaisesRegex(ValueError, 'no real target'):
                build_batdat.export_editor(destination, source)
            self.assertFalse(destination.exists())


if __name__ == '__main__':
    unittest.main()
