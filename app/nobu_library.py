r"""The note library on disk.

Notes\                 library root
  Unassigned\          new transcripts land here (the inbox)
  <Project>\           one folder per book / campaign, holding .nobu notes
  .trash\              deleted things go here, never destroyed outright
"""
import datetime
import json
import os
import re
import shutil

import nobu_doc as nd
from nobu_config import INBOX_DIR, NOTES_DIR, TRASH_DIR, abs_from_home, rel_to_home

INBOX_NAME = "Unassigned"
EXT = ".nobu"


def safe_name(s, fallback="Untitled"):
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', " ", s or "")
    s = re.sub(r"\s+", " ", s).strip(" .")
    return (s[:80].strip() or fallback)


# Note titles may contain any character. Windows forbids  " / \\ : * ? < > |  in file names, so in the
# file name each one is swapped for a look-alike character, and swapped back wherever the title is shown.
_TO_FILE = {'"': "\uff02", "/": "\u2215", "\\": "\u29f5", ":": "\ua789", "*": "\uff0a", "?": "\uff1f",
            "<": "\uff1c", ">": "\uff1e", "|": "\uff5c"}
_FROM_FILE = {v: k for k, v in _TO_FILE.items()}
_FROM_FILE["\u2024"] = "."          # dots at the very end (Windows drops those)
_FROM_FILE["\u2060"] = ""           # marks a reserved device name such as CON or NUL
_RESERVED = {"CON", "PRN", "AUX", "NUL"} | {"COM%d" % i for i in range(1, 10)} | {"LPT%d" % i for i in range(1, 10)}


def note_stem(name, fallback="Untitled"):
    """The file name (without .nobu) for a note title; any symbols are kept (as look-alikes)."""
    s = re.sub(r"[\x00-\x1f\x7f]+", " ", name or "")
    s = re.sub(r"\s+", " ", s).strip()
    s = "".join(_TO_FILE.get(c, c) for c in s)[:110].strip()
    m = re.search(r"\.+$", s)
    if m:
        s = s[:m.start()] + "\u2024" * len(m.group())
    if not s:
        return fallback
    if s.split(".")[0].upper() in _RESERVED:
        s += "\u2060"
    return s


def same_title(text, path):
    """Would this title give the note the name it already has?"""
    stem = os.path.splitext(os.path.basename(path))[0]
    want = note_stem(text, "")
    return bool(want) and (want == stem or re.sub(r" \(\d+\)$", "", stem) == want)


def unique_path(folder, stem, ext=EXT):
    p = os.path.join(folder, stem + ext)
    n = 2
    while os.path.exists(p):
        p = os.path.join(folder, "%s (%d)%s" % (stem, n, ext))
        n += 1
    return p


def is_inbox(folder):
    return os.path.normcase(os.path.abspath(folder)) == os.path.normcase(os.path.abspath(INBOX_DIR))


def projects():
    out = []
    try:
        for name in os.listdir(NOTES_DIR):
            p = os.path.join(NOTES_DIR, name)
            if os.path.isdir(p) and not name.startswith(".") and name != INBOX_NAME:
                out.append(p)
    except FileNotFoundError:
        pass
    return _ordered(out, folder_meta(NOTES_DIR).get("order"))


def _scan(folder):
    """(notes [(path, mtime)], sub-folders [path]) in one pass over the folder (fast on Windows:
    the file times come with the listing, no extra disk reads)."""
    notes, subs = [], []
    try:
        with os.scandir(folder) as it:
            for e in it:
                n = e.name
                if n.startswith("."):
                    continue
                try:
                    if e.is_dir():
                        subs.append(e.path)
                    elif n.lower().endswith(EXT):
                        notes.append((e.path, e.stat().st_mtime))
                except OSError:
                    pass
    except (FileNotFoundError, NotADirectoryError, PermissionError):
        pass
    return notes, subs


def notes_in(folder):
    notes, _subs = _scan(folder)
    if is_inbox(folder):
        return [p for p, _m in sorted(notes, key=lambda x: x[1], reverse=True)]   # newest first
    return _ordered([p for p, _m in notes], folder_meta(folder).get("note_order"))


