import numpy as np
from PIL import Image
import os

def extract_channels(file_name):
    # 설정값 (분석 결과 기반)
    width = 20
    height = 24
    num_glyphs = 1024
    expected_size = width * height * num_glyphs

    # 1. 파일 읽기
    if not os.path.exists(file_name):
        print(f"오류: {file_name} 파일을 찾을 수 없습니다.")
        return

    with open(file_name, 'rb') as f:
        # 데이터가 더 크더라도 이미지 영역(491,520 바이트)만 읽음
        data = np.frombuffer(f.read(expected_size), dtype=np.uint8)

    # 2. 픽셀별 채널 분리 (r2g2b2p2 방식)
    # R: bits 0-1, G: bits 2-3, B: bits 4-5
    red = ((data >> 0) & 0x03) * 85         # 0~3 단계를 0~255로 변환
    green = ((data >> 2) & 0x03) * 85
    blue = ((data >> 4) & 0x03) * 85
    alpha = ((data >> 6) & 0x03) * 85

    # 3. 이미지 저장 (보기 편하게 32x32 그리드로 재배열)
    grid_w = 32
    grid_h = 32
    
    channels = [('Red', red), ('Green', green), ('Blue', blue), ('Alpha', alpha)]
    
    for name, channel_data in channels:
        # 1차원 데이터를 (1024, 24, 20) 형태로 변형
        glyphs = channel_data.reshape((num_glyphs, height, width))
        
        # 큰 캔버스 생성 (640 x 768 px)
        canvas = Image.new('L', (grid_w * width, grid_h * height))
        
        for i in range(num_glyphs):
            row = i // grid_w
            col = i % grid_w
            glyph_img = Image.fromarray(glyphs[i])
            canvas.paste(glyph_img, (col * width, row * height))
        
        output_file = f"font1_{name.lower()}.png"
        canvas.save(output_file)
        print(f"성공: {output_file} 저장 완료.")

if __name__ == "__main__":
    extract_channels('font1.bin')