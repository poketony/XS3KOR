#!/usr/bin/env python3
import struct, json, os, sys, re

# 일본어 원본 인코딩 (EUC-JP 2004)
ENCODE_SRC = 'euc-jisx0213'
VALID_TAGS = {b'TOP\x00', b'CHA\x00', b'EVE\x00'}
ENTRY_SIZES = {b'TOP\x00': 32, b'CHA\x00': 16, b'EVE\x00': 32}

PTR_FIELDS = {
    b'TOP\x00': ('p1', 'p2', 'p3'),
    b'CHA\x00': ('p1', 'p2', 'p3'),
    b'EVE\x00': ('p1', 'p2'),
}

def entry_size(tag_bytes):
    return ENTRY_SIZES.get(tag_bytes, 32)

def ptr_fields(tag_bytes):
    return PTR_FIELDS.get(tag_bytes, ('p1', 'p2', 'p3'))

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
    num = struct.unpack_from('<I', data, 0)[0]
    result = []
    for i in range(num):
        base = 4 + i * 8
        offset = struct.unpack_from('<I', data, base)[0]
        size   = struct.unpack_from('<I', data, base + 4)[0]
        result.append({'index': i, 'offset': offset, 'size': size})
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
    if abs_pos <= 0 or abs_pos >= len(data): return ''
    raw = data[abs_pos:].split(b'\x00')[0]
    try: return raw.decode(ENCODE_SRC)
    except: return raw.decode('latin-1', errors='replace')

def collect_strings(data):
    datasets = get_datasets(data)
    seen = {}
    for ds in datasets:
        ds_off, ds_size, ds_idx = ds['offset'], ds['size'], ds['index']
        if is_ptr_dataset(data, ds_off):
            pos, ptr_idx = ds_off, 0
            while pos + 4 <= ds_off + ds_size:
                ptr = struct.unpack_from('<I', data, pos)[0]
                if ptr == 0 or ptr >= ds_size: break
                abs_p = ds_off + ptr
                raw = data[abs_p:].split(b'\x00')[0]
                if raw and abs_p not in seen:
                    seen[abs_p] = {'ds_idx': ds_idx, 'ds_off': ds_off, 'abs_pos': abs_p, 'raw_size': len(raw)+1, 'text': read_str(data, abs_p)}
                pos += 4; ptr_idx += 1
        else:
            n_entries = count_entries(data, ds_off, ds_size)
            pos = ds_off
            for _ in range(n_entries):
                tb = data[pos:pos+TAG_SIZE]
                esz = entry_size(tb)
                ptrs = struct.unpack_from('<3I', data, pos + TAG_SIZE)
                fields = ptr_fields(tb)
                for i, field in enumerate(('p1', 'p2', 'p3')):
                    if field in fields:
                        ptr = ptrs[i]
                        if 0 < ptr < ds_size:
                            abs_p = ds_off + ptr
                            raw = data[abs_p:].split(b'\x00')[0]
                            if raw and abs_p not in seen:
                                seen[abs_p] = {'ds_idx': ds_idx, 'ds_off': ds_off, 'abs_pos': abs_p, 'raw_size': len(raw)+1, 'text': read_str(data, abs_p)}
                pos += esz
    return sorted(seen.values(), key=lambda r: r['abs_pos'])

# ─── 실행 로직 ─────────────────────────────────────────────────────────────

# 정규식: <<<데이터셋번호:상세정보:절대주소>>> 텍스트
META_RE = re.compile(r'^<<<(\d+):.*:([0-9a-fA-F]+)>>> ?(.*)', re.DOTALL)

def patch_ptrs(data, ds_info, old_ptr, new_ptr):
    ds_off, ds_size = ds_info['offset'], ds_info['size']
    old_b, new_b = struct.pack('<I', old_ptr), struct.pack('<I', new_ptr)
    pos = ds_off
    while pos < ds_off + ds_size:
        if data[pos:pos+4] == old_b: data[pos:pos+4] = new_b
        pos += 4

def cmd_import(bin_path, txt_path, out_path, charmap):
    with open(bin_path, 'rb') as f: orig = bytearray(f.read())
    with open(txt_path, 'r', encoding='utf-8-sig') as f: lines = f.readlines()

    records = collect_strings(bytes(orig))
    size_map = {r['abs_pos']: r['raw_size'] for r in records}
    datasets = get_datasets(bytes(orig))
    ds_map = {ds['index']: ds for ds in datasets}
    
    patched, overflow = 0, []

    for line in lines:
        m = META_RE.match(line.strip())
        if not m: continue
        ds_idx, abs_pos, text = int(m.group(1)), int(m.group(2), 16), m.group(3)
        orig_size = size_map.get(abs_pos, 0)
        if orig_size == 0: continue

        # 1. [menu_sita] 특수 규칙 처리
        text = process_menu_sita(text)
        # 2. 한글 -> 한자 치환
        final_text = apply_charmap(text, charmap)
        # 3. 인코딩
        try:
            new_bytes = final_text.encode(ENCODE_SRC) + b'\x00'
        except UnicodeEncodeError as e:
            print(f"[오류] 미치환 글자: '{final_text[e.start:e.end]}'")
            sys.exit(1)

        if len(new_bytes) <= orig_size:
            orig[abs_pos:abs_pos + orig_size] = new_bytes + b'\x00' * (orig_size - len(new_bytes))
            patched += 1
        else:
            overflow.append((abs_pos, new_bytes, orig_size, ds_idx))

    if overflow:
        orig.extend(b'\x00' * ((-len(orig)) % 16))
        for abs_pos, new_bytes, orig_size, ds_idx in overflow:
            new_off = len(orig)
            orig.extend(new_bytes)
            ds_info = ds_map[ds_idx]
            patch_ptrs(orig, ds_info, abs_pos - ds_info['offset'], new_off - ds_info['offset'])
            orig[abs_pos:abs_pos + orig_size] = b'\x00' * orig_size
            patched += 1
    
    with open(out_path, 'wb') as f: f.write(bytes(orig))
    print(f"임포트 완료: {patched}개 패치 적용 -> {out_path}")

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
        records = collect_strings(data)
        with open(out, 'w', encoding='utf-8') as f:
            for r in records:
                f.write(f"<<<{r['ds_idx']}:addr:{r['abs_pos']:06x}>>> {r['text']}\n")
    elif cmd == 'import':
        txt = sys.argv[3]
        out = sys.argv[4] if len(sys.argv) > 4 else bin_path.replace('.bin', '.bin.new')
        cmd_import(bin_path, txt, out, charmap)

if __name__ == '__main__':
    main()