"""Native editor selection, unchanged publishing, format limits and failure safety."""

import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

import build_menu
import build_native_images as native


HOME = Path(__file__).resolve().parents[1]


def fixture(format_name, mode, size=(512, 448), **options):
    stream = io.BytesIO()
    Image.new(mode, size).save(stream, format=format_name, **options)
    return stream.getvalue()


class NativeImageTests(unittest.TestCase):
    def test_canonical_editors_are_published_byte_exact(self):
        rows = native.prepare()
        self.assertEqual(len(rows), 124)
        for name, output, data, protected in rows:
            self.assertEqual(data, protected[0].read_bytes())
            self.assertEqual(protected[0], build_menu.input_path(native.ASSETS[name][0]))
            self.assertIn(output, [protected[0].parent / (Path(path).name+'.new') for path in native.archive_paths(name)])

    def test_drop_uses_supplied_bytes_without_editing_them(self):
        with tempfile.TemporaryDirectory(dir=HOME) as directory:
            path = Path(directory) / 'alternate image.png'
            data = fixture('PNG', 'RGBA')
            path.write_bytes(data)
            row = native.prepare(('title1',), path)[0]
            self.assertEqual(row[2], data)
            self.assertEqual(row[3][0], path)
            self.assertEqual(path.read_bytes(), data)

    def test_missing_drop_never_falls_back(self):
        with self.assertRaises(FileNotFoundError):
            native.prepare(('title1',), HOME / '__missing_native_image__.png')

    def test_ambiguous_or_duplicate_selection_rejected(self):
        for names in ((), ('unknown',), ('title1', 'title1')):
            with self.assertRaises(ValueError):
                native.prepare(names)
        with self.assertRaises(ValueError):
            native.prepare(editor=HOME / '__unused__.png')

    def test_png_rgb_size_and_truncation_rejected(self):
        for data in (fixture('PNG', 'RGB'), fixture('PNG', 'RGBA', (511, 448)),
                     fixture('PNG', 'RGBA')[:-20], b'not an image'):
            with self.assertRaises((ValueError, OSError, SyntaxError)):
                native.validate(data, 'title1')

    def test_animated_png_rejected(self):
        stream = io.BytesIO()
        image = Image.new('RGBA', (512, 448))
        image.save(stream, format='PNG', save_all=True,
                   append_images=[Image.new('RGBA', (512, 448), 'white')], duration=100)
        with self.assertRaises(ValueError):
            native.validate(stream.getvalue(), 'title1')

    def test_baseline_jpeg_subsampling_modes_accepted(self):
        for subsampling in (0, 1, 2):
            for name in ('intm10', 'wall'):
                native.validate(fixture('JPEG', 'RGB', subsampling=subsampling), name)

    def test_wall_drop_and_separate_loader_capacity(self):
        with tempfile.TemporaryDirectory(dir=HOME) as directory:
            path = Path(directory) / 'alternate wall.jpg'
            data = fixture('JPEG', 'RGB', color='white')
            path.write_bytes(data)
            row = native.prepare(('wall',), path)[0]
            self.assertEqual(row[2], data)
            self.assertEqual(row[3][0], path)
            self.assertEqual(row[1], HOME.parents[1] / '0.X30/mnu/kr/wall.jpg.new')
        self.assertEqual(native.ASSETS['wall'][3], 512 * 448)
        self.assertLess(native.ASSETS['wall'][3], native.ASSETS['intm10'][3])
        with self.assertRaisesRegex(ValueError, 'wall: image exceeds'):
            native.validate(bytes(512 * 448 + 1), 'wall')

    def test_wall_progressive_jpeg_rejected(self):
        with self.assertRaisesRegex(ValueError, 'wall:'):
            native.validate(fixture('JPEG', 'RGB', progressive=True), 'wall')

    def test_synopsis_coverage_matches_working_originals(self):
        originals = {'mnu/syno/'+p.name for p in (HOME.parents[1] / '0.X30/mnu/syno/original').glob('*.jpg')}
        paths = {asset[1] for name, asset in native.ASSETS.items() if name.startswith('syno')}
        self.assertEqual(len(paths), 71)
        self.assertEqual(paths, originals)
        self.assertEqual(native.ASSETS['syno010'][3], 0x1fe00)
        self.assertEqual(set(build_menu.NATIVE_EDIT_FILES), {asset[0] for asset in native.ASSETS.values()})

    def test_synopsis_default_selects_only_its_images(self):
        with patch.object(native, 'prepare', return_value=[]) as prepare, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(native.main(['--synopsis', '--check']), 0)
        names, editor = prepare.call_args.args
        self.assertEqual(len(names), 71)
        self.assertTrue(all(name.startswith('syno') for name in names))
        self.assertIsNone(editor)

    def test_synopsis_drop_uses_name_and_exact_bytes(self):
        with tempfile.TemporaryDirectory(dir=HOME) as directory:
            path = Path(directory) / '391.jpg'
            data = fixture('JPEG', 'RGB')
            path.write_bytes(data)
            with patch.object(native, 'write_output') as write, contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(native.main(['--synopsis', str(path)]), 0)
            self.assertEqual(write.call_args.args[0], HOME.parents[1] / '0.X30/mnu/syno/391.jpg.new')
            self.assertEqual(write.call_args.args[1], data)
            self.assertEqual(path.read_bytes(), data)

    def test_synopsis_ambiguous_drop_rejected_without_fallback(self):
        for name in ('010.png', 'unknown.jpg', '000.jpg', '10.jpg'):
            with patch.object(native, 'prepare') as prepare, contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(native.main(['--synopsis', name]), 1)
            prepare.assert_not_called()

    def test_synopsis_capacity_and_progressive_rejected(self):
        with self.assertRaisesRegex(ValueError, 'buffer'):
            native.validate(bytes(0x1fe01), 'syno010')
        with self.assertRaisesRegex(ValueError, 'syno010:'):
            native.validate(fixture('JPEG', 'RGB', progressive=True), 'syno010')

    def test_unsupported_jpeg_modes_and_truncation_rejected(self):
        for data in (fixture('JPEG', 'RGB', progressive=True), fixture('JPEG', 'CMYK'),
                     fixture('JPEG', 'L'), fixture('JPEG', 'RGB', (512, 447)),
                     fixture('JPEG', 'RGB')[:-2], fixture('PNG', 'RGB')):
            with self.assertRaises((ValueError, OSError, SyntaxError)):
                native.validate(data, 'intm10')

    def test_extended_sequential_and_extra_scans_rejected(self):
        data = fixture('JPEG', 'RGB')
        for changed in (data.replace(b'\xff\xc0', b'\xff\xc1', 1),
                        data[:-2]+b'\xff\xda\x00\x0c'+bytes((3, 1, 0, 2, 17, 3, 17, 0, 63, 0))+b'\xff\xd9'):
            with self.assertRaises(ValueError):
                native.validate(changed, 'intm10')

    def test_loader_capacities_rejected(self):
        for name, (_, _, _, capacity) in native.ASSETS.items():
            with self.assertRaisesRegex(ValueError, 'buffer'):
                native.validate(bytes(capacity+1), name)

    def test_check_writes_nothing(self):
        with patch.object(native, 'write_output') as write, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(native.main(['--check']), 0)
        write.assert_not_called()

    def test_invalid_input_does_not_publish(self):
        with tempfile.TemporaryDirectory(dir=HOME) as directory:
            path = Path(directory) / 'broken.png'
            path.write_bytes(b'broken')
            with patch.object(native, 'write_output') as write, contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(native.main(['--asset', 'title1', str(path)]), 1)
            write.assert_not_called()

if __name__ == '__main__':
    unittest.main()
