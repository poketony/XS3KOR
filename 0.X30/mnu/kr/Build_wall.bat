@echo off
chcp 65001 >nul
setlocal DisableDelayedExpansion
rem 기본 실행은 wall.jpg를 검증해 같은 폴더에 wall.jpg.new를 만듭니다.
rem JPG를 끌어 놓으면 그 이미지를 사용합니다. 이미지를 재인코딩하지 않습니다.
rem --check는 저장 없이 검사합니다. --extract는 원본 추출이며 기존 편집 파일이 있으면 거부합니다.
rem ROM 작업 폴더로 자동 복사하지 않습니다. 실패한 실행의 결과를 적용하지 마세요.
python -X utf8 -B "%~dp0..\..\..\tools\x30\build_native_images.py" --asset wall %*
set "BUILD_RESULT=%ERRORLEVEL%"
if not "%BUILD_RESULT%"=="0" echo BUILD FAILED. Do not apply output files.
if not defined XS3_NO_PAUSE pause
exit /b %BUILD_RESULT%
