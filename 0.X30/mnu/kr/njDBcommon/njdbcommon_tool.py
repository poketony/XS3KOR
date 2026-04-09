#!/usr/bin/env python3
"""
njDBcommon.bin Extract / Import Tool
=====================================
파일 구조 (헤더 16바이트):
  [0x00] uint32 LE  = 뭔가의 개수  (변경 불필요, 무시)
  [0x04] uint32 LE  = 포인터 기준점 (ptr_base)
                      포인터 테이블의 시작 오프셋이자
                      실제 오프셋 계산 기준: real_offset = pval + ptr_base
  [0x08] uint32 LE  = payload 크기 (ptr_base 이후 전체)
                      파일 전체 크기 = ptr_base + payload_size
  [0x0c] uint32 LE  = 0x90909090 (패딩)

포인터 테이블 (ptr_base부터):
  4바이트 LE × N개
  real_offset = pval + ptr_base
  첫 pval + ptr_base = 문자열 영역 시작
  N = (문자열 영역 시작 - ptr_base) / 4

문자열 영역: null-terminated, EUC-JP

Usage:
  python njdbcommon_tool.py extract <input.bin> <output.txt>
  python njdbcommon_tool.py import  <original.bin> <translated.txt> <output.bin> [--table TABLE.json]
"""

import struct, sys, json, os

ENC_PRI = 'euc-jp'
ENC_FB  = 'euc-jis-2004'

# ── 파싱 ──────────────────────────────────────

def parse_header(data):
    ptr_base     = struct.unpack_from('<I', data, 0x04)[0]
    payload_size = struct.unpack_from('<I', data, 0x08)[0]
    return ptr_base, payload_size

def load_ptrs(data, ptr_base):
    first_pval = struct.unpack_from('<I', data, ptr_base)[0]
    str_start  = first_pval + ptr_base
    n          = (str_start - ptr_base) // 4
    offsets    = [struct.unpack_from('<I', data, ptr_base + i*4)[0] + ptr_base for i in range(n)]
    return offsets, str_start

def decode_str(raw):
    for enc in (ENC_PRI, ENC_FB):
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            pass
    return raw.decode('latin-1')

def read_strings(data, offsets):
    result = []
    for off in offsets:
        try:
            end = data.index(b'\x00', off)
        except ValueError:
            end = len(data)
        result.append(decode_str(data[off:end]))
    return result

# ── 치환표 (import 전용) ──────────────────────

def find_table_candidates(hint=None):
    cands = []
    if hint:
        cands.append(hint)
    for d in (os.getcwd(), os.path.dirname(os.path.abspath(__file__))):
        for f in os.listdir(d):
            if f.lower().endswith('.json') and 'kor' in f.lower():
                cands.append(os.path.join(d, f))
    seen = set()
    return [c for c in cands if not (c in seen or seen.add(c))]

def load_table(path):
    for enc in ('utf-8-sig', 'utf-8'):
        try:
            with open(path, 'r', encoding=enc) as f:
                obj = json.load(f)
            break
        except UnicodeDecodeError:
            continue
    rt = obj.get('replace-table', obj)
    if not isinstance(rt, dict):
        raise ValueError("replace-table이 dict 형식이 아닙니다.")
    return rt  # {한글: 한자}

def auto_load_table(hint=None):
    for path in find_table_candidates(hint):
        if os.path.isfile(path):
            try:
                tbl = load_table(path)
                if tbl:
                    print(f"[치환표] {path} ({len(tbl)}개)")
                    return tbl
            except Exception as e:
                print(f"[경고] {path}: {e}")
    return {}

def apply_table(s, k2h):
    result, i = [], 0
    while i < len(s):
        for kor, hanja in k2h.items():
            if s[i:i+len(kor)] == kor:
                result.append(hanja)
                i += len(kor)
                break
        else:
            result.append(s[i])
            i += 1
    return ''.join(result)

