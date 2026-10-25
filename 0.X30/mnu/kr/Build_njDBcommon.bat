@echo off
setlocal DisableDelayedExpansion
chcp 65001 >nul
rem 더블클릭: 같은 폴더의 njDBcommon.KOR.txt을 읽어 njDBcommon.bin.new를 만듭니다.
rem TXT 하나를 드롭하면 그 파일로 시험 빌드합니다. --check는 저장 없이 검사합니다.
rem 원본 njDBcommon.bin과 치환표를 직접 읽고 작업 TXT와 원본은 덮어쓰지 않습니다.
rem 원문 재추출은 Extract_menu_text.batlock을 사용하세요. 외부 ROM에는 자동 적용하지 않습니다.
python -X utf8 -B "%~dp0..\..\..\tools\x30\build_menu.py" --asset njDBcommon %*
set "BUILD_RESULT=%ERRORLEVEL%"
if not "%BUILD_RESULT%"=="0" echo BUILD FAILED. Do not apply output files.
if not defined XS3_NO_PAUSE pause
exit /b %BUILD_RESULT%
