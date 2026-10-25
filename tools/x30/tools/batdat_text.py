"""Validated batdat text sections; keep file size, stats and section offsets fixed."""

import json
import struct


ENCODING = 'euc_jis_2004'
# Header index, existing editor label, record size, name-pointer field offset, has description.
PROFILES = (
    (0, '\ud30c\ud2f0\uc6d0 \uc774\ub984', 56, 22, False),
    (1, '\uc5d0\ub108\ubbf8 \uc774\ub984', 56, 22, False),
    (4, '\uc5d0\ud14c\ub974 1', 32, 0, False),
    (5, '\uc5d0\ud14c\ub974 2', 32, 0, False),
    (6, '\uc5d0\ud14c\ub974 3', 32, 0, True),
    (7, '\uacf5\uaca9\uae30 1', 40, 0, True),
    (8, '\uacf5\uaca9\uae30 2', 40, 0, True),
    (9, '\ub3c4\uad6c', 40, 0, True),
    (10, '\ucf64\ubcf4', 8, 0, True),
    (11, '\uc124\uba85 1', 8, 0, True),
    (12, '\uc124\uba85 2', 20, 0, True),
    (13, 'TEC 1', 20, 0, True),
    (14, 'TEC 2', 28, 0, True),
    (15, 'KAP', 24, 0, True),
    (16, 'AF', 20, 0, True),
    (17, 'G', 20, 0, True),
    (18, '\uc2ac\ub86f 1', 20, 0, True),
    (19, '\uc2ac\ub86f 2', 24, 0, True),
    (23, '\uc804\ud22c \uba54\ub274', 4, 0, True),
    (27, '\uc138\uadf8\uba3c\ud2b8', 8, 0, True),
)


def parse_json(content):
    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f'Duplicate JSON key: {key}')
            result[key] = value
        return result
    return json.loads(content.removeprefix('\ufeff'), object_pairs_hook=unique_object)


def read_sections(data):
    """Read canonical originals. Repacked/deduplicated outputs are not new originals."""
    data = bytes(data)
    if len(data) < 120 or struct.unpack_from('<2I', data) != (28, len(data)):
        raise ValueError('Invalid batdat section count or file size')
    bases = struct.unpack_from('<28I', data, 8)
    if (bases[0] != 120 or list(bases) != sorted(set(bases)) or
            bases[-1] >= len(data) or any(base % 4 for base in bases)):
        raise ValueError('Invalid batdat section boundaries')
    sections = []
    for index, label, stride, pointer_offset, has_desc in PROFILES:
        base = bases[index]
        end = bases[index + 1] if index + 1 < len(bases) else len(data)
        if base + pointer_offset + 2 > end:
            raise ValueError(f'{label}: truncated record table')
        first = struct.unpack_from('<H', data, base + pointer_offset)[0]
        if first == 0 or first % stride or first >= end - base:
            raise ValueError(f'{label}: invalid record table length')
        # The pointer offset is inside each record, not a header preceding the table.
        count = first // stride
        fields = ('name', 'desc') if has_desc else ('name',)
        cursor, records = base + first, []
        for entry_index in range(count):
            record = []
            for field_index, field in enumerate(fields):
                ptr_pos = base + entry_index * stride + pointer_offset + field_index * 2
                relative = struct.unpack_from('<H', data, ptr_pos)[0]
                address = base + relative
                if address != cursor or not base + first <= address < end:
                    raise ValueError(f'{label} [{entry_index}] {field}: invalid original string pointer')
                stop = data.find(b'\0', address, end)
                if stop < 0:
                    raise ValueError(f'{label} [{entry_index}] {field}: unterminated string')
                raw = data[address:stop]
                record.append({'field': field, 'ptr_pos': ptr_pos, 'relative': relative,
                               'raw': raw, 'text': raw.decode(ENCODING)})
                cursor = stop + 1
            records.append(record)
        if end - cursor > 3 or any(data[cursor:end]):
            raise ValueError(f'{label}: unaccounted data in the original string pool')
        sections.append({'label': label, 'base': base, 'end': end, 'pool_start': base + first,
                         'stride': stride, 'hdr_off': pointer_offset, 'records': records,
                         'sec_type': 'name_desc_pair' if index == 23 else ('name_desc' if has_desc else 'name_only')})
    return sections


def section_document(data, section):
    entries = []
    for index, fields in enumerate(section['records']):
        entry = {'idx': index, 'ptr_pos': fields[0]['ptr_pos'], 'name_ptr': fields[0]['relative']}
        if len(fields) == 1:
            # Legacy metadata name only: this word is a scalar, not an end pointer.
            entry['end_ptr'] = struct.unpack_from('<H', data, fields[0]['ptr_pos'] + 2)[0]
            entry.update({'jp': fields[0]['text'], 'ko': fields[0]['text']})
        else:
            entry['desc_ptr'] = fields[1]['relative']
            for field in fields:
                entry['jp_' + field['field']] = field['text']
                entry['ko_' + field['field']] = field['text']
        entries.append(entry)
    return {'base': section['base'], 'end_sec': section['end'] - 1,
            'stride': section['stride'], 'hdr_off': section['hdr_off'],
            'sec_type': section['sec_type'], 'entries': entries}


def extract_document(data):
    return {section['label']: section_document(data, section) for section in read_sections(data)}


