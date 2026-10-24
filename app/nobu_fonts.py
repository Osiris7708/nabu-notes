"""Fonts: Nobu's font library, your own fonts, and Windows' fonts.

  app\\fonts\\lib\\   ~64 free fonts (SIL Open Font License) + fonts.json (family, category, files)
  app\\fonts\\        older bundled copies (IM Fell English, Grenze)
  fonts\\             your own fonts (e.g. Varnyx) - drop any .ttf/.otf here

At start-up they are loaded privately for Nobu, and (by default) installed into Windows
for your user account only, so Word and other programs can show the same fonts.
"""
import glob
import json
import logging
import os
import shutil
import threading
import tkinter.font as tkfont

from nobu_config import HOME

log = logging.getLogger("nobu.fonts")

APP_FONTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
LIB_FONTS = os.path.join(APP_FONTS, "lib")
USER_FONTS = os.path.join(HOME, "fonts")
CACHE = os.path.join(HOME, "cache")
BODY_FALLBACKS = ["IM FELL English", "Palatino Linotype", "Book Antiqua", "Georgia", "Cambria", "Times New Roman"]
HEADING_FALLBACKS = ["Eagle Lake", "Varnyx", "IM FELL English", "Palatino Linotype", "Georgia"]
UI_FALLBACKS = ["Grenze", "Segoe UI"]
CATEGORIES = [("fantasy", "Fantasy & medieval"), ("serif", "Book & manuscript"), ("script", "Handwriting & script"),
              ("gothic", "Gothic & horror"), ("typewriter", "Typewriter"), ("modern", "Clean & modern"),
              ("yours", "Your fonts"), ("system", "Windows fonts")]

_lock = threading.RLock()
_registry = None
_cover = {}


def _name_of(path):
    """(family, style) from a font file, using fontTools when available."""
    try:
        from fontTools.ttLib import TTFont
        t = TTFont(path, lazy=True, fontNumber=0)
        names = {r.nameID: r.toUnicode() for r in t["name"].names if r.platformID in (3, 0, 1)}
        fam = names.get(16) or names.get(1)
        sub = (names.get(17) or names.get(2) or "Regular").lower()
        t.close()
        return fam, sub
    except Exception:
        base = os.path.splitext(os.path.basename(path))[0]
        return base.split("-")[0], "regular"


def _style_key(sub):
    b = "bold" in sub or "black" in sub or "heavy" in sub
    i = "italic" in sub or "oblique" in sub
    return "bolditalic" if b and i else "bold" if b else "italic" if i else "regular"


def registry():
    """List of {family, category, files: {regular,bold,italic,bolditalic: abs path}}."""
    global _registry
    with _lock:
        if _registry is not None:
            return _registry
        reg = {}
        try:
            with open(os.path.join(LIB_FONTS, "fonts.json"), encoding="utf-8") as f:
                for e in json.load(f):
                    reg[e["family"]] = {"family": e["family"], "category": e["category"],
                                        "files": {k: os.path.join(LIB_FONTS, v) for k, v in e["files"].items()}}
        except Exception:
            log.warning("font library index missing")
        for d, cat in ((APP_FONTS, "fantasy"), (USER_FONTS, "yours")):
            for p in _font_files(d):
                fam, sub = _name_of(p)
                if not fam:
                    continue
                e = reg.setdefault(fam, {"family": fam, "category": cat, "files": {}})
                key = _style_key(sub)
                cur = e["files"].get(key)
                if cur is None or (cur.lower().endswith(".otf") and p.lower().endswith(".ttf")):
                    e["files"][key] = p          # prefer .ttf (PDFs need TrueType)
                if cat == "yours":
                    e["category"] = "yours"
        _registry = sorted(reg.values(), key=lambda e: e["family"].lower())
        return _registry


def _font_files(d):
    out = []
    for ext in ("*.ttf", "*.otf", "*.TTF", "*.OTF"):
        out += glob.glob(os.path.join(d, ext))
    return sorted(set(out))


def _same_file(a, b):
    try:
        if os.path.getsize(a) != os.path.getsize(b):
            return False
        with open(a, "rb") as fa, open(b, "rb") as fb:
            return fa.read() == fb.read()
    except OSError:
        return False


def _place(data_or_path, name):
    """Put one font into the fonts folder. Returns (path, already_there).

    A font that's already there is left alone - Windows keeps fonts in use locked, which is
    what caused 'Permission denied' when the same fonts were added twice."""
    dest = os.path.join(USER_FONTS, name)
    if os.path.exists(dest):
        if isinstance(data_or_path, bytes):
            try:
                with open(dest, "rb") as f:
                    if f.read() == data_or_path:
                        return dest, True
            except OSError:
                pass
        elif _same_file(data_or_path, dest):
            return dest, True
        stem, ext = os.path.splitext(name)
        n = 2
        while os.path.exists(dest):
            dest = os.path.join(USER_FONTS, "%s (%d)%s" % (stem, n, ext))
            n += 1
    if isinstance(data_or_path, bytes):
        with open(dest, "wb") as f:
            f.write(data_or_path)
    else:
        shutil.copyfile(data_or_path, dest)
    return dest, False


