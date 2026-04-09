#!/usr/bin/env python3
"""
SegmentFileData.bin 텍스트 추출/임포트 도구
Xenosaga Episode III 세그먼트 파일 데이터

파일 구조:
  [0x00~0x1f] 파일 헤더 (32바이트):
    [0~3]   데이터셋 개수 (uint32 LE)
    [4~...]  (offset LE, size LE) 쌍 × 개수
    나머지:  0x90 패딩

  데이터셋 0: SEG 헤더 반복 (각 48바이트) + 문자열 영역
    [0~3]   'SEG\x00' 태그
    [4~7]   f1: 문자열 포인터 (ds_off 기준 상대)
    [8~11]  f2: 문자열 포인터
    [12~15] f3: 플래그/인덱스 (포인터 아님 — str_area 미만의 작은 값)
    [16~19] f4: 플래그/인덱스 (포인터 아님)
    [20~23] f5: 문자열 포인터
    [24~27] f6: 문자열 포인터
    [28~31] f7: 문자열 포인터
    [32~35] 0
    [36~47] 0x90 패딩

  데이터셋 1: 포인터 배열 + 문자열 (헤더 없음, ds_off부터 바로 시작)
    포인터: ds_off 기준 상대 오프셋 (uint32 LE)
    ptr==0 또는 ptr>=ds_size 에서 종료
"""

import struct, json, os, sys, shutil, re

ENCODE_SRC = 'euc-jisx0213'
ENCODE_DST = 'euc-kr'
SEG_TAG    = b'SEG\x00'
SEG_SIZE   = 48
# SEG 헤더 내 문자열 포인터 필드 오프셋 (f1,f2,f5,f6,f7)
SEG_PTR_OFFSETS = (4, 8, 20, 24, 28)


# ─── 치환표 ──────────────────────────────────────────────────────────────────

def load_charmap(path):
    try:
        with open(path, 'r', encoding='utf-8-sig') as f:
            data = json.load(f)
            if isinstance(data, dict) and 'replace-table' in data:
                return data['replace-table']
            return data
    except Exception as e:
        print(f'[경고] {path} 로드 실패: {e}')
        return None

def find_charmap():
    target = 'XENOSAGA KOR-JPN.json'
    if os.path.exists(target):
        cm = load_charmap(target)
        if cm:
            print(f'[치환표] {target} 로드 완료 ({len(cm)}개 항목)')
            return cm
    return None

def apply_charmap(text, charmap):
    if not charmap:
        return text
    keys = sorted([k for k in charmap if isinstance(charmap[k], str)], key=len, reverse=True)
    for k in keys:
        text = text.replace(k, charmap[k])
    return text


# ─── 파일 구조 파싱 ──────────────────────────────────────────────────────────

def get_datasets(data):
    num = struct.unpack_from('<I', data, 0)[0]
    result = []
    for i in range(num):
        base   = 4 + i * 8
        offset = struct.unpack_from('<I', data, base)[0]
        size   = struct.unpack_from('<I', data, base + 4)[0]
        is_seg = data[offset:offset+4] == SEG_TAG
        result.append({'index': i, 'offset': offset, 'size': size, 'is_seg': is_seg})
    return result

def read_str(data, abs_pos):
    if abs_pos <= 0 or abs_pos >= len(data):
        return ''
    raw = data[abs_pos:].split(b'\x00')[0]
    if not raw:
        return ''
    for enc in (ENCODE_SRC, ENCODE_DST):
        try:
            return raw.decode(enc)
        except Exception:
            pass
    return ''

def is_valid_ptr(ptr, ds_size, data, ds_off):
    if ptr == 0 or ptr >= ds_size:
        return False
    abs_p = ds_off + ptr
    if abs_p >= len(data):
        return False
    if data[abs_p] in (0x00, 0x90):
        return False
    raw = data[abs_p:].split(b'\x00')[0]
    if len(raw) < 2:
        return False
    for enc in (ENCODE_SRC, ENCODE_DST):
        try:
            raw.decode(enc)
            return True
        except Exception:
            pass
    return False


# ─── 문자열 수집 ─────────────────────────────────────────────────────────────

