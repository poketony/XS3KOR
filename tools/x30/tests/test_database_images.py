"""Database JPG selection, paired output and native constraints."""

import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import build_menu
import build_native_images as native
from test_native_images import fixture


HOME = Path(__file__).resolve().parents[1]
NAMES = tuple(f'dtimg{index:04}' for index in build_menu.DATABASE_IMAGE_IDS)


class DatabaseImageTests(unittest.TestCase):
    def test_original_pairs_and_editor_coverage(self):
        rows = native.prepare(NAMES)
        self.assertEqual(len(NAMES), 25)
        self.assertEqual(len(rows), 50)
        self.assertEqual(len({row[1] for row in rows}), 50)
        self.assertEqual(len({row[3][0] for row in rows}), 25)
        for name in NAMES:
            self.assertIn(native.ASSETS[name][0], build_menu.NATIVE_EDIT_FILES)
            pair = [row for row in rows if row[0] == name]
            self.assertEqual(pair[0][2], pair[1][2])
            self.assertEqual(pair[0][2], pair[0][3][0].read_bytes())

    def test_default_database_selection(self):
        with patch.object(native, 'prepare', return_value=[]) as prepare, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(native.main(['--database', '--check']), 0)
        self.assertEqual(prepare.call_args.args, (NAMES, None))

    def test_named_drop_publishes_both_aliases(self):
        with tempfile.TemporaryDirectory(dir=HOME) as directory:
            path = Path(directory) / 'dtimg_0393.JPG'
            data = fixture('JPEG', 'RGB', (211, 134))
            path.write_bytes(data)
            with patch.object(native, 'write_output') as write, contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(native.main(['--database', str(path)]), 0)
            self.assertEqual([call.args[0] for call in write.call_args_list],
                             [HOME.parents[1] / '0.X30/jpg/kr' / (Path(p).name+'.new') for p in native.archive_paths('dtimg0393')])
            self.assertTrue(all(call.args[1] == data for call in write.call_args_list))
            self.assertEqual(path.read_bytes(), data)

    def test_explicit_asset_accepts_custom_filename_and_keeps_pair(self):
        with tempfile.TemporaryDirectory(dir=HOME) as directory:
            path = Path(directory) / 'custom image.jpg'
            data = fixture('JPEG', 'RGB', (211, 134))
            path.write_bytes(data)
            rows = native.prepare(('dtimg0400',), path)
            self.assertEqual(len(rows), 2)
            self.assertTrue(all(row[2] == data and row[3][0] == path for row in rows))

    def test_ambiguous_and_alias_drops_rejected_without_fallback(self):
        for name in ('dtimg_1393.jpg', 'dtimg_0393.png', 'dtimg_393.jpg', 'dtimg_0001.jpg', 'custom.jpg'):
            with patch.object(native, 'prepare') as prepare, contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(native.main(['--database', name]), 1)
            prepare.assert_not_called()

    def test_missing_named_drop_fails_without_output(self):
        with tempfile.TemporaryDirectory(dir=HOME) as directory:
            with patch.object(native, 'write_output') as write, contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(native.main(['--database', str(Path(directory) / 'dtimg_0393.jpg')]), 1)
            write.assert_not_called()

    def test_original_dimensions_and_supported_sampling(self):
        for subsampling in (0, 1, 2):
            native.validate(fixture('JPEG', 'RGB', (211, 134), subsampling=subsampling), 'dtimg0393')
        for size in ((212, 134), (211, 140), (512, 448)):
            with self.assertRaisesRegex(ValueError, '211x134'):
                native.validate(fixture('JPEG', 'RGB', size), 'dtimg0393')

    def test_capacity_boundary(self):
        data = fixture('JPEG', 'RGB', (211, 134))
        capacity = native.ASSETS['dtimg0393'][3]
        self.assertEqual(capacity, 30720)
        # An ignored APP marker permits an exact byte-size boundary fixture.
        padding = capacity-len(data)
        data = data[:2]+b'\xff\xef'+(padding-2).to_bytes(2, 'big')+bytes(padding-4)+data[2:]
        self.assertEqual(len(data), capacity)
        native.validate(data, 'dtimg0393')
        with self.assertRaisesRegex(ValueError, '30720-byte'):
            native.validate(data+b'\0', 'dtimg0393')

    def test_wrong_formats_rejected(self):
        for data in (fixture('JPEG', 'RGB', (211, 134), progressive=True),
                     fixture('JPEG', 'CMYK', (211, 134)), fixture('JPEG', 'L', (211, 134)),
                     fixture('PNG', 'RGB', (211, 134)), fixture('JPEG', 'RGB', (211, 134))[:-2]):
            with self.assertRaises((ValueError, OSError, SyntaxError)):
                native.validate(data, 'dtimg0393')

    def test_check_mode_does_not_write(self):
        with patch.object(native, 'write_output') as write, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(native.main(['--database', '--check']), 0)
        write.assert_not_called()

    def test_invalid_final_image_does_not_publish_earlier_images(self):
        validate = native.validate
        def reject_last(data, name):
            if name == NAMES[-1]:
                raise ValueError('Invalid last image')
            validate(data, name)
        with patch.object(native, 'validate', side_effect=reject_last), patch.object(native, 'write_output') as write:
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(native.main(['--database']), 1)
        write.assert_not_called()

if __name__ == '__main__':
    unittest.main()
