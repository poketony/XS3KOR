@echo off
setlocal DisableDelayedExpansion
chcp 65001 >nul
set "ROM_ROOT=C:\Users\JO\Desktop\XENO_ARC\Xenosaga\Xenosaga3"
python -X utf8 -B "%~dp0..\tools\subtitles\subtitles.py" encode --disc 1 --rom-root "%ROM_ROOT%" %*
set "RESULT=%ERRORLEVEL%"
if not "%RESULT%"=="0" echo FAILED: Do not rebuild the ISO until this succeeds.
if not defined XS3_NO_PAUSE pause
exit /b %RESULT%
