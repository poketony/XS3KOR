@echo off
setlocal DisableDelayedExpansion
chcp 65001 >nul
rem 더블클릭: 공통 지명 PNG 25개로 ESD와 연결된 맵 ESP를 함께 리빌드합니다.
rem PNG를 드롭하면 해당 ESD와 같은 지명을 쓰는 맵만 처리합니다.
rem 결과: 이 폴더의 *.esd.new 및 ..\..\map\*.esp.new. --check는 저장 없이 검사합니다.
python -X utf8 -B "%~dp0..\..\..\..\tools\x30\build_effects.py" --group esd %*
set "RESULT=%ERRORLEVEL%"
if not "%RESULT%"=="0" echo 실패한 실행의 결과물을 적용하지 마세요.
if not defined XS3_NO_PAUSE pause
exit /b %RESULT%
