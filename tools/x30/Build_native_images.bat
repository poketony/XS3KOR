@echo off
chcp 65001 >nul
setlocal DisableDelayedExpansion
rem 기본 실행은 등록된 PNG와 JPG 전체를 각 작업 폴더의 .new 파일로 만듭니다.
rem --asset title1 또는 wall 또는 intm10, --synopsis, --database로 범위를 선택합니다. 단일 항목은 이미지 경로를 추가할 수 있습니다.
rem --check는 저장 없이 검사합니다. --extract는 원본 추출이며 기존 편집 파일이 있으면 거부합니다.
rem ROM 작업 폴더로 자동 복사하지 않습니다. 실패한 실행의 결과를 적용하지 마세요.
python -X utf8 -B "%~dp0build_native_images.py" %*
set "BUILD_RESULT=%ERRORLEVEL%"
if not "%BUILD_RESULT%"=="0" echo BUILD FAILED. Do not apply output files.
if not defined XS3_NO_PAUSE pause
exit /b %BUILD_RESULT%
