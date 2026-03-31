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
        
        if json_path and os.path.exists(json_path):
            try:
                with open(json_path, 'r', encoding='utf-8-sig') as f:
                    data = json.load(f)
                    self.kor_to_jp_table = data.get("replace-table", {})
                if self.kor_to_jp_table:
                    print(f"[*] 변환 테이블 로드 완료: {len(self.kor_to_jp_table)}개 문자")
            except Exception as e:
                print(f"[!] JSON 로드 실패: {e}")

    def convert_kor_to_jp(self, text):
        result = ""
        for char in text:
            result += self.kor_to_jp_table.get(char, char)
        return result

    def scan_structure(self, data):
        """파일 구조 분석: seg_now 또는 특정 대사열을 기준으로 찾음"""
        # 1순위: --- main --- 찾기
        self.base_addr = data.find(b'--- main ---')
        
        # 2순위: --- main ---가 없으면 사용자가 언급한 문자열로 찾기 (EUC-JP 인코딩)
        if self.base_addr == -1:
            target_str = "E.S.に乗りますか？".encode('euc-jp')
            self.base_addr = data.find(target_str)
            if self.base_addr != -1:
                print("[*] 'seg_now' 대신 대사 시작점을 기준으로 분석을 시작합니다.")

        if self.base_addr == -1:
            print("[!] 기준점(--- main --- 또는 대사 시작점)을 찾을 수 없습니다.")
            return False

        # 포인터 테이블은 기준점보다 앞선 위치에 4바이트 단위로 존재함
        search_pos = (self.base_addr // 4) * 4
        found_end_of_table = -1
        
        # 0x00000000(테이블 끝 표시)을 거슬러 올라가며 탐색
        while search_pos > 0:
            val = struct.unpack('<I', data[search_pos-4:search_pos])[0]
            if val == 0:
                found_end_of_table = search_pos
                break
            search_pos -= 4
        
        if found_end_of_table == -1: 
            # 만약 0을 못 찾았다면 파일 처음부터 기준점까지가 전부 테이블일 가능성 염두
            found_end_of_table = 4 

        curr = found_end_of_table - 4
        last_valid = found_end_of_table
        
        # 유효한 포인터 값(데이터 길이 내의 값)이 끝나는 지점을 찾음
        while curr >= 0:
            val = struct.unpack('<I', data[curr:curr+4])[0]
            # 오프셋 값이 파일 크기보다 작고 0보다 큰지 확인
            if 0 < val < len(data): 
                last_valid = curr
            else:
                break
            curr -= 4
        
        self.ptr_table_start = last_valid
        print(f"[*] 구조 분석 완료: Table({hex(self.ptr_table_start)}) / Base({hex(self.base_addr)})")
        return True

    def extract(self, sb_path):
        with open(sb_path, 'rb') as f:
            data = f.read()
        if not self.scan_structure(data): return
        
        txt_path = os.path.splitext(sb_path)[0] + ".txt"
        extracted = []
        curr_ptr = self.ptr_table_start
        
        while curr_ptr < self.base_addr:
            offset = struct.unpack('<I', data[curr_ptr:curr_ptr+4])[0]
            if offset == 0: break
            
            # 실제 주소 계산
            actual_off = self.base_addr + offset
            if actual_off >= len(data): break
            
            end = actual_off
            while end < len(data) and data[end] != 0x00:
                end += 1
            
            raw_bytes = data[actual_off:end]
            try:
                text = raw_bytes.decode(self.encoding)
            except:
                text = raw_bytes.decode(self.encoding, errors='ignore')
                
            extracted.append((hex(actual_off), text))
            curr_ptr += 4

        with open(txt_path, 'w', encoding='utf-8-sig') as f:
            for off, txt in extracted:
                f.write(f"[{off}]\n{txt.replace('\n', '[n]')}\n\n")
        print(f"[*] {txt_path} 추출 완료")

    def iimport(self, original_sb, txd_path):
        if not self.kor_to_jp_table:
            print("[!] 오류: 변환 테이블이 로드되지 않았습니다.")
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
            converted_text = self.convert_kor_to_jp(clean_text)
            
            try:
                new_bytes = converted_text.encode(self.encoding)
            except UnicodeEncodeError:
                print(f"[!] 인코딩 에러: {orig_off_str} 위치에서 테이블에 없는 한글 발견!")
                continue
            
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
    JSON_FILE = "XENOSAGA KOR-JPN.json"
    p = Xeno3AutoScanner(JSON_FILE)
    if sys.argv[1] == "extract": p.extract(sys.argv[2])
    elif sys.argv[1] == "import": p.iimport(sys.argv[2], sys.argv[3])