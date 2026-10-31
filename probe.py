"""Schritt 1: liest aus, was Empfänger und Maus können. Schreibt nichts."""

import sys

from hidpp import FEATURE_NAMES, Device, HidppError, Receiver, find_receiver

# Entladekurve LiPo (mV -> %), wie sie Solaar für 0x1001 nutzt.
VOLTAGE_CURVE = [
    (4186, 100), (4067, 90), (3989, 80), (3922, 70), (3859, 60), (3811, 50),
    (3778, 40), (3751, 30), (3717, 20), (3671, 10), (3646, 5), (3579, 2), (3500, 0),
]


def voltage_percent(mv):
    if mv >= VOLTAGE_CURVE[0][0]:
        return 100
    for (hi_mv, hi_p), (lo_mv, lo_p) in zip(VOLTAGE_CURVE, VOLTAGE_CURVE[1:]):
        if mv >= lo_mv:
            return round(lo_p + (mv - lo_mv) * (hi_p - lo_p) / (hi_mv - lo_mv))
    return 0


def section(title):
    print(f"\n== {title}")


def try_print(label, fn):
    try:
        print(f"  {label}: {fn()}")
    except (HidppError, KeyError, TimeoutError) as e:
        print(f"  {label}: – ({e})")


def device_name(dev):
    length = dev.feature(0x0005, 0)[0]
    name = b""
    while len(name) < length:
        name += dev.feature(0x0005, 1, [len(name)])
    return name[:length].decode("ascii", "replace")


def firmware(dev):
    kinds = {0: "Firmware", 1: "Bootloader", 2: "Hardware", 3: "Touchpad", 4: "Sensor", 5: "Funk-Stack"}
    count = dev.feature(0x0003, 0)[0]
    parts = []
    for i in range(count):
        r = dev.feature(0x0003, 1, [i])
        kind = r[0] & 0x0F
        if kind == 2:
            parts.append(f"{kinds[kind]} {r[1]}")
            continue
        prefix = r[1:4].decode("ascii", "replace").strip("\0")
        build = r[6] << 8 | r[7]
        label = " ".join(filter(None, [kinds.get(kind, str(kind)), prefix]))
        parts.append(f"{label} {r[4]:02X}.{r[5]:02X}.B{build:04X}")
    return ", ".join(parts)


def battery(dev):
    if dev.has(0x1004):
        r = dev.feature(0x1004, 1)
        return f"{r[0]} %{' (lädt)' if r[2] else ''}"
    if dev.has(0x1001):
        r = dev.feature(0x1001, 0)
        mv = r[0] << 8 | r[1]
        return f"{mv} mV, ca. {voltage_percent(mv)} %{' (lädt)' if r[2] & 0x80 else ''}"
    if dev.has(0x1000):
        r = dev.feature(0x1000, 0)
        return f"{r[0]} %"
    raise KeyError("kein Akku-Feature")


def dpi(dev):
    sensors = dev.feature(0x2201, 0)[0]
    lines = []
    for s in range(sensors):
        r = dev.feature(0x2201, 1, [s])
        values = [r[i] << 8 | r[i + 1] for i in range(1, len(r) - 1, 2)]
        values = values[: values.index(0)] if 0 in values else values
        desc = []
        for v in values:
            desc.append(f"Schritt {v & 0x1FFF}" if v >> 13 == 0b111 else str(v))
        cur = dev.feature(0x2201, 2, [s])
        lines.append(
            f"Sensor {s}: aktuell {cur[1] << 8 | cur[2]}, Standard {cur[3] << 8 | cur[4]}, "
            f"möglich {' / '.join(desc)}"
        )
    return "; ".join(lines)


