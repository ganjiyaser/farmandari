@echo off
rem Build script - keep this file ASCII-only (cmd.exe misparses non-ASCII
rem bytes in .bat files regardless of chcp).
rem
rem Usage:
rem   build_installer.bat x86
rem   build_installer.bat x64
rem   build_installer.bat all
rem
rem Python 3.8 is required (last CPython with Windows 7 support). Point the
rem launchers at the 32-bit / 64-bit interpreters or venvs:
rem   set PY38_X86=E:\venvs\py38-x86\Scripts\python.exe
rem   set PY38_X64=E:\venvs\py38-x64\Scripts\python.exe
rem Without them, the py launcher selectors (py -3.8-32 / py -3.8-64) are used.
rem
rem BUILD_ROOT is optional; it defaults to this folder. Set it to build outside
rem the repository (for example on another drive).

setlocal EnableExtensions
cd /d "%~dp0"

set "ARCH=%~1"
if "%ARCH%"=="" set "ARCH=x64"
if /I "%ARCH%"=="all" (
    call "%~f0" x86
    if errorlevel 1 exit /b 1
    call "%~f0" x64
    exit /b %errorlevel%
)
if /I not "%ARCH%"=="x86" if /I not "%ARCH%"=="x64" (
    echo [ERROR] Usage: build_installer.bat [x86^|x64^|all]
    exit /b 1
)

if defined BUILD_ROOT (
    set "ROOT=%BUILD_ROOT%"
) else (
    set "ROOT=%~dp0"
)
set "DIST=%ROOT%\dist"
set "WORK=%ROOT%\build"
set "OUTPUT=%ROOT%\Output"

if /I "%ARCH%"=="x86" (
    set "PY=%PY38_X86%"
    if not defined PY set "PY=py -3.8-32"
) else (
    set "PY=%PY38_X64%"
    if not defined PY set "PY=py -3.8-64"
)

echo ============================================
echo   Build installer - Farmandari App (%ARCH%)
echo ============================================
echo.

%PY% -c "import sys; assert sys.version_info[:2] == (3, 8), 'Python 3.8 is required for Windows 7 builds'"
if errorlevel 1 (
    echo [ERROR] Python 3.8 was not found for %ARCH%.
    echo         Set PY38_X86 / PY38_X64 to the interpreter or venv path.
    exit /b 1
)

echo [1/4] Cleaning previous %ARCH% outputs...
if exist "%DIST%\FarmandariApp-%ARCH%" rmdir /s /q "%DIST%\FarmandariApp-%ARCH%" 2>nul
if exist "%WORK%\%ARCH%" rmdir /s /q "%WORK%\%ARCH%" 2>nul
if not exist "%DIST%" mkdir "%DIST%"
if not exist "%OUTPUT%" mkdir "%OUTPUT%"

echo [2/4] Building app with PyInstaller (onedir, %ARCH%)...
set "FARMANDARI_ARCH=%ARCH%"
%PY% -m PyInstaller farmandari.spec --noconfirm --clean --distpath "%DIST%" --workpath "%WORK%\%ARCH%"
if errorlevel 1 (
    echo [ERROR] PyInstaller failed
    exit /b 1
)

if not exist "%DIST%\FarmandariApp-%ARCH%\FarmandariApp-%ARCH%.exe" (
    echo [ERROR] FarmandariApp-%ARCH%.exe was not produced
    exit /b 1
)

echo [3/4] Locating NSIS...
set "MAKENSIS="
if defined NSIS_HOME if exist "%NSIS_HOME%\makensis.exe" set "MAKENSIS=%NSIS_HOME%\makensis.exe"
if not defined MAKENSIS if exist "C:\Program Files (x86)\NSIS\makensis.exe" set "MAKENSIS=C:\Program Files (x86)\NSIS\makensis.exe"
if not defined MAKENSIS if exist "C:\Program Files\NSIS\makensis.exe" set "MAKENSIS=C:\Program Files\NSIS\makensis.exe"
if not defined MAKENSIS for %%I in (makensis.exe) do if not "%%~$PATH:I"=="" set "MAKENSIS=%%~$PATH:I"
if not defined MAKENSIS (
    echo [ERROR] NSIS not found. Install NSIS 3.x or set NSIS_HOME.
    exit /b 1
)

echo [4/4] Building installer with NSIS...
"%MAKENSIS%" /DAPP_ARCH=%ARCH% /DAPP_SRC="%DIST%\FarmandariApp-%ARCH%" /DOUTPUT_DIR="%OUTPUT%" farmandari.nsi
if errorlevel 1 (
    echo [ERROR] makensis failed
    exit /b 1
)

echo.
echo ============================================
echo   Build complete: %OUTPUT%\FarmandariSetup_1.2.0_%ARCH%.exe
echo ============================================
exit /b 0
