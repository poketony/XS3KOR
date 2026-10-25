"""Working-folder source/output contracts and non-destructive extraction."""

import contextlib
import hashlib
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import tempfile

import build_sb
import build_batdat
from build_menu import HOME, input_path
from tools import sb_text, batdat_text


def fixture(test):
    temporary = tempfile.TemporaryDirectory(dir=HOME, prefix='test-folder-')
    test.addCleanup(temporary.cleanup)
    return Path(temporary.name)


class FolderSBTests(unittest.TestCase):
    def test_uses_working_original_mapping_and_new_suffix(self):
        for name in ('cf/8050', 'bat/REN_B01'):
            _, output, _, inputs = build_sb.prepare(asset_name=name)[0]
            group, stem = name.split('/')
            folder = HOME.parents[1] / '0.X30' / group / 'kr'
            self.assertEqual(inputs[0], folder / (stem+'.sb'))
            self.assertEqual(inputs[1], folder / (stem+'.txt'))
            self.assertEqual(inputs[2], folder / 'XENOSAGA KOR-JPN.json')
            self.assertEqual(output, folder / (stem+'.sb.new'))

    def test_extract_does_not_read_translation_and_is_lossless(self):
        manifest = json.loads((HOME / 'sb_sources.json').read_text(encoding='utf-8'))
        for name in ('cf/8050', manifest['restored_first_rows'][0]['asset'], 'bat/REN_B01'):
            editor = input_path(manifest['assets'][name]['edit'])
            real_read = Path.read_text
            def read(path, *args, **kwargs):
                if path == editor:
                    raise AssertionError('Extractor must not depend on an existing translation')
                return real_read(path, *args, **kwargs)
            with patch.object(Path, 'read_text', read):
                _, output, data, inputs = build_sb.prepare(asset_name=name, extract=True)[0]
            original = inputs[0].read_bytes()
            self.assertEqual(output, editor)
            self.assertEqual(sb_text.rebuild(original, data.decode('utf-8'), {}), original)

    def test_extract_preflights_whole_batch_and_preserves_translation(self):
        folder = fixture(self)
        empty, existing = folder / 'first.txt', folder / 'second.txt'
        existing.write_bytes(b'WORK IN PROGRESS')
        results = [('first', empty, b'new', ()), ('second', existing, b'new', ())]
        with patch.object(build_sb, 'prepare', return_value=results), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(build_sb.main(['--extract']), 1)
        self.assertFalse(empty.exists())
        self.assertEqual(existing.read_bytes(), b'WORK IN PROGRESS')

    def test_extract_creates_only_named_txt_and_refuses_second_run(self):
        folder = fixture(self)
        _, _, data, inputs = build_sb.prepare(asset_name='cf/8050', extract=True)[0]
        output = folder / '8050.txt'
        results = [('cf/8050', output, data, inputs)]
        with patch.object(build_sb, 'prepare', return_value=results):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(build_sb.main(['--extract']), 0)
            self.assertEqual(output.read_bytes(), data)
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(build_sb.main(['--extract']), 1)
        self.assertEqual(list(folder.iterdir()), [output])

    def test_check_and_drop_only_do_not_publish(self):
        with patch.object(build_sb, 'write_output') as save:
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(build_sb.main(['--extract', '--asset', 'cf/8050', '--check']), 0)
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(build_sb.main(['--group', 'cf', '--require-editors']), 1)
            save.assert_not_called()

    def test_changed_local_mapping_is_rejected(self):
        target = HOME.parents[1] / '0.X30/cf/kr/XENOSAGA KOR-JPN.json'
        real_read = Path.read_bytes
        def read(path):
            data = real_read(path)
            return data+b'changed' if path == target else data
        with patch.object(Path, 'read_bytes', read):
            with self.assertRaisesRegex(ValueError, 'hash mismatch'):
                build_sb.prepare(asset_name='cf/8050')


class FolderBatdatTests(unittest.TestCase):
    def test_working_original_mapping_and_new_suffix(self):
        output, _, inputs, _ = build_batdat.prepare()
        folder = HOME.parents[1] / '0.X30/bat/kr/batdatEdit'
        self.assertEqual(inputs[:3], (folder / 'batdat.bin', folder / 'batdat.json', folder / 'XENOSAGA KOR-JPN.json'))
        self.assertEqual(output, folder / 'batdat.bin.new')

    def test_extract_creates_lossless_json_and_refuses_existing(self):
        config = json.loads((HOME / 'batdat_sources.json').read_text(encoding='utf-8'))
        folder = fixture(self)
        source, editor = folder / 'batdat.bin', folder / 'batdat.json'
        source.write_bytes(input_path(config['original']).read_bytes())
        targets = {config['original']: source, config['edit']: editor}
        before = source.read_bytes()
        with patch.object(build_batdat, 'input_path', side_effect=targets.__getitem__):
            self.assertEqual(build_batdat.extract_editor(check=True), editor)
            self.assertFalse(editor.exists())
            self.assertEqual(build_batdat.extract_editor(), editor)
            document = batdat_text.parse_json(editor.read_text(encoding='utf-8'))
            self.assertEqual(batdat_text.rebuild(before, document, {})[0], before)
            editor.write_bytes(b'MY TRANSLATION')
            with self.assertRaises(FileExistsError):
                build_batdat.extract_editor()
            self.assertEqual(editor.read_bytes(), b'MY TRANSLATION')
        self.assertEqual(source.read_bytes(), before)

    def test_real_existing_editor_is_unchanged_by_extract_failure(self):
        config = json.loads((HOME / 'batdat_sources.json').read_text(encoding='utf-8'))
        editor = input_path(config['edit'])
        before = hashlib.sha256(editor.read_bytes()).hexdigest()
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(build_batdat.main(['--extract']), 1)
        self.assertEqual(hashlib.sha256(editor.read_bytes()).hexdigest(), before)

    def test_extract_rejects_dropped_editor_before_write(self):
        with patch.object(build_batdat, 'extract_editor') as extract, contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(build_batdat.main(['--extract', 'anything.json']), 1)
            extract.assert_not_called()


if __name__ == '__main__':
    unittest.main()
