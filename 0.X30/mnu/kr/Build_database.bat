@echo off
setlocal DisableDelayedExpansion
chcp 65001 >nul
rem 더블클릭: 같은 폴더의 DBC.bin.KOR.txt로 DBC.bin.new와 DBC2.bin.new를 함께 만듭니다.
rem TXT 하나를 드롭하면 그 내용을 두 원본에 적용합니다. --check는 저장 없이 검사합니다.
rem 두 원본과 치환표를 직접 읽으며 기존 TXT/BIN과 DBC2의 분류용 원문은 보존합니다.
rem 원문 재추출은 Extract_database.batlock을 사용하세요. 외부 ROM에는 자동 적용하지 않습니다.
python -X utf8 -B "%~dp0..\..\..\tools\x30\build_database.py" %*
set "BUILD_RESULT=%ERRORLEVEL%"
if not "%BUILD_RESULT%"=="0" echo BUILD FAILED. Do not apply output files.
if not defined XS3_NO_PAUSE pause
exit /b %BUILD_RESULT%
