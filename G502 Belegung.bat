@echo off
rem Startet die Belegungs-Oberflaeche im Browser. Fenster offen lassen, solange sie laeuft.
cd /d "%~dp0"
if not exist "windows-einrichten.bat" (
  echo Bitte das ZIP erst entpacken und die Datei im entpackten Ordner starten.
  pause
  exit /b 1
)
set "OK="
if exist ".venv\Scripts\python.exe" ".venv\Scripts\python.exe" -c "import hid" >/dev/null 2>/dev/null && set "OK=1"
if not defined OK (
  call windows-einrichten.bat
  if errorlevel 1 exit /b 1
)
echo Starte Oberflaeche ...
".venv\Scripts\python.exe" server.py
if errorlevel 1 pause
