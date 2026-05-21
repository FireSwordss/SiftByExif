@echo off
echo ========================================
echo   SiftByExif - Windows Build
echo ========================================

python -m PyInstaller ^
  --name SiftByExif ^
  --onefile ^
  --windowed ^
  --add-data "siftbyexif/cities.json;siftbyexif" ^
  --hidden-import PIL._tkinter_finder ^
  --icon NONE ^
  main.py

echo.
echo Build complete. Output in dist/SiftByExif.exe
