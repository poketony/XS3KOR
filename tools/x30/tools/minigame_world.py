"""World.Dat names consumed by OV04 at +0x38 with a 32-byte stride."""

import struct

from . import njdbcommon_tool as common


FILE_SIZE = 0x678
NAME_BASE = 0x38
NAME_SIZE = 0x20
NAME_COUNT = 10


def read_rows(data):
    if len(data) != FILE_SIZE or struct.unpack_from('<H', data)[0] != NAME_COUNT:
        raise ValueError('Invalid World.Dat size or world count')
    rows = []
    for index in range(NAME_COUNT):
        address = NAME_BASE + index * NAME_SIZE
        slot = data[address:address + NAME_SIZE]
        stop = slot.find(b'\0')
        if stop <= 0:
            raise ValueError(f'World.Dat record {index}: name must be nonempty and NUL-terminated')
        raw = slot[:stop]
        rows.append({'index': index, 'address': address, 'raw': raw, 'text': common.decode_str(raw)})
    return rows


def extract_text(data):
    return ''.join(f'//[{row["index"]:04d}]\n{row["text"]}\n' for row in read_rows(data))


def rebuild(data, content, charmap):
    rows = read_rows(data)
    entries = common.parse_text(content, NAME_COUNT)
    result = bytearray(data)
    for row in rows:
        text = entries[row['index']]
        if text == row['text']:
            continue
        raw = common.encode_str(text, charmap)
        # An empty name terminates the world-selection loop (OV04 00a90968).
        if not raw or len(raw) >= NAME_SIZE:
            raise ValueError(f'World.Dat record {row["index"]}: name must be 1-31 encoded bytes')
        address = row['address']
        result[address:address + NAME_SIZE] = raw.ljust(NAME_SIZE, b'\0')
    read_rows(result)
    return bytes(result)
