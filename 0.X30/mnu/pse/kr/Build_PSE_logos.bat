@echo off
chcp 65001 >nul
setlocal DisableDelayedExpansion
rem 기본 실행은 로고 3장을 각각 원본 이름.tm2.new로 만듭니다.
rem logo_ep1.png 등을 끌어 놓으면 해당 로고만 생성합니다. --asset logo_ep1로도 선택할 수 있습니다.
rem --check는 저장 없이 검사합니다. --extract는 원본 추출이며 기존 편집 파일이 있으면 거부합니다.
rem ROM 작업 폴더로 자동 복사하지 않습니다. 실패한 실행의 결과를 적용하지 마세요.
python -X utf8 -B "%~dp0..\..\..\..\tools\x30\build_pse_logos.py" %*
set "BUILD_RESULT=%ERRORLEVEL%"
if not "%BUILD_RESULT%"=="0" echo BUILD FAILED. Do not apply output files.
if not defined XS3_NO_PAUSE pause
exit /b %BUILD_RESULT%
