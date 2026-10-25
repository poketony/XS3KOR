"""Build X30 minigame text using local Japanese references."""

import argparse
import hashlib
import json
import sys

from build_menu import explicit_editor, input_path, local_path, read_verified
from tools import minigame_text, minigame_world
from tools.output import validate_outputs, write_output


ASSETS = {'Message.Dat': ('minigame_sources.json', minigame_text),
          'World.Dat': ('world_sources.json', minigame_world)}


def prepare(editor=None, asset='Message.Dat', extract=False):
    if extract and editor is not None:
        raise ValueError('Extraction reads registered originals, not a dropped TXT')
    filename, format_tool = ASSETS[asset]
    manifest = json.loads(local_path(filename).read_text(encoding='utf-8'))
    table_path = input_path(manifest['charmap'])
    table = json.loads(read_verified(table_path, manifest['charmap_sha256']).decode('utf-8-sig'))['replace-table']
    if not table or any(len(k) != 1 or not isinstance(v, str) or not v for k, v in table.items()):
        raise ValueError('Expected a nonempty single-character substitution table')
    original_path = input_path(manifest['original'])
    editor_path = explicit_editor(editor) if editor is not None else input_path(manifest['edit'])
    original = read_verified(original_path, manifest['original_sha256'])
    content = format_tool.extract_text(original) if extract else editor_path.read_text(encoding='utf-8-sig')
    result = format_tool.rebuild(original, content, table)
    if extract:
        if result != original:
            raise ValueError('Original extraction did not roundtrip byte-for-byte')
        return editor_path, content.encode('utf-8'), (original_path, table_path)
    output = original_path.with_name(original_path.name+'.new')
    return output, result, (original_path, editor_path, table_path)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--asset', choices=ASSETS, default='Message.Dat')
    parser.add_argument('--check', action='store_true', help='Validate/rebuild without saving')
    parser.add_argument('--extract', action='store_true', help='Extract Japanese original to canonical TXT; never overwrite')
    parser.add_argument('editor', nargs='?', help='Optional translation TXT in this repository')
    args = parser.parse_args(argv)
    try:
        output, result, inputs = prepare(args.editor, args.asset, extract=args.extract)
        if not args.check:
            validate_outputs((output,), inputs, overwrite=not args.extract)
            write_output(output, result, inputs, overwrite=not args.extract)
        print(f'Input: {inputs[0 if args.extract else 1]}')
        print(f'Output: {output}')
        print(f'{args.asset}: {len(result)} bytes, sha256={hashlib.sha256(result).hexdigest()}')
        print('CHECK PASSED (no files written)' if args.check else 'BUILD SUCCEEDED')
        return 0
    except (OSError, ValueError, KeyError) as exc:
        print(f'BUILD FAILED: {exc}', file=sys.stderr)
        print('Do not apply outputs from a failed run. Previous output may still exist.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
