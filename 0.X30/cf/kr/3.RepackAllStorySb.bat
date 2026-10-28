@echo off
setlocal DisableDelayedExpansion
chcp 65001 >nul
rem [JPN]은 유지하고 [KOR]만 편집하세요. 더블클릭하면 등록된 스토리 TXT 786개를 모두 리빌드합니다.
rem 결과는 각 원본 바로 옆의 이름.sb.new이며 원본 SB와 번역 TXT는 보존합니다.
rem --check: 저장 없이 검사합니다. 선택한 TXT만 처리하려면 4.DragStoryTxt.bat를 사용하세요.
python -X utf8 -B "%~dp0..\..\..\tools\x30\build_sb.py" --group cf %*
set "RESULT=%ERRORLEVEL%"
if not "%RESULT%"=="0" echo 실패한 실행의 결과물은 적용하지 마세요.
if not defined XS3_NO_PAUSE pause
exit /b %RESULT%
