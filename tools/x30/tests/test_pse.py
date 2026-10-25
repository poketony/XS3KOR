"""Episode-summary text roundtrips, consumer limits and canonical inputs."""

import contextlib
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import build_pse
from build_menu import HOME
from tools import pse_text as pse


def runtime_records(data):
    records, current = [], None
    for line in data.rstrip(b'\0').split(b'\r\n')[:-1]:
        if line.startswith(b'#MESSAGE '):
            current = bytearray()
            records.append(current)
        elif current is not None:
            current.extend(b'\1\xff\r\n' + line)
    return [bytes(value) + b'\0' for value in records]


class PseTextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = json.loads((HOME / 'pse_sources.json').read_text(encoding='utf-8'))
        cls.originals = {name: (HOME / asset['original']).read_bytes()
                         for name, asset in cls.config['assets'].items()}
        cls.table = json.loads((HOME / 'XENOSAGA KOR-JPN.json').read_text(encoding='utf-8-sig'))['replace-table']
        cls.sample = b'#MESSAGE 0\r\nFIRST\r\n\r\n#MESSAGE 1\r\nSECOND\r\n'

    def test_all_originals_hash_and_roundtrip(self):
        for name, original in self.originals.items():
            with self.subTest(name=name):
                asset = self.config['assets'][name]
                self.assertEqual(hashlib.sha256(original).hexdigest(), asset['original_sha256'])
                content = pse.extract_text(original)
                self.assertEqual(pse.rebuild(original, content, self.table), original)
                self.assertEqual(pse.rebuild(original, content.replace('\n', '\r\n'), self.table), original)
                self.assertEqual(len(pse.read_document(original)[1]), asset['message_count'])

    def test_runtime_size_matches_independent_control_expansion(self):
        for data in self.originals.values():
            rows = pse.read_document(data)[1]
            self.assertEqual([row['runtime_bytes'] for row in rows],
                             [len(raw) for raw in runtime_records(data)])

    def test_current_ac_editor_is_encoded_without_rewriting(self):
        asset = self.config['assets']['AC']
        path = (HOME / asset['edit']).resolve()
        before = path.read_bytes()
        result = build_pse.prepare(('AC',))[0]
        text = before.decode('utf-8-sig').replace('\r\n', '\n')
        converted = ''.join(self.table.get(c, c) for c in text).replace('\n', '\r\n').encode('euc_jis_2004')
        self.assertEqual(result[2], converted + b'\0')
        self.assertEqual(result[3][1], path)
        self.assertEqual(path.read_bytes(), before)

    def test_translated_body_preserves_punctuation_and_lines(self):
        value = '<\uacf5\uaca9> [n] $rubyb;ABC$rubye; \\n'
        content = pse.extract_text(self.sample).replace('FIRST', value)
        result = pse.rebuild(self.sample, content, self.table)
        encoded = ''.join(self.table.get(c, c) for c in value).encode('euc_jis_2004')
        self.assertEqual(result, self.sample.replace(b'FIRST', encoded) + b'\0')
        self.assertEqual(pse.rebuild(result, pse.extract_text(result), self.table), result)

    def test_utf8_bom_and_crlf_editor_are_supported(self):
        text = '\ufeff' + pse.extract_text(self.sample).replace('FIRST', 'NEW').replace('\n', '\r\n')
        self.assertEqual(pse.rebuild(self.sample, text, self.table), self.sample.replace(b'FIRST', b'NEW') + b'\0')

    def test_empty_message_is_preserved_as_explicit_record(self):
        content = pse.extract_text(self.sample).replace('FIRST\n\n', '')
        result = pse.rebuild(self.sample, content, self.table)
        self.assertEqual(pse.read_document(result)[1][0]['runtime_bytes'], 1)

    def test_exact_runtime_boundary_and_one_byte_overflow(self):
        source = b'#MESSAGE 0\r\nOK\r\n'
        content = '#MESSAGE 0\n' + 'X' * 2023 + '\n'
        result = pse.rebuild(source, content, self.table)
        self.assertEqual(len(runtime_records(result)[0]), 2028)
        with self.assertRaisesRegex(ValueError, '2028'):
            pse.rebuild(source, content.replace('X\n', 'XX\n'), self.table)

    def test_runtime_limit_counts_korean_after_substitution(self):
        source = b'#MESSAGE 0\r\nOK\r\n'
        value = '\uacf5' * 1011 + 'X'
        result = pse.rebuild(source, '#MESSAGE 0\n' + value + '\n', self.table)
        self.assertEqual(len(runtime_records(result)[0]), 2028)
        with self.assertRaisesRegex(ValueError, '2028'):
            pse.rebuild(source, '#MESSAGE 0\n' + value + 'X\n', self.table)

    def test_input_file_capacity_boundary(self):
        tail = b'#MESSAGE 0\r\nXX\r\n'
        data = b'\r\n' * ((102400 - len(tail)) // 2) + tail
        self.assertEqual(len(data), 102400)
        pse.read_document(data)
        with self.assertRaisesRegex(ValueError, '102400'):
            pse.read_document(data + b'\0')

    def test_order_duplicate_missing_and_added_ids_fail(self):
        text = pse.extract_text(self.sample)
        cases = [text.replace('#MESSAGE 0', '#MESSAGE 1'),
                 text.replace('#MESSAGE 1', '#MESSAGE 0'),
                 text[:text.index('#MESSAGE 1')],
                 text + '#MESSAGE 2\nEXTRA\n',
                 '#MESSAGE 1\nSECOND\n#MESSAGE 0\nFIRST\n']
        for content in cases:
            with self.assertRaises(ValueError):
                pse.rebuild(self.sample, content, self.table)

    def test_parser_tokens_and_missing_eol_are_rejected(self):
        text = pse.extract_text(self.sample)
        for content in (text.replace('FIRST', 'A#B'), text.replace('FIRST', 'FRAME 5$'),
                        text.replace('FIRST', 'INFRAMEWORD'), text.rstrip('\n'),
                        text.replace('FIRST', 'A\rB'), text.replace('FIRST', 'A\0B')):
            with self.assertRaises(ValueError):
                pse.rebuild(self.sample, content, self.table)

    def test_original_line_endings_and_nul_are_strict(self):
        for data in (self.sample.replace(b'\r\n', b'\n'), self.sample.replace(b'\r\n', b'\r'),
                     self.sample + b'BAD', self.sample.replace(b'FIRST', b'F\0IRST'),
                     b'', b'PLAIN\r\n', b'BAD\r\n' + self.sample):
            with self.assertRaises(ValueError):
                pse.read_document(data)

    def test_unencodable_characters_are_not_dropped(self):
        for value in ('\U0001f9ea', '\u2014'):
            with self.assertRaises(UnicodeError):
                pse.rebuild(self.sample, pse.extract_text(self.sample).replace('FIRST', value), self.table)

    def test_explicit_canonical_matches_default(self):
        for name, asset in self.config['assets'].items():
            default = build_pse.prepare((name,))
            self.assertEqual(default, build_pse.prepare((name,), (HOME / asset['edit']).resolve()))

    def test_dropped_editor_used_and_left_unchanged(self):
        with tempfile.TemporaryDirectory(dir=HOME) as folder:
            path = Path(folder) / 'different name & \uD55C\uAE00.txt'
            text = pse.extract_text(self.originals['EP1']).replace('\n#MESSAGE 1', '\nDROP TEXT\n#MESSAGE 1', 1)
            path.write_text(text, encoding='utf-8')
            before = path.read_bytes()
            result = build_pse.prepare(('EP1',), path)[0]
            self.assertIn(b'DROP TEXT\r\n', result[2])
            self.assertEqual(path.read_bytes(), before)

    def test_unknown_or_multiple_selection_fails(self):
        for names in ((), ('UNKNOWN',), ('EP1', 'EP1')):
            with self.assertRaises(ValueError):
                build_pse.prepare(names)
        with self.assertRaises(ValueError):
            build_pse.prepare(editor=HOME / '__not_read__.txt')
        with self.assertRaises(FileNotFoundError):
            build_pse.prepare(('EP1',), HOME / '__missing_pse__.txt')

    def test_check_all_and_inferred_cli_do_not_write(self):
        path = (HOME / self.config['assets']['AC']['edit']).resolve()
        with patch.object(build_pse, 'write_output') as write, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(build_pse.main(['--check']), 0)
            self.assertEqual(build_pse.main([str(path), '--check']), 0)
        write.assert_not_called()

    def test_bad_last_editor_publishes_nothing(self):
        target = (HOME / self.config['assets']['test']['edit']).resolve()
        read = Path.read_text
        def damaged(path, *args, **kwargs):
            text = read(path, *args, **kwargs)
            return text + '#MESSAGE 3\nBAD\n' if path == target else text
        with patch.object(Path, 'read_text', damaged), patch.object(build_pse, 'write_output') as write:
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(build_pse.main([]), 1)
        write.assert_not_called()

    def test_source_hash_failure_publishes_nothing(self):
        with patch.object(build_pse, 'read_verified', side_effect=ValueError('Source hash mismatch')):
            with patch.object(build_pse, 'write_output') as write, contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(build_pse.main([]), 1)
        write.assert_not_called()


if __name__ == '__main__':
    unittest.main()
