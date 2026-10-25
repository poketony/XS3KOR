"""Title label format, manual selection and export safety."""

import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

import build_menu
import build_title
from tools import title_text


HOME = Path(__file__).resolve().parents[1]


class TitleGraphicsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (build_title.EDITOR / 'titleobj.xtx').read_bytes()
        cls.images = title_text.extract(cls.source)

    def test_unmodified_roundtrip_and_five_correct_rows(self):
        self.assertEqual(title_text.ROWS, (0, 1, 2, 4, 5))
        result, details = title_text.rebuild(self.source, self.images)
        self.assertEqual(result, self.source)
        self.assertEqual(sum(d['changed_pixels'] for d in details), 0)

    def test_every_label_pixel_edit_is_confined_to_one_byte(self):
        colors = title_text.palette(self.source)
        for row, name in zip(title_text.ROWS, title_text.LABELS):
            with self.subTest(label=name):
                image = Image.open(io.BytesIO(self.images[name])).convert('RGBA')
                pos = title_text.offsets(row)[0]
                image.putpixel((0, 0), next(c for c in colors if c != colors[self.source[pos]]))
                images = {**self.images, name: title_text.png_bytes(list(image.getdata()))}
                result, _ = title_text.rebuild(self.source, images)
                self.assertEqual([i for i, (a, b) in enumerate(zip(self.source, result)) if a != b], [pos])

    def test_canonical_pngs_are_inputs_not_snapshot_copies(self):
        _, _, protected, _ = build_title.prepare()
        self.assertEqual(protected, build_title.input_paths())
        for path in protected[1:]:
            self.assertEqual(path.parent, HOME.parents[1] / '0.X30/mnu/kr/titleobj')
            self.assertEqual(build_menu.input_path(str(path)), path)

    def test_explicit_png_is_used_and_preserved(self):
        with tempfile.TemporaryDirectory(dir=HOME) as temp:
            path = Path(temp) / 'new_game.png'
            image = Image.open(io.BytesIO(self.images['new_game'])).convert('RGBA')
            color = next(c for c in title_text.palette(self.source) if c != image.getpixel((0, 0)))
            image.putpixel((0, 0), color)
            path.write_bytes(title_text.png_bytes(list(image.getdata())))
            before = path.read_bytes()
            _, data, inputs, _ = build_title.prepare([path])
            self.assertIn(path, inputs)
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(title_text.palette(self.source)[data[title_text.offsets(0)[0]]], color)

    def test_missing_or_duplicate_explicit_png_does_not_fall_back(self):
        with self.assertRaises(FileNotFoundError):
            build_title.prepare([HOME / '__nonexistent__/new_game.png'])
        path = build_title.EDITOR / 'new_game.png'
        with self.assertRaises(ValueError):
            build_title.prepare([path, path])

    def test_wrong_source_image_shape_and_alpha_fail(self):
        with self.assertRaises(ValueError):
            title_text.rebuild(self.source[:-1], self.images)
        for image in (Image.new('RGBA', (120, 19)), Image.new('RGB', (120, 18))):
            stream = io.BytesIO()
            image.save(stream, format='PNG')
            with self.assertRaises(ValueError):
                title_text.rebuild(self.source, {**self.images, 'data': stream.getvalue()})

    def test_existing_png_blocks_export_before_any_write(self):
        with patch.object(build_title, 'write_output') as write, self.assertRaises(FileExistsError):
            build_title.export()
        write.assert_not_called()

    def test_check_mode_does_not_write(self):
        with contextlib.redirect_stdout(io.StringIO()), patch.object(build_title, 'write_output') as write:
            self.assertEqual(build_title.main(['--check']), 0)
        write.assert_not_called()

    def test_unrepresentable_color_is_reported(self):
        image = Image.open(io.BytesIO(self.images['new_game'])).convert('RGBA')
        image.putpixel((0, 0), (12, 34, 56, 78))
        _, details = title_text.rebuild(self.source, {**self.images, 'new_game': title_text.png_bytes(list(image.getdata()))})
        self.assertEqual(details[0]['quantized_pixels'], 1)


if __name__ == '__main__':
    unittest.main()
