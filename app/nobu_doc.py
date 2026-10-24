"""Note file format (.nobu) and helpers that work without any window.

A note is JSON: {"format": "nobu-note", "version": 1, "items": [...]} where an
item is {"t": "text", "g": [tags]} or {"i": "Images/x.png", "w": 400, "g": [tags]}.
Image paths are relative to the Nobu Notes folder, so the folder can be moved.
"""
import json
import os
import shutil
import time

from nobu_config import HOME, IMAGES_DIR, abs_from_home, rel_to_home

AUDIO_PREFIX = "audio|"


def persistent(tag):
    import nobu_rich
    return nobu_rich.persistent(tag) or tag in ("h1", "h2", "center")


def empty_doc():
    return {"format": "nobu-note", "version": 2, "items": []}


def load_doc(path):
    with open(path, "r", encoding="utf-8") as f:
        d = json.load(f)
    if not isinstance(d, dict) or "items" not in d:
        raise ValueError("Not a Nobu note file")
    return d


def save_doc(path, doc):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False)
    if os.path.exists(path):
        try:   # one backup per note, kept out of sight in Notes\.backups
            bdir = os.path.join(HOME, "Notes", ".backups")
            os.makedirs(bdir, exist_ok=True)
            shutil.copy2(path, os.path.join(bdir, os.path.basename(path) + ".bak"))
        except OSError:
            pass
    os.replace(tmp, path)


def audio_files(doc):
    """Recordings linked from a note (absolute paths)."""
    out = []
    for it in doc.get("items", []):
        for g in it.get("g", []):
            if g.startswith(AUDIO_PREFIX):
                p = abs_from_home(g[len(AUDIO_PREFIX):])
                if p not in out:
                    out.append(p)
    return out


def welcome_items():
    return [
        {"t": "Nobu Notes\n", "g": ["st:title"]},
        {"t": "Your voice-to-text notebook for writing.\n", "g": ["st:subtitle"]},
        {"t": "How it works\n", "g": ["st:h1"]},
        {"t": "Say  “Nobu, record this”  (said “no-boo”) and start talking. Recording stops after 8 seconds of "
              "silence, or when you say  “Nobu, end recording”. Each recording becomes a note in "
              "Unassigned, ready to file into a book or campaign.\n", "g": []},
        {"t": "Writing\n", "g": ["st:h1"]},
        {"t": "The page works like Word: styles, fonts, sizes, colours, lists, tables, pictures, page breaks, "
              "spell check (red underline, right-click for suggestions) and a thesaurus (right-click a word). "
              "Use ⇧ Export / share to make a Word file, PDF, e-book or web page.\n", "g": []},
        {"t": "You can delete this text whenever you like.\n", "g": ["meta"]},
    ]


def transcript_items(when, wav_path, paragraphs):
    stamp = when.strftime("%b %d, %Y  ·  %I:%M %p")
    if stamp.count(" 0"):
        stamp = stamp.replace(" 0", " ")
    rel = rel_to_home(wav_path)
    items = [
        {"t": stamp + "    ", "g": ["meta"]},
        {"t": "▶ Play recording", "g": ["meta", AUDIO_PREFIX + rel]},
        {"t": "\n", "g": []},
    ]
    for p in paragraphs:
        items.append({"t": p + "\n", "g": []})
    if not paragraphs:
        items.append({"t": "(no speech recognized)\n", "g": ["meta"]})
    items.append({"t": "\n", "g": []})
    return items


def _last_text(items):
    for it in reversed(items):
        if "t" in it and it["t"]:
            return it["t"]
        if "i" in it:
            return "\u0000"
    return ""


def append_items_to_file(path, new_items):
    """Append items to a note on disk (note not open in the editor)."""
    try:
        doc = load_doc(path)
    except FileNotFoundError:
        doc = empty_doc()
        doc["items"] = welcome_items()
    items = doc["items"]
    last = _last_text(items)
    if last and not last.endswith("\n"):
        items.append({"t": "\n", "g": []})
    items.extend(new_items)
    save_doc(path, doc)


def import_image(src, note_path):
    """Copy an image into Images/<note>/ and return its path relative to HOME."""
    stem = os.path.splitext(os.path.basename(note_path or "Notes"))[0]
    folder = os.path.join(IMAGES_DIR, stem)
    os.makedirs(folder, exist_ok=True)
    src_abs = os.path.abspath(src)
    try:
        if os.path.commonpath([os.path.abspath(folder), src_abs]) == os.path.abspath(folder):
            return rel_to_home(src_abs)
    except ValueError:
        pass
    base, ext = os.path.splitext(os.path.basename(src))
    dest = os.path.join(folder, base + ext)
    n = 2
    while os.path.exists(dest):
        dest = os.path.join(folder, "%s_%d%s" % (base, n, ext))
        n += 1
    shutil.copy2(src, dest)
    return rel_to_home(dest)


def save_pil_image(img, note_path):
    stem = os.path.splitext(os.path.basename(note_path or "Notes"))[0]
    folder = os.path.join(IMAGES_DIR, stem)
    os.makedirs(folder, exist_ok=True)
    name = "pasted_" + time.strftime("%Y%m%d_%H%M%S")
    dest = os.path.join(folder, name + ".png")
    n = 2
    while os.path.exists(dest):
        dest = os.path.join(folder, "%s_%d.png" % (name, n))
        n += 1
    img.save(dest, "PNG")
    return rel_to_home(dest)


def to_html(doc, title="Nobu Note"):
    import nobu_rich as R
    return R.to_html(R.items_to_paras(doc.get("items", [])), R.Ctx(), full_page=True, title=title)

