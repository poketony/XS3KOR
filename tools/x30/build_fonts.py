"""Build both X30 fonts from local PNG sheets, preserving the original tails."""

import argparse
import hashlib
import io
import json
import sys
from pathlib import Path

from build_menu import HOME, input_path, local_path, read_verified
from tools import font_bitmap
from tools.output import validate_outputs, write_output


NAMES = ('font0', 'font1')
EDITOR = HOME.parents[1] / '0.X30/mnu/kr/fonts'


def input_paths():
    manifest = json.loads(local_path('font_sources.json').read_text(encoding='utf-8'))
    return tuple(input_path(value) for asset in manifest['assets'].values()
                 for value in (asset['original'], *(row['edit'] for row in asset['channels'].values())))


def prepare(names=None, sheets=(), extract=False):
    if extract and sheets:
        raise ValueError('Extraction does not accept PNG overrides')
    overrides = {}
    for value in sheets:
        path = Path(value).resolve(strict=True)
        if not any(path.is_relative_to(root) for root in (HOME, HOME.parents[1] / '0.X30')):
            raise ValueError('Font PNGs must stay inside this repository: 0.X30 or tools/x30')
        matches = [(name, channel) for name in NAMES for channel in font_bitmap.CHANNELS
                   if path.name.lower() == f'{name}_{channel}.png']
        if len(matches) != 1:
            raise ValueError('Expected font0/font1_red/green/blue/alpha.png')
        key = matches[0]
        if key in overrides:
            raise ValueError(f'Duplicate font sheet: {path.name}')
        overrides[key] = path
    if names is None:
        names = tuple(name for name in NAMES if not overrides or any(key[0] == name for key in overrides))
    names = tuple(names)
    if not names or len(set(names)) != len(names) or any(name not in NAMES for name in names):
        raise ValueError('Select each known font at most once')
    if any(name not in names for name, _ in overrides):
        raise ValueError('Dropped PNG does not belong to the selected font')
    manifest = json.loads(local_path('font_sources.json').read_text(encoding='utf-8'))
    results = []
    for name in names:
        asset = manifest['assets'][name]
        original_path = input_path(asset['original'])
        original = read_verified(original_path, asset['original_sha256'])
        if set(asset['channels']) != set(font_bitmap.CHANNELS):
            raise ValueError(f'{name}: incomplete channel manifest')
        paths = {channel: input_path(asset['channels'][channel]['edit']) for channel in font_bitmap.CHANNELS}
        paths.update({channel: path for (font, channel), path in overrides.items() if font == name})
        if extract:
            from PIL import Image
            images = {}
            for channel, pixels in font_bitmap.unpack(original).items():
                stream = io.BytesIO()
                Image.frombytes('L', font_bitmap.SIZE, pixels).save(stream, format='PNG')
                images[channel] = stream.getvalue()
            if font_bitmap.rebuild(original, images) != original:
                raise ValueError(f'{name}: extraction failed its original roundtrip')
            results.extend((name+'_'+channel, paths[channel], data, (original_path,))
                           for channel, data in images.items())
            continue
        try:
            result = font_bitmap.rebuild(original, {channel: path.read_bytes() for channel, path in paths.items()})
        except (OSError, ValueError) as exc:
            raise ValueError(f'{name}: {exc}') from exc
        output = original_path.with_name(original_path.name+'.new')
        results.append((name, output, result, (original_path, *paths.values())))
    return results


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--asset', choices=NAMES)
    parser.add_argument('--check', action='store_true', help='Validate/rebuild without saving')
    parser.add_argument('--extract', action='store_true', help='Extract original PNG sheets without overwriting')
    parser.add_argument('sheets', nargs='*', help='Optional named font PNGs; other channels use their working sheets')
    args = parser.parse_args(argv)
    try:
        results = prepare((args.asset,) if args.asset else None, args.sheets, extract=args.extract)
        protected = tuple(path for item in results for path in item[3])
        if not args.check:
            validate_outputs((row[1] for row in results), protected, overwrite=not args.extract)
            for _, output, result, _ in results:
                write_output(output, result, protected, overwrite=not args.extract)
        for name, output, result, inputs in results:
            for path in inputs[1:]:
                print(f'Input: {path}')
            print(f'Output: {output}')
            print(f'{name}: {len(result)} bytes, sha256={hashlib.sha256(result).hexdigest()}')
        print('CHECK PASSED (no files written)' if args.check else 'EXTRACT SUCCEEDED' if args.extract else 'BUILD SUCCEEDED')
        return 0
    except ImportError as exc:
        print(f'BUILD FAILED: {exc}. Font PNG support requires Pillow in this Python environment.', file=sys.stderr)
        return 1
    except (OSError, ValueError, KeyError) as exc:
        print(f'BUILD FAILED: {exc}', file=sys.stderr)
        print('Do not apply outputs from a failed run. Previous outputs may still exist.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
