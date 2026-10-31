"""Minimaler HID++-Zugriff auf Logitech-Lightspeed-Empfänger über hidapi.

HID++ 1.0: Register des Empfängers (sub 0x80-0x83).
HID++ 2.0: Features des Geräts, angesprochen über Feature-Index und Funktion.
"""

import threading
import time

import hid

LOGI_VID = 0x046D
RECEIVER_PIDS = (0xC539, 0xC53F, 0xC547, 0xC54D)
RECEIVER_INDEX = 0xFF

SHORT, LONG = 0x10, 0x11
SIZES = {SHORT: 7, LONG: 20}
SW_ID = 0x0A

# Nur ein Zugriff auf den Empfänger zur Zeit (Oberfläche und Profilwechsel laufen in eigenen Threads).
LOCK = threading.RLock()

HIDPP10_ERRORS = {
    0x01: "invalid sub id",
    0x02: "invalid address",
    0x03: "invalid value",
    0x04: "connect fail",
    0x05: "too many devices",
    0x06: "already exists",
    0x07: "busy",
    0x08: "unknown device",
    0x09: "resource error",
    0x0A: "request unavailable",
    0x0B: "invalid param value",
    0x0C: "wrong pin code",
}

HIDPP20_ERRORS = {
    0x01: "unknown",
    0x02: "invalid argument",
    0x03: "out of range",
    0x04: "hardware error",
    0x05: "logitech internal",
    0x06: "invalid feature index",
    0x07: "invalid function",
    0x08: "busy",
    0x09: "unsupported",
}

FEATURE_NAMES = {
    0x0000: "Root",
    0x0001: "FeatureSet",
    0x0002: "FeatureInfo",
    0x0003: "DeviceFwVersion",
    0x0005: "DeviceName",
    0x0007: "DeviceFriendlyName",
    0x0020: "ConfigChange",
    0x00C2: "DfuControlSigned",
    0x00D0: "Dfu",
    0x1000: "BatteryStatus",
    0x1001: "BatteryVoltage",
    0x1004: "UnifiedBattery",
    0x1300: "LedControl",
    0x1802: "DeviceReset",
    0x1803: "GpioAccess",
    0x1806: "ConfigurableDeviceProperties",
    0x1801: "ManufacturingMode",
    0x1805: "OobState",
    0x1830: "PowerModes",
    0x1890: "RfTest",
    0x18A1: "LedTest",
    0x1B04: "ReprogControlsV4",
    0x1D4B: "WirelessDeviceStatus",
    0x1E00: "EnableHiddenFeatures",
    0x1E22: "SpiDirectAccess",
    0x1EB0: "TdeAccess",
    0x1F20: "AdcMeasurement",
    0x2201: "AdjustableDpi",
    0x2202: "ExtendedAdjustableDpi",
    0x2205: "PointerMotionScaling",
    0x2121: "HiResWheel",
    0x2250: "AnalysisMode",
    0x8060: "ReportRate",
    0x8061: "ExtendedReportRate",
    0x8070: "ColorLedEffects",
    0x8071: "RgbEffects",
    0x8081: "PerKeyLighting",
    0x8090: "ModeStatus",
    0x8100: "OnboardProfiles",
    0x8110: "MouseButtonSpy",
}


class HidppError(Exception):
    def __init__(self, protocol, code):
        table = HIDPP10_ERRORS if protocol == 1 else HIDPP20_ERRORS
        self.protocol = protocol
        self.code = code
        super().__init__(f"HID++ {protocol}.0 Fehler 0x{code:02X} ({table.get(code, '?')})")


def find_receiver():
    """HID++-Schnittstellen (Usage Page 0xFF00) des ersten Empfängers, leer wenn keiner da ist.

    macOS und Linux liefern kurze und lange Reports über einen Pfad, Windows über je
    einen eigenen (Usage 0x0001 kurz, 0x0002 lang).
    """
    candidates = [
        d
        for d in hid.enumerate(LOGI_VID, 0)
        if d["product_id"] in RECEIVER_PIDS and d["usage_page"] == 0xFF00 and d["usage"] in (0x0001, 0x0002)
    ]
    if not candidates:
        return []
    first = candidates[0]["product_id"]
    return [d for d in candidates if d["product_id"] == first]


