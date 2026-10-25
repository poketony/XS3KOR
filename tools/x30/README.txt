제노사가 III: X30 작업 안내
==========================
기준 경로: C:\Users\JO\XS3KOR
이 안내의 작업 경로는 0.X30 아래 상대 경로입니다.
ROM은 C:\Users\JO\Desktop\XENO_ARC\Xenosaga\Xenosaga3에서 따로 만듭니다.

일상 작업
---------
1. 아래 표의 TXT/JSON/PNG/JPG 작업본을 수정합니다.
2. 같은 작업 폴더의 BAT를 실행합니다. BUILD SUCCEEDED와 종료 코드 0을 확인합니다.
3. 생성된 .new를 확인하고, .new를 제거한 게임 파일명으로 외부 ROM 작업 폴더에 직접 적용합니다.
4. 외부 Xenosaga3의 1.RebuildDisc1.bat와 2.RebuildDisc2.bat로 ISO를 각각 만듭니다.
   공통 X30을 바꿨다면 두 디스크 모두 다시 만듭니다.

저장소 변환과 외부 ROM 빌드는 서로 독립적입니다.
BAT가 외부 ROM 폴더를 자동 갱신하거나 그쪽 도구가 XS3KOR의 TXT를 읽지 않습니다.
저장소 내부 X30 아카이브 빌더는 제거했습니다. Build_x30.bat를 거치는 단계는 없습니다.
Python 3.10 이상, 이미지 변환에는 Pillow가 필요합니다.

메뉴 텍스트: mnu/kr
------------------
편집 파일                    실행 BAT                       결과
njDataText.KOR.txt            Build_njDataText.bat           njDataText.bin.new
MVtext.KOR.txt                Build_MVtext.bat               MVtext.bin.new
SegmentFileData.KOR.txt       Build_SegmentFileData.bat      SegmentFileData.bin.new
njDBcommon.KOR.txt            Build_njDBcommon.bat           njDBcommon.bin.new
njBtlText.KOR.txt             Build_njBtlText.bat            njBtlText.JPN.bin.new
devchk.txd_kor.txt            Build_devchk.bat               devchk.txd.new
discchg.txd.kor.txt           Build_discchg.bat              discchg.txd.new
menutext.txd_kor.txt          Build_menutext.bat              menutext.JPN.txd.new
synopsis.txd_kor.txt          Build_synopsis.bat             synopsis.txd.new
DBC.bin.KOR.txt               Build_database.bat             DBC.bin.new + DBC2.bin.new

ROM 적용 위치: X30_UNPACKED/mnu/jp/
이름 예외: njBtlText.JPN.bin.new -> njBtlText.bin
           menutext.JPN.txd.new -> menutext.txd
DBC 두 결과는 함께 적용합니다. MVtext는 무비 뷰어 목록/설명이며 컷신 자막이 아닙니다.

