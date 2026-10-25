"""Validate and publish native PNG/JPEG editors without re-encoding or ROM access."""

import argparse
import hashlib
import io
import json
from pathlib import Path
import struct
import sys

from PIL import Image

from build_menu import HOME, SYNOPSIS_IMAGE_IDS, DATABASE_IMAGE_IDS, input_path, local_path, read_verified
from tools.output import validate_outputs, write_output


ASSETS = {
    'title1': ('../../0.X30/mnu/kr/title1.png', 'mnu/jp/title1.png', 'PNG', 0x100000),
    'intm10': ('../../0.X30/mnu/intm/10.jpg', 'mnu/intm/10.jpg', 'JPEG', 0x40000),
    'wall': ('../../0.X30/mnu/kr/wall.jpg', 'mnu/jp/wall.jpg', 'JPEG', 512 * 448),
}
ASSETS.update({f'syno{index:03}': (f'../../0.X30/mnu/syno/{index:03}.jpg',
                               f'mnu/syno/{index:03}.jpg', 'JPEG', 0x1fe00)
               for index in SYNOPSIS_IMAGE_IDS})
ASSETS.update({f'dtimg{index:04}': (f'../../0.X30/jpg/kr/dtimg_{index:04}.jpg',
                                f'jpg/dtimg_{index:04}.jpg', 'JPEG', 0x7800)
               for index in DATABASE_IMAGE_IDS})


def archive_paths(name):
    paths = (ASSETS[name][1],)
    if name.startswith('dtimg'):
        # Both original IDs contain identical bytes; maintain just one editor.
        paths += (f'jpg/dtimg_{int(name[5:])+1000:04}.jpg',)
    return paths


def input_paths(names=None):
    manifest = json.loads(local_path('native_sources.json').read_text(encoding='utf-8'))
    return tuple(input_path(value) for name in (ASSETS if names is None else names)
                 for value in (ASSETS[name][0], manifest['assets'][name]['original']))


def check_jpeg_scan(data, name):
    # SLPS 0018df68 handles SOF0; 0018da30 expects one three-component scan.
    pos, scan, frame = 2, False, False
    while pos < len(data):
        if scan:
            pos = data.find(b'\xff', pos)
            if pos < 0:
                break
        if data[pos] != 255:
            raise ValueError('Invalid JPEG marker boundary')
        while pos < len(data) and data[pos] == 255:
            pos += 1
        if pos == len(data):
            break
        marker = data[pos]
        pos += 1
        if scan:
            if marker == 0 or 0xd0 <= marker <= 0xd7:
                continue
            if marker == 0xd9 and pos == len(data):
                return
            raise ValueError(f'{name}: expected a single baseline JPEG scan')
        if pos+2 > len(data):
            break
        size = int.from_bytes(data[pos:pos+2], 'big')
        if size < 2 or pos+size > len(data):
            raise ValueError('Truncated JPEG marker')
        payload = data[pos+2:pos+size]
        if 0xc0 <= marker <= 0xcf and marker not in (0xc4, 0xc8, 0xcc):
            if marker != 0xc0 or frame:
                raise ValueError(f'{name}: only baseline SOF0 JPEG is supported')
            frame = True
        if marker == 0xda:
            if not frame or payload != bytes((3, 1, 0, 2, 17, 3, 17, 0, 63, 0)):
                raise ValueError(f'{name}: expected standard Y/Cb/Cr scan and Huffman selectors')
            scan = True
        pos += size
    raise ValueError('Truncated JPEG scan')


def validate(data, name):
    _, _, format_name, capacity = ASSETS[name]
    size = (211, 134) if name.startswith('dtimg') else (512, 448)
    if not data or len(data) > capacity:
        raise ValueError(f'{name}: image exceeds the {capacity}-byte loader input buffer')
    if format_name == 'PNG':
        if (len(data) < 33 or data[:16] != b'\x89PNG\r\n\x1a\n\0\0\0\rIHDR'
                or struct.unpack('>2I5B', data[16:29]) != (512, 448, 8, 6, 0, 0, 0)):
            raise ValueError('title1: expected non-interlaced 512x448, 8-bit RGBA PNG')
    elif not data.startswith(b'\xff\xd8') or not data.endswith(b'\xff\xd9'):
        raise ValueError(f'{name}: missing JPEG start/end marker')
    else:
        check_jpeg_scan(data, name)
    with Image.open(io.BytesIO(data)) as image:
        if image.format != format_name or image.size != size or getattr(image, 'n_frames', 1) != 1:
            raise ValueError(f'{name}: expected a single {size[0]}x{size[1]} {format_name} image')
        if format_name == 'JPEG' and (image.mode != 'RGB' or image.bits != 8
                or image.info.get('progressive') or image.info.get('progression')):
            raise ValueError(f'{name}: expected 8-bit RGB baseline JPEG, not progressive/CMYK')
        if format_name == 'JPEG' and image.layer not in [
                [(1, h, v, 0), (2, 1, 1, 1), (3, 1, 1, 1)] for h, v in ((1, 1), (2, 1), (2, 2))]:
            raise ValueError(f'{name}: expected standard YCbCr 4:4:4, 4:2:2 or 4:2:0 components')
        image.verify()
    with Image.open(io.BytesIO(data)) as image:
        image.load()


