@echo off
cd /d "%~dp0"

rem Delete all image files in the current directory and subdirectories
del /q /s *.jpg
del /q /s *.jpeg
del /q /s *.png
del /q /s *.gif
del /q /s *.bmp
del /q /s *.tiff
del /q /s *.webp

echo Finished
pause