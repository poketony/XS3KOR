import os
import json
import struct
import sys

# --- 설정 ---
JSON_TABLE_PATH = "XENOSAGA KOR-JPN.json"
ENCODING = "EUC-JP"

STRING_BLOCK_STARTS = [
    0x4718, 0x15908, 0x225F8, 0x2E318, 0x363B8,
    0x3AAA8, 0x42998, 0x47E58, 0x4E618, 0x53378,
    0x56488, 0x5FB38
]

# ──────────────────────────────────────────────
# DBC1 번들 구조:
#   각 번들은 고유한 POINTER_BASE(직전 마지막 DBF 위치)를 가짐
#   포인터 = POINTER_BASE + val  (32비트, 마스킹 없음)
#   포인터 테이블 범위: POINTER_BASE ~ string_start
#   파일 끝 재배치 가능 (val이 32비트이므로 파일 끝 주소도 표현 가능)
# ──────────────────────────────────────────────

def load_table():
    if not os.path.exists(JSON_TABLE_PATH):
        print(f"[-] 에러: {JSON_TABLE_PATH} 파일을 찾을 수 없습니다.")
        sys.exit(1)
    with open(JSON_TABLE_PATH, 'r', encoding='utf-8-sig') as f:
        return json.load(f)['replace-table']


def build_bundle_info(data):
    """각 번들의 (index, base, start, limit, str_end) 반환."""
    bundles = []
    last_bundle_end = 0
    for i, start_addr in enumerate(STRING_BLOCK_STARTS):
        base_point = data.find(b'DBF', last_bundle_end)
        if base_point == -1 or base_point > start_addr:
            base_point = data.rfind(b'DBF', 0, start_addr)
        if base_point == -1:
            continue

        next_dbf = data.find(b'DBF', start_addr)
        bundle_limit = next_dbf if next_dbf != -1 else len(data)

        bundles.append({
            'index':   i,
            'base':    base_point,
            'start':   start_addr,
            'limit':   bundle_limit,
            'str_end': STRING_BLOCK_STARTS[i+1] if i+1 < len(STRING_BLOCK_STARTS) else len(data),
        })
        last_bundle_end = bundle_limit
    return bundles


def extract(bin_path):
    output_txt = bin_path + ".txt"
    if not os.path.exists(bin_path):
        print(f"[-] 에러: {bin_path} 파일이 없습니다.")
        return

    with open(bin_path, 'rb') as f:
        data = f.read()

    bundles = build_bundle_info(data)
    results = []

    print(f"[*] 추출 시작: {bin_path}")
    for b in bundles:
        base_point = b['base']
        start_addr = b['start']
        str_end    = b['str_end']

        # 문자열 수집: start_addr ~ str_end 전체
        strings_in_bundle = {}
        curr = start_addr
        while curr < str_end:
            if data[curr] != 0:
                s_start = curr
                s_end = data.find(b'\x00', s_start)
                if s_end == -1 or s_end > str_end:
                    s_end = str_end
                try:
                    text = data[s_start:s_end].decode(ENCODING) \
                               .replace('\n', '\\n').replace('\r', '\\r')
                    strings_in_bundle[s_start] = text
                except:
                    pass
                curr = s_end + 1
            else:
                curr += 1

        # 포인터 스캔: base_point ~ start_addr (32비트 val, 마스킹 없음)
        header_cursor = base_point
        while header_cursor < start_addr:
            if header_cursor + 4 > len(data):
                break
            val = struct.unpack('<I', data[header_cursor:header_cursor + 4])[0]
            target_addr = base_point + val
            if target_addr in strings_in_bundle:
                results.append(f"{hex(target_addr)}|{strings_in_bundle[target_addr]}")
            header_cursor += 4

    with open(output_txt, 'w', encoding='utf-8-sig') as f:
        for item in results:
            f.write(item + '\n')
    print(f"[*] 추출 완료: {output_txt} ({len(results)}줄)")


def find_all_pointer_refs(data, target_addr, bundle_base, ptr_table_start, ptr_table_end):
    """포인터 테이블(ptr_table_start~ptr_table_end) 내에서
    target_addr를 가리키는 포인터 위치를 반환.
    포인터 값 = target_addr - bundle_base (32비트)
    4바이트 정렬된 위치만 유효."""
    val = target_addr - bundle_base
    if val <= 0 or val > 0xFFFFFFFF:
        return []
    search = struct.pack('<I', val)
    refs = []
    search_slice = data[ptr_table_start:ptr_table_end]
    pos = 0
    while True:
        p = search_slice.find(search, pos)
        if p == -1:
            break
        abs_p = ptr_table_start + p
        if abs_p % 4 == 0:
            refs.append(abs_p)
        pos = p + 1
    return refs


