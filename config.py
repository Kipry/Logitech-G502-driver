"""Konfigurationsdatei (TOML) in Profilsektoren übersetzen. Siehe g502.toml."""

import tomllib

from profiles import KEYS, with_crc

BUTTON_KEYS = ["links", "rechts", "mitte", "g4", "g5", "g6", "g7", "g8", "g9", "rad_rechts", "rad_links"]

PROFILE_KEYS = {
    "slot", "name", "eingeschaltet", "aktiv", "dpi", "start_dpi", "sniper_dpi", "hz",
    "logo", "streifen", "tasten", "gshift", "erlaube_links",
}

MOUSE = {"maus:links": 0x0001, "maus:rechts": 0x0002, "maus:mitte": 0x0004, "maus:zurück": 0x0008, "maus:vor": 0x0010}

SPECIAL = {
    "rad:links": 0x01, "rad:rechts": 0x02, "dpi+": 0x03, "dpi-": 0x04, "dpi-wechsel": 0x05,
    "dpi-standard": 0x06, "sniper": 0x07, "profil+": 0x08, "profil-": 0x09, "profil-wechsel": 0x0A,
    "g-shift": 0x0B, "akku": 0x0C,
}

MEDIA = {
    "medien:lauter": 0x00E9, "medien:leiser": 0x00EA, "medien:stumm": 0x00E2, "medien:play": 0x00CD,
    "medien:weiter": 0x00B5, "medien:zurück": 0x00B6, "medien:stopp": 0x00B7,
}

MOD_BITS = {
    "ctrl": 0x01, "strg": 0x01, "shift": 0x02, "alt": 0x04, "option": 0x04, "cmd": 0x08, "win": 0x08,
    "rctrl": 0x10, "rshift": 0x20, "ralt": 0x40, "rcmd": 0x80,
}

KEY_CODES = {name.lower(): code for code, name in KEYS.items() if code < 0xE0}
KEY_CODES.update({
    "space": 0x2C, "return": 0x28, "delete": 0x4C, "left": 0x50, "right": 0x4F,
    "up": 0x52, "down": 0x51, "pageup": 0x4B, "pagedown": 0x4E, "home": 0x4A, "end": 0x4D,
})

REPORT_RATES = (125, 250, 500, 1000)

MOD_NAMES = ["ctrl", "shift", "alt", "cmd", "rctrl", "rshift", "ralt", "rcmd"]


class ConfigError(Exception):
    pass


def load(path):
    with open(path, "rb") as f:
        try:
            raw = tomllib.load(f)
        except tomllib.TOMLDecodeError as e:
            raise ConfigError(f"{path}: {e}") from e
    return validate(raw.get("profil", []))


def validate(specs):
    if not isinstance(specs, list) or not all(isinstance(s, dict) for s in specs):
        raise ConfigError("Profile müssen eine Liste sein.")
    if not specs:
        raise ConfigError("Keine [[profil]]-Einträge gefunden.")
    slots = set()
    for spec in specs:
        unknown = set(spec) - PROFILE_KEYS
        if unknown:
            raise ConfigError(f"Unbekannte Einträge: {', '.join(sorted(unknown))}")
        if "slot" not in spec:
            raise ConfigError("Jedes Profil braucht „slot“ (1-5).")
        if spec["slot"] in slots:
            raise ConfigError(f"Slot {spec['slot']} kommt doppelt vor.")
        slots.add(spec["slot"])
        for table in ("tasten", "gshift"):
            unknown = set(spec.get(table, {})) - set(BUTTON_KEYS)
            if unknown:
                raise ConfigError(f"Slot {spec['slot']}: unbekannte Tasten {', '.join(sorted(unknown))}")
    if sum(bool(s.get("aktiv")) for s in specs) > 1:
        raise ConfigError("Nur ein Profil darf „aktiv = true“ haben.")
    return specs


def encode_action(text):
    t = text.strip().lower()
    if t == "aus":
        return b"\xff\xff\xff\xff"
    if t in MOUSE:
        return bytes([0x80, 0x01]) + MOUSE[t].to_bytes(2, "big")
    if t in SPECIAL:
        return bytes([0x90, SPECIAL[t], 0, 0])
    if t in MEDIA:
        return bytes([0x80, 0x03]) + MEDIA[t].to_bytes(2, "big")
    *mods, last = [p.strip() for p in t.split("+")]
    bits, key = 0, 0
    for m in mods:
        if m not in MOD_BITS:
            raise ConfigError(f"„{text}“: „{m}“ ist keine Zusatztaste (ctrl, shift, alt, cmd)")
        bits |= MOD_BITS[m]
    if last in KEY_CODES:
        key = KEY_CODES[last]
    elif last in MOD_BITS:
        bits |= MOD_BITS[last]
    else:
        raise ConfigError(f"„{text}“: Taste „{last}“ unbekannt")
    return bytes([0x80, 0x02, bits, key])


