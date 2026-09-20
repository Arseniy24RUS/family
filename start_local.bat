@echo off
cd /d "%~dp0"
echo Open http://localhost:8080/ in your browser.
echo Press Ctrl+C to stop the local server.
where py >nul 2>nul
if %ERRORLEVEL% EQU 0 (
  py -3 -m http.server 8080 --directory docs
) else (
  python -m http.server 8080 --directory docs
)
pause
