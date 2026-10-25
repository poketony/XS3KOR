"""One canonical editor pair, two independently named ROM destinations."""

import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import elf_text_tool as t


class DeliveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.originals, cls.table = t.load_inputs()

    def setUp(self):
        temp = tempfile.TemporaryDirectory(dir=t.HERE, prefix='test-delivery-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.repo = self.root / 'repo'
        self.editors = self.repo / 'discmetadata'
        self.rom = self.root / 'rom'
        self.editors.mkdir(parents=True)
        for name, original in self.originals.items():
            (self.editors / f'{name}.txt').write_text(t.export_text(name, original, True), encoding='utf-8')
        self.profiles = {str(disc): {'metadata': {
            f'SLPS_256.4{disc-1}': {'size': len(self.originals['SLPS']), 'sha256': t.ASSETS['SLPS']['sha256']},
            'OV04.OVL': {'size': len(self.originals['OV04']), 'sha256': t.ASSETS['OV04']['sha256']},
        }} for disc in (1, 2)}
        self.put(self.rom / 'iso-data/profile.json', json.dumps(self.profiles).encode())
        self.put(self.rom / 'disc1metadata/SLPS_256.40', self.originals['SLPS'])
        self.put(self.rom / 'disc1metadata/OV04.OVL', self.originals['OV04'])
        self.put(self.rom / 'disc1metadata/SYSTEM.CNF', b'keep disc 1 boot path')
        self.put(self.rom / 'rebuild.py', b'ROM builder remains independent')
        for attr, value in (('REPO', self.repo), ('EDITOR', self.editors)):
            mocked = patch.object(t, attr, value)
            mocked.start()
            self.addCleanup(mocked.stop)

    def put(self, path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def snapshot(self, root):
        return {p.relative_to(root): t.sha(p.read_bytes()) for p in root.rglob('*') if p.is_file()}

    def run_delivery(self, check=False):
        with contextlib.redirect_stdout(io.StringIO()):
            t.run('check' if check else 'build', rom_root=self.rom)

    def test_both_names_and_overlay_copy_without_touching_inputs_or_boot_files(self):
        editor = self.editors / 'OV04.txt'
        editor.write_text(editor.read_text(encoding='utf-8').replace('\u9632\u5177', '\ubc29\uc5b4\uad6c'), encoding='utf-8')
        inputs = self.snapshot(self.repo)
        self.run_delivery()
        for disc in (1, 2):
            for name, filename in (('SLPS', f'SLPS_256.4{disc-1}'), ('OV04', 'OV04.OVL')):
                expected = t.build_blob(name, self.originals[name],
                    (self.editors / f'{name}.txt').read_text(encoding='utf-8'), self.table)
                self.assertEqual((self.rom / f'disc{disc}metadata' / filename).read_bytes(), expected)
        self.assertEqual(self.snapshot(self.repo), inputs)
        self.assertEqual((self.rom / 'disc1metadata/SYSTEM.CNF').read_bytes(), b'keep disc 1 boot path')
        self.assertEqual((self.rom / 'rebuild.py').read_bytes(), b'ROM builder remains independent')
        self.assertEqual({p.name for p in (self.rom / 'disc2metadata').iterdir()}, {'SLPS_256.41', 'OV04.OVL'})
        self.assertFalse(list(self.rom.rglob('*.pending')))
        self.assertFalse(list(self.rom.rglob('*.new')))

    def test_check_writes_nothing_and_does_not_create_disc2_directory(self):
        before = self.snapshot(self.root)
        self.run_delivery(check=True)
        self.assertEqual(before, self.snapshot(self.root))
        self.assertFalse((self.rom / 'disc2metadata').exists())

    def test_same_results_are_not_rewritten(self):
        self.run_delivery()
        with patch.object(t, 'write_verified') as write:
            self.run_delivery()
        write.assert_not_called()

    def test_bad_second_editor_copies_nothing(self):
        (self.editors / 'OV04.txt').write_text('invalid', encoding='utf-8')
        before = self.snapshot(self.rom)
        with self.assertRaises(ValueError):
            self.run_delivery()
        self.assertEqual(before, self.snapshot(self.rom))

    def test_late_profile_mismatch_copies_nothing(self):
        self.profiles['2']['metadata']['SLPS_256.41']['sha256'] = 'wrong'
        self.put(self.rom / 'iso-data/profile.json', json.dumps(self.profiles).encode())
        before = self.snapshot(self.rom)
        with self.assertRaisesRegex(ValueError, 'Japanese original'):
            self.run_delivery()
        self.assertEqual(before, self.snapshot(self.rom))

    def test_unrelated_code_patch_is_not_erased(self):
        target = self.rom / 'disc2metadata/OV04.OVL'
        modified = bytearray(self.originals['OV04'])
        modified[0x1000] ^= 1
        self.put(target, modified)
        before = self.snapshot(self.rom)
        with self.assertRaisesRegex(ValueError, 'incompatible changes'):
            self.run_delivery()
        self.assertEqual(before, self.snapshot(self.rom))

    def test_late_pending_file_stops_before_any_write(self):
        self.put(self.rom / 'disc2metadata/OV04.OVL.pending', b'interrupted')
        before = self.snapshot(self.rom)
        with self.assertRaisesRegex(ValueError, 'Unfinished output'):
            self.run_delivery()
        self.assertEqual(before, self.snapshot(self.rom))

    def test_input_change_is_rejected_before_delivery(self):
        output = {filename: self.originals[name]
                  for name, spec in t.ASSETS.items() for filename in spec['outputs']}
        before = self.snapshot(self.rom)
        with self.assertRaisesRegex(ValueError, 'Input changed'):
            t.deliver(output, self.originals, self.rom, {self.editors / 'SLPS.txt': 'wrong'})
        self.assertEqual(before, self.snapshot(self.rom))

    def test_repository_cannot_be_used_as_rom_destination(self):
        self.put(self.repo / 'iso-data/profile.json', json.dumps(self.profiles).encode())
        before = self.snapshot(self.repo)
        with self.assertRaisesRegex(ValueError, 'Unsafe ROM destination'), contextlib.redirect_stdout(io.StringIO()):
            t.run('build', rom_root=self.repo)
        self.assertEqual(before, self.snapshot(self.repo))

    def test_failed_replace_preserves_previous_executable(self):
        target = self.rom / 'disc1metadata/SLPS_256.40'
        before = target.read_bytes()
        with patch.object(t.os, 'replace', side_effect=OSError('interrupted')):
            with self.assertRaises(OSError):
                self.run_delivery()
        self.assertEqual(target.read_bytes(), before)
        self.assertTrue(target.with_name(target.name + '.pending').is_file())

    def test_optional_single_asset_targets_both_discs_only_for_that_asset(self):
        before = (self.rom / 'disc1metadata/SLPS_256.40').read_bytes()
        with contextlib.redirect_stdout(io.StringIO()):
            t.run('build', asset='OV04', rom_root=self.rom)
        self.assertEqual((self.rom / 'disc1metadata/SLPS_256.40').read_bytes(), before)
        self.assertEqual({p.name for p in (self.rom / 'disc2metadata').iterdir()}, {'OV04.OVL'})

    def test_export_keeps_single_canonical_editor_pair(self):
        before = self.snapshot(self.repo)
        with contextlib.redirect_stdout(io.StringIO()):
            t.run('export')
        self.assertEqual(before, self.snapshot(self.repo))
        self.assertFalse((t.HERE / 'edit/SLPS.txt').exists())
        self.assertFalse((t.HERE / 'edit/OV04.txt').exists())


if __name__ == '__main__':
    unittest.main()
