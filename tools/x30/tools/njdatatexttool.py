#!/usr/bin/env python3
import struct, json, os, sys, re
try:
    from .output import write_output
except ImportError:
    from output import write_output

# 일본어 원본 인코딩 (EUC-JP 2004)
ENCODE_SRC = 'euc_jis_2004'
VALID_TAGS = {b'TOP\x00', b'CHA\x00', b'EVE\x00', b'MVD\x00', b'SEG\x00'}
ENTRY_SIZES = {b'TOP\x00': 32, b'CHA\x00': 16, b'EVE\x00': 32, b'MVD\x00': 48, b'SEG\x00': 48}

PTR_FIELDS = {
    b'TOP\x00': (('p1', 4), ('p2', 8), ('p3', 12)),
    b'CHA\x00': (('p1', 4), ('p3', 12)),
    b'EVE\x00': (('p1', 4), ('p2', 8)),
    b'MVD\x00': (('p1', 12), ('p2', 16)),
    b'SEG\x00': (('f4', 4), ('f8', 8), ('f20', 20), ('f24', 24), ('f28', 28)),
}

def entry_size(tag_bytes):
    return ENTRY_SIZES.get(tag_bytes, 32)

def ptr_fields(tag_bytes):
    return PTR_FIELDS[tag_bytes]

# ─── [menu_sita] 처리 로직 ──────────────────────────────────────────────────

def process_menu_sita(text):
    tag = "[menu_sita]"
    if text.strip().endswith(tag):
        # 1. 태그 제거
        text = text.replace(tag, "").rstrip()
        # 2. 반각 공백 -> 、 (먼저)
        text = text.replace(" ", "、")
        # 3. @ -> 반각 공백 (나중)
        text = text.replace("@", " ")
    return text

# ─── 치환표 로직 ───────────────────────────────────────────────────────────

def load_charmap(path):
    try:
        with open(path, 'r', encoding='utf-8-sig') as f:
            data = json.load(f)
            if isinstance(data, dict) and "replace-table" in data:
                return data["replace-table"]
            return data
    except Exception as e:
        print(f"[경고] {path} 로드 실패: {e}")
        return None

def find_charmap():
    target = 'XENOSAGA KOR-JPN.json'
    if os.path.exists(target):
        cm = load_charmap(target)
        if cm:
            print(f"[치환표] {target} 로드 완료 ({len(cm)}개 항목)")
            return cm
    return None

def apply_charmap(text, charmap):
    if not charmap:
        return text
    # 긴 문자열부터 치환
    keys = sorted([k for k in charmap.keys() if isinstance(charmap[k], str)], key=len, reverse=True)
    for k in keys:
        text = text.replace(k, charmap[k])
    return text

# ─── 바이너리 분석/수집 ─────────────────────────────────────────────────────

TAG_SIZE = 4

def get_datasets(data):
    if len(data) < 4:
        raise ValueError('Truncated dataset header')
    num = struct.unpack_from('<I', data, 0)[0]
    if 4 + num * 8 > len(data):
        raise ValueError('Truncated dataset table')
    result = []
    previous_end = 4 + num * 8
    for i in range(num):
        base = 4 + i * 8
        offset = struct.unpack_from('<I', data, base)[0]
        size   = struct.unpack_from('<I', data, base + 4)[0]
        if offset < previous_end or size < 4 or offset + size > len(data):
            raise ValueError(f'Invalid dataset bounds: {i}')
        result.append({'index': i, 'offset': offset, 'size': size})
        previous_end = offset + size
    return result

def is_ptr_dataset(data, ds_off):
    if ds_off + TAG_SIZE > len(data): return True
    return data[ds_off:ds_off + TAG_SIZE] not in VALID_TAGS

def count_entries(data, ds_off, ds_size):
    n, pos = 0, ds_off
    while pos < ds_off + ds_size:
        tb = data[pos:pos + TAG_SIZE]
        if tb not in VALID_TAGS: break
        sz = entry_size(tb)
        if pos + sz > ds_off + ds_size: break
        n += 1; pos += sz
    return n

def read_str(data, abs_pos):
    end = data.index(b'\x00', abs_pos)
    return data[abs_pos:end].decode(ENCODE_SRC)


