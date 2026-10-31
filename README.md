# G502 ohne G Hub

Eigenes Werkzeug für die **Logitech G502 Lightspeed**. Belegt Tasten, DPI-Stufen, Abfragerate und Beleuchtung direkt im Speicher der Maus. Danach braucht die Maus keine Software mehr, auch nicht an einem anderen Rechner.

Getestet mit G502 Lightspeed und Lightspeed-Empfänger 046D:C539. Andere Lightspeed-Mäuse mit Onboard-Profilen (HID++ 2.0, Feature 0x8100, Profilformat 3) könnten gehen, sind aber nicht geprüft.

## Was es kann

- Tasten belegen: Tastenkürzel per Tastendruck aufnehmen, Maustasten, DPI, Profilwechsel, Medien, G-Shift
- DPI-Stufen, Start- und Sniper-DPI, Abfragerate, Beleuchtung je Profil
- Vorschau aller Änderungen vor dem Schreiben, automatische Sicherung vorher, Zurückspielen jeder Sicherung
- **Nur Mac:** Menüleisten-App, die das Mausprofil passend zum Programm im Vordergrund wechselt

## Windows

Python 3.11 oder neuer von [python.org](https://www.python.org/downloads/) installieren. Dann in PowerShell:

```powershell
irm https://raw.githubusercontent.com/Kipry/Logitech-G502-driver/main/install.ps1 | iex
```

Danach im Startmenü **„G502 Belegung“** öffnen. Die Oberfläche läuft im Browser, das schwarze Fenster offen lassen, solange sie benutzt wird. Derselbe Befehl aktualisiert eine vorhandene Installation.

Ohne PowerShell: auf GitHub „Code → Download ZIP“, entpacken, `G502 Belegung.bat` doppelklicken.

## Mac

```bash
git clone https://github.com/Kipry/Logitech-G502-driver.git ~/projects/g502
cd ~/projects/g502
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python make_app.py
```

`make_app.py` legt `/Applications/G502.app` an. Die App startet den Code aus dem geklonten Ordner, den Ordner also nicht verschieben. Nach Code-Änderungen reicht ein Neustart der App.

## Kommandozeile

```bash
.venv/bin/python probe.py                 # auslesen, was Maus und Empfänger können
.venv/bin/python g502.py zeigen           # Profile anzeigen und sichern
.venv/bin/python g502.py pruefen          # zeigen, was g502.toml ändern würde
.venv/bin/python g502.py schreiben        # g502.toml in die Maus schreiben
.venv/bin/python g502.py zurueck backups/DATEI.json
```

## Sicherheit

Geschrieben werden nur das Profilverzeichnis und die Profile. Firmware und Update-Funktionen der Maus werden nie angesprochen. Vor jedem Schreiben landet der ganze Profilspeicher in `backups/`, und nach dem Schreiben wird nachgelesen und verglichen.

Die Oberfläche läuft nur auf `127.0.0.1:8502` und nimmt Schreibbefehle nur von sich selbst an.

## Grenzen

- Makros mit mehreren Schritten werden angezeigt und bleiben erhalten, lassen sich aber nicht neu anlegen.
- Kürzel, die das System selbst abfängt (Schreibtisch wechseln, Alt+Tab …), lassen sich nicht aufnehmen. Die gibt es als feste Auswahl.
- Die Maus sendet Tasten nach Position: „cmd“ ist am Mac Cmd und unter Windows die Windows-Taste. Für Mac und PC also getrennte Profile anlegen.
