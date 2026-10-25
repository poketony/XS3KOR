@echo off
setlocal
python -X utf8 -B "%~dp0elf_text_tool.py" export
set "RESULT=%ERRORLEVEL%"
pause
exit /b %RESULT%