def add_user_fonts(paths, install=True):
    """Add font files (.ttf/.otf, or a .zip of them) to your fonts folder and make them usable right away.

    Returns (families added, families that were already there, problems)."""
    import zipfile
    os.makedirs(USER_FONTS, exist_ok=True)
    problems, placed = [], []          # placed: (path, already_there)
    for p in paths:
        low = p.lower()
        try:
            if low.endswith(".zip"):
                with zipfile.ZipFile(p) as z:
                    names = [n for n in z.namelist() if n.lower().endswith((".ttf", ".otf"))
                             and not os.path.basename(n).startswith(".") and "__MACOSX" not in n]
                    if not names:
                        problems.append("%s: no .ttf or .otf font inside" % os.path.basename(p))
                    for n in names:
                        placed.append(_place(z.read(n), os.path.basename(n)))
            elif low.endswith((".ttf", ".otf")):
                if os.path.normcase(os.path.dirname(os.path.abspath(p))) == os.path.normcase(os.path.abspath(USER_FONTS)):
                    placed.append((p, True))
                else:
                    placed.append(_place(p, os.path.basename(p)))
            else:
                problems.append("%s: not a .ttf, .otf or .zip font file" % os.path.basename(p))
        except Exception as e:
            problems.append("%s: %s" % (os.path.basename(p), e))
    added, already = [], []
    for f, had in placed:
        fam, _sub = _name_of(f)
        if not fam:
            problems.append("%s: not a readable font" % os.path.basename(f))
            continue
        if not had and os.name == "nt":
            try:
                import ctypes
                ctypes.windll.gdi32.AddFontResourceExW(ctypes.c_wchar_p(f), 0x10, 0)
            except Exception:
                log.exception("could not load %s", f)
        target = already if had else added
        if fam not in target and fam not in added:
            target.append(fam)
    already = [x for x in already if x not in added]
    global _registry
    with _lock:
        _registry = None          # re-scan so the new fonts appear in every list
    if install and added:
        try:
            install_into_windows()
        except Exception:
            log.exception("install new fonts")
    return added, already, problems


def all_files():
    out = []
    for e in registry():
        out += list(e["files"].values())
    return sorted(set(out))


def load_private():
    """Make all of Nobu's fonts usable inside Nobu straight away (no installation needed)."""
    os.makedirs(USER_FONTS, exist_ok=True)
    files = all_files()
    if os.name == "nt":
        try:
            import ctypes
            add = ctypes.windll.gdi32.AddFontResourceExW
            for f in files:
                if not add(ctypes.c_wchar_p(f), 0x10, 0):
                    log.warning("could not load font %s", f)
        except Exception:
            log.exception("font loading failed")
    return files


def install_into_windows(force=False):
    """Install Nobu's fonts for this Windows user (no admin) so Word etc. can use them.

    Returns the number of newly installed files."""
    if os.name != "nt":
        return 0
    import ctypes
    import winreg
    marker = os.path.join(CACHE, "fonts_installed.json")
    try:
        with open(marker, encoding="utf-8") as f:
            done = set(json.load(f))
    except Exception:
        done = set()
    dest_dir = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "Windows", "Fonts")
    os.makedirs(dest_dir, exist_ok=True)
    new = 0
    key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows NT\CurrentVersion\Fonts")
    for e in registry():
        for style, src in e["files"].items():
            ident = "%s|%s|%d" % (e["family"], style, os.path.getsize(src))
            if ident in done and not force:
                continue
            dest = os.path.join(dest_dir, "Nobu_" + os.path.basename(src))
            try:
                if not os.path.exists(dest) or os.path.getsize(dest) != os.path.getsize(src):
                    shutil.copy2(src, dest)
                label = {"regular": "", "bold": " Bold", "italic": " Italic", "bolditalic": " Bold Italic"}[style]
                ext = "OpenType" if src.lower().endswith(".otf") else "TrueType"
                winreg.SetValueEx(key, "%s%s (%s)" % (e["family"], label, ext), 0, winreg.REG_SZ, dest)
                ctypes.windll.gdi32.AddFontResourceW(ctypes.c_wchar_p(dest))
                done.add(ident)
                new += 1
            except Exception:
                log.exception("could not install font %s", src)
    winreg.CloseKey(key)
    if new:
        try:
            res = ctypes.c_ulong()
            ctypes.windll.user32.SendMessageTimeoutW(0xFFFF, 0x001D, 0, 0, 0x0002, 1000, ctypes.byref(res))
        except Exception:
            pass
    os.makedirs(CACHE, exist_ok=True)
    with open(marker, "w", encoding="utf-8") as f:
        json.dump(sorted(done), f)
    log.info("installed %d font files into Windows", new)
    return new


def families(root):
    try:
        return sorted({f for f in tkfont.families(root) if not f.startswith("@")}, key=str.lower)
    except Exception:
        return []


