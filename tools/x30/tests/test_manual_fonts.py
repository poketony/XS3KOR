"""Manual font selection must leave packing rules, other planes and tails alone."""

import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

import build_fonts
from tools import font_bitmap


HOME = Path(__file__).resolve().parents[1]


class FontManualTests(unittest.TestCase):
    def test_defaults_match_preserved_fonts_and_original_tails(self):
        for name, _, data, inputs in build_fonts.prepare():
            self.assertEqual(data, (HOME / f'reference/{name}.current.bin').read_bytes())
            self.assertEqual(data[-3072:], inputs[0].read_bytes()[-3072:])
            self.assertEqual(len(data), font_bitmap.FILE_BYTES)

    def test_explicit_sheet_selects_only_that_font(self):
        path = build_fonts.EDITOR / 'font0_red.png'
        default = build_fonts.prepare(('font0',))
        self.assertEqual(build_fonts.prepare(sheets=[path]), default)

    def test_explicit_pixel_changes_only_its_two_bit_plane(self):
        before = build_fonts.prepare(('font0',))[0][2]
        with tempfile.TemporaryDirectory(dir=HOME) as temp:
            path = Path(temp) / 'font0_red.png'
            with Image.open(build_fonts.EDITOR / 'font0_red.png') as source:
                image = source.convert('L')
            image.putpixel((0, 0), 0 if image.getpixel((0, 0)) >= 128 else 255)
            image.save(path)
            input_bytes = path.read_bytes()
            result = build_fonts.prepare(('font0',), [path])[0]
            after = result[2]
            self.assertEqual(before[1:], after[1:])
            self.assertNotEqual(before[0], after[0])
            self.assertEqual(before[0] & 0xfc, after[0] & 0xfc)
            self.assertEqual(path.read_bytes(), input_bytes)
            self.assertIn(path, result[3])

    def test_duplicate_wrong_font_and_unknown_name_fail(self):
        path = build_fonts.EDITOR / 'font0_red.png'
        for names, sheets in ((None, [path, path]), (('font1',), [path]),
                              (None, [build_fonts.EDITOR / 'font0.bin'])):
            with self.assertRaises(ValueError):
                build_fonts.prepare(names, sheets)

    def test_missing_explicit_sheet_has_no_fallback(self):
        with self.assertRaises(FileNotFoundError):
            build_fonts.prepare(sheets=[HOME / '__missing__/font0_red.png'])

    def test_outside_sheet_rejected_before_read(self):
        path = HOME.parents[2] / 'font0_red.png'
        with patch.object(Path, 'resolve', return_value=path), self.assertRaises(ValueError):
            build_fonts.prepare(sheets=[path])

    def test_cli_check_does_not_publish(self):
        with contextlib.redirect_stdout(io.StringIO()), patch.object(build_fonts, 'write_output') as write:
            self.assertEqual(build_fonts.main(['--check', str(build_fonts.EDITOR / 'font1_green.png')]), 0)
        write.assert_not_called()


if __name__ == '__main__':
    unittest.main()
