"""Programme auf dem Mac: laufende Programme, Namen und Symbole (über AppKit)."""

from AppKit import (
    NSApplicationActivationPolicyRegular,
    NSBitmapImageRep,
    NSCompositingOperationCopy,
    NSGraphicsContext,
    NSMakeRect,
    NSPNGFileType,
    NSWorkspace,
)


def running_apps():
    """[{id, name}] der sichtbaren laufenden Programme, alphabetisch."""
    seen = {}
    for app in NSWorkspace.sharedWorkspace().runningApplications():
        bid = app.bundleIdentifier()
        if bid and app.activationPolicy() == NSApplicationActivationPolicyRegular:
            seen[bid] = app.localizedName() or bid
    return sorted(({"id": k, "name": v} for k, v in seen.items()), key=lambda a: a["name"].lower())


def icon_png(bundle_id, size=64):
    ws = NSWorkspace.sharedWorkspace()
    url = ws.URLForApplicationWithBundleIdentifier_(bundle_id)
    if url is None:
        return None
    image = ws.iconForFile_(url.path())
    rep = NSBitmapImageRep.alloc().initWithBitmapDataPlanes_pixelsWide_pixelsHigh_bitsPerSample_samplesPerPixel_hasAlpha_isPlanar_colorSpaceName_bytesPerRow_bitsPerPixel_(
        None, size, size, 8, 4, True, False, "NSDeviceRGBColorSpace", 0, 0
    )
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.setCurrentContext_(NSGraphicsContext.graphicsContextWithBitmapImageRep_(rep))
    image.drawInRect_fromRect_operation_fraction_(NSMakeRect(0, 0, size, size), NSMakeRect(0, 0, 0, 0), NSCompositingOperationCopy, 1.0)
    NSGraphicsContext.restoreGraphicsState()
    return bytes(rep.representationUsingType_properties_(NSPNGFileType, {}))
