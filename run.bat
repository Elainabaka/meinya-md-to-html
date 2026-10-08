@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>nul
cd /d "%~dp0"
title Meinya MD to HTML

set "PY_CMD="
where py >nul 2>nul && set "PY_CMD=py"
if not defined PY_CMD (
  where python >nul 2>nul && set "PY_CMD=python"
)

if not defined PY_CMD (
  echo.
  echo [MD to HTML] Khong tim thay Python.
  echo Hay cai Python 3.10+ tu python.org, tick "Add Python to PATH", sau do chay lai run.bat.
  echo.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo [MD to HTML] Khoi tao lan dau...
  %PY_CMD% -m venv ".venv"
  if errorlevel 1 goto :error
)

set "VPY=%CD%\.venv\Scripts\python.exe"
set "VPYW=%CD%\.venv\Scripts\pythonw.exe"
if not exist "%VPYW%" set "VPYW=%VPY%"
"%VPY%" -c "import webview" >nul 2>nul
if errorlevel 1 (
  echo [MD to HTML] Dang cai dependency lan dau, can Internet 1 lan...
  "%VPY%" -m pip install --disable-pip-version-check --upgrade pip
  if errorlevel 1 goto :error
  "%VPY%" -m pip install --disable-pip-version-check -r "requirements.txt"
  if errorlevel 1 goto :error
)

if "%~1"=="" (
  rem Mo app desktop, khong console. Console tu tat sau 3s, app mo rieng.
  echo [MD to HTML] Dang mo app desktop...
  start "" "%VPYW%" "%CD%\main.py"
  ping -n 4 127.0.0.1 >nul
  tasklist /fi "imagename eq pythonw.exe" 2>nul | find /i "pythonw.exe" >nul
  if errorlevel 1 (
    echo.
    echo [MD to HTML] App khong khoi dong duoc. Chay truc tiep de xem loi:
    echo   "%VPY%" "%CD%\main.py"
    echo.
    pause
    exit /b 1
  )
  exit /b 0
)

rem Co tham so: chay CLI (keo-tha file .md vao run.bat van chay)
"%VPY%" "%CD%\md_to_html.py" %*
exit /b %ERRORLEVEL%

:error
echo.
echo [MD to HTML] Khoi dong that bai.
echo Kiem tra Python 3.10+ va Internet cho LAN DAU cai dependency.
echo Neu loi WebView, hay cap nhat Microsoft Edge WebView2 Runtime.
echo.
pause
exit /b 1
