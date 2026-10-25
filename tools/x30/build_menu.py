"""Build X30 menu text from repository inputs without accessing the ROM workspace."""

import argparse
import hashlib
import json
import sys
from pathlib import Path

from tools import njdatatexttool, njdbcommon_tool, njbtltext
from tools.txd_tool import TXDTool
from tools.output import validate_outputs, write_output


HOME = Path(__file__).resolve().parent
DATASET_NAMES = ('njDataText', 'MVtext', 'SegmentFileData')
TXD_NAMES = ('devchk', 'discchg', 'menutext', 'synopsis')
TXD_EDIT_FILES = ('devchk.txd_kor.txt', 'discchg.txd.kor.txt',
                  'menutext.txd_kor.txt', 'synopsis.txd_kor.txt')
MENU_EDIT_FILES = ('njDataText.KOR.txt', 'MVtext.KOR.txt', 'SegmentFileData.KOR.txt',
                   'njDBcommon.KOR.txt', 'njBtlText.KOR.txt', 'DBC.bin.KOR.txt') + TXD_EDIT_FILES
TITLE_EDIT_FILES = tuple('titleobj/' + name + '.png' for name in
                        ('new_game', 'continue', 'data', 'disc1', 'disc2'))
WINDOW_EDIT_FILES = tuple('window/' + name + '.png' for name in
                         ('enemy_info', 'boost', 'command', 'boost_red', 'stock',
                          'player', 'enemy', 'anima', 'act_large', 'act_small'))
SYNOPSIS_IMAGE_IDS = tuple(sorted((*range(10, 671, 10), 391, 641, 642, 643)))
DATABASE_IMAGE_IDS = (393, 400, *range(431, 454))
NATIVE_EDIT_FILES = ('../../0.X30/mnu/kr/title1.png', '../../0.X30/mnu/intm/10.jpg',
                     '../../0.X30/mnu/kr/wall.jpg') + tuple(
                         f'../../0.X30/mnu/syno/{index:03}.jpg' for index in SYNOPSIS_IMAGE_IDS) + tuple(
                         f'../../0.X30/jpg/kr/dtimg_{index:04}.jpg' for index in DATABASE_IMAGE_IDS)
PSE_EDIT_FILES = ('AC.mes.kor.txt', 'EP1.mes.txt', 'EP2.mes.txt', 'opening.mes.txt', 'PP.mes.txt', 'test.mes.txt')
PSE_LOGO_FILES = ('logo_ep1.png', 'logo_ep2.png', 'logo_pp.png')
GRAPHICS_SOURCE_FILES = {
    '0.X30/mnu/kr/titleobj': ('titleobj.xtx',),
    '0.X30/mnu/kr/window': ('window0.xtx', 'window1.xtx', 'window2.xtx'),
    '0.X30/mnu/pse/kr': tuple(Path(name).with_suffix('.tm2').name for name in PSE_LOGO_FILES),
    '0.X30/mnu/kr/fonts': ('font0.bin', 'font1.bin') + tuple(
        f'font{index}_{channel}.png' for index in (0, 1) for channel in ('red', 'green', 'blue', 'alpha')),
}
NAMES = DATASET_NAMES + ('njDBcommon', 'njBtlText') + TXD_NAMES
TEXT_SOURCE_FILES = {
    '0.X30/mnu/kr': ('njDataText.bin', 'MVtext.bin', 'SegmentFileData.bin',
                    'njDBcommon.bin', 'njBtlText.JPN.bin', 'DBC.bin', 'DBC2.bin',
                    'devchk.txd', 'discchg.txd', 'menutext.JPN.txd', 'synopsis.txd'),
    '0.X30/mg1/kr': ('Message.Dat', 'World.Dat'),
    '0.X30/mnu/pse/kr': tuple(name+'.mes' for name in ('AC', 'EP1', 'EP2', 'opening', 'PP', 'test')),
}


def local_path(relative):
    path = HOME / relative
    if not path.resolve().is_relative_to(HOME):
        raise ValueError(f'Path must stay inside the X30 kit: {relative}')
    return path


def input_path(relative):
    path = (HOME / relative).resolve()
    if path.is_relative_to(HOME):
        return path
    for folder, names in GRAPHICS_SOURCE_FILES.items():
        if path.parent == HOME.parents[1] / folder and path.name in names:
            return path
    for folder, names in TEXT_SOURCE_FILES.items():
        if path.parent == HOME.parents[1] / folder and path.name in (*names, 'XENOSAGA KOR-JPN.json'):
            return path
    if (path.suffix.lower() in ('.txt', '.sb') or path.name == 'XENOSAGA KOR-JPN.json') and path.parent in (
            HOME.parents[1] / '0.X30/cf/kr', HOME.parents[1] / '0.X30/bat/kr'):
        return path
    if path.is_relative_to(HOME.parents[1] / '0.X30/ef'):
        from build_effects import manifest
        relative = path.relative_to(HOME.parents[1]).as_posix()
        if relative in {row[key] for row in manifest()['assets'] for key in ('source', 'editor')}:
            return path
    # Only declared canonical editors may be read outside the tool directory.
    editors = {HOME.parents[1] / '0.X30/mnu/kr' / name for name in MENU_EDIT_FILES + TITLE_EDIT_FILES + WINDOW_EDIT_FILES}
    editors.add(HOME.parents[1] / '0.X30/mg1/kr/Message.Dat.txt')
    editors.add(HOME.parents[1] / '0.X30/mg1/kr/World.Dat.txt')
    editors.update(HOME.parents[1] / '0.X30/mnu/pse/kr' / name for name in PSE_EDIT_FILES + PSE_LOGO_FILES)
    native_editors = {HOME.parents[1] / name.removeprefix('../../') for name in NATIVE_EDIT_FILES}
    editors.update(native_editors)
    editors.update(path.parent / 'original' / path.name for path in native_editors)
    editors.add(HOME.parents[1] / '0.X30/bat/kr/batdatEdit/batdat.json')
    editors.update(HOME.parents[1] / '0.X30/bat/kr/batdatEdit' / name for name in
                   ('batdat.bin', 'XENOSAGA KOR-JPN.json'))
    if path not in editors:
        raise ValueError(f'Input must stay in the X30 kit or use a canonical menu editor: {relative}')
    return path