def collect_strings(data):
    datasets = get_datasets(data)
    seen = {}  # abs_pos -> record

    for ds in datasets:
        ds_off  = ds['offset']
        ds_size = ds['size']
        ds_idx  = ds['index']

        if ds['is_seg']:
            # ── SEG 헤더 방식 ─────────────────────────────────────────────
            pos       = ds_off
            entry_idx = 0
            while pos + SEG_SIZE <= ds_off + ds_size:
                if data[pos:pos+4] != SEG_TAG:
                    break
                for field_off in SEG_PTR_OFFSETS:
                    ptr = struct.unpack_from('<I', data, pos + field_off)[0]
                    if not is_valid_ptr(ptr, ds_size, data, ds_off):
                        continue
                    abs_p = ds_off + ptr
                    text  = read_str(data, abs_p)
                    if not text:
                        continue
                    if abs_p not in seen:
                        raw = data[abs_p:].split(b'\x00')[0]
                        seen[abs_p] = {
                            'ds_idx':    ds_idx,
                            'ds_off':    ds_off,
                            'is_seg':    True,
                            'entry_idx': entry_idx,
                            'field_off': field_off,
                            'ptr':       ptr,
                            'abs_pos':   abs_p,
                            'raw_size':  len(raw) + 1,
                            'text':      text,
                        }
                entry_idx += 1
                pos += SEG_SIZE

        else:
            # ── 포인터 배열 방식 (헤더 없음) ─────────────────────────────
            pos     = ds_off
            ptr_idx = 0
            while pos + 4 <= ds_off + ds_size:
                ptr = struct.unpack_from('<I', data, pos)[0]
                if ptr == 0 or ptr >= ds_size:
                    break
                abs_p = ds_off + ptr
                text  = read_str(data, abs_p)
                if text and abs_p not in seen:
                    raw = data[abs_p:].split(b'\x00')[0]
                    seen[abs_p] = {
                        'ds_idx':  ds_idx,
                        'ds_off':  ds_off,
                        'is_seg':  False,
                        'ptr_idx': ptr_idx,
                        'ptr':     ptr,
                        'abs_pos': abs_p,
                        'raw_size': len(raw) + 1,
                        'text':    text,
                    }
                pos     += 4
                ptr_idx += 1

    return sorted(seen.values(), key=lambda r: r['abs_pos'])


# ─── 추출 ────────────────────────────────────────────────────────────────────

