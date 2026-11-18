@echo off
setlocal
cd /d "%~dp0\.."

echo ==================================================
echo Smart Video Downloader 2.5.3 - Windows Build
echo Target: Windows 7 SP1 / 8 / 8.1 / 10 / 11
echo Build runtime: Python 3.8 x64
echo ==================================================

py -3.8 --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python 3.8 was not found. Install 64-bit Python 3.8 first.
    pause
    exit /b 1
)

if not exist "vendor\yt-dlp-source\yt_dlp\__init__.py" (
    echo ERROR: Tested yt-dlp package is missing from vendor\yt-dlp-source.
    pause
    exit /b 1
)
if not exist "vendor\curlcffi" (
    echo ERROR: Tested curl_cffi package is missing from vendor\curlcffi.
    pause
    exit /b 1
)

if not exist ".build-venv\Scripts\python.exe" (
    py -3.8 -m venv .build-venv
    if errorlevel 1 goto failed
)

call ".build-venv\Scripts\activate.bat"
python -m pip install --upgrade "pip<25"
if errorlevel 1 goto failed
python -m pip install -r packaging\requirements-build.txt
if errorlevel 1 goto failed

python packaging\prepare_windows_build.py
if errorlevel 1 goto failed

python -m PyInstaller --noconfirm --clean packaging\SmartVideoDownloader.spec
if errorlevel 1 goto failed

echo.
echo BUILD COMPLETED.
echo Output: dist\SmartVideoDownloader\
echo Distribute the complete folder, not the EXE alone.
echo Test on Windows 7 SP1 before declaring compatibility.
pause
exit /b 0

:failed
echo.
echo BUILD FAILED. Read the error above.
pause
exit /b 1
