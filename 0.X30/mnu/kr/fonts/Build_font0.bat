@echo off
chcp 65001 >nul
setlocal DisableDelayedExpansion
rem 기본 실행은 이 폴더의 font0_색상.png 4장으로 font0.bin.new를 만듭니다.
rem 같은 이름의 PNG를 끌어 놓으면 그 채널만 대체합니다. --check는 저장 없이 검사합니다.
rem 원본 마지막 3072바이트는 유지합니다. ROM 작업 폴더로 자동 복사하지 않습니다.
python -X utf8 -B "%~dp0..\..\..\..\tools\x30\build_fonts.py" --asset font0 %*
set "BUILD_RESULT=%ERRORLEVEL%"
if not "%BUILD_RESULT%"=="0" echo BUILD FAILED. Do not apply output files.
if not defined XS3_NO_PAUSE pause
exit /b %BUILD_RESULT%