def relocate_slot(bin_data, old_addr, new_bytes,
                  bundle_base, ptr_table_start, ptr_table_end):
    """슬롯을 파일 끝으로 재배치.
    내부 오프셋 포인터도 함께 업데이트.
    new_bytes: null terminator 포함."""
    old_end = bin_data.find(b'\x00', old_addr)
    if old_end == -1:
        old_end = len(bin_data)
    old_slot_len = old_end - old_addr

    new_addr = len(bin_data)
    print(f"  [reloc] {hex(old_addr)} -> {hex(new_addr)} "
          f"({old_slot_len}B -> {len(new_bytes)-1}B)")

    # 슬롯 내 모든 오프셋에 대한 포인터 수집
    internal_refs = {}
    for offset in range(0, old_slot_len + 1):
        target = old_addr + offset
        refs = find_all_pointer_refs(bytes(bin_data), target,
                                     bundle_base, ptr_table_start, ptr_table_end)
        for r in refs:
            internal_refs[r] = target

    # 새 데이터를 파일 끝에 추가
    bin_data.extend(new_bytes)

    # 포인터 업데이트
    for ptr_pos, old_target in internal_refs.items():
        new_target = new_addr + (old_target - old_addr)
        new_val = new_target - bundle_base
        bin_data[ptr_pos:ptr_pos+4] = struct.pack('<I', new_val)

    # 원본 슬롯 클리어
    for i in range(old_addr, old_end + 1):
        if i < len(bin_data):
            bin_data[i] = 0x00

    return bin_data


def import_text(bin_path, txt_path):
    table = load_table()
    out_bin = bin_path + ".new"

    with open(bin_path, 'rb') as f:
        bin_data = bytearray(f.read())

    bundles = build_bundle_info(bytes(bin_data))

    # 주소 -> 번들 매핑
    def find_bundle(addr):
        for b in bundles:
            if b['start'] <= addr < b['str_end']:
                return b
        return None

    print(f"[*] 리빌드 시작: {txt_path}")
    patch_data = {}
    with open(txt_path, 'r', encoding='utf-8-sig') as f:
        for line in f:
            line = line.rstrip('\n').rstrip('\r')
            if '|' not in line:
                continue
            addr_str, content = line.split('|', 1)
            clean = content.strip()
            if clean == "-1" or len(clean) == 0:
                continue
            patch_data[int(addr_str, 16)] = content

    patched_count   = 0
    relocated_count = 0

    for addr, content in patch_data.items():
        bundle = find_bundle(addr)
        if bundle is None:
            continue

        bundle_base   = bundle['base']
        ptr_tbl_start = bundle['base']
        ptr_tbl_end   = bundle['start']

        patched_text = "".join([table.get(char, char) for char in content])
        try:
            new_bytes = patched_text.encode(ENCODING)
        except:
            new_bytes = patched_text.encode(ENCODING, errors='ignore')

        orig_end = bin_data.find(b'\x00', addr)
        if orig_end == -1:
            continue
        max_len = orig_end - addr

        if len(new_bytes) > max_len:
            # 오버플로우: 파일 끝 재배치
            null_terminated = new_bytes + b'\x00'
            bin_data = relocate_slot(bin_data, addr, null_terminated,
                                     bundle_base, ptr_tbl_start, ptr_tbl_end)
            relocated_count += 1
            patched_count   += 1
        else:
            # 인-플레이스 패치
            write_len = len(new_bytes)
            # EUC-JP 2바이트 경계 보정: decode 시도로 정확히 판단
            while write_len > 0:
                try:
                    new_bytes[:write_len].decode(ENCODING)
                    break
                except:
                    write_len -= 1

            if bin_data[addr:addr+write_len] != new_bytes[:write_len]:
                bin_data[addr:addr+write_len] = new_bytes[:write_len]
                for i in range(write_len, max_len):
                    bin_data[addr + i] = 0
                patched_count += 1

    with open(out_bin, 'wb') as f:
        f.write(bin_data)
    print(f"[*] 리빌드 완료: 총 {patched_count}개 패치 ({relocated_count}개 재배치).")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("\n[Xeno3 DBC2 Tool v41]")
        print("  python database2_tool.py extract [DBC.bin]")
        print("  python database2_tool.py import [DBC.bin] [DBC.bin.txt]")
    else:
        mode, target = sys.argv[1].lower(), sys.argv[2]
        if mode == "extract":
            extract(target)
        elif mode == "import":
            txt = sys.argv[3] if len(sys.argv) > 3 else target + ".txt"
            import_text(target, txt)
