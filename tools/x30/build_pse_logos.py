"""Rebuild the three PSE logo TM2 files from canonical PNGs, without ROM access."""

import argparse
import hashlib
from pathlib import Path
import sys

from build_menu import HOME, input_path
from tools import pse_logo
from tools.output import validate_outputs, write_output


NAMES = tuple(pse_logo.ASSETS)


def input_paths(names=None):
    paths = []
    for name in NAMES if names is None else names:
        paths.extend((input_path('../../0.X30/mnu/pse/kr/'+name+'.tm2'),
                      input_path('../../0.X30/mnu/pse/kr/'+name+'.png')))
    return tuple(paths)


def prepare(names=None, editor=None, extract=False):
    names = tuple(NAMES if names is None else names)
    if not names or len(set(names)) != len(names) or any(name not in NAMES for name in names):
        raise ValueError('Select each known PSE logo at most once')
    if editor is not None and len(names) != 1:
        raise ValueError('A dropped PNG requires one logo asset')
    if extract and editor is not None:
        raise ValueError('Extraction does not accept PNG overrides')
    override = None
    if editor is not None:
        override = Path(editor).resolve(strict=True)
        if not override.is_file() or override.suffix.lower() != '.png' or not any(
                override.is_relative_to(base) for base in (HOME, HOME.parents[1] / '0.X30')):
            raise ValueError('PNG input must be a file inside this repository: 0.X30 or tools/x30')
    results = []
    for name in names:
        original, default = input_paths((name,))
        source = override if override is not None else default
        raw = original.read_bytes()
        if extract:
            data = pse_logo.extract(raw, name)
            if pse_logo.rebuild(raw, data, name) != raw:
                raise ValueError(f'{name}: extraction failed its original roundtrip')
            results.append((name, default, data, (original,)))
        else:
            data = pse_logo.rebuild(raw, source.read_bytes(), name)
            results.append((name, original.with_name(original.name+'.new'), data, (original, source)))
    return results


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--asset', choices=NAMES)
    parser.add_argument('--check', action='store_true', help='Validate without saving')
    parser.add_argument('--extract', action='store_true', help='Extract original PNGs without replacing existing editors')
    parser.add_argument('editor', nargs='?', help='Optional PNG; its original name selects the logo')
    args = parser.parse_args(argv)
    try:
        name = args.asset
        if args.editor and name is None:
            supplied = Path(args.editor)
            name = supplied.stem.lower()
            if supplied.suffix.lower() != '.png' or name not in NAMES:
                raise ValueError('Cannot select logo from filename; specify --asset')
        results = prepare((name,) if name else None, args.editor, extract=args.extract)
        protected = tuple(path for item in results for path in item[3])
        if not args.check:
            validate_outputs((row[1] for row in results), protected, overwrite=not args.extract)
            for _, output, data, _ in results:
                write_output(output, data, protected, overwrite=not args.extract)
        for name, output, data, inputs in results:
            print(f'Input: {inputs[-1]}')
            print(f'Output: {output}')
            print(f'{name}.tm2: {len(data)} bytes, sha256={hashlib.sha256(data).hexdigest()}')
        print('Header/dimensions preserved; PNG alpha mapped to game range 0..128.')
        print('CHECK PASSED (no files written)' if args.check else 'EXTRACT SUCCEEDED' if args.extract else 'BUILD SUCCEEDED')
        return 0
    except (OSError, ValueError, KeyError) as exc:
        print(f'BUILD FAILED: {exc}', file=sys.stderr)
        print('Do not apply outputs from a failed run. Previous outputs may still exist.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
