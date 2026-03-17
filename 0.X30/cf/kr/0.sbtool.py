import sys
import os
import re
import struct
import json

class Xeno3AutoScanner:
    def __init__(self, json_path=None):
        self.encoding = 'euc-jp'
        self.base_addr = None
        self.ptr_table_start = None
        self.kor_to_jp_table = {}
        
        # [수정] UTF-8 BOM 대응을 위해 utf-8-sig 사용
        if json_path and os.path.exists(json_path):
            try:
                with open(json_path, 'r', encoding='utf-8-sig') as f:
                    data = json.load(f)
                    self.kor_to_jp_table = data.get("replace-table", {})
                if self.kor_to_jp_table:
                    print(f"[*] 변환 테이블 로드 완료: {len(self.kor_to_jp_table)}개 문자")
                else:
                    print("[!] 경고: JSON은 읽었으나 'replace-table'이 비어 있습니다.")
            except Exception as e:
                print(f"[!] JSON 로드 실패: {e}")

    def convert_kor_to_jp(self, text):
        """한글 문자를 테이블 기반 일본어 한자로 변환"""
        result = ""
        for char in text:
            # 변환 테이블에 없으면 원래 문자 유지 (이때 한글이면 나중에 에러 발생 가능)
            result += self.kor_to_jp_table.get(char, char)
        return result

    def scan_structure(self, data):
        """파일 구조 분석 (기존과 동일)"""
        self.base_addr = data.find(b'seg_now')
        if self.base_addr == -1: return False

        search_pos = (self.base_addr // 4) * 4
        found_end_of_table = -1
        while search_pos > 0:
            val = struct.unpack('<I', data[search_pos-4:search_pos])[0]
            if val == 0:
                found_end_of_table = search_pos
                break
            search_pos -= 4
        
        if found_end_of_table == -1: return False

        curr = found_end_of_table - 4
        last_valid = found_end_of_table
        while curr >= 0:
            val = struct.unpack('<I', data[curr:curr+4])[0]
            if 0 < val < len(data): last_valid = curr
            else: break
            curr -= 4
        
        self.ptr_table_start = last_valid
        print(f"[*] 구조 분석 완료: Table({hex(self.ptr_table_start)}) / Base({hex(self.base_addr)})")
        return True

    def extract(self, sb_path):
        """추출 기능 (기존과 동일)"""
        with open(sb_path, 'rb') as f:
            data = f.read()
        if not self.scan_structure(data): return
        
        txt_path = os.path.splitext(sb_path)[0] + ".txt"
        extracted = []
        curr_ptr = self.ptr_table_start
        while curr_ptr < self.base_addr:
            offset = struct.unpack('<I', data[curr_ptr:curr_ptr+4])[0]
            if offset == 0: break
            actual_off = self.base_addr + offset
            if actual_off >= len(data): break
            end = actual_off
            while end < len(data) and data[end] != 0x00: end += 1
            raw_bytes = data[actual_off:end]
            text = raw_bytes.decode(self.encoding, errors='ignore')
            extracted.append((hex(actual_off), text))
            curr_ptr += 4

        with open(txt_path, 'w', encoding='utf-8-sig') as f:
            for off, txt in extracted:
                f.write(f"[{off}]\n{txt.replace('\n', '[n]')}\n\n")
        print(f"[*] {txt_path} 추출 완료")

    def iimport(self, original_sb, txd_path):
        """치환 후 리빌드"""
        if not self.kor_to_jp_table:
            print("[!] 오류: 변환 테이블이 로드되지 않았습니다. 작업을 중단합니다.")
            return

        with open(original_sb, 'rb') as f:
            sb_data = bytearray(f.read())
        if not self.scan_structure(sb_data): return
        
        with open(txd_path, 'r', encoding='utf-8-sig') as f:
            content = f.read()

        items = re.findall(r"\[(0x[0-9a-fA-F]+)\]\r?\n(.*?)(?=\r?\n\r?\n\[0x|\r?\n\r?\n\Z|$)", content, re.DOTALL)
        
        extension_pos = len(sb_data)
        new_ext_data = bytearray()

        for i, (orig_off_str, text) in enumerate(items):
            orig_off = int(orig_off_str, 16)
            clean_text = text.replace('[n]', '\n')
            
            # 한글 -> 일본어 한자 치환
            converted_text = self.convert_kor_to_jp(clean_text)
            
            try:
                new_bytes = converted_text.encode(self.encoding)
            except UnicodeEncodeError as e:
                # [수정] 어떤 문자가 에러를 일으켰는지 더 자세히 알려줌
                print(f"[!] 인코딩 에러: {orig_off_str} 위치에서 변환되지 않은 한글 발견!")
                print(f"    문제의 텍스트: {converted_text}")
                raise e
            
            temp_off = orig_off
            while temp_off < len(sb_data) and sb_data[temp_off] != 0x00:
                temp_off += 1
            orig_len = temp_off - orig_off
            
            if len(new_bytes) <= orig_len:
                sb_data[orig_off : orig_off + len(new_bytes)] = new_bytes
                for j in range(orig_off + len(new_bytes), temp_off):
                    sb_data[j] = 0x00
                new_ptr_val = orig_off - self.base_addr
            else:
                current_ext_off = extension_pos + len(new_ext_data)
                new_ext_data.extend(new_bytes)
                new_ext_data.append(0x00)
                new_ptr_val = current_ext_off - self.base_addr
            
            ptr_pos = self.ptr_table_start + (i * 4)
            if ptr_pos + 4 <= self.base_addr:
                struct.pack_into('<I', sb_data, ptr_pos, new_ptr_val)

        if new_ext_data:
            sb_data.extend(new_ext_data)

        output = original_sb + ".new"
        with open(output, 'wb') as f:
            f.write(sb_data)
        print(f"[+] 리팩 완료: {output}")

if __name__ == "__main__":
    if len(sys.argv) < 3: sys.exit(1)
    # JSON 파일명이 정확한지 확인해 주세요.
    JSON_FILE = "XENOSAGA KOR-JPN.json"
    p = Xeno3AutoScanner(JSON_FILE)
    if sys.argv[1] == "extract": p.extract(sys.argv[2])
    elif sys.argv[1] == "import": p.iimport(sys.argv[2], sys.argv[3])