def subfolders(folder):
    """Sub-folders of a book/campaign folder (in your order, hidden ones skipped)."""
    _notes, subs = _scan(folder)
    return _ordered(subs, folder_meta(folder).get("order"))


def contents(folder):
    """(sub-folders, notes) of a folder, both in display order, from a single scan."""
    notes, subs = _scan(folder)
    meta = folder_meta(folder)
    if is_inbox(folder):
        ns = [p for p, _m in sorted(notes, key=lambda x: x[1], reverse=True)]
    else:
        ns = _ordered([p for p, _m in notes], meta.get("note_order"))
    return _ordered(subs, meta.get("order")), ns


def has_children(folder):
    try:
        with os.scandir(folder) as it:
            for e in it:
                if not e.name.startswith(".") and (e.name.lower().endswith(EXT) or e.is_dir()):
                    return True
    except OSError:
        pass
    return False


def count_notes(folder):
    """(notes, sub-folders) counted all the way down - cheap, no files are opened."""
    n = d = 0
    stack = [folder]
    while stack:
        notes, subs = _scan(stack.pop())
        n += len(notes)
        d += len(subs)
        stack.extend(subs)
    return n, d


def _ordered(paths, order):
    """Alphabetical, except items you have dragged into place (their order is remembered)."""
    alpha = sorted(paths, key=lambda p: os.path.basename(p).lower())
    if not order:
        return alpha
    rank = {n: i for i, n in enumerate(order)}
    placed = sorted([p for p in alpha if os.path.basename(p) in rank], key=lambda p: rank[os.path.basename(p)])
    rest = [p for p in alpha if os.path.basename(p) not in rank]
    return placed + rest


_meta_cache = {}


def folder_meta(folder):
    p = os.path.join(folder, FOLDER_META)
    try:
        mt = os.stat(p).st_mtime_ns
    except OSError:
        return {}
    c = _meta_cache.get(p)
    if c and c[0] == mt:
        return dict(c[1])
    try:
        with open(p, encoding="utf-8") as f:
            m = json.load(f)
        m = m if isinstance(m, dict) else {}
    except Exception:
        m = {}
    _meta_cache[p] = (mt, m)
    return dict(m)


def _write_meta(folder, meta):
    p = os.path.join(folder, FOLDER_META)
    hidden_api = None
    if os.name == "nt":
        try:
            import ctypes
            hidden_api = ctypes.windll.kernel32.SetFileAttributesW
            if os.path.exists(p):
                hidden_api(p, 0x80)      # un-hide so it can be rewritten
        except Exception:
            hidden_api = None
    os.makedirs(folder, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False)
    _meta_cache.pop(p, None)
    if hidden_api:
        try:
            hidden_api(p, 0x02)
        except Exception:
            pass


def set_order(parent, names, key="order"):
    meta = folder_meta(parent)
    meta[key] = list(names)
    _write_meta(parent, meta)


def _rename_in_order(parent, old, new):
    meta = folder_meta(parent)
    changed = False
    for key in ("order", "note_order"):
        lst = meta.get(key)
        if lst and old in lst:
            lst[lst.index(old)] = new
            changed = True
    if changed:
        _write_meta(parent, meta)


