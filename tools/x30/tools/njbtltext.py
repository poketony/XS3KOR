"""Battle-label editing using the existing njDBcommon container layout."""

from . import njdbcommon_tool as common


def read_slots(data):
    base, _ = common.parse_header(data)
    offsets, start = common.load_ptrs(data, base)
    if offsets != sorted(set(offsets)):
        raise ValueError('Expected distinct ordered njBtlText slots')
    slots = []
    for index, address in enumerate(offsets):
        limit = offsets[index + 1] if index + 1 < len(offsets) else len(data)
        stop = data.find(b'\0', address, limit)
        if stop < 0 or any(data[stop + 1:limit]):
            raise ValueError(f'njBtlText slot {index} is not a NUL-padded string')
        raw = bytes(data[address:stop])
        slots.append({'address': address, 'limit': limit, 'raw': raw, 'text': common.decode_str(raw)})
    return base, start, slots


def extract_text(data):
    _, _, slots = read_slots(data)
    return ''.join(f'//[{index:02d}]\n{slot["text"]}\n' for index, slot in enumerate(slots))


def rebuild(data, content, charmap):
    data = bytes(data)
    base, _, slots = read_slots(data)
    entries = common.parse_text(content, len(slots))
    expected = [slot['raw'] if entries[index] == slot['text'] else common.encode_str(entries[index], charmap)
                for index, slot in enumerate(slots)]
    # Preserve the existing binary-only patch exactly when all labels fit their slots.
    if all(len(raw) + 1 <= slot['limit'] - slot['address'] for raw, slot in zip(expected, slots)):
        output = bytearray(data)
        for raw, slot in zip(expected, slots):
            if raw != slot['raw']:
                output[slot['address']:slot['limit']] = (raw + b'\0').ljust(slot['limit'] - slot['address'], b'\0')
        result = bytes(output)
    else:
        result = common.rebuild(data, content, charmap)
    common.parse_header(result)
    offsets, _ = common.load_ptrs(result, base)
    actual = [result[address:result.index(b'\0', address)] for address in offsets]
    if actual != expected:
        raise ValueError('njBtlText rebuilt references differ from the editor')
    return result
