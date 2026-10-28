"""X30 SB string tables, retaining the existing address-tagged TXT format."""

import re
import struct


ENCODING = 'euc_jis_2004'
TAG = re.compile(r'\[(0x[0-9a-fA-F]+)\]')
BILINGUAL_HEADER = '# SB-TEXT: JPN-KOR v1'
INTERNAL_FIRST = {b'seg_now', b'--- main ---'}


def read_rows(data):
    """Read a canonical original, not a previously extended build output."""
    data = bytes(data)
    if len(data) < 64 or data[:8] != b'SB  \x01\0\x01\0':
        raise ValueError('Invalid SB signature/version')
    sections = struct.unpack_from('<6I', data, 8)
    if (sections[0] != 64 or list(sections) != sorted(set(sections)) or
            sections[-1] >= len(data) or any(value % 4 for value in sections)):
        raise ValueError('Invalid SB section boundaries')
    start, end = sections[2:4]
    if start + 8 > end:
        raise ValueError('Truncated SB string section')
    header, count = struct.unpack_from('<2I', data, start)
    if header != 8 or count > (end - start - header) // 4:
        raise ValueError('Invalid SB string table size')
    table = start + header
    base = table + count * 4
    offsets = struct.unpack_from(f'<{count}I', data, table)
    if offsets and (offsets[0] != 0 or list(offsets) != sorted(set(offsets))):
        raise ValueError('Expected the original contiguous SB string pool')
    rows = []
    previous_end = base
    for index, offset in enumerate(offsets):
        address = base + offset
        if address != previous_end or not base <= address < end:
            raise ValueError(f'Invalid SB string pointer at slot {index}')
        stop = data.find(b'\0', address, end)
        if stop < 0:
            raise ValueError(f'Unterminated SB string at {address:#x}')
        raw = data[address:stop]
        text = raw.decode(ENCODING)
        if '\r' in text or '[n]' in text:
            raise ValueError(f'SB text cannot be represented losslessly at {address:#x}')
        rows.append({'address': address, 'ptr_pos': table + index * 4, 'base': base,
                     'raw': raw, 'text': text,
                     'editable': index != 0 or raw not in INTERNAL_FIRST})
        previous_end = stop + 1
    if end - previous_end > 3 or any(data[previous_end:end]):
        raise ValueError('Unexpected data after the SB string pool')
    return rows


def render_bilingual(rows, translations=None):
    translations = {} if translations is None else translations
    blocks = []
    for row in rows:
        if not row['editable']:
            continue
        address = row['address']
        original = row['text'].replace('\n', '[n]')
        translated = translations.get(address, '').replace('\n', '[n]')
        blocks.append(f'[{address:#x}]\n[JPN]\n{original}\n[KOR]\n{translated}\n')
    return BILINGUAL_HEADER + '\n\n' + '\n'.join(blocks) if blocks else ''


def extract_text(data, bilingual=True):
    rows = read_rows(data)
    if bilingual:
        return render_bilingual(rows)
    return ''.join(f"[{row['address']:#x}]\n" + row['text'].replace('\n', '[n]') + '\n\n'
                   for row in rows if row['editable'])


def normalized_lines(content):
    content = content.removeprefix('\ufeff').replace('\r\n', '\n')
    if '\r' in content or '\0' in content:
        raise ValueError('Bare CR or NUL is not allowed in SB TXT')
    return content.split('\n')


def parse_text(content):
    # One physical body line; [n] represents physical LF inside a game string.
    # Blank separator lines are formatting, while spaces on the body are data.
    lines = normalized_lines(content)
    entries = {}
    index = 0
    while index < len(lines):
        if lines[index] == '':
            index += 1
            continue
        match = TAG.fullmatch(lines[index])
        if not match:
            raise ValueError(f'Expected an SB address tag at line {index + 1}')
        address = int(match[1], 16)
        if address in entries:
            raise ValueError(f'Duplicate SB address {address:#x} at line {index + 1}')
        if index + 1 >= len(lines) or TAG.fullmatch(lines[index + 1]):
            raise ValueError(f'Missing SB text line after {address:#x}')
        entries[address] = lines[index + 1].replace('[n]', '\n')
        index += 2
    return entries


def is_bilingual(content):
    return any(line in (BILINGUAL_HEADER, '[JPN]', '[KOR]') or
               line.startswith('# SB-TEXT:') for line in content.splitlines())