class Receiver:
    def __init__(self, interfaces):
        LOCK.acquire()
        opened = {}
        try:
            self.handles = {}
            for info in interfaces:
                path = info["path"]
                if path not in opened:
                    dev = hid.device()
                    dev.open_path(path)
                    opened[path] = dev
                self.handles[SHORT if info["usage"] == 0x0001 else LONG] = opened[path]
            if not opened:
                raise OSError("Keine HID++-Schnittstelle gefunden")
            for report in (SHORT, LONG):
                self.handles.setdefault(report, next(iter(opened.values())))
            self.devices = list(opened.values())
        except BaseException:
            for dev in opened.values():
                dev.close()
            LOCK.release()
            raise

    def close(self):
        try:
            for dev in self.devices:
                dev.close()
        finally:
            LOCK.release()

    def _read(self, timeout_ms):
        if len(self.devices) == 1:
            data = self.devices[0].read(64, timeout_ms)
            return bytes(data) if data else None
        # Windows: Antworten kommen je nach Länge auf verschiedenen Kanälen, abwechselnd abfragen.
        per = max(1, min(10, timeout_ms // len(self.devices)))
        for dev in self.devices:
            data = dev.read(64, per)
            if data:
                return bytes(data)
        return None

    def request(self, devidx, sub, addr, params=b"", long=False, timeout=1.0):
        """Sendet eine Anfrage und wartet auf die passende Antwort (Nutzdaten ab Byte 4)."""
        report = LONG if long or len(params) > 3 else SHORT
        msg = bytes([report, devidx, sub, addr]) + bytes(params)
        self.handles[report].write(msg.ljust(SIZES[report], b"\0"))

        deadline = time.monotonic() + timeout
        while (left := deadline - time.monotonic()) > 0:
            r = self._read(max(1, int(left * 1000)))
            if not r or len(r) < 6 or r[0] not in SIZES or r[1] != devidx:
                continue
            if r[2] in (0x8F, 0xFF) and r[3] == sub and r[4] == addr:
                raise HidppError(1 if r[2] == 0x8F else 2, r[5])
            if r[2] == sub and r[3] == addr:
                return r[4:]
        raise TimeoutError(f"Keine Antwort von Gerät 0x{devidx:02X}")

    def read_register(self, reg, params=b""):
        return self.request(RECEIVER_INDEX, 0x81, reg, params)

    def read_long_register(self, reg, params=b""):
        return self.request(RECEIVER_INDEX, 0x83, reg, params)

    def pairing_info(self, slot):
        """WPID und Name des Geräts im Slot 1-6, None wenn leer."""
        try:
            info = self.read_long_register(0xB5, [0x20 + slot - 1])
        except HidppError:
            return None
        wpid = info[3] << 8 | info[4]
        name = None
        try:
            raw = self.read_long_register(0xB5, [0x40 + slot - 1])
            name = raw[2 : 2 + raw[1]].decode("ascii", "replace")
        except HidppError:
            pass
        return wpid, name


class Device:
    def __init__(self, receiver, index):
        self.rcv = receiver
        self.index = index
        self._features = {}

    def call(self, feat_index, func, params=b"", timeout=1.0):
        return self.rcv.request(self.index, feat_index, (func << 4) | SW_ID, params, long=True, timeout=timeout)

    def ping(self):
        """Protokollversion (major, minor), wirft bei ausgeschaltetem Gerät."""
        r = self.call(0x00, 1, b"\0\0\x5a")
        return r[0], r[1]

    def feature_index(self, feature_id):
        if feature_id not in self._features:
            r = self.call(0x00, 0, feature_id.to_bytes(2, "big"))
            self._features[feature_id] = r[0] or None
        return self._features[feature_id]

    def has(self, feature_id):
        return self.feature_index(feature_id) is not None

    def feature(self, feature_id, func, params=b"", timeout=1.0):
        idx = self.feature_index(feature_id)
        if idx is None:
            raise KeyError(f"Feature 0x{feature_id:04X} nicht vorhanden")
        return self.call(idx, func, params, timeout)

    def list_features(self):
        """[(index, feature_id, flags, version)] ohne Root."""
        count = self.feature(0x0001, 0)[0]
        result = []
        for i in range(1, count + 1):
            r = self.feature(0x0001, 1, [i])
            fid = r[0] << 8 | r[1]
            self._features[fid] = i
            result.append((i, fid, r[2], r[3]))
        return result


def connect():
    """Öffnet den Empfänger und liefert (Receiver, Device) der ersten antwortenden Maus."""
    interfaces = find_receiver()
    if not interfaces:
        raise RuntimeError("Kein Lightspeed-Empfänger gefunden.")
    rcv = Receiver(interfaces)
    # Zwei Runden: eine schlafende Maus wacht von der ersten Anfrage auf.
    for attempt in range(2):
        for slot in range(1, 7):
            dev = Device(rcv, slot)
            try:
                dev.ping()
            except (HidppError, TimeoutError):
                continue
            return rcv, dev
        time.sleep(0.5)
    rcv.close()
    raise RuntimeError("Maus antwortet nicht. Einschalten oder kurz bewegen und erneut starten.")
