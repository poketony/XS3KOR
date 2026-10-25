"""Explicit editor selection must not fall back, write inputs, or alter defaults."""

import contextlib
import io
import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import build_database
import build_menu
import build_minigame


HOME = Path(__file__).resolve().parents[1]


class ManualInputTests(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads((HOME / 'sources.json').read_text(encoding='utf-8'))

    def editor(self, name):
        return (HOME / self.manifest['assets'][name]['edit']).resolve()

    def test_explicit_menu_editors_match_defaults(self):
        for name in build_menu.NAMES:
            with self.subTest(name=name):
                default = build_menu.prepare((name,))[0]
                explicit = build_menu.prepare((name,), self.editor(name))[0]
                self.assertEqual(default, explicit)

    def test_explicit_database_matches_default(self):
        self.assertEqual(build_database.prepare(), build_database.prepare(self.editor('DBC')))

    def test_alternate_editor_is_really_read_and_not_changed(self):
        with tempfile.TemporaryDirectory(dir=HOME) as temp:
            editor = Path(temp) / 'translation with spaces & \uD55C\uAE00.txt'
            content = re.sub(r'(?m)^(\[\d+\]).*$', r'\1DROP INPUT TEST',
                             self.editor('devchk').read_text(encoding='utf-8-sig'), count=1)
            editor.write_text(content, encoding='utf-8')
            before = editor.read_bytes()
            result = build_menu.prepare(('devchk',), editor)[0]
            self.assertIn(b'DROP INPUT TEST', result[2])
            self.assertEqual(result[3][1], editor)
            self.assertEqual(editor.read_bytes(), before)

    def test_missing_explicit_editor_has_no_fallback(self):
        for prepare in (lambda path: build_menu.prepare(('devchk',), path), build_database.prepare):
            with self.assertRaises(FileNotFoundError):
                prepare(HOME / '__nonexistent_editor__.txt')

    def test_explicit_file_cannot_select_many_menu_assets(self):
        with self.assertRaises(ValueError):
            build_menu.prepare(build_menu.NAMES, self.editor('devchk'))

    def test_game_binary_is_not_a_translation(self):
        with self.assertRaisesRegex(ValueError, 'TXT'):
            build_menu.explicit_editor(HOME.parents[1] / '0.X30/mnu/kr/devchk.txd')

    def test_external_and_lab_inputs_rejected_before_read(self):
        for path in (HOME.parents[1] / 'codex-lab/editor.txt', HOME.parents[2] / 'external.txt'):
            with self.subTest(path=path), patch.object(Path, 'resolve', return_value=path), \
                    patch.object(Path, 'is_file', return_value=True), self.assertRaises(ValueError):
                build_menu.explicit_editor(path)

    def test_cli_infers_menu_format_from_canonical_filename(self):
        with contextlib.redirect_stdout(io.StringIO()), patch.object(build_menu, 'write_output') as write:
            self.assertEqual(build_menu.main(['--check', str(self.editor('devchk'))]), 0)
            write.assert_not_called()

    def test_cli_unknown_name_fails_without_outputs(self):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()), \
                patch.object(build_menu, 'write_output') as write:
            self.assertEqual(build_menu.main(['unexpected.txt']), 1)
            write.assert_not_called()

    def test_database_check_with_explicit_input_does_not_publish(self):
        with contextlib.redirect_stdout(io.StringIO()), patch.object(build_database, 'write_output') as write:
            self.assertEqual(build_database.main(['--check', str(self.editor('DBC'))]), 0)
            write.assert_not_called()

    def test_minigame_uses_sole_canonical_working_editor(self):
        target = HOME.parents[1] / '0.X30/mg1/kr/Message.Dat.txt'
        self.assertFalse((HOME / 'edit/Message.Dat.txt').exists())
        default = build_minigame.prepare()
        self.assertEqual(default[2][1], target)
        self.assertEqual(default, build_minigame.prepare(target))
        with self.assertRaises(FileNotFoundError):
            build_minigame.prepare(HOME / '__missing__.txt')

    def test_minigame_canonical_edits_affect_output(self):
        target = HOME.parents[1] / '0.X30/mg1/kr/Message.Dat.txt'
        before = build_minigame.prepare()[1]
        read = Path.read_text
        def edited(path, *args, **kwargs):
            text = read(path, *args, **kwargs)
            if path.resolve() == target:
                text = re.sub(r'(//\[0000\]\n)[^\n]*', r'\1CANONICAL MINIGAME TEST', text, count=1)
            return text
        with patch.object(Path, 'read_text', edited):
            after = build_minigame.prepare()[1]
        self.assertNotEqual(before, after)
        self.assertIn(b'CANONICAL MINIGAME TEST', after)

    def test_minigame_check_mode_never_writes(self):
        target = HOME.parents[1] / '0.X30/mg1/kr/Message.Dat.txt'
        with contextlib.redirect_stdout(io.StringIO()), patch.object(build_minigame, 'write_output') as write:
            self.assertEqual(build_minigame.main(['--check', str(target)]), 0)
        write.assert_not_called()


if __name__ == '__main__':
    unittest.main()
