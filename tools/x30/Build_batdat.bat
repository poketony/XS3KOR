@echo off
setlocal DisableDelayedExpansion
chcp 65001 >nul
rem 기본 실행은 작업 폴더 batdat.json으로 같은 폴더의 batdat.bin.new를 만듭니다.
rem JSON 경로를 추가하면 그 번역을 사용합니다. --check는 저장 없이 검사합니다.
rem --extract는 일본어 원본 JSON 추출입니다. --export-editor 새경로.json은 현재 번역을 포함한 검토용 JSON입니다.
rem 추출과 검토용 JSON 내보내기는 기존 파일을 덮어쓰지 않습니다. 서로 다른 실행 모드이므로 함께 지정하지 마세요.
python -X utf8 -B "%~dp0build_batdat.py" %*
set "BUILD_RESULT=%ERRORLEVEL%"
if not "%BUILD_RESULT%"=="0" echo BUILD FAILED. Do not apply output files.
if not defined XS3_NO_PAUSE pause
exit /b %BUILD_RESULT%