def report_rate(dev):
    mask = dev.feature(0x8060, 0)[0]
    rates = [1000 // (i + 1) for i in range(8) if mask & (1 << i)]
    cur = dev.feature(0x8060, 1)[0]
    return f"aktuell {1000 // cur} Hz, möglich {' / '.join(map(str, rates))} Hz"


def onboard_profiles(dev):
    d = dev.feature(0x8100, 0)
    print(
        f"  Speichermodell {d[0]}, Profilformat {d[1]}, Makroformat {d[2]}, "
        f"{d[3]} Profile (+{d[4]} ab Werk), {d[5]} Tasten, "
        f"{d[6]} Sektoren à {d[7] << 8 | d[8]} Byte"
    )
    mode = dev.feature(0x8100, 2)[0]
    print(f"  Modus: {({1: 'Onboard (Maus selbst)', 2: 'Host (Software)'}).get(mode, mode)}")
    cur = dev.feature(0x8100, 4)
    sector = cur[0] << 8 | cur[1]
    print(f"  Aktives Profil: Sektor 0x{sector:04X}{' (ab Werk)' if sector & 0x0100 else ''}")
    try_print("Aktive DPI-Stufe", lambda: dev.feature(0x8100, 0xB)[0])

    # Verzeichnis in Sektor 0: je 4 Byte (Sektor, aktiviert, reserviert), Ende 0xFFFF.
    entries = []
    for offset in (0, 16):
        chunk = dev.feature(0x8100, 5, [0, 0, 0, offset])
        for i in range(0, 16, 4):
            sec = chunk[i] << 8 | chunk[i + 1]
            if sec == 0xFFFF:
                break
            entries.append(f"0x{sec:04X} {'an' if chunk[i + 2] else 'aus'}")
        else:
            continue
        break
    print(f"  Verzeichnis: {', '.join(entries) or 'leer (Maus nutzt Werksprofile)'}")


def main():
    interfaces = find_receiver()
    if not interfaces:
        sys.exit("Kein Lightspeed-Empfänger gefunden.")
    info = interfaces[0]

    section("Empfänger")
    print(f"  {info['product_string']} 046D:{info['product_id']:04X}")
    try:
        rcv = Receiver(interfaces)
    except OSError as e:
        sys.exit(
            f"  Öffnen fehlgeschlagen: {e}\n"
            "  Vermutlich fehlt die Berechtigung „Eingabeüberwachung“ für das Terminal."
        )

    try:
        slots = []
        for slot in range(1, 7):
            p = rcv.pairing_info(slot)
            if p:
                slots.append(slot)
                print(f"  Slot {slot}: WPID 0x{p[0]:04X} {p[1] or ''}")
        if not slots:
            print("  Register 0xB5 liefert nichts, suche Gerät direkt.")
            slots = range(1, 7)

        dev = None
        for slot in slots:
            d = Device(rcv, slot)
            try:
                major, minor = d.ping()
            except (HidppError, TimeoutError) as e:
                print(f"  Slot {slot}: keine Antwort ({e})")
                continue
            print(f"  Slot {slot}: antwortet, HID++ {major}.{minor}")
            dev = d
            break
        if not dev:
            sys.exit("\nMaus antwortet nicht. Einschalten oder kurz bewegen und erneut starten.")

        section("Maus")
        try_print("Name", lambda: device_name(dev))
        try_print("Firmware", lambda: firmware(dev))
        try_print("Akku", lambda: battery(dev))
        try_print("DPI", lambda: dpi(dev))
        try_print("Abfragerate", lambda: report_rate(dev))

        section("Features")
        for idx, fid, flags, ver in dev.list_features():
            tags = [t for bit, t in ((0x80, "obsolet"), (0x40, "versteckt"), (0x20, "intern")) if flags & bit]
            print(
                f"  [{idx:2d}] 0x{fid:04X} {FEATURE_NAMES.get(fid, '?'):<28} v{ver}"
                f"{'  (' + ', '.join(tags) + ')' if tags else ''}"
            )

        section("Onboard-Profile")
        if dev.has(0x8100):
            onboard_profiles(dev)
        else:
            print("  nicht vorhanden")
    finally:
        rcv.close()


if __name__ == "__main__":
    main()
