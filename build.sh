#!/usr/bin/env bash
# Genera dist/OptiSolver (Linux / macOS)
set -e
python3 -m pip install --upgrade pyinstaller
python3 -m PyInstaller --noconfirm --clean --onefile --windowed --name OptiSolver main.py
echo
echo "Listo. Ejecutable en: dist/OptiSolver"
