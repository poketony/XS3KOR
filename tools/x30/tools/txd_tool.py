import struct
import os
import sys
import re
import json
try:
    from .output import write_output
except ImportError:
    from output import write_output

class TXDTool:
    def __init__(self, encoding='euc_jis_2004'):
        self.encoding = encoding

    def get_data_start(self, data):
        if len(data) >= 8:
            first, second = struct.unpack_from('<2I', data)
            if first and second == (first + 1) * 4 and second <= len(data):
                # A count can itself be divisible by four. Check its whole table
                # before accepting it, since ordinary pointers can look similar.
                try:
                    self.read_slots(data, first + 1)
                except ValueError:
                    pass
                else:
                    return second
            if first and first % 4 == 0 and first <= len(data):
                return first
        # Fallback for a source with leading NULL slots, not an address-width limit.
        for i in range(0, len(data), 4):
            if i + 4 > len(data): break
            upper_half = struct.unpack('<H', data[i+2:i+4])[0]
            if upper_half != 0:
                return i
        return len(data)

    def safe_decode(self, raw_bytes):
        """디코딩 에러 발생 시 2바이트씩 묶어서 [0xXXXX] 형태로 추출"""
        decoded_str = ""
        curr_bytes = raw_bytes
        
        while curr_bytes:
            try:
                # 현재 남은 바이트를 통째로 디코딩 시도
                decoded_str += curr_bytes.decode(self.encoding).replace('\r\n', '\n')
                break
            except UnicodeDecodeError as e:
                # 에러 발생 전까지의 정상적인 부분은 추가
                decoded_str += curr_bytes[:e.start].decode(self.encoding).replace('\r\n', '\n')
                
                # 에러 지점부터 2바이트를 추출 (남은 바이트가 1바이트뿐이면 1바이트만)
                step = 2 if len(curr_bytes) >= e.start + 2 else 1
                bad_unit = curr_bytes[e.start : e.start + step]
                
                decoded_str += f"[0x{bad_unit.hex().upper()}]"
                curr_bytes = curr_bytes[e.start + step:]
        return decoded_str

    def read_slots(self, data, count=None):
        start = self.get_data_start(data) if count is None else count * 4
        if not 0 < start <= len(data) or start % 4:
            raise ValueError('Invalid TXD pointer table')
        slots = []
        for pos in range(0, start, 4):
            ptr = struct.unpack_from('<I', data, pos)[0]
            if pos == 0 and ptr == start // 4 - 1:
                slots.append(None)  # menutext: entry count, not a string pointer
                continue
            if ptr == 0:
                slots.append(None)
                continue
            if not start <= ptr < len(data):
                raise ValueError(f'Invalid TXD pointer: {pos:#x}')
            end = data.find(b'\x00', ptr)
            if end < 0:
                raise ValueError(f'Unterminated TXD string: {ptr:#x}')
            slots.append(data[ptr:end])
        return slots

    def extract_text(self, data):
        return ''.join(f'[{i}]{self.safe_decode(raw) if raw is not None else ""}\n'
                       for i, raw in enumerate(self.read_slots(data)))

    def parse_text(self, content, count):
        content = content.removeprefix('\ufeff').replace('\r\n', '\n')
        markers = list(re.finditer(r'^\[(\d+)\]', content, re.MULTILINE))
        if not markers or content[:markers[0].start()].strip():
            raise ValueError('Missing TXD record marker')
        texts = {}
        for i, marker in enumerate(markers):
            index = int(marker[1])
            if index >= count or index in texts:
                raise ValueError(f'Unknown or duplicate TXD ID: {index}')
            end = markers[i+1].start() if i+1 < len(markers) else len(content)
            texts[index] = content[marker.end():end].removesuffix('\n')
        if len(texts) != count:
            raise ValueError(f'Missing TXD IDs: expected {count}, got {len(texts)}')
        return texts

    def encode_text(self, text, charmap):
        # Preserve the existing TXD-specific menu_sita convention.
        if '[menu_sita]' in text:
            text = text.replace('[menu_sita]', '').replace(' ', '、')
        text = ''.join(charmap.get(char, char) for char in text)
        raw = bytearray()
        for token in re.split(r'(\[0x[0-9A-Fa-f]+\])', text):
            match = re.fullmatch(r'\[0x([0-9A-Fa-f]+)\]', token)
            if match:
                digits = match[1]
                if len(digits) % 2:
                    digits = '0' + digits
                raw.extend(bytes.fromhex(digits))
            else:
                raw.extend(token.replace('\n', '\r\n').encode(self.encoding))
        if b'\x00' in raw:
            raise ValueError('Embedded NUL in TXD string')
        return bytes(raw)

    def rebuild(self, data, content, charmap=None):
        slots = self.read_slots(data)
        texts = self.parse_text(content, len(slots))
        first_word = struct.unpack_from('<I', data)[0]
        counted = first_word == len(slots) - 1
        if counted:
            # Old exports dereferenced the count and emitted a spurious [0] line.
            legacy = self.safe_decode(data[first_word:data.index(b'\x00', first_word)])
            if texts[0] not in ('', legacy):
                raise ValueError('TXD ID 0 is a read-only count header, not translatable text')
            texts[0] = ''
        expected = []
        for i, raw in enumerate(slots):
            original = self.safe_decode(raw) if raw is not None else ''
            if texts[i] == original:
                expected.append(raw)
            else:
                expected.append(self.encode_text(texts[i], charmap or {}))
        if expected == slots:
            return data

        table = bytearray(len(slots) * 4)
        if counted:
            struct.pack_into('<I', table, 0, first_word)
        pool = bytearray()
        for i, raw in enumerate(expected):
            if raw is None:
                continue
            struct.pack_into('<I', table, i * 4, len(table) + len(pool))
            pool.extend(raw + b'\x00')
        result = bytes(table + pool)
        if self.read_slots(result, len(slots)) != expected:
            raise ValueError('TXD result verification failed')
        return result

    def extract(self, txd_path):
        with open(txd_path, 'rb') as f:
            data = f.read()
        output = txd_path + '.txt'
        write_output(output, self.extract_text(data).encode('utf-8'), (txd_path,), overwrite=False)
        print(f'Extract complete: {output}')

    def repack(self, original_txd, modified_txt, output_path=None, charmap=None):
        with open(original_txd, 'rb') as f:
            data = f.read()
        with open(modified_txt, 'r', encoding='utf-8-sig') as f:
            content = f.read()
        result = self.rebuild(data, content, charmap)
        output_path = output_path or os.path.splitext(original_txd)[0] + '_repacked.txd'
        write_output(output_path, result, (original_txd, modified_txt))
        print(f'Repack complete: {output_path}')

if __name__ == "__main__":
    tool = TXDTool()
    if len(sys.argv) < 3:
        print("사용법:")
        print("  추출: python txd_tool.py e 파일명.txd")
        print("  리팩: python txd_tool.py r 파일명.txd 파일명.txt")
    else:
        mode = sys.argv[1].lower()
        if mode == 'e': tool.extract(sys.argv[2])
        elif mode == 'r':
            table = {}
            if len(sys.argv) > 5:
                with open(sys.argv[5], encoding='utf-8-sig') as f:
                    table = json.load(f)['replace-table']
            tool.repack(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else sys.argv[2] + '.txt',
                        sys.argv[4] if len(sys.argv) > 4 else None, table)
