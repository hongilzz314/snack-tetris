@echo off
chcp 65001 >nul
cd /d "%~dp0"
py -m pip install --upgrade pyinstaller
py -m PyInstaller --clean --noconfirm --onefile --windowed --name SnackTetris main.py
if errorlevel 1 (
    echo.
    echo EXE build failed. Check the error above.
    pause
    exit /b 1
)
echo.
echo Build complete: dist\SnackTetris.exe
echo Copy the assets folder next to the EXE if you use game_over.png.
pause
