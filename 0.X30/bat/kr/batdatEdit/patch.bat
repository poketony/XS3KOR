@echo off
setlocal DisableDelayedExpansion
chcp 65001 >nul
rem 더블클릭: 같은 폴더의 batdat.json을 읽어 batdat.bin.new를 만듭니다.
rem JSON 한 개를 드롭하면 그 내용을 시험 빌드합니다. 기본 작업 JSON은 바뀌지 않습니다.
rem --check: 저장 없이 검사. --export-editor "새 파일명.json": 현재 번역의 전체 구조를 검토용으로 내보내기.
rem 검토 JSON은 이 작업 폴더 또는 tools/x30/output 안의 새 경로여야 하며 기존 파일은 덮어쓰지 않습니다.
rem 원문 추출은 Extract_batdat.batlock을 사용하세요. 원본 BIN과 인게임 번역은 자동 변경하지 않습니다.
python -X utf8 -B "%~dp0..\..\..\..\tools\x30\build_batdat.py" %*
set "RESULT=%ERRORLEVEL%"
if not "%RESULT%"=="0" echo 실패한 실행의 결과물은 적용하지 마세요.
if not defined XS3_NO_PAUSE pause
exit /b %RESULT%
