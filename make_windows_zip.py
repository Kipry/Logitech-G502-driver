"""Packt alles für den Windows-PC in dist/G502-Windows.zip (Ordner „G502“ im Archiv).

Auf dem PC entpacken und „G502 Belegung.bat“ doppelklicken; beim ersten Start wird
die Python-Umgebung eingerichtet. Die Mac-App-Teile bleiben draußen.
"""

import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FILES = [
    "hidpp.py", "profiles.py", "config.py", "backup.py", "g502.py", "probe.py", "server.py", "settings.py",
    "index.html", "g502.toml", "requirements.txt", "windows-einrichten.bat", "G502 Belegung.bat",
]


def main():
    target = ROOT / "dist" / "G502-Windows.zip"
    target.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
        for name in FILES:
            z.write(ROOT / name, f"G502/{name}")
        # Sicherungen mitnehmen, damit sie auch am PC zurückgespielt werden können.
        for backup in sorted((ROOT / "backups").glob("*.json")):
            z.write(backup, f"G502/backups/{backup.name}")
    print(f"Angelegt: {target}")


if __name__ == "__main__":
    main()
