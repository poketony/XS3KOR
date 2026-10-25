"""Opt-in memory-card title postprocessor. Publish menu and SLPS as one bundle."""

import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import sys

import elf_text_tool as elf
from elfdata import Elf


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
MENU_HASH = '3bb922d9266a2735049aa9733ed3ac2839bb1f3a2d9c59a08cde091b6543ccdf'
MENU_COUNT = 909
MENU_LIMIT = 0x4000
NAME_BASE = 0x2a7
NAME_COUNT = 16
PATCH_VA = 0x23230c
PATCH_WORD = 0x244402a7
HEADER = '# XS3 save-title names v1'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def slots(data, count=MENU_COUNT):
    start = (count+1)*4
    if len(data) < start or struct.unpack_from('<2I', data) != (count, start):
        raise ValueError('Expected the counted menutext TXD layout; do not use an already patched menu')
    result = [None]
    for index in range(1, count+1):
        pointer = struct.unpack_from('<I', data, index*4)[0]
        if pointer == 0:
            result.append(None)
            continue
        if not start <= pointer < len(data):
            raise ValueError(f'Menu pointer out of range: {index}')
        end = data.find(b'\0', pointer)
        if end < 0:
            raise ValueError(f'Menu string has no terminator: {index}')
        result.append(data[pointer:end])
    return result


def convert_pair(first, second):
    # SLPS 001892a8. The PS2 browser uses system SJIS, not the patched game font.
    first = (first+0x80) & 255
    if first & 1:
        second = (second+0x9f) & 255
        first = (first >> 1)+0x71
    else:
        second = (second-3) & 255
        first = (first >> 1)+0x70
    if first > 0x9f:
        first += 0x40
    if second > 0x7e:
        second = (second+1) & 255
    if (first, second) == (0x87, 0x54):
        first, second = 0x82, 0x50
    return bytes((first & 255, second))


def encode_name(text):
    data = text.encode('euc_jis_2004', errors='strict')
    if not data or len(data) > 20 or len(data) % 2 or not all(0xa1 <= b <= 0xfe for b in data):
        raise ValueError('Save names require 1..10 fullwidth two-byte characters; no ASCII or font substitution')
    actual = b''.join(convert_pair(data[i], data[i+1]) for i in range(0, len(data), 2))
    if actual != text.encode('cp932', errors='strict'):
        raise ValueError('Name is incompatible with the actual game-to-system-font converter')
    return data


def parse_names(content):
    lines = content.removeprefix('\ufeff').splitlines()
    if not lines or lines[0] != HEADER:
        raise ValueError('Missing save-title names header')
    values = {}
    for line in lines[1:]:
        if not line or line.startswith('#'):
            continue
        key, separator, text = line.partition('|')
        if not separator or not re.fullmatch(r'[0-9]{1,2}', key):
            raise ValueError('Expected character ID|name, without changing punctuation or whitespace')
        index = int(key)
        if not 1 <= index <= NAME_COUNT or index in values:
            raise ValueError(f'Unknown or duplicate character ID: {index}')
        try:
            values[index] = encode_name(text)
        except (ValueError, UnicodeError) as exc:
            raise ValueError(f'Name {index:02}: {exc}') from exc
    if set(values) != set(range(1, NAME_COUNT+1)):
        raise ValueError('All sixteen character names are required')
    return tuple(values[index] for index in range(1, NAME_COUNT+1))


def export_original_names(menu):
    values = slots(menu)
    lines = [HEADER, '# Original Japanese names, not a translation or a selected release policy.',
             '# ID|name. PS2 system-font names only; no Korean-to-kanji substitution.',
             '# Keep 1..10 fullwidth characters. No automatic punctuation conversion.']
    lines += [f'{index:02}|'+values[NAME_BASE+index+1].decode('euc_jis_2004')
              for index in range(1, NAME_COUNT+1)]
    return '\n'.join(lines)+'\n'


def append_names(menu, names, original):
    old = slots(menu)
    reference = slots(original)
    if len(names) != NAME_COUNT:
        raise ValueError('Expected sixteen save names')
    for name in names:
        if encode_name(name.decode('euc_jis_2004')) != name:
            raise ValueError('Non-roundtripping save name')
    if old[0x277:0x283] != reference[0x277:0x283]:
        raise ValueError('Save-title format, digits or star differ from original; not changed automatically')
    added = (b'', *names)
    old_start, shift = (MENU_COUNT+1)*4, len(added)*4
    result = bytearray(menu[:old_start]+bytes(shift)+menu[old_start:])
    struct.pack_into('<I', result, 0, MENU_COUNT+len(added))
    for index in range(1, MENU_COUNT+1):
        pointer = struct.unpack_from('<I', menu, index*4)[0]
        if pointer:
            struct.pack_into('<I', result, index*4, pointer+shift)
    for index, name in enumerate(added, MENU_COUNT+1):
        struct.pack_into('<I', result, index*4, len(result))
        result.extend(name+b'\0')
    if len(result) > MENU_LIMIT:
        raise ValueError(f'Save-title menu exceeds the 16384-byte resident boundary: {len(result)} bytes')
    if slots(result, MENU_COUNT+len(added)) != [*old, *added]:
        raise ValueError('Existing menu slot contents changed')
    if result[old_start+shift:len(menu)+shift] != menu[old_start:]:
        raise ValueError('Existing menu string-pool bytes changed')
    return bytes(result)


