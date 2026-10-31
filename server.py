"""Belegungs-Oberfläche: kleiner lokaler Server, nur auf 127.0.0.1.

    server.py            starten und Browser öffnen
    server.py --still    nur starten
"""

import json
import sys
import webbrowser
from urllib.parse import parse_qs, urlparse
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import backup
import config
import g502
import profiles
import settings
from hidpp import HidppError, connect
from probe import battery

PORT = 8502
ROOT = Path(__file__).parent
ALLOWED_HOSTS = {f"127.0.0.1:{PORT}", f"localhost:{PORT}"}

cache = {"state": None}

# Von der Menüleisten-App gesetzt; ohne App bleiben sie leer.
HOOKS = {"show": None, "switcher": None, "settings_changed": None}


def ui_state(state, battery_text=None):
    """Sicherungsform in das, was die Oberfläche braucht."""
    desc = state["description"]
    sectors = backup.sectors_of(state)
    count = desc["button_count"]
    enabled = {e["sector"]: e["enabled"] for e in profiles.parse_directory(sectors[profiles.DIRECTORY])}
    result = []
    for slot in range(1, desc["profile_count"] + 1):
        data = sectors.get(slot)
        empty = not (data and profiles.crc_ok(data))
        if empty:
            data = sectors[g502.ROM_PROFILE]
        p = profiles.parse_profile(data, count, sectors)

        def buttons(base):
            return [
                {
                    "key": config.BUTTON_KEYS[i],
                    "label": profiles.button_label(i),
                    "action": config.binding_to_action(data[base + 4 * i : base + 4 * i + 4]),
                    "text": profiles.describe_binding(data[base + 4 * i : base + 4 * i + 4], sectors),
                }
                for i in range(count)
            ]

        result.append({
            "slot": slot,
            "empty": empty,
            "name": p["name"],
            "enabled": enabled.get(slot, False),
            "active": slot == state["active_sector"],
            "dpi": p["dpi"],
            "start_dpi": p["dpi"][p["default_dpi_index"]] if p["default_dpi_index"] < len(p["dpi"]) else p["dpi"][0],
            "sniper_dpi": p["dpi"][p["sniper_dpi_index"]] if p["sniper_dpi_index"] < len(p["dpi"]) else p["dpi"][0],
            "hz": p["report_rate_hz"],
            "leds": [
                {"text": config.led_to_text(data[208 + 11 * i : 219 + 11 * i]), "desc": p["leds"][i]}
                for i in range(2)
            ],
            "buttons": buttons(32),
            "gshift": buttons(96),
        })
    return {
        "device": state["device"]["name"],
        "battery": battery_text,
        "profiles": result,
        "backups": backup_names(),
    }


def backup_names():
    files = sorted(backup.BACKUP_DIR.glob("*.json"), reverse=True)
    names = [f.name for f in files if f.name != "original.json"]
    return (["original.json"] if (backup.BACKUP_DIR / "original.json").exists() else []) + names


def read_fresh(dev):
    state = backup.read_state(dev)
    try:
        bat = battery(dev)
    except (HidppError, KeyError, TimeoutError):
        bat = None
    cache["state"] = state
    return ui_state(state, bat)


