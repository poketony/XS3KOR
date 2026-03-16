@echo off
@chcp 65001
XenoRepack.exe x3.10_LBA_origin.txt x3.10_LBA_new.txt X31.big.new
XenoLbar.exe x3.10 x3.10_LBA_new.txt x3.10.new
python SpliterForX31.py
ren "X31.big.new.part1" "x3.11.new"
ren "X31.big.new.part2" "x3.12.new"
ren "X31.big.new.part3" "x3.13.new"
echo X31 리팩 작업이 완료되었습니다.
pause