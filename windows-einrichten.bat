@echo off
rem Python-Umgebung mit hidapi anlegen oder reparieren.
cd /d "%~dp0"
set "PY="
rem Gesucht wird Python 3.11 oder neuer (tomllib gehoert erst ab 3.11 dazu).
py -3 -c "import tomllib" >/dev/null 2>/dev/null && set "PY=py -3"
if not defined PY python -c "import tomllib" >/dev/null 2>/dev/null && set "PY=python"
if not defined PY for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do if exist "%%D\python.exe" "%%D\python.exe" -c "import tomllib" >/dev/null 2>/dev/null && set PY="%%D\python.exe"
if not defined PY for /d %%D in ("%ProgramFiles%\Python3*") do if exist "%%D\python.exe" "%%D\python.exe" -c "import tomllib" >/dev/null 2>/dev/null && set PY="%%D\python.exe"
if not defined PY (
  echo Python 3.11 oder neuer wurde nicht gefunden.
  echo Bitte von https://www.python.org/downloads/ installieren und erneut starten.
  pause
  exit /b 1
)
echo Verwende Python: %PY%
%PY% -m venv --clear .venv || goto fehler
.venv\Scripts\python -m pip install --quiet --upgrade pip || goto fehler
.venv\Scripts\python -m pip install --quiet -r requirements.txt || goto fehler
echo Fertig eingerichtet.
exit /b 0
:fehler
echo Einrichtung fehlgeschlagen.
pause
exit /b 1
