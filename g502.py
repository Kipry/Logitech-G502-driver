"""G502 Lightspeed ohne G Hub.

    g502.py zeigen                 Maus auslesen, sichern und anzeigen
    g502.py pruefen [DATEI]        zeigen, was DATEI (Standard g502.toml) ändern würde
    g502.py schreiben [DATEI]      sichern, schreiben, nachlesen
    g502.py zurueck SICHERUNG      Verzeichnis und Profile aus einer Sicherung zurückschreiben
"""

import json
import sys
from pathlib import Path

import backup
import config
import profiles
from hidpp import connect

DEFAULT_CONFIG = Path(__file__).parent / "g502.toml"
ROM_PROFILE = profiles.ROM_BASE + 1


def plan(state, specs):
    """Liste [(Sektor, neue Bytes, Bezeichnung)] und das zu aktivierende Profil (oder None)."""
    sectors = backup.sectors_of(state)
    desc = state["description"]
    directory = profiles.parse_directory(sectors[profiles.DIRECTORY])
    enabled = {e["sector"]: e["enabled"] for e in directory}
    changes = []
    active = None

    for spec in specs:
        slot = spec["slot"]
        if not 1 <= slot <= desc["profile_count"]:
            raise config.ConfigError(f"Slot {slot}: erlaubt 1-{desc['profile_count']}")
        current = sectors.get(slot)
        # Leere oder kaputte Plätze starten vom Werksprofil.
        base = current if current and profiles.crc_ok(current) else sectors[ROM_PROFILE]
        new = config.build_profile(base, spec)
        if new != current:
            changes.append((slot, new, f"Profil {slot}"))
        if "eingeschaltet" in spec:
            enabled[slot] = spec["eingeschaltet"]
        if spec.get("aktiv"):
            active = slot
            enabled[slot] = True

    if not any(enabled.values()):
        raise config.ConfigError("Mindestens ein Profil muss eingeschaltet bleiben.")
    final_active = active if active is not None else state["active_sector"]
    if final_active < profiles.ROM_BASE and not enabled.get(final_active, False):
        raise config.ConfigError(f"Profil {final_active} ist aktiv und kann nicht ausgeschaltet werden.")
    new_dir = profiles.set_directory(sectors[profiles.DIRECTORY], enabled)
    if new_dir != sectors[profiles.DIRECTORY]:
        changes.insert(0, (profiles.DIRECTORY, new_dir, "Verzeichnis"))
    if active == state["active_sector"]:
        active = None
    return changes, active


def change_lines(state, sector, new):
    """[(Was, vorher, nachher)] für einen geänderten Sektor."""
    old = backup.sectors_of(state).get(sector)
    count = state["description"]["button_count"]
    if sector == profiles.DIRECTORY:
        before = {e["sector"]: e["enabled"] for e in profiles.parse_directory(old)}
        return [
            (f"Profil {e['sector']}", "an" if before.get(e["sector"]) else "aus", "an" if e["enabled"] else "aus")
            for e in profiles.parse_directory(new)
            if before.get(e["sector"]) != e["enabled"]
        ]
    sectors = backup.sectors_of(state)
    a = profiles.parse_profile(old, count, sectors) if old and profiles.crc_ok(old) else None
    b = profiles.parse_profile(new, count, sectors)

    def lines(p):
        if p is None:
            return {}
        out = {
            "Name": p["name"] or "–",
            "DPI": " / ".join(map(str, p["dpi"])),
            "Start-DPI": p["dpi"][p["default_dpi_index"]] if p["default_dpi_index"] < len(p["dpi"]) else "–",
            "Sniper-DPI": p["dpi"][p["sniper_dpi_index"]] if p["sniper_dpi_index"] < len(p["dpi"]) else "–",
            "Abfragerate": f"{p['report_rate_hz']} Hz",
        }
        for name, led in zip(profiles.LED_NAMES, p["leds"]):
            out[name] = led
        for i in range(count):
            out[profiles.button_label(i)] = p["buttons"][i]
            out[f"{profiles.button_label(i)} (G-Shift)"] = p["gshift_buttons"][i]
        return out

    la, lb = lines(a), lines(b)
    return [(key, str(la.get(key, "–")), str(value)) for key, value in lb.items() if la.get(key) != value]


