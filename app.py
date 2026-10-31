"""G502 als Mac-Programm: Symbol in der Menüleiste, eigenes Fenster, Profilwechsel nach Programm.

    app.py           starten und Fenster öffnen
    app.py --still   nur in der Menüleiste starten (Anmeldung)
"""

import os
import plistlib
import re
import sys
import threading
import urllib.request
from pathlib import Path

import objc
from AppKit import (
    NSApp,
    NSApplication,
    NSApplicationActivationPolicyAccessory,
    NSBackingStoreBuffered,
    NSControlStateValueOff,
    NSControlStateValueOn,
    NSImage,
    NSImageLeading,
    NSMenu,
    NSMenuItem,
    NSStatusBar,
    NSTimer,
    NSVariableStatusItemLength,
    NSViewHeightSizable,
    NSViewWidthSizable,
    NSWindow,
    NSWindowStyleMaskClosable,
    NSWindowStyleMaskMiniaturizable,
    NSWindowStyleMaskResizable,
    NSWindowStyleMaskTitled,
    NSWorkspace,
    NSWorkspaceApplicationKey,
    NSWorkspaceDidActivateApplicationNotification,
)
from Foundation import NSURL, NSMakeRect, NSMakeSize, NSObject, NSURLRequest
from PyObjCTools import AppHelper
from WebKit import WKWebView, WKWebViewConfiguration

import server
import settings
from switcher import Switcher

URL = f"http://127.0.0.1:{server.PORT}/"
APP_PATH = "/Applications/G502.app"
LAUNCH_AGENT = Path.home() / "Library" / "LaunchAgents" / "de.kpk.g502.plist"


def start_server_or_show_existing():
    """Eigener Server, oder None, wenn G502 schon läuft (dann dort das Fenster öffnen)."""
    try:
        return server.create_server()
    except OSError:
        req = urllib.request.Request(
            URL + "api/zeigen", data=b"{}", method="POST",
            headers={"X-G502": "1", "Content-Type": "application/json"},
        )
        try:
            urllib.request.urlopen(req, timeout=3)
        except OSError:
            pass
        return None


