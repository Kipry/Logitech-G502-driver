@echo off
rem Einmalig: Python-Umgebung mit hidapi anlegen.
cd /d "%~dp0"
where py >/dev/null 2>nul
if errorlevel 1 (
  echo Python fehlt. Bitte von https://www.python.org/downloads/ installieren
  echo und dabei "Add python.exe to PATH" ankreuzen. Danach erneut starten.
  pause
  exit /b 1
)
py -3 -m venv .venv || goto fehler
.venv\Scripts\python -m pip install --quiet --upgrade pip || goto fehler
.venv\Scripts\python -m pip install --quiet -r requirements.txt || goto fehler
echo Fertig eingerichtet.
exit /b 0
:fehler
echo Einrichtung fehlgeschlagen.
pause
exit /b 1
