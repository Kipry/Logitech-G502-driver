"""Onboard-Profile (Feature 0x8100): Speicher lesen und Profilformat 3 dekodieren.

Aufbau eines Profilsektors (255 Byte bei der G502 Lightspeed):
    0      Abfrageintervall in ms
    1      Standard-DPI-Stufe
    2      DPI-Stufe bei gehaltener Sniper-Taste
    3-12   5 DPI-Stufen, je u16 little endian, 0 = unbenutzt
    13-15  Profilfarbe RGB
    16     Energiemodus
    17     Angle Snapping
    28-31  Zeit bis Energiesparen / Ausschalten, je u16 little endian
    32     16 Tastenbelegungen à 4 Byte
    96     16 Belegungen bei gehaltener G-Shift-Taste
    160    Name, UTF-16 little endian, 24 Zeichen
    208    2 LED-Einstellungen à 11 Byte (Logo, Seitenstreifen)
    230    2 LED-Einstellungen für G-Shift
    253    CRC-CCITT über Byte 0-252, big endian
"""

from hidpp import HidppError

FEATURE = 0x8100
DIRECTORY = 0x0000
ROM_BASE = 0x0100

# Reihenfolge laut Werksprofil (0x0101).
BUTTON_NAMES = ["Links", "Rechts", "Mitte", "G4", "G5", "G6", "G7", "G8", "G9", "Rad →", "Rad ←"]

MOUSE_BUTTONS = {0x0001: "Links", 0x0002: "Rechts", 0x0004: "Mitte", 0x0008: "Zurück", 0x0010: "Vor"}

SPECIALS = {
    0x01: "Rad links",
    0x02: "Rad rechts",
    0x03: "DPI hoch",
    0x04: "DPI runter",
    0x05: "DPI durchschalten",
    0x06: "DPI Standard",
    0x07: "Sniper (DPI halten)",
    0x08: "Profil vor",
    0x09: "Profil zurück",
    0x0A: "Profil durchschalten",
    0x0B: "G-Shift",
    0x0C: "Akkustand anzeigen",
}

MODIFIERS = ["Ctrl", "Shift", "Alt", "Cmd", "RCtrl", "RShift", "RAlt", "RCmd"]

KEYS = {
    **{0x04 + i: chr(ord("a") + i) for i in range(26)},
    **{0x1E + i: str((i + 1) % 10) for i in range(10)},
    0x28: "Enter", 0x29: "Esc", 0x2A: "Backspace", 0x2B: "Tab", 0x2C: "Leertaste",
    0x2D: "-", 0x2E: "=", 0x2F: "[", 0x30: "]", 0x31: "\\", 0x33: ";", 0x34: "'",
    0x35: "`", 0x36: ",", 0x37: ".", 0x38: "/", 0x39: "CapsLock",
    **{0x3A + i: f"F{i + 1}" for i in range(12)},
    0x46: "Druck", 0x47: "Rollen", 0x48: "Pause", 0x49: "Einfg", 0x4A: "Pos1",
    0x4B: "BildAuf", 0x4C: "Entf", 0x4D: "Ende", 0x4E: "BildAb",
    0x4F: "Rechts", 0x50: "Links", 0x51: "Runter", 0x52: "Hoch", 0x64: "<",
    **{0x68 + i: f"F{i + 13}" for i in range(12)},
    **{0xE0 + i: m for i, m in enumerate(["Ctrl", "Shift", "Alt", "Cmd", "RCtrl", "RShift", "RAlt", "RCmd"])},
}

CONSUMER = {
    0x00B5: "Nächster Titel", 0x00B6: "Voriger Titel", 0x00B7: "Stopp",
    0x00CD: "Play/Pause", 0x00E2: "Stumm", 0x00E9: "Lauter", 0x00EA: "Leiser",
}

LED_NAMES = ["Logo", "Streifen"]

# Makrobefehle ohne Parameter (0x01 = nichts tun, wird übersprungen).
MACRO_FLOW = {0x02: "bis Loslassen warten", 0x03: "wiederholen bis Loslassen", 0x04: "wiederholen"}


def crc_ccitt(data):
    crc = 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else crc << 1
            crc &= 0xFFFF
    return crc


def description(dev):
    d = dev.feature(FEATURE, 0)
    return {
        "memory_model": d[0],
        "profile_format": d[1],
        "macro_format": d[2],
        "profile_count": d[3],
        "rom_profile_count": d[4],
        "button_count": d[5],
        "sector_count": d[6],
        "sector_size": d[7] << 8 | d[8],
    }


