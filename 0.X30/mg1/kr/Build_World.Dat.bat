@echo off
setlocal DisableDelayedExpansion
chcp 65001 >nul
rem 더블클릭: 같은 폴더의 World.Dat.txt를 읽어 World.Dat.new를 만듭니다.
rem TXT 하나 드롭: 해당 작업본으로 시험 빌드. --check: 저장 없이 검사.
rem 원본 World.Dat와 치환표를 직접 읽고 기존 파일과 외부 ROM은 수정하지 않습니다.
rem 원문 재추출은 Extract_World.Dat.batlock을 사용하세요.
python -X utf8 -B "%~dp0..\..\..\tools\x30\build_minigame.py" --asset World.Dat %*
set "BUILD_RESULT=%ERRORLEVEL%"
if not "%BUILD_RESULT%"=="0" echo BUILD FAILED. Do not apply output files.
if not defined XS3_NO_PAUSE pause
exit /b %BUILD_RESULT%
