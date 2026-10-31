"""Schritt 2: sichert den ganzen Profilspeicher der Maus und zeigt die Profile lesbar an.

    backup.py               Maus auslesen, Sicherung in backups/ ablegen, anzeigen
    backup.py DATEI.json    vorhandene Sicherung nur anzeigen
"""

import json
import sys
from datetime import datetime
from pathlib import Path

import profiles
from probe import device_name, firmware
from hidpp import connect

BACKUP_DIR = Path(__file__).parent / "backups"


def read_state(dev):
    """Ganzer Profilspeicher samt Modus und aktivem Profil, in der Form einer Sicherung."""
    desc = profiles.description(dev)
    if desc["profile_format"] != 3:
        print(f"Achtung: Profilformat {desc['profile_format']}, dekodiert wird Format 3.")
    print(f"Lese {desc['sector_count']} Sektoren à {desc['sector_size']} Byte …")
    sectors = profiles.read_all(dev, desc)
    mode = dev.feature(profiles.FEATURE, 2)[0]
    cur = dev.feature(profiles.FEATURE, 4)
    return {
        "created": datetime.now().isoformat(timespec="seconds"),
        "device": {"index": dev.index, "name": device_name(dev), "firmware": firmware(dev)},
        "description": desc,
        "mode": mode,
        "active_sector": cur[0] << 8 | cur[1],
        "sectors": {f"0x{n:04X}": data.hex() for n, data in sectors.items()},
    }


def sectors_of(state):
    return {int(k, 16): bytes.fromhex(v) for k, v in state["sectors"].items()}


def save(state):
    BACKUP_DIR.mkdir(exist_ok=True)
    path = BACKUP_DIR / f"{datetime.now():%Y-%m-%d_%H%M%S}.json"
    path.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Gesichert: {path}")
    return path


def dump_from_device():
    rcv, dev = connect()
    try:
        state = read_state(dev)
    finally:
        rcv.close()
    save(state)
    return state


def show(backup):
    desc = backup["description"]
    sectors = sectors_of(backup)
    size = desc["sector_size"]

    directory = profiles.parse_directory(sectors.get(profiles.DIRECTORY, b""))
    profile_sectors = {e["sector"] for e in directory}

    used = []
    for n, data in sorted(sectors.items()):
        if data == b"\xff" * size:
            continue
        if n == profiles.DIRECTORY:
            kind = "Verzeichnis"
        elif n in profile_sectors:
            kind = "Profil"
        elif n > profiles.ROM_BASE:
            kind = "Werk"
        else:
            kind = "Makros"
        # Makro-Sektoren und Werksprofil tragen keine Prüfsumme.
        if kind in ("Verzeichnis", "Profil") and not profiles.crc_ok(data):
            kind += ", CRC falsch"
        used.append(f"0x{n:04X} {kind}")
    print(f"\n{backup['device']['name']}, {len(sectors)} Sektoren gelesen")
    print(f"  belegt: {', '.join(used)}")
    entries = [(e["sector"], e["enabled"]) for e in directory]
    entries += [(n, True) for n in sorted(sectors) if n > profiles.ROM_BASE]

    for sector, enabled in entries:
        data = sectors.get(sector)
        if not data:
            print(f"\n== Sektor 0x{sector:04X}: nicht gelesen")
            continue
        p = profiles.parse_profile(data, desc["button_count"], sectors)
        tags = []
        if sector > profiles.ROM_BASE:
            tags.append("ab Werk")
        if not enabled:
            tags.append("aus")
        if sector == backup["active_sector"]:
            tags.append("aktiv")
        if not p["crc_ok"] and sector < profiles.ROM_BASE:
            tags.append("CRC falsch")
        print(f"\n== Profil 0x{sector:04X} „{p['name'] or 'ohne Namen'}“{'  [' + ', '.join(tags) + ']' if tags else ''}")
        dpis = [f"[{d}]" if i == p["default_dpi_index"] else str(d) for i, d in enumerate(p["dpi"])]
        sniper = p["dpi"][p["sniper_dpi_index"]] if p["sniper_dpi_index"] < len(p["dpi"]) else "–"
        print(f"  DPI {' / '.join(dpis)}, Sniper {sniper}, {p['report_rate_hz']} Hz")
        print(f"  LEDs: {', '.join(f'{n} {l}' for n, l in zip(profiles.LED_NAMES, p['leds']))}")
        for i, action in enumerate(p["buttons"]):
            alt = p["gshift_buttons"][i]
            extra = f"   (G-Shift: {alt})" if alt != action else ""
            print(f"  {profiles.button_label(i):<10} {action}{extra}")


def main():
    if len(sys.argv) > 1:
        show(json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")))
    else:
        show(dump_from_device())


if __name__ == "__main__":
    main()
