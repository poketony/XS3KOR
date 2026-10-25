"""PSE TM2 pixel bounds, PNG alpha, canonical inputs and manual build failures."""

import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

import build_menu
import build_pse_logos as builder
from tools import pse_logo


HOME = Path(__file__).resolve().parents[1]


def png(image):
    stream = io.BytesIO()
    image.save(stream, format='PNG')
    return stream.getvalue()


class PseLogoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sources = {name: builder.input_paths((name,))[0].read_bytes() for name in builder.NAMES}
        cls.images = {name: pse_logo.extract(data, name) for name, data in cls.sources.items()}

    def test_three_original_roundtrips_byte_exact(self):
        for name, data in self.sources.items():
            with self.subTest(name=name):
                self.assertEqual(pse_logo.rebuild(data, self.images[name], name), data)

    def test_pixel_edits_change_only_the_requested_four_bytes(self):
        for name, data in self.sources.items():
            with self.subTest(name=name), Image.open(io.BytesIO(self.images[name])) as image:
                width, height = image.size
                x, y = width-1, height-1
                pos = 64+(y*width+x)*4
                old = data[pos:pos+4]
                image.putpixel((x, y), tuple(255-value for value in old[:3])+(255 if old[3] == 0 else 0,))
                output = pse_logo.rebuild(data, png(image), name)
                self.assertEqual(len(output), len(data))
                self.assertEqual(output[:pos], data[:pos])
                self.assertEqual(output[pos+4:], data[pos+4:])
                self.assertEqual([i for i, (a, b) in enumerate(zip(data, output)) if a != b], list(range(pos, pos+4)))

    def test_all_game_alpha_levels_are_representable_without_drift(self):
        name = 'logo_ep1'
        with Image.open(io.BytesIO(self.images[name])) as image:
            for alpha in range(129):
                image.putpixel((alpha, 0), (12, 34, 56, alpha*255//128))
            output = pse_logo.rebuild(self.sources[name], png(image), name)
        self.assertEqual(output[67:67+129*4:4], bytes(range(129)))
        self.assertEqual(output[:64], self.sources[name][:64])

    def test_png_alpha_quantization_is_bounded_and_rgb_preserved(self):
        name = 'logo_ep1'
        with Image.open(io.BytesIO(self.images[name])) as image:
            image.putpixel((0, 0), (12, 34, 56, 78))
            output = pse_logo.rebuild(self.sources[name], png(image), name)
        self.assertEqual(output[64:68], bytes((12, 34, 56, 39)))
        self.assertEqual(output[68:], self.sources[name][68:])

    def test_wrong_original_rejected(self):
        for data in (self.sources['logo_ep1'][:-1], self.sources['logo_ep2'], b'bad'):
            with self.assertRaisesRegex(ValueError, 'SHA-256'):
                pse_logo.rebuild(data, self.images['logo_ep1'], 'logo_ep1')

    def test_wrong_dimensions_rgb_jpeg_and_truncated_images_rejected(self):
        stream = io.BytesIO()
        Image.new('RGB', (136, 90)).save(stream, format='JPEG')
        cases = (png(Image.new('RGBA', (137, 90))), png(Image.new('RGB', (136, 90))),
                 stream.getvalue(), b'bad', self.images['logo_ep1'][:100])
        for data in cases:
            with self.assertRaises((ValueError, OSError)):
                pse_logo.rebuild(self.sources['logo_ep1'], data, 'logo_ep1')

    def test_animated_png_rejected(self):
        stream = io.BytesIO()
        Image.new('RGBA', (136, 90)).save(stream, format='PNG', save_all=True,
            append_images=[Image.new('RGBA', (136, 90), 'white')], duration=100)
        with self.assertRaises(ValueError):
            pse_logo.rebuild(self.sources['logo_ep1'], stream.getvalue(), 'logo_ep1')

    def test_canonical_pngs_direct_and_source_paths_fingerprinted(self):
        rows = builder.prepare()
        self.assertEqual(len(rows), 3)
        self.assertEqual(tuple(path for row in rows for path in row[3]), builder.input_paths())
        self.assertEqual(set(build_menu.PSE_LOGO_FILES), {name+'.png' for name in builder.NAMES})
        for name, output, data, (original, editor) in rows:
            self.assertEqual(editor.parent, HOME.parents[1] / '0.X30/mnu/pse/kr')
            self.assertEqual(editor, build_menu.input_path(str(editor)))
            self.assertEqual(output, original.with_name(original.name+'.new'))
            self.assertEqual(data, pse_logo.rebuild(original.read_bytes(), editor.read_bytes(), name))

    def test_dropped_custom_png_used_and_preserved(self):
        with tempfile.TemporaryDirectory(dir=HOME) as directory:
            path = Path(directory) / 'custom logo.png'
            image = Image.new('RGBA', (136, 90), (255, 0, 0, 255))
            contents = png(image)
            path.write_bytes(contents)
            row = builder.prepare(('logo_ep1',), path)[0]
            self.assertEqual(row[2][64:], bytes((255, 0, 0, 128))*(136*90))
            self.assertEqual(row[3][1], path)
            self.assertEqual(path.read_bytes(), contents)

    def test_missing_drop_rejected_without_fallback(self):
        with self.assertRaises(FileNotFoundError):
            builder.prepare(('logo_ep1',), HOME / '__missing_pse_logo__.png')

    def test_selection_ambiguity_unknown_duplicate_rejected(self):
        for names in ((), ('unknown',), ('logo_ep1', 'logo_ep1')):
            with self.assertRaises(ValueError):
                builder.prepare(names)
        with self.assertRaises(ValueError):
            builder.prepare(editor=HOME / '__unused__.png')

    def test_named_drop_infers_only_that_asset(self):
        with patch.object(builder, 'prepare', return_value=[]) as prepare, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(builder.main(['logo_pp.png', '--check']), 0)
        prepare.assert_called_once_with(('logo_pp',), 'logo_pp.png', extract=False)

    def test_unknown_filename_requires_explicit_asset(self):
        with patch.object(builder, 'prepare') as prepare, contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(builder.main(['custom.png']), 1)
        prepare.assert_not_called()

    def test_check_never_writes(self):
        with patch.object(builder, 'write_output') as write, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(builder.main(['--check']), 0)
        write.assert_not_called()

    def test_bad_last_logo_prevents_publishing_first_ones(self):
        with patch.object(pse_logo, 'rebuild', side_effect=[b'first', b'second', ValueError('bad third')]), \
                patch.object(builder, 'write_output') as write, contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(builder.main([]), 1)
        write.assert_not_called()

if __name__ == '__main__':
    unittest.main()
