@echo off
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 scripts\preview_platform.py
) else (
  python scripts\preview_platform.py
)
pause
