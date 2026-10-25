"""Consumer-defined HUD label bounds, shared editors and three-variant preservation."""

import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

import build_menu
import build_window as builder
from tools import window_text as codec


HOME = Path(__file__).resolve().parents[1]


def png(image):
    stream = io.BytesIO()
    image.save(stream, format='PNG')
    return stream.getvalue()


class WindowGraphicsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sources = {name: (builder.EDITOR / (name+'.xtx')).read_bytes() for name in codec.SOURCES}
        cls.images = codec.extract(cls.sources['window0'], 'window0')

    def test_all_three_originals_roundtrip_with_one_shared_editor_set(self):
        for name, data in self.sources.items():
            with self.subTest(variant=name):
                self.assertEqual(codec.extract(data, name), self.images)
                rebuilt, details = codec.rebuild(data, self.images, name)
                self.assertEqual(rebuilt, data)
                self.assertTrue(all(item['changed_pixels'] == item['quantized_pixels'] == 0 for item in details))

    def test_each_label_edit_changes_only_one_index_byte_in_each_variant(self):
        for label, (_, rect, cbp) in codec.LABELS.items():
            pos = codec.offsets(rect)[0]
            with Image.open(io.BytesIO(self.images[label])) as image:
                old = image.getpixel((0, 0))
                color = next(c for c in codec.palette(self.sources['window0'], cbp) if c != old)
                image.putpixel((0, 0), color)
                images = {**self.images, label: png(image)}
            for name, data in self.sources.items():
                with self.subTest(label=label, variant=name):
                    rebuilt, _ = codec.rebuild(data, images, name)
                    self.assertEqual(len(rebuilt), len(data))
                    self.assertEqual([i for i, (a, b) in enumerate(zip(data, rebuilt)) if a != b], [pos])
                    self.assertEqual(codec.palette(data, cbp)[rebuilt[pos]], color)

    def test_editable_bytes_disjoint_and_do_not_touch_any_upload_palette(self):
        occupied = set()
        for _, rect, _ in codec.LABELS.values():
            positions = codec.offsets(rect)
            self.assertEqual(len(positions), len(set(positions)))
            self.assertFalse(occupied.intersection(positions))
            occupied.update(positions)
        # Every window CLUT lives in the last 32 CT32 rows, at x>=192.
        protected = {80+(y*384+x)*4+c for y in range(96, 128) for x in range(192, 384) for c in range(4)}
        self.assertFalse(occupied.intersection(protected))
        self.assertGreaterEqual(min(occupied), 80)
        self.assertLess(max(occupied), 196688)

    def test_bad_variant_source_or_incomplete_editor_set_rejected(self):
        for data, variant in ((b'bad', 'window0'), (self.sources['window0'], 'window1'),
                              (self.sources['window0'], 'unknown')):
            with self.assertRaisesRegex(ValueError, 'SHA-256'):
                codec.rebuild(data, self.images, variant)
        for images in ({}, {**self.images, 'extra': b'bad'}):
            with self.assertRaises(ValueError):
                codec.rebuild(self.sources['window0'], images, 'window0')

    def test_wrong_size_alpha_format_and_animation_rejected(self):
        jpeg = io.BytesIO()
        Image.new('RGB', (87, 17)).save(jpeg, format='JPEG')
        apng = io.BytesIO()
        Image.new('RGBA', (87, 17)).save(apng, format='PNG', save_all=True,
            append_images=[Image.new('RGBA', (87, 17), 'white')], duration=100)
        for blob in (png(Image.new('RGBA', (88, 17))), png(Image.new('RGB', (87, 17))),
                     jpeg.getvalue(), apng.getvalue(), b'bad', self.images['enemy_info'][:70]):
            with self.assertRaises((ValueError, OSError)):
                codec.rebuild(self.sources['window0'], {**self.images, 'enemy_info': blob}, 'window0')

    def test_palette_quantization_is_reported_without_changing_clut(self):
        with Image.open(io.BytesIO(self.images['enemy_info'])) as image:
            image.putpixel((0, 0), (12, 34, 56, 78))
            rebuilt, details = codec.rebuild(self.sources['window0'],
                {**self.images, 'enemy_info': png(image)}, 'window0')
        self.assertEqual(details[0]['quantized_pixels'], 1)
        self.assertGreater(details[0]['max_rgba_squared_error'], 0)
        for cbp in codec.CLUTS:
            self.assertEqual(codec.palette(rebuilt, cbp), codec.palette(self.sources['window0'], cbp))

    def test_direct_canonical_inputs_and_archive_coverage(self):
        rows, _ = builder.prepare()
        self.assertEqual({p for row in rows for p in row[3]}, set(builder.input_paths()))
        self.assertEqual(set(build_menu.WINDOW_EDIT_FILES), {'window/'+n+'.png' for n in codec.LABELS})
        for name, output, data, inputs in rows:
            self.assertEqual(output, builder.EDITOR / (name+'.xtx.new'))
            self.assertEqual(data, codec.rebuild(inputs[0].read_bytes(),
                {p.stem: p.read_bytes() for p in inputs[1:]}, name)[0])
            for p in inputs[1:]:
                self.assertEqual(p.parent, builder.EDITOR)
                self.assertEqual(build_menu.input_path(str(p)), p)

    def test_named_drop_applies_to_all_three_and_is_not_rewritten(self):
        with tempfile.TemporaryDirectory(dir=HOME) as directory:
            path = Path(directory) / 'enemy_info.png'
            with Image.open(io.BytesIO(self.images['enemy_info'])) as image:
                color = next(c for c in codec.palette(self.sources['window0'], 0x3b8) if c != image.getpixel((0, 0)))
                image.putpixel((0, 0), color)
                contents = png(image)
            path.write_bytes(contents)
            rows, _ = builder.prepare([path])
            self.assertEqual(path.read_bytes(), contents)
            for name, _, data, inputs in rows:
                self.assertIn(path, inputs)
                self.assertNotEqual(data, self.sources[name])

    def test_missing_unknown_and_duplicate_drop_do_not_fall_back(self):
        with self.assertRaises(FileNotFoundError):
            builder.prepare([HOME / '__missing_window__/enemy.png'])
        path = builder.EDITOR / 'enemy.png'
        with self.assertRaises(ValueError):
            builder.prepare([path, path])
        with self.assertRaises(ValueError):
            builder.prepare([HOME / 'README.txt'])

    def test_missing_canonical_png_does_not_use_original_as_fallback(self):
        with tempfile.TemporaryDirectory(dir=HOME) as directory, patch.object(builder, 'EDITOR', Path(directory)):
            with self.assertRaises(FileNotFoundError):
                builder.prepare()

    def test_check_never_writes(self):
        with patch.object(builder, 'write_output') as write, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(builder.main(['--check']), 0)
        write.assert_not_called()

    def test_invalid_last_variant_prevents_any_publish(self):
        with patch.object(codec, 'rebuild', side_effect=[(b'first', []), (b'second', []), ValueError('bad third')]), \
                patch.object(builder, 'write_output') as write, contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(builder.main([]), 1)
        write.assert_not_called()

    def test_pending_last_output_prevents_any_publish(self):
        rows, details = builder.prepare()
        with tempfile.TemporaryDirectory(dir=HOME) as directory:
            rows = [(name, Path(directory) / output.name, data, inputs) for name, output, data, inputs in rows]
            pending = rows[-1][1].with_name(rows[-1][1].name+'.pending')
            pending.write_bytes(b'preserve interrupted result')
            with patch.object(builder, 'prepare', return_value=(rows, details)), \
                    patch.object(builder, 'write_output') as write, contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(builder.main([]), 1)
            write.assert_not_called()
            self.assertEqual(pending.read_bytes(), b'preserve interrupted result')


if __name__ == '__main__':
    unittest.main()
