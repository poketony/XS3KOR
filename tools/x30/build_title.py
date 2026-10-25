"""Export or rebuild only the five title-menu labels; never access the ROM folder."""

import argparse
import hashlib
import sys
from pathlib import Path

from build_menu import HOME
from tools import title_text
from tools.output import validate_outputs, write_output


EDITOR = HOME.parents[1] / '0.X30/mnu/kr/titleobj'


def input_paths():
    return (EDITOR / 'titleobj.xtx',
            *(image_path(EDITOR / (name+'.png')) for name in title_text.LABELS))


def image_path(value, must_exist=True):
    path = Path(value).resolve(strict=must_exist)
    if not any(path.is_relative_to(base) for base in (HOME, HOME.parents[1] / '0.X30')):
        raise ValueError('PNG inputs must stay inside this repository: 0.X30 or tools/x30')
    if path.suffix.lower() != '.png' or path.stem not in title_text.LABELS:
        raise ValueError('Expected new_game/continue/data/disc1/disc2.png')
    return path


def prepare(editors=()):
    selected = {}
    for value in editors:
        path = image_path(value)
        if path.stem in selected:
            raise ValueError(f'Duplicate label input: {path.stem}')
        selected[path.stem] = path
    paths = {name: selected[name] if name in selected else image_path(EDITOR / (name+'.png'))
             for name in title_text.LABELS}
    original = EDITOR / 'titleobj.xtx'
    data, details = title_text.rebuild(original.read_bytes(), {name: path.read_bytes() for name, path in paths.items()})
    output = original.with_name(original.name+'.new')
    return output, data, (original, *paths.values()), details


def export(check=False):
    original = EDITOR / 'titleobj.xtx'
    data = original.read_bytes()
    images = title_text.extract(data)
    if title_text.rebuild(data, images)[0] != data:
        raise ValueError('Title extraction failed its original roundtrip')
    paths = {name: image_path(EDITOR / (name+'.png'), must_exist=False) for name in title_text.LABELS}
    if not check:
        validate_outputs(paths.values(), (original,), overwrite=False)
        for name, path in paths.items():
            write_output(path, images[name], (original,), overwrite=False)
            print(f'Exported: {path}')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--extract', '--export', dest='extract', action='store_true', help='Create five original PNGs; existing editors are never overwritten')
    parser.add_argument('--check', action='store_true', help='Validate in memory, without saving')
    parser.add_argument('editors', nargs='*', help='Optional named label PNGs; remaining labels use their working PNGs')
    args = parser.parse_args(argv)
    try:
        if args.extract:
            if args.editors:
                raise ValueError('--export does not accept PNG inputs')
            export(args.check)
            print('CHECK PASSED (no files written)' if args.check else 'EXTRACT SUCCEEDED')
            return 0
        output, data, inputs, details = prepare(args.editors)
        if not args.check:
            validate_outputs((output,), inputs)
            write_output(output, data, inputs)
        for path in inputs[1:]:
            print(f'Input: {path}')
        for item in details:
            print(f"{item['label']}: changed={item['changed_pixels']}, quantized={item['quantized_pixels']}")
        print(f'Output: {output}')
        print(f'titleobj.xtx: {len(data)} bytes, sha256={hashlib.sha256(data).hexdigest()}')
        print('CHECK PASSED (no files written)' if args.check else 'BUILD SUCCEEDED')
        return 0
    except (OSError, ValueError, ImportError) as exc:
        print(f'BUILD FAILED: {exc}', file=sys.stderr)
        print('Do not apply output from a failed run. PNG support requires Pillow.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
