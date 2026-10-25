"""UTF-8 subtitle editors -> font substitution -> EUC-JIS-2004 delivery."""

import argparse
import json
import os
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
ENCODING = 'euc_jis_2004'
TABLE = Path('0.X30/cf/kr/XENOSAGA KOR-JPN.json')
# Japanese disc TOC membership.
SCRIPTS = {
    1: {
        'evt': '''s000100 s000500 s000700 s010100 s010200 s021200 s021500
                  s022300 s025100 s025300 s025800 s030600 s030700 s031200
                  s040110 s041710 s060100 s060720 s061420 s061600 s061700
                  s061900 s070500 s070710 s071400 s071500 s071610 s071620
                  s071800 s072000 s072100 s072600 s072800 s073100 s073500''',
        'mov': '''s000300 s000600 s010300 s030100 s031300 s060300 s060400
                  s060700 s061400 s072900 s073120 s073300 s073600''',
    },
    2: {
        'evt': '''s080600 s080820 s081100 s081500 s081800 s083000 s090900
                  s091100 s091500 s091600 s091800 s092100 s092300 s092600
                  s092900 s093000 s093910 s094010''',
        'mov': '''s080030 s081600 s083110 s083200 s083410 s093500 s093600
                  s094110 s094210 s094600 s094820 s095200 s100010 s100120
                  s100900''',
    },
}


def game_paths(disc):
    return [Path(kind, 'jp', name + '.txt')
            for kind, names in SCRIPTS[disc].items() for name in names.split()]


def inside(root, path):
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError(f'Path escapes its workspace: {path}')
    return path


def hangul(char):
    code = ord(char)
    return (0x1100 <= code <= 0x11FF or 0x3130 <= code <= 0x318F or
            0xA960 <= code <= 0xA97F or 0xAC00 <= code <= 0xD7FF)


def load_table(path):
    table = json.loads(path.read_bytes().decode('utf-8-sig'))['replace-table']
    if not isinstance(table, dict) or not table or not all(
        len(key) == 1 and hangul(key) and isinstance(value, str) and
        len(value) == 1 and not hangul(value) and ord(value) >= 128
        for key, value in table.items()
    ):
        raise ValueError(f'Expected single Hangul -> game character mappings: {path}')
    for value in table.values():
        if value.encode(ENCODING).decode(ENCODING) != value:
            raise ValueError(f'Non-roundtripping font mapping: {value!r}')
    return table


def decode_game(data):
    text = data.decode(ENCODING)
    if '\0' in text or text.encode(ENCODING) != data:
        raise ValueError('Game text must roundtrip without NUL bytes')
    return text.encode('utf-8')


def encode_editor(data, table):
    text = data.decode('utf-8-sig')
    if '\0' in text:
        raise ValueError('NUL is not allowed; save the editor as UTF-8, not UTF-16')
    # Only Hangul changes. Timing, markup, comments, punctuation and CR/LF stay intact.
    converted = ''.join(table.get(char, char) for char in text)
    for index, char in enumerate(converted):
        if hangul(char):
            line = converted.count('\n', 0, index) + 1
            raise ValueError(f'Line {line}: Hangul missing from font mapping: {char!r}')
    try:
        result = converted.encode(ENCODING)
    except UnicodeEncodeError as exc:
        line = converted.count('\n', 0, exc.start) + 1
        raise ValueError(f'Line {line}: cannot encode {converted[exc.start:exc.end]!r} '
                         f'as {ENCODING}') from exc
    if result.decode(ENCODING) != converted:
        raise ValueError('Encoded text does not roundtrip exactly')
    return result


def editor_paths(root, disc):
    folder = root / f'{disc}.X3{disc}'
    paths = {game: inside(root, folder / game.parts[0] / 'kr' / game.name)
             for game in game_paths(disc)}
    found = {path for kind in ('evt', 'mov') for path in (folder / kind / 'kr').glob('*.txt')}
    unexpected = found - set(paths.values())
    if unexpected:
        raise ValueError('Unregistered editor TXT: ' + ', '.join(str(p) for p in sorted(unexpected)))
    return paths


