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

import struct, sys, json, os, re
try:
    from .output import write_output
except ImportError:
    from output import write_output

ENC_PRI = 'euc_jis_2004'

# ── 파싱 ──────────────────────────────────────

def parse_header(data):
    if len(data) < 16:
        raise ValueError('Truncated njDBcommon header')
    ptr_base     = struct.unpack_from('<I', data, 0x04)[0]
    payload_size = struct.unpack_from('<I', data, 0x08)[0]
    if ptr_base < 16 or ptr_base % 4 or payload_size < 4 or ptr_base + payload_size != len(data):
        raise ValueError('Invalid njDBcommon payload bounds')
    return ptr_base, payload_size

def load_ptrs(data, ptr_base):
    first_pval = struct.unpack_from('<I', data, ptr_base)[0]
    str_start  = first_pval + ptr_base
    if first_pval < 4 or first_pval % 4 or str_start >= len(data):
        raise ValueError('Invalid njDBcommon pointer table')
    n          = (str_start - ptr_base) // 4
    offsets    = [struct.unpack_from('<I', data, ptr_base + i*4)[0] + ptr_base for i in range(n)]
    if any(not str_start <= off < len(data) for off in offsets):
        raise ValueError('njDBcommon pointer outside string pool')
    return offsets, str_start

def decode_str(raw):
    return raw.decode(ENC_PRI)

def read_strings(data, offsets):
    result = []
    for off in offsets:
        end = data.index(b'\x00', off)
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
    if '\x00' in converted:
        raise ValueError('Embedded NUL in njDBcommon string')
    return converted.encode(ENC_PRI)

# ── extract ───────────────────────────────────

def cmd_extract(bin_path, txt_path):
    with open(bin_path, 'rb') as stream:
        data = stream.read()
    write_output(txt_path, extract_text(data).encode('utf-8'), (bin_path,), overwrite=False)
    print(f'Extract complete: {txt_path}')


def extract_text(data):
    ptr_base, _ = parse_header(data)
    offsets, _  = load_ptrs(data, ptr_base)
    strings     = read_strings(data, offsets)
    return ''.join(f'//[{i:02d}]\n{s}\n' for i, s in enumerate(strings))

# ── import ────────────────────────────────────

def parse_text(content, count):
    content = content.removeprefix('\ufeff').replace('\r\n', '\n')
    markers = list(re.finditer(r'^//\[(\d+)\](?:\n|$)', content, re.MULTILINE))
    if not markers or content[:markers[0].start()].strip():
        raise ValueError('Missing njDBcommon record marker')
    entries = {}
    for i, marker in enumerate(markers):
        index = int(marker[1])
        if index >= count or index in entries:
            raise ValueError(f'Unknown or duplicate njDBcommon ID: {index}')
        end = markers[i+1].start() if i+1 < len(markers) else len(content)
        entries[index] = content[marker.end():end].removesuffix('\n')
    if len(entries) != count:
        raise ValueError(f'Missing njDBcommon IDs: expected {count}, got {len(entries)}')
    return entries


def rebuild(data, content, charmap):
    ptr_base, _  = parse_header(data)
    offsets, str_start = load_ptrs(data, ptr_base)
    orig_strs    = read_strings(data, offsets)
    n            = len(offsets)
    entries = parse_text(content, n)
    original_raw = [data[off:data.index(b'\0', off)] for off in offsets]
    expected = [original_raw[i] if entries[i] == orig_strs[i] else encode_str(entries[i], charmap) for i in range(n)]
    if expected == original_raw:
        return bytes(data)
    new_str  = bytearray()
    new_pvals = []
    for i in range(n):
        real = len(new_str) + str_start
        new_pvals.append(real - ptr_base)
        new_str += expected[i] + b'\x00'

    gap = data[ptr_base + n*4 : str_start]
    new_payload = n*4 + len(gap) + len(new_str)

    out = bytearray(data[:ptr_base])
    struct.pack_into('<I', out, 0x08, new_payload)
    for pv in new_pvals:
        out += struct.pack('<I', pv)
    out += gap
    out += new_str

    result = bytes(out)
    parse_header(result)
    actual_offsets, _ = load_ptrs(result, ptr_base)
    actual_raw = [result[off:result.index(b'\0', off)] for off in actual_offsets]
    if actual_raw != expected:
        raise ValueError('njDBcommon result verification failed')
    return result


def cmd_import(orig_bin, txt_path, out_bin, table_hint=None):
    with open(orig_bin, 'rb') as stream:
        data = stream.read()
    with open(txt_path, encoding='utf-8-sig') as stream:
        content = stream.read()
    result = rebuild(data, content, auto_load_table(table_hint))
    inputs = (orig_bin, txt_path) + ((table_hint,) if table_hint else ())
    write_output(out_bin, result, inputs)
    print(f'Import complete: {out_bin}')

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