def patch_slps(data, original):
    section = Elf(original).sections['.text']
    offset = section['offset']+PATCH_VA-section['va']
    if len(data) != len(original) or data[offset-4:offset+8] != original[offset-4:offset+8]:
        raise ValueError('Save-title code changed or was already patched')
    if struct.unpack_from('<2I', data, offset-4) != (0x0c000000 | 0x212640//4, PATCH_WORD):
        raise ValueError('Expected the original name-getter call and ADDIU delay slot')
    result = bytearray(data)
    struct.pack_into('<I', result, offset, (PATCH_WORD & 0xffff0000) | MENU_COUNT)
    return bytes(result), offset


def select_inputs(values):
    menu, names = None, elf.local('edit/save_title.names.txt')
    have_names = False
    for value in values:
        path = Path(value).resolve(strict=True)
        if not path.is_file() or not path.is_relative_to(REPO):
            raise ValueError('Explicit inputs must be files inside this repository')
        if path.suffix.lower() == '.txd' and menu is None:
            menu = path
        elif path.suffix.lower() == '.txt' and not have_names and path.is_relative_to(HERE):
            names, have_names = path, True
        else:
            raise ValueError('Drop one menutext TXD and optionally one names TXT inside tools/elf')
    if menu is None:
        raise ValueError('Drag a freshly rebuilt menutext.txd onto this BAT, or give its path on the command line')
    if menu.stat().st_size > MENU_LIMIT:
        raise ValueError('Input menu already exceeds the 16384-byte resident boundary')
    return menu, names


def check_inputs(hashes):
    for path, expected in hashes.items():
        if sha(path.read_bytes()) != expected:
            raise ValueError(f'Input changed during the build: {path}')


def prepare(values):
    menu, names = select_inputs(values)
    reference = elf.local('original/menutext.txd')
    source = elf.local('original/SLPS.original')
    editor = elf.editor_path('SLPS')
    mapping = elf.local('XENOSAGA KOR-JPN.json')
    snapshots = {path: path.read_bytes() for path in (menu, names, reference, source, editor, mapping)}
    hashes = {path: sha(data) for path, data in snapshots.items()}
    if hashes[reference] != MENU_HASH or hashes[mapping] != elf.TABLE_HASH:
        raise ValueError('Original menu or game-font mapping changed')
    parsed = parse_names(snapshots[names].decode('utf-8-sig'))
    translated = elf.build_blob('SLPS', snapshots[source], snapshots[editor].decode('utf-8-sig'),
                                json.loads(snapshots[mapping].decode('utf-8-sig'))['replace-table'])
    patched, offset = patch_slps(translated, snapshots[source])
    extended = append_names(snapshots[menu], parsed, snapshots[reference])
    outputs = {'menutext.txd.new': extended, 'SLPS_256.40.new': patched, 'SLPS_256.41.new': patched}
    report = {'format': 'XS3 paired save-title patch v1', 'game_runtime_verified': False,
              'apply_together': list(outputs), 'never_mix_with_unpatched_menu_or_slps': True,
              'input_sha256': {p.relative_to(REPO).as_posix(): h for p, h in hashes.items()},
              'output_sha256': {name: sha(data) for name, data in outputs.items()},
              'names_from_editor': [name.decode('euc_jis_2004') for name in parsed],
              'menu_count': MENU_COUNT+NAME_COUNT+1, 'menu_bytes': len(extended),
              'menu_capacity_bytes': MENU_LIMIT, 'private_name_base': MENU_COUNT,
              'slps_patch_va': f'{PATCH_VA:08X}', 'slps_patch_offset': offset,
              'slps_patch_bytes': [offset, offset+1], 'original_menu_slots_and_pool_preserved': True}
    check_inputs(hashes)
    return outputs, report, hashes


def publish(outputs, report, hashes, name):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}', name):
        raise ValueError('Bundle name must be 1..64 ASCII letters, digits, underscores or hyphens')
    target = elf.local('output/save-title/'+name)
    pending = target.with_name(name+'.pending')
    if target.exists() or pending.exists():
        raise FileExistsError('Bundle or interrupted .pending already exists; choose a new name')
    check_inputs(hashes)
    pending.mkdir(parents=True)
    for filename, data in outputs.items():
        path = pending / filename
        with path.open('xb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if path.read_bytes() != data:
            raise ValueError(f'Output verification failed: {filename}')
    with (pending / 'VERIFIED.json').open('x', encoding='utf-8') as stream:
        json.dump(report, stream, ensure_ascii=True, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    check_inputs(hashes)
    pending.rename(target)
    return target


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('inputs', nargs='*', help='One rebuilt menutext TXD; optional names TXT')
    parser.add_argument('--check', action='store_true', help='Validate in memory without saving')
    parser.add_argument('--name', help='New bundle name; default is a unique UTC timestamp')
    args = parser.parse_intermixed_args(argv)
    try:
        outputs, report, hashes = prepare(args.inputs)
        if not args.check:
            name = args.name or datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d-%H%M%S-%f')
            target = publish(outputs, report, hashes, name)
            print(f'Bundle: {target}')
        print(f"Menu: {report['menu_bytes']}/{MENU_LIMIT} bytes; private names: {NAME_COUNT}")
        print('Apply this bundle menu and the matching disc SLPS together. No automatic ROM copy.')
        print('CHECK PASSED (no files written)' if args.check else 'BUILD SUCCEEDED')
        return 0
    except (OSError, ValueError, KeyError) as exc:
        print(f'BUILD FAILED: {exc}', file=sys.stderr)
        print('Never apply an incomplete .pending bundle or mix files from different bundles.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
