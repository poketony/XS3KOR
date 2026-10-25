제노사가 III 실행 파일 번역 도구
==============================

사용 순서
1. 저장소 discmetadata/SLPS.txt 또는 discmetadata/OV04.txt를 UTF-8로 편집한다.
   주소|원문 바이트/허용 바이트|본문 중 두 번째 | 뒤만 바꾼다.
2. 같은 폴더의 discmetadata/Build_elf.bat를 실행한다.
   두 TXT를 직접 읽어 전체 검증 후 두 디스크의 외부 메타데이터 폴더에 자동 복사한다.
   별도 번역 사본이나 로컬 .new 산출물은 만들지 않는다. 같은 결과는 다시 쓰지 않는다.
3. 복사가 성공하면 ROM 작업 폴더의 1.RebuildDisc1.bat / 2.RebuildDisc2.bat로 ISO를 만든다.
   ELF BAT 자체는 ISO를 만들지 않는다.

자동 적용 위치
- discmetadata/SLPS.txt -> Xenosaga3/disc1metadata/SLPS_256.40
- 같은 SLPS.txt -> Xenosaga3/disc2metadata/SLPS_256.41
- discmetadata/OV04.txt -> 두 디스크의 discNmetadata/OV04.OVL
- 기본 외부 경로: C:\Users\JO\Desktop\XENO_ARC\Xenosaga\Xenosaga3
  경로가 바뀌면 discmetadata/Build_elf.bat의 ROM_ROOT만 수정한다.

원본 두 디스크의 실행 파일은 파일명만 다르고 바이트는 같다.
따라서 저장소는 discmetadata 한 곳의 번역본만 관리하고 tools/elf/edit에 사본을 두지 않는다.
discmetadata/SLPS_256.40은 기존 파일을 보존한 것이며 빌드 입력/출력이 아니다.
원본 바이너리는 tools/elf/original, 일본어 대조 TXT는 tools/elf/reference에 있다.
외부 ROM 폴더의 disc1metadata/disc2metadata 이름은 변경하지 않는다.
없는 외부 disc2metadata는 검증 성공 후 만들며 SLPS와 OV04만 넣는다.
SYSTEM.CNF, OV01/OV02, IOP, 폰트와 다른 파일은 수정하지 않는다.
ROM 빌더는 기존처럼 자기 폴더의 정식 파일명만 읽는다. 저장소를 읽는 의존성은 없다.
정식 파일이 없으면 ROM 빌더 자체의 일본판 기준 파일을 사용한다.

수동 실행과 드롭
- Build_elf.bat는 기본적으로 두 작업 TXT를 모두 읽는다. TXT를 드롭하면 전달한 대상만
  두 디스크에 적용하며 두 종류를 함께 드롭할 수도 있다. 같은 대상을 두 번 주면 오류다.
- 드롭 TXT는 discmetadata 또는 tools/elf 안에 있어야 한다. # asset: 헤더로 구분한다.
- 없는 입력, 잘못된 헤더, 잘못된 본문은 기본 TXT로 대체하지 않는다. 입력 TXT는 수정하지 않는다.
- Build_elf.bat --check는 빌드와 외부 대상 검증만 한다. 파일/폴더를 생성하지 않는다.
  XS3_NO_PAUSE=1이면 마지막 키 입력을 생략한다.
- 도구 폴더에서 python -X utf8 -B elf_text_tool.py build --asset OV04 --check로 개별 검사할 수 있다.
- Python CLI에서 --rom-root를 생략한 build는 기존처럼 tools/elf/output에 .new만 만든다.
  --rom-root "외부 작업 폴더"를 주면 로컬 .new 없이 외부 두 디스크에 적용한다.

기본 번역 상태
- SLPS.txt: 기존 바탕화면 실행 파일의 아이템/돈 획득 번역 3개를 보존했다.
  영상 읽기 오류 안내 1개는 일본어 원문이다.
