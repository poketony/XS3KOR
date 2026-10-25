"""Rebuild ten shared HUD labels in window0/1/2, keeping each original's other bytes."""

import argparse
import hashlib
from pathlib import Path
import sys

from build_menu import HOME, input_path
from tools import window_text
from tools.output import validate_outputs, write_output


EDITOR = HOME.parents[1] / '0.X30/mnu/kr/window'


def input_paths():
    return (*(EDITOR / (name+'.xtx') for name in window_text.SOURCES),
            *(input_path(EDITOR / (name+'.png')) for name in window_text.LABELS))


def prepare(editors=(), extract=False):
    if extract:
        if editors:
            raise ValueError('Extraction does not accept PNG overrides')
        sources = tuple(EDITOR / (name+'.xtx') for name in window_text.SOURCES)
        images = None
        for name, path in zip(window_text.SOURCES, sources):
            data = path.read_bytes()
            current = window_text.extract(data, name)
            if images is not None and current != images:
                raise ValueError('Window variants no longer share identical label images')
            if window_text.rebuild(data, current, name)[0] != data:
                raise ValueError(f'{name}: extraction failed its original roundtrip')
            images = current
        return [(name, EDITOR / (name+'.png'), data, sources) for name, data in images.items()], {}
    selected = {}
    for value in editors:
        path = Path(value).resolve(strict=True)
        if not path.is_file() or not any(path.is_relative_to(base) for base in (HOME, HOME.parents[1] / '0.X30')):
            raise ValueError('PNG inputs must be files inside this repository: 0.X30 or tools/x30')
        if path.suffix.lower() != '.png' or path.stem not in window_text.LABELS:
            raise ValueError('Use an original window label filename: '+', '.join(window_text.LABELS))
        if path.stem in selected:
            raise ValueError(f'Duplicate label input: {path.stem}')
        selected[path.stem] = path
    paths = {name: selected[name] if name in selected else input_path(EDITOR / (name+'.png'))
             for name in window_text.LABELS}
    images = {name: path.read_bytes() for name, path in paths.items()}
    results, details = [], {}
    for name in window_text.SOURCES:
        original = EDITOR / (name+'.xtx')
        data, details[name] = window_text.rebuild(original.read_bytes(), images, name)
        results.append((name, original.with_name(original.name+'.new'), data, (original, *paths.values())))
    return results, details


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Validate without saving')
    parser.add_argument('--extract', action='store_true', help='Extract original PNGs without replacing existing editors')
    parser.add_argument('editors', nargs='*', help='Named label PNG overrides; other labels use working PNGs')
    args = parser.parse_args(argv)
    try:
        results, details = prepare(args.editors, extract=args.extract)
        protected = tuple(path for row in results for path in row[3])
        if not args.check:
            validate_outputs((row[1] for row in results), protected, overwrite=not args.extract)
            for _, output, data, _ in results:
                write_output(output, data, protected, overwrite=not args.extract)
        for path in results[0][3][1:]:
            print(f'Input: {path}')
        for name, output, data, _ in results:
            print(f'Output: {output}')
            print(f'{name}: {len(data)} bytes, sha256={hashlib.sha256(data).hexdigest()}')
            for item in details.get(name, ()):
                print(f"  {item['label']}: changed={item['changed_pixels']}, quantized={item['quantized_pixels']}")
        print('Original palettes and all non-label bytes preserved. Inspect quantized colors in game.')
        print('CHECK PASSED (no files written)' if args.check else 'EXTRACT SUCCEEDED' if args.extract else 'BUILD SUCCEEDED')
        return 0
    except (OSError, ValueError, ImportError) as exc:
        print(f'BUILD FAILED: {exc}', file=sys.stderr)
        print('Do not apply outputs from a failed run. PNG support requires Pillow.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
