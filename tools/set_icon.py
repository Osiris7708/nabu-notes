"""Give Nabu Notes a new icon, everywhere it appears.

    runtime\\python.exe tools\\set_icon.py picture.png

From one square picture (an app-icon style rounded square; anything outside it, like a black border, is cut
away and becomes see-through) this makes:
  app\\nabu_icon.png            256 x 256: the window corner, taskbar, pop-out windows, dialogs and the tray icon
  launcher\\nabu_icon_source.png  the picture itself (1024 x 1024), kept so the icon can be made again
  launcher\\nabu.ico             16 - 256 pixels: the icon built into NabuNotes.exe
and puts the new icon into NabuNotes.exe itself (Windows' resource update; no need to rebuild the launcher).
Windows remembers icons for a while: if Explorer still shows the old one, it updates on its own.
(If the launcher is ever rebuilt with Go, make launcher\\rsrc_windows_amd64.syso from nabu.ico first:
 go run github.com/akavel/rsrc -ico nabu.ico -o rsrc_windows_amd64.syso)
"""
import ctypes
import io
import os
import struct
import sys

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SIZES = (16, 24, 32, 48, 64, 128, 256)


def _bounds(img):
    """The rounded square inside the picture: the box around everything clearly brighter than the border."""
    g = img.convert("L")
    corner = max(g.getpixel((2, 2)), g.getpixel((g.width - 3, g.height - 3)))
    mask = g.point(lambda v: 255 if v > corner + 6 else 0)
    return mask.getbbox() or (0, 0, img.width, img.height)


def cut_out(src):
    """The rounded square on its own, corners see-through, as a square RGBA picture."""
    img = Image.open(src).convert("RGBA")
    l, t, r, b = _bounds(img)
    side = max(r - l, b - t)
    cx, cy = (l + r) / 2.0, (t + b) / 2.0
    box = (int(cx - side / 2), int(cy - side / 2), int(cx - side / 2) + side, int(cy - side / 2) + side)
    img = img.crop(box)
    # a smooth rounded-corner mask (drawn 4x bigger, then shrunk, for soft edges)
    k = 4
    m = Image.new("L", (side * k, side * k), 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, side * k - 1, side * k - 1), radius=int(side * k * 0.18), fill=255)
    img.putalpha(m.resize((side, side), Image.LANCZOS))
    return img


def _ico_images(art):
    out = []
    for s in SIZES:
        im = art.resize((s, s), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, "PNG")                         # (PNG-in-ICO: fine for every size on Windows Vista and later)
        out.append((s, buf.getvalue()))
    return out


def write_ico(art, path):
    imgs = _ico_images(art)
    head = struct.pack("<HHH", 0, 1, len(imgs))
    entries, data, off = b"", b"", 6 + 16 * len(imgs)
    for s, png in imgs:
        entries += struct.pack("<BBBBHHII", s % 256, s % 256, 0, 0, 1, 32, len(png), off)
        data += png
        off += len(png)
    with open(path, "wb") as f:
        f.write(head + entries + data)
    return imgs


def _icon_ids(exe):
    """The numbers of the icon pictures stored in exe."""
    from ctypes import wintypes
    k32 = ctypes.windll.kernel32
    k32.LoadLibraryExW.restype = ctypes.c_void_p
    k32.LoadLibraryExW.argtypes = [ctypes.c_wchar_p, ctypes.c_void_p, ctypes.c_uint]
    k32.FreeLibrary.argtypes = [ctypes.c_void_p]
    proc = ctypes.WINFUNCTYPE(wintypes.BOOL, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)
    k32.EnumResourceNamesW.argtypes = [ctypes.c_void_p, ctypes.c_void_p, proc, ctypes.c_void_p]
    ids = []
    cb = proc(lambda hm, typ, name, lp: ids.append(int(name)) or True if name and name <= 0xFFFF else True)
    h = k32.LoadLibraryExW(exe, None, 0x2)            # (as data: nothing in it runs)
    if h:
        k32.EnumResourceNamesW(h, 3, cb, None)
        k32.FreeLibrary(h)
    return ids


def refresh_icons():
    """Ask Windows to forget the icons it remembered (Explorer, desktop shortcuts)."""
    import subprocess
    try:
        ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)     # SHCNE_ASSOCCHANGED
        subprocess.run(["ie4uinit.exe", "-show"], timeout=30)
    except Exception:
        pass


def patch_exe(exe, imgs):
    """Replace the icon inside exe (group icon 1, icons 1..n) with Windows' resource-update calls."""
    k32 = ctypes.windll.kernel32
    k32.BeginUpdateResourceW.restype = ctypes.c_void_p
    k32.BeginUpdateResourceW.argtypes = [ctypes.c_wchar_p, ctypes.c_bool]
    k32.UpdateResourceW.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ushort,
                                    ctypes.c_void_p, ctypes.c_uint]
    k32.EndUpdateResourceW.argtypes = [ctypes.c_void_p, ctypes.c_bool]
    RT_ICON, RT_GROUP_ICON, LANG = 3, 14, 1033
    old = _icon_ids(exe)                            # (the old icon may have had more sizes: those go too)
    h = k32.BeginUpdateResourceW(exe, False)
    if not h:
        raise OSError("can't open %s to change its icon (is Nabu Notes running?)" % exe)
    ok = True
    group = struct.pack("<HHH", 0, 1, len(imgs))
    for n, (s, png) in enumerate(imgs, 1):
        buf = ctypes.create_string_buffer(png, len(png))
        ok &= bool(k32.UpdateResourceW(h, RT_ICON, n, LANG, buf, len(png)))
        group += struct.pack("<BBBBHHIH", s % 256, s % 256, 0, 0, 1, 32, len(png), n)
    for n in old:
        if n > len(imgs):
            ok &= bool(k32.UpdateResourceW(h, RT_ICON, n, LANG, None, 0))
    gbuf = ctypes.create_string_buffer(group, len(group))
    ok &= bool(k32.UpdateResourceW(h, RT_GROUP_ICON, 1, LANG, gbuf, len(group)))
    if not k32.EndUpdateResourceW(h, not ok) or not ok:
        raise OSError("Windows didn't accept the new icon for %s" % exe)


def main(argv):
    if not argv:
        print(__doc__)
        return 1
    art = cut_out(argv[0])
    big = art.resize((1024, 1024), Image.LANCZOS) if art.width > 1024 else art
    big.save(os.path.join(ROOT, "launcher", "nabu_icon_source.png"))
    art.resize((256, 256), Image.LANCZOS).save(os.path.join(ROOT, "app", "nabu_icon.png"))
    imgs = write_ico(art, os.path.join(ROOT, "launcher", "nabu.ico"))
    print("made app\\nabu_icon.png, launcher\\nabu.ico and launcher\\nabu_icon_source.png")
    exe = os.path.join(ROOT, "NabuNotes.exe")
    if os.name == "nt" and os.path.isfile(exe):
        patch_exe(exe, imgs)
        refresh_icons()
        print("NabuNotes.exe has the new icon")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
