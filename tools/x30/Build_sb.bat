@echo off
chcp 65001 >nul
setlocal DisableDelayedExpansion
rem 기본 실행은 cf와 bat의 작업 TXT 전체를 읽습니다. --group cf 또는 bat로 범위를 선택합니다.
rem --asset cf/8050처럼 하나를 고르거나 TXT를 여러 개 지정할 수 있습니다. --check는 저장 없이 검사합니다.
rem --extract는 원본 TXT를 추출하며 기존 파일이 있으면 거부합니다. 결과는 작업 원본 옆의 .sb.new입니다.
python -X utf8 -B "%~dp0build_sb.py" %*
set "BUILD_RESULT=%ERRORLEVEL%"
if not "%BUILD_RESULT%"=="0" echo BUILD FAILED. Do not apply output files.
if not defined XS3_NO_PAUSE pause
exit /b %BUILD_RESULT%
