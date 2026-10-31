# Installiert oder aktualisiert G502 unter Windows.
#   irm https://raw.githubusercontent.com/Kipry/Logitech-G502-driver/main/install.ps1 | iex
# Legt alles in %LOCALAPPDATA%\G502 ab und einen Eintrag "G502 Belegung" im Startmenue.
# Sicherungen (backups) und die Python-Umgebung bleiben bei einer Aktualisierung erhalten.

$ErrorActionPreference = 'Stop'
$repo = 'https://github.com/Kipry/Logitech-G502-driver/archive/refs/heads/main.zip'
$dest = Join-Path $env:LOCALAPPDATA 'G502'

if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    Write-Host 'Python fehlt. Bitte von https://www.python.org/downloads/ installieren'
    Write-Host '(dabei "Add python.exe to PATH" ankreuzen) und diesen Befehl erneut ausfuehren.'
    return
}

Write-Host 'Lade G502 herunter ...'
$zip = Join-Path $env:TEMP 'g502-main.zip'
$unpacked = Join-Path $env:TEMP 'g502-main'
Invoke-WebRequest $repo -OutFile $zip -UseBasicParsing
Remove-Item $unpacked -Recurse -Force -ErrorAction SilentlyContinue
Expand-Archive $zip $unpacked
$src = (Get-ChildItem $unpacked -Directory | Select-Object -First 1).FullName

New-Item -ItemType Directory -Force $dest | Out-Null
Copy-Item (Join-Path $src '*') $dest -Recurse -Force
Remove-Item $zip, $unpacked -Recurse -Force

Write-Host 'Richte Python-Umgebung ein ...'
& (Join-Path $dest 'windows-einrichten.bat')
if ($LASTEXITCODE -ne 0) { throw 'Einrichtung fehlgeschlagen.' }

$startMenu = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs'
$shortcut = (New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $startMenu 'G502 Belegung.lnk'))
$shortcut.TargetPath = Join-Path $dest 'G502 Belegung.bat'
$shortcut.WorkingDirectory = $dest
$shortcut.Description = 'Logitech G502 Lightspeed belegen'
$shortcut.Save()

Write-Host ''
Write-Host "Fertig. G502 liegt in $dest."
Write-Host 'Starten ueber das Startmenue: "G502 Belegung".'
