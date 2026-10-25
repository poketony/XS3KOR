"""Local graphics sources, original recovery, whole-batch protection and routing."""
import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import build_menu
import build_title
import build_window
import build_pse_logos
import build_fonts
import build_native_images
from tools import title_text, window_text, pse_logo, font_bitmap

HOME = build_menu.HOME
BUILDERS = (build_window, build_pse_logos, build_fonts, build_native_images)


def extraction(builder):
    result = builder.prepare(extract=True)
    return result[0] if builder is build_window else result


def supplied(builder, rows):
    return (rows, {}) if builder is build_window else rows


class GraphicsFolderTests(unittest.TestCase):
    def test_all_graphics_inputs_and_outputs_are_colocated(self):
        output, _, inputs, _ = build_title.prepare()
        self.assertEqual(output, inputs[0].with_name(inputs[0].name+'.new'))
        for builder in BUILDERS:
            rows = builder.prepare()
            if builder is build_window:
                rows = rows[0]
            self.assertEqual({p for row in rows for p in row[3]}, set(builder.input_paths()))
            for name, output, data, paths in rows:
                self.assertTrue(output.is_relative_to(HOME.parents[1] / '0.X30'))
                self.assertTrue(output.name.endswith('.new'))
                for path in paths:
                    self.assertTrue(path.is_file())
                    self.assertEqual(build_menu.input_path(path), path)
                if builder is not build_native_images:
                    self.assertEqual(output, paths[0].with_name(paths[0].name+'.new'))
                    self.assertTrue(all(p.parent == output.parent for p in paths))
                else:
                    self.assertEqual(output.parent, paths[0].parent)
                    self.assertEqual(paths[1].parent, output.parent / 'original')

    def test_extracted_assets_rebuild_originals_byte_exact(self):
        rows = extraction(build_window)
        images = {name: data for name, _, data, _ in rows}
        for path in rows[0][3]:
            raw = path.read_bytes()
            self.assertEqual(window_text.rebuild(raw, images, path.stem)[0], raw)
        for name, _, data, inputs in extraction(build_pse_logos):
            self.assertEqual(pse_logo.rebuild(inputs[0].read_bytes(), data, name), inputs[0].read_bytes())
        rows = extraction(build_fonts)
        for name in build_fonts.NAMES:
            selected = [row for row in rows if row[0].startswith(name+'_')]
            raw = selected[0][3][0].read_bytes()
            images = {row[0].removeprefix(name+'_'): row[2] for row in selected}
            self.assertEqual(font_bitmap.rebuild(raw, images), raw)
        rows = extraction(build_native_images)
        self.assertEqual(len(rows), 99)
        for _, _, data, inputs in rows:
            self.assertEqual(data, inputs[0].read_bytes())

    def test_title_extract_writes_missing_editors_but_never_replaces(self):
        with tempfile.TemporaryDirectory(dir=HOME) as directory:
            folder = Path(directory)
            raw = (build_title.EDITOR / 'titleobj.xtx').read_bytes()
            (folder / 'titleobj.xtx').write_bytes(raw)
            with patch.object(build_title, 'EDITOR', folder), contextlib.redirect_stdout(io.StringIO()):
                build_title.export()
                images = {name: (folder / (name+'.png')).read_bytes() for name in title_text.LABELS}
                self.assertEqual(title_text.rebuild(raw, images)[0], raw)
                with self.assertRaises(FileExistsError):
                    build_title.export()
                self.assertEqual(images, {name: (folder / (name+'.png')).read_bytes() for name in title_text.LABELS})
                self.assertEqual((folder / 'titleobj.xtx').read_bytes(), raw)

    def test_actual_extraction_publication_to_empty_test_folders(self):
        for builder in BUILDERS:
            with self.subTest(builder=builder.__name__), tempfile.TemporaryDirectory(dir=HOME) as directory:
                rows = [(name, Path(directory) / output.name, data, inputs)
                        for name, output, data, inputs in extraction(builder)]
                with patch.object(builder, 'prepare', return_value=supplied(builder, rows)), contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(builder.main(['--extract']), 0)
                self.assertTrue(all(output.read_bytes() == data for _, output, data, _ in rows))

    def test_existing_last_editor_prevents_any_partial_extraction(self):
        for builder in BUILDERS:
            with self.subTest(builder=builder.__name__), tempfile.TemporaryDirectory(dir=HOME) as directory:
                rows = [(name, Path(directory) / output.name, data, inputs)
                        for name, output, data, inputs in extraction(builder)]
                rows[-1][1].write_bytes(b'user edit')
                with patch.object(builder, 'prepare', return_value=supplied(builder, rows)), \
                        patch.object(builder, 'write_output') as write, contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(builder.main(['--extract']), 1)
                write.assert_not_called()
                self.assertEqual(rows[-1][1].read_bytes(), b'user edit')
                self.assertTrue(all(not row[1].exists() for row in rows[:-1]))

    def test_pending_last_output_prevents_any_partial_rebuild(self):
        for builder in BUILDERS:
            with self.subTest(builder=builder.__name__), tempfile.TemporaryDirectory(dir=HOME) as directory:
                rows = builder.prepare()
                details = {}
                if builder is build_window:
                    rows, details = rows
                rows = [(name, Path(directory) / output.name, data, inputs) for name, output, data, inputs in rows]
                pending = rows[-1][1].with_name(rows[-1][1].name+'.pending')
                pending.write_bytes(b'interrupted')
                result = (rows, details) if builder is build_window else rows
                with patch.object(builder, 'prepare', return_value=result), patch.object(builder, 'write_output') as write, \
                        contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(builder.main([]), 1)
                write.assert_not_called()
                self.assertEqual(pending.read_bytes(), b'interrupted')

    def test_check_extract_never_writes_or_requires_absent_editors(self):
        for builder in (build_title, *BUILDERS):
            with self.subTest(builder=builder.__name__), patch.object(builder, 'write_output') as write, contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(builder.main(['--extract', '--check']), 0)
                write.assert_not_called()

    def test_extraction_does_not_accept_dropped_inputs(self):
        for builder in (build_title, *BUILDERS):
            with self.subTest(builder=builder.__name__), patch.object(builder, 'write_output') as write, contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(builder.main(['--extract', 'unknown.png']), 1)
                write.assert_not_called()

    def test_invalid_font_selections_fail(self):
        for names in ((), ('font0', 'font0'), ('unknown',)):
            with self.assertRaises(ValueError):
                build_fonts.prepare(names)


if __name__ == '__main__':
    unittest.main()
