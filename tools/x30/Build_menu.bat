@echo off
chcp 65001 >nul
setlocal DisableDelayedExpansion
rem 기본 실행은 메뉴 9종 전체입니다. --asset devchk 등으로 하나를 선택합니다.
rem TXT 경로를 추가하면 해당 파일을 사용합니다. --check는 저장 없이 검사합니다.
rem --extract는 원본을 추출하며 기존 작업 TXT가 있으면 거부합니다. 일반 결과는 작업 원본 옆의 .new입니다.
python -X utf8 -B "%~dp0build_menu.py" %*
set "BUILD_RESULT=%ERRORLEVEL%"
if not "%BUILD_RESULT%"=="0" echo BUILD FAILED. Do not apply output files.
if not defined XS3_NO_PAUSE pause
exit /b %BUILD_RESULT%
