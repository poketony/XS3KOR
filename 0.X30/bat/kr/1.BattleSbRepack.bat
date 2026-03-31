@echo off
@chcp 65001
echo 튜토리얼 .sb 파일 리팩을 시작합니다...

:: 리팩할 .sb 파일들 실행
python 0.sbtool.py import REN_B01.sb REN_B01.txt
python 0.sbtool.py import SPC_B01.sb SPC_B01.txt
python 0.sbtool.py import UMD_B01.sb UMD_B01.txt
python 0.sbtool.py import UMD_B03.sb UMD_B03.txt
python 0.sbtool.py import UMD_B04.sb UMD_B04.txt

echo.
echo 모든 작업이 완료되었습니다!
pause