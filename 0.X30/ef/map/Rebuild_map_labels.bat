@echo off
setlocal DisableDelayedExpansion
chcp 65001 >nul
rem 더블클릭: ef/esd/kr의 공통 PNG로 맵 ESP 45개를 리빌드합니다.
rem ef/esd/kr의 ce*.png를 드롭하면 같은 지명을 쓰는 맵만 처리합니다.
rem *.location.png는 추출 참고본이며 빌드 입력이 아닙니다. --check는 저장 없이 검사합니다.
rem 결과는 원본 ESP와 같은 폴더의 *.esp.new입니다. 다른 맵 데이터는 보존합니다.
python -X utf8 -B "%~dp0..\..\..\tools\x30\build_effects.py" --group map %*
set "RESULT=%ERRORLEVEL%"
if not "%RESULT%"=="0" echo 실패한 실행의 결과물을 적용하지 마세요.
if not defined XS3_NO_PAUSE pause
exit /b %RESULT%