def pick(root, wanted, fallbacks):
    have = {f.lower(): f for f in families(root)}
    for name in [wanted] + list(fallbacks):
        if name and name.lower() in have:
            return have[name.lower()]
    return "TkDefaultFont"


def by_category(root):
    """{category: [family,...]} for the font menus/browser (Windows fonts last)."""
    reg = registry()
    known = set()
    out = {c: [] for c, _ in CATEGORIES}
    for e in reg:
        out.setdefault(e["category"], []).append(e["family"])
        known.add(e["family"].lower())
    for f in families(root):
        if f.lower() not in known and not f.startswith(("@", "Tk")):
            out["system"].append(f)
    return out


# ---------------------------------------------------------------- font files for exporters
def _windows_index():
    """family -> {style: path} for fonts installed in Windows (cached)."""
    os.makedirs(CACHE, exist_ok=True)
    dirs = []
    if os.name == "nt":
        dirs = [os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"),
                os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "Windows", "Fonts")]
    files = []
    for d in dirs:
        files += _font_files(d)
    cache_p = os.path.join(CACHE, "winfonts.json")
    try:
        with open(cache_p, encoding="utf-8") as f:
            c = json.load(f)
        if c.get("n") == len(files):
            return c["idx"]
    except Exception:
        pass
    idx = {}
    for p in files:
        fam, sub = _name_of(p)
        if fam:
            idx.setdefault(fam, {}).setdefault(_style_key(sub), p)
    try:
        with open(cache_p, "w", encoding="utf-8") as f:
            json.dump({"n": len(files), "idx": idx}, f)
    except OSError:
        pass
    return idx


_KNOWN_WIN = {   # common Windows fonts, so exports don't have to scan the whole Fonts folder
    "segoe ui symbol": ("seguisym.ttf", None, None, None), "segoe ui historic": ("seguihis.ttf", None, None, None),
    "segoe ui": ("segoeui.ttf", "segoeuib.ttf", "segoeuii.ttf", "segoeuiz.ttf"),
    "arial unicode ms": ("ARIALUNI.TTF", None, None, None),
    "times new roman": ("times.ttf", "timesbd.ttf", "timesi.ttf", "timesbi.ttf"),
    "georgia": ("georgia.ttf", "georgiab.ttf", "georgiai.ttf", "georgiaz.ttf"),
    "palatino linotype": ("pala.ttf", "palab.ttf", "palai.ttf", "palabi.ttf"),
    "book antiqua": ("BKANT.TTF", "ANTQUAB.TTF", "ANTQUAI.TTF", "ANTQUABI.TTF"),
    "arial": ("arial.ttf", "arialbd.ttf", "ariali.ttf", "arialbi.ttf"),
    "calibri": ("calibri.ttf", "calibrib.ttf", "calibrii.ttf", "calibriz.ttf"),
    "garamond": ("GARA.TTF", "GARABD.TTF", "GARAIT.TTF", None),
}


def font_file(family, bold=False, italic=False):
    """Best font file for a family/style (None if unknown). Returns (path, synthetic_bold, synthetic_italic)."""
    want = "bolditalic" if bold and italic else "bold" if bold else "italic" if italic else "regular"
    files = None
    for e in registry():
        if e["family"].lower() == (family or "").lower():
            files = e["files"]
            break
    if files is None and os.name == "nt":
        quick = _KNOWN_WIN.get((family or "").lower())
        if quick:
            wf = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
            cand = {k: os.path.join(wf, v) for k, v in zip(("regular", "bold", "italic", "bolditalic"), quick) if v}
            cand = {k: v for k, v in cand.items() if os.path.exists(v)}
            if "regular" in cand:
                files = cand
    if files is None:
        idx = _windows_index()
        for fam, f in idx.items():
            if fam.lower() == (family or "").lower():
                files = f
                break
    if not files:
        return None, False, False
    for k in (want, "regular" if want != "regular" else None, "bold", "italic", "bolditalic"):
        if k and k in files:
            return files[k], (bold and "bold" not in k), (italic and "italic" not in k)
    return None, False, False


def coverage(path):
    """Set of characters a font file can draw."""
    if path in _cover:
        return _cover[path]
    try:
        from fontTools.ttLib import TTFont
        t = TTFont(path, lazy=True, fontNumber=0)
        cm = set(t.getBestCmap().keys())
        t.close()
    except Exception:
        cm = set(range(32, 127))
    _cover[path] = cm
    return cm


def licence_blocks_embedding(family):
    """Fonts we must not pack into shared files: personal-use, demo and trial fonts."""
    f = (family or "").lower()
    if f.startswith("varnyx") or any(w in f for w in ("personal", "trial", "demo", "non-commercial", "noncommercial")):
        return True
    for e in registry():
        if e["family"].lower() == f and e["category"] == "yours":
            names = " ".join(os.path.basename(x).lower() for x in e["files"].values())
            if any(w in names for w in ("personal", "trial", "demo")):
                return True
    return False


