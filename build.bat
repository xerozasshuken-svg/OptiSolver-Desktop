@echo off
REM Genera dist\OptiSolver.exe (requiere Python instalado)
py -m pip install --upgrade pyinstaller
py -m PyInstaller --noconfirm --clean --onefile --windowed --name OptiSolver main.py
echo.
echo Listo. Ejecutable en: dist\OptiSolver.exe
pause
