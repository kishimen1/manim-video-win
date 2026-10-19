@echo off
rem Run build.py with uv-managed Python 3.12 (no system Python needed)
setlocal
set "UV=uv"
where uv >nul 2>nul || set "UV=%USERPROFILE%\.local\bin\uv.exe"
"%UV%" run --quiet --no-project --python 3.12 "%~dp0build.py" %*
exit /b %ERRORLEVEL%
