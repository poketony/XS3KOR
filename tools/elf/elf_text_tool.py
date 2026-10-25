"""XS3 original-based ELF text export/build. Never modifies input executables."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys

from elfdata import Elf, read_string


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
EDITOR = REPO / 'discmetadata'
TABLE_HASH = '1f461ef9eee4b58a856ef214e80f38ffa84c24865bddd7a494662685f00ab007'
DESKTOP_HASH = '25a92b9079590bc33aeba8c009bee84de17508ab02ee320fd54fede09f1adcaf'
ASSETS = {
    'SLPS': {
        'source': 'SLPS.original',
        'sha256': 'b82b6744bac7b9557cce5cadde1c721b90fd2959d576828882b05feb03a54ec9',
        'outputs': ('SLPS_256.40.new', 'SLPS_256.41.new'),
        'slots': ((0x410780, 33, 39), (0x4107C8, 37, 39), (0x4107F0, 33, 39),
                  (0x41EE70, 104, 111)),
    },
    'OV04': {
        'source': 'OV04.OVL',
        'sha256': 'f9d5644bc55a6b2aa40b444ad1767df55c27e1949a2b4b18bc3074fd1d4d1198',
        'outputs': ('OV04.OVL.new',),
        'slots': ((0x3DDA8, 11, 11), (0x3F020, 26, 31), (0x3F040, 32, 39),
                  (0x3F068, 12, 15), (0x3F078, 16, 23), (0x3F090, 16, 23),
                  (0x3F0A8, 4, 7), (0x3F0B0, 10, 15), (0x3F0C0, 4, 7),
                  (0x3F0C8, 12, 15), (0x3F0D8, 10, 15), (0x3F0E8, 14, 15),
                  (0x40400, 32, 39)),
    },
}
# Existing Desktop translations, not newly translated text. Their exact output
# is checked against DESKTOP_HASH, including the original bytes after each NUL.
SEED = {
    0x410780: r'<s0>%s%s:\\n%s%s{0CC0C0C0}' + '(\uc744)\ub97c \uc5bb\uc5c8\ub2e4!',
    0x4107C8: r'<s0>%s%s:\\n%s%s{0CC0C0C0} %d' + '\uac1c\ub97c \uc5bb\uc5c8\ub2e4!',
    0x4107F0: r'<s0>%s%s:\\n%s%dG' + '\ub97c \uc5bb\uc5c8\ub2e4!',
}
PRINTF = re.compile(rb'%(?:%|[-+ #0]*\d*(?:\.\d+)?[diuoxXfFeEgGcs])')
MARKUP = re.compile(rb'<[^<>]*>|\$[^;]*;|\\.')
BUTTONS = re.compile('[\u25cb\u25b3\u25a1\u00d7]')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def local(relative):
    path = HERE / relative
    require(path.resolve().is_relative_to(HERE), f'Path escapes tool directory: {relative}')
    require(not path.is_symlink(), f'Symbolic link not allowed: {relative}')
    return path


def editor_path(name):
    path = EDITOR / f'{name}.txt'
    require(EDITOR.resolve().is_relative_to(REPO.resolve()) and
            path.resolve().is_relative_to(EDITOR.resolve()), 'Editor escapes repository metadata')
    return path


def load_inputs():
    table_bytes = local('XENOSAGA KOR-JPN.json').read_bytes()
    require(sha(table_bytes) == TABLE_HASH, 'Font mapping changed; revalidate before building')
    table = json.loads(table_bytes.decode('utf-8-sig'))['replace-table']
    require(isinstance(table, dict) and all(isinstance(k, str) and len(k) == 1
            and isinstance(v, str) and len(v) == 1 for k, v in table.items()), 'Bad font mapping')
    originals = {}
    for name, spec in ASSETS.items():
        data = local('original/' + spec['source']).read_bytes()
        catalog(name, data)
        originals[name] = data
    seeded = build_blob('SLPS', originals['SLPS'], export_text('SLPS', originals['SLPS'], True), table)
    require(sha(seeded) == DESKTOP_HASH, 'Preserved Desktop translation mismatch')
    return originals, table


def encode_text(text, table):
    result, literal = bytearray(), []

    def flush():
        converted = ''.join(table.get(c, c) for c in literal)
        require(not re.search('[\u1100-\u11ff\u3130-\u318f\uac00-\ud7af]', converted),
                'Korean character missing from font mapping')
        result.extend(converted.encode('euc_jis_2004', errors='strict'))
        literal.clear()

    index = 0
    while index < len(text):
        char = text[index]
        if char == '{':
            end = text.find('}', index + 1)
            token = text[index + 1:end] if end >= 0 else ''
            require(bool(token) and len(token) % 2 == 0 and re.fullmatch('[0-9A-Fa-f]+', token),
                    'Malformed {HEX} token')
            flush()
            result.extend(bytes.fromhex(token))
            index = end + 1
        elif char == '\\':
            require(index + 1 < len(text) and text[index + 1] in ('n', '\\'),
                    r'Use \n for 0A or \\ for a literal backslash')
            flush()
            result.append(10 if text[index + 1] == 'n' else 92)
            index += 2
        else:
            require(char != '}' and ord(char) >= 32, 'Unexpected brace or literal control')
            literal.append(char)
            index += 1
    flush()
    raw = bytes(result)
    parsed, display, _ = read_string(raw + b'\0', 0, len(raw) + 1)
    require(parsed == raw, 'Embedded NUL or malformed control/character')
    return raw


def catalog(name, data):
    spec = ASSETS[name]
    require(sha(data) == spec['sha256'], f'{name}: expected immutable Japanese original')
    elf = Elf(data)
    result = {}
    for offset, length, capacity in spec['slots']:
        raw, text, controls = read_string(data, offset, offset + capacity + 1)
        require(len(raw) == length and not any(data[offset+length+1:offset+capacity+1]),
                f'{offset:08X}: literal slot layout changed')
        require(encode_text(text, {}) == raw, 'Non-roundtripping original')
        result[offset] = dict(length=length, capacity=capacity, raw=raw, text=text,
                              controls=controls, va=elf.va(offset))
    return result


def export_text(name, data, seeded=False):
    rows = catalog(name, data)
    lines = ['# XS3 ELF text v1', f'# asset: {name}', f'# origin-sha256: {ASSETS[name]["sha256"]}',
             '# offset|original bytes/capacity bytes|text',
             '# Edit only after the second |. Missing rows use Japanese original.',
             r'# \n = byte 0A; \\n = literal backslash+n; {HEX} = control packet.',
             '# Preserve controls, % formats, markup and button symbols.',
             '# Slots cannot relocate. Code, fonts and other strings remain unchanged.']
    for offset, row in rows.items():
        if offset == 0x3DDA8:
            lines.append('# COUNT: ASCII 0 must remain first; the game copies exactly 12 bytes.')
        if offset == 0x4107F0:
            lines.append('# Existing Desktop money text omits {0CC0C0C0}; both original/preserved controls are accepted.')
        text = SEED.get(offset, row['text']) if seeded and name == 'SLPS' else row['text']
        lines.append(f'{offset:08X}|{row["length"]}/{row["capacity"]}|{text}')
    return '\n'.join(lines) + '\n'


def parse_edits(name, text, rows):
    edits, headers, assets = {}, [], []
    for number, line in enumerate(text.lstrip('\ufeff').splitlines(), 1):
        if line.startswith('# origin-sha256: '):
            headers.append(line.removeprefix('# origin-sha256: '))
        if line.startswith('# asset: '):
            assets.append(line.removeprefix('# asset: '))
        if not line or line.startswith('#'):
            continue
        parts = line.split('|', 2)
        require(len(parts) == 3 and re.fullmatch('[0-9A-Fa-f]{8}', parts[0]),
                f'Line {number}: malformed record')
        offset = int(parts[0], 16)
        require(offset in rows and offset not in edits, f'Line {number}: unknown/duplicate offset')
        row = rows[offset]
        require(parts[1] == f'{row["length"]}/{row["capacity"]}', f'Line {number}: changed byte limit')
        edits[offset] = parts[2]
    require(headers == [ASSETS[name]['sha256']] and assets == [name], 'Wrong/missing/duplicate TXT header')
    return edits


def formats(raw):
    require(b'%' not in PRINTF.sub(b'', raw), 'Unrecognized % format')
    return PRINTF.findall(raw)


def validate_text(name, offset, row, raw):
    require(len(raw) <= row['capacity'], f'Length {len(raw)} exceeds capacity {row["capacity"]}')
    _, display, controls = read_string(raw + b'\0', 0, len(raw) + 1)
    original_controls = row['controls']
    # Preserve the already-approved money message, without silently restoring its color.
    accepted = [original_controls, []] if name == 'SLPS' and offset == 0x4107F0 else [original_controls]
    require(controls in accepted, 'Control packets/line breaks changed')
    require(formats(raw) == formats(row['raw']), '% placeholders/order changed')
    require(MARKUP.findall(raw) == MARKUP.findall(row['raw']), 'Text markup changed')
    require(BUTTONS.findall(display) == BUTTONS.findall(row['text']), 'Button symbols changed')
    if offset == 0x3DDA8:
        require(raw.startswith(b'0') and (len(raw) == 1 or raw[1:2] not in b'0123456789'),
                'COUNT must begin with one ASCII 0 at byte zero')


def verify_output(name, original, output, expected):
    rows = catalog(name, original)
    require(len(output) == len(original), 'Executable length changed')
    previous = 0
    for offset, row in sorted(rows.items()):
        require(output[previous:offset] == original[previous:offset], 'Bytes outside text slots changed')
        raw, _, _ = read_string(output, offset, offset + row['capacity'] + 1)
        require(raw == expected.get(offset, row['raw']), f'{offset:08X}: output text mismatch')
        validate_text(name, offset, row, raw)
        previous = offset + row['capacity'] + 1
        require(output[offset+len(raw)+1:previous] == original[offset+len(raw)+1:previous],
                'Unused literal tail changed')
    require(output[previous:] == original[previous:], 'Bytes outside text slots changed')


def build_blob(name, original, text, table):
    rows = catalog(name, original)
    edits = parse_edits(name, text, rows)
    result, expected = bytearray(original), {}
    for offset, text in edits.items():
        try:
            raw = encode_text(text, table)
            validate_text(name, offset, rows[offset], raw)
        except (ValueError, UnicodeError) as error:
            raise ValueError(f'{name} {offset:08X}: {error}') from error
        # Leave bytes after the new NUL alone: no-edit exports remain byte-exact,
        # including the shorter pre-existing Desktop translations.
        result[offset:offset+len(raw)+1] = raw + b'\0'
        expected[offset] = raw
    output = bytes(result)
    verify_output(name, original, output, expected)
    return output


def write_verified(path, data):
    pending = path.with_name(path.name + '.pending')
    require(not path.exists() or path.is_file(), f'Not a file: {path}')
    require(not pending.exists(), f'Unfinished output exists: {pending}; inspect before retrying')
    path.parent.mkdir(parents=True, exist_ok=True)
    with pending.open('xb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    require(pending.read_bytes() == data, f'Written output differs: {pending}')
    os.replace(pending, path)
    require(path.read_bytes() == data, f'Destination differs after replacement: {path}')


def publish(relative, data):
    write_verified(local(relative), data)


def deliver(outputs, originals, rom_root, input_hashes, check=False):
    root = Path(rom_root).resolve(strict=True)
    require(root.is_dir(), 'ROM workspace must be a directory')
    profile_path = root / 'iso-data/profile.json'
    require(profile_path.resolve().is_relative_to(root), 'Disc profile escapes ROM workspace')
    profile_bytes = profile_path.read_bytes()
    profiles = json.loads(profile_bytes.decode('utf-8-sig'))
    plans = []
    targets = ((1, 'SLPS', 'SLPS_256.40'), (1, 'OV04', 'OV04.OVL'),
               (2, 'SLPS', 'SLPS_256.41'), (2, 'OV04', 'OV04.OVL'))
    for disc, name, filename in targets:
        if filename + '.new' not in outputs:
            continue
        original = originals[name]
        metadata = profiles[str(disc)]['metadata'][filename]
        require(metadata['sha256'] == ASSETS[name]['sha256'] and metadata['size'] == len(original),
                f'Disc {disc} does not match the Japanese original: {filename}')
        target = root / f'disc{disc}metadata' / filename
        require(target.resolve().is_relative_to(root) and
                not target.resolve().is_relative_to(REPO.resolve()),
                f'Unsafe ROM destination: {target}')
        require(not target.parent.exists() or target.parent.is_dir(), 'Invalid metadata directory')
        require(not target.exists() or target.is_file(), f'Not a file: {target}')
        require(not target.with_name(target.name + '.pending').exists(),
                f'Unfinished output exists: {target}.pending; inspect before retrying')
        before = target.read_bytes() if target.exists() else None
        if before is not None:
            require(not any(target.samefile(p) for p in input_hashes),
                    f'Destination aliases an input: {target}')
            require(len(before) == len(original), f'Existing executable size changed: {target}')
            # Do not erase unrelated code/font/save-title patches in the ROM workspace.
            expected = {offset: read_string(before, offset, offset + capacity + 1)[0]
                        for offset, _, capacity in ASSETS[name]['slots']}
            try:
                verify_output(name, original, before, expected)
            except ValueError as exc:
                raise ValueError(f'Existing executable has incompatible changes; not overwritten: '
                                 f'{target}: {exc}') from exc
        plans.append((target, before, outputs[filename + '.new']))
    require(profile_path.read_bytes() == profile_bytes, 'Disc profile changed while validating')
    for path, expected in input_hashes.items():
        require(sha(path.read_bytes()) == expected, f'Input changed while validating: {path}')
    for target, before, _ in plans:
        require((target.read_bytes() if target.exists() else None) == before,
                f'Destination changed while validating: {target}')
    if check:
        for target, before, after in plans:
            print(f'[CHECK] {target} | ' + ('unchanged' if before == after else 'will copy'))
        print('[PASS] Build and delivery validated. Nothing written.')
        return
    for target, before, after in plans:
        if before == after:
            print(f'[KEEP] {target}')
            continue
        require((target.read_bytes() if target.exists() else None) == before,
                f'Destination changed before copying: {target}')
        write_verified(target, after)
        print(f'[COPIED] {target} | SHA256 {sha(after)}')
    print('[PASS] Both discs updated. ISO was not rebuilt.')


def run(command, asset=None, editors=(), rom_root=None):
    require(asset is None or asset in ASSETS, 'Unknown executable asset')
    require(command != 'export' or not editors, 'Export does not accept translation inputs')
    require(command != 'export' or rom_root is None, 'Export does not accept a ROM workspace')
    selected = {}
    input_hashes = {}
    for value in editors:
        path = Path(value).resolve(strict=True)
        require((path.is_relative_to(HERE) or path.is_relative_to(EDITOR.resolve())) and
                path.is_file() and path.suffix.lower() == '.txt',
                'Translation TXT must be inside discmetadata or tools/elf')
        raw = path.read_bytes()
        text = raw.decode('utf-8-sig')
        input_hashes[path] = sha(raw)
        names = [line.removeprefix('# asset: ') for line in text.lstrip('\ufeff').splitlines()
                 if line.startswith('# asset: ')]
        require(len(names) == 1 and names[0] in ASSETS, 'Wrong/missing/duplicate TXT asset header')
        name = names[0]
        require(asset is None or asset == name, 'Dropped TXT belongs to a different executable')
        require(name not in selected, f'Duplicate translation input: {name}')
        selected[name] = path, text
    names = tuple(name for name in ASSETS if (asset is None or name == asset)
                  and (not selected or name in selected))
    originals, table = load_inputs()
    input_hashes[local('XENOSAGA KOR-JPN.json')] = TABLE_HASH
    input_hashes.update({local('original/' + ASSETS[name]['source']): ASSETS[name]['sha256']
                         for name in ASSETS})
    if command == 'export':
        for name in names:
            data = originals[name]
            for path, seeded in ((local(f'reference/{name}.JP.txt'), False), (editor_path(name), True)):
                if path.exists():
                    print(f'[KEEP] {path}')
                    continue
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open('x', encoding='utf-8-sig', newline='\r\n') as stream:
                    stream.write(export_text(name, data, seeded))
                print(f'[EXPORT] {path}')
        return
    outputs = {}
    for name in names:
        if name in selected:
            path, text = selected[name]
        else:
            path = editor_path(name)
            raw = path.read_bytes()
            text = raw.decode('utf-8-sig')
            input_hashes[path] = sha(raw)
        output = build_blob(name, originals[name], text, table)
        print(f'Input: {path}')
        for filename in ASSETS[name]['outputs']:
            outputs[filename] = output
    if rom_root is not None:
        deliver(outputs, originals, rom_root, input_hashes, check=command == 'check')
        return
    if command == 'check':
        print('[PASS] All text validated. Nothing written.')
        return
    # Validate all translations and destinations before publishing any result.
    for filename in outputs:
        path = local('output/' + filename)
        require(not path.exists() or path.is_file(), 'Invalid output path')
        require(not local('output/' + filename + '.pending').exists(), 'Unfinished output exists')
    for filename, output in outputs.items():
        publish('output/' + filename, output)
        print(f'[PASS] {local("output/" + filename)} | SHA256 {sha(output)}')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('export', 'check', 'build'))
    parser.add_argument('--asset', choices=tuple(ASSETS), help='Build only the selected executable')
    parser.add_argument('--check', action='store_true', help='Validate a build without saving')
    parser.add_argument('--rom-root', type=Path, help='Deliver validated results to both discs; no local outputs')
    parser.add_argument('editors', nargs='*', help='Optional TXT files in discmetadata/tools/elf')
    args = parser.parse_intermixed_args(argv)
    try:
        require(not args.check or args.command != 'export', '--check cannot be combined with export')
        run('check' if args.check else args.command, args.asset, args.editors, args.rom_root)
    except (OSError, ValueError, KeyError) as error:
        print(f'[ERROR] {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
    raise SystemExit(main())