def cmd_extract(bin_path, out_path, charmap):
    with open(bin_path, 'rb') as f:
        data = f.read()

    records = collect_strings(data)
    lines   = []
    for r in records:
        text = apply_charmap(r['text'], charmap) if charmap else r['text']
        if r['is_seg']:
            id_part = f"{r['ds_idx']}:{r['entry_idx']}:f{r['field_off']}:{r['abs_pos']:06x}"
        else:
            id_part = f"{r['ds_idx']}:str{r['ptr_idx']}:ptr:{r['abs_pos']:06x}"
        lines.append(f"<<<{id_part}>>> {text}")

    with open(out_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')

    print(f"추출 완료: {len(records)}개 문자열 → {out_path}")


# ─── 임포트 ──────────────────────────────────────────────────────────────────

META_RE = re.compile(r'^<<<(\d+):[^:]+:[^:]+:([0-9a-f]+)>>> ?(.*)', re.DOTALL)


MENU_SITA_TAG = '[menu_sita]'

def apply_menu_sita(text):
    tag = '[menu_sita]'
    if text.strip().endswith(tag):
        text = text.replace(tag, '').rstrip()
        text = text.replace(' ', '、')
        text = text.replace('@', ' ')
    return text


def patch_ptrs(data, ds_info, old_ptr, new_ptr):
    ds_off  = ds_info['offset']
    ds_size = ds_info['size']
    old_b   = struct.pack('<I', old_ptr)
    new_b   = struct.pack('<I', new_ptr)

    if ds_info['is_seg']:
        pos = ds_off
        while pos + SEG_SIZE <= ds_off + ds_size:
            if data[pos:pos+4] != SEG_TAG:
                break
            for field_off in SEG_PTR_OFFSETS:
                if data[pos+field_off:pos+field_off+4] == old_b:
                    data[pos+field_off:pos+field_off+4] = new_b
            pos += SEG_SIZE
    else:
        pos = ds_off
        while pos + 4 <= ds_off + ds_size:
            if data[pos:pos+4] == old_b:
                data[pos:pos+4] = new_b
            pos += 4

def cmd_import(bin_path, txt_path, out_path, charmap):
    with open(bin_path, 'rb') as f:
        orig = bytearray(f.read())

    with open(txt_path, 'r', encoding='utf-8') as f:
        lines = [l.rstrip('\n') for l in f]

    datasets = get_datasets(bytes(orig))
    records  = collect_strings(bytes(orig))
    size_map = {r['abs_pos']: r['raw_size'] for r in records}
    ds_map   = {ds['index']: ds for ds in datasets}

    patched  = 0
    overflow = []

    for line in lines:
        m = META_RE.match(line)
        if not m:
            continue
        ds_idx    = int(m.group(1))
        abs_pos   = int(m.group(2), 16)
        text      = m.group(3)
        orig_size = size_map.get(abs_pos, 0)
        if orig_size == 0:
            continue

        text = apply_menu_sita(text)
        final_text = apply_charmap(text, charmap)
        try:
            new_bytes = final_text.encode(ENCODE_SRC) + b'\x00'
        except UnicodeEncodeError as e:
            print(f"[오류] 미치환 글자: '{final_text[e.start:e.end]}'")
            sys.exit(1)
        if len(new_bytes) <= orig_size:
            orig[abs_pos:abs_pos + orig_size] = \
                new_bytes + b'\x00' * (orig_size - len(new_bytes))
            patched += 1
        else:
            overflow.append((abs_pos, new_bytes, orig_size, ds_idx))

    if overflow:
        print(f"[오버플로우] {len(overflow)}개 → 파일 끝 재배치")
        orig.extend(b'\x00' * ((-len(orig)) % 16))

        for abs_pos, new_bytes, orig_size, ds_idx in overflow:
            new_off = len(orig)
            orig.extend(new_bytes)
            ds_info = ds_map[ds_idx]
            patch_ptrs(orig, ds_info,
                       old_ptr=abs_pos - ds_info['offset'],
                       new_ptr=new_off  - ds_info['offset'])
            orig[abs_pos:abs_pos + orig_size] = b'\x00' * orig_size
            patched += 1
            print(f"  {hex(abs_pos)} → {hex(new_off)}")

    with open(out_path, 'wb') as f:
        f.write(bytes(orig))
    print(f"임포트 완료: {patched}개 패치 → {out_path}")


# ─── CLI ─────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 3:
        print("사용법:\n"
              "  python segmentfiledatatool.py extract <bin> [출력.txt] [치환표.json]\n"
              "  python segmentfiledatatool.py import  <bin> <입력.txt> [출력.bin] [치환표.json]")
        sys.exit(1)

    cmd, bin_path = sys.argv[1].lower(), sys.argv[2]

    charmap = None
    for arg in sys.argv[3:]:
        if arg.endswith('.json'):
            charmap = load_charmap(arg)
            print(f"[치환표] {arg} ({len(charmap)}개 항목)")
            break
    if charmap is None:
        charmap = find_charmap()

    non_json = [a for a in sys.argv[3:] if not a.endswith('.json')]

    if cmd == 'extract':
        out = non_json[0] if non_json else bin_path.replace('.bin', '.txt')
        cmd_extract(bin_path, out, charmap)
    elif cmd == 'import':
        if not non_json:
            print("txt 파일을 지정하세요."); sys.exit(1)
        txt = non_json[0]
        out = non_json[1] if len(non_json) > 1 else bin_path.replace('.bin', '_new.bin')
        bak = bin_path + '.bak'
        if not os.path.exists(bak):
            shutil.copy2(bin_path, bak)
            print(f"[백업] {bak}")
        cmd_import(bin_path, txt, out, charmap)
    else:
        print(f"알 수 없는 명령: {cmd}"); sys.exit(1)

if __name__ == '__main__':
    main()