def print_plan(state, changes, active):
    if not changes and active is None:
        print("Nichts zu ändern, Maus entspricht der Datei.")
        return
    for sector, new, label in changes:
        print(f"  {label} (Sektor 0x{sector:04X}):")
        for key, before, after in change_lines(state, sector, new):
            print(f"    {key:<22} {before}  →  {after}")
    if active is not None:
        print(f"  Aktives Profil: {state['active_sector']} → {active}")


def apply(dev, state, changes, active):
    for sector, new, label in changes:
        print(f"Schreibe {label} …", end=" ", flush=True)
        profiles.write_sector(dev, sector, new)
        check = profiles.read_sector(dev, sector, len(new))
        if check != new:
            raise RuntimeError(f"{label} liest sich anders zurück. Mit „g502.py zurueck“ die Sicherung einspielen.")
        print("ok")
    target = active if active is not None else state["active_sector"]
    # Neu auswählen, damit die Maus ein geändertes aktives Profil frisch lädt.
    if active is not None or any(s == target for s, _, _ in changes):
        dev.feature(profiles.FEATURE, 3, [target >> 8, target & 0xFF])
        print(f"Profil {target} aktiviert.")
    if state["mode"] != 1:
        dev.feature(profiles.FEATURE, 1, [1])
        print("Maus auf eigene Profile (Onboard) umgestellt.")


def cmd_check(path, write):
    specs = config.load(path)
    rcv, dev = connect()
    try:
        state = backup.read_state(dev)
        changes, active = plan(state, specs)
        print_plan(state, changes, active)
        if write and (changes or active is not None):
            backup.save(state)
            apply(dev, state, changes, active)
            print("Fertig.")
    finally:
        rcv.close()


def restore_plan(saved, state):
    """Wie plan(), aber Ziel ist eine Sicherung. Sektoren ohne Prüfsumme werden nicht geschrieben."""
    current = backup.sectors_of(state)
    changes = []
    for sector, data in sorted(backup.sectors_of(saved).items()):
        if sector >= profiles.ROM_BASE or current.get(sector) == data:
            continue
        if not profiles.crc_ok(data):
            print(f"  Sektor 0x{sector:04X} weicht ab, hat aber keine Prüfsumme (Makros?) – übersprungen.")
            continue
        changes.append((sector, data, "Verzeichnis" if sector == 0 else f"Profil {sector}"))
    active = saved["active_sector"] if saved["active_sector"] != state["active_sector"] else None
    return changes, active


def cmd_restore(path):
    saved = json.loads(Path(path).read_text(encoding="utf-8"))
    rcv, dev = connect()
    try:
        state = backup.read_state(dev)
        changes, active = restore_plan(saved, state)
        print_plan(state, changes, active)
        if changes or active is not None:
            backup.save(state)
            apply(dev, state, changes, active)
            print("Sicherung eingespielt.")
    finally:
        rcv.close()


def main():
    args = sys.argv[1:]
    try:
        if args[:1] == ["zeigen"]:
            backup.show(backup.dump_from_device())
        elif args[:1] in (["pruefen"], ["schreiben"]):
            cmd_check(args[1] if len(args) > 1 else DEFAULT_CONFIG, write=args[0] == "schreiben")
        elif args[:1] == ["zurueck"] and len(args) == 2:
            cmd_restore(args[1])
        else:
            print(__doc__)
            sys.exit(1)
    except (config.ConfigError, RuntimeError) as e:
        sys.exit(f"Fehler: {e}")


if __name__ == "__main__":
    main()
