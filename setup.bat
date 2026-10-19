@echo off
rem Double-click to install everything needed for the manim-video-win skill (no admin rights needed).
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0skill\manim-video-win\scripts\setup.ps1" %*
echo.
pause