def prepare(names=None, editor=None, extract=False):
    names = tuple(ASSETS if names is None else names)
    if not names or any(name not in ASSETS for name in names) or len(set(names)) != len(names):
        raise ValueError('Select declared native images once each: ' + ', '.join(ASSETS))
    if editor is not None and len(names) != 1:
        raise ValueError('A dropped image requires exactly one --asset')
    if extract and editor is not None:
        raise ValueError('Extraction does not accept image overrides')
    override = None
    if editor is not None:
        override = Path(editor).resolve(strict=True)
        if not override.is_file() or not any(override.is_relative_to(root)
                for root in (HOME, HOME.parents[1] / '0.X30')):
            raise ValueError('Images must be files inside this repository: 0.X30 or tools/x30')
    results = []
    manifest = json.loads(local_path('native_sources.json').read_text(encoding='utf-8'))
    for name in names:
        default = input_path(ASSETS[name][0])
        asset = manifest['assets'][name]
        if asset['edit'] != ASSETS[name][0]:
            raise ValueError(f'{name}: native editor manifest mismatch')
        original = input_path(asset['original'])
        raw = read_verified(original, asset['original_sha256'])
        source = override if override is not None else default
        data = raw if extract else source.read_bytes()
        validate(data, name)
        if extract:
            results.append((name, default, data, (original,)))
        else:
            for game_path in archive_paths(name):
                output = default.parent / (Path(game_path).name+'.new')
                results.append((name, output, data, (source, original)))
    return results


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument('--asset', choices=ASSETS)
    selection.add_argument('--synopsis', action='store_true', help='Build the 71 synopsis images, or one named JPG drop')
    selection.add_argument('--database', action='store_true', help='Build 25 database images and their +1000 duplicates, or one named JPG pair')
    parser.add_argument('--check', action='store_true', help='Validate without saving')
    parser.add_argument('--extract', action='store_true', help='Restore pristine images without replacing existing editors')
    parser.add_argument('editor', nargs='?', help='Optional image override; requires --asset')
    args = parser.parse_args(argv)
    try:
        names = (args.asset,) if args.asset else None
        if args.synopsis:
            names = tuple(f'syno{index:03}' for index in SYNOPSIS_IMAGE_IDS)
            if args.editor:
                supplied = Path(args.editor)
                name = 'syno'+supplied.stem
                if supplied.suffix.lower() != '.jpg' or name not in names:
                    raise ValueError('Synopsis drops require an original filename such as 010.jpg; use --asset syno010 for a custom filename')
                names = (name,)
        if args.database:
            names = tuple(f'dtimg{index:04}' for index in DATABASE_IMAGE_IDS)
            if args.editor:
                supplied = Path(args.editor)
                name = supplied.stem.replace('dtimg_', 'dtimg', 1)
                if supplied.suffix.lower() != '.jpg' or supplied.stem != 'dtimg_'+name[5:] or name not in names:
                    raise ValueError('Database drops require a working filename such as dtimg_0393.jpg; use --asset dtimg0393 for a custom filename')
                names = (name,)
        results = prepare(names, args.editor, extract=args.extract)
        protected = tuple(path for item in results for path in item[3])
        if not args.check:
            validate_outputs((row[1] for row in results), protected, overwrite=not args.extract)
        for name, output, data, inputs in results:
            if not args.check:
                write_output(output, data, inputs, overwrite=not args.extract)
            print(f'Input: {inputs[0]}')
            print(f'Output: {output}')
            print(f'{name}: {len(data)} bytes, sha256={hashlib.sha256(data).hexdigest()} (no re-encoding)')
        print('CHECK PASSED (no files written)' if args.check else 'EXTRACT SUCCEEDED' if args.extract else 'BUILD SUCCEEDED')
        return 0
    except (OSError, ValueError, SyntaxError) as exc:
        print(f'BUILD FAILED: {exc}', file=sys.stderr)
        print('Do not apply output from a failed run. Images were not re-encoded.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
