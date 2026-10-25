@echo off
setlocal DisableDelayedExpansion
chcp 65001 >nul
rem 더블클릭: 튜토리얼 5개와 전투 문구 24개, 총 29개 TXT를 리빌드합니다.
rem TXT를 하나 또는 여러 개 드롭하면 해당 파일만 처리합니다.
rem --check: 저장 없이 검사합니다. 결과는 같은 폴더의 이름.sb.new입니다.
rem 원본 SB, 작업 TXT, 외부 ROM 폴더는 수정하지 않습니다.
python -X utf8 -B "%~dp0..\..\..\tools\x30\build_sb.py" --group bat %*
set "RESULT=%ERRORLEVEL%"
if not "%RESULT%"=="0" echo 실패한 실행의 결과물은 적용하지 마세요.
if not defined XS3_NO_PAUSE pause
exit /b %RESULT%
