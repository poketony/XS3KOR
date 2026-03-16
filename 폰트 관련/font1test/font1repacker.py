import numpy as np
from PIL import Image
import os

def pack_channels(output_file='font1_rebuild.bin'):
    # 설정값 (추출 시와 동일하게 설정)
    width = 20
    height = 24
    num_glyphs = 1024
    grid_w = 32
    
    # 1. 4개의 채널 이미지 로드
    channel_names = ['red', 'green', 'blue', 'alpha']
    images = {}
    
    print("이미지 파일을 읽는 중...")
    for name in channel_names:
        file_path = f"font1_{name}.png"
        if not os.path.exists(file_path):
            print(f"오류: {file_path} 파일이 없습니다.")
            return
        # 그레이스케일(L) 모드로 읽기
        images[name] = np.array(Image.open(file_path).convert('L'))

    # 2. 각 이미지에서 글자별 데이터 다시 추출 및 비트 변환
    # (0~255) 값을 (0~3) 범위로 복원. +42는 반올림 효과를 위한 오프셋입니다.
    data_2bit = {name: (images[name].astype(np.uint16) + 42) // 85 for name in channel_names}

    # 최종 바이너리 데이터를 담을 배열 생성
    rebuilt_data = np.zeros(num_glyphs * height * width, dtype=np.uint8)

    print("비트 결합 및 바이너리 생성 중...")
    
    idx = 0
    for i in range(num_glyphs):
        # 그리드 상의 위치 계산
        row = i // grid_w
        col = i % grid_w
        
        y_start = row * height
        x_start = col * width
        
        # 각 채널에서 20x24 글자 영역 추출 및 1차원으로 펼치기
        r = data_2bit['red'][y_start:y_start+height, x_start:x_start+width].flatten()
        g = data_2bit['green'][y_start:y_start+height, x_start:x_start+width].flatten()
        b = data_2bit['blue'][y_start:y_start+height, x_start:x_start+width].flatten()
        a = data_2bit['alpha'][y_start:y_start+height, x_start:x_start+width].flatten()

        # 3. 비트 결합 (AABB GGRR)
        # Red: bits 0-1, Green: bits 2-3, Blue: bits 4-5, Alpha: bits 6-7
        packed = (r & 0x03) | \
                 ((g & 0x03) << 2) | \
                 ((b & 0x03) << 4) | \
                 ((a & 0x03) << 6)
        
        rebuilt_data[idx : idx + (width * height)] = packed
        idx += (width * height)

    # 4. 파일 저장
    with open(output_file, 'wb') as f:
        f.write(rebuilt_data.tobytes())
    
    print(f"성공: {output_file} 파일이 생성되었습니다.")
    print(f"최종 크기: {len(rebuilt_data)} 바이트")

if __name__ == "__main__":
    pack_channels()