def place(path, target, where):
    """Drag & drop: put a note or folder 'into' a folder, or 'above' / 'below' another item.
    Returns the item's new path."""
    if where == "into":
        if not os.path.isdir(target):
            raise ValueError("Notes can only go into folders.")
        return move_item(path, target)
    parent = os.path.dirname(target)
    top = os.path.normcase(os.path.abspath(parent)) == os.path.normcase(os.path.abspath(NOTES_DIR))
    if top and not os.path.isdir(path):
        raise ValueError("Notes live inside a book or campaign (or Unassigned) - drop it onto a folder.")
    if os.path.normcase(os.path.dirname(os.path.abspath(path))) != os.path.normcase(os.path.abspath(parent)):
        path = move_item(path, parent)
    if os.path.isdir(path) != os.path.isdir(target) or (not top and is_inbox(parent)):
        return path       # folders are always listed before notes; inbox is newest-first
    if os.path.isdir(path):
        siblings, key = (projects() if top else subfolders(parent)), "order"
    else:
        siblings, key = notes_in(parent), "note_order"
    names = [os.path.basename(x) for x in siblings if os.path.normcase(x) != os.path.normcase(path)]
    tname = os.path.basename(target)
    i = names.index(tname) + (1 if where == "below" else 0) if tname in names else len(names)
    names.insert(i, os.path.basename(path))
    set_order(parent, names, key)
    return path


def all_notes(folder):
    """Every note in a folder and all its sub-folders."""
    out = list(notes_in(folder))
    for sub in subfolders(folder):
        out += all_notes(sub)
    return out


def all_folders(folder=None, depth=0):
    """(path, depth) for every book/campaign folder and sub-folder, in sidebar order."""
    out = []
    for p in (projects() if folder is None else subfolders(folder)):
        out.append((p, depth))
        out += all_folders(p, depth + 1)
    return out


def book_of(path):
    """The book / campaign (top-level folder) a note or folder belongs to; None for Unassigned and the rest."""
    d = os.path.abspath(path if os.path.isdir(path) else os.path.dirname(path))
    root = os.path.normcase(os.path.abspath(NOTES_DIR))
    while True:
        up = os.path.dirname(d)
        if os.path.normcase(up) == root:
            return None if is_inbox(d) else d
        if up == d:
            return None
        d = up


def is_top_level(folder):
    return os.path.normcase(os.path.dirname(os.path.abspath(folder))) == os.path.normcase(os.path.abspath(NOTES_DIR))


def crumbs(folder):
    """'The Hollow Crown \u25b8 Characters' style label for a folder inside the library."""
    try:
        rel = os.path.relpath(folder, NOTES_DIR)
    except ValueError:
        return os.path.basename(folder)
    parts = [x for x in re.split(r"[\\/]", rel) if x and x != "."]
    return " \u25b8 ".join(parts)


def create_folder(parent, name):
    name = safe_name(name)
    p = os.path.join(parent, name)
    if os.path.exists(p):
        raise ValueError("A folder called \u201c%s\u201d already exists there." % name)
    os.makedirs(p)
    return p


def move_item(path, folder):
    """Move a note or a whole folder into another folder."""
    if os.path.isdir(path):
        src, dst = os.path.normcase(os.path.abspath(path)), os.path.normcase(os.path.abspath(folder))
        if dst == src or dst.startswith(src + os.sep):
            raise ValueError("A folder can't be moved inside itself.")
        if os.path.normcase(os.path.dirname(src)) == dst:
            return path
        dest = os.path.join(folder, os.path.basename(path))
        n = 2
        while os.path.exists(dest):
            dest = os.path.join(folder, "%s (%d)" % (os.path.basename(path), n))
            n += 1
        shutil.move(path, dest)
        return dest
    return move_note(path, folder)


def inbox_count():
    return len(_scan(INBOX_DIR)[0])


def title(path):
    stem = os.path.splitext(os.path.basename(path))[0]
    if any(c in _FROM_FILE for c in stem):
        return "".join(_FROM_FILE.get(c, c) for c in stem)
    return stem


def create_project(name):
    name = safe_name(name)
    if name.lower() == INBOX_NAME.lower():
        raise ValueError("That name is reserved for the inbox.")
    p = os.path.join(NOTES_DIR, name)
    if os.path.exists(p):
        raise ValueError("A project called “%s” already exists." % name)
    os.makedirs(p)
    return p


def rename_project(path, new_name):
    new_name = safe_name(new_name)
    if new_name.lower() == INBOX_NAME.lower():
        raise ValueError("That name is reserved for the inbox.")
    dest = os.path.join(os.path.dirname(path), new_name)
    if os.path.normcase(dest) == os.path.normcase(path):
        return path
    if os.path.exists(dest):
        raise ValueError("A project called “%s” already exists." % new_name)
    os.rename(path, dest)
    _rename_in_order(os.path.dirname(path), os.path.basename(path), os.path.basename(dest))
    return dest


# ---------------------------------------------------------------- trash
# Every deleted thing becomes one bundle folder in Notes\.trash:
#   <stamp> <name>\item\<the note file or project folder>
#                  \audio\<its recordings>
#                  \info.json   (where everything came from, so it can be restored)

def _note_audio(note_path):
    try:
        doc = nd.load_doc(note_path)
    except Exception:
        return []
    out = []
    for wav in nd.audio_files(doc):
        for p in (wav, os.path.splitext(wav)[0] + ".txt"):
            if os.path.exists(p):
                out.append(p)
    return out


def to_trash(path, with_audio=True):
    os.makedirs(TRASH_DIR, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    is_dir = os.path.isdir(path)
    name = os.path.basename(path) if is_dir else title(path)
    bundle = os.path.join(TRASH_DIR, safe_name("%s %s" % (stamp, name)))
    n = 2
    while os.path.exists(bundle):
        bundle = os.path.join(TRASH_DIR, safe_name("%s %s (%d)" % (stamp, name, n)))
        n += 1
    os.makedirs(os.path.join(bundle, "item"))
    audio = []
    if with_audio:
        notes = all_notes(path) if is_dir else [path]
        for note in notes:
            audio += _note_audio(note)
    moved_audio = []
    if audio:
        os.makedirs(os.path.join(bundle, "audio"))
        for a in audio:
            dest = os.path.join(bundle, "audio", os.path.basename(a))
            try:
                shutil.move(a, dest)
                moved_audio.append({"from": rel_to_home(a), "name": os.path.basename(a)})
            except OSError:
                pass
    shutil.move(path, os.path.join(bundle, "item", os.path.basename(path)))
    bak = os.path.join(NOTES_DIR, ".backups", os.path.basename(path) + ".bak")
    if not is_dir and os.path.exists(bak):
        try:
            os.remove(bak)
        except OSError:
            pass
    info = {"type": ("project" if is_top_level(path) else "folder") if is_dir else "note", "name": name, "from": rel_to_home(path),
            "deleted": datetime.datetime.now().isoformat(timespec="seconds"), "audio": moved_audio}
    with open(os.path.join(bundle, "info.json"), "w", encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False, indent=1)
    return bundle


def trash_items():
    """List of (bundle_path, info) newest first."""
    out = []
    try:
        names = os.listdir(TRASH_DIR)
    except FileNotFoundError:
        return out
    for n in names:
        b = os.path.join(TRASH_DIR, n)
        if not os.path.isdir(b):
            continue
        try:
            with open(os.path.join(b, "info.json"), encoding="utf-8") as f:
                info = json.load(f)
        except Exception:
            info = {"type": "?", "name": n, "deleted": ""}
        out.append((b, info))
    out.sort(key=lambda x: x[1].get("deleted", ""), reverse=True)
    return out


def trash_count():
    try:
        with os.scandir(TRASH_DIR) as it:
            return sum(1 for e in it if e.is_dir())
    except OSError:
        return 0


def restore(bundle):
    """Put a trashed item (and its audio) back where it was. Returns the restored path."""
    with open(os.path.join(bundle, "info.json"), encoding="utf-8") as f:
        info = json.load(f)
    item_dir = os.path.join(bundle, "item")
    inner = os.listdir(item_dir)[0]
    src = os.path.join(item_dir, inner)
    orig = abs_from_home(info["from"])
    if info["type"] in ("project", "folder"):
        os.makedirs(os.path.dirname(orig), exist_ok=True)     # parent folder may be gone too
        dest = orig
        n = 2
        while os.path.exists(dest):
            dest = "%s (%d)" % (orig, n)
            n += 1
    else:
        folder = os.path.dirname(orig)
        os.makedirs(folder, exist_ok=True)
        dest = unique_path(folder, title(orig))
    shutil.move(src, dest)
    for a in info.get("audio", []):
        s = os.path.join(bundle, "audio", a["name"])
        d = abs_from_home(a["from"])
        if os.path.exists(s):
            os.makedirs(os.path.dirname(d), exist_ok=True)
            if not os.path.exists(d):
                shutil.move(s, d)
    shutil.rmtree(bundle, ignore_errors=True)
    return dest


def to_recycle_bin(paths):
    """Permanently remove from Nobu: send to the Windows Recycle Bin (recoverable there)."""
    paths = [os.path.abspath(p) for p in paths if os.path.exists(p)]
    if not paths:
        return True
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        class SHFILEOPSTRUCTW(ctypes.Structure):
            _fields_ = [("hwnd", wintypes.HWND), ("wFunc", wintypes.UINT), ("pFrom", ctypes.c_void_p),
                        ("pTo", wintypes.LPCWSTR), ("fFlags", ctypes.c_uint16), ("fAnyOperationsAborted", wintypes.BOOL),
                        ("hNameMappings", ctypes.c_void_p), ("lpszProgressTitle", wintypes.LPCWSTR)]
        FO_DELETE = 3
        flags = 0x0040 | 0x0010 | 0x0004 | 0x0400   # ALLOWUNDO | NOCONFIRMATION | SILENT | NOERRORUI
        buf = ctypes.create_unicode_buffer("\0".join(paths) + "\0\0")   # double-NUL-terminated list
        op = SHFILEOPSTRUCTW(None, FO_DELETE, ctypes.addressof(buf), None, flags, False, None, None)
        res = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
        return res == 0 and not op.fAnyOperationsAborted
    for p in paths:   # other systems (testing): delete outright
        if os.path.isdir(p):
            shutil.rmtree(p, ignore_errors=True)
        else:
            os.remove(p)
    return True


def migrate_trash():
    """v2 put loose note files in .trash; wrap them in bundles, and tidy old .bak files."""
    try:
        names = os.listdir(TRASH_DIR)
    except FileNotFoundError:
        names = []
    for n in names:
        p = os.path.join(TRASH_DIR, n)
        if os.path.isfile(p) and n.lower().endswith(EXT):
            stamp = n[:15]
            bundle = os.path.join(TRASH_DIR, os.path.splitext(n)[0])
            os.makedirs(os.path.join(bundle, "item"), exist_ok=True)
            orig_name = n[16:] if len(n) > 16 else n
            shutil.move(p, os.path.join(bundle, "item", orig_name))
            try:
                d = datetime.datetime.strptime(stamp, "%Y%m%d-%H%M%S").isoformat(timespec="seconds")
            except ValueError:
                d = ""
            with open(os.path.join(bundle, "info.json"), "w", encoding="utf-8") as f:
                json.dump({"type": "note", "name": os.path.splitext(orig_name)[0], "deleted": d,
                           "from": rel_to_home(os.path.join(INBOX_DIR, orig_name)), "audio": []}, f)
    # one-time tidy of old .bak files (walking the whole library at every start would be slow with big libraries)
    marker = os.path.join(os.path.dirname(_cache_file()), ".tidied-v4")
    if os.path.exists(marker):
        return
    for dp, _dirs, files in os.walk(NOTES_DIR):
        if ".trash" in dp or ".backups" in dp:
            continue
        for f in files:
            if f.endswith(".nobu.bak"):
                try:
                    os.remove(os.path.join(dp, f))
                except OSError:
                    pass
    try:
        os.makedirs(os.path.dirname(marker), exist_ok=True)
        open(marker, "w").close()
    except OSError:
        pass


def create_note(folder, name, items=None):
    os.makedirs(folder, exist_ok=True)
    path = unique_path(folder, note_stem(name))
    doc = nd.empty_doc()
    doc["items"] = items if items is not None else [{"t": title(path) + "\n", "g": ["st:title"]}, {"t": "\n", "g": []}]
    nd.save_doc(path, doc)
    return path


def rename_note(path, new_name, sync_title=False):
    """Rename a note. sync_title: also change the Title line inside it, if it showed the old name."""
    shown = re.sub(r"\s+", " ", new_name or "").strip()
    stem = note_stem(new_name)
    folder = os.path.dirname(path)
    if same_title(new_name, path):
        return path
    old = title(path)
    dest = unique_path(folder, stem)
    os.rename(path, dest)
    _rename_in_order(folder, os.path.basename(path), os.path.basename(dest))
    if sync_title:
        try:
            doc = nd.load_doc(dest)
            for it in doc.get("items", [])[:12]:
                if "st:title" in it.get("g", []) and it.get("t", "").rstrip("\n").strip() == old:
                    it["t"] = shown + ("\n" if it["t"].endswith("\n") else "")
                    nd.save_doc(dest, doc)
                    break
        except Exception:
            pass
    return dest


def move_note(path, folder):
    if os.path.normcase(os.path.dirname(os.path.abspath(path))) == os.path.normcase(os.path.abspath(folder)):
        return path
    dest = unique_path(folder, title(path))
    shutil.move(path, dest)
    return dest


# ---------------------------------------------------------------- note info & colour labels
# Colour labels: 8 families (columns in the menu), light to deep. The first 12 names/values are the
# original ones, so labels you've already set keep their names.
COLOR_FAMILIES = [
    ("Reds", [("Blush", "#ffb3b3"), ("Coral", "#ff8a80"), ("Crimson", "#e06666"), ("Scarlet", "#e04848"),
              ("Ruby", "#c43c4c")]),
    ("Oranges", [("Peach", "#ffc9a0"), ("Apricot", "#ffad73"), ("Ember", "#f08a4b"), ("Rust", "#d9703a"),
                 ("Copper", "#c0794b")]),
    ("Yellows", [("Butter", "#fff1a0"), ("Lemon", "#f7e26b"), ("Gold", "#e8cf6a"), ("Amber", "#e0a33a"),
                 ("Mustard", "#c9a227")]),
    ("Greens", [("Mint", "#b8f0c0"), ("Lime", "#c2e86a"), ("Moss", "#9bc26b"), ("Emerald", "#4cc38a"),
                ("Forest", "#4e9e5c")]),
    ("Teals", [("Aqua", "#a6eee6"), ("Turquoise", "#5fd8cc"), ("Teal", "#45c4c0"), ("Lagoon", "#2fa9b5"),
               ("Pine", "#3c8f8a")]),
    ("Blues", [("Ice", "#c4e2ff"), ("Sky", "#6fb6f0"), ("Cornflower", "#8fa8f8"), ("Royal blue", "#7f9cf5"),
               ("Sapphire", "#5c7fe0")]),
    ("Purples & pinks", [("Lavender", "#d6c4ff"), ("Violet", "#b28cf0"), ("Plum", "#a070c8"), ("Orchid", "#e08ce0"),
                         ("Rose", "#f08cc0")]),
    ("Earth & greys", [("Sand", "#e0c9a0"), ("Tan", "#c8a27a"), ("Bark", "#a07a58"), ("Silver", "#c8ccd6"),
                       ("Slate", "#a0a8b8")]),
]
COLORS = [c for _f, cols in COLOR_FAMILIES for c in cols]
FOLDER_META = ".nobufolder"
_info_cache = {}        # path -> (mtime, size, info); kept on disk between runs (cache\noteinfo.json)
_cache_state = {"loaded": False, "dirty": 0}
_EMPTY_INFO = {"color": None, "preview": "", "audio": False, "titled": False}


def _cache_file():
    from nobu_config import HOME
    return os.path.join(HOME, "cache", "noteinfo.json")


def _load_cache():
    _cache_state["loaded"] = True
    try:
        with open(_cache_file(), encoding="utf-8") as f:
            data = json.load(f)
        if data.get("v") == 2:
            for k, (mt, size, info) in data.get("notes", {}).items():
                _info_cache[abs_from_home(k)] = (mt, size, info)
    except Exception:
        pass


def save_cache(prune=False):
    """Write the note summaries to disk so the next start doesn't have to open every note again."""
    if not _cache_state["dirty"] and not prune:
        return
    items = list(_info_cache.items())
    if prune:
        items = [(k, v) for k, v in items if os.path.exists(k)]
    try:
        os.makedirs(os.path.dirname(_cache_file()), exist_ok=True)
        tmp = _cache_file() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"v": 2, "notes": {rel_to_home(k): list(v) for k, v in items}}, f, ensure_ascii=False)
        os.replace(tmp, _cache_file())
        _cache_state["dirty"] = 0
    except Exception:
        pass


def note_info(path, st=None):
    """{'color', 'preview', 'audio', 'titled', 'mtime'} for a note, cached until the file changes."""
    if not _cache_state["loaded"]:
        _load_cache()
    try:
        st = st or os.stat(path)
    except OSError:
        return dict(_EMPTY_INFO, mtime=0)
    mt, size = st.st_mtime, st.st_size
    c = _info_cache.get(path)
    if c and c[0] == mt and c[1] == size:
        return c[2]
    try:
        doc = nd.load_doc(path)
    except Exception:
        doc = {"items": []}
    parts, audio, n = [], False, 0
    for it in doc.get("items", []):
        g = it.get("g", [])
        if not audio and any(x.startswith("audio|") for x in g):
            audio = True
        if n < 400 and "t" in it and "meta" not in g and "lm" not in g and \
                not ({"h1", "st:h1", "st:title"} & set(g)):
            parts.append(it["t"])
            n += len(it["t"])
    txt = re.sub(r"\s+", " ", "".join(parts)).strip()[:400]
    info = {"color": doc.get("color"), "preview": txt, "audio": audio, "titled": bool(doc.get("titled")),
            "mtime": mt}
    _info_cache[path] = (mt, size, info)
    _cache_state["dirty"] += 1
    return info


def preview(path, n=110):
    txt = note_info(path)["preview"]
    return txt[:n] + ("…" if len(txt) > n else "")


def set_note_color(path, color):
    doc = nd.load_doc(path)
    if color:
        doc["color"] = color
    else:
        doc.pop("color", None)
    nd.save_doc(path, doc)


def folder_color(folder):
    return folder_meta(folder).get("color")


def set_folder_color(folder, color):
    meta = folder_meta(folder)
    if color:
        meta["color"] = color
    else:
        meta.pop("color", None)
    _write_meta(folder, meta)


AUTO_NAME = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}\.\d{2}")


def is_auto_named(path):
    """Transcripts are named '2026-10-21 10.55 – first words' until you give them a title."""
    return bool(AUTO_NAME.match(title(path)))


def make_inbox_note(started, wav_path, paragraphs):
    when = started or datetime.datetime.now()
    first = " ".join(" ".join(paragraphs).split()[:7]) if paragraphs else "(no speech recognized)"
    first = re.sub(r"[.,;:!?]+$", "", first)
    stem = "%s – %s" % (when.strftime("%Y-%m-%d %H.%M"), note_stem(first, "Recording"))
    path = unique_path(INBOX_DIR, note_stem(stem))
    doc = nd.empty_doc()
    doc["items"] = nd.transcript_items(when, wav_path, paragraphs)
    os.makedirs(INBOX_DIR, exist_ok=True)
    nd.save_doc(path, doc)
    return path


def migrate_legacy():
    """v1 kept notes directly in Notes\\ - move them into the inbox."""
    moved = []
    try:
        names = os.listdir(NOTES_DIR)
    except FileNotFoundError:
        return moved
    for f in names:
        p = os.path.join(NOTES_DIR, f)
        if os.path.isfile(p) and f.lower().endswith(EXT):
            moved.append(move_note(p, INBOX_DIR))
        elif os.path.isfile(p) and f.lower().endswith((".bak", ".tmp")):
            try:
                os.remove(p)
            except OSError:
                pass
    return moved
