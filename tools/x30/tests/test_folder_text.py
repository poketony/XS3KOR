"""Local menu/database/minigame/PSE workflows and extraction safety."""

import contextlib
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import tempfile

import build_menu
import build_database
import build_minigame
import build_pse
from build_menu import HOME, input_path
from tools.output import validate_outputs


def fixture(test):
    temporary = tempfile.TemporaryDirectory(dir=HOME, prefix='test-folder-')
    test.addCleanup(temporary.cleanup)
    return Path(temporary.name)


def cases():
    return ((build_menu, ['--asset', 'devchk']), (build_database, []),
            (build_minigame, ['--asset', 'Message.Dat']),
            (build_minigame, ['--asset', 'World.Dat']), (build_pse, ['--asset', 'EP1']))


class FolderTextTests(unittest.TestCase):
    def test_all_outputs_are_original_name_plus_new_in_working_folder(self):
        results = build_menu.prepare(build_menu.NAMES)+build_pse.prepare()
        for _, output, _, inputs in results:
            self.assertEqual(output, inputs[0].with_name(inputs[0].name+'.new'))
            self.assertEqual(output.parent, inputs[1].parent)
            self.assertEqual(output.parent, inputs[2].parent)
            self.assertTrue(output.is_relative_to(HOME.parents[1] / '0.X30'))
        database, inputs, _ = build_database.prepare()
        for item, source in zip(database, inputs):
            self.assertEqual(item[1], source.with_name(source.name+'.new'))
        for name in build_minigame.ASSETS:
            output, _, inputs = build_minigame.prepare(asset=name)
            self.assertEqual(output, inputs[0].with_name(inputs[0].name+'.new'))
            self.assertEqual(output.parent, inputs[2].parent)

    def test_all_extractors_roundtrip_without_reading_existing_editors(self):
        paths = set()
        for file in ('sources.json', 'pse_sources.json', 'minigame_sources.json', 'world_sources.json'):
            config = json.loads((HOME / file).read_text(encoding='utf-8'))
            assets = config['assets'].values() if 'assets' in config else (config,)
            paths.update(input_path(row['edit']) for row in assets if 'edit' in row)
        real_read = Path.read_text
        def read(path, *args, **kwargs):
            if path in paths:
                raise AssertionError(f'Extraction depends on existing translation: {path}')
            return real_read(path, *args, **kwargs)
        with patch.object(Path, 'read_text', read):
            menu = build_menu.prepare(build_menu.NAMES, extract=True)
            pse = build_pse.prepare(extract=True)
            database, _, _ = build_database.prepare(extract=True)
            mini = [build_minigame.prepare(asset=name, extract=True) for name in build_minigame.ASSETS]
        self.assertEqual(len(menu)+len(pse)+len(database)+len(mini), 18)
        for _, output, data, inputs in menu+pse:
            self.assertIn(output, paths)
            self.assertTrue(data.decode('utf-8'))
            self.assertNotIn(output, inputs)

    def test_existing_translation_refusal_happens_before_any_write(self):
        for builder, arguments in cases():
            with self.subTest(builder=builder.__name__, args=arguments):
                with patch.object(builder, 'write_output') as write, contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(builder.main(arguments+['--extract']), 1)
                    write.assert_not_called()

    def test_extract_check_never_writes(self):
        for builder, arguments in cases():
            with patch.object(builder, 'write_output') as write, contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(builder.main(arguments+['--extract', '--check']), 0)
                write.assert_not_called()

    def test_extract_rejects_dropped_txt(self):
        for builder, arguments in cases():
            with patch.object(builder, 'write_output') as write, contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(builder.main(arguments+['--extract', 'not-a-source.txt']), 1)
                write.assert_not_called()

    def test_each_extractor_can_create_a_new_editor_and_refuses_overwrite(self):
        folder = fixture(self)
        menu = build_menu.prepare(('devchk',), extract=True)
        pse = build_pse.prepare(('EP1',), extract=True)
        db, db_inputs, details = build_database.prepare(extract=True)
        mini = build_minigame.prepare(extract=True)
        prepared = (
            (build_menu, ['--asset', 'devchk'], [(menu[0][0], folder/'menu.txt', menu[0][2], menu[0][3])]),
            (build_pse, ['--asset', 'EP1'], [(pse[0][0], folder/'pse.txt', pse[0][2], pse[0][3])]),
            (build_database, [], ([(db[0][0], folder/'database.txt', db[0][2])], db_inputs, details)),
            (build_minigame, [], (folder/'mini.txt', mini[1], mini[2])),
        )
        for builder, args, result in prepared:
            with patch.object(builder, 'prepare', return_value=result):
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(builder.main(args+['--extract']), 0)
                with contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(builder.main(args+['--extract']), 1)
        self.assertEqual((folder/'menu.txt').read_bytes(), menu[0][2])
        self.assertEqual((folder/'pse.txt').read_bytes(), pse[0][2])
        self.assertEqual((folder/'database.txt').read_bytes(), db[0][2])
        self.assertEqual((folder/'mini.txt').read_bytes(), mini[1])
        self.assertEqual(len(list(folder.iterdir())), 4)

    def test_late_extract_collision_does_not_publish_earlier_files(self):
        for builder in (build_menu, build_pse):
            folder = fixture(self)
            output, existing = folder/'first.txt', folder/'last.txt'
            existing.write_bytes(b'KEEP')
            result = [('first', output, b'NEW', ()), ('last', existing, b'NEW', ())]
            with patch.object(builder, 'prepare', return_value=result), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(builder.main(['--extract']), 1)
            self.assertFalse(output.exists())
            self.assertEqual(existing.read_bytes(), b'KEEP')

    def test_changed_local_mapping_fails_for_every_text_builder(self):
        real_read = Path.read_bytes
        def read(path):
            data = real_read(path)
            if path.name == 'XENOSAGA KOR-JPN.json' and not path.is_relative_to(HOME):
                return data+b'CHANGED'
            return data
        for builder, args in cases():
            with patch.object(Path, 'read_bytes', read), patch.object(builder, 'write_output') as write:
                with contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(builder.main(args), 1)
                write.assert_not_called()

    def test_missing_local_source_has_no_snapshot_fallback(self):
        real_read = Path.read_bytes
        def read(path):
            if path.suffix.lower() in ('.bin', '.txd', '.dat', '.mes') and not path.is_relative_to(HOME):
                raise FileNotFoundError(path)
            return real_read(path)
        for builder, args in cases():
            with patch.object(Path, 'read_bytes', read), patch.object(builder, 'write_output') as write:
                with contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(builder.main(args), 1)
                write.assert_not_called()