다른 텍스트
-----------
cf/kr/*.txt
  전체: 3.RepackAllStorySb.bat
  선택: 4.DragStoryTxt.bat에 수정한 TXT를 드롭
  결과: 같은 폴더의 *.sb.new -> X30_UNPACKED/cf/jp/

bat/kr/*.txt
  실행: 1.BattleSbRepack.bat
  결과: *.sb.new -> X30_UNPACKED/bat/jp/

bat/kr/batdatEdit/batdat.json
  실행: patch.bat
  결과: batdat.bin.new -> X30_UNPACKED/bat/jp/batdat.bin

mg1/kr/Message.Dat.txt
  실행: Build_Message.Dat.bat
  결과: Message.Dat.new -> X30_UNPACKED/mg1/jp/Message.Dat

mg1/kr/World.Dat.txt
  실행: Build_World.Dat.bat
  결과: World.Dat.new -> X30_UNPACKED/mg1/com/Stage/World.Dat

mnu/pse/kr/AC.mes.kor.txt, EP1.mes.txt, EP2.mes.txt,
opening.mes.txt, PP.mes.txt, test.mes.txt
  실행: Build_PSE.bat
  결과: *.mes.new 6개 -> X30_UNPACKED/mnu/pse/jp/

그래픽과 폰트
-------------
mnu/kr/titleobj: new_game/continue/data/disc1/disc2.png
  Build_titleobj.bat -> titleobj.xtx.new -> X30_UNPACKED/mnu/jp/

mnu/kr/window: enemy_info/boost/command/boost_red/stock/player/enemy/anima/act_large/act_small.png
  Build_window.bat -> window0/1/2.xtx.new -> X30_UNPACKED/mnu/jp/

mnu/pse/kr: logo_ep1.png, logo_ep2.png, logo_pp.png
  Build_PSE_logos.bat -> 같은 이름의 .tm2.new -> X30_UNPACKED/mnu/pse/

mnu/kr/title1.png / wall.jpg
  Build_title1.bat / Build_wall.bat -> 원래 확장자 뒤 .new -> X30_UNPACKED/mnu/jp/

mnu/intm/10.jpg
  Build_10.bat -> 10.jpg.new -> X30_UNPACKED/mnu/intm/

mnu/syno/NNN.jpg 71개
  Build_synopsis_images.bat -> NNN.jpg.new -> X30_UNPACKED/mnu/syno/

jpg/kr/dtimg_NNNN.jpg 25개
  Build_database_images.bat -> 해당 번호와 +1000 번호의 JPG.new 50개 -> X30_UNPACKED/jpg/
  작업본은 낮은 번호만 편집합니다. 두 번호의 결과를 모두 적용합니다.

ef/esd/kr/ce*.png 25개
  Rebuild_esd.bat -> *.esd.new 및 같은 지명을 쓰는 ef/map/*.esp.new를 함께 생성
  ESD -> X30_UNPACKED/ef/esd/jp/ 및 ef/esd/ce000/ 양쪽, ESP -> X30_UNPACKED/ef/map/

ef/map: 맵만 처리할 때
  Rebuild_map_labels.bat도 ef/esd/kr/ce*.png를 사용 -> *.esp.new -> X30_UNPACKED/ef/map/
  기존 *.location.png는 추출/대조용이며 빌드 입력이 아닙니다.

mnu/kr/fonts/font0_{red,green,blue,alpha}.png, font1의 같은 네 채널
  Build_font0.bat / Build_font1.bat -> font0.bin.new / font1.bin.new -> X30_UNPACKED/mnu/jp/
  폰트를 바꿀 때만 실행합니다. 원본의 마지막 3,072바이트는 그대로 보존합니다.

이미지는 기존 크기와 형식을 유지합니다. PNG의 알파를 없애지 마세요.
JPG는 baseline RGB JPEG로 저장하며 progressive/CMYK JPEG는 지원하지 않습니다.
일반 PNG/JPG는 검증 후 바이트 그대로 출력합니다. 자동 재압축하지 않습니다.
타이틀/HUD/로고 등의 개별 형식 제한은 docs 안의 해당 기술 문서를 참고하세요.

ESD: 이미지 수정부터 ROM까지
---------------------------
예: ef/esd/kr/ce003_999.png

1. 기존 PNG를 열어 문구를 편집합니다. 현재 작업 PNG에 한글 작업 내용이 들어 있습니다.
   같은 이름, 256x32, 알파가 있는 단일 PNG로 저장합니다.
   재추출은 일상 편집 단계가 아닙니다. 원문 추출 BAT로 현재 작업을 교체하지 마세요.

2. Rebuild_esd.bat를 실행하면 ESD 25개와 연결된 맵 ESP 45개를 함께 처리합니다.
   수정한 PNG만 BAT 위에 드롭하면 해당 ESD와 같은 지명을 쓰는 맵만 처리합니다.
   원본이 검정 RGB+알파 램프이면 글자 본체와 그림자를 모두 알파로 옮깁니다.
   검정은 기존 알파를 유지하고, 회색은 밝기에 맞는 반투명 검정으로 변환합니다.
   변환식은 새 알파 = 기존 알파 * (255 - 회색값) / 255이며, 반올림한 뒤
   원본 알파 단계에 맞춥니다. 흰 배경 위에서의 명암을 보존하는 방식으로,
   그림자를 분리하거나 지우지 않습니다. 유색 입력은 임의로 변환하지 않고 중단합니다.
   작업 PNG와 ESD/ESP 각각의 원본 팔레트를 보존합니다. 실제 다색 팔레트에만 투명색 포함
   최대 16색의 전용 팔레트를 만들며 완전 투명한 픽셀의 숨은 RGB는 무시합니다.
   quantized_pixels는 감색/알파 변환된 픽셀 수, palette_mode는 alpha_mask/rgba,
   palette_changed는 팔레트 갱신 여부입니다. 무수정 추출 PNG는 그대로 왕복합니다.

3. 같은 폴더에 ce003_999.esd.new가 생성되고, ../../map에
   ef1220.esp.new와 ef1228.esp.new가 함께 생성됩니다.
   BUILD SUCCEEDED를 확인합니다. 실패한 실행에는 예전 .new가 남아 있을 수 있습니다.

4. ce003_999.esd.new를 ce003_999.esd라는 이름으로 아래 두 곳에 직접 적용합니다.
   Xenosaga3/X30_UNPACKED/ef/esd/jp/ce003_999.esd
   Xenosaga3/X30_UNPACKED/ef/esd/ce000/ce003_999.esd
   두 곳 모두 동일한 결과를 사용합니다. .new 이름 그대로 넣어서는 적용되지 않습니다.

5. 함께 생성된 ef1220.esp.new/ef1228.esp.new도 .new 없이 외부
   X30_UNPACKED/ef/map/에 적용합니다. 맵 PNG를 따로 수정하거나 두 번째 BAT를
   실행할 필요는 없습니다. 대응 관계는 effect_sources.json의 texture_name 기준입니다.
   맵 전용 BAT도 공통 PNG를 사용하므로 오래된 *.location.png로 되돌아가지 않습니다.
   지명 이미지와 전용 팔레트 외 데이터는 보존합니다. 기준 알파 램프가 다른
   ef0420도 팔레트를 덮어쓰지 않고 같은 마스크 형상을 가장 가까운 단계로 배치합니다.

6. 외부 Xenosaga3에서 1.RebuildDisc1.bat, 2.RebuildDisc2.bat를 차례로 실행합니다.
   현재 X30/X31/X32_UNPACKED를 직접 패킹하므로 옛 X30_REPACK 등을 먼저 돌릴 필요가 없습니다.
   X31/X32의 작업 파일은 외부 ROM 빌더가 그대로 사용합니다.
   각 디스크 빌드 중 새 ISO를 위한 약 4.8GB 이상의 추가 여유 공간을 확보하세요.

7. 외부 Xenosaga3 폴더의 Xenosaga3_Disc1_KOR.iso / Xenosaga3_Disc2_KOR.iso를 확인합니다.
   성공 표시와 종료 코드 0을 확인한 뒤 게임에서 해당 지명 표시를 확인합니다.
   파일 구조 검증 통과가 화면 위치, 가독성, 색상까지 보장하지는 않습니다.

실행 파일: discmetadata (도구 코드는 tools/elf)
-------------------
discmetadata/SLPS.txt와 OV04.txt -> 같은 폴더의 Build_elf.bat
  SLPS 결과 -> Xenosaga3/disc1metadata/SLPS_256.40
  같은 SLPS 결과 -> Xenosaga3/disc2metadata/SLPS_256.41
  OV04 결과 -> 두 디스크의 discNmetadata/OV04.OVL
이 BAT는 전체 검증 후 외부 작업 폴더에 자동 복사합니다. 로컬 .new 사본은 만들지 않습니다.
ROM 빌더는 계속 독립적으로 실행합니다. 자세한 제어 코드와 길이 제한은 tools/elf/README.txt를 참고하세요.
메모리카드 브라우저 제목은 사용자 요청으로 보류 중이며 일반 번역 빌드에 자동 적용하지 않습니다.

편집/실패 처리 규칙
-------------------
- UTF-8 한글 작업 TXT를 직접 편집합니다. 치환한 TXT 사본은 따로 만들 필요가 없습니다.
- 도구가 작업 폴더의 한글/한자 표를 읽어 치환하고 EUC-JIS-2004로 저장합니다.
- 기존 주소/ID/제어 코드, 꺾쇠와 인용부호를 유지합니다. 문장 부호를 자동 변환하지 않습니다.
- [menu_sita]의 기존 처리 규칙은 유지합니다.
- 원본 BIN/TXD/SB/ESD/ESP, original 이미지, 치환표와 *_sources.json은 일반 편집 대상이 아닙니다.
- .new는 변환 결과입니다. 이를 기준 원본으로 덮어쓰지 마세요.
- .batlock은 원문 추출/검토용입니다. 기존 편집 파일이 있으면 추출을 거부합니다.
- --check는 메모리에서 재구성/검사만 합니다. 작업본과 결과 파일을 쓰지 않습니다.
- 여러 출력은 한꺼번에 원자적으로 교체되지 않습니다. 실패한 실행 결과는 적용하지 마세요.
- 원본/치환표 해시 불일치, 없는 입력, 표현 불가능한 문자, 포맷별 용량 초과는 오류입니다.
- tools/x30/edit 사본, codex-lab, 외부 ROM 폴더를 대체 입력으로 찾지 않습니다.

도구 폴더와 검증
----------------
build_*.py, tools/: 개별 포맷 변환 코드. 작업 폴더 BAT가 이 코드를 호출합니다.
*_sources.json, sources.json: 입력 경로, 기준 해시와 게임 내부 목적지 정보.
reference/batdat.legacy.json: 구형 batdat JSON 호환에 필요한 기준 자료. 삭제하지 마세요.
reference의 나머지 소형 자료와 batdat_migration.json: 회귀 테스트용 기준 자료.
docs/: 포맷 제약과 분석 근거. tests/: 회귀 테스트 코드.
루트의 Build_menu/Build_sb 등은 여러 자산 일괄 변환용 보조 진입점입니다.

개발 검증은 tools/x30에서:
  python -X utf8 -B -m unittest discover -s tests
개별 도구 검사는:
  python -X utf8 -B build_menu.py --check
  python -X utf8 -B build_effects.py --group esd --check
검증 중 임시 파일은 종료 시 정리합니다. 별도 아카이브/ISO 사본을 만들지 않습니다.