def encode_str(s, k2h):
    converted = apply_table(s, k2h) if k2h else s
    for enc in (ENC_PRI, ENC_FB):
        try:
            return converted.encode(enc)
        except (UnicodeEncodeError, LookupError):
            pass
    raise ValueError(f"인코딩 실패: {converted!r}  (원본: {s!r})")

# ── extract ───────────────────────────────────

def cmd_extract(bin_path, txt_path):
    data = open(bin_path, 'rb').read()
    ptr_base, _ = parse_header(data)
    offsets, _  = load_ptrs(data, ptr_base)
    strings     = read_strings(data, offsets)

    with open(txt_path, 'w', encoding='utf-8') as f:
        for i, s in enumerate(strings):
            f.write(f'//[{i:02d}]\n{s}\n')

    print(f"[extract] {len(strings)}개 → {txt_path}")
    for i, s in enumerate(strings):
        print(f"  [{i:02d}] {s!r}")

# ── import ────────────────────────────────────

def parse_txt(path):
    entries, cur_idx, cur_lines = {}, None, []
    for line in open(path, 'r', encoding='utf-8'):
        s = line.rstrip('\n')
        if s.startswith('//[') and ']' in s:
            if cur_idx is not None:
                entries[cur_idx] = '\n'.join(cur_lines)
            try:
                cur_idx = int(s[3:s.index(']')])
            except ValueError:
                cur_idx = None
            cur_lines = []
        elif cur_idx is not None:
            cur_lines.append(s)
    if cur_idx is not None:
        entries[cur_idx] = '\n'.join(cur_lines)
    return entries

def cmd_import(orig_bin, txt_path, out_bin, table_hint=None):
    data = open(orig_bin, 'rb').read()
    ptr_base, _  = parse_header(data)
    offsets, str_start = load_ptrs(data, ptr_base)
    orig_strs    = read_strings(data, offsets)
    n            = len(offsets)

    k2h     = auto_load_table(table_hint)
    entries = parse_txt(txt_path)

    new_str  = bytearray()
    new_pvals = []
    for i in range(n):
        real = len(new_str) + str_start
        new_pvals.append(real - ptr_base)
        text = entries.get(i, orig_strs[i])
        try:
            enc = encode_str(text, k2h)
        except ValueError as e:
            print(f"[오류] [{i:02d}] {e} → 원본 유지")
            off = offsets[i]
            try: end = data.index(b'\x00', off)
            except ValueError: end = len(data)
            enc = data[off:end]
        new_str += enc + b'\x00'

    gap = data[ptr_base + n*4 : str_start]
    new_payload = n*4 + len(gap) + len(new_str)

    out = bytearray()
    out += data[0x00:0x04]
    out += data[0x04:0x08]
    out += struct.pack('<I', new_payload)
    out += data[0x0c:0x10]
    for pv in new_pvals:
        out += struct.pack('<I', pv)
    out += gap
    out += new_str

    open(out_bin, 'wb').write(out)

    print(f"\n[import] → {out_bin}  ({len(data)} → {len(out)} bytes)")
    for i in range(n):
        t = entries.get(i, orig_strs[i])
        flag = '  ← 변경' if t != orig_strs[i] else ''
        print(f"  [{i:02d}] {t!r}{flag}")

# ── CLI ───────────────────────────────────────

def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__); sys.exit(1)

    cmd, table_hint = args[0].lower(), None
    if '--table' in args:
        ti = args.index('--table')
        if ti+1 < len(args):
            table_hint = args[ti+1]
            args = args[:ti] + args[ti+2:]

    if cmd == 'extract' and len(args) >= 3:
        cmd_extract(args[1], args[2])
    elif cmd == 'import' and len(args) >= 4:
        cmd_import(args[1], args[2], args[3], table_hint)
    else:
        print(__doc__); sys.exit(1)

if __name__ == '__main__':
    main()
