@echo off
@chcp 65001
XenoRepack.exe x3.00_LBA_origin.txt x3.00_LBA_new.txt X30.big.new
XenoLbar.exe x3.00 x3.00_LBA_new.txt x3.00.new
python SpliterForX30.py
ren "X30.big.new.part1" "x3.01.new"
ren "X30.big.new.part2" "x3.02.new"
echo X30 리팩 작업이 완료되었습니다.
pause