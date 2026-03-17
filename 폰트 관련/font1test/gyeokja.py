from PIL import Image, ImageDraw

def draw_grid_on_sheet(input_path, output_name):
    # 1. 원본 이미지 불러오기
    try:
        img = Image.open(input_path).convert('RGB') # 선을 색상 있게 그리려면 RGB 변환
    except:
        print("이미지 파일을 열 수 없습니다.")
        return

    draw = ImageDraw.Draw(img)
    width, height = img.size

    # 2. 규격 설정 (기존 규격: 20x24)
    glyph_w, glyph_h = 20, 24
    
    # 3. 가로선 그리기 (행 구분)
    for y in range(0, height + 1, glyph_h):
        draw.line([(0, y), (width, y)], fill=(100, 100, 100), width=1) # 회색 선

    # 4. 세로선 그리기 (열 구분)
    for x in range(0, width + 1, glyph_w):
        draw.line([(x, 0), (x, height)], fill=(100, 100, 100), width=1) # 회색 선

    # 5. 결과 저장 및 확인
    img.save(output_name)
    img.show()
    print(f"격자선이 추가된 시트 저장 완료: {output_name}")

if __name__ == "__main__":
    # 파일명이 'font1_blue_jpn.png'라고 가정합니다.
    draw_grid_on_sheet("font1_blue_jpn.png", "font1_blue_jpn_grid.png")