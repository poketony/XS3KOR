@echo off
setlocal DisableDelayedExpansion
chcp 65001 >nul
python -X utf8 -B "%~dp0..\tools\subtitles\subtitles.py" decode --disc 1 %*
set "RESULT=%ERRORLEVEL%"
if not defined XS3_NO_PAUSE pause
exit /b %RESULT%
