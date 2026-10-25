"""Manual ELF selection and drop validation; preserve all existing editor bytes."""

import contextlib
import io
import os
from pathlib import Path
import unittest
from unittest.mock import patch
import tempfile

import elf_text_tool as t


class ManualEntrypointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.originals, cls.table = t.load_inputs()
        temporary = tempfile.TemporaryDirectory(dir=t.HERE, prefix='test-manual-')
        cls.addClassCleanup(temporary.cleanup)
        cls.root = Path(temporary.name)

    def editor(self, name, filename):
        path = self.root / filename
        path.write_text(t.export_text(name, self.originals[name]), encoding='utf-8')
        return path

    def invoke(self, *args, **kwargs):
        with contextlib.redirect_stdout(io.StringIO()), patch.object(t, 'publish') as publish:
            t.run(*args, **kwargs)
        return publish.call_args_list

    def test_default_build_matches_current_canonical_editors(self):
        calls = self.invoke('build')
        self.assertEqual([call.args[0] for call in calls],
                         ['output/SLPS_256.40.new', 'output/SLPS_256.41.new', 'output/OV04.OVL.new'])
        expected = {name: t.build_blob(name, data,
            t.editor_path(name).read_text(encoding='utf-8-sig'), self.table)
            for name, data in self.originals.items()}
        self.assertEqual(calls[0].args[1], expected['SLPS'])
        self.assertEqual(calls[0].args[1], calls[1].args[1])
        self.assertEqual(calls[2].args[1], expected['OV04'])

    def test_one_asset_only_publishes_selected_executable(self):
        calls = self.invoke('build', 'OV04')
        self.assertEqual(len(calls), 1)
        expected = t.build_blob('OV04', self.originals['OV04'],
            t.editor_path('OV04').read_text(encoding='utf-8-sig'), self.table)
        self.assertEqual(calls[0].args, ('output/OV04.OVL.new', expected))

    def test_custom_filename_uses_header_and_rebuilds_only_that_executable(self):
        path = self.editor('OV04', 'custom overlay.txt')
        before = path.read_bytes()
        calls = self.invoke('build', editors=[path])
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].args[0], 'output/OV04.OVL.new')
        self.assertEqual(path.read_bytes(), before)

    def test_explicit_content_reaches_output_instead_of_default_editor(self):
        path = self.editor('SLPS', 'original main.txt')
        calls = self.invoke('build', 'SLPS', [path])
        self.assertEqual(len(calls), 2)
        self.assertTrue(all(call.args[1] == self.originals['SLPS'] for call in calls))

    def test_two_drops_use_each_file_without_rewriting(self):
        paths = [self.editor(name, name+' drop.txt') for name in t.ASSETS]
        before = [p.read_bytes() for p in paths]
        calls = self.invoke('build', editors=paths)
        self.assertEqual(len(calls), 3)
        self.assertEqual(calls[0].args[1], self.originals['SLPS'])
        self.assertEqual(calls[-1].args[1], self.originals['OV04'])
        self.assertEqual([p.read_bytes() for p in paths], before)

    def test_wrong_asset_and_duplicate_drops_rejected_before_publish(self):
        path = self.editor('OV04', 'wrong asset.txt')
        for asset, editors in (('SLPS', [path]), (None, [path, path])):
            with patch.object(t, 'publish') as publish, self.assertRaises(ValueError):
                t.run('build', asset, editors)
            publish.assert_not_called()

    def test_missing_drop_does_not_fall_back(self):
        with patch.object(t, 'publish') as publish, self.assertRaises(FileNotFoundError):
            t.run('build', editors=[self.root / 'missing.txt'])
        publish.assert_not_called()

    def test_outside_or_non_txt_drop_rejected(self):
        outside = t.HERE / 'README.txt'
        with patch.object(t, 'HERE', self.root), patch.object(t, 'publish') as publish, self.assertRaises(ValueError):
            t.run('build', editors=[outside])
        publish.assert_not_called()
        for path in (t.HERE / 'elf_text_tool.py',):
            with patch.object(t, 'publish') as publish, self.assertRaises(ValueError):
                t.run('build', editors=[path])
            publish.assert_not_called()

    def test_invalid_second_drop_publishes_nothing(self):
        first = self.editor('SLPS', 'good first.txt')
        second = self.root / 'bad second.txt'
        second.write_text('# asset: OV04\nbad', encoding='utf-8')
        with contextlib.redirect_stdout(io.StringIO()), patch.object(t, 'publish') as publish, self.assertRaises(ValueError):
            t.run('build', editors=[first, second])
        publish.assert_not_called()

    def test_check_command_and_build_flag_never_publish(self):
        path = self.editor('OV04', 'check me.txt')
        for args in (['check'], ['build', '--check'],
                     ['build', '--asset', 'OV04', str(path), '--check']):
            with contextlib.redirect_stdout(io.StringIO()), patch.object(t, 'publish') as publish:
                self.assertEqual(t.main(args), 0)
            publish.assert_not_called()

    def test_cli_asset_plus_drop_and_relative_path(self):
        path = self.editor('OV04', 'cli.txt')
        with contextlib.redirect_stdout(io.StringIO()), patch.object(t, 'publish') as publish:
            self.assertEqual(t.main(['build', '--asset', 'OV04', os.path.relpath(path)]), 0)
        self.assertEqual(publish.call_args.args[0], 'output/OV04.OVL.new')

    def test_export_rejects_input_or_check_instead_of_ignoring_it(self):
        path = self.editor('SLPS', 'not export.txt')
        for args in (['export', str(path)], ['export', '--check']):
            with contextlib.redirect_stderr(io.StringIO()), patch.object(t, 'load_inputs') as load:
                self.assertEqual(t.main(args), 1)
            load.assert_not_called()


if __name__ == '__main__':
    unittest.main()
