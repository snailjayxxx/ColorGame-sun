@echo off
setlocal
cd /d "%~dp0"

py -m pip install --upgrade pip
if errorlevel 1 goto :error
py -m pip install -e ".[dev]"
if errorlevel 1 goto :error

py -m pytest
if errorlevel 1 goto :error

py -m PyInstaller --noconfirm --clean --onefile --windowed ^
  --name ColorGame ^
  --collect-all pynput ^
  run.py
if errorlevel 1 goto :error

echo.
echo Build completed: dist\ColorGame.exe
pause
exit /b 0

:error
echo.
echo Build failed. Please review the error messages above.
pause
exit /b 1