def parse_bilingual(content):
    """Parse JPN/KOR fields while retaining the existing one-line/[n] rule."""
    lines = normalized_lines(content)
    if not lines or lines[0] != BILINGUAL_HEADER:
        raise ValueError('JPN/KOR TXT header is missing or unsupported')
    originals, translations = {}, {}
    index = 1
    while index < len(lines):
        while index < len(lines) and lines[index] == '':
            index += 1
        if index == len(lines):
            break
        match = TAG.fullmatch(lines[index])
        if not match:
            raise ValueError(f'Expected an SB address tag at line {index + 1}')
        address = int(match[1], 16)
        if address in originals:
            raise ValueError(f'Duplicate SB address {address:#x} at line {index + 1}')
        index += 1
        if index >= len(lines) or lines[index] != '[JPN]':
            raise ValueError(f'Missing [JPN] after {address:#x}')
        index += 1
        if index >= len(lines):
            raise ValueError(f'Missing JPN text line after {address:#x}')
        originals[address] = lines[index]
        index += 1
        if index < len(lines) and lines[index] == '[KOR]':
            index += 1
            if index >= len(lines):
                raise ValueError(f'Missing KOR text line after {address:#x}')
            value = lines[index]
            if value.strip():
                translations[address] = value
            index += 1
        if index < len(lines) and lines[index] != '':
            raise ValueError(f'Unexpected content after {address:#x} at line {index + 1}; '
                             'use [n] for LF')
    return originals, translations


def editor_entries(data, content):
    rows = read_rows(data)
    expected = {row['address']: row for row in rows if row['editable']}
    if is_bilingual(content):
        originals, translations = parse_bilingual(content)
        if set(originals) != set(expected):
            missing = sorted(set(expected) - set(originals))
            extra = sorted(set(originals) - set(expected))
            raise ValueError(f'SB address set mismatch: missing={[hex(v) for v in missing[:8]]}, '
                             f'unknown={[hex(v) for v in extra[:8]]}')
        for address, value in originals.items():
            if value.replace('[n]', '\n') != expected[address]['text']:
                raise ValueError(f'SB {address:#x}: JPN differs from the original')
        return {address: translations.get(address, row['text'].replace('\n', '[n]')).replace('[n]', '\n')
                for address, row in expected.items()}
    return parse_text(content)


def rebuild(data, content, charmap):
    data = bytes(data)
    rows = read_rows(data)
    entries = editor_entries(data, content)
    expected = {row['address'] for row in rows if row['editable']}
    if set(entries) != expected:
        missing, extra = sorted(expected - entries.keys()), sorted(entries.keys() - expected)
        raise ValueError(f'SB address set mismatch: missing={[hex(v) for v in missing[:8]]}, '
                         f'unknown={[hex(v) for v in extra[:8]]}')
    encoded = {}
    for row in rows:
        address = row['address']
        if not row['editable'] or entries[address] == row['text']:
            encoded[address] = row['raw']
            continue
        text = ''.join(charmap.get(char, char) for char in entries[address])
        try:
            raw = text.encode(ENCODING)
        except UnicodeEncodeError as exc:
            bad = ascii(exc.object[exc.start:exc.end])
            raise ValueError(f'SB {address:#x}: cannot encode {bad} as {ENCODING}') from exc
        if b'\0' in raw:
            raise ValueError(f'NUL is not allowed in SB text at {address:#x}')
        encoded[address] = raw
    result = bytearray(data)
    for row in rows:
        address, raw = row['address'], encoded[row['address']]
        if raw == row['raw']:
            continue
        if len(raw) <= len(row['raw']):
            result[address:address + len(row['raw'])] = raw.ljust(len(row['raw']), b'\0')
        else:
            new_address = len(result)
            relative = new_address - row['base']
            if relative > 0xffffffff:
                raise ValueError('SB string pointer exceeds uint32')
            result.extend(raw + b'\0')
            struct.pack_into('<I', result, row['ptr_pos'], relative)
    # Header, bytecode and non-string sections are never scanned for pointer-like values.
    for row in rows:
        address = row['base'] + struct.unpack_from('<I', result, row['ptr_pos'])[0]
        stop = result.find(b'\0', address)
        if stop < 0 or result[address:stop] != encoded[row['address']]:
            raise ValueError(f'SB rebuilt string verification failed at {row["address"]:#x}')
    return bytes(result)
