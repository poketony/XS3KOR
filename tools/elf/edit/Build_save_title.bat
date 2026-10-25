@echo off
setlocal DisableDelayedExpansion
python -X utf8 -B "%~dp0..\save_title_tool.py" %*
set "BUILD_RESULT=%ERRORLEVEL%"
if not "%BUILD_RESULT%"=="0" echo BUILD FAILED. Do not apply an incomplete or mismatched bundle.
if not defined XS3_NO_PAUSE pause
exit /b %BUILD_RESULT%
