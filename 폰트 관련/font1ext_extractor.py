import numpy as np
from PIL import Image
import os

# ============================================================
# font1_ext.bin 구조 (분석 결과)
# ============================================================
# [0x000 ~ 0x3FF] 헤더 1024바이트 = 256글리프 * 4바이트
#   각 4바이트: (even_left, even_adv, odd_left, odd_adv)
#   even = 짝수 행(0,2,4...14)으로 구성된 글리프
#   odd  = 홀수 행(1,3,5...15)으로 구성된 글리프
#
# [0x400 ~ 0xBFF] 비트맵 2048바이트 (= ansi.raw)
#   셀 크기: 8px(1바이트/row) x 16행
#   128셀이 32열 x 4행 그리드로 배치
#   각 셀 안에 두 글리프가 홀짝 행으로 인터리브:
#     짝수 행(row 0,2,4,6,8,10,12,14) → 글리프 A (8행짜리)
#     홀수 행(row 1,3,5,7,9,11,13,15) → 글리프 B (8행짜리)
#   → 실제 글리프 수: 128셀 * 2 = 256글리프
#
# 비트맵 인덱싱:
#   셀 gi (0~127): col = gi % 32, row = gi // 32
#   짝수 글리프: 인덱스 gi*2     (= gi의 짝수 행)
#   홀수 글리프: 인덱스 gi*2 + 1 (= gi의 홀수 행)
#
# 메트릭 (left, adv):
#   left = 글리프 비트맵 내 픽셀 시작 x (left bearing)
#   adv  = advance width (렌더링 시 오른쪽으로 이동할 픽셀 수)
#   실제 표시 픽셀: bits[left : adv]
# ============================================================

def extract_glyphs(input_file='font1_ext.bin', output_dir='font1_ext_glyphs'):
    if not os.path.exists(input_file):
        print(f"오류: {input_file} 파일을 찾을 수 없습니다.")
        return

    with open(input_file, 'rb') as f:
        data = f.read()

    assert len(data) == 3072, f"예상 크기 3072바이트, 실제 {len(data)}바이트"

    header = data[:1024]
    bitmap = data[1024:]  # 2048바이트

    os.makedirs(output_dir, exist_ok=True)

    # 비트맵 → 256x64 픽셀 시트로 언팩 (1bit/pixel → 0 or 255)
    bits = []
    for byte in bitmap:
        for bit in range(7, -1, -1):
            bits.append(255 if (byte >> bit) & 1 else 0)

    sheet = Image.new('L', (256, 64))
    sheet.putdata(bits)

    CELL_W, CELL_H = 8, 16
    COLS = 32

    # 256글리프 추출
    glyphs = {}  # glyph_index → (pixels 8x8, left, adv)

    for cell_i in range(128):
        col = cell_i % COLS
        row = cell_i // COLS
        x0 = col * CELL_W
        y0 = row * CELL_H

        # 헤더에서 메트릭 읽기
        even_left = header[cell_i * 4 + 0]
        even_adv  = header[cell_i * 4 + 1]
        odd_left  = header[cell_i * 4 + 2]
        odd_adv   = header[cell_i * 4 + 3]

        # 짝수 행 글리프 (8행)
        even_rows = []
        for r in range(0, CELL_H, 2):  # 0,2,4,6,8,10,12,14
            row_pixels = [sheet.getpixel((x0 + px, y0 + r)) for px in range(CELL_W)]
            even_rows.append(row_pixels)

        # 홀수 행 글리프 (8행)
        odd_rows = []
        for r in range(1, CELL_H, 2):  # 1,3,5,7,9,11,13,15
            row_pixels = [sheet.getpixel((x0 + px, y0 + r)) for px in range(CELL_W)]
            odd_rows.append(row_pixels)

        glyphs[cell_i * 2]     = (even_rows, even_left, even_adv)
        glyphs[cell_i * 2 + 1] = (odd_rows,  odd_left,  odd_adv)

    # 전체 글리프 시트 이미지 저장 (짝수/홀수 각각)
    for layer, label in [(0, 'even'), (1, 'odd')]:
        GRID_COLS = 32
        GRID_ROWS = 4
        SCALE = 4
        canvas = Image.new('L', (GRID_COLS * CELL_W, GRID_ROWS * 8), 0)

        for cell_i in range(128):
            gi = cell_i * 2 + layer
            rows, left, adv = glyphs[gi]
            col = cell_i % GRID_COLS
            row = cell_i // GRID_COLS
            x0 = col * CELL_W
            y0 = row * 8
            for ry, row_pixels in enumerate(rows):
                for px, pv in enumerate(row_pixels):
                    canvas.putpixel((x0 + px, y0 + ry), pv)

        canvas_big = canvas.resize((canvas.width * SCALE, canvas.height * SCALE), Image.NEAREST)
        out_path = os.path.join(output_dir, f'sheet_{label}.png')
        canvas_big.save(out_path)
        print(f"저장: {out_path}")

    # 개별 글리프 PNG 저장 (크롭된 버전)
    SCALE = 4
    for gi in range(256):
        rows, left, adv = glyphs[gi]
        w = max(adv - left, 1)
        img = Image.new('L', (w, 8), 0)
        for ry, row_pixels in enumerate(rows):
            for px in range(w):
                if left + px < CELL_W:
                    img.putpixel((px, ry), row_pixels[left + px])
        img_big = img.resize((w * SCALE, 8 * SCALE), Image.NEAREST)
        img_big.save(os.path.join(output_dir, f'glyph_{gi:03d}.png'))

    print(f"\n완료: 글리프 256개 → {output_dir}/")
    print(f"  sheet_even.png : 짝수 레이어 전체 시트")
    print(f"  sheet_odd.png  : 홀수 레이어 전체 시트")
    print(f"  glyph_000.png ~ glyph_255.png : 개별 글리프 (크롭)")


def print_metrics(input_file='font1_ext.bin'):
    """헤더 메트릭 테이블 출력"""
    with open(input_file, 'rb') as f:
        data = f.read()
    header = data[:1024]

    print(f"{'cell':>4} {'gi_even':>7} {'el':>3} {'ea':>3} | {'gi_odd':>6} {'ol':>3} {'oa':>3}")
    print("-" * 40)
    for i in range(128):
        el = header[i*4+0]
        ea = header[i*4+1]
        ol = header[i*4+2]
        oa = header[i*4+3]
        print(f"{i:4d}  {i*2:7d}  {el:3d}  {ea:3d} | {i*2+1:6d}  {ol:3d}  {oa:3d}")


if __name__ == '__main__':
    extract_glyphs('font1_ext.bin', 'font1_ext_glyphs')
    # print_metrics('font1_ext.bin')  # 메트릭 테이블 출력하려면 주석 해제
