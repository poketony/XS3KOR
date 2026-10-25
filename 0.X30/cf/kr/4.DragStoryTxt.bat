@echo off
setlocal DisableDelayedExpansion
chcp 65001 >nul
rem TXT 하나 또는 여러 개를 드롭하면 그 파일들만 원본 SB에 적용합니다.
rem 입력 없이 실행하면 오류로 멈춥니다. 전체 작업은 3.RepackAllStorySb.bat를 사용하세요.
rem --check를 함께 주면 저장 없이 검사합니다. 출력은 원본 옆의 이름.sb.new입니다.
rem 다른 이름이나 중복 파일, 누락된 TXT는 건너뛰지 않고 전체 실행을 중단합니다.
python -X utf8 -B "%~dp0..\..\..\tools\x30\build_sb.py" --group cf --require-editors %*
set "RESULT=%ERRORLEVEL%"
if not "%RESULT%"=="0" echo TXT를 드롭했는지와 오류 내용을 확인하세요. 실패한 결과물은 적용하지 마세요.
if not defined XS3_NO_PAUSE pause
exit /b %RESULT%
