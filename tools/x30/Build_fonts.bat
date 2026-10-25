@echo off
chcp 65001 >nul
setlocal DisableDelayedExpansion
rem 기본 실행은 0.X30/mnu/kr/fonts의 두 폰트를 각각 .bin.new로 만듭니다.
rem --asset font0 또는 --asset font1로 선택합니다. 이름이 유지된 PNG를 끌어 놓으면 그 채널만 대체합니다.
rem --check는 저장 없이 검사합니다. --extract는 원본 추출이며 기존 편집 파일이 있으면 거부합니다.
rem ROM 작업 폴더로 자동 복사하지 않습니다. 실패한 실행의 결과를 적용하지 마세요.
python -X utf8 -B "%~dp0build_fonts.py" %*
set "BUILD_RESULT=%ERRORLEVEL%"
if not "%BUILD_RESULT%"=="0" echo BUILD FAILED. Do not apply output files.
if not defined XS3_NO_PAUSE pause
exit /b %BUILD_RESULT%
