@echo off
setlocal DisableDelayedExpansion
chcp 65001 >nul
rem Double-click: encode all TXT files. Drop one or more TXT files: encode only those.
rem UTF-8 -> Hangul font mapping -> EUC-JIS-2004. Output: original.txt.new.
rem --check validates without saving. Editors are preserved; no external ROM copy.
python -X utf8 -B "%~dp0..\..\..\..\tools\subtitles\encode_battle.py" %*
set "RESULT=%ERRORLEVEL%"
if not "%RESULT%"=="0" echo FAILED: Do not apply output files from this run.
if not defined XS3_NO_PAUSE pause
exit /b %RESULT%
