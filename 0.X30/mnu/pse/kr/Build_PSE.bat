@echo off
setlocal DisableDelayedExpansion
chcp 65001 >nul
rem 더블클릭: AC/EP1/EP2/opening/PP/test의 작업 TXT 6개를 읽어 각각 이름.mes.new를 만듭니다.
rem 등록된 이름의 TXT 하나를 드롭하면 그 파일만 처리합니다. --asset EP1 등으로 직접 선택할 수도 있습니다.
rem --check: 저장 없이 검사. 예: Build_PSE.bat --asset EP1 --check
rem 원본 MES와 치환표를 이 폴더에서 직접 읽고 작업 TXT와 원본은 덮어쓰지 않습니다.
rem 원문 재추출은 Extract_PSE.batlock을 사용하세요. 외부 ROM에는 자동 적용하지 않습니다.
python -X utf8 -B "%~dp0..\..\..\..\tools\x30\build_pse.py" %*
set "BUILD_RESULT=%ERRORLEVEL%"
if not "%BUILD_RESULT%"=="0" echo BUILD FAILED. Do not apply output files.
if not defined XS3_NO_PAUSE pause
exit /b %BUILD_RESULT%
