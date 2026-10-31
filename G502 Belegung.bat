@echo off
rem Startet die Belegungs-Oberflaeche im Browser. Fenster offen lassen, solange sie laeuft.
cd /d "%~dp0"
set "OK="
if exist .venv\Scripts\python.exe .venv\Scripts\python -c "import hid" >/dev/null 2>/dev/null && set "OK=1"
if not defined OK (
  call windows-einrichten.bat
  if errorlevel 1 exit /b 1
)
.venv\Scripts\python server.py
if errorlevel 1 pause
