import numpy as np
from PIL import Image, ImageDraw, ImageFont

def generate_kor_font_sheet_final_v2(output_name, char_list, font_size=16, stretch_ratio=1.15):
    glyph_w, glyph_h = 20, 24
    grid_w, grid_h = 32, 32
    canvas = Image.new('L', (glyph_w * grid_w, glyph_h * grid_h), color=0)
    
    try:
        font_path = r"Pretendard-Medium.otf"
        font = ImageFont.truetype(font_path, font_size)
    except:
        print("폰트 파일을 찾을 수 없습니다.")
        return

    fixed_y_pos = 19 

    for i, char in enumerate(char_list):
        if i >= grid_w * grid_h: break
        
        temp_w = 40
        temp_img = Image.new('L', (temp_w, glyph_h), color=0)
        temp_draw = ImageDraw.Draw(temp_img)
        temp_draw.text((10, fixed_y_pos), char, font=font, fill=255, anchor="ls")

        bbox = temp_img.getbbox()
        if bbox:
            # 세로는 0~24 전체 유지, 가로는 글자 영역(bbox)만 추출
            char_strip = temp_img.crop((bbox[0], 0, bbox[2], glyph_h))
            orig_char_w = bbox[2] - bbox[0]
            
            # [핵심 수정] 강제 18px이 아니라, 원래 폭의 stretch_ratio만큼만 확장
            new_w = int(orig_char_w * stretch_ratio)
            
            # 단, 칸 너비(20px)를 넘지 않도록 최대치 제한 (보통 18px 권장)
            new_w = min(new_w, 18)
            
            char_stretched = char_strip.resize((new_w, glyph_h), Image.Resampling.LANCZOS)
            
            col, row = i % grid_w, i // grid_w
            # 늘어난 폭에 맞춰 다시 중앙 정렬
            paste_x = (col * glyph_w) + (glyph_w - new_w) // 2
            paste_y = (row * glyph_h)
            
            canvas.paste(char_stretched, (paste_x, paste_y))

    print(f"생성 완료: {output_name} (비율: {stretch_ratio})")
    canvas.save(output_name)
    canvas.show()

if __name__ == "__main__":
    with open('hangul_2048_final.txt', 'r', encoding='utf-8') as f:
        full_chars = f.read()
    # 1.15배 정도로 살짝만 늘려보고, 너무 좁으면 1.2로 조정하세요.
    generate_kor_font_sheet_final_v2("font1_pro_ratio.png", full_chars[:1024], stretch_ratio=1.2, font_size=17)