import os
import json
import struct
import sys

# --- 설정 ---
JSON_TABLE_PATH = "XENOSAGA KOR-JPN.json"
ENCODING = "EUC-JP"

def load_table():
    if not os.path.exists(JSON_TABLE_PATH):
        print(f"[-] 에러: {JSON_TABLE_PATH} 파일을 찾을 수 없습니다.")
        sys.exit(1)
    with open(JSON_TABLE_PATH, 'r', encoding='utf-8-sig') as f:
        return json.load(f)['replace-table']

def extract(bin_path):
    output_txt = bin_path + ".txt"
    if not os.path.exists(bin_path):
        print(f"[-] 에러: {bin_path} 파일이 없습니다.")
        return

    with open(bin_path, 'rb') as f:
        data = f.read()

    string_block_starts = [
        0x4718, 0x15908, 0x225F8, 0x2E318, 0x363B8,
        0x3AAA8, 0x42998, 0x47E58, 0x4E618, 0x53378,
        0x56488, 0x5FB38
    ]

    results = []
    last_bundle_end = 0

    print(f"[*] 추출 시작: {bin_path}")
    for start_addr in string_block_starts:
        base_point = data.find(b'DBF', last_bundle_end)
        if base_point == -1 or base_point > start_addr:
            base_point = data.rfind(b'DBF', 0, start_addr)
        if base_point == -1: continue

        next_dbf = data.find(b'DBF', start_addr)
        bundle_limit = next_dbf if next_dbf != -1 else len(data)

        strings_in_bundle = {}
        curr_s_ptr = start_addr
        while curr_s_ptr < bundle_limit:
            if data[curr_s_ptr] != 0:
                s_start = curr_s_ptr
                s_end = data.find(b'\x00', s_start)
                if s_end == -1 or s_end > bundle_limit: s_end = bundle_limit
                try:
                    # 원문의 0x5c 0x6e를 그대로 텍스트 파일에 표기
                    text = data[s_start:s_end].decode(ENCODING).replace('\n', '\\n').replace('\r', '\\r')
                    strings_in_bundle[s_start] = text
                except: pass
                curr_s_ptr = s_end + 1
            else: curr_s_ptr += 1

        header_cursor = base_point
        while header_cursor < start_addr:
            if header_cursor + 4 > len(data): break
            val = struct.unpack('<I', data[header_cursor : header_cursor + 4])[0]
            target_addr = base_point + (val & 0xFFFF)
            if target_addr in strings_in_bundle:
                results.append(f"{hex(target_addr)}|{strings_in_bundle[target_addr]}")
            header_cursor += 4
        last_bundle_end = bundle_limit

    with open(output_txt, 'w', encoding='utf-8-sig') as f:
        for item in results: f.write(item + '\n')
    print(f"[*] 추출 완료: {output_txt}")

def import_text(bin_path, txt_path):
    table = load_table()
    out_bin = bin_path + ".new"
    with open(bin_path, 'rb') as f:
        bin_data = bytearray(f.read())
    
    print(f"[*] 리빌드 시작: {txt_path}")
    patch_data = {}
    with open(txt_path, 'r', encoding='utf-8-sig') as f:
        for line in f:
            line = line.rstrip('\n').rstrip('\r')
            if '|' not in line: continue
            addr_str, content = line.split('|', 1)
            
            # "-1"이나 쓰레기 값 완전 제외 (바이너리 수정 리스트에 넣지 않음)
            clean_content = content.strip()
            if clean_content == "-1" or len(clean_content) == 0:
                continue
            patch_data[int(addr_str, 16)] = content

    patched_count = 0
    for addr, content in patch_data.items():
        # [핵심 수정] \\n을 개행문자(0x0a)로 바꾸지 않고 그대로 둡니다.
        # 이렇게 하면 원본처럼 0x5c 0x6e 바이트가 그대로 입력됩니다.
        patched_text = "".join([table.get(char, char) for char in content])
        try:
            new_bytes = patched_text.encode(ENCODING)
        except:
            new_bytes = patched_text.encode(ENCODING, errors='ignore')
        
        orig_end = bin_data.find(b'\x00', addr)
        if orig_end != -1:
            max_len = orig_end - addr
            
            # 프리즈 방지: EUC-JP 2바이트 문자 잘림 보정
            if len(new_bytes) > max_len:
                write_len = max_len
                if (0x81 <= new_bytes[write_len-1] <= 0x9F) or (0xE0 <= new_bytes[write_len-1] <= 0xEF):
                    write_len -= 1
            else:
                write_len = len(new_bytes)
            
            # 실제 데이터가 원본과 다를 때만 덮어쓰기
            if bin_data[addr : addr + write_len] != new_bytes[:write_len]:
                bin_data[addr : addr + write_len] = new_bytes[:write_len]
                # 수정된 부분 이후부터 원본 Null 영역까지 0x00으로 채움
                for i in range(write_len, max_len):
                    bin_data[addr + i] = 0
                patched_count += 1

    with open(out_bin, 'wb') as f:
        f.write(bin_data)
    print(f"[*] 리빌드 완료: 총 {patched_count}개의 유효 주소 패치됨.")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("\n[Xeno3 DBC Tool v35]")
        print("  python database_tool.py extract [DBC.bin]")
        print("  python database_tool.py import [DBC.bin] [DBC.bin.txt]")
    else:
        mode, target = sys.argv[1].lower(), sys.argv[2]
        if mode == "extract":
            extract(target)
        elif mode == "import":
            txt = sys.argv[3] if len(sys.argv) > 3 else target + ".txt"
            import_text(target, txt)