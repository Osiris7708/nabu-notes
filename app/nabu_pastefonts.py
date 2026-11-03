"""Fonts in pasted text: change them into the font and size the writer chose, and ask only when a paste
brings a fresh font.

* The fonts of the last paste are remembered (config "last_paste_fonts"; emptied and refilled by each paste
  that has fonts). A paste whose fonts were all in the last paste changes quietly; one with a font that
  wasn't opens the font window (PasteFontsWindow), one row per font in the paste.
* Choices are kept in config "paste_font_rules": {family in lower case: {"name": Family, "font": f, "size": s}}
  font: "" keep the pasted font, "*" use the note's own font, else a family name.
  size: 0 keep the pasted size, -1 use the note's own size, else points.
  They stay until changed in the window or in Settings > Fonts.
Text copied from another Nabu note is never changed or asked about.
"""
import tkinter as tk
from tkinter import ttk

import nabu_theme as T

FONT_KEEP = "Keep the pasted font"
FONT_MINE = "My note font"
SIZE_KEEP = "Keep the pasted size"
SIZE_MINE = "My note size"
SIZES = ["8", "9", "10", "10.5", "11", "12", "13", "14", "16", "18", "20", "22", "24", "28", "32", "36"]


def families_in(items):
    """The font families used in items, in order, each once (whatever the capitals)."""
    out, seen = [], set()
    for it in items:
        for g in it.get("g", []):
            if g.startswith("ff:"):
                fam = g[3:].strip()
                if fam and fam.lower() not in seen:
                    seen.add(fam.lower())
                    out.append(fam)
    return out


def _size_tag(pt):
    return "fs:" + ("%.1f" % float(pt)).rstrip("0").rstrip(".")


def apply_rules(items, rules):
    """A copy of items with each font changed as rules say (text in other fonts, pictures etc. untouched)."""
    if not rules:
        return items
    out = []
    for it in items:
        g = it.get("g", [])
        fam = next((x[3:].strip() for x in g if x.startswith("ff:")), None)
        rule = rules.get(fam.lower()) if fam else None
        if not rule:
            out.append(it)
            continue
        tags = list(g)
        f = rule.get("font") or ""
        if f:
            tags = [x for x in tags if not x.startswith("ff:")]
            if f != "*":
                tags.append("ff:" + f)
        s = rule.get("size") or 0
        if s:
            tags = [x for x in tags if not x.startswith("fs:")]
            if s > 0:
                tags.append(_size_tag(s))
        out.append(dict(it, g=sorted(set(tags))))
    return out


def fresh(fams, last):
    """The fonts of this paste that weren't in the last one."""
    had = {x.lower() for x in last or []}
    return [f for f in fams if f.lower() not in had]


def font_choices(root):
    import nabu_fonts
    cats = nabu_fonts.by_category(root)
    fams = []
    for c, _ in nabu_fonts.CATEGORIES:
        fams += cats.get(c, [])
    return [FONT_KEEP, FONT_MINE] + fams


SIZE_CHOICES = [SIZE_KEEP, SIZE_MINE] + SIZES


def font_label(rule):
    f = (rule or {}).get("font") or ""
    return FONT_KEEP if not f else FONT_MINE if f == "*" else f


def size_label(rule):
    s = (rule or {}).get("size") or 0
    return SIZE_KEEP if not s else SIZE_MINE if s < 0 else ("%.1f" % s).rstrip("0").rstrip(".")


def make_rule(name, font_text, size_text):
    """The rule for one row of drop-downs (None: keep everything as pasted)."""
    font_text = (font_text or "").strip()
    font = "" if font_text in ("", FONT_KEEP) else "*" if font_text == FONT_MINE else font_text
    size_text = (size_text or "").strip()
    if size_text in ("", SIZE_KEEP):
        size = 0
    elif size_text == SIZE_MINE:
        size = -1
    else:
        try:
            size = max(4.0, min(400.0, float(size_text)))
        except ValueError:
            size = 0
    if not font and not size:
        return None
    return {"name": name, "font": font, "size": size}


def describe(rule):
    """'EB Garamond, 13 pt' style summary of a rule."""
    if not rule:
        return "kept as pasted"
    f, s = rule.get("font") or "", rule.get("size") or 0
    return "%s, %s" % ("same font" if not f else "my note font" if f == "*" else f,
                       "same size" if not s else "my note size" if s < 0 else size_label(rule) + " pt")


def fetch_status(outcome, detail=""):
    """One line for the font window about looking for a free copy."""
    if outcome == "downloaded":
        return "✓ Downloaded (free, from Google Fonts) and added to your fonts."
    if outcome == "not_free":
        return ("✕ Not downloaded: there's no free, legal copy (it's probably a paid font). "
                "Here it shows in a similar font.")
    return "✕ Not downloaded: the download didn't work (%s). Try pasting again later." % (detail or "no internet?")


class PasteFontsWindow:
    """Shown after a paste with a fresh font: one row per font in the paste (what it is, whether it was
    downloaded, and drop-downs for what it should change into). Apply saves the choices and changes the
    text just pasted; Close leaves both as they were."""

    def __init__(self, editor, fams, on_apply):
        self.ed = editor
        self.app = editor.app
        self.on_apply = on_apply
        self.rows = {}           # family (lower case) -> (name, status label, font box, size box)
        rules = self.app.cfg.get("paste_font_rules") or {}
        win = self.win = T.toplevel(editor.frame, "Fonts in the pasted text")
        f = ttk.Frame(win, padding=18)
        f.pack(fill="both", expand=True)
        ttk.Label(f, wraplength=620, justify="left", text=(
            "This paste has a font your last paste didn't. Pick what each font should change into. Nabu "
            "remembers it for every paste in that font until you change it here or in Settings > Fonts.")
                  ).pack(anchor="w", pady=(0, 12))
        grid = ttk.Frame(f)
        grid.pack(fill="x")
        for c, head in enumerate(("Pasted font", "Change into", "Size")):
            ttk.Label(grid, text=head, style="Muted.TLabel").grid(row=0, column=c, sticky="w", padx=(0, 10))
        choices = font_choices(editor.root)
        for i, fam in enumerate(fams):
            r = 1 + 2 * i
            ttk.Label(grid, text=fam, font=T.UI_BOLD).grid(row=r, column=0, sticky="w", padx=(0, 10), pady=(6, 0))
            fb = ttk.Combobox(grid, values=choices, width=28, state="readonly")
            fb.set(font_label(rules.get(fam.lower())))
            fb.grid(row=r, column=1, sticky="w", padx=(0, 10), pady=(6, 0))
            sb = ttk.Combobox(grid, values=SIZE_CHOICES, width=18)
            sb.set(size_label(rules.get(fam.lower())))
            sb.grid(row=r, column=2, sticky="w", pady=(6, 0))
            st = ttk.Label(grid, text="", style="Muted.TLabel", wraplength=600, justify="left")
            st.grid(row=r + 1, column=0, columnspan=3, sticky="w")
            self.rows[fam.lower()] = (fam, st, fb, sb)
        b = ttk.Frame(f)
        b.pack(anchor="e", pady=(16, 0))
        ttk.Button(b, text="Close", command=self.close).pack(side="right", padx=(6, 0))
        ttk.Button(b, text="Apply", style="Accent.TButton", command=self.apply).pack(side="right")
        win.bind("<Escape>", lambda _e: self.close())
        win.protocol("WM_DELETE_WINDOW", self.close)
        T.fit(win)
        win.grab_set()

    def alive(self):
        try:
            return bool(self.win.winfo_exists())
        except tk.TclError:
            return False

    def set_status(self, fam, text):
        row = self.rows.get(fam.lower())
        if row and self.alive():
            row[1].configure(text=text)
            T.fit(self.win)

    def choices(self):
        """{family lower case: rule or None} from the drop-downs."""
        return {k: make_rule(name, fb.get(), sb.get()) for k, (name, _st, fb, sb) in self.rows.items()}

    def apply(self):
        rules = dict(self.app.cfg.get("paste_font_rules") or {})
        for k, rule in self.choices().items():
            if rule:
                rules[k] = rule
            else:
                rules.pop(k, None)
        self.app.cfg.update(paste_font_rules=rules)
        self.close()
        self.on_apply(rules)

    def close(self):
        if self.alive():
            self.win.destroy()
