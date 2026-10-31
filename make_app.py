"""Legt /Applications/G502.app an: Startdatei, Info.plist und Symbol.

Das Programm startet app.py aus diesem Ordner mit der Python-Umgebung hier.
Nach Code-Änderungen muss es nicht neu gebaut werden, nur neu gestartet.
"""

import plistlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from AppKit import (
    NSBezierPath,
    NSBitmapImageRep,
    NSColor,
    NSCompositingOperationSourceAtop,
    NSCompositingOperationSourceOver,
    NSFontWeightMedium,
    NSGradient,
    NSGraphicsContext,
    NSImage,
    NSImageSymbolConfiguration,
    NSMakeRect,
    NSPNGFileType,
    NSRectFillUsingOperation,
)

ROOT = Path(__file__).resolve().parent
TARGET = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/Applications/G502.app")

LAUNCHER = f"""#!/bin/zsh
# Startet die G502-App aus {ROOT}
mkdir -p "$HOME/Library/Logs"
exec "{ROOT}/.venv/bin/python" "{ROOT}/app.py" "$@" >> "$HOME/Library/Logs/G502.log" 2>&1
"""


def draw_icon(path, size=1024):
    rep = NSBitmapImageRep.alloc().initWithBitmapDataPlanes_pixelsWide_pixelsHigh_bitsPerSample_samplesPerPixel_hasAlpha_isPlanar_colorSpaceName_bytesPerRow_bitsPerPixel_(
        None, size, size, 8, 4, True, False, "NSDeviceRGBColorSpace", 0, 0
    )
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.setCurrentContext_(NSGraphicsContext.graphicsContextWithBitmapImageRep_(rep))

    # Fläche nach Apples Symbolraster: 824 px mit runden Ecken, mittig.
    inset = size * 100 / 1024
    body = NSMakeRect(inset, inset, size - 2 * inset, size - 2 * inset)
    shape = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(body, size * 0.18, size * 0.18)
    NSGradient.alloc().initWithStartingColor_endingColor_(
        NSColor.colorWithSRGBRed_green_blue_alpha_(0.25, 0.26, 0.30, 1),
        NSColor.colorWithSRGBRed_green_blue_alpha_(0.09, 0.09, 0.11, 1),
    ).drawInBezierPath_angle_(shape, -90)

    config = NSImageSymbolConfiguration.configurationWithPointSize_weight_(size * 0.42, NSFontWeightMedium)
    symbol = NSImage.imageWithSystemSymbolName_accessibilityDescription_("computermouse.fill", None)
    symbol = symbol.imageWithSymbolConfiguration_(config)
    w, h = symbol.size().width, symbol.size().height
    white = NSImage.alloc().initWithSize_(symbol.size())
    white.lockFocus()
    symbol.drawInRect_(NSMakeRect(0, 0, w, h))
    NSColor.whiteColor().set()
    NSRectFillUsingOperation(NSMakeRect(0, 0, w, h), NSCompositingOperationSourceAtop)
    white.unlockFocus()
    white.drawInRect_fromRect_operation_fraction_(
        NSMakeRect((size - w) / 2, (size - h) / 2, w, h), NSMakeRect(0, 0, 0, 0), NSCompositingOperationSourceOver, 1.0
    )

    NSGraphicsContext.restoreGraphicsState()
    path.write_bytes(bytes(rep.representationUsingType_properties_(NSPNGFileType, {})))


def make_icns(dest):
    with tempfile.TemporaryDirectory() as tmp:
        master = Path(tmp) / "icon.png"
        draw_icon(master)
        iconset = Path(tmp) / "G502.iconset"
        iconset.mkdir()
        for px in (16, 32, 128, 256, 512):
            for scale in (1, 2):
                out = iconset / f"icon_{px}x{px}{'@2x' if scale == 2 else ''}.png"
                subprocess.run(["sips", "-z", str(px * scale), str(px * scale), str(master), "--out", str(out)],
                               check=True, capture_output=True)
        subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(dest)], check=True)


def main():
    if TARGET.exists():
        shutil.rmtree(TARGET)
    macos = TARGET / "Contents" / "MacOS"
    resources = TARGET / "Contents" / "Resources"
    macos.mkdir(parents=True)
    resources.mkdir(parents=True)

    launcher = macos / "G502"
    launcher.write_text(LAUNCHER)
    launcher.chmod(0o755)
    make_icns(resources / "G502.icns")
    (TARGET / "Contents" / "Info.plist").write_bytes(plistlib.dumps({
        "CFBundleName": "G502",
        "CFBundleDisplayName": "G502",
        "CFBundleIdentifier": "de.kpk.g502",
        "CFBundleExecutable": "G502",
        "CFBundleIconFile": "G502",
        "CFBundlePackageType": "APPL",
        "CFBundleShortVersionString": "1.0",
        "CFBundleVersion": "1",
        "LSUIElement": True,
        "NSHighResolutionCapable": True,
    }))
    # Finder soll das neue Symbol sofort zeigen.
    subprocess.run(["touch", str(TARGET)])
    print(f"Angelegt: {TARGET}")


if __name__ == "__main__":
    main()
