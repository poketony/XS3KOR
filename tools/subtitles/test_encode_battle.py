import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import encode_battle as battle
import subtitles as sub


class BattleSubtitleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).parent, prefix='test-battle-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'repo'
        self.folder = self.root / battle.FOLDER
        self.folder.mkdir(parents=True)
        table = self.root / sub.TABLE
        table.parent.mkdir(parents=True)
        table.write_text(json.dumps({'replace-table': {'\uac00': '\u4e00'}}), encoding='utf-8')
        self.paths = [self.folder / name for name in
                      ('CHRV_EVE0000.txt', 'CHRV_EVE0001.txt', 'KAOV_EVE0000.txt')]
        self.editor = '\ufeff;comment\r\n00:00:02\t\uac00\\n\u300c\u4ff1\u300d\u2026\r\nend\n'.encode('utf-8')
        for path in self.paths:
            path.write_bytes(self.editor)

    def output(self, path):
        return path.with_name(path.name + '.new')

    def snapshot(self):
        return {p.relative_to(self.root): p.read_bytes()
                for p in self.root.rglob('*') if p.is_file()}

    def test_all_outputs_have_new_suffix_and_preserve_exact_content(self):
        before = self.snapshot()
        stats = battle.encode_batch(self.root)
        self.assertEqual((stats['total'], stats['changed']), (3, 3))
        expected = self.editor.decode('utf-8-sig').replace('\uac00', '\u4e00').encode(sub.ENCODING)
        for path in self.paths:
            self.assertEqual(self.output(path).read_bytes(), expected)
        for path, data in before.items():
            self.assertEqual((self.root / path).read_bytes(), data)
        times = {self.output(p): self.output(p).stat().st_mtime_ns for p in self.paths}
        self.assertEqual(battle.encode_batch(self.root)['unchanged'], 3)
        self.assertEqual(times, {p: p.stat().st_mtime_ns for p in times})
        self.assertFalse(list(self.root.rglob('*.pending')))

    def test_one_or_multiple_drops_only_write_selected_files(self):
        stats = battle.encode_batch(self.root, [self.paths[0]])
        self.assertEqual(stats['total'], 1)
        self.assertTrue(self.output(self.paths[0]).exists())
        self.assertFalse(self.output(self.paths[1]).exists())
        stats = battle.encode_batch(self.root, self.paths[1:])
        self.assertEqual(stats['total'], 2)
        self.assertTrue(all(self.output(p).exists() for p in self.paths))

    def test_check_writes_nothing(self):
        before = self.snapshot()
        self.assertEqual(battle.encode_batch(self.root, check=True)['total'], 3)
        self.assertEqual(self.snapshot(), before)

    def test_bad_last_editor_prevents_any_output_changes(self):
        for invalid in (b'\xff', b'e\0n\0d\0', '\uac01'.encode('utf-8'), '\u2014'.encode('utf-8')):
            with self.subTest(invalid=invalid):
                self.paths[-1].write_bytes(invalid)
                self.output(self.paths[0]).write_bytes(b'OLD OUTPUT')
                before = self.snapshot()
                with self.assertRaisesRegex(ValueError, 'KAOV_EVE0000.txt'):
                    battle.encode_batch(self.root)
                self.assertEqual(self.snapshot(), before)

    def test_encoded_size_limit_not_utf8_size(self):
        path = self.paths[0]
        path.write_bytes(('\uac00' * 512).encode('utf-8'))
        battle.encode_batch(self.root, [path])
        self.assertEqual(len(self.output(path).read_bytes()), 1024)
        path.write_bytes(('\uac00' * 513).encode('utf-8'))
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, 'exceeds 1024 bytes'):
            battle.encode_batch(self.root, [path])
        self.assertEqual(self.snapshot(), before)

    def test_pending_blocks_entire_batch(self):
        self.output(self.paths[-1]).with_name(self.paths[-1].name + '.new.pending').write_bytes(b'KEEP')
        before = self.snapshot()
        with self.assertRaises(FileExistsError):
            battle.encode_batch(self.root)
        self.assertEqual(self.snapshot(), before)

    def test_pending_is_not_ignored_when_output_is_unchanged(self):
        battle.encode_batch(self.root)
        output = self.output(self.paths[-1])
        output.with_name(output.name + '.pending').write_bytes(b'KEEP')
        before = self.snapshot()
        with self.assertRaises(FileExistsError):
            battle.encode_batch(self.root)
        self.assertEqual(self.snapshot(), before)

    def test_invalid_duplicate_and_outside_drops_are_rejected(self):
        outside = self.root / 'elsewhere.txt'
        outside.write_bytes(self.editor)
        wrong = self.folder / 'not-a-txt.bin'
        wrong.write_bytes(self.editor)
        for paths in ([outside], [wrong], [self.paths[0], self.paths[0]], [self.folder / 'missing.txt']):
            with self.subTest(paths=paths), self.assertRaises((ValueError, FileNotFoundError)):
                battle.encode_batch(self.root, paths)

    def test_output_alias_of_editor_is_rejected(self):
        output = self.output(self.paths[0])
        output.write_bytes(self.editor)
        real_resolve = Path.resolve
        def resolve(path, *args, **kwargs):
            return real_resolve(self.paths[0] if path == output else path, *args, **kwargs)
        with patch.object(Path, 'resolve', resolve), self.assertRaisesRegex(ValueError, 'aliases'):
            battle.encode_batch(self.root, [self.paths[0]])

    def test_cli_all_and_selected_and_failure_status(self):
        with patch.object(sub, 'ROOT', self.root), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(battle.main(['--check']), 0)
            self.assertEqual(battle.main([str(self.paths[0])]), 0)
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(battle.main([str(self.folder / 'missing.txt')]), 1)


if __name__ == '__main__':
    unittest.main()