def validate_document(data, sections, document):
    if not isinstance(document, dict) or set(document) != {section['label'] for section in sections}:
        raise ValueError('batdat JSON must contain every expected section, with no unknown sections')
    values = {}
    for section in sections:
        label = section['label']
        expected = section_document(data, section)
        actual = document[label]
        if not isinstance(actual, dict) or set(actual) != set(expected):
            raise ValueError(f'{label}: invalid section keys')
        for key in expected.keys() - {'entries'}:
            if type(actual[key]) is not type(expected[key]) or actual[key] != expected[key]:
                raise ValueError(f'{label}: read-only metadata mismatch: {key}')
        if not isinstance(actual['entries'], list):
            raise ValueError(f'{label}: entries must be a list')
        by_id = {}
        for entry in actual['entries']:
            if not isinstance(entry, dict) or type(entry.get('idx')) is not int:
                raise ValueError(f'{label}: entry idx must be an integer')
            index = entry['idx']
            if index in by_id:
                raise ValueError(f'{label}: duplicate entry idx {index}')
            by_id[index] = entry
        if set(by_id) != set(range(len(expected['entries']))):
            raise ValueError(f'{label}: missing or unknown entry idx')
        for original in expected['entries']:
            index = original['idx']
            actual_entry = by_id[index]
            if set(actual_entry) != set(original):
                raise ValueError(f'{label} [{index}]: missing or unknown field')
            for key, value in original.items():
                if key == 'ko' or key.startswith('ko_'):
                    if not isinstance(actual_entry[key], str):
                        raise ValueError(f'{label} [{index}] {key}: text must be a string')
                    values[(label, index, key)] = actual_entry[key]
                elif type(actual_entry[key]) is not type(value) or actual_entry[key] != value:
                    raise ValueError(f'{label} [{index}]: read-only source field mismatch: {key}')
    return values


def encode_text(text, charmap):
    text = ''.join(charmap.get(char, char) for char in text)
    tag = '[menu_sita]'
    if text.endswith(tag):
        text = text[:-len(tag)].replace(' ', '\u3001').replace('@', ' ')
    raw = text.encode(ENCODING)
    if b'\0' in raw:
        raise ValueError('Embedded NUL is not allowed')
    return raw


def pack_pool(records, first_relative, share_pairs):
    pool, pointers, known = bytearray(), [], {}
    shared = 0
    for record in records:
        key = tuple(record)
        if share_pairs and key in known:
            pointers.append(known[key])
            shared += 1
            continue
        offsets = []
        for raw in record:
            relative = first_relative + len(pool)
            if relative > 0xffff:
                raise ValueError('batdat string pointer exceeds uint16')
            offsets.append(relative)
            pool.extend(raw + b'\0')
        pointers.append(offsets)
        known[key] = offsets
    return bytes(pool), pointers, shared


def rebuild(data, document, charmap):
    data = bytes(data)
    sections = read_sections(data)
    values = validate_document(data, sections, document)
    prepared, details = [], []
    for section in sections:
        label, encoded, changed = section['label'], [], 0
        for index, fields in enumerate(section['records']):
            record = []
            for field in fields:
                key = 'ko' if len(fields) == 1 else 'ko_' + field['field']
                text = values[(label, index, key)]
                try:
                    raw = field['raw'] if text == field['text'] else encode_text(text, charmap)
                except (ValueError, UnicodeError) as exc:
                    raise ValueError(f'{label} [{index}] {key}: {exc}') from exc
                changed += raw != field['raw']
                record.append(raw)
            encoded.append(record)
        capacity = section['end'] - section['pool_start']
        first_relative = section['pool_start'] - section['base']
        pool, pointers, shared = pack_pool(encoded, first_relative, False)
        unshared_size = len(pool)
        # Keep name/description adjacency; share only complete, byte-identical records.
        if changed and len(pool) > capacity:
            pool, pointers, shared = pack_pool(encoded, first_relative, True)
        if changed and len(pool) > capacity:
            raise ValueError(f'{label}: pool overflow by {len(pool) - capacity} bytes '
                             f'({len(pool)} > {capacity}); no output was written')
        prepared.append((section, encoded, changed, pool, pointers))
        details.append({'section': label, 'entries': len(encoded), 'fields': sum(map(len, encoded)),
                        'changed_fields': changed, 'pool_capacity': capacity, 'pool_bytes': len(pool),
                        'free_bytes': capacity - len(pool), 'shared_records': shared,
                        'sharing_saved_bytes': unshared_size - len(pool)})
    result = bytearray(data)
    for section, _, changed, pool, pointers in prepared:
        if not changed:
            continue
        result[section['pool_start']:section['end']] = pool.ljust(section['end'] - section['pool_start'], b'\0')
        for fields, offsets in zip(section['records'], pointers):
            for field, relative in zip(fields, offsets):
                struct.pack_into('<H', result, field['ptr_pos'], relative)
    if len(result) != len(data) or result[:120] != data[:120]:
        raise ValueError('batdat size or header changed')
    for section, encoded, _, _, _ in prepared:
        for fields, values in zip(section['records'], encoded):
            for field, expected in zip(fields, values):
                address = section['base'] + struct.unpack_from('<H', result, field['ptr_pos'])[0]
                stop = result.find(b'\0', address, section['end'])
                if not section['pool_start'] <= address <= stop < section['end'] or result[address:stop] != expected:
                    raise ValueError(f'{section["label"]}: rebuilt reference verification failed')
    return bytes(result), details
