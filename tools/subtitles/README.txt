X31 / X32 자막 작업
==================

저장소 구조 (jp와 kr 모두 UTF-8)
  jp: 일본판 원본 자막. 번역 시 참고용으로 보존한다.
  kr: 한글로 수정할 번역 작업본. 아직 번역 전이면 일본어일 수 있다.
  디스크 1: 1.X31/evt/{jp,kr} 각 35개, 1.X31/mov/{jp,kr} 각 13개
  디스크 2: 2.X32/evt/{jp,kr} 각 18개, 2.X32/mov/{jp,kr} 각 15개
  파일명은 jp와 kr에서 동일하다. 내용은 자동 번역하지 않는다.

각 디스크 폴더의 BAT
  1.Decode_UTF8.bat
    최초 준비용. jp 원본이 게임 인코딩이면 UTF-8로 변환한다.
    이미 UTF-8인 jp는 그대로 두고, kr에 없는 작업본만 만든다.
    기존 kr는 덮어쓰지 않는다. UTF-8이 아니면 오류로 중단한다.
    일본어 원문 내용은 보존하며, 한자를 한글로 역치환하지 않는다.
    현재는 양쪽 디스크 모두 준비되어 있어 다시 실행할 필요가 없다.

  2.Encode_and_Copy.bat
    해당 디스크의 kr 작업 TXT 전체를 읽어 한글을 치환한 다음
    EUC-JIS-2004로 인코딩하고 전체 검증 후 외부 작업 폴더에 반영한다.
    evt/kr -> X31_UNPACKED 또는 X32_UNPACKED의 evt/jp
    mov/kr -> X31_UNPACKED 또는 X32_UNPACKED의 mov/jp
    게임 경로는 한글판 패치에서도 jp가 맞다. kr 폴더를 만들지 않는다.
    저장소 TXT는 수정하지 않는다. 별도 재인코딩 사본도 쌓지 않는다.
    이미 같은 결과인 외부 파일은 쓰지 않고 건너뛴다.

  BAT에 --check를 붙이면 저장/복사 없이 검증만 한다.
  Python 3.10 이상, 표준 라이브러리만 필요하다.

ROM 작업 폴더
  C:\Users\JO\Desktop\XENO_ARC\Xenosaga\Xenosaga3
  위치가 바뀌면 각 2.Encode_and_Copy.bat의 ROM_ROOT만 수정한다.
  자막 BAT는 ISO를 만들지 않는다. 복사 성공 후 ROM 폴더의
  1.RebuildDisc1.bat 또는 2.RebuildDisc2.bat를 실행한다.
  ROM 빌더 자체는 XS3KOR, codex-lab에 의존하지 않는다.

치환표 및 보존
  기존 0.X30/cf/kr/XENOSAGA KOR-JPN.json을 직접 읽는다.
  누락된 한글, 인코딩 불가능 문자, 왕복 변환 불일치, 잘못된 대상 경로는
  복사 전에 오류로 중단한다. 문자 누락/대체, 문장 부호 정규화는 없다.
  타이밍, 탭, 공백, 줄바꿈, 주석, 리터럴 \n, 루비/서식 명령도 유지한다.
  UTF-8 BOM은 게임용 출력에 넣지 않는다.
  외부 iso-data/LBA1.txt 또는 LBA2.txt로 디스크 등록 여부를 확인한다.
  X31에 섞여 있던 디스크 2 EVT 중복 18개는 삭제했다.
  디스크 2 자막은 2.X32/evt/kr 또는 mov/kr에서만 작업한다.
  다른 디스크의 TXT가 kr에 들어오면 오류로 중단한다.

중단/실패
  파일마다 .pending에 기록/검증 후 교체한다. 인코딩 오류가 하나라도
  있으면 복사를 시작하지 않는다. 쓰기 도중 디스크/권한 오류가 나면
  일부 파일만 반영될 수 있으므로 ISO를 빌드하지 말고 원인을 해결한다.
  남은 .pending은 해당 파일을 확인 후 정리하고 BAT를 다시 실행한다.

테스트
  python -X utf8 -B -m unittest discover -s tools/subtitles -p "test_*.py"