class AppDelegate(NSObject):
    def initWithServer_(self, srv):
        self = objc.super(AppDelegate, self).init()
        self.srv = srv
        self.window = None
        self.webview = None
        return self

    def applicationDidFinishLaunching_(self, note):
        self.switcher = Switcher(on_status=self.statusFromThread)
        server.HOOKS.update(show=self.showFromThread, switcher=self.switcher)
        threading.Thread(target=self.srv.serve_forever, name="server", daemon=True).start()

        self.buildMainMenu()
        self.item = NSStatusBar.systemStatusBar().statusItemWithLength_(NSVariableStatusItemLength)
        image = NSImage.imageWithSystemSymbolName_accessibilityDescription_("computermouse.fill", "G502")
        image.setTemplate_(True)
        self.item.button().setImage_(image)
        self.item.button().setImagePosition_(NSImageLeading)
        self.menu = NSMenu.alloc().init()
        self.menu.setAutoenablesItems_(False)
        self.menu.setDelegate_(self)
        self.item.setMenu_(self.menu)

        NSWorkspace.sharedWorkspace().notificationCenter().addObserver_selector_name_object_(
            self, "appActivated:", NSWorkspaceDidActivateApplicationNotification, None
        )
        # Akku und Profilnamen gelegentlich auffrischen.
        NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(300, self, "tick:", None, True)
        if "--still" not in sys.argv:
            self.showWindow_(None)

    def applicationShouldHandleReopen_hasVisibleWindows_(self, app, visible):
        # Erneuter Start aus Programme oder Spotlight: Fenster zeigen.
        self.showWindow_(None)
        return False

    # ---- Profil nach Programm ----

    def appActivated_(self, note):
        app = note.userInfo()[NSWorkspaceApplicationKey]
        if app.processIdentifier() == os.getpid():
            return
        bundle_id = app.bundleIdentifier()
        if bundle_id:
            self.switcher.app_activated(bundle_id, app.localizedName() or bundle_id)

    def tick_(self, timer):
        self.switcher.refresh()

    def statusFromThread(self):
        self.performSelectorOnMainThread_withObject_waitUntilDone_("updateTitle:", None, False)

    def updateTitle_(self, _):
        st = self.switcher.status
        name = st["names"].get(st["active"], ("", False))[0] if st["active"] else ""
        if st["error"]:
            title = " –"
        elif name:
            title = " " + (name if len(name) <= 14 else name[:13] + "…")
        else:
            title = f" {st['active']}" if st["active"] else ""
        self.item.button().setTitle_(title)

    # ---- Menü ----

    @objc.python_method
    def add(self, title, action=None, key="", tag=0, on=None):
        item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, action, key)
        if action:
            item.setTarget_(self)
        item.setEnabled_(action is not None)
        item.setTag_(tag)
        if on is not None:
            item.setState_(NSControlStateValueOn if on else NSControlStateValueOff)
        self.menu.addItem_(item)
        return item

    def menuNeedsUpdate_(self, menu):
        menu.removeAllItems()
        st = self.switcher.status
        if st["error"]:
            self.add("Maus nicht erreichbar")
        else:
            pct = re.search(r"(\d+) %", st["battery"] or "")
            self.add("G502" + (f" · Akku {pct.group(1)} %" if pct else ""))
        menu.addItem_(NSMenuItem.separatorItem())
        for slot, (name, enabled) in sorted(st["names"].items()):
            if enabled:
                self.add(f"{slot}  {name or 'Ohne Namen'}", "switchProfile:", tag=slot, on=slot == st["active"])
        if st["names"]:
            menu.addItem_(NSMenuItem.separatorItem())
        self.add("Profil nach Programm wechseln", "toggleAuto:", on=settings.load()["auto"])
        self.add("Belegung öffnen …", "showWindow:", ",")
        self.add("Beim Anmelden starten", "toggleLogin:", on=LAUNCH_AGENT.exists())
        menu.addItem_(NSMenuItem.separatorItem())
        self.add("G502 beenden", "quit:", "q")
        self.switcher.refresh()

    def switchProfile_(self, sender):
        self.switcher.switch_to(sender.tag())

    def toggleAuto_(self, sender):
        conf = settings.load()
        conf["auto"] = not conf["auto"]
        settings.save(conf)
        front = NSWorkspace.sharedWorkspace().frontmostApplication()
        if conf["auto"] and front and front.bundleIdentifier():
            self.switcher.app_activated(front.bundleIdentifier(), front.localizedName())

    def toggleLogin_(self, sender):
        if LAUNCH_AGENT.exists():
            LAUNCH_AGENT.unlink()
        else:
            LAUNCH_AGENT.parent.mkdir(parents=True, exist_ok=True)
            LAUNCH_AGENT.write_bytes(plistlib.dumps({
                "Label": "de.kpk.g502",
                "ProgramArguments": ["/usr/bin/open", "-a", APP_PATH, "--args", "--still"],
                "RunAtLoad": True,
            }))

    def quit_(self, sender):
        NSApp.terminate_(None)

    # ---- Fenster ----

    def showFromThread(self):
        self.performSelectorOnMainThread_withObject_waitUntilDone_("showWindow:", None, False)

    def showWindow_(self, sender):
        if self.window is None:
            rect = NSMakeRect(0, 0, 1120, 820)
            style = (NSWindowStyleMaskTitled | NSWindowStyleMaskClosable
                     | NSWindowStyleMaskMiniaturizable | NSWindowStyleMaskResizable)
            window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(rect, style, NSBackingStoreBuffered, False)
            window.setTitle_("G502")
            window.setReleasedWhenClosed_(False)
            window.setMinSize_(NSMakeSize(720, 520))
            window.center()
            window.setFrameAutosaveName_("G502Fenster")
            webview = WKWebView.alloc().initWithFrame_configuration_(rect, WKWebViewConfiguration.alloc().init())
            webview.setAutoresizingMask_(NSViewWidthSizable | NSViewHeightSizable)
            window.setContentView_(webview)
            webview.loadRequest_(NSURLRequest.requestWithURL_(NSURL.URLWithString_(URL)))
            self.window, self.webview = window, webview
        elif not self.window.isVisible():
            self.webview.evaluateJavaScript_completionHandler_("window.g502Shown && window.g502Shown()", None)
        NSApp.activateIgnoringOtherApps_(True)
        self.window.makeKeyAndOrderFront_(None)

    def buildMainMenu(self):
        # Unsichtbar (Menüleisten-App), aber nötig für ⌘C/⌘V/⌘W im Fenster.
        main = NSMenu.alloc().init()
        for title, items in (
            ("G502", [("Fenster schließen", "performClose:", "w"), ("G502 beenden", "terminate:", "q")]),
            ("Bearbeiten", [("Widerrufen", "undo:", "z"), ("Wiederholen", "redo:", "Z"), ("Ausschneiden", "cut:", "x"),
                            ("Kopieren", "copy:", "c"), ("Einsetzen", "paste:", "v"), ("Alles auswählen", "selectAll:", "a")]),
        ):
            top = NSMenuItem.alloc().init()
            sub = NSMenu.alloc().initWithTitle_(title)
            for t, action, key in items:
                sub.addItemWithTitle_action_keyEquivalent_(t, action, key)
            top.setSubmenu_(sub)
            main.addItem_(top)
        NSApp.setMainMenu_(main)


def main():
    srv = start_server_or_show_existing()
    if srv is None:
        return
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
    delegate = AppDelegate.alloc().initWithServer_(srv)
    app.setDelegate_(delegate)
    AppHelper.runEventLoop()


if __name__ == "__main__":
    main()