def plan_json(state, changes, active):
    return {
        "changes": [
            {"label": label, "lines": g502.change_lines(state, sector, new)} for sector, new, label in changes
        ],
        "active": active,
    }


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        sys.stderr.write("%s\n" % (fmt % args))

    def send_json(self, code, payload):
        body = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def host_ok(self):
        # Schützt gegen DNS-Rebinding: nur Anfragen an unseren eigenen Namen.
        if self.headers.get("Host") not in ALLOWED_HOSTS:
            self.send_error(403)
            return False
        return True

    def do_GET(self):
        if not self.host_ok():
            return
        if self.path in ("/", "/index.html"):
            body = (ROOT / "index.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/api/state":
            self.with_device(read_fresh)
        elif self.path == "/api/apps":
            self.send_json(200, apps_payload())
        elif self.path.startswith("/api/icon?"):
            self.send_icon(parse_qs(urlparse(self.path).query).get("id", [""])[0])
        else:
            self.send_error(404)

    def do_POST(self):
        if not self.host_ok():
            return
        # Eigener Header erzwingt bei fremden Seiten eine CORS-Vorabfrage, die wir nie erlauben.
        if self.headers.get("X-G502") != "1":
            self.send_error(403)
            return
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        except json.JSONDecodeError:
            self.send_json(400, {"error": "Ungültige Anfrage"})
            return

        if self.path == "/api/plan":
            try:
                state = cache["state"]
                if state is None:
                    raise RuntimeError("Maus noch nicht gelesen")
                specs = config.validate(body.get("profiles", []))
                self.send_json(200, plan_json(state, *g502.plan(state, specs)))
            except (config.ConfigError, RuntimeError, TypeError, ValueError, KeyError) as e:
                self.send_json(400, {"error": str(e)})
        elif self.path == "/api/write":
            self.with_device(lambda dev: self.write(dev, body))
        elif self.path == "/api/restore":
            self.with_device(lambda dev: self.restore(dev, body))
        elif self.path == "/api/apps":
            try:
                settings.save(body.get("settings", {}))
            except (ValueError, TypeError, AttributeError) as e:
                self.send_json(400, {"error": str(e)})
                return
            if HOOKS["settings_changed"]:
                HOOKS["settings_changed"]()
            self.send_json(200, apps_payload())
        elif self.path == "/api/zeigen":
            if HOOKS["show"]:
                HOOKS["show"]()
            self.send_json(200, {})
        else:
            self.send_error(404)

    def send_icon(self, bundle_id):
        try:
            import apps

            png = apps.icon_png(bundle_id) if bundle_id else None
        except ImportError:
            png = None
        if not png:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", "image/png")
        self.send_header("Content-Length", str(len(png)))
        self.send_header("Cache-Control", "max-age=86400")
        self.end_headers()
        self.wfile.write(png)

    def with_device(self, fn):
        try:
            rcv, dev = connect()
        except (RuntimeError, OSError) as e:
            sys.stderr.write(f"Maus nicht erreichbar: {e}\n")
            self.send_json(503, {"error": str(e)})
            return
        try:
            self.send_json(200, fn(dev))
        except (config.ConfigError, RuntimeError, HidppError, TimeoutError, TypeError, ValueError, KeyError) as e:
            self.send_json(400, {"error": str(e)})
        finally:
            rcv.close()

    def write(self, dev, body):
        specs = config.validate(body.get("profiles", []))
        state = backup.read_state(dev)
        changes, active = g502.plan(state, specs)
        if changes or active is not None:
            backup.save(state)
            g502.apply(dev, state, changes, active)
        result = read_fresh(dev)
        result["written"] = [label for _, _, label in changes]
        return result

    def restore(self, dev, body):
        name = Path(body.get("name", "")).name
        path = backup.BACKUP_DIR / name
        if not name or not path.exists():
            raise RuntimeError("Sicherung nicht gefunden")
        saved = json.loads(path.read_text(encoding="utf-8"))
        state = backup.read_state(dev)
        changes, active = g502.restore_plan(saved, state)
        if changes or active is not None:
            backup.save(state)
            g502.apply(dev, state, changes, active)
        result = read_fresh(dev)
        result["written"] = [label for _, _, label in changes]
        return result


def apps_payload():
    try:
        import apps

        running = apps.running_apps()
    except ImportError:
        running = []
    sw = HOOKS["switcher"]
    return {
        "settings": settings.load(),
        "running": running,
        "app": sw is not None,
        "log": sw.status["log"] if sw else [],
    }


def create_server():
    return HTTPServer(("127.0.0.1", PORT), Handler)


def main():
    url = f"http://127.0.0.1:{PORT}/"
    try:
        server = create_server()
    except OSError:
        # Läuft schon: nur den Browser öffnen.
        webbrowser.open(url)
        return
    print(f"G502-Belegung läuft auf {url}  (Beenden: Ctrl+C)")
    if "--still" not in sys.argv:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
