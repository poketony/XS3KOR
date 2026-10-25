"""Build the X30 batdat editor with strict validation and fixed-size section pools."""

import argparse
import hashlib
import json
import sys
from pathlib import Path

from build_menu import HOME, input_path, local_path, read_verified
from tools import batdat_text, batdat_legacy
from tools.output import write_output


def load_editor(editor=None):
    manifest = json.loads(local_path('batdat_sources.json').read_text(encoding='utf-8'))
    table_path = input_path(manifest['charmap'])
    table = json.loads(read_verified(table_path, manifest['charmap_sha256']).decode('utf-8-sig'))['replace-table']
    if not table or any(len(k) != 1 or not isinstance(v, str) or not v for k, v in table.items()):
        raise ValueError('Expected a nonempty single-character substitution table')
    original_path, editor_path = input_path(manifest['original']), input_path(manifest['edit'])
    if editor is not None:
        editor_path = Path(editor).resolve(strict=True)
        if (not editor_path.is_file() or editor_path.suffix.lower() != '.json'
                or not any(editor_path.is_relative_to(root) for root in (HOME, HOME.parents[1] / '0.X30'))):
            raise ValueError('Expected a JSON editor inside this repository: 0.X30 or tools/x30')
    original = read_verified(original_path, manifest['original_sha256'])
    document = batdat_text.parse_json(editor_path.read_text(encoding='utf-8-sig'))
    legacy_path = local_path(manifest['legacy_editor'])
    legacy = batdat_text.parse_json(read_verified(legacy_path, manifest['legacy_editor_sha256']).decode('utf-8-sig'))
    document = batdat_legacy.normalize(original, document, legacy)
    return manifest, original, document, table, (original_path, editor_path, table_path, legacy_path)


def prepare(editor=None):
    manifest, original, document, table, inputs = load_editor(editor)
    result, details = batdat_text.rebuild(original, document, table)
    output = inputs[0].with_name(inputs[0].name + '.new')
    return output, result, inputs, details


def extract_editor(check=False):
    manifest = json.loads(local_path('batdat_sources.json').read_text(encoding='utf-8'))
    source = input_path(manifest['original'])
    output = input_path(manifest['edit'])
    original = read_verified(source, manifest['original_sha256'])
    document = batdat_text.extract_document(original)
    if batdat_text.rebuild(original, document, {})[0] != original:
        raise ValueError('Original batdat extraction roundtrip failed')
    data = (json.dumps(document, ensure_ascii=False, indent=2)+'\n').encode('utf-8')
    if not check:
        if output.exists():
            raise FileExistsError(f'Extraction never overwrites existing JSON: {output}')
        if output.with_name(output.name+'.pending').exists():
            raise FileExistsError(f'Inspect interrupted output: {output}.pending')
        write_output(output, data, (source,), overwrite=False)
    return output


def export_editor(destination, editor=None):
    path = Path(destination).resolve()
    working = HOME.parents[1] / '0.X30/bat/kr/batdatEdit'
    if (path.suffix.lower() != '.json' or path.name in ('batdat.json', 'XENOSAGA KOR-JPN.json')
            or not (path.is_relative_to(HOME / 'output') or path.parent == working)):
        raise ValueError('Review JSON must be a new file in the batdat working folder or tools/x30/output')
    if path.exists():
        raise FileExistsError(f'Export refuses to overwrite a file: {path}')
    _, original, document, table, inputs = load_editor(editor)
    batdat_text.rebuild(original, document, table)
    data = (json.dumps(document, ensure_ascii=False, indent=2)+'\n').encode('utf-8')
    path.parent.mkdir(parents=True, exist_ok=True)
    write_output(path, data, inputs, overwrite=False)
    return path, inputs[1]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--check', action='store_true', help='Validate/rebuild without saving')
    mode.add_argument('--export-editor', metavar='PATH', help='Export current translations as full review JSON; never overwrite')
    mode.add_argument('--extract', action='store_true', help='Extract original Japanese to batdat.json; never overwrite')
    parser.add_argument('editor', nargs='?', help='Optional JSON drop; existing editor files are never rewritten')
    args = parser.parse_args(argv)
    try:
        if args.extract:
            if args.editor:
                raise ValueError('Extraction reads the original BIN, not a dropped JSON')
            print(f'Extracted original Japanese: {extract_editor()}')
            return 0
        if args.export_editor:
            path, source = export_editor(args.export_editor, args.editor)
            print(f'Input: {source}')
            print(f'Expanded review JSON: {path}')
            print('Review only: the canonical editor was not replaced. Drop this JSON on patch.bat to test it.')
            print('EXPORT SUCCEEDED')
            return 0
        path, result, inputs, details = prepare(args.editor)
        if not args.check:
            write_output(path, result, inputs)
        for section in details:
            print(f"{section['section']}: {section['pool_bytes']}/{section['pool_capacity']} bytes, "
                  f"free={section['free_bytes']}, changed={section['changed_fields']}, "
                  f"shared_records={section['shared_records']}")
        print(f'batdat: {len(result)} bytes, sha256={hashlib.sha256(result).hexdigest()}')
        print(f'Input: {inputs[1]}')
        print(f'Output: {path}')
        print('Known legacy JSON is normalized in memory; input JSON is never rewritten.')
        print('CHECK PASSED (no files written)' if args.check else 'BUILD SUCCEEDED')
        return 0
    except (OSError, ValueError, KeyError) as exc:
        print(f'BUILD FAILED: {exc}', file=sys.stderr)
        print('Do not apply outputs from a failed run. Previous output may still exist.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