def read_sector(dev, sector, size):
    """Liest einen ganzen Sektor in 16-Byte-Stücken; das letzte Stück endet genau am Sektorende."""

    def chunk(offset):
        return dev.feature(FEATURE, 5, [sector >> 8, sector & 0xFF, offset >> 8, offset & 0xFF])[:16]

    data = b"".join(chunk(o) for o in range(0, size - 16, 16))
    return data[: size - 16] + chunk(size - 16)


def read_all(dev, desc):
    """Alle Sektoren des Nutzerspeichers plus Werksprofile. Nicht lesbare werden übersprungen."""
    numbers = list(range(desc["sector_count"]))
    numbers += [ROM_BASE + i + 1 for i in range(desc["rom_profile_count"])]
    sectors = {}
    for n in numbers:
        try:
            sectors[n] = read_sector(dev, n, desc["sector_size"])
        except HidppError:
            pass
    return sectors


def crc_ok(data):
    return crc_ccitt(data[:-2]) == int.from_bytes(data[-2:], "big")


def with_crc(data):
    """Ersetzt die letzten zwei Byte durch die Prüfsumme der übrigen."""
    body = bytes(data[:-2])
    return body + crc_ccitt(body).to_bytes(2, "big")


def write_sector(dev, sector, data):
    """Schreibt einen ganzen Sektor (Länge = Sektorgröße, Prüfsumme muss schon stimmen)."""
    size = len(data)
    dev.feature(FEATURE, 6, [sector >> 8, sector & 0xFF, 0, 0, size >> 8, size & 0xFF])
    for offset in range(0, size, 16):
        dev.feature(FEATURE, 7, data[offset : offset + 16].ljust(16, b"\0"))
    dev.feature(FEATURE, 8, timeout=3.0)


def set_directory(data, enabled):
    """Verzeichnis mit neuen Ein/Aus-Werten {Sektor: bool}; fehlende Einträge werden angehängt."""
    data = bytearray(data)
    rest = dict(enabled)
    end = 0
    for i in range(0, len(data) - 3, 4):
        sector = data[i] << 8 | data[i + 1]
        if sector == 0xFFFF:
            end = i
            break
        if sector in rest:
            data[i + 2] = int(rest.pop(sector))
    for sector, on in sorted(rest.items()):
        data[end : end + 4] = bytes([sector >> 8, sector & 0xFF, int(on), 0xFF])
        end += 4
    return with_crc(data)


def parse_directory(data):
    entries = []
    for i in range(0, len(data) - 3, 4):
        sector = data[i] << 8 | data[i + 1]
        if sector == 0xFFFF:
            break
        entries.append({"sector": sector, "enabled": bool(data[i + 2])})
    return entries


def key_name(code):
    return KEYS.get(code, f"0x{code:02X}")


def read_macro(sectors, sector, offset, limit=200):
    """Folgt dem Makro-Bytestrom ab (Sektor, Position) über Sprünge und liefert die Schritte."""
    steps = []
    data = sectors.get(sector)
    while data is not None and len(steps) < limit:
        op = data[offset]
        if op == 0xFF:
            break
        if op in (0x43, 0x44):
            steps.append(("drücken" if op == 0x43 else "loslassen", data[offset + 2]))
            offset += 3
        elif op == 0x40:
            steps.append(("warten", data[offset + 1] << 8 | data[offset + 2]))
            offset += 3
        elif op == 0x60:
            sector = data[offset + 1] << 8 | data[offset + 2]
            offset = data[offset + 3] << 8 | data[offset + 4]
            data = sectors.get(sector)
        elif op == 0x01:
            offset += 1
        elif op in MACRO_FLOW:
            steps.append((MACRO_FLOW[op], None))
            offset += 1
        else:
            steps.append(("unbekannt", op))
            break
    return steps


def describe_macro(steps):
    """Fasst Drücken/Loslassen zu Kombinationen zusammen: „Cmd+l, Shift+Cmd+Enter“."""
    parts, held, chord = [], set(), []
    for kind, value in steps:
        if kind == "drücken":
            held.add(value)
            chord.append(key_name(value))
        elif kind == "loslassen":
            held.discard(value)
            if not held and chord:
                parts.append("+".join(chord))
                chord = []
        elif kind == "warten":
            # Kurze Pausen zwischen Tasten sind nur Abstand, längere gehören zum Ablauf.
            if value > 100 and not held:
                parts.append(f"{value} ms Pause")
        elif kind == "unbekannt":
            parts.append(f"unbekannter Befehl 0x{value:02X}")
        else:
            parts.append(kind)
    if chord:
        parts.append("+".join(chord) + " (bleibt gedrückt)")
    return "Makro " + ", ".join(parts)


