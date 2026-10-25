"""Read the known historical batdat JSON layout without rewriting its editor."""

import json

from . import batdat_text


def signature(document):
    if not isinstance(document, dict):
        raise ValueError('batdat editor must be an object')
    shape = {}
    for label, section in document.items():
        if not isinstance(section, dict) or not isinstance(section.get('entries'), list):
            raise ValueError(f'{label}: invalid section')
        entries = {}
        for entry in section['entries']:
            if not isinstance(entry, dict) or type(entry.get('idx')) is not int:
                raise ValueError(f'{label}: invalid entry idx')
            if entry['idx'] in entries:
                raise ValueError(f'{label}: duplicate entry idx')
            row = dict(entry)
            for key in ('ko', 'ko_name', 'ko_desc'):
                if key in row:
                    if not isinstance(row[key], str):
                        raise ValueError(f'{label}: {key} must be a string')
                    row[key] = None
            entries[row['idx']] = row
        shape[label] = {**section, 'entries': [entries[i] for i in sorted(entries)]}
    return json.dumps(shape, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def normalize(data, document, template):
    if signature(document) != signature(template):
        # The normal strict validator handles current format and rejects altered metadata.
        return document
    current = batdat_text.extract_document(data)
    carried = expected = 0
    for label, section in current.items():
        old_fields = {}
        old_section = document[label]
        for entry in old_section['entries']:
            fields = ('name',) if old_section['sec_type'] == 'name_only' else ('name', 'desc')
            for field in fields:
                key = 'ko' if len(fields) == 1 else 'ko_'+field
                jp = key.replace('ko', 'jp', 1)
                position = entry['ptr_pos']+(2 if field == 'desc' else 0)
                if position in old_fields:
                    raise ValueError(f'{label}: duplicate legacy pointer')
                old_fields[position] = (entry, key, jp, field)
                expected += entry[key] != entry[jp]
        for entry in section['entries']:
            fields = ('name',) if section['sec_type'] == 'name_only' else ('name', 'desc')
            for field in fields:
                key = 'ko' if len(fields) == 1 else 'ko_'+field
                jp = key.replace('ko', 'jp', 1)
                position = entry['ptr_pos']+(2 if field == 'desc' else 0)
                old = old_fields.pop(position, None)
                if old is None:
                    continue
                old_entry, old_key, old_jp, old_field = old
                if (old_field != field or old_entry[old_jp] != entry[jp]
                        or old_entry[field+'_ptr'] != entry[field+'_ptr']):
                    raise ValueError(f'{label}: cannot map legacy field at {position:#x}')
                entry[key] = old_entry[old_key]
                carried += entry[key] != entry[jp]
        for position, (entry, key, jp, _) in old_fields.items():
            if entry[key] != entry[jp]:
                raise ValueError(f'{label}: translated legacy field has no real target at {position:#x}')
    if carried != expected:
        raise ValueError('A legacy batdat translation would be lost')
    return current
