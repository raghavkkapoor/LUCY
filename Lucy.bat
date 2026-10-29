@echo off

:: Check for administrative privileges
net session >nul 2>&1
if %errorLevel% == 0 (
    goto :admin
) else (
    goto :elevate
)

:elevate
:: Re-launch the batch file as administrator
powershell Start-Process -FilePath "%0" -Verb RunAs
exit


:admin
:: Batch Script to Check, Download, Install, and Add Python 3.11.0 to PATH
:: Run this script as Administrator for best results.

TITLE "Lucy Setup & Launcher"
color 0B

set "PYTHON_VERSION=3.11.0"
set "INSTALLER_NAME=python-3.11.0-amd64.exe"
set "DOWNLOAD_URL=https://www.python.org/ftp/python/3.11.0/%INSTALLER_NAME%"
set "DOWNLOAD_PATH=%TEMP%\%INSTALLER_NAME%"
set "ALREADY_INSTALLED=0"

echo Setting up lucy...
echo.


:: 1. Check if Python 3.11.x is active in PATH
python --version >nul 2>&1
if %errorLevel% equ 0 (
    for /f "tokens=2" %%i in ('python --version 2^>^&1') do set "INSTALLED_VER=%%i"
    echo > Python found in PATH: %INSTALLED_VER%
    echo.
    echo %INSTALLED_VER% | findstr /b "3.11." >nul
    echo.

    if %errorLevel% equ 0 (
        set "ALREADY_INSTALLED=1"
    )
)

:: 2. If not found in PATH, check Windows Registry for 3.11 installation
if "%ALREADY_INSTALLED%"=="0" (
    reg query "HKLM\SOFTWARE\Python\PythonCore\3.11" >nul 2>&1
    if %errorLevel% equ 0 set "ALREADY_INSTALLED=1"
)
if "%ALREADY_INSTALLED%"=="0" (
    reg query "HKCU\SOFTWARE\Python\PythonCore\3.11" >nul 2>&1
    if %errorLevel% equ 0 set "ALREADY_INSTALLED=1"
)

:: If Python 3.11 is already detected, skip
if "%ALREADY_INSTALLED%"=="1" (
    echo > Python 3.11.0 already exists.
    echo.
    goto END
)

echo > Downloading Python %PYTHON_VERSION% from python.org...
echo.

powershell -Command "Invoke-WebRequest -Uri '%DOWNLOAD_URL% -OutFile '%DOWNLOAD_PATH%'" 2>nul
:: Fallback download method using .NET if PowerShell web request fails
if not exist "%DOWNLOAD_PATH%" (
    powershell -Command "(New-Object System.Net.WebClient).DownloadFile('%DOWNLOAD_URL%', '%DOWNLOAD_PATH%')"
)

if not exist "%DOWNLOAD_PATH%" (
    echo > ERROR: Failed to download the Python installer. Please check your internet connection and try again.
    echo.
    goto END
)

echo [2/3] Running installer (Adding to PATH, installing pip, all users)...
echo.
start /wait "" "%DOWNLOAD_PATH%" /quiet InstallAllUsers=1 PrependPath=1 Include_pip=1

echo [3/3] Cleaning up temporary files...
echo.
if exist "%DOWNLOAD_PATH%" del "%DOWNLOAD_PATH%"

echo > Python 3.11.0 Installed.
echo.

:END

:: run lucy
echo > Checking and installing dependencies...
echo.
cd /d "%~dp0"
py -3.11 -m pip install -r requirements.txt
echo.

echo Launching LUCY...
echo.
start "LUCY v0.1.0" py -3.11 main.py

::TODO: REMOVE BEFORE PUBLISH
::pause