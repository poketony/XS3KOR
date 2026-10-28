"""Encode X30 battle subtitle editors to adjacent .txt.new files."""

import argparse
from pathlib import Path
import sys

import subtitles as sub


FOLDER = Path('0.X30/mov/kr/bat')
MAX_BYTES = 1024  # The scripts' original header specifies a 1 KiB limit.


def encode_batch(root, editors=(), check=False):
    folder = sub.inside(root, root / FOLDER).resolve(strict=True)
    selected = editors if editors else sorted(folder.glob('*.txt'))
    paths = [Path(value).resolve(strict=True) for value in selected]
    if not paths:
        raise ValueError(f'No subtitle TXT files: {folder}')
    if len(paths) != len(set(paths)):
        raise ValueError('Drop each subtitle TXT only once')
    for path in paths:
        if path.parent != folder or path.suffix.lower() != '.txt' or not path.is_file():
            raise ValueError(f'Expected a TXT directly inside {folder}: {path}')
    table_path = sub.inside(root, root / sub.TABLE)
    table = sub.load_table(table_path)
    protected = [table_path, *paths]
    changes = []
    total_bytes = 0
    for path in paths:
        try:
            after = sub.encode_editor(path.read_bytes(), table)
            if len(after) > MAX_BYTES:
                raise ValueError(f'Encoded script exceeds {MAX_BYTES} bytes: {len(after)}')
        except (UnicodeError, ValueError) as exc:
            raise ValueError(f'{path}: {exc}') from exc
        output = sub.inside(folder, path.with_name(path.name + '.new'))
        if any(output.resolve() == p.resolve() or
               (output.exists() and output.samefile(p)) for p in protected):
            raise ValueError(f'Output aliases a subtitle input: {output}')
        if output.with_name(output.name + '.pending').exists():
            raise FileExistsError(f'Inspect interrupted output first: {output}.pending')
        before = output.read_bytes() if output.exists() else None
        if before != after:
            changes.append((output, before, after))
        total_bytes += len(after)
    sub.publish(changes, check)
    return {'total': len(paths), 'changed': len(changes), 'unchanged': len(paths)-len(changes),
            'encoded_bytes': total_bytes}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('editors', nargs='*', help='Optional TXT drops; no arguments encodes all')
    parser.add_argument('--check', action='store_true', help='Validate only; write nothing')
    args = parser.parse_args(argv)
    try:
        stats = encode_batch(sub.ROOT, args.editors, args.check)
        print('CHECK SUCCEEDED' if args.check else 'BUILD SUCCEEDED', stats)
        print(f'Output: {sub.ROOT / FOLDER / "*.txt.new"}')
        return 0
    except (OSError, ValueError, KeyError) as exc:
        print(f'FAILED: {exc}', file=sys.stderr)
        print('Do not apply results of a failed run. Inspect any .pending files before retrying.',
              file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
