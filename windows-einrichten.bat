@echo off
rem Python-Umgebung mit hidapi anlegen oder reparieren.
cd /d "%~dp0"
echo Ordner: %CD%
echo [1/3] Suche Python 3.11 oder neuer ...
set "PY="
rem tomllib gehoert erst ab Python 3.11 dazu.
py -3 -c "import tomllib" >/dev/null 2>/dev/null && set "PY=py -3"
if not defined PY python -c "import tomllib" >/dev/null 2>/dev/null && set "PY=python"
if not defined PY for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*" "%LOCALAPPDATA%\Python\pythoncore-3*" "%ProgramFiles%\Python3*") do if exist "%%D\python.exe" "%%D\python.exe" -c "import tomllib" >/dev/null 2>/dev/null && set PY="%%D\python.exe"
if not defined PY (
  echo Python 3.11 oder neuer wurde nicht gefunden.
  echo Bitte von https://www.python.org/downloads/ installieren und erneut starten.
  pause
  exit /b 1
)
%PY% -c "import sys; print('      gefunden:', sys.executable, sys.version.split()[0])"
echo [2/3] Lege Python-Umgebung an (.venv) ...
%PY% -m venv --clear .venv
if errorlevel 1 goto fehler
if not exist ".venv\Scripts\python.exe" (
  echo .venv\Scripts\python.exe fehlt nach dem Anlegen. Inhalt von .venv:
  dir /b /s .venv | findstr /i "python.exe"
  goto fehler
)
echo [3/3] Installiere hidapi ...
".venv\Scripts\python.exe" -m pip install --quiet --disable-pip-version-check -r requirements.txt
if errorlevel 1 goto fehler
echo Fertig eingerichtet.
exit /b 0
:fehler
echo.
echo Einrichtung fehlgeschlagen. Bitte diesen Text an Claude schicken.
pause
exit /b 1
