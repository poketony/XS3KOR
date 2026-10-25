@echo off
chcp 65001 >nul
setlocal DisableDelayedExpansion
rem 기본 실행은 이 폴더의 PNG 5장으로 titleobj.xtx.new를 만듭니다.
rem 수정 PNG를 끌어 놓으면 그 이름의 항목만 대체하고 나머지는 이 폴더에서 읽습니다.
rem --check는 저장 없이 검사합니다. --extract는 원본 추출이며 기존 편집 파일이 있으면 거부합니다.
rem ROM 작업 폴더로 자동 복사하지 않습니다. 실패한 실행의 결과를 적용하지 마세요.
python -X utf8 -B "%~dp0..\..\..\..\tools\x30\build_title.py" %*
set "BUILD_RESULT=%ERRORLEVEL%"
if not "%BUILD_RESULT%"=="0" echo BUILD FAILED. Do not apply output files.
if not defined XS3_NO_PAUSE pause
exit /b %BUILD_RESULT%
