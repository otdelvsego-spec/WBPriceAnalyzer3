@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    py -3.11 -m venv .venv
    if errorlevel 1 exit /b 1
)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
if errorlevel 1 exit /b 1
pip install -r requirements-build.txt
if errorlevel 1 exit /b 1

python -m unittest discover -s tests -v
if errorlevel 1 exit /b 1
python scripts\generate_version_info.py
if errorlevel 1 exit /b 1
pyinstaller --noconfirm --clean WBPriceAnalyzer.spec
if errorlevel 1 exit /b 1

powershell -NoProfile -ExecutionPolicy Bypass -File scripts\smoke_test_windows.ps1 ^
  -ExecutablePath dist\WBPriceAnalyzer\WBPriceAnalyzer.exe
if errorlevel 1 exit /b 1

powershell -NoProfile -ExecutionPolicy Bypass -File scripts\sign_windows.ps1 ^
  -ExecutablePath dist\WBPriceAnalyzer\WBPriceAnalyzer.exe
if errorlevel 1 exit /b 1
copy /Y README_WINDOWS.txt "dist\WBPriceAnalyzer\Прочтите_перед_запуском.txt" >nul

for /f %%i in ('python -c "from wb_app import __version__; print(__version__)"') do set APP_VERSION=%%i
if not exist artifacts mkdir artifacts
powershell -NoProfile -Command ^
  "Compress-Archive -Path 'dist\WBPriceAnalyzer\*' -DestinationPath 'artifacts\WBPriceAnalyzer-Windows-x64-v%APP_VERSION%.zip' -Force"
if errorlevel 1 exit /b 1

echo.
echo Готовая программа: dist\WBPriceAnalyzer\WBPriceAnalyzer.exe
echo Архив для передачи: artifacts\WBPriceAnalyzer-Windows-x64-v%APP_VERSION%.zip
