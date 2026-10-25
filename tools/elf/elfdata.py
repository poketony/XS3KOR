"""ELF32 layout and lossless candidate-string inspection for XS3."""

import re
import struct


class Elf:
    def __init__(self, data):
        self.data = data
        if len(data) < 52 or data[:7] != b'\x7fELF\x01\x01\x01':
            raise ValueError('Expected little-endian ELF32')
        h = struct.unpack_from('<16sHHIIIIIHHHHHH', data)
        if h[2] != 8 or (h[8], h[9], h[11]) != (52, 32, 40):
            raise ValueError('Unsupported ELF/MIPS layout')
        self.entry = h[4]
        self.ph = [struct.unpack('<8I', self.slice(h[5] + i * 32, 32)) for i in range(h[10])]
        sections = [struct.unpack('<10I', self.slice(h[6] + i * 40, 40)) for i in range(h[12])]
        names = sections[h[13]]
        names = self.slice(names[4], names[5])
        self.sections = {}
        for s in sections:
            end = names.find(b'\0', s[0])
            if end < 0:
                raise ValueError('Invalid section name')
            name = names[s[0]:end].decode('ascii')
            if name in self.sections:
                raise ValueError('Duplicate section')
            self.sections[name] = dict(type=s[1], flags=s[2], va=s[3], offset=s[4], size=s[5])
            if s[1] != 8:
                self.slice(s[4], s[5])
        for p in self.ph:
            self.slice(p[1], p[4])
            if p[4] > p[5]:
                raise ValueError('Invalid load size')

    def slice(self, offset, size):
        if offset < 0 or size < 0 or offset + size > len(self.data):
            raise ValueError('ELF range out of bounds')
        return self.data[offset:offset + size]

    def va(self, offset):
        for s in self.sections.values():
            if s['type'] != 8 and s['flags'] & 2 and s['offset'] <= offset < s['offset'] + s['size']:
                return s['va'] + offset - s['offset']
        raise ValueError('Offset outside allocated section')


def control_size(data, offset, limit):
    code = data[offset]
    sizes = {9: 1, 10: 1, 11: 1, 12: 4, 13: 2, 14: 6, 15: 4, 25: 2, 27: 2}
    if code in (8, 21):
        if offset + 2 > limit:
            raise ValueError('Truncated control')
        operand = data[offset + 1]
        size = 2 + (sum(n for bit, n in ((1, 2), (2, 2), (4, 3), (8, 2), (16, 2)) if operand & bit)
                    if code == 8 else operand)
    elif code in sizes:
        size = sizes[code]
    else:
        raise ValueError(f'Unknown control {code:02X}')
    if offset + size > limit:
        raise ValueError('Truncated control')
    return size


def read_string(data, start, limit):
    offset, display, controls = start, [], []
    while offset < limit:
        code = data[offset]
        if code == 0:
            return data[start:offset], ''.join(display), controls
        if code < 32:
            size = control_size(data, offset, limit)
            packet = data[offset:offset + size]
            controls.append(packet.hex())
            display.append('\\n' if code == 10 else '{' + packet.hex().upper() + '}')
        elif code < 127:
            size = 1
            display.append('\\\\' if code == 92 else '{' + f'{code:02X}' + '}' if code in (123, 125) else chr(code))
        else:
            size = 3 if code == 143 else 2
            raw = data[offset:offset + size]
            char = raw.decode('euc_jis_2004')
            if char.encode('euc_jis_2004') != raw:
                raise ValueError('Non-roundtripping character')
            display.append(char)
        offset += size
    raise ValueError('No terminator')


def candidates(data, start, end):
    used = start
    for offset in range(start, end, 4):
        if offset < used or not data[offset]:
            continue
        try:
            raw, text, controls = read_string(data, offset, min(end, offset + 8192))
        except (ValueError, UnicodeError):
            continue
        if not re.search('[\u3041-\u30ff]', text):
            continue
        used = offset + len(raw) + 1
        yield {'offset': offset, 'size': len(raw), 'text': text, 'controls': controls}
