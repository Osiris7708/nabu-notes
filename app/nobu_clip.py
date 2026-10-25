"""Windows clipboard with formatting: puts HTML + RTF + plain text, so pasting into Word keeps
fonts, sizes, colours and pictures; reads HTML back when pasting from Word or a browser."""
import ctypes
import logging
import os

log = logging.getLogger("nobu.clip")
IS_WIN = os.name == "nt"

if IS_WIN:
    from ctypes import wintypes
    u32 = ctypes.windll.user32
    k32 = ctypes.windll.kernel32
    u32.OpenClipboard.argtypes = [wintypes.HWND]
    u32.SetClipboardData.argtypes = [wintypes.UINT, ctypes.c_void_p]
    u32.SetClipboardData.restype = ctypes.c_void_p
    u32.GetClipboardData.argtypes = [wintypes.UINT]
    u32.GetClipboardData.restype = ctypes.c_void_p
    u32.RegisterClipboardFormatW.argtypes = [wintypes.LPCWSTR]
    u32.RegisterClipboardFormatW.restype = wintypes.UINT
    u32.IsClipboardFormatAvailable.argtypes = [wintypes.UINT]
    k32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    k32.GlobalAlloc.restype = ctypes.c_void_p
    k32.GlobalLock.argtypes = [ctypes.c_void_p]
    k32.GlobalLock.restype = ctypes.c_void_p
    k32.GlobalUnlock.argtypes = [ctypes.c_void_p]
    k32.GlobalSize.argtypes = [ctypes.c_void_p]
    k32.GlobalSize.restype = ctypes.c_size_t
    CF_UNICODETEXT = 13
    CF_DIB = 8
    GMEM_MOVEABLE = 0x0002


def _cf_html(fragment):
    head = ("Version:0.9\r\nStartHTML:{0:010d}\r\nEndHTML:{1:010d}\r\n"
            "StartFragment:{2:010d}\r\nEndFragment:{3:010d}\r\n")
    pre = "<html><head><meta charset='utf-8'></head><body><!--StartFragment-->"
    post = "<!--EndFragment--></body></html>"
    dummy = head.format(0, 0, 0, 0)
    start_html = len(dummy.encode("utf-8"))
    start_frag = start_html + len(pre.encode("utf-8"))
    end_frag = start_frag + len(fragment.encode("utf-8"))
    end_html = end_frag + len(post.encode("utf-8"))
    return (head.format(start_html, end_html, start_frag, end_frag) + pre + fragment + post).encode("utf-8")


def _put(fmt, data):
    h = k32.GlobalAlloc(GMEM_MOVEABLE, len(data))
    p = k32.GlobalLock(h)
    ctypes.memmove(p, data, len(data))
    k32.GlobalUnlock(h)
    if not u32.SetClipboardData(fmt, h):
        log.warning("SetClipboardData failed for format %s", fmt)


def _picture_data(path):
    """The picture as a Windows bitmap (DIB, which every program can paste) and as PNG (keeps see-through parts)."""
    import io
    from PIL import Image, ImageOps
    with Image.open(path) as src:        # (closed straight away: never locks the file)
        img = ImageOps.exif_transpose(src)
        img.load()
    png = io.BytesIO()
    img.save(png, "PNG")
    if img.mode in ("RGBA", "LA", "P"):
        rgba = img.convert("RGBA")
        flat = Image.new("RGB", rgba.size, (255, 255, 255))
        flat.paste(rgba, mask=rgba.split()[3])
    else:
        flat = img.convert("RGB")
    dib = io.BytesIO()
    flat.save(dib, "DIB")
    return dib.getvalue(), png.getvalue()


def set_rich(text, html_fragment=None, rtf=None, picture=None):
    """Returns True if the rich clipboard was set (Windows only). picture: a picture file to put on the
    clipboard as a picture too, so programs that only take pictures (Paint, chat apps...) can paste it."""
    if not IS_WIN:
        return False
    pic = None
    if picture:
        try:
            pic = _picture_data(picture)
        except Exception:
            log.exception("could not read the picture for the clipboard")
    for _ in range(5):
        if u32.OpenClipboard(None):
            break
        k32.Sleep(30)
    else:
        return False
    try:
        u32.EmptyClipboard()
        if text:
            _put(CF_UNICODETEXT, (text + "\0").encode("utf-16-le"))
        if pic:
            _put(CF_DIB, pic[0])
            _put(u32.RegisterClipboardFormatW("PNG"), pic[1])
        if html_fragment:
            _put(u32.RegisterClipboardFormatW("HTML Format"), _cf_html(html_fragment) + b"\0")
        if rtf:
            _put(u32.RegisterClipboardFormatW("Rich Text Format"), rtf.encode("latin-1", "replace") + b"\0")
        return True
    except Exception:
        log.exception("clipboard write failed")
        return False
    finally:
        u32.CloseClipboard()


def get_html():
    """HTML on the clipboard (from Word, a browser, ...), or None."""
    if not IS_WIN:
        return None
    fmt = u32.RegisterClipboardFormatW("HTML Format")
    if not u32.IsClipboardFormatAvailable(fmt):
        return None
    if not u32.OpenClipboard(None):
        return None
    try:
        h = u32.GetClipboardData(fmt)
        if not h:
            return None
        p = k32.GlobalLock(h)
        size = k32.GlobalSize(h)
        raw = ctypes.string_at(p, size)
        k32.GlobalUnlock(h)
        return raw.split(b"\0", 1)[0].decode("utf-8", "replace")
    except Exception:
        log.exception("clipboard read failed")
        return None
    finally:
        u32.CloseClipboard()