class OutputPreflightTests(unittest.TestCase):
    def test_duplicate_output_and_input_alias_are_rejected(self):
        folder = fixture(self)
        source, output = folder/'source', folder/'output'
        source.write_bytes(b'KEEP')
        for paths in ((output, output), (source,)):
            with self.assertRaises(ValueError):
                validate_outputs(paths, (source,))

    def test_pending_output_is_rejected_before_publication(self):
        folder = fixture(self)
        output = folder/'output'
        output.with_name(output.name+'.pending').write_bytes(b'INTERRUPTED')
        with self.assertRaises(FileExistsError):
            validate_outputs((output,))
        self.assertFalse(output.exists())

    def test_matching_file_identity_is_rejected(self):
        folder = fixture(self)
        source, alias = folder/'source', folder/'alias'
        source.write_bytes(b'KEEP')
        alias.write_bytes(b'KEEP')
        real_stat = Path.stat
        # The Windows sandbox denies hardlink creation; emulate its stat identity.
        def stat(path, *args, **kwargs):
            return real_stat(source if path == alias else path, *args, **kwargs)
        with patch.object(Path, 'stat', stat):
            with self.assertRaises(ValueError):
                validate_outputs((alias,), (source,))
            with self.assertRaises(ValueError):
                validate_outputs((source, alias))


if __name__ == '__main__':
    unittest.main()
