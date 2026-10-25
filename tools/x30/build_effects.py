"""Rebuild ESD and matching map labels from one shared PNG per location."""

import argparse
import hashlib
import json
from pathlib import Path
import sys

from tools import effect_labels
from tools.output import write_output


HOME = Path(__file__).resolve().parent
ROOT = HOME.parents[1]
CONFIG = HOME / 'effect_sources.json'


def local(relative):
    path = (ROOT / relative).resolve()
    if not path.is_relative_to(ROOT / '0.X30/ef'):
        raise ValueError('Effect paths must stay inside 0.X30/ef')
    return path


def manifest():
    return json.loads(CONFIG.read_text(encoding='utf-8'))


def input_paths():
    config = manifest()
    owners = shared_editors(config)
    return tuple(dict.fromkeys((CONFIG, *(local(path) for row in config['assets']
                                         for path in (row['source'], owners[row['texture_name']])))))


def shared_editors(config):
    owners = {}
    for row in config['assets']:
        if row['group'] == 'esd':
            name = row['texture_name']
            if name in owners:
                raise ValueError(f'Ambiguous shared location image: {name}')
            owners[name] = row['editor']
    if any(row['texture_name'] not in owners for row in config['assets']):
        raise ValueError('Every map label must have a registered ESD editor')
    return owners


def select(group, editors, extract=False):
    config = manifest()
    if group not in (None, 'esd', 'map'):
        raise ValueError('Unknown effect group')
    owners = shared_editors(config)
    rows = [r for r in config['assets']
            if group is None or r['group'] == group or (group == 'esd' and not extract)]
    if editors:
        selected = []
        seen = set()
        for value in editors:
            path = Path(value).resolve(strict=True)
            matches = [r for r in rows
                       if local(r['editor'] if extract else owners[r['texture_name']]) == path]
            if not matches or path in seen:
                raise ValueError('Drop each registered PNG once; rebuild uses shared PNGs in ef/esd/kr')
            seen.add(path)
            selected.extend(matches)
        rows = selected
    if not rows:
        raise ValueError('No selected effect labels')
    return config, rows


def prepare(group=None, editors=(), extract=False):
    config, rows = select(group, editors, extract)
    owners = shared_editors(config)
    pngs = {}
    results = []
    for row in rows:
        source = local(row['source'])
        editor = local(row['editor'] if extract else owners[row['texture_name']])
        data = source.read_bytes()
        if hashlib.sha256(data).hexdigest() != row['source_sha256']:
            raise ValueError(f'Effect source changed: {source.name}')
        found = effect_labels.locations(data, config['label_names'])
        if len(found) != 1 or found[0][0].name != row['texture_name']:
            raise ValueError(f'Expected exactly the registered location label: {source.name}')
        image, pal = found[0]
        if extract:
            output, result, detail = editor, effect_labels.extract(data, image, pal), {}
            protected = (source, CONFIG)
        else:
            output = source.with_name(source.name+'.new')
            if editor not in pngs:
                pngs[editor] = editor.read_bytes()
            result, detail = effect_labels.rebuild(data, image, pal, pngs[editor])
            protected = (source, editor, CONFIG)
        results.append((row, output, result, protected, detail))
    return results


def publish(results, extract=False):
    protected = tuple(path for row in results for path in row[3])
    outputs = [r[1] for r in results]
    if len(outputs) != len(set(outputs)):
        raise ValueError('Duplicate effect output path')
    # Check the complete batch before creating the first file.
    for output in outputs:
        if output.with_name(output.name+'.pending').exists():
            raise FileExistsError(f'Inspect interrupted output: {output.name}.pending')
        if extract and output.exists():
            raise FileExistsError(f'Extraction never overwrites existing PNG: {output}')
        if output.resolve() in {p.resolve() for p in protected}:
            raise ValueError('Output aliases an input')
    for _, output, data, _, _ in results:
        write_output(output, data, protected, overwrite=not extract)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--group', choices=('esd', 'map'),
                        help='esd rebuilds ESD plus matching maps; map rebuilds maps only')
    parser.add_argument('--extract', action='store_true')
    parser.add_argument('--check', action='store_true')
    parser.add_argument('editors', nargs='*', help='Shared location PNGs in 0.X30/ef/esd/kr')
    args = parser.parse_args(argv)
    try:
        results = prepare(args.group, args.editors, args.extract)
        if not args.check:
            publish(results, args.extract)
        for _, output, data, protected, detail in results:
            if not args.extract:
                print(f'Input: {protected[1]}')
            print(f'{output}: {len(data)} bytes'+(f', {detail}' if detail else ''))
        print('CHECK PASSED (no files written)' if args.check else 'BUILD SUCCEEDED')
        return 0
    except (OSError, ValueError, KeyError, ImportError) as exc:
        print(f'FAILED: {exc}', file=sys.stderr)
        print('Do not apply results of a failed run. Existing PNGs are never replaced by extraction.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
