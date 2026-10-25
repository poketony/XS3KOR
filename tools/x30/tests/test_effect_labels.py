"""ESD/ESP byte preservation, editing, and non-destructive extraction."""

import hashlib
import io
import json
from pathlib import Path
import struct
import unittest
from unittest.mock import patch
import tempfile
import uuid

from PIL import Image

import build_effects as b
from tools import effect_labels as e


class EffectTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = b.manifest()
        temporary = tempfile.TemporaryDirectory(dir=b.HOME, prefix='test-effects-')
        cls.addClassCleanup(temporary.cleanup)
        cls.root = Path(temporary.name)

    def sample(self):
        row = self.config['assets'][0]
        data = b.local(row['source']).read_bytes()
        image, pal = e.locations(data, self.config['label_names'])[0]
        return data, image, pal

    def color_sample(self):
        data, image, pal = self.sample()
        colored = bytearray(data)
        colors = [(0, 0, 0, 0)] + [
            (i*17, (i*47) % 256, (i*83) % 256, 128) for i in range(1, 16)
        ]
        colored[pal.offset+64:pal.offset+pal.size] = bytes(
            channel for color in colors for channel in color)
        return bytes(colored), image, pal

    def png(self, frame):
        stream = io.BytesIO()
        frame.save(stream, format='PNG')
        return stream.getvalue()

    def shadow_preview(self, mask, shade=187, offset=(2, 2)):
        shadow = Image.new('RGBA', mask.size, (shade, shade, shade, 0))
        shifted = Image.new('L', mask.size)
        shifted.paste(mask, offset)
        shadow.putalpha(shifted)
        text = Image.new('RGBA', mask.size)
        text.putalpha(mask)
        return Image.alpha_composite(shadow, text)

    def assert_label_only(self, source, rebuilt, image, pal):
        restored = bytearray(rebuilt)
        for chunk in (image, pal):
            restored[chunk.offset+64:chunk.offset+chunk.size] = source[chunk.offset+64:chunk.offset+chunk.size]
        self.assertEqual(bytes(restored), source)
        self.assertEqual(len(rebuilt), len(source))

    def test_all_builds_use_shared_png_and_preserve_other_bytes(self):
        results = b.prepare()
        owners = b.shared_editors(self.config)
        self.assertEqual(len(results), 70)
        self.assertEqual(sum(len(row['archive_paths']) for row, *_ in results), 95)
        self.assertEqual(set(b.input_paths()), {path for row in results for path in row[3]})
        self.assertEqual(len(b.input_paths()), 96)
        decoded = {}
        for row, output, data, protected, detail in results:
            source = protected[0].read_bytes()
            self.assertEqual(hashlib.sha256(source).hexdigest(), row['source_sha256'])
            self.assertEqual(protected[1], b.local(owners[row['texture_name']]))
            image, pal = e.locations(source, self.config['label_names'])[0]
            self.assert_label_only(source, data, image, pal)
            self.assertEqual(data, e.rebuild(source, image, pal, protected[1].read_bytes())[0])
            self.assertEqual(output, protected[0].with_name(protected[0].name+'.new'))
            pixels = e.pixels(data, image, pal)
            reference = decoded.setdefault(row['texture_name'], pixels)
            self.assertEqual([pixel[3] == 0 for pixel in pixels],
                             [pixel[3] == 0 for pixel in reference])
            self.assertTrue(all(a[:3] == b[:3] and abs(a[3]-b[3]) <= 16
                                for a, b in zip(pixels, reference)))
            self.assertLessEqual(len(set(pixels)), 16)
            self.assertTrue(all(alpha <= 128 for alpha in data[pal.offset+67:pal.offset+pal.size:4]))
            self.assertFalse(detail['palette_changed'])

    def test_all_sources_roundtrip_and_real_pixel_edits_are_local(self):
        for row in self.config['assets']:
            with self.subTest(source=row['source']):
                data = b.local(row['source']).read_bytes()
                image, pal = e.locations(data, self.config['label_names'])[0]
                png = e.extract(data, image, pal)
                self.assertEqual(e.rebuild(data, image, pal, png)[0], data)
                colors = e.palette(data, pal)
                frame = Image.open(io.BytesIO(png)).convert('RGBA')
                chosen = next(color for color in colors if color != frame.getpixel((0, 0)))
                frame.putpixel((0, 0), chosen)
                frame.putpixel((1, 0), chosen)
                stream = io.BytesIO()
                frame.save(stream, format='PNG')
                rebuilt, detail = e.rebuild(data, image, pal, stream.getvalue())
                self.assertNotEqual(rebuilt, data)
                self.assertEqual(rebuilt[:image.offset+64], data[:image.offset+64])
                self.assertEqual(rebuilt[image.offset+65:], data[image.offset+65:])
                self.assertEqual(e.pixels(rebuilt, image, pal)[:2], [chosen, chosen])
                self.assertEqual(detail['quantized_pixels'], 0)
                self.assertFalse(detail['palette_changed'])

    def test_rgba_preview_becomes_source_alpha_mask(self):
        data, image, pal = self.sample()
        mask = Image.new('L', (256, 32))
        mask.putpixel((0, 0), 255)
        mask.putpixel((1, 0), 128)
        mask.putpixel((2, 0), 1)
        frame = self.shadow_preview(mask)
        rebuilt, detail = e.rebuild(data, image, pal, self.png(frame))
        pixels = e.pixels(rebuilt, image, pal)
        self.assertEqual(pixels[:3], [(0, 0, 0, 253), (0, 0, 0, 125), (0, 0, 0, 0)])
        shadow = 2*256+2
        self.assertEqual(pixels[shadow:shadow+3],
                         [(0, 0, 0, 63), (0, 0, 0, 33), (0, 0, 0, 0)])
        self.assertTrue(all(pixel == (0, 0, 0, 0) for i, pixel in enumerate(pixels)
                            if i not in (0, 1, shadow, shadow+1)))
        self.assertFalse(detail['palette_changed'])
        self.assertEqual(detail['palette_mode'], 'alpha_mask')
        self.assertEqual(detail['quantized_pixels'], 5)
        self.assertEqual(detail['max_rgba_squared_error'], 25)
        expected_changes = sum(a != c for a, c in zip(e.pixels(data, image, pal), pixels))
        self.assertEqual(detail['changed_pixels'], expected_changes)
        self.assert_label_only(data, rebuilt, image, pal)
        self.assertEqual(e.rebuild(rebuilt, image, pal, e.extract(rebuilt, image, pal))[0], rebuilt)

    def test_many_colors_quantize_without_changing_transparent_mask(self):
        data, image, pal = self.color_sample()
        frame = Image.new('RGBA', (256, 32))
        values = [(255, 255, 255, 0) if i % 4 == 0 else
                  ((i % 64)*4,)*3 + (255,) for i in range(8192)]
        frame.putdata(values)
        rebuilt, detail = e.rebuild(data, image, pal, self.png(frame))
        pixels = e.pixels(rebuilt, image, pal)
        self.assertLessEqual(len(set(pixels)), 16)
        self.assertEqual([p[3] == 0 for p in pixels], [p[3] == 0 for p in values])
        self.assertTrue(detail['palette_changed'])
        self.assertGreater(detail['quantized_pixels'], 0)
        visible_errors = [(a-b)**2 for p, q in zip(values, pixels) if p[3]
                          for a, b in zip(p[:3], q[:3])]
        self.assertLess((sum(visible_errors)/len(visible_errors))**0.5, 12)
        self.assert_label_only(data, rebuilt, image, pal)
        self.assertEqual(e.rebuild(data, image, pal, self.png(frame))[0], rebuilt)

    def test_invisible_rgb_does_not_consume_palette_entries(self):
        data, image, pal = self.color_sample()
        frame = Image.new('RGBA', (256, 32))
        values = [(i % 256, (i*7) % 256, (i*11) % 256, 0) if i % 2 else
                  (187, 187, 187, 255) for i in range(8192)]
        frame.putdata(values)
        rebuilt, detail = e.rebuild(data, image, pal, self.png(frame))
        frame.putdata([p if p[3] else (0, 0, 0, 0) for p in values])
        self.assertEqual(e.rebuild(data, image, pal, self.png(frame))[0], rebuilt)
        self.assertEqual(detail['quantized_pixels'], 0)
        self.assertEqual(detail['max_rgba_squared_error'], 0)
        self.assertEqual(len(set(e.pixels(rebuilt, image, pal))), 2)

    def test_many_alpha_levels_keep_foreground_and_preview_shadow(self):
        data, image, pal = self.sample()
        mask = Image.new('L', (256, 32))
        for x in range(256):
            mask.putpixel((x, 4), x)
        frame = self.shadow_preview(mask)
        rebuilt, _ = e.rebuild(data, image, pal, self.png(frame))
        pixels = e.pixels(rebuilt, image, pal)
        for row in range(32):
            output = pixels[row*256:(row+1)*256]
            if row == 4:
                output_alpha = [p[3] for p in output]
                self.assertEqual(output_alpha, sorted(output_alpha))
                self.assertGreater(len(set(output_alpha)), 8)
                self.assertEqual(output_alpha[-1], 253)
            elif row == 6:
                output_alpha = [p[3] for p in output]
                self.assertEqual(output_alpha, sorted(output_alpha))
                self.assertGreater(len(set(output_alpha)), 3)
                self.assertEqual(output_alpha[-1], 63)
            else:
                self.assertEqual(set(output), {(0, 0, 0, 0)})
        self.assertLessEqual(len(set(pixels)), 16)
        self.assertEqual({p[:3] for p in pixels if p[3]}, {(0, 0, 0)})
        self.assertTrue(all(alpha <= 128 for alpha in rebuilt[pal.offset+67:pal.offset+pal.size:4]))
        self.assertEqual(rebuilt[pal.offset+64:pal.offset+pal.size],
                         data[pal.offset+64:pal.offset+pal.size])
        self.assert_label_only(data, rebuilt, image, pal)

    def test_shadow_overlap_other_offsets_and_shades(self):
        mask = Image.new('L', (256, 32))
        for y in range(8, 18):
            for x in range(16, 40):
                mask.putpixel((x, y), ((x*7+y*3) % 16)*17)
        for offset in ((2, 2), (-3, 1), (1, -2), (7, 5)):
            for shade in (96, 187, 255):
                with self.subTest(offset=offset, shade=shade):
                    frame = self.shadow_preview(mask, shade, offset)
                    values = list(frame.getdata())
                    composite = Image.alpha_composite(Image.new('RGBA', mask.size, 'white'), frame)
                    expected = [255-pixel[0] for pixel in composite.getdata()]
                    self.assertEqual(e.preview_coverage(values), expected)
                    if shade < 255:
                        self.assertTrue(any(a == 0 and c > 0
                                            for a, c in zip(mask.getdata(), expected)))

    def test_one_foreign_pixel_cannot_silently_change_the_whole_mask(self):
        data, image, pal = self.sample()
        frame = Image.new('RGBA', (256, 32), (187, 187, 187, 128))
        rebuilt, _ = e.rebuild(data, image, pal, self.png(frame))
        before = e.pixels(rebuilt, image, pal)
        self.assertEqual(set(before), {(0, 0, 0, 33)})
        frame.putpixel((0, 0), (0, 0, 0, 255))
        rebuilt, _ = e.rebuild(data, image, pal, self.png(frame))
        after = e.pixels(rebuilt, image, pal)
        self.assertEqual(after[0], (0, 0, 0, 253))
        self.assertEqual(after[1:], before[1:])
        frame.putpixel((0, 0), (255, 0, 0, 255))
        with self.assertRaisesRegex(ValueError, 'monochrome'):
            e.rebuild(data, image, pal, self.png(frame))

    def test_all_real_editors_preserve_complete_grayscale_appearance(self):
        for row, _, rebuilt, protected, _ in b.prepare('esd'):
            with self.subTest(source=row['source']):
                with Image.open(protected[1]) as editor:
                    frame = editor.convert('RGBA')
                composite = Image.alpha_composite(Image.new('RGBA', frame.size, 'white'), frame)
                expected = [255-pixel[0] for pixel in composite.getdata()]
                self.assertEqual(e.preview_coverage(list(frame.getdata())), expected)
                image, pal = e.locations(rebuilt, self.config['label_names'])[0]
                alphas = sorted({p[3] for p in e.palette(rebuilt, pal)})
                output = e.pixels(rebuilt, image, pal)
                for amount, pixel in zip(expected, output):
                    self.assertEqual(pixel[:3], (0, 0, 0))
                    self.assertEqual(abs(pixel[3]-amount), min(abs(a-amount) for a in alphas))
                # Gray-only shadow pixels must survive whenever the CLUT can represent them.
                shadow = [i for i, p in enumerate(frame.getdata())
                          if 0 < p[0] < 255 and p[3] and expected[i] >= alphas[1]]
                self.assertTrue(all(output[i][3] > 0 for i in shadow))

    def test_all_gray_alpha_pairs_match_composite_without_quantization(self):
        frame = Image.new('RGBA', (256, 256))
        values = [(gray, gray, gray, alpha) for gray in range(256) for alpha in range(256)]
        frame.putdata(values)
        composite = Image.alpha_composite(Image.new('RGBA', frame.size, 'white'), frame)
        self.assertEqual(e.preview_coverage(values), [255-p[0] for p in composite.getdata()])

    def test_sixteen_opaque_colors_remain_exact(self):
        data, image, pal = self.color_sample()
        frame = Image.new('RGBA', (256, 32))
        values = [((i % 16)*17,)*3+(255,) for i in range(8192)]
        frame.putdata(values)
        rebuilt, detail = e.rebuild(data, image, pal, self.png(frame))
        self.assertEqual(e.pixels(rebuilt, image, pal), values)
        self.assertEqual(detail['quantized_pixels'], 0)
        self.assertTrue(detail['palette_changed'])
        self.assert_label_only(data, rebuilt, image, pal)

    def test_fully_transparent_png_and_duplicate_indices_roundtrip(self):
        data, image, pal = self.sample()
        frame = Image.new('RGBA', (256, 32), (255, 255, 255, 0))
        rebuilt, detail = e.rebuild(data, image, pal, self.png(frame))
        self.assertTrue(all(pixel[3] == 0 for pixel in e.pixels(rebuilt, image, pal)))
        self.assertFalse(detail['palette_changed'])
        self.assertEqual(detail['quantized_pixels'], 0)
        duplicate = bytearray(data)
        duplicate[pal.offset+64:pal.offset+pal.size] = b'\x00'*64
        duplicate[image.offset+64:image.offset+65] = b'\xf7'
        self.assertEqual(e.rebuild(bytes(duplicate), image, pal,
                                  e.extract(duplicate, image, pal))[0], duplicate)
        opaque = bytearray(data)
        opaque[pal.offset+64:pal.offset+pal.size] = bytes((0, 0, 0, 128))*16
        blank, detail = e.rebuild(bytes(opaque), image, pal, self.png(frame))
        self.assertTrue(detail['palette_changed'])
        self.assertEqual(set(e.pixels(blank, image, pal)), {(0, 0, 0, 0)})

    def test_indexed_png_transparency_is_supported(self):
        data, image, pal = self.sample()
        frame = Image.new('P', (256, 32))
        frame.putpalette([255, 255, 255, 187, 187, 187]+[0]*762)
        frame.info['transparency'] = 0
        frame.putpixel((0, 0), 1)
        rebuilt, detail = e.rebuild(data, image, pal, self.png(frame))
        pixels = e.pixels(rebuilt, image, pal)
        self.assertEqual(pixels[0], (0, 0, 0, 63))
        self.assertEqual(set(pixels[1:]), {(0, 0, 0, 0)})
        self.assertEqual(detail['quantized_pixels'], 1)
        self.assertFalse(detail['palette_changed'])

    def test_invalid_png_rejected(self):
        data, image, pal = self.sample()
        for size, mode in (((255, 32), 'RGBA'), ((256, 32), 'RGB')):
            stream = io.BytesIO()
            Image.new(mode, size).save(stream, format='PNG')
            with self.assertRaises(ValueError):
                e.rebuild(data, image, pal, stream.getvalue())

    def test_bad_container_and_palette_rejected(self):
        data, image, pal = self.sample()
        for offset in (0, 64, image.offset, pal.offset):
            bad = bytearray(data)
            struct.pack_into('<I', bad, offset, 1)
            with self.assertRaises(ValueError):
                e.locations(bad, self.config['label_names'])

    def test_drop_selects_esd_and_exact_matching_maps(self):
        row = next(r for r in self.config['assets'] if r['source'].endswith('ce003_999.esd'))
        editor = b.local(row['editor'])
        results = b.prepare('esd', [editor])
        self.assertEqual({r[1].name for r in results},
                         {'ce003_999.esd.new', 'ef1220.esp.new', 'ef1228.esp.new'})
        self.assertTrue(all(r[3][1] == editor for r in results))
        decoded = [e.pixels(data, *e.locations(data, self.config['label_names'])[0])
                   for _, _, data, _, _ in results]
        self.assertTrue(all(pixels == decoded[0] for pixels in decoded))
        maps = b.prepare('map', [editor])
        self.assertEqual({r[1].name for r in maps}, {'ef1220.esp.new', 'ef1228.esp.new'})
        self.assertEqual([r[2] for r in maps], [r[2] for r in results if r[0]['group'] == 'map'])
        old = b.local(next(r['editor'] for r in self.config['assets'] if r['source'].endswith('ef1220.esp')))
        for group, paths in (('map', [old]), ('esd', [editor, editor]),
                             ('esd', [editor.with_name('absent.png')])):
            with self.assertRaises((ValueError, FileNotFoundError)):
                b.prepare(group, paths)

    def test_default_group_counts_and_extraction_scope(self):
        self.assertEqual(len(b.select('esd', [])[1]), 70)
        self.assertEqual(len(b.select('map', [])[1]), 45)
        self.assertEqual(len(b.select('esd', [], extract=True)[1]), 25)
        extracted = b.prepare('map', extract=True)
        self.assertEqual(len(extracted), 45)
        self.assertTrue(all(output.name.endswith('.location.png') for _, output, *_ in extracted))

    def test_missing_shared_png_never_falls_back_to_old_map_png(self):
        editor = b.local('0.X30/ef/esd/kr/ce003_999.png')
        original_read = Path.read_bytes
        def read(path):
            if path == editor:
                raise FileNotFoundError('Shared editor missing')
            return original_read(path)
        with patch.object(Path, 'read_bytes', read), self.assertRaises(FileNotFoundError):
            b.prepare('map')

    def test_build_does_not_read_reference_pngs_or_external_files(self):
        permitted = {b.local(r['source']) for r in self.config['assets']}
        permitted.update(b.local(p) for p in b.shared_editors(self.config).values())
        original_read = Path.read_bytes
        def read(path):
            self.assertIn(path, permitted)
            return original_read(path)
        with patch.object(Path, 'read_bytes', read):
            self.assertEqual(len(b.prepare('esd')), 70)

    def test_bad_linked_map_prevents_publishing_esd(self):
        editor = b.local('0.X30/ef/esd/kr/ce003_999.png')
        target = b.local('0.X30/ef/map/ef1228.esp')
        original_read = Path.read_bytes
        def read(path):
            data = original_read(path)
            return data+b'changed' if path == target else data
        with patch.object(Path, 'read_bytes', read), patch.object(b, 'publish') as publish, \
                patch('sys.stderr', new=io.StringIO()):
            self.assertEqual(b.main(['--group', 'esd', str(editor)]), 1)
        publish.assert_not_called()

    def test_duplicate_or_missing_shared_owner_fails(self):
        owner = next(r for r in self.config['assets'] if r['group'] == 'esd')
        for assets in (self.config['assets']+[owner], [r for r in self.config['assets'] if r is not owner]):
            with self.assertRaises(ValueError):
                b.shared_editors({'assets': assets})

    def test_single_png_snapshot_is_reused_for_linked_maps(self):
        editor = b.local('0.X30/ef/esd/kr/ce003_999.png')
        original_read = Path.read_bytes
        reads = []
        def read(path):
            if path == editor:
                reads.append(path)
            return original_read(path)
        with patch.object(Path, 'read_bytes', read):
            b.prepare('esd', [editor])
        self.assertEqual(reads, [editor])

    def fixture(self):
        directory = self.root / uuid.uuid4().hex
        directory.mkdir()
        source, editor = directory/'source.esd', directory/'source.png'
        data, image, pal = self.sample()
        source.write_bytes(data)
        return directory, source, editor, data, e.extract(data, image, pal)

    def test_extract_collision_stops_before_writing_any_png(self):
        directory, source, editor, data, png = self.fixture()
        other = directory/'second.png'
        editor.write_bytes(b'user edited PNG')
        rows = [({}, other, png, (source,), {}), ({}, editor, png, (source,), {})]
        with self.assertRaises(FileExistsError):
            b.publish(rows, extract=True)
        self.assertFalse(other.exists())
        self.assertEqual(editor.read_bytes(), b'user edited PNG')
        self.assertEqual(source.read_bytes(), data)

    def test_extract_and_build_write_only_named_outputs(self):
        directory, source, editor, data, png = self.fixture()
        b.publish([({}, editor, png, (source,), {})], extract=True)
        self.assertEqual(editor.read_bytes(), png)
        output = source.with_name(source.name+'.new')
        b.publish([({}, output, data, (source, editor), {})])
        self.assertEqual(output.read_bytes(), data)
        self.assertEqual(source.read_bytes(), data)

    def test_pending_and_input_alias_rejected(self):
        directory, source, editor, data, png = self.fixture()
        with self.assertRaises(ValueError):
            b.publish([({}, source, png, (source,), {})])
        output = directory/'source.esd.new'
        output.with_name(output.name+'.pending').write_bytes(b'interrupted')
        with self.assertRaises(FileExistsError):
            b.publish([({}, output, data, (source,), {})])
        self.assertFalse(output.exists())

    def test_check_never_publishes(self):
        with patch.object(b, 'publish') as publish, patch('sys.stdout', new=io.StringIO()):
            self.assertEqual(b.main(['--group', 'esd', '--check']), 0)
        publish.assert_not_called()

    def test_paths_cannot_escape_effect_working_area(self):
        for relative in ('tools/x30/README.txt', '0.X30/ef/../../../outside.bin'):
            with self.assertRaises(ValueError):
                b.local(relative)


if __name__ == '__main__':
    unittest.main()
