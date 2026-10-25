"""Build X30 episode-summary MES files from their canonical UTF-8 editors."""

import argparse
import hashlib
import json
from pathlib import Path
import sys

from build_menu import explicit_editor, input_path, local_path, read_verified
from tools import pse_text
from tools.output import validate_outputs, write_output


NAMES = ('AC', 'EP1', 'EP2', 'opening', 'PP', 'test')


def prepare(names=None, editor=None, extract=False):
    names = tuple(NAMES if names is None else names)
    if not names or len(set(names)) != len(names) or any(name not in NAMES for name in names):
        raise ValueError('Select each known MES asset at most once')
    if editor is not None and len(names) != 1:
        raise ValueError('A dropped editor requires exactly one MES asset')
    if extract and editor is not None:
        raise ValueError('Extraction reads registered originals, not a dropped TXT')
    manifest = json.loads(local_path('pse_sources.json').read_text(encoding='utf-8'))
    table_path = input_path(manifest['charmap'])
    table = json.loads(read_verified(table_path, manifest['charmap_sha256']).decode('utf-8-sig'))['replace-table']
    if not table or any(len(k) != 1 or not isinstance(v, str) or not v for k, v in table.items()):
        raise ValueError('Expected a nonempty single-character substitution table')
    results = []
    for name in names:
        asset = manifest['assets'][name]
        original_path = input_path(asset['original'])
        editor_path = explicit_editor(editor) if editor is not None else input_path(asset['edit'])
        original = read_verified(original_path, asset['original_sha256'])
        try:
            content = pse_text.extract_text(original) if extract else editor_path.read_text(encoding='utf-8-sig')
            data = pse_text.rebuild(original, content, table)
            if extract and data != original:
                raise ValueError('Original extraction did not roundtrip byte-for-byte')
        except (ValueError, UnicodeError) as exc:
            raise ValueError(f'{name}.mes: {exc}') from exc
        if extract:
            results.append((name, editor_path, content.encode('utf-8'), (original_path, table_path)))
        else:
            output = original_path.with_name(original_path.name+'.new')
            results.append((name, output, data, (original_path, editor_path, table_path)))
    return results


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--asset', choices=NAMES)
    parser.add_argument('--check', action='store_true', help='Validate without saving')
    parser.add_argument('--extract', action='store_true', help='Extract Japanese originals to canonical TXT; never overwrite')
    parser.add_argument('editor', nargs='?', help='Optional UTF-8 TXT in this repository')
    args = parser.parse_args(argv)
    try:
        name = args.asset
        if args.editor and name is None:
            manifest = json.loads(local_path('pse_sources.json').read_text(encoding='utf-8'))
            candidates = [key for key, value in manifest['assets'].items()
                          if Path(value['edit']).name.lower() == Path(args.editor).name.lower()]
            if len(candidates) != 1:
                raise ValueError('Cannot select MES from filename; specify --asset')
            name = candidates[0]
        results = prepare((name,) if name else None, args.editor, extract=args.extract)
        protected = tuple(path for item in results for path in item[3])
        if not args.check:
            validate_outputs((item[1] for item in results), protected, overwrite=not args.extract)
            for _, output, data, inputs in results:
                write_output(output, data, inputs, overwrite=not args.extract)
        for name, output, data, inputs in results:
            print(f'Input: {inputs[0 if args.extract else 1]}')
            print(f'Output: {output}')
            print(f'{name}.mes: {len(data)} bytes, sha256={hashlib.sha256(data).hexdigest()}')
        print('CHECK PASSED (no files written)' if args.check else 'BUILD SUCCEEDED')
        return 0
    except (OSError, ValueError, KeyError) as exc:
        print(f'BUILD FAILED: {exc}', file=sys.stderr)
        print('Do not apply outputs from a failed run. Previous outputs may still exist.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
