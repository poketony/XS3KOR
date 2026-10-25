"""Build DBC and DBC2 from the canonical repository TXT, independently of the ROM workspace."""

import argparse
import hashlib
import json
import sys

from build_menu import explicit_editor, input_path, local_path, read_verified
from tools.database_text import extract_text, rebuild_pair
from tools.output import validate_outputs, write_output


def prepare(editor=None, extract=False):
    if extract and editor is not None:
        raise ValueError('Extraction reads registered originals, not a dropped TXT')
    manifest = json.loads(local_path('sources.json').read_text(encoding='utf-8'))
    table_path = input_path(manifest['charmap'])
    table = json.loads(read_verified(table_path, manifest['charmap_sha256']).decode('utf-8-sig'))['replace-table']
    sources, paths = [], []
    for name in ('DBC', 'DBC2'):
        asset = manifest['assets'][name]
        path = input_path(asset['original'])
        sources.append(read_verified(path, asset['original_sha256']))
        paths.append(path)
    editor_path = input_path(manifest['assets']['DBC']['edit'])
    if editor is not None:
        editor_path = explicit_editor(editor)
    content = extract_text(sources[0]) if extract else editor_path.read_text(encoding='utf-8-sig')
    primary, secondary, details = rebuild_pair(*sources, content, table)
    if extract:
        if (primary, secondary) != tuple(sources):
            raise ValueError('Database extraction did not roundtrip both originals')
        return [('DBC TXT', editor_path, content.encode('utf-8'))], tuple(paths)+(table_path,), details
    protected = tuple(paths) + (editor_path, table_path)
    outputs = []
    for name, source, data in (('DBC', paths[0], primary), ('DBC2', paths[1], secondary)):
        target = source.with_name(source.name+'.new')
        outputs.append((name, target, data))
    return outputs, protected, details


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--extract', action='store_true', help='Extract original DBC TXT; existing translation is never overwritten')
    parser.add_argument('editor', nargs='?', help='Optional translation TXT in this repository; never modified')
    args = parser.parse_args(argv)
    try:
        outputs, protected, details = prepare(args.editor, extract=args.extract)
        if not args.check:
            validate_outputs((item[1] for item in outputs), protected, overwrite=not args.extract)
            for _, target, data in outputs:
                write_output(target, data, protected, overwrite=not args.extract)
        print(f'Input: {protected[0 if args.extract else 2]}')
        for name, target, data in outputs:
            print(f'Output: {target}')
            print(f'{name}: {len(data)} bytes, sha256={hashlib.sha256(data).hexdigest()}')
        print(json.dumps(details))
        print('CHECK PASSED (no files written)' if args.check else 'BUILD SUCCEEDED')
        return 0
    except (ValueError, KeyError, OSError) as exc:
        print(f'BUILD FAILED: {exc}', file=sys.stderr)
        print('Do not apply outputs from a failed run. Previous outputs may still exist.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
