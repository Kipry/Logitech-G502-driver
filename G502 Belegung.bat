@echo off
rem Startet die Belegungs-Oberflaeche im Browser. Fenster offen lassen, solange sie laeuft.
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe call windows-einrichten.bat || exit /b 1
.venv\Scripts\python server.py
if errorlevel 1 pause