- OV04.txt: 미니게임의 연속 골/보상/뷰 모드 문구 13개이며 아직 일본어다.
- reference/*.JP.txt: 대조용 원문. 이 파일은 build 입력이 아니다.
- 기본 SLPS 빌드 SHA-256은 바탕화면 실행 파일과 완전히 같다.
  기존 돈 획득 문구가 색상 코드 {0CC0C0C0}를 생략한 상태도 그대로 유지한다.
  해당 줄만 원문과 동일한 색상 코드를 복구하는 것도 허용한다.

규칙
- 한글 -> 동봉된 한글/한자 치환표 -> EUC-JIS-2004 순서로 인코딩한다.
- 매핑 없는 한글, 인코딩 불가 문자, 길이 초과는 오류다. 누락/절단하지 않는다.
- \n은 실제 줄바꿈 바이트 0A, \\n은 역슬래시와 n이라는 두 문자다.
  {HEX}는 원래의 제어 코드다. %s/%d, <s0>, 버튼 기호, 줄바꿈을 유지한다.
- 문장 부호를 자동 변환하지 않는다.
- OV04의 0003DDA8 행은 첫 ASCII 0을 유지해야 한다. 게임이 그 자리에 숫자를 쓴다.
  이 행은 NUL을 포함하여 정확히 12바이트를 복사하므로 본문 최대 11바이트다.
- 그 밖의 길이 제한은 원문 문자열과 바로 뒤의 확인된 8바이트 정렬 패딩까지다.
  더 긴 번역의 자동 재배치, 코드/포인터 수정은 하지 않는다.
- 누락한 행은 일본어 원문으로 돌아간다. 중복/알 수 없는 주소는 오류다.
- tools/elf/Export_elf.bat는 discmetadata에 없는 번역 TXT와 reference의 없는 대조 TXT만 생성한다.
  기존 번역 TXT를 덮어쓰거나 옛 edit 폴더에 번역 사본을 만들지 않는다.
- 자동 복사는 외부 iso-data/profile.json의 일본판 기준을 확인한다. 기존 실행 파일에 번역
  슬롯 밖의 코드/폰트/메모리카드 제목 패치가 있으면 덮어쓰지 않고 오류로 중단한다.
- 모든 입력을 검증한 뒤 .pending에 쓰고 재확인하여 .new로 바꾼다.
  자동 복사에서는 .new 대신 각 디스크의 정식 이름으로 바꾼다.
  실패한 .pending이 남아 있으면 자동 삭제하지 않고 재실행을 중단한다.
  각 파일은 개별적으로 교체된다. 도중 실패 시 모든 출력이 최신이라고 가정하지 말고,
  원인을 해결한 뒤 전체 빌드를 다시 완료한다.

분석 범위
메인 ELF와 OV01/OV02/OV04를 검사했다. 현재 편집 허용 범위는 코드 참조를 확인한
메인 4개, OV04 13개다. 모든 바이너리 문자열을 무조건 번역 대상으로 삼은 것은 아니다.
디버그 로그/테스트 메뉴/폰트 코드표/내부 파일명은 제외했다.
OV01은 메인 ELF 안의 사본과 일치하며 수정하지 않는다. OV02도 수정하지 않는다.
DISC 교체 등 외부 리소스에 있는 문구는 이 도구의 편집 대상이 아니다.
자세한 주소와 근거는 docs/ANALYSIS.txt를 참고한다.

독립성 및 보존
Python 3.10 이상과 표준 라이브러리만 사용한다. pip 설치나 Ghidra는 실행에 필요 없다.
빌드는 이 폴더의 원본/치환표/코드와 저장소 discmetadata의 번역 TXT만 읽는다.
codex-lab, XS2KOR, 원본 ISO에 런타임 의존하지 않는다.
명시적 --rom-root 전달 때만 외부 작업 폴더의 기준 자료를 검증하고 해당 SLPS/OV04를 갱신한다.
ROM 빌더 자체는 수정하지 않으며 저장소 없이 독립 실행된다.
저장소 원본/기존 실행 파일/폰트/X30/X31/X32 파일은 수정하지 않는다.
일본어 기준 파일과 치환표의 SHA-256이 달라지면 빌드를 중단한다.

검증 명령
  python -X utf8 -B elf_text_tool.py check
  python -X utf8 -B -m unittest discover -s tests
테스트 임시 파일과 시험 출력은 종료 시 정리한다.
검증은 바이너리 구조/제약/재현성에 관한 것이다. 게임 내 화면, 줄바꿈 폭,
동영상 오류 화면 및 디스크 교체의 실제 동작은 별도 게임 테스트가 필요하다.

선택 기능: 메모리카드 저장 제목
- 사용자 요청으로 보류 중입니다. discmetadata/Build_elf.bat에는 자동 적용하지 않습니다.
- edit/save_title.names.txt는 일본어 원문 이름 16개를 추출한 새 작업 파일입니다.
  출시용 표기 방침을 결정한 것이 아니며 기존 인게임 이름 TXT는 수정하지 않습니다.
- 먼저 Build_menutext.bat로 메뉴를 만든 뒤, 그 결과 menutext.txd를 이름 TXT 옆의
  edit/Build_save_title.bat에 드롭하세요. 명시한 메뉴와 현재 discmetadata/SLPS.txt를 사용합니다.
  메뉴를 지정하지 않으면 안내 후 중단하며 오래된 output을 자동 선택하지 않습니다.
- 새 output/save-title/날짜시간 폴더에 메뉴와 디스크별 실행 파일을 함께 만듭니다.
  세 바이너리 모두 .new로 만들며 수동 적용할 때만 .new 확장자를 제거합니다.
  반드시 같은 묶음의 메뉴와 해당 디스크 실행 파일을 함께 적용해야 합니다.
  이후 일반 빌드 결과로 한쪽만 덮어쓰면 안 됩니다. 되돌릴 때도 둘 다 되돌리세요.
- 원하는 표기로 고친 이름 TXT도 메뉴와 함께 드롭할 수 있습니다. --check는 저장 없이
  검사하고 --name은 새 결과 폴더명을 지정합니다. 기존 묶음은 덮어쓰지 않습니다.
- 이 선택 도구만 사용자가 명시한 저장소 내부 TXD를 추가로 읽습니다. 일반 ELF 빌드의
  저장소 내부 독립성은 그대로이며, 외부 ROM 폴더나 codex-lab에는 의존하지 않습니다.
- PS2 시스템 글꼴용 제목이라 한글/한자 치환표를 이름에 적용하지 않습니다. 원래 게임의
  변환기가 처리할 수 있는 전각 1~10자만 허용하며 임의 변환/생략/절단은 하지 않습니다.
  인게임 이름 번역에는 기존 한글 치환 방식이 그대로 유지됩니다.
- 실패한 .pending은 적용하지 마세요. 완성 파일 전체를 검증한 뒤 폴더 단위로 공개합니다.
- 자세한 근거와 적용 경로는 docs/SAVE_TITLE.txt에 있습니다. 실제 게임/저장/PS2 브라우저
  화면 검증은 아직 하지 않았으며 원본 ISO와 ROM 작업 폴더에는 적용하지 않았습니다.
- 검사: python -X utf8 -B -m unittest test_save_title_tool
