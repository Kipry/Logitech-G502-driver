"""Hintergrund-Thread: wechselt das Mausprofil passend zum Programm im Vordergrund.

Gewechselt wird erst, wenn ein Programm kurz vorne bleibt, und nur, wenn die Maus
nicht schon auf dem Zielprofil steht. So bleibt es bei wenigen Befehlen an die Maus.
"""

import threading
import time
from datetime import datetime

import profiles
import settings
from hidpp import HidppError, connect
from probe import battery

DEBOUNCE = 0.8


class Switcher:
    def __init__(self, on_status=None):
        self.status = {"active": None, "names": {}, "battery": None, "error": None, "log": []}
        self._on_status = on_status
        self._cv = threading.Condition()
        self._app = None
        self._switch = None
        self._refresh = True
        threading.Thread(target=self._run, name="switcher", daemon=True).start()

    def app_activated(self, bundle_id, name):
        with self._cv:
            self._app = (bundle_id, name, time.monotonic())
            self._cv.notify()

    def switch_to(self, slot):
        with self._cv:
            self._switch = slot
            self._cv.notify()

    def refresh(self):
        with self._cv:
            self._refresh = True
            self._cv.notify()

    def _next_job(self):
        with self._cv:
            while True:
                if self._switch is not None or self._refresh:
                    break
                if self._app:
                    left = self._app[2] + DEBOUNCE - time.monotonic()
                    if left <= 0:
                        break
                    self._cv.wait(left)
                    continue
                self._cv.wait()
            switch, self._switch = self._switch, None
            self._refresh = False
            app = None
            if self._app and self._app[2] + DEBOUNCE <= time.monotonic():
                app, self._app = self._app, None
            return switch, app

    def _run(self):
        while True:
            switch, app = self._next_job()
            try:
                self._work(switch, app)
                self.status["error"] = None
            except (RuntimeError, OSError, HidppError, TimeoutError) as e:
                self.status["error"] = str(e)
            if self._on_status:
                self._on_status()

    def _work(self, switch, app):
        rcv, dev = connect()
        try:
            active, names = profiles.read_names(dev, None)
            target, reason = None, None
            if switch is not None:
                target, reason = switch, "Menü"
            elif app:
                conf = settings.load()
                if conf["auto"]:
                    target, reason = settings.target_for(conf, app[0]), app[1]
            if target is not None and target != active and names.get(target, ("", False))[1]:
                profiles.set_active(dev, target)
                active = target
                self._log(reason, target, names)
            try:
                bat = battery(dev)
            except (HidppError, KeyError, TimeoutError):
                bat = None
        finally:
            rcv.close()
        self.status.update(active=active, names=names, battery=bat)

    def _log(self, reason, target, names):
        entry = {"time": datetime.now().strftime("%H:%M:%S"), "reason": reason, "profile": target,
                 "name": names.get(target, ("", False))[0]}
        self.status["log"] = ([entry] + self.status["log"])[:20]
