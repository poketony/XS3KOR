"""Message.Dat: 1024 signed nonnegative offsets and a NUL-terminated pool."""

import struct

from . import njdbcommon_tool as common


SLOT_COUNT = 1024
POOL_BASE = SLOT_COUNT * 2
MAX_POOL_SIZE = 0x10000
MAX_OFFSET = 0x7fff
STAGE_NAME_IDS = range(99, 199)
MAX_STAGE_NAME_BYTES = 26


def read_rows(data):
    data = bytes(data)
    if not POOL_BASE < len(data) <= POOL_BASE + MAX_POOL_SIZE:
        raise ValueError('Invalid Message.Dat size')
    offsets = struct.unpack_from(f'<{SLOT_COUNT}H', data)
    if any(offset > MAX_OFFSET for offset in offsets):
        raise ValueError('Message.Dat offset exceeds the signed int16 range (32767)')
    unique = sorted(set(offsets))
    # The canonical file has an ordered active prefix and zero-valued trailing slots.
    # Those trailing slots alias the first string; they are not discarded as NULLs.
    if offsets[0] != 0 or list(offsets[:len(unique)]) != unique or any(offsets[len(unique):]):
        raise ValueError('Invalid Message.Dat reference-table layout')
    refs = {offset: [] for offset in unique}
    for index, offset in enumerate(offsets):
        refs[offset].append(index * 2)
    rows, cursor = [], POOL_BASE
    for index, relative in enumerate(unique):
        address = POOL_BASE + relative
        if address != cursor or address >= len(data):
            raise ValueError(f'Message.Dat record {index}: invalid pointer or pool gap')
        stop = data.find(b'\0', address)
        if stop < 0:
            raise ValueError(f'Message.Dat record {index}: missing NUL')
        raw = data[address:stop]
        # OV04 00a91390 appends the name after "St 0." in a 32-byte row.
        if index in STAGE_NAME_IDS and len(raw) > MAX_STAGE_NAME_BYTES:
            raise ValueError(f'Message.Dat record {index}: stage name exceeds 26 encoded bytes')
        rows.append({'index': index, 'relative': relative, 'refs': refs[relative],
                     'raw': raw, 'text': common.decode_str(raw)})
        cursor = stop + 1
    if cursor != len(data):
        raise ValueError('Message.Dat has unreferenced trailing bytes')
    return rows


def extract_text(data):
    return ''.join(f'//[{row["index"]:04d}]\n{row["text"]}\n' for row in read_rows(data))


def rebuild(data, content, charmap):
    data = bytes(data)
    rows = read_rows(data)
    entries = common.parse_text(content, len(rows))
    expected = [row['raw'] if entries[row['index']] == row['text']
                else common.encode_str(entries[row['index']], charmap) for row in rows]
    if expected == [row['raw'] for row in rows]:
        return data
    header, pool = bytearray(data[:POOL_BASE]), bytearray()
    for row, raw in zip(rows, expected):
        relative = len(pool)
        # OV04 uses LH, not LHU, when adding these references to the pool base.
        if relative > MAX_OFFSET:
            raise ValueError(f'Message.Dat record {row["index"]}: offset exceeds the signed int16 range (32767)')
        if relative + len(raw) + 1 > MAX_POOL_SIZE:
            raise ValueError('Message.Dat string pool exceeds the supported uint16 range (65536 bytes)')
        for position in row['refs']:
            struct.pack_into('<H', header, position, relative)
        pool.extend(raw + b'\0')
    result = bytes(header + pool)
    rebuilt = read_rows(result)
    if [row['raw'] for row in rebuilt] != expected or [row['refs'] for row in rebuilt] != [row['refs'] for row in rows]:
        raise ValueError('Message.Dat rebuilt strings or aliases changed unexpectedly')
    return result