def pointer_fields(data, ds):
    ds_off, ds_size = ds['offset'], ds['size']
    refs = []
    if is_ptr_dataset(data, ds_off):
        table_size = struct.unpack_from('<I', data, ds_off)[0]
        if not 0 < table_size < ds_size or table_size % 4:
            raise ValueError(f"Invalid pointer array: dataset {ds['index']}")
        for i in range(table_size // 4):
            refs.append((ds_off + i * 4, f'str{i}', 'ptr'))
        pool_start = ds_off + table_size
    else:
        pos = ds_off
        for i in range(count_entries(data, ds_off, ds_size)):
            tag = data[pos:pos + TAG_SIZE]
            for field, offset in ptr_fields(tag):
                refs.append((pos + offset, str(i), field))
            pos += entry_size(tag)
        # The final TOP entry uses its nominal tail padding for string bytes.
        pool_start = max(ref[0] + 4 for ref in refs)
    for pos, entry, field in refs:
        ptr = struct.unpack_from('<I', data, pos)[0]
        if ptr and not pool_start <= ds_off + ptr < ds_off + ds_size:
            raise ValueError(f'Pointer outside the source string pool: {pos:#x}')
        if ptr:
            yield pos, entry, field

def collect_strings(data):
    data = bytes(data)
    datasets = get_datasets(data)
    seen = {}
    for ds in datasets:
        ds_off, ds_size, ds_idx = ds['offset'], ds['size'], ds['index']
        for ptr_pos, entry, field in pointer_fields(data, ds):
            abs_p = ds_off + struct.unpack_from('<I', data, ptr_pos)[0]
            end = data.find(b'\x00', abs_p, ds_off + ds_size)
            if end < 0:
                raise ValueError(f'Unterminated source string: {abs_p:#x}')
            if abs_p not in seen:
                seen[abs_p] = {'ds_idx': ds_idx, 'ds_off': ds_off, 'abs_pos': abs_p,
                               'raw_size': end - abs_p + 1, 'text': read_str(data, abs_p),
                               'entry': entry, 'field': field, 'refs': []}
            seen[abs_p]['refs'].append(ptr_pos)
    return sorted(seen.values(), key=lambda r: r['abs_pos'])

# ─── 실행 로직 ─────────────────────────────────────────────────────────────

# 정규식: <<<데이터셋번호:상세정보:절대주소>>> 텍스트
META_RE = re.compile(r'<<<(\d+):[^\r\n]+:([0-9a-fA-F]+)>>> ?([^\r\n]*)')

def extract_text(data):
    return ''.join(f"<<<{r['ds_idx']}:{r['entry']}:{r['field']}:{r['abs_pos']:06x}>>> {r['text']}\n"
                   for r in collect_strings(data))


def rebuild(data, content, charmap):
    records = collect_strings(data)
    by_address = {r['abs_pos']: r for r in records}
    encoded = {}
    for number, line in enumerate(content.split('\n'), 1):
        line = line.removesuffix('\r')
        if not line:
            continue
        m = META_RE.fullmatch(line)
        if not m:
            raise ValueError(f'Invalid TXT record on line {number}')
        ds_idx, abs_pos, text = int(m.group(1)), int(m.group(2), 16), m.group(3)
        record = by_address.get(abs_pos)
        if record is None or record['ds_idx'] != ds_idx or abs_pos in encoded:
            raise ValueError(f'Unknown, mismatched or duplicate address on line {number}: {abs_pos:#x}')
        final_text = apply_charmap(process_menu_sita(text), charmap)
        if '\x00' in final_text:
            raise ValueError(f'Embedded NUL on line {number}')
        encoded[abs_pos] = final_text.encode(ENCODE_SRC) + b'\x00'
    missing = by_address.keys() - encoded.keys()
    if missing:
        raise ValueError(f'Missing {len(missing)} TXT records; first address: {min(missing):#x}')
    for left, right in zip(records, records[1:]):
        if left['abs_pos'] + left['raw_size'] > right['abs_pos']:
            raise ValueError('Overlapping source strings need explicit handling')

    orig = bytearray(data)
    overflow = []
    for record in records:
        abs_pos, orig_size = record['abs_pos'], record['raw_size']
        new_bytes = encoded[abs_pos]
        if len(new_bytes) <= orig_size:
            orig[abs_pos:abs_pos + orig_size] = new_bytes + b'\x00' * (orig_size - len(new_bytes))
        else:
            overflow.append(record)
    if overflow:
        orig.extend(b'\x00' * ((-len(orig)) % 16))
        for record in overflow:
            abs_pos, orig_size = record['abs_pos'], record['raw_size']
            new_off = len(orig)
            orig.extend(encoded[abs_pos])
            for ptr_pos in record['refs']:
                struct.pack_into('<I', orig, ptr_pos, new_off - record['ds_off'])
            orig[abs_pos:abs_pos + orig_size] = b'\x00' * orig_size
    # Re-read every original reference, including pointers to appended strings.
    for record in records:
        expected = encoded[record['abs_pos']]
        for ptr_pos in record['refs']:
            target = record['ds_off'] + struct.unpack_from('<I', orig, ptr_pos)[0]
            if orig[target:target + len(expected)] != expected:
                raise ValueError(f'Pointer verification failed: {ptr_pos:#x}')
    return bytes(orig)


def cmd_import(bin_path, txt_path, out_path, charmap):
    with open(bin_path, 'rb') as f: data = f.read()
    with open(txt_path, 'r', encoding='utf-8-sig') as f: content = f.read()
    result = rebuild(data, content, charmap)
    write_output(out_path, result, (bin_path, txt_path))
    print(f"Import complete: {out_path}")

def main():
    if len(sys.argv) < 3:
        print("사용법: python njdatatexttool.py <extract/import> <bin> <txt>")
        sys.exit(1)

    cmd_raw, bin_path = sys.argv[1].lower(), sys.argv[2]
    cmd = 'extract' if cmd_raw in ['extract', '추출'] else 'import' if cmd_raw in ['import', '가져오기'] else cmd_raw
    charmap = find_charmap()

    if cmd == 'extract':
        out = sys.argv[3] if len(sys.argv) > 3 else bin_path.replace('.bin', '.txt')
        with open(bin_path, 'rb') as f: data = f.read()
        write_output(out, extract_text(data).encode('utf-8'), (bin_path,), overwrite=False)
    elif cmd == 'import':
        txt = sys.argv[3]
        out = sys.argv[4] if len(sys.argv) > 4 else bin_path.replace('.bin', '.bin.new')
        cmd_import(bin_path, txt, out, charmap)

if __name__ == '__main__':
    main()
