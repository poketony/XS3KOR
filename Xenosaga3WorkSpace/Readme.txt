Xenosaga III Trad Kit
By Lybac

Tools (they all work in command line)

To use them you need to have the table and the munge file of one of the packs, the table is the .x0 file and to get the munge file you need to join the
files following. For example for the pack 0 you need X3.00 and a file F3.big that you get by joining X3.01 and X3.02 with the command

copy /b X3.01 + X3.02 X3.big

-Xeno1Lbae.exe and Xeno23Lbae.exe extract the munge file table from the .x0 file. The first one works with Xeno 1 and the second with xeno 2 and 3.
-Xenounpack.exe unpacks the munge file to a UNPACKED rep. You need an extracted table to make it work. It works with all xeno games
-xenorepack.exe repack the munge file and build a new table file (that you will need to repack with the last programm). You still need the old extracted
table for this programm.
-XenoLbar.exe repacks the table file given by xenoreapack.exe to a standard .x0 file.

Things you need to replace in packs 1 and 2 : everything but the subtitles (I include some retimed subtitles files with the tools for the scenes where
the timing was way off)

Things you need to replace in pack 0 :

-rep KAO (models
-rep SND (and all its sub reps)
-rep PAC (and all its sub reps)
-rep MG1/com/sound/voices
-rep /ef/esp/ (there is a sub rep us you have replace the two files that are in it with the two corresponding file taht are just in
/ef/esp/ in tha jap version)
-rep /ef/esd/ and sub-reps (there is a sub-rep us replace its files by those that are in the sub-rep jp on the jap version)
-rep MDl (and all its sub reps)

Finally put the sb files given with this tutorial in /cf/us/. And you're done.

Rebuild the munge files, then the table files. Rebuild the iso with Sony CD/DVD gen, burn (or put it on your PS2 hd) and play.

Enjoy!