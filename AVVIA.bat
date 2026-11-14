@echo off
chcp 65001 >nul
title ContaCasse
cd /d "%~dp0"
where python >nul 2>nul || (
  echo Python non trovato. Installalo da python.org spuntando "Add python.exe to PATH".
  pause
  exit /b
)
python -c "import numpy, cv2, mss, dxcam" 2>nul || (
  echo Installo le librerie che servono, solo la prima volta...
  python -m pip install --user numpy opencv-python-headless mss dxcam
)
python contacasse.py
pause