def encode_led(text):
    words = text.strip().lower().split()
    if words == ["aus"]:
        return bytes(11)
    if len(words) == 1 and words[0].startswith("#") and len(words[0]) == 7:
        return bytes([0x01]) + bytes.fromhex(words[0][1:]) + bytes(7)
    if words and words[0] == "farbwechsel":
        period = int(words[1]) if len(words) > 1 else 8000
        brightness = int(words[2]) if len(words) > 2 else 100
        if not (1000 <= period <= 20000 and 0 <= brightness <= 100):
            raise ConfigError(f"„{text}“: Dauer 1000-20000 ms, Helligkeit 0-100")
        return bytes([0x03, 0, 0, 0, 0, 0]) + period.to_bytes(2, "big") + bytes([brightness, 0, 0])
    raise ConfigError(f"LED „{text}“: erlaubt sind aus, #rrggbb, farbwechsel [ms] [helligkeit]")


def build_profile(base, spec):
    """Neuer Profilsektor: base mit den Angaben aus spec überschrieben, Prüfsumme neu."""
    data = bytearray(base)
    slot = spec["slot"]

    def fail(msg):
        raise ConfigError(f"Slot {slot}: {msg}")

    if "hz" in spec:
        if spec["hz"] not in REPORT_RATES:
            fail(f"hz muss eins von {REPORT_RATES} sein")
        data[0] = 1000 // spec["hz"]

    dpis = [int.from_bytes(data[3 + 2 * i : 5 + 2 * i], "little") for i in range(5)]
    dpis = [d for d in dpis if d]
    if "dpi" in spec:
        dpis = spec["dpi"]
        if not 1 <= len(dpis) <= 5:
            fail("dpi braucht 1 bis 5 Werte")
        for d in dpis:
            if not (100 <= d <= 25600 and d % 50 == 0):
                fail(f"DPI {d}: erlaubt 100-25600 in 50er-Schritten")
        data[3:13] = b"".join(d.to_bytes(2, "little") for d in dpis + [0] * (5 - len(dpis)))
        data[1] = 0
        data[2] = dpis.index(min(dpis))
    for key, pos in (("start_dpi", 1), ("sniper_dpi", 2)):
        if key in spec:
            if spec[key] not in dpis:
                fail(f"{key} {spec[key]} steht nicht in dpi {dpis}")
            data[pos] = dpis.index(spec[key])

    if "name" in spec:
        name = spec["name"]
        if len(name) > 24:
            fail("name höchstens 24 Zeichen")
        data[160:208] = name.encode("utf-16-le").ljust(48, b"\0")

    tasten = spec.get("tasten", {})
    if "links" in tasten and encode_action(tasten["links"]) != encode_action("maus:links") and not spec.get("erlaube_links"):
        fail("Linke Taste umbelegen nur mit „erlaube_links = true“")
    for name, action in tasten.items():
        i = BUTTON_KEYS.index(name)
        binding = encode_action(action)
        data[32 + 4 * i : 36 + 4 * i] = binding
        # G-Shift folgt der normalen Belegung, außer [gshift] sagt etwas anderes.
        data[96 + 4 * i : 100 + 4 * i] = binding
    for name, action in spec.get("gshift", {}).items():
        i = BUTTON_KEYS.index(name)
        data[96 + 4 * i : 100 + 4 * i] = encode_action(action)

    for i, key in enumerate(("logo", "streifen")):
        if key in spec:
            data[208 + 11 * i : 219 + 11 * i] = encode_led(spec[key])

    return with_crc(data)


def binding_to_action(b):
    """Umkehrung von encode_action; None für Makros und Unbekanntes (nicht bearbeitbar)."""
    if b == b"\xff\xff\xff\xff":
        return "aus"
    if b[0] == 0x90:
        return next((n for n, c in SPECIAL.items() if c == b[1]), None)
    if b[0] != 0x80:
        return None
    code = b[2] << 8 | b[3]
    if b[1] == 0x01:
        return next((n for n, m in MOUSE.items() if m == code), None)
    if b[1] == 0x03:
        return next((n for n, c in MEDIA.items() if c == code), None)
    if b[1] == 0x02:
        parts = [MOD_NAMES[i] for i in range(8) if b[2] & (1 << i)]
        if b[3]:
            if b[3] not in KEYS or b[3] >= 0xE0:
                return None
            parts.append(KEYS[b[3]].lower())
        return "+".join(parts) or None
    return None


def led_to_text(led):
    """Umkehrung von encode_led; None für Effekte, die die Datei nicht beschreiben kann."""
    if led[0] == 0x00:
        return "aus"
    if led[0] == 0x01:
        return "#" + led[1:4].hex()
    if led[0] == 0x03:
        return f"farbwechsel {led[6] << 8 | led[7]} {led[8]}"
    return None