def describe_binding(b, sectors=None):
    if b == b"\xff\xff\xff\xff":
        return "Aus"
    kind = b[0]
    if kind == 0x80:
        sub = b[1]
        if sub == 0x00:
            return "Aus"
        if sub == 0x01:
            mask = b[2] << 8 | b[3]
            return "Maustaste " + "+".join(n for m, n in MOUSE_BUTTONS.items() if mask & m) if mask else "Aus"
        if sub == 0x02:
            mods = [MODIFIERS[i] for i in range(8) if b[2] & (1 << i)]
            key = key_name(b[3]) if b[3] else None
            return "Tastatur " + "+".join(mods + ([key] if key else []))
        if sub == 0x03:
            code = b[2] << 8 | b[3]
            return "Medien " + CONSUMER.get(code, f"0x{code:04X}")
    if kind == 0x90:
        return SPECIALS.get(b[1], f"Sonderfunktion 0x{b[1]:02X}")
    if kind == 0x00:
        if sectors is None:
            return f"Makro (Sektor 0x{b[1]:02X}, Position {b[3]})"
        return describe_macro(read_macro(sectors, b[1], b[3]))
    return f"unbekannt {b.hex(' ')}"


def describe_led(led):
    mode = led[0]
    if mode == 0x00:
        return "aus"
    if mode == 0x01:
        return f"fest #{led[1]:02X}{led[2]:02X}{led[3]:02X}"
    if mode == 0x03:
        return f"Farbwechsel, {led[6] << 8 | led[7]} ms, Helligkeit {led[8]} %"
    if mode == 0x0A:
        return f"Atmen #{led[1]:02X}{led[2]:02X}{led[3]:02X}, {led[4] << 8 | led[5]} ms, Helligkeit {led[7]} %"
    if mode == 0xFF:
        return "unverändert"
    return f"Modus 0x{mode:02X} ({led.hex(' ')})"


def parse_profile(data, button_count, sectors=None):
    dpis = [int.from_bytes(data[3 + 2 * i : 5 + 2 * i], "little") for i in range(5)]
    raw_name = data[160:208]
    name = None
    if raw_name.strip(b"\xff"):
        name = raw_name.decode("utf-16-le", "replace").split("\0")[0] or None
    return {
        "report_rate_hz": 1000 // max(1, data[0]),
        "dpi": [d for d in dpis if d],
        "default_dpi_index": data[1],
        "sniper_dpi_index": data[2],
        "color": data[13:16].hex(),
        "name": name,
        "buttons": [describe_binding(data[32 + 4 * i : 36 + 4 * i], sectors) for i in range(button_count)],
        "gshift_buttons": [describe_binding(data[96 + 4 * i : 100 + 4 * i], sectors) for i in range(button_count)],
        "leds": [describe_led(data[208 + 11 * i : 219 + 11 * i]) for i in range(2)],
        "crc_ok": crc_ok(data),
    }


def button_label(i):
    return BUTTON_NAMES[i] if i < len(BUTTON_NAMES) else f"Taste {i + 1}"


def read_names(dev, desc):
    """Schnell: aktives Profil und {Sektor: (Name, eingeschaltet)} ohne ganze Sektoren zu lesen."""

    def chunk(sector, offset):
        return dev.feature(FEATURE, 5, [sector >> 8, sector & 0xFF, offset >> 8, offset & 0xFF])[:16]

    directory = parse_directory(chunk(DIRECTORY, 0) + chunk(DIRECTORY, 16))
    names = {}
    for e in directory:
        raw = chunk(e["sector"], 160) + chunk(e["sector"], 176) + chunk(e["sector"], 192)
        name = raw.decode("utf-16-le", "replace").split("\0")[0] if raw.strip(b"\xff") else ""
        names[e["sector"]] = (name, e["enabled"])
    cur = dev.feature(FEATURE, 4)
    return cur[0] << 8 | cur[1], names


def set_active(dev, sector):
    dev.feature(FEATURE, 3, [sector >> 8, sector & 0xFF])