def publish(changes, check):
    # Validate the whole batch before touching any destination.
    for path, before, after in changes:
        current = path.read_bytes() if path.exists() else None
        if current != before:
            raise ValueError(f'File changed during validation; retry: {path}')
        if path.with_name(path.name + '.pending').exists():
            raise FileExistsError(f'Inspect interrupted output first: {path}.pending')
    if check:
        return
    for path, before, after in changes:
        path.parent.mkdir(parents=True, exist_ok=True)
        pending = path.with_name(path.name + '.pending')
        with pending.open('xb') as stream:
            stream.write(after)
            stream.flush()
            os.fsync(stream.fileno())
        if pending.read_bytes() != after:
            raise OSError(f'Written data mismatch: {pending}')
        os.replace(pending, path)
        if path.read_bytes() != after:
            raise OSError(f'Destination verification failed: {path}')


def decode_batch(root, disc, check=False):
    paths = editor_paths(root, disc)
    changes = []
    decoded = created = kept = 0
    for game, editor in paths.items():
        source = inside(root, root / f'{disc}.X3{disc}' / game)
        raw = source.read_bytes()
        try:
            original = raw.decode('utf-8-sig')
        except UnicodeDecodeError:
            try:
                original_utf8 = decode_game(raw)
            except (UnicodeError, ValueError) as exc:
                raise ValueError(f'{source}: {exc}') from exc
            changes.append((source, raw, original_utf8))
            decoded += 1
        else:
            if '\0' in original:
                raise ValueError(f'NUL in original: {source}')
            original_utf8 = raw
        before = editor.read_bytes() if editor.exists() else None
        if before is not None:
            try:
                text = before.decode('utf-8-sig')
            except UnicodeDecodeError as exc:
                raise ValueError(f'Existing editor must be UTF-8; not overwritten: {editor}') from exc
            if '\0' in text:
                raise ValueError(f'NUL in editor: {editor}')
            kept += 1
        else:
            changes.append((editor, None, original_utf8))
            created += 1
    publish(changes, check)
    return {'total': len(paths), 'originals_decoded': decoded,
            'editors_created': created, 'kept_utf8': kept}


def encode_batch(root, disc, rom_root, check=False):
    table_path = inside(root, root / TABLE)
    table = load_table(table_path)
    paths = editor_paths(root, disc)
    index = inside(rom_root, rom_root / 'iso-data' / f'LBA{disc}.txt')
    registered = {line.split('|')[-1].strip().replace('\\', '/').lstrip('/')
                  for line in index.read_text(encoding='utf-8-sig').splitlines()}
    unpacked = inside(rom_root, rom_root / f'X3{disc}_UNPACKED')
    protected = [table_path, *paths.values()]
    changes = []
    total_bytes = 0
    for game, editor in paths.items():
        if game.as_posix() not in registered:
            raise ValueError(f'Subtitle is not registered in disc {disc}: {game}')
        target = inside(unpacked, unpacked / game)
        if not target.is_file():
            raise FileNotFoundError(f'Expected existing ROM subtitle: {target}')
        if any(target.resolve() == p.resolve() or (p.exists() and target.samefile(p))
               for p in protected):
            raise ValueError(f'ROM target aliases a repository input: {target}')
        try:
            after = encode_editor(editor.read_bytes(), table)
        except (UnicodeError, ValueError) as exc:
            raise ValueError(f'{editor}: {exc}') from exc
        before = target.read_bytes()
        if before != after:
            changes.append((target, before, after))
        total_bytes += len(after)
    publish(changes, check)
    return {'total': len(paths), 'changed': len(changes), 'unchanged': len(paths) - len(changes),
            'encoded_bytes': total_bytes}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('decode', 'encode'))
    parser.add_argument('--disc', required=True, type=int, choices=(1, 2))
    parser.add_argument('--rom-root', type=Path)
    parser.add_argument('--check', action='store_true', help='Validate only; write nothing')
    args = parser.parse_args(argv)
    if args.action == 'encode' and args.rom_root is None:
        parser.error('encode requires --rom-root')
    try:
        if args.action == 'decode':
            stats = decode_batch(ROOT, args.disc, args.check)
        else:
            stats = encode_batch(ROOT, args.disc, args.rom_root, args.check)
        print(('CHECK SUCCEEDED' if args.check else args.action.upper() + ' SUCCEEDED'), stats)
        if args.action == 'encode':
            print(f'Destination: {args.rom_root / ("X3" + str(args.disc) + "_UNPACKED")}')
            print('ISO was not rebuilt. Use the ROM workspace RebuildDisc BAT when ready.')
        return 0
    except (OSError, ValueError, KeyError) as exc:
        print(f'FAILED: {exc}', file=sys.stderr)
        print('No ISO was built. If writing was interrupted, inspect .pending files and rerun.',
              file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
