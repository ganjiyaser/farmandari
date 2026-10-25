@echo off
rem Build script - keep this file ASCII-only (cmd.exe misparses non-ASCII
rem bytes in .bat files regardless of chcp).
echo ============================================
echo   Build installer - Farmandari App
echo ============================================
echo.

cd /d "%~dp0"

set PY=".venv\Scripts\python.exe"
if not exist %PY% set PY="..\desktop_app\.venv\Scripts\python.exe"

echo [1/3] Cleaning previous outputs...
if exist dist rmdir /s /q dist 2>nul
if exist build rmdir /s /q build 2>nul
if exist Output rmdir /s /q Output 2>nul

echo [2/3] Building app with PyInstaller (farmandari.spec, onedir)...
%PY% -m PyInstaller farmandari.spec --noconfirm --clean
if errorlevel 1 (
    echo [ERROR] PyInstaller failed
    exit /b 1
)

if not exist "dist\FarmandariApp\FarmandariApp.exe" (
    echo [ERROR] dist\FarmandariApp\FarmandariApp.exe was not produced
    exit /b 1
)

echo [3/3] Building installer with NSIS...
if not exist Output mkdir Output
if exist "C:\Program Files (x86)\NSIS\makensis.exe" (
    "C:\Program Files (x86)\NSIS\makensis.exe" farmandari.nsi
) else if exist "C:\Program Files\NSIS\makensis.exe" (
    "C:\Program Files\NSIS\makensis.exe" farmandari.nsi
) else (
    echo [WARN] NSIS not found. Install NSIS or compile farmandari.nsi manually.
    exit /b 1
)
if errorlevel 1 (
    echo [ERROR] makensis failed
    exit /b 1
)

echo.
echo ============================================
echo   Build complete: Output\FarmandariSetup_1.2.0.exe
echo ============================================
exit /b 0
