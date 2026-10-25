"""Plain EUC-JIS-2004 #MESSAGE documents read by SLPS 00249980/00249790."""

import re

from . import njdbcommon_tool as common


MAX_FILE_BYTES = 0x19000
MESSAGE_BUFFER_BYTES = 0x7ec
HEADER = re.compile(rb'#MESSAGE ([0-9]+)')


def read_document(data):
    data = bytes(data)
    if not data or len(data) > MAX_FILE_BYTES:
        raise ValueError('PSE MES exceeds the 102400-byte input buffer or is empty')
    payload = data[:-1] if data.endswith(b'\0') else data
    if b'\0' in payload or not payload.endswith(b'\r\n'):
        raise ValueError('PSE MES requires complete CRLF lines and no embedded NUL')
    if b'\r' in payload.replace(b'\r\n', b'') or b'\n' in payload.replace(b'\r\n', b''):
        raise ValueError('PSE MES requires CRLF, not bare CR or LF')
    text = common.decode_str(payload)
    rows, current = [], None
    for number, line in enumerate(payload.split(b'\r\n')[:-1], 1):
        marker = HEADER.fullmatch(line)
        if marker:
            index = int(marker[1])
            if index != len(rows):
                raise ValueError(f'PSE MES line {number}: MESSAGE IDs must remain ordered from 0')
            current = {'index': index, 'lines': [], 'runtime_bytes': 1}
            rows.append(current)
        elif b'#' in line or b'FRAME' in line:
            raise ValueError(f'PSE MES line {number}: reserved # or FRAME parser token')
        elif current is None:
            if line:
                raise ValueError('PSE MES has text before the first MESSAGE')
        else:
            current['lines'].append(line)
            # Each CRLF line becomes four control bytes + its text, then final NUL.
            current['runtime_bytes'] += 4 + len(line)
            if current['runtime_bytes'] > MESSAGE_BUFFER_BYTES:
                raise ValueError(f'PSE MES record {current["index"]}: rendered message exceeds 2028 bytes')
    if not rows:
        raise ValueError('PSE MES has no MESSAGE records')
    return text, rows


def extract_text(data):
    return read_document(data)[0].replace('\r\n', '\n')


def rebuild(original, content, charmap):
    text, rows = read_document(original)
    content = content.removeprefix('\ufeff').replace('\r\n', '\n')
    if '\r' in content or '\0' in content:
        raise ValueError('PSE editor contains bare CR or NUL')
    if content == text.replace('\r\n', '\n'):
        return bytes(original)
    # Explicit EOF protects the last message's unbounded scan; originals remain exact.
    result = common.encode_str(content.replace('\n', '\r\n'), charmap) + b'\0'
    _, rebuilt = read_document(result)
    if len(rebuilt) != len(rows):
        raise ValueError('PSE MES MESSAGE count changed; preserve every original ID')
    return result
