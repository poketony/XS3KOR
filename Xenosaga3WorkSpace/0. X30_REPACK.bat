@echo off
@chcp 65001
python ArchivePatchTool.py
XenoLbar.exe x3.00 x3.00_LBA_new.txt x3.00.new
python SpliterForX30.py
ren "X30.big.new.part1" "x3.01.new"
ren "X30.big.new.part2" "x3.02.new"
echo X30 Repacking Complete
pause