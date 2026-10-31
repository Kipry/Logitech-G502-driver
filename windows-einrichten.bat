@echo off
rem Python-Umgebung mit hidapi anlegen oder reparieren.
setlocal
cd /d "%~dp0"
echo Ordner: %CD%
echo [1/3] Suche Python 3.11 bis 3.14 ...
set "PY="
call :suche
if not defined PY (
  set "PM="
  if exist "%LOCALAPPDATA%\Python\bin" set "PM=1"
  py install --help <nul >nul 2>nul && set "PM=1"
  if defined PM (
    echo       Keine passende Version installiert. Hole Python 3.14 ueber den Python Install Manager ...
    py install 3.14
    call :suche
  )
)
if not defined PY (
  echo Python 3.11 bis 3.14 wurde nicht gefunden.
  echo hidapi gibt es fuer neuere Versionen noch nicht fertig. Bitte Python 3.14 installieren:
  echo https://www.python.org/downloads/
  pause
  exit /b 1
)
echo       gefunden: %PY%
echo [2/3] Lege Python-Umgebung an (.venv) ...
"%PY%" -m venv --clear .venv
if errorlevel 1 goto fehler
if not exist ".venv\Scripts\python.exe" (
  echo .venv\Scripts\python.exe fehlt nach dem Anlegen. Gefundene python.exe in .venv:
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

:suche
rem hidapi gibt es fertig nur fuer diese Versionen. Gemerkt wird der echte Pfad der python.exe,
rem nicht die Verknuepfung in WindowsApps.
for %%V in (3.14 3.13 3.12 3.11) do if not defined PY call :frage py -%%V
for %%V in (3.14 3.13 3.12 3.11) do if not defined PY call :datei "%LOCALAPPDATA%\Python\pythoncore-%%V-64\python.exe"
for %%V in (314 313 312 311) do if not defined PY call :datei "%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe"
for %%V in (314 313 312 311) do if not defined PY call :datei "%ProgramFiles%\Python%%V\python.exe"
exit /b 0

:frage
for /f "delims=" %%P in ('%* -c "import sys; print(sys.executable)" ^<nul 2^>nul') do set "PY=%%P"
if defined PY if not exist "%PY%" set "PY="
exit /b 0

:datei
if exist "%~1" set "PY=%~1"
exit /b 0
