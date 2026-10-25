"""DBF records in the Japanese X30 DBC/DBC2 dataset containers."""

import collections
import re
import struct

from .njdatatexttool import get_datasets


STRIDE = 208
TEXT_FIELDS = (12, 20, 36, 40, 44, 48, 52, 56)
ENCODING = 'euc_jis_2004'


def read_rows(data):
    data = bytes(data)
    rows = []
    identities = set()
    for ds in get_datasets(data):
        base, size = ds['offset'], ds['size']
        if size < 200 or data[base:base+4] != b'DBF\0':
            raise ValueError(f"Invalid DBF dataset: {ds['index']}")
        first = struct.unpack_from('<I', data, base+12)[0]
        count, tail = divmod(first+8, STRIDE)
        if tail or count < 1 or first >= size:
            raise ValueError('DBF record boundary does not match the source layout')
        for entry in range(count):
            pos = base + entry*STRIDE
            if data[pos:pos+4] != b'DBF\0':
                raise ValueError(f'Missing DBF tag: {pos:#x}')
            entry_id = struct.unpack_from('<I', data, pos+4)[0]
            if entry_id in identities:
                raise ValueError(f'Duplicate DBF entry ID: {entry_id}')
            identities.add(entry_id)
            for field in TEXT_FIELDS:
                ptr_pos = pos+field
                target = base + struct.unpack_from('<I', data, ptr_pos)[0]
                if not base+first <= target < base+size:
                    raise ValueError(f'DBF pointer outside source pool: {ptr_pos:#x}')
                end = data.find(b'\0', target, base+size)
                if end < 0:
                    raise ValueError(f'Unterminated DBF string: {target:#x}')
                raw = data[target:end]
                text = raw.decode(ENCODING)
                if '\n' in text or '\r' in text:
                    raise ValueError('Physical line breaks require a distinct editor escape convention')
                rows.append({'id': entry_id, 'field': field, 'ptr_pos': ptr_pos, 'ds_off': base,
                             'address': target, 'raw': raw, 'text': text})
    return rows


def extract_text(data):
    return ''.join(f"{row['address']:#x}|{row['text']}\n" for row in read_rows(data))


def parse_text(content, rows):
    counts = collections.Counter()
    texts = {}
    first_lines = {}
    expected_counts = collections.Counter(row['address'] for row in rows)
    for number, line in enumerate(content.removeprefix('\ufeff').split('\n'), 1):
        line = line.removesuffix('\r')
        if not line:
            continue
        match = re.fullmatch(r'(0x[0-9a-fA-F]+)\|([^\r\n]*)', line)
        if not match:
            raise ValueError(f'Invalid database TXT line: {number}')
        address, text = int(match[1], 16), match[2]
        if address not in expected_counts:
            raise ValueError(f'Unknown database address on line {number}: {address:#x}')
        if address in texts and texts[address] != text:
            raise ValueError(f'Conflicting translations at {address:#x}, lines {first_lines[address]} and {number}')
        texts[address] = text
        first_lines.setdefault(address, number)
        counts[address] += 1
    if counts != expected_counts:
        raise ValueError('Database TXT has missing or extra address occurrences')
    return texts


def encode_rows(rows, texts, charmap):
    expected = []
    for row in rows:
        text = texts[row['address']]
        if text == row['text']:
            expected.append(row['raw'])
            continue
        value = ''.join(charmap.get(char, char) for char in text)
        if '\0' in value:
            raise ValueError(f"Embedded NUL at {row['address']:#x}")
        expected.append(value.encode(ENCODING))
    return expected


def patch_rows(data, rows, expected):
    if len(rows) != len(expected):
        raise ValueError('DBF field count mismatch')
    slots = {}
    for row, raw in zip(rows, expected):
        slot = slots.setdefault(row['address'], {'raw': row['raw'], 'rows': []})
        if row['raw'] != slot['raw'] or b'\0' in raw:
            raise ValueError('Invalid shared DBF string')
        slot['rows'].append((row, raw))
    ordered = sorted(slots)
    for left, right in zip(ordered, ordered[1:]):
        if left + len(slots[left]['raw']) + 1 > right:
            raise ValueError('Overlapping DBF strings need explicit handling')

    result = bytearray(data)
    for address, slot in slots.items():
        original = slot['raw']
        variants = set(raw for _, raw in slot['rows'])
        if variants == {original}:
            continue
        if len(variants) == 1 and len(next(iter(variants))) <= len(original):
            raw = next(iter(variants))
            result[address:address+len(original)+1] = raw + b'\0' * (len(original)+1-len(raw))
            continue
        targets = {original: address}
        for row, raw in slot['rows']:
            if raw not in targets:
                targets[raw] = len(result)
                result.extend(raw + b'\0')
            struct.pack_into('<I', result, row['ptr_pos'], targets[raw]-row['ds_off'])
        if original not in variants:
            result[address:address+len(original)+1] = b'\0' * (len(original)+1)

    for row, raw in zip(rows, expected):
        target = row['ds_off'] + struct.unpack_from('<I', result, row['ptr_pos'])[0]
        if result[target:target+len(raw)+1] != raw + b'\0':
            raise ValueError(f"DBF pointer verification failed: {row['ptr_pos']:#x}")
    return bytes(result)


def rebuild(data, content, charmap):
    rows = read_rows(data)
    expected = encode_rows(rows, parse_text(content, rows), charmap)
    return patch_rows(data, rows, expected)


def rebuild_pair(primary, secondary, content, charmap):
    primary_rows, secondary_rows = read_rows(primary), read_rows(secondary)
    encoded = encode_rows(primary_rows, parse_text(content, primary_rows), charmap)
    keyed = {(row['id'], row['field']): (row, raw) for row, raw in zip(primary_rows, encoded)}
    if set(keyed) != {(row['id'], row['field']) for row in secondary_rows}:
        raise ValueError('DBC and DBC2 entry identities differ')
    secondary_expected = []
    kept_categories = 0
    for row in secondary_rows:
        original, translated = keyed[row['id'], row['field']]
        if row['raw'] == original['raw']:
            secondary_expected.append(translated)
        elif row['field'] == 12:
            # DBC uses category labels; DBC2 uses Japanese reading groups here.
            secondary_expected.append(row['raw'])
            kept_categories += 1
        else:
            raise ValueError(f"DBC/DBC2 source mismatch: entry {row['id']}, field {row['field']}")
    return (patch_rows(primary, primary_rows, encoded),
            patch_rows(secondary, secondary_rows, secondary_expected),
            {'primary_fields': len(primary_rows), 'secondary_fields': len(secondary_rows),
             'secondary_reading_groups_preserved': kept_categories})
