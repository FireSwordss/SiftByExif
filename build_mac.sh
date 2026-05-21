#!/bin/bash
echo "========================================"
echo "  SiftByExif - macOS Build"
echo "========================================"

python3 -m PyInstaller \
  --name SiftByExif \
  --onefile \
  --windowed \
  --add-data "siftbyexif/cities.json:siftbyexif" \
  --hidden-import PIL._tkinter_finder \
  main.py

echo
echo "Build complete. Output in dist/SiftByExif"
