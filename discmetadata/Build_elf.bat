@echo off
setlocal DisableDelayedExpansion
chcp 65001 >nul
set "ROM_ROOT=C:\Users\JO\Desktop\XENO_ARC\Xenosaga\Xenosaga3"
python -X utf8 -B "%~dp0..\tools\elf\elf_text_tool.py" build --rom-root "%ROM_ROOT%" %*
set "RESULT=%ERRORLEVEL%"
if not "%RESULT%"=="0" echo [ERROR] Build failed. Do not use unfinished outputs.
if not defined XS3_NO_PAUSE if /I not "%~1"=="--check" pause
exit /b %RESULT%
