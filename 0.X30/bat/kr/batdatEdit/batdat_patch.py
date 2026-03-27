#!/usr/bin/env python3
"""
batdat_patch.py  —  Xenosaga III  batdat.bin  인플레이스 패치 툴

원본 파일 구조(파일 크기, 섹션 오프셋 테이블)를 완전히 유지하면서
JSON에서 변경된 필드만 수정합니다.

동작 방식:
  변경된 엔트리가 있는 섹션은 pool을 섹션 단위로 재구성합니다.
    - 변경된 엔트리 → ko 바이트
    - 변경 없는 엔트리 → 원본 바이트 그대로
    - pool 재구성 후 원본 pool 크기보다 작으면 NUL 패딩
    - pool 재구성 후 원본 pool 크기 초과 → 오류 (번역문 길이 초과)

  파일 크기, 섹션 오프셋 테이블, 스탯 데이터는 일절 건드리지 않습니다.

사용법:
  python batdat_patch.py <batdat.bin> <translated.json> [output.bin] [char_table.json]

char_table.json 자동 탐지:
  translated.json 과 같은 디렉터리에 char_table.json 이 있으면 자동 로드.
"""

import sys
import json
import struct
import os
from pathlib import Path

ENCODING = 'euc-jis-2004'


# ─────────────────────────────────────────────────────────────
# 유틸
# ─────────────────────────────────────────────────────────────
def load_char_table(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    with open(path, encoding='utf-8-sig') as f:
        obj = json.load(f)
    return obj.get('replace-table', {})


def apply_char_table(text: str, table: dict) -> str:
    if not table:
        return text
    return ''.join(table.get(ch, ch) for ch in text)


MENU_SITA_TAG = '[menu_sita]'

def apply_menu_sita(text: str) -> str:
    """문자열 끝에 [menu_sita]가 있으면 태그를 제거하고 반각 공백을 、로 치환"""
    if text.endswith(MENU_SITA_TAG):
        text = text[:-len(MENU_SITA_TAG)]
        text = text.replace(' ', '、')
    return text


def encode_str(text: str) -> bytes:
    return text.encode(ENCODING, errors='replace')


def read_nul_str(data: bytearray, abs_addr: int) -> bytes:
    """절대 주소에서 NUL 종단 바이트열 (NUL 미포함)"""
    nul = data.find(b'\x00', abs_addr)
    return bytes(data[abs_addr:nul]) if nul > abs_addr else b''


# ─────────────────────────────────────────────────────────────
# PATCH
# ─────────────────────────────────────────────────────────────
def cmd_patch(bin_path: str, json_path: str, out_path: str,
              char_table_path: str | None = None):

    buf = bytearray(open(bin_path, 'rb').read())
    filesize_orig = len(buf)

    with open(json_path, encoding='utf-8') as f:
        trans = json.load(f)

    # char_table 로드
    char_table = {}
    if char_table_path:
        char_table = load_char_table(char_table_path)
        print(f'[patch] char_table: {char_table_path}  ({len(char_table)}개 매핑)')
    else:
        auto = Path(json_path).parent / 'char_table.json'
        if auto.exists():
            char_table = load_char_table(str(auto))
            print(f'[patch] char_table 자동 로드: {auto}  ({len(char_table)}개 매핑)')

    print(f'[patch] {bin_path}  ({filesize_orig:,} bytes)')
    print()

    # 헤더 오프셋 테이블
    header_bases = [struct.unpack_from('<I', buf, 0x0008 + i * 4)[0] for i in range(28)]
    base_to_hidx = {v: i for i, v in enumerate(header_bases)}

    stats = {'sec_patched': 0, 'field_patched': 0, 'skip': 0, 'error': 0}
    errors = []

    for label, sec in trans.items():
        sec_type = sec['sec_type']
        base     = sec['base']
        hdr_off  = sec['hdr_off']
        stride   = sec['stride']
        entries  = sec['entries']

        # ── 섹션의 pool 범위 계산 ─────────────────────────────
        first_ptr     = struct.unpack_from('<H', buf, base + hdr_off)[0]
        pool_start    = base + first_ptr          # pool 절대 시작
        hidx          = base_to_hidx.get(base)
        if hidx is None:
            continue
        pool_end      = header_bases[hidx + 1] if hidx + 1 < len(header_bases) else filesize_orig
        pool_size     = pool_end - pool_start     # 원본 pool 크기 (불변)

        # ── 이 섹션에 변경된 엔트리가 있는지 먼저 확인 ────────
        def get_fields(e):
            if sec_type == 'name_only':
                return [
                    (e.get('jp',''),      e.get('ko',''),
                     e['ptr_pos'],        e['name_ptr'], 'name'),
                ]
            else:
                return [
                    (e.get('jp_name',''), e.get('ko_name',''),
                     e['ptr_pos'],        e['name_ptr'], 'name'),
                    (e.get('jp_desc',''), e.get('ko_desc',''),
                     e['ptr_pos'] + 2,   e['desc_ptr'], 'desc'),
                ]

        has_change = False
        for e in entries:
            for jp, ko, _, _, _ in get_fields(e):
                ko_f = apply_menu_sita(apply_char_table(ko, char_table))
                if encode_str(jp) != encode_str(ko_f):
                    has_change = True
                    break
            if has_change:
                break

        if not has_change:
            stats['skip'] += len(entries)
            continue

        # ── pool 재구성 ──────────────────────────────────────
        # 변경된 엔트리는 ko, 나머지는 원본 바이트 그대로 복사
        new_pool      = bytearray()
        new_ptrs      = []   # (ptr_file_pos, new_rel) 목록

        ok = True
        for e in entries:
            fields = get_fields(e)
            entry_parts = []   # (ptr_file_pos, new_rel, bytes_to_write)

            for jp, ko, ptr_file_pos, str_rel, field_label in fields:
                ko_f     = apply_menu_sita(apply_char_table(ko, char_table))
                jp_bytes = encode_str(jp)
                ko_bytes = encode_str(ko_f)

                if jp_bytes == ko_bytes:
                    # 변경 없음 → 원본 바이트 그대로
                    orig_raw = read_nul_str(buf, base + str_rel)
                    chunk    = orig_raw + b'\x00'
                else:
                    # 변경 있음 → ko 바이트
                    chunk = ko_bytes + b'\x00'
                    stats['field_patched'] += 1

                new_rel = pool_start - base + len(new_pool)
                entry_parts.append((ptr_file_pos, new_rel))
                new_pool += chunk

            new_ptrs.extend(entry_parts)

        # pool 크기 초과 검사
        if len(new_pool) > pool_size:
            over = len(new_pool) - pool_size
            msg = (f'[{label}] pool 크기 초과: '
                   f'번역 pool {len(new_pool)}B > 원본 pool {pool_size}B (+{over}B)\n'
                   f'  이 섹션은 패치하지 않았습니다.\n'
                   f'  해결 방법: 이 섹션의 번역문 총합을 {over}바이트 줄여주세요.')
            errors.append(msg)
            stats['error'] += 1
            continue

        # ── pool 쓰기 (원본 크기 유지, 남는 공간은 NUL) ───────
        padding = b'\x00' * (pool_size - len(new_pool))
        buf[pool_start : pool_end] = new_pool + padding

        # ── 포인터 업데이트 ───────────────────────────────────
        for ptr_file_pos, new_rel in new_ptrs:
            struct.pack_into('<H', buf, ptr_file_pos, new_rel)

        stats['sec_patched'] += 1
        saved = pool_size - len(new_pool)
        print(f'  [{label:<14}] pool 재구성: {pool_size}B '
              f'(번역 {len(new_pool)}B + NUL패딩 {saved}B)')

    # 파일 크기 불변 확인
    assert len(buf) == filesize_orig, \
        f'파일 크기 변화! {len(buf)} != {filesize_orig}'

    with open(out_path, 'wb') as f:
        f.write(buf)

    print()
    print(f'[patch] 완료 → {out_path}')
    print(f'  파일 크기: {len(buf):,} bytes (원본과 동일 ✓)')
    print(f'  패치된 섹션: {stats["sec_patched"]}개  '
          f'패치된 필드: {stats["field_patched"]}개  '
          f'오류: {stats["error"]}개')

    if errors:
        print()
        print('=== 패치 실패 섹션 ===')
        for msg in errors:
            print(msg)


# ─────────────────────────────────────────────────────────────
# main
# ─────────────────────────────────────────────────────────────
def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    bin_path  = sys.argv[1]
    json_path = sys.argv[2]
    out_path  = sys.argv[3] if len(sys.argv) > 3 else 'batdat_patched.bin'
    char_tbl  = sys.argv[4] if len(sys.argv) > 4 else None

    cmd_patch(bin_path, json_path, out_path, char_tbl)


if __name__ == '__main__':
    main()
