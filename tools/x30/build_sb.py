"""Build existing X30 field/battle SB editors using local verified originals."""

import argparse
import hashlib
import json
import sys

from build_menu import explicit_editor, input_path, local_path, read_verified
from tools import sb_text
from tools.output import write_output


def normalize_editor(original, content, restored=None):
    if restored is None:
        return content
    first = sb_text.read_rows(original)[0]
    if not first['editable'] or hex(first['address']) != restored['address'] or first['text'] != restored['text']:
        raise ValueError('Recorded legacy SB omission disagrees with the original')
    if first['address'] in sb_text.parse_text(content):
        return content
    return (f'[{first["address"]:#x}]\n'+first['text'].replace('\n', '[n]')+'\n\n'
            + content.removeprefix('\ufeff'))


def prepare(group=None, asset_name=None, editors=(), extract=False):
    manifest = json.loads(local_path('sb_sources.json').read_text(encoding='utf-8'))
    if extract and editors:
        raise ValueError('Extraction reads registered originals; select --group or --asset, not TXT drops')
    assets = {name: asset for name, asset in manifest['assets'].items() if 'edit' in asset}
    if group is not None and asset_name is not None:
        raise ValueError('Select either an SB group or one asset')
    overrides = {}
    for value in editors:
        path = explicit_editor(value)
        matches = [name for name in assets if
                   (name == asset_name if asset_name else name.rsplit('/', 1)[1].lower() == path.stem.lower())
                   and (group is None or name.startswith(group+'/'))]
        if len(matches) != 1:
            raise ValueError(f'Cannot select one configured SB for: {path.name}')
        name = matches[0]
        if name in overrides:
            raise ValueError(f'Duplicate SB input: {name}')
        overrides[name] = path
    if asset_name is not None:
        if asset_name not in assets:
            raise ValueError(f'No configured SB editor: {asset_name}')
        names = (asset_name,)
    elif overrides:
        names = tuple(overrides)
    else:
        names = tuple(name for name in assets if group is None or name.startswith(group + '/'))
    if not names:
        raise ValueError('No SB assets selected')
    results = []
    restored = {row['asset']: row for row in manifest['restored_first_rows']}
    tables = {}
    for name in names:
        asset = assets[name]
        table_path = input_path(manifest['charmaps'][name.split('/')[0]])
        if table_path not in tables:
            tables[table_path] = json.loads(read_verified(table_path, manifest['charmap_sha256']).decode('utf-8-sig'))['replace-table']
            if not tables[table_path] or any(len(k) != 1 or not isinstance(v, str) or not v for k, v in tables[table_path].items()):
                raise ValueError('Expected a nonempty single-character substitution table')
        charmap = tables[table_path]
        original_path = input_path(asset['original'])
        editor_path = overrides[name] if name in overrides else input_path(asset['edit'])
        original = read_verified(original_path, asset['original_sha256'])
        if extract:
            content = sb_text.extract_text(original)
            if sb_text.rebuild(original, content, charmap) != original:
                raise ValueError(f'Extraction roundtrip failed: {name}')
            results.append((name, editor_path, content.encode('utf-8'), (original_path, table_path)))
            continue
        content = editor_path.read_text(encoding='utf-8-sig')
        try:
            content = normalize_editor(original, content, restored.get(name))
            result = sb_text.rebuild(original, content, charmap)
        except (ValueError, UnicodeError) as exc:
            raise ValueError(f'{name}: {exc}') from exc
        output = original_path.with_name(original_path.name + '.new')
        results.append((name, output, result, (original_path, editor_path, table_path)))
    return results


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument('--group', choices=('cf', 'bat'))
    selection.add_argument('--asset', help='One configured editor, e.g. cf/8050 or bat/REN_B01')
    parser.add_argument('--check', action='store_true', help='Rebuild and verify without writing')
    parser.add_argument('--extract', action='store_true', help='Extract original Japanese to canonical TXT; refuse existing files')
    parser.add_argument('--require-editors', action='store_true', help='Drop-only launcher: fail when no TXT was supplied')
    parser.add_argument('editors', nargs='*', help='Optional TXT drops; filenames select assets within the chosen group')
    args = parser.parse_args(argv)
    try:
        if args.require_editors and not args.editors:
            raise ValueError('Drop-only mode requires one or more TXT files')
        results = prepare(args.group, args.asset, args.editors, extract=args.extract)
        protected = tuple(path for item in results for path in item[3])
        if not args.check:
            # Every input and pending output is checked before the first publication.
            resolved_inputs = {path.resolve() for path in protected}
            input_ids = {(path.stat().st_dev, path.stat().st_ino) for path in protected}
            output_ids, output_paths = set(), set()
            for _, output, _, _ in results:
                if args.extract and output.exists():
                    raise FileExistsError(f'Extraction never overwrites existing TXT: {output}')
                if output.with_name(output.name + '.pending').exists():
                    raise FileExistsError(f'Interrupted write must be inspected first: {output}.pending')
                resolved = output.resolve()
                if resolved in resolved_inputs or resolved in output_paths:
                    raise ValueError(f'Output aliases an input or another output: {output}')
                output_paths.add(resolved)
                if output.exists():
                    info = output.stat()
                    identity = (info.st_dev, info.st_ino)
                    if identity in input_ids or identity in output_ids:
                        raise ValueError(f'Output aliases an input or another output: {output}')
                    output_ids.add(identity)
            for _, output, result, inputs in results:
                write_output(output, result, inputs, overwrite=not args.extract)
        if args.asset:
            name, _, result, _ = results[0]
            print(f'{name}: {len(result)} bytes, sha256={hashlib.sha256(result).hexdigest()}')
        if not args.extract and (args.editors or args.asset):
            for name, output, _, inputs in results:
                print(f'{name}: {inputs[1]} -> {output}')
        print('Extraction refuses existing TXT; rebuild never rewrites input TXT or original SB.')
        print(f'SB files verified: {len(results)}; total bytes: {sum(len(item[2]) for item in results)}')
        print('CHECK PASSED (no files written)' if args.check else 'BUILD SUCCEEDED')
        return 0
    except (OSError, ValueError, KeyError) as exc:
        print(f'BUILD FAILED: {exc}', file=sys.stderr)
        print('Do not apply outputs from a failed run. Previous outputs may still exist.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