def explicit_editor(value):
    path = Path(value).resolve(strict=True)
    root = HOME.parents[1]
    if not path.is_file() or not any(path.is_relative_to(base) for base in (root / '0.X30', HOME)):
        raise ValueError('Dropped editors must be files inside this repository: 0.X30 or tools/x30')
    if path.suffix.lower() != '.txt':
        raise ValueError('Expected a UTF-8 translation TXT, not a game binary')
    return path


def read_verified(path, expected):
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != expected:
        raise ValueError(f'Source hash mismatch: {path.name}')
    return data


def prepare(names, editor=None, extract=False):
    names = tuple(names)
    if not names or len(set(names)) != len(names) or any(name not in NAMES for name in names):
        raise ValueError('Select each known menu asset at most once')
    if extract and editor is not None:
        raise ValueError('Extraction reads registered originals, not a dropped TXT')
    if editor is not None and len(names) != 1:
        raise ValueError('A dropped editor must select exactly one menu asset')
    manifest = json.loads(local_path('sources.json').read_text(encoding='utf-8'))
    table_path = input_path(manifest['charmap'])
    table_bytes = read_verified(table_path, manifest['charmap_sha256'])
    charmap = json.loads(table_bytes.decode('utf-8-sig'))['replace-table']
    if not charmap or any(len(k) != 1 or not isinstance(v, str) or not v for k, v in charmap.items()):
        raise ValueError('Expected a nonempty single-character substitution table')
    results = []
    for name in names:
        asset = manifest['assets'][name]
        original_path, editor_path = input_path(asset['original']), input_path(asset['edit'])
        if editor is not None:
            editor_path = explicit_editor(editor)
        original = read_verified(original_path, asset['original_sha256'])
        try:
            if name in DATASET_NAMES:
                format_tool = njdatatexttool
            elif name == 'njDBcommon':
                format_tool = njdbcommon_tool
            elif name == 'njBtlText':
                format_tool = njbtltext
            else:
                format_tool = TXDTool()
            content = format_tool.extract_text(original) if extract else editor_path.read_text(encoding='utf-8-sig')
            result = format_tool.rebuild(original, content, charmap)
            if extract and result != original:
                raise ValueError('Original extraction did not roundtrip byte-for-byte')
            # SLPS 001b3df8 places diskchg.bin at text-buffer + 0x400.
            if name == 'discchg' and len(result) > 0x400:
                raise ValueError(f'TXD exceeds the 1024-byte disc-change text buffer: {len(result)} bytes')
            # SLPS ov01: menutext at 0x3c2040, followed by umn.bin at 0x3c6040.
            if name == 'menutext' and len(result) > 0x4000:
                raise ValueError(f'TXD exceeds the 16384-byte resident menu text buffer: {len(result)} bytes')
        except (ValueError, UnicodeError) as exc:
            raise ValueError(f'{name}: {exc}') from exc
        if extract:
            results.append((name, editor_path, content.encode('utf-8'), (original_path, table_path)))
        else:
            output = original_path.with_name(original_path.name+'.new')
            results.append((name, output, result, (original_path, editor_path, table_path)))
    return results


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--asset', choices=NAMES)
    parser.add_argument('editor', nargs='?', help='Optional translation TXT in this repository; never modified')
    parser.add_argument('--check', action='store_true', help='Validate and rebuild in memory without saving')
    parser.add_argument('--extract', action='store_true', help='Extract Japanese originals to canonical TXT; never overwrite')
    args = parser.parse_args(argv)
    try:
        asset = args.asset
        if args.editor and asset is None:
            manifest = json.loads(local_path('sources.json').read_text(encoding='utf-8'))
            matches = [name for name in NAMES
                       if Path(manifest['assets'][name]['edit']).name.lower() == Path(args.editor).name.lower()]
            if len(matches) != 1:
                raise ValueError('Cannot select menu format from filename; use the matching per-file BAT or --asset')
            asset = matches[0]
        names = (asset,) if asset else NAMES
        results = prepare(names, args.editor, extract=args.extract)
        # Validate every selected asset before publishing the first result.
        protected = tuple(path for item in results for path in item[3])
        if not args.check:
            validate_outputs((item[1] for item in results), protected, overwrite=not args.extract)
            for name, output, result, inputs in results:
                write_output(output, result, inputs, overwrite=not args.extract)
        for name, output, result, protected_paths in results:
            print(f'Input: {protected_paths[0 if args.extract else 1]}')
            print(f'Output: {output}')
            print(f'{name}: {len(result)} bytes, sha256={hashlib.sha256(result).hexdigest()}')
        print('CHECK PASSED (no files written)' if args.check else 'BUILD SUCCEEDED')
        return 0
    except (OSError, ValueError, KeyError) as exc:
        print(f'BUILD FAILED: {exc}', file=sys.stderr)
        print('Do not apply outputs from a failed run. Previous outputs may still exist.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
