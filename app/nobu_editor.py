"""The note editor: a Word-style page (8.5\" wide, 1\" margins) with a full formatting ribbon,
lists, tables, pictures, page breaks, pagination, zoom, spell check and thesaurus."""
import bisect
import datetime
import difflib
import logging
import os
import re
import subprocess
import sys
import time
import tkinter as tk
import tkinter.font as tkfont
from tkinter import colorchooser, filedialog, ttk

from PIL import Image

import nobu_clip
import nobu_doc as nd
import nobu_float
import nobu_pictool
import nobu_library as lib
import nobu_rich as R
import nobu_theme as T
from nobu_config import abs_from_home

log = logging.getLogger("nobu.editor")

IMG_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tif", ".tiff")
PAPER = T.PAPER      # set from the colour theme when this module is first imported
DESK = T.DESK
INK = T.INK
SIZES_PT = ["8", "9", "10", "10.5", "11", "12", "13", "14", "16", "18", "20", "22", "24", "26", "28", "32", "36",
            "40", "48", "60", "72"]
ZOOMS = ["Fit width", "50%", "75%", "90%", "100%", "110%", "125%", "150%", "175%", "200%"]
TEXT_COLORS = [("Automatic", None), ("Black", "#000000"), ("Dark red", "#c00000"), ("Red", "#ff0000"),
               ("Orange", "#ffc000"), ("Yellow", "#ffff00"), ("Light green", "#92d050"), ("Green", "#00b050"),
               ("Light blue", "#00b0f0"), ("Blue", "#0070c0"), ("Dark blue", "#002060"), ("Purple", "#7030a0"),
               ("Grey", "#7f7f7f"), ("Gold", "#bf9000"), ("Blood", "#8b0000"), ("Moss", "#6b8e23")]
HIGHLIGHTS = [("Yellow", "#ffff00"), ("Bright green", "#00ff00"), ("Turquoise", "#00ffff"), ("Pink", "#ff00ff"),
              ("Blue", "#0000ff"), ("Red", "#ff0000"), ("Dark blue", "#000080"), ("Teal", "#008080"),
              ("Green", "#008000"), ("Violet", "#800080"), ("Dark red", "#800000"), ("Dark yellow", "#808000"),
              ("Grey 50%", "#808080"), ("Grey 25%", "#c0c0c0")]
SYMBOLS = [("Punctuation", "— – … “ ” ‘ ’ « » ¡ ¿ • · ¶ § † ‡ ‰ ′ ″"),
           ("Signs", "© ® ™ ° ± × ÷ ≈ ≠ ≤ ≥ ∞ √ µ € £ ¥ ¢"),
           ("Arrows & shapes", "← → ↑ ↓ ↔ ⇒ ★ ☆ ✦ ✧ ❖ ◆ ◇ ○ ● ♠ ♣ ♥ ♦ ☽ ☾ ☀ ⚔ ⚚ ☠ ⚜"),
           ("Fractions", "½ ⅓ ⅔ ¼ ¾ ⅛"),
           ("Accented", "á à â ä ã å æ ç é è ê ë í ì î ï ñ ó ò ô ö õ ø œ ú ù û ü ý ÿ ß Á É Í Ó Ú Ñ Ä Ö Ü Æ Ø ð þ"),
           ("Runes", "ᚠ ᚢ ᚦ ᚨ ᚱ ᚲ ᚷ ᚹ ᚺ ᚾ ᛁ ᛃ ᛇ ᛈ ᛉ ᛊ ᛏ ᛒ ᛖ ᛗ ᛚ ᛜ ᛞ ᛟ")]
BULLETS = ["•", "◦", "▪"]
VOICE_EDIT = "Nobu, edit this"
VOICE_CUT = "Nobu, cut this"


def open_path(path):
    try:
        if sys.platform.startswith("win"):
            os.startfile(path)  # noqa
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception:
        log.exception("could not open %s", path)


def _btn(parent, text, cmd, font=None, width=None, tip=None, bg=None):
    b = tk.Button(parent, text=text, command=cmd, relief="flat", bd=0, padx=5, pady=3,
                  bg=bg or T.PANEL, fg=T.FG, activebackground=T.HOVER, activeforeground=T.FG,
                  font=font or T.UI_FONT, cursor="hand2", highlightthickness=0)
    if width:
        b.config(width=width)
    if tip:
        _Tip(b, tip)
    return b


class _Tip:
    """A tooltip that appears when the mouse rests on a button (not while just passing over it)."""
    DELAY = 450

    def __init__(self, w, text):
        self.w, self.text, self.top, self.job = w, text, None, None
        w.bind("<Enter>", self._soon, add="+")
        w.bind("<Leave>", self.hide, add="+")
        w.bind("<ButtonPress>", self.hide, add="+")

    def _soon(self, _e=None):
        if self.job is None and self.top is None:
            self.job = T.later(self.w, self.DELAY, self.show)

    def show(self, _e=None):
        self.job = None
        if self.top:
            return
        try:
            if not self.w.winfo_viewable():
                return
        except tk.TclError:
            return
        self.top = t = tk.Toplevel(self.w)
        t.overrideredirect(True)
        t.attributes("-topmost", True)
        tk.Label(t, text=self.text, bg=T.HOVER, fg=T.FG, font=T.UI_FONT, padx=8, pady=3).pack()
        t.geometry("+%d+%d" % (self.w.winfo_rootx(), self.w.winfo_rooty() + self.w.winfo_height() + 4))

    def hide(self, _e=None):
        if self.job is not None:
            try:
                self.w.after_cancel(self.job)
            except tk.TclError:
                pass
            self.job = None
        if self.top:
            try:
                self.top.destroy()
            except tk.TclError:
                pass
            self.top = None


# ====================================================================== blocks inside the page
class TableBlock:
    def __init__(self, ed, rows):
        self.ed = ed
        self.frame = tk.Frame(ed.text, bg=T.FAINT, bd=0)
        self.cells = []
        rows = rows or [["", ""], ["", ""]]
        for r in rows:
            self._add_row_widgets(r)
        self._layout()

    def _cell(self, text=""):
        c = tk.Text(self.frame, height=1, wrap="word", font=self.ed.font_for_body(), bg=PAPER, fg=INK,
                    insertbackground=INK, relief="flat", padx=6, pady=3, undo=True, highlightthickness=0,
                    selectbackground=T.SELECT)
        c.insert("1.0", text)
        self.ed._watch_widget(c)
        c.bind("<KeyRelease>", lambda e, c=c: self._fit(c), add="+")
        c.bind("<Button-3>", lambda e, c=c: self._menu(e, c))
        c.bind("<Tab>", lambda e, c=c: (self._next(c, 1), "break")[1])
        c.bind("<Shift-Tab>", lambda e, c=c: (self._next(c, -1), "break")[1])
        c.bind("<<Modified>>", lambda e, c=c: (c.edit_modified(False), self.ed._mark_changed()))
        return c

    def _add_row_widgets(self, row, at=None):
        cells = [self._cell(t) for t in row]
        if at is None:
            self.cells.append(cells)
        else:
            self.cells.insert(at, cells)

    def _layout(self):
        for w in self.frame.grid_slaves():
            w.grid_forget()
        ncol = max(len(r) for r in self.cells)
        width_px = self.ed.text_width_px()
        for ri, row in enumerate(self.cells):
            while len(row) < ncol:
                row.append(self._cell())
            for ci, c in enumerate(row):
                c.grid(row=ri, column=ci, sticky="nsew", padx=(1, 0 if ci < ncol - 1 else 1),
                       pady=(1, 0 if ri < len(self.cells) - 1 else 1))
                self._fit(c)
        for ci in range(ncol):
            self.frame.grid_columnconfigure(ci, minsize=int(width_px / ncol) - 2, weight=1)
        self.frame.configure(width=width_px)
        for c in [c for r in self.cells for c in r]:
            c.configure(width=max(4, int(width_px / ncol / max(6, self.ed.font_for_body().measure("n"))) - 1))

    def _fit(self, c):
        try:
            ncol = max(1, max(len(r) for r in self.cells))
            avail = max(40, self.ed.text_width_px() / ncol - 16)
            f = self.ed.font_for_body()
            lines = 0
            for ln in c.get("1.0", "end-1c").split("\n"):
                lines += max(1, -(-f.measure(ln) // int(avail)))
            c.configure(height=max(1, min(30, lines)))
        except (tk.TclError, ValueError):
            pass

    def _pos(self, c):
        for ri, row in enumerate(self.cells):
            if c in row:
                return ri, row.index(c)
        return 0, 0

    def _next(self, c, d):
        flat = [x for r in self.cells for x in r]
        i = flat.index(c) + d
        if 0 <= i < len(flat):
            flat[i].focus_set()
        elif d > 0:
            self.add_row(len(self.cells))
            self.cells[-1][0].focus_set()

    def _menu(self, e, c):
        ri, ci = self._pos(c)
        m = T.menu(self.frame)
        m.add_command(label="Insert row above", command=lambda: self.add_row(ri))
        m.add_command(label="Insert row below", command=lambda: self.add_row(ri + 1))
        m.add_command(label="Insert column left", command=lambda: self.add_col(ci))
        m.add_command(label="Insert column right", command=lambda: self.add_col(ci + 1))
        m.add_separator()
        m.add_command(label="Delete row", command=lambda: self.del_row(ri))
        m.add_command(label="Delete column", command=lambda: self.del_col(ci))
        m.add_separator()
        m.add_command(label="Delete table", command=lambda: self.ed.delete_block(self))
        m.tk_popup(e.x_root, e.y_root)
        return "break"

    def add_row(self, at):
        self.ed._push_undo()
        self._add_row_widgets([""] * max(len(r) for r in self.cells), at)
        self._layout()
        self.ed._mark_changed()

    def add_col(self, at):
        self.ed._push_undo()
        for row in self.cells:
            row.insert(at, self._cell())
        self._layout()
        self.ed._mark_changed()

    def del_row(self, ri):
        if len(self.cells) <= 1:
            return self.ed.delete_block(self)
        self.ed._push_undo()
        for c in self.cells.pop(ri):
            c.destroy()
        self._layout()
        self.ed._mark_changed()

    def del_col(self, ci):
        if max(len(r) for r in self.cells) <= 1:
            return self.ed.delete_block(self)
        self.ed._push_undo()
        for row in self.cells:
            if ci < len(row):
                row.pop(ci).destroy()
        self._layout()
        self.ed._mark_changed()

    def rows(self):
        return [[c.get("1.0", "end-1c") for c in row] for row in self.cells]

    def rezoom(self):
        f = self.ed.font_for_body()
        for c in [c for r in self.cells for c in r]:
            c.configure(font=f)
        self._layout()


class PageBreakBlock:
    def __init__(self, ed):
        self.ed = ed
        self.frame = tk.Frame(ed.text, bg=PAPER, height=24)
        self.frame.pack_propagate(False)
        self.lbl = tk.Label(self.frame, text="· · · · ·   page break   · · · · ·", bg=PAPER,
                            fg=T.FAINT, font=T.UI_FONT)
        self.lbl.pack(fill="both", expand=True)
        self.frame.bind("<Button-3>", self._menu)
        self.lbl.bind("<Button-3>", self._menu)
        self.rezoom()

    def _menu(self, e):
        m = T.menu(self.frame)
        m.add_command(label="Remove page break", command=lambda: self.ed.delete_block(self))
        m.tk_popup(e.x_root, e.y_root)

    def rezoom(self):
        self.frame.configure(width=self.ed.text_width_px())


# ====================================================================== the editor
class NoteEditor:
    def __init__(self, parent, app, cfg):
        self.app = app
        self.cfg = cfg
        self.root = parent.winfo_toplevel()
        self.frame = ttk.Frame(parent)
        self.path = None
        self.dirty = False
        self._save_job = None
        self._img_counter = 0
        self.images = {}
        self.blocks = {}
        self.pending = {}
        self.painter = None
        self._fonts = {}
        self._ptags = {}
        self._ftags = {}           # character-format tag -> (size, sup/sub) it was made for
        self._undo, self._redo = [], []
        self._last_type = 0.0
        self._ver = 0              # bumps on every change
        self._snap = None          # (version, items) - the note as it was at the last quiet moment
        self._idle_job = None
        self._loaded_title = None
        self._loading = False
        self._spell_queue = []
        self._spell_job = None
        self._page_job = None
        self._pages_later = False  # pages to count once this note is shown (hidden tabs aren't counted)
        self._gut_job = None
        self._rib_job = None
        self._rib_check_job = None
        self._head_fixed = False
        self._gut = 70             # width of the margins beside the page (slim when pages sit side by side)
        self._desk_w = 1100
        self._fr = None            # the Find & replace window, while open
        self._fr_find = self._fr_entry = None
        self._added_job = self._cut_job = self._fonts_job = None
        self._drop_caret = self._drop_hint = None    # blue line + label while files from Explorer are over the page
        self.font_win = None           # the "Fonts in the pasted text" window (nobu_pastefonts), while open
        self.meta = {}             # colour label, 'titled' flag ... (kept as they are when saving)
        self.page_marks = []
        self.zoom_mode = cfg.get("zoom") or "Fit width"
        self.zoom = 1.0
        self.dpi = float(self.root.winfo_fpixels("1i"))
        self.ctx = R.Ctx(getattr(app, "body_family", "IM FELL English"), getattr(app, "heading_family", "Eagle Lake"),
                         float(cfg["font_size"]))
        self.pictool = None        # moving / resizing pictures with the mouse (nobu_pictool)
        self._styled = set()       # colour / highlight / link tags already set up (and raised, once)
        self._sel_up = False       # "sel" is above every raised tag (raising a tag makes Tk measure the whole note)
        self._margins_up = False   # the page-margin tags have been raised (once is enough)
        self.flow = None           # pictures placed anywhere, with the text flowing round them (nobu_float)
        self._build_ui()

    # ------------------------------------------------------------------ measurements
    def px(self, inches):
        return int(round(inches * self.dpi * self.zoom))

    def pt_px(self, pt):
        return pt * self.dpi / 72.0 * self.zoom

    def text_width_px(self):
        return self.px(6.5)

    def font_for(self, fam, size_pt, bold=False, italic=False):
        key = (fam, round(size_pt * 2) / 2.0, bold, italic)
        f = self._fonts.get(key)
        if f is None:
            f = tkfont.Font(family=fam, size=-max(4, int(round(self.pt_px(size_pt)))),
                            weight="bold" if bold else "normal", slant="italic" if italic else "roman")
            self._fonts[key] = f
        return f

    def font_for_body(self):
        return self.font_for(self.ctx.body, self.ctx.size)

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        f = self.frame
        self.on_header = None          # set by the workspace (pop-out window titles etc.)
        head = self.head = ttk.Frame(f, padding=(16, 8, 16, 4))
        head.pack(side="top", fill="x")
        top = self.head_top = ttk.Frame(head)
        top.pack(side="top", fill="x")
        self.pane_btns = tk.Frame(top, bg=T.BG)    # toolbar / side by side / pop out / close (from the workspace)
        self.pane_btns.pack(side="right")
        # small versions of the buttons, used when the page is narrow (notes side by side)
        sb_ = self.btns_small = tk.Frame(top, bg=T.BG)
        for text, cmd, tip in (("⇧", lambda: self.app.export_dialog([self.path] if self.path else []),
                                "Export / share (Word, PDF, e-book, web page, text)"),
                               ("Move ▾", lambda: self.app.move_menu(self._move_small, [self.path]), "Move to a folder"),
                               ("✎", lambda: self.path and self.app.rename_note(self.path), "Rename this note"),
                               ("⋯", lambda: self._more_menu(self._more_small), "More")):
            b = _btn(sb_, text, cmd, tip=tip, bg=T.BG)
            b.configure(padx=7)
            b.pack(side="left", padx=1)
            if text.startswith("Move"):
                self._move_small = b
            if text == "⋯":
                self._more_small = b
        self.where = ttk.Label(top, text="", style="Muted.TLabel")
        self.where.pack(side="left", anchor="w")
        row = self.head_row = ttk.Frame(head)
        row.pack(side="top", fill="x")
        btns = self.btns_full = ttk.Frame(row)
        btns.pack(side="right")
        self.title = ttk.Label(row, text="", style="NoteTitle.TLabel")
        self.title.pack(side="left", anchor="w", fill="x", expand=True)
        self.export_btn = ttk.Button(btns, text="⇧  Export / share", style="Accent.TButton",
                                     command=lambda: self.app.export_dialog([self.path] if self.path else []))
        self.export_btn.pack(side="left", padx=3)
        self.move_btn = ttk.Button(btns, text="Move to ▾", command=lambda: self.app.move_menu(self.move_btn, [self.path]))
        self.move_btn.pack(side="left", padx=3)
        self.rename_btn = ttk.Button(btns, text="Rename", command=lambda: self.path and self.app.rename_note(self.path))
        self.rename_btn.pack(side="left", padx=3)
        self.more_btn = ttk.Button(btns, text="⋯", width=3, command=self._more_menu)
        self.more_btn.pack(side="left", padx=3)
        _Tip(self.export_btn, "Export / share (Word, PDF, e-book, web page, text)")
        _Tip(self.rename_btn, "Rename this note")
        self._compact = False
        head.bind("<Configure>", lambda e: self._fit_head(e.width))

        self.banner = tk.Label(f, text="  This transcript is unassigned. When you're ready, use “Move to” to "
                               "file it into a book or campaign.", anchor="w", bg=T.BANNER_BG, fg=T.BANNER_FG,
                               font=T.UI_FONT, padx=10, pady=5)
        self.action = tk.Frame(f, bg=T.ACTION_BG, padx=10, pady=6)
        self.action_lbl = tk.Label(self.action, text="", bg=T.ACTION_BG, fg=T.ACTION_FG, font=T.UI_FONT, anchor="w",
                                   justify="left", wraplength=800)
        self.action_lbl.pack(side="left", fill="x", expand=True)
        self.action_btns = tk.Frame(self.action, bg=T.ACTION_BG)
        self.action_btns.pack(side="right")

        self._build_ribbon(f)

        # status bar (bottom): pages, words, zoom
        sb = tk.Frame(f, bg=T.BG)
        sb.pack(side="bottom", fill="x", padx=16, pady=(2, 6))
        self.page_lbl = tk.Label(sb, text="Page 1 of 1", bg=T.BG, fg=T.MUTED, font=T.UI_FONT)
        self.page_lbl.pack(side="left")
        self.page_nav = tk.Frame(sb, bg=T.BG)
        self.page_nav.pack(side="left", padx=10)
        self.zoom_cb = ttk.Combobox(sb, values=ZOOMS, width=9, state="readonly")
        self.zoom_cb.set(self.zoom_mode)
        self.zoom_cb.bind("<<ComboboxSelected>>", lambda e: self.set_zoom(self.zoom_cb.get()))
        self.zoom_cb.pack(side="right")
        tk.Label(sb, text="Zoom", bg=T.BG, fg=T.MUTED, font=T.UI_FONT).pack(side="right", padx=4)
        self.words_lbl = tk.Label(sb, text="", bg=T.BG, fg=T.MUTED, font=T.UI_FONT, cursor="hand2")
        self.words_lbl.pack(side="right", padx=14)
        self.words_lbl.bind("<Button-1>", lambda e: self.word_count_dialog())

        # the desk with the page in the middle
        desk = self.desk = tk.Frame(f, bg=DESK)
        desk.pack(side="top", fill="both", expand=True, padx=16, pady=(4, 0))
        self.vsb = ttk.Scrollbar(desk, orient="vertical")
        self.vsb.pack(side="right", fill="y")
        mid = tk.Frame(desk, bg=DESK)
        mid.pack(side="left", fill="both", expand=True)
        self.gut_l = tk.Canvas(mid, bg=DESK, highlightthickness=0, width=70)
        self.gut_r = tk.Canvas(mid, bg=DESK, highlightthickness=0, width=70)
        self.paper = tk.Frame(mid, bg=PAPER)
        # the gutters share the spare width equally, so the page sits in the middle
        self.gut_l.pack(side="left", fill="both", expand=True)
        self.paper.pack(side="left", fill="y")
        self.gut_r.pack(side="left", fill="both", expand=True)
        self.paper.pack_propagate(False)
        self.text = tk.Text(self.paper, wrap="word", undo=False, bg=PAPER, fg=INK, insertbackground=INK,
                            insertwidth=2, relief="flat", borderwidth=0, highlightthickness=0,
                            selectbackground=T.SELECT, selectforeground=T.SELECT_FG, inactiveselectbackground=T.SELECT,
                            font=self.font_for_body(), tabs=(self.px(0.5),))
        self.text.pack(fill="both", expand=True)
        self._watch_changes()
        self.text.configure(yscrollcommand=self._on_yscroll)
        self.vsb.configure(command=self.text.yview)
        mid.bind("<Configure>", lambda e: self._on_desk_resize(e.width))
        # mouse wheel beside the page zooms; on the page it scrolls
        for w in (desk, mid, self.gut_l, self.gut_r):
            w.bind("<MouseWheel>", self._wheel_zoom)
            w.bind("<Button-4>", lambda e: self._wheel_zoom(e, 1))
            w.bind("<Button-5>", lambda e: self._wheel_zoom(e, -1))
        self.gut_l.bind("<Configure>", lambda e: self._schedule_gutters())
        self._configure_static_tags()
        self._bind_keys()
        self._setup_dnd()
        self._apply_zoom_geometry()

    def _fit_head(self, width):
        """Narrow page (several notes side by side): small buttons so nothing is cut off. Both header rows
        keep a fixed height either way, so pages side by side line up exactly."""
        if not self._head_fixed:
            self._head_fixed = True
            h1 = max(self.btns_small.winfo_reqheight(), self.where.winfo_reqheight(), self.pane_btns.winfo_reqheight())
            h2 = max(self.btns_full.winfo_reqheight(), self.title.winfo_reqheight())
            self.head_top.configure(height=h1)
            self.head_top.pack_propagate(False)
            self.head_row.configure(height=h2)
            self.head_row.pack_propagate(False)
        need = self.title.winfo_reqwidth() + self.btns_full.winfo_reqwidth() + 40    # title + big buttons side by side
        compact = width < max(int(640 * T.ui_scale(self.root)), need)
        if compact == self._compact:
            return
        self._compact = compact
        if compact:
            self.btns_full.pack_forget()
            self.btns_small.pack(side="right", padx=(0, 10), before=self.where)
        else:
            self.btns_small.pack_forget()
            self.btns_full.pack(side="right", before=self.title)
        if self.path:
            self._update_header(refit=False)

    def show_ribbon(self, show):
        """Show or hide the formatting toolbar."""
        if show and not self.ribbon.winfo_manager():       # (never re-pack one that's already in place)
            self.ribbon.pack(side="top", fill="x", padx=16, pady=(4, 0))
        elif not show and self.ribbon.winfo_manager():
            self.ribbon.pack_forget()

    def _check_rib_box(self):
        """Tk sometimes leaves the toolbar's holder collapsed after a re-layout (the page then sits higher
        than its neighbour's). Re-attaching the toolbar fixes it."""
        self._rib_check_job = None
        try:
            if self.ribbon.winfo_manager() and \
                    self.rib_box.winfo_reqheight() < self.ribbon.winfo_reqheight():
                self.ribbon.pack_forget()
                self.ribbon.pack(side="top", fill="x", padx=16, pady=(4, 0))
        except tk.TclError:
            pass

    def _check_rib_soon(self):
        if not self._rib_check_job:
            self._rib_check_job = T.later(self.frame, 30, self._check_rib_box)

    def set_compact_ribbon(self, on):
        """Compact toolbar (pages side by side): two rows - style, font & size / bold, italic, underline -
        and everything else in "More tools"."""
        self.show_ribbon(True)
        if bool(on) != self._rib_compact:
            self._rib_compact = bool(on)
            self._flow_ribbon(max(1, self.ribbon.winfo_width()))
            if self.path:
                self._update_header()

    def ribbon_compact(self):
        return self._rib_compact

    def _build_ribbon(self, f):
        self.rib_box = tk.Frame(f, bg=T.BG)
        self.rib_box.pack(side="top", fill="x")
        rib = tk.Frame(self.rib_box, bg=T.PANEL, height=80)
        rib.pack(side="top", fill="x", padx=16, pady=(4, 0))
        rib.pack_propagate(False)
        self.ribbon = rib
        self._groups = []

        def group():
            g = tk.Frame(rib, bg=T.PANEL, padx=5, pady=3)
            self._groups.append(g)
            return g
        r1 = group()

        # row 1: style, font, size, character formatting
        self.style_cb = ttk.Combobox(r1, values=[R.STYLES[s]["label"] for s in R.STYLE_ORDER], width=10,
                                     state="readonly")
        self.style_cb.set("Normal")
        self.style_cb.bind("<<ComboboxSelected>>", lambda e: self.set_style(
            R.STYLE_ORDER[[R.STYLES[s]["label"] for s in R.STYLE_ORDER].index(self.style_cb.get())]))
        self.style_cb.pack(side="left", padx=2)
        self.font_cb = ttk.Combobox(r1, width=17)
        self.font_cb.bind("<<ComboboxSelected>>", lambda e: self.set_char("ff", self.font_cb.get()))
        self.font_cb.bind("<Return>", lambda e: self.set_char("ff", self.font_cb.get()))
        self.font_cb.pack(side="left", padx=2)
        self._fonts_job = T.later(self.frame, 200, self._fill_fonts)
        _btn(r1, "Fonts…", self.app.open_font_browser, tip="Browse all fonts with previews").pack(side="left")
        self.size_cb = ttk.Combobox(r1, values=SIZES_PT, width=5)
        self.size_cb.bind("<<ComboboxSelected>>", lambda e: self._size_from_box())
        self.size_cb.bind("<Return>", lambda e: self._size_from_box())
        self.size_cb.pack(side="left", padx=2)
        _btn(r1, "A⁺", lambda: self.grow_font(1), tip="Grow font").pack(side="left")
        _btn(r1, "A⁻", lambda: self.grow_font(-1), tip="Shrink font").pack(side="left")
        r1 = group()
        self.fbtn = {}
        for key, label, fnt, tip in (("b", "B", (T.UI_FAMILY, T.UI_SIZE + 1, "bold"), "Bold (Ctrl+B)"),
                                     ("i", "I", (T.UI_FAMILY, T.UI_SIZE + 1, "italic"), "Italic (Ctrl+I)"),
                                     ("u", "U", (T.UI_FAMILY, T.UI_SIZE + 1, "underline"), "Underline (Ctrl+U)"),
                                     ("s", "S", (T.UI_FAMILY, T.UI_SIZE + 1, "overstrike"), "Strikethrough"),
                                     ("sup", "x²", None, "Superscript (Ctrl+Shift+=)"),
                                     ("sub", "x₂", None, "Subscript (Ctrl+=)")):
            b = _btn(r1, label, lambda k=key: self.toggle_flag(k), font=fnt, width=2, tip=tip)
            b.pack(side="left", padx=1)
            self.fbtn[key] = b
        r1 = group()
        self.color_btn = _btn(r1, "A ▾", self._color_menu, tip="Text colour")
        self.color_btn.configure(fg="#ff6b6b", font=(T.UI_FAMILY, T.UI_SIZE + 1, "bold"))
        self.color_btn.pack(side="left")
        self.hl_btn = _btn(r1, "✎ ▾", self._hl_menu, tip="Highlight colour")
        self.hl_btn.configure(fg="#ffff66")
        self.hl_btn.pack(side="left")
        _btn(r1, "Aa ▾", self._case_menu, tip="Change case").pack(side="left")
        _btn(r1, "✘ Clear", self.clear_formatting, tip="Clear all formatting").pack(side="left")
        self.painter_btn = _btn(r1, "✒ Painter", self.start_painter,
                                tip="Format painter: copy formatting, then select text to apply it")
        self.painter_btn.pack(side="left")
        r1 = group()
        _btn(r1, "⌕ Find & replace", self.find_replace_dialog, tip="Find & replace (Ctrl+F / Ctrl+H)").pack(side="left")
        _btn(r1, "✓ Spelling", self.spell_next, tip="Go to the next spelling mistake (F7)").pack(side="left")
        _btn(r1, "≡ Thesaurus", self.thesaurus_at_cursor, tip="Synonyms for the word at the cursor (Shift+F7)").pack(side="left")

        # paragraph, insert, voice
        r2 = group()
        for al, sym, tip in (("left", "≡←", "Align left (Ctrl+L)"), ("center", "≡↔", "Centre (Ctrl+E)"),
                             ("right", "→≡", "Align right (Ctrl+R)"), ("justify", "≣", "Justify (Ctrl+J)")):
            _btn(r2, sym, lambda a=al: self.set_par("al", a), tip=tip, width=3).pack(side="left", padx=1)
        _btn(r2, "↕ Spacing ▾", self._spacing_menu, tip="Line & paragraph spacing").pack(side="left")
        _btn(r2, "⇤", lambda: self.indent(-0.5), tip="Decrease indent").pack(side="left")
        _btn(r2, "⇥", lambda: self.indent(0.5), tip="Increase indent").pack(side="left")
        _btn(r2, "• List", lambda: self.toggle_list("bullet"), tip="Bullets").pack(side="left")
        _btn(r2, "1. List", lambda: self.toggle_list("num"), tip="Numbering").pack(side="left")
        r2 = group()
        _btn(r2, "▦ Table", self.insert_table_dialog, tip="Insert a table").pack(side="left")
        _btn(r2, "▣ Picture", self.insert_image_dialog, tip="Insert a picture (or paste / drag one in)").pack(side="left")
        _btn(r2, "⤓ Page break", self.insert_page_break, tip="Start a new page (Ctrl+Enter)").pack(side="left")
        _btn(r2, "Ω Symbol ▾", self._symbol_menu, tip="Insert a symbol").pack(side="left")
        _btn(r2, "⧖ Date", self.insert_date, tip="Insert today's date").pack(side="left")
        r2 = group()
        vf = (T.UI_FAMILY, max(8, T.UI_SIZE - 2))
        self._voice_hints = {}
        for key, label, voice, cmd in (("edit", "● Dictate here", VOICE_EDIT, lambda: self.app.start_in_note("edit", self)),
                                       ("cut", "✂ Cut by voice", VOICE_CUT, lambda: self.app.start_in_note("cut", self))):
            box = tk.Frame(r2, bg=T.PANEL)
            box.pack(side="left", padx=2)
            b = _btn(box, label, cmd)
            b.pack()
            lbl = tk.Label(box, text="(%s)" % voice, bg=T.PANEL, fg=T.MUTED, font=vf)
            lbl.pack()
            self._voice_hints[key] = (lbl, voice)
        # "More tools" (only shown on the compact toolbar of side-by-side pages)
        self._rib_compact = False
        gm = self._g_more = tk.Frame(rib, bg=T.PANEL, padx=5, pady=3)
        self._more_btn2 = _btn(gm, "\u25be More tools", lambda: self._more_tools(self._more_btn2),
                               tip="Colours, alignment, lists, find, spelling, insert, dictation\u2026")
        self._more_btn2.pack(side="left")
        self.update_shortcut_hints()
        rib.bind("<Configure>", lambda e: self._flow_ribbon(e.width))

    def update_shortcut_hints(self):
        """Show the voice phrase and the keyboard shortcut under the Dictate / Cut buttons."""
        for key, (lbl, voice) in self._voice_hints.items():
            sc = self.cfg.get("hotkey_" + key) or ""
            lbl.configure(text="(%s%s)" % (voice, ("  \u00b7  " + sc) if sc else ""))
        if self.ribbon.winfo_width() > 1:
            self._flow_ribbon(self.ribbon.winfo_width())

    def _flow_ribbon(self, width):
        """Lay the tool groups out left to right, wrapping onto more rows when the window is narrow."""
        if self._rib_compact:
            keep = (self._groups[0], self._groups[1], self._g_more)
            for g in self._groups:
                if g not in keep:
                    g.place_forget()
            g0, g1, gm = keep
            g0.place(x=0, y=0)
            h0 = g0.winfo_reqheight()
            g1.place(x=0, y=h0 + 1)
            gm.place(x=g1.winfo_reqwidth() + 1, y=h0 + 1)
            need = h0 + 1 + max(g1.winfo_reqheight(), gm.winfo_reqheight())
            if abs(int(self.ribbon.cget("height")) - need) > 1:
                self.ribbon.configure(height=need)
            self._check_rib_soon()
            return
        self._g_more.place_forget()
        x, y, row_h = 0, 0, 0
        for g in self._groups:
            w, h = g.winfo_reqwidth(), g.winfo_reqheight()
            if x and x + w > width:
                x, y = 0, y + row_h + 1
                row_h = 0
            g.place(x=x, y=y)
            x += w + 1
            row_h = max(row_h, h)
        need = y + row_h
        if abs(int(self.ribbon.cget("height")) - need) > 1:
            self.ribbon.configure(height=need)
        self._check_rib_soon()

    def _fill_fonts(self):
        self._fonts_job = None
        try:
            if not self.font_cb.winfo_exists():
                return
            import nobu_fonts
            cats = nobu_fonts.by_category(self.root)
            fams = []
            for c, _ in nobu_fonts.CATEGORIES:
                fams += cats.get(c, [])
            self.font_cb.configure(values=fams)
        except Exception:
            log.exception("font list failed")

    def _more_menu(self, widget=None):
        widget = widget or self.more_btn
        m = T.menu(self.root)
        m.add_command(label="Word count…", command=self.word_count_dialog)
        m.add_command(label="Show file in folder", command=lambda: self.path and open_path(os.path.dirname(self.path)))
        m.add_separator()
        m.add_command(label="Delete note (to Trash)", command=lambda: self.path and self.app.delete_note(self.path))
        m.tk_popup(widget.winfo_rootx(), widget.winfo_rooty() + widget.winfo_height())

    def _configure_static_tags(self):
        t = self.text
        t.tag_configure("u", underline=True)
        t.tag_configure("s", overstrike=True)
        t.tag_configure("meta", foreground=T.MUTED)
        t.tag_configure("found", background="#6b5a1e", foreground="white")
        t.tag_configure("cutmatch", background="#7a2a2a", foreground="white", overstrike=True)
        t.tag_configure("dictspot", background="#24405f")
        t.tag_configure("justadded", background="#1f3d2c")
        t.tag_configure("sp_err", underline=True, underlinefg="#ff5c5c")
        t.tag_configure("lm", foreground=INK)

    def _bind_keys(self):
        t = self.text
        t.bind("<<Modified>>", self._on_modified)
        t.bind("<Key>", self._on_key)
        t.bind("<Return>", self._on_return)
        t.bind("<Control-Return>", lambda e: (self.insert_page_break(), "break")[1])
        t.bind("<Tab>", self._on_tab)
        t.bind("<Shift-Tab>", lambda e: (self.list_level(-1), "break")[1])
        t.bind("<BackSpace>", self._on_backspace)
        t.bind("<Delete>", self._on_delete)
        for seq, fn in (("<Control-v>", self.paste), ("<Control-V>", self.paste), ("<Shift-Insert>", self.paste),
                        ("<Control-c>", self.copy), ("<Control-C>", self.copy), ("<Control-Insert>", self.copy),
                        ("<Control-x>", self.cut), ("<Control-X>", self.cut), ("<Shift-Delete>", self.cut)):
            t.bind(seq, lambda e, fn=fn: (fn(), "break")[1])
        for seq, fn in (("<Control-b>", lambda: self.toggle_flag("b")), ("<Control-i>", lambda: self.toggle_flag("i")),
                        ("<Control-u>", lambda: self.toggle_flag("u")), ("<Control-equal>", lambda: self.toggle_flag("sub")),
                        ("<Control-plus>", lambda: self.toggle_flag("sup")), ("<Control-s>", self.save),
                        ("<Control-f>", self.find_replace_dialog), ("<Control-h>", self.find_replace_dialog),
                        ("<Control-z>", self.undo), ("<Control-y>", self.redo), ("<Control-Z>", self.redo),
                        ("<Control-l>", lambda: self.set_par("al", "left")), ("<Control-e>", lambda: self.set_par("al", "center")),
                        ("<Control-r>", lambda: self.set_par("al", "right")), ("<Control-j>", lambda: self.set_par("al", "justify")),
                        ("<Control-a>", lambda: self.text.tag_add("sel", "1.0", "end-1c")),
                        ("<Control-space>", self.clear_formatting), ("<F7>", self.spell_next),
                        ("<Shift-F7>", self.thesaurus_at_cursor), ("<Control-bracketright>", lambda: self.grow_font(1)),
                        ("<Control-bracketleft>", lambda: self.grow_font(-1))):
            t.bind(seq, lambda e, fn=fn: (fn(), "break")[1])
        t.bind("<ButtonRelease-1>", self._on_click_release, add="+")
        t.bind("<KeyRelease>", lambda e: self._sync_ribbon_soon(), add="+")
        t.bind("<Button-3>", self._on_right_click)
        t.bind("<Double-Button-1>", self._on_double_click)
        t.bind("<MouseWheel>", lambda e: T.later(self.frame, None, self._draw_gutters), add="+")
        t.bind("<Control-MouseWheel>", self._wheel_zoom)
        self.pictool = nobu_pictool.PictureTool(self)
        self.flow = nobu_float.FloatLayer(self)
        for seq in ("<Configure>", "<Map>"):          # (shown again: count the pages it skipped while hidden)
            t.bind(seq, lambda e: self._schedule_pages() if self._pages_later and t.winfo_width() >= self.px(2.0)
                   else None, add="+")
        for seq, d in (("<Left>", (-1, 0)), ("<Right>", (1, 0)), ("<Up>", (0, -1)), ("<Down>", (0, 1))):
            t.bind(seq, lambda e, d=d: self._nudge_picture(e, *d))

    def _watch_changes(self):
        """Count every change to the page's text (typing, Tk's own key handling, pictures, tables...).
        The cached copy of the note is reused only while this count hasn't moved, so nothing can be missed.
        Done in Tcl, so errors and speed are exactly as before."""
        self._vervar = "nobu_ver" + str(self.text).replace(".", "_").replace("!", "")
        self.text.tk.call("set", "::" + self._vervar, 0)
        self._watch_widget(self.text)

    def _watch_widget(self, t):
        """Route a Text widget's commands through a tiny Tcl proc that counts edits."""
        w = str(t)
        orig = w + "_nobu"
        t.tk.call("rename", w, orig)
        t.tk.eval("""
            proc %(w)s {args} {
                set c [lindex $args 0]
                if {$c eq "insert" || $c eq "delete" || $c eq "replace" ||
                    (($c eq "image" || $c eq "window") && [lindex $args 1] eq "create")} {
                    incr ::%(v)s
                }
                uplevel 1 [linsert $args 0 %(o)s]
            }""" % {"v": self._vervar, "w": w, "o": orig})
        t.bind("<Destroy>", lambda e, w=w: t.tk.call("rename", w, "") if e.widget is t else None, add="+")

    def _version(self):
        try:
            return self._ver + int(self.text.tk.getvar(self._vervar))
        except (tk.TclError, AttributeError, ValueError):
            return self._ver

    # ------------------------------------------------------------------ zoom & page geometry
    def _wheel_zoom(self, ev, direction=None):
        d = direction if direction is not None else (1 if ev.delta > 0 else -1)
        cur = int(round(self.zoom * 100 / 10.0)) * 10
        new = max(30, min(300, cur + 10 * d))
        if new != int(round(self.zoom * 100)):
            self.set_zoom("%d%%" % new)
        return "break"

    def _on_desk_resize(self, width):
        self._desk_w = width
        # narrow (notes side by side): slim margins beside the page, so the page itself gets the room
        gut = 70 if width >= int(760 * T.ui_scale(self.root)) else 10
        if gut != self._gut:
            self._gut = gut
            self.gut_l.configure(width=gut)
            self.gut_r.configure(width=gut)
        if self.zoom_mode == "Fit width":
            z = max(0.3, min(1.0, (width - 2 * gut - 10) / (8.5 * self.dpi)))
            if abs(z - self.zoom) > 0.01:
                self.zoom = z
                self._rezoom()

    def set_zoom(self, mode):
        self.zoom_mode = mode
        self.zoom_cb.set(mode)
        self.cfg.set_temp(zoom=mode)
        if mode == "Fit width":
            self._on_desk_resize(self._desk_w)
            return
        self.zoom = int(mode.rstrip("%")) / 100.0
        self._rezoom()

    def _apply_zoom_geometry(self):
        self.paper.configure(width=self.px(8.5))
        self.text.configure(padx=self.px(1.0), pady=self.px(0.12), tabs=(self.px(0.5),))
        self.text.tag_configure("docstart", spacing1=self.px(0.88))
        self.text.tag_configure("docend", spacing3=self.px(0.88))
        self.gut_l.configure(width=self._gut)
        self.gut_r.configure(width=self._gut)
        self._schedule_gutters()

    def _rezoom(self):
        top = self.text.yview()[0]
        self._apply_zoom_geometry()
        for (_fam, size, _b, _i), f in self._fonts.items():
            f.configure(size=-max(4, int(round(self.pt_px(size)))))
        for name, key in list(self._ptags.items()):
            self.text.tag_configure(name, **self._par_options(key))
        for name, (size, vpos) in self._ftags.items():
            if vpos:                      # raised / lowered text moves with the zoom too
                self.text.tag_configure(name, offset=self._vpos_offset(size, vpos))
        self.text.configure(font=self.font_for_body())
        for name, info in list(self.images.items()):
            try:
                photo, _w, _h = self._make_photo(info["rel"], info["w"], info.get("h"))
                self._show_photo(name, photo)
            except Exception:
                pass
        for b in self.blocks.values():
            b.rezoom()
        self.text.yview_moveto(top)
        self._schedule_pages()
        if self.flow:
            self.flow.schedule()

    # ------------------------------------------------------------------ composite formatting tags
    def _ftag(self, fam, size, bold, italic, vpos):
        key = "F|%s|%s|%d|%d|%s" % (fam, size, bold, italic, vpos)
        if key not in self._ftags:
            self._ftags[key] = (size, vpos)
            f = self.font_for(fam, size * (0.65 if vpos else 1.0), bold, italic)
            self.text.tag_configure(key, font=f, offset=self._vpos_offset(size, vpos))
            self.text.tag_lower(key)
        return key

    def _vpos_offset(self, size, vpos):
        off = int(self.pt_px(size) * 0.33) if vpos else 0
        return off if vpos == "sup" else -off

    def _par_options(self, key):
        style, al, ls, sb, sa, ind, fi, li = key
        s = R.STYLES.get(style, R.STYLES["normal"])
        size = self.ctx.size * s["size"]
        line = self.pt_px(size) * 1.18
        ls = ls if ls is not None else s.get("ls", 1.08)
        sb = sb if sb is not None else s.get("sb", 0)
        sa = sa if sa is not None else s.get("sa", 8)
        ind = (ind or 0) + s.get("ind", 0)
        fi = fi or 0
        lm1 = ind + max(fi, -ind)
        lm2 = ind
        tabs = (self.px(0.5),)
        if li:
            lvl = li[1]
            lm1 = ind + 0.25 * lvl
            lm2 = lm1 + 0.3
            tabs = (self.px(lm2),)
        extra = max(0, (ls - 1.0)) * line
        return dict(spacing1=int(self.pt_px(sb) + extra / 2), spacing2=int(extra), spacing3=int(self.pt_px(sa) + extra / 2),
                    lmargin1=self.px(lm1), lmargin2=self.px(lm2), rmargin=0,
                    justify={"justify": "left"}.get(al, al), tabs=tabs)

    def _ptag(self, names):
        p = R._par_from_tags(names)
        key = (p["style"], p["align"], p["ls"], p["sb"], p["sa"], p["ind"], p["fi"], p["list"])
        name = "P|" + "|".join(str(x) for x in key)
        if name not in self._ptags:
            self._ptags[name] = key
            self.text.tag_configure(name, **self._par_options(key))
            self.text.tag_lower(name)
        return name

    def _restyle(self, a="1.0", b="end"):
        t = self.text
        a = t.index("%s linestart" % a)
        b = t.index("%s lineend +1c" % b)
        for tg in t.tag_names():
            if tg.startswith(("F|", "P|")):
                t.tag_remove(tg, a, b)
        # paragraphs
        line = a
        guard = 0
        while t.compare(line, "<", b) and guard < 200000:
            guard += 1
            le = t.index("%s lineend +1c" % line)
            t.tag_add(self._ptag(t.tag_names(line)), line, le)
            if le == line:
                break
            line = le
        # character runs
        bounds = {a, b}
        for _key, val, idx in t.dump(a, b, tag=True):
            if R.is_char_tag(val) or val.startswith("st:"):
                bounds.add(t.index(idx))
        pts = sorted(bounds, key=lambda i: tuple(int(x) for x in i.split(".")))
        for s, e in zip(pts, pts[1:]):
            names = t.tag_names(s)
            run = R._run_from_tags("", names)
            style = R.tag_value(names, "st", "normal")
            fam, size, bold, italic = self.ctx.run_font(style, run)
            vpos = "sup" if run.get("sup") else "sub" if run.get("sub") else ""
            t.tag_add(self._ftag(fam, size, bold, italic, vpos), s, e)
        self._margins()
        for tg in t.tag_names():
            if tg.startswith(("fg:", "hl:")) and tg not in self._styled:
                self._color_tag(tg)
        if not self._sel_up:         # (raising a tag makes Tk measure every line again: only when needed)
            t.tag_raise("sel")
            self._sel_up = True

    def _margins(self):
        """Top and bottom page margins live on the first/last line (the Text's own padding would stay on screen)."""
        t = self.text
        t.tag_remove("docstart", "1.0", "end")
        t.tag_remove("docend", "1.0", "end")
        t.tag_add("docstart", "1.0", "1.0 lineend +1c")
        t.tag_add("docend", "end -1c linestart", "end")
        if not self._margins_up:      # (paragraph tags are made at the bottom, so once keeps these above them)
            t.tag_raise("docstart")
            t.tag_raise("docend")
            self._margins_up = True

    def _color_tag(self, tg):
        t = self.text
        col = tg[3:]
        if tg.startswith("fg:"):
            if T.LIGHT:   # keep text readable on the page: very pale colours are darkened on light themes
                shown = col if R.luminance(col) <= 0.8 else "#6b6b6b"
            else:         # ... and very dark ones lightened on dark themes (exports keep the real colour)
                shown = col if R.luminance(col) >= 0.35 else "#d6d6da"
            t.tag_configure(tg, foreground=shown)
        else:
            t.tag_configure(tg, background=col, foreground="#111111" if R.luminance(col) > 0.45 else "#ffffff")
            if tg not in self._styled:
                t.tag_raise(tg)
                self._sel_up = False
        self._styled.add(tg)

    # ------------------------------------------------------------------ selection helpers
    def _sel(self):
        try:
            return self.text.index("sel.first"), self.text.index("sel.last")
        except tk.TclError:
            return None

    def _sel_lines(self):
        t = self.text
        s = self._sel()
        a, b = (s if s else (t.index("insert"), t.index("insert")))
        b = t.index("%s lineend" % b)
        while "softnl" in t.tag_names(b):              # (a paragraph flowing round a picture goes on)
            b = t.index("%s +1c lineend" % b)
        return self._par_start(a), t.index("%s +1c" % b)

    def _par_start(self, idx):
        """Where the paragraph holding idx starts (a paragraph beside a floating picture is split into
        several lines by invisible breaks)."""
        return self.flow.par_start(idx) if self.flow else self.text.index("%s linestart" % idx)

    def _is_cont(self, line):
        """Is this line the rest of a paragraph (after an invisible break), not a paragraph of its own?"""
        t = self.text
        return t.compare(line, ">", "1.0") and "softnl" in t.tag_names("%s -1c" % line)

    def _remove_key(self, key, a, b, flag=False):
        t = self.text
        for tg in t.tag_names():
            if (flag and tg == key) or (not flag and tg.startswith(key + ":")):
                t.tag_remove(tg, a, b)

    # ------------------------------------------------------------------ character formatting
    def toggle_flag(self, flag):
        s = self._sel()
        if not s:
            cur = self.pending.get(flag)
            if cur is None:
                cur = flag in self.text.tag_names("insert-1c")
            self.pending[flag] = not cur
            if flag in ("sup", "sub") and self.pending[flag]:
                self.pending["sub" if flag == "sup" else "sup"] = False
            self._sync_ribbon()
            return
        self._push_undo()
        a, b = s
        on = flag not in self.text.tag_names(a)
        self._remove_key(flag, a, b, flag=True)
        if on:
            if flag in ("sup", "sub"):
                self._remove_key("sub" if flag == "sup" else "sup", a, b, flag=True)
            self.text.tag_add(flag, a, b)
        self._after_format(a, b)

    def set_char(self, key, value):
        """Font family (ff), size (fs), colour (fg), highlight (hl). value None removes."""
        if key == "ff" and value:
            value = value.strip()
        s = self._sel()
        if not s:
            self.pending[key] = value
            self.text.focus_set()
            return
        self._push_undo()
        a, b = s
        self._remove_key(key, a, b)
        if value not in (None, ""):
            v = value
            if key == "fs":
                v = ("%.1f" % float(value)).rstrip("0").rstrip(".")
            tg = "%s:%s" % (key, v)
            self.text.tag_add(tg, a, b)
            if key in ("fg", "hl"):
                self._color_tag(tg)
        self._after_format(a, b)
        self.text.focus_set()

    def _size_from_box(self):
        try:
            v = float(self.size_cb.get().strip())
        except ValueError:
            return
        self.set_char("fs", max(4.0, min(400.0, v)))

    def grow_font(self, d):
        cur = self._current_size()
        steps = [float(x) for x in SIZES_PT]
        if d > 0:
            nxt = next((x for x in steps if x > cur), cur + 4)
        else:
            nxt = next((x for x in reversed(steps) if x < cur), max(4.0, cur - 2))
        self.set_char("fs", nxt)

    def _current_size(self):
        names = self.text.tag_names("insert-1c" if not self._sel() else "sel.first")
        run = R._run_from_tags("", names)
        return self.ctx.run_font(R.tag_value(names, "st", "normal"), run)[1]

    def clear_formatting(self):
        s = self._sel()
        a, b = s if s else self._sel_lines()
        self._push_undo()
        t = self.text
        for tg in t.tag_names():
            if (R.is_char_tag(tg) and tg not in ("lm",) and not tg.startswith((R.AUDIO, "link:")) and tg != "meta"):
                t.tag_remove(tg, a, b)
        la, lb = t.index("%s linestart" % a), t.index("%s lineend +1c" % b)
        for tg in t.tag_names():
            if R.is_par_tag(tg) and not tg.startswith("li:"):
                t.tag_remove(tg, la, lb)
        self.pending.clear()
        self._after_format(la, lb)

    def change_case(self, mode):
        s = self._sel()
        if not s:                         # nothing selected: the word at the cursor
            t = self.text
            word, wa, wb = self._word_at("insert" if t.compare("insert", "==", "insert wordstart") else "insert -1c")
            if not word:
                self.app.set_status("Select the words to change first.")
                return
            t.tag_add("sel", wa, wb)
            s = (wa, wb)
        self._push_undo()
        t = self.text
        a, b = s
        segs = [(val, ix) for key, val, ix in t.dump(a, b, text=True)]
        whole = "".join(v for v, _ in segs)
        if mode == "sentence":
            new = re.sub(r"(^|[.!?]\s+)([a-z])", lambda m: m.group(1) + m.group(2).upper(), whole.lower())
        elif mode == "lower":
            new = whole.lower()
        elif mode == "upper":
            new = whole.upper()
        elif mode == "title":
            new = re.sub(r"\b([a-z])", lambda m: m.group(1).upper(), whole.lower())
        else:
            new = whole.swapcase()
        if len(new) != len(whole):
            return
        pos = 0
        for val, ix in segs:
            rep = new[pos:pos + len(val)]
            pos += len(val)
            if rep != val:
                tags = t.tag_names(ix)
                end = t.index("%s+%dc" % (ix, len(val)))
                t.delete(ix, end)
                t.insert(ix, rep, tags)
        t.tag_add("sel", a, b)
        self._after_format(a, b)

    def start_painter(self):
        s = self._sel()
        idx = s[0] if s else "insert-1c"
        names = self.text.tag_names(idx)
        self.painter = ([n for n in names if R.is_char_tag(n) and n not in ("lm", "meta") and not n.startswith(R.AUDIO)],
                        [n for n in names if R.is_par_tag(n) and not n.startswith("li:")])
        self.painter_btn.configure(bg=T.ACCENT_DARK)
        self.app.set_status("Format painter: select the text you want to format.")

    def _on_click_release(self, e=None):
        self._clear_pending()
        if self.painter and self._sel():
            a, b = self._sel()
            self._push_undo()
            ch, par = self.painter
            t = self.text
            for tg in t.tag_names():
                if R.is_char_tag(tg) and tg not in ("lm", "meta") and not tg.startswith(R.AUDIO):
                    t.tag_remove(tg, a, b)
            for tg in ch:
                t.tag_add(tg, a, b)
            la, lb = t.index("%s linestart" % a), t.index("%s lineend +1c" % b)
            if par:
                for tg in t.tag_names():
                    if R.is_par_tag(tg) and not tg.startswith("li:"):
                        t.tag_remove(tg, la, lb)
                for tg in par:
                    t.tag_add(tg, la, lb)
            self.painter = None
            self.painter_btn.configure(bg=T.PANEL)
            self._after_format(la, lb)
        self._sync_ribbon_soon()

    # ------------------------------------------------------------------ paragraph formatting
    def set_par(self, key, value):
        self._push_undo()
        a, b = self._sel_lines()
        self._remove_key(key, a, b)
        if key == "al":    # only store alignment that differs from the style's own (Title is centred)
            style = R.tag_value(self.text.tag_names(a), "st", "normal")
            if value == R.STYLES.get(style, R.STYLES["normal"]).get("align", "left"):
                value = None
        if key == "st":    # a new style brings its own alignment
            self._remove_key("al", a, b)
        if value not in (None, "") and not (key == "st" and value == "normal"):
            v = value if isinstance(value, str) else ("%.2f" % value).rstrip("0").rstrip(".")
            self.text.tag_add("%s:%s" % (key, v), a, b)
        self._after_format(a, b)
        self.text.focus_set()

    def set_style(self, style):
        self.set_par("st", style)

    def indent(self, d):
        a, _b = self._sel_lines()
        cur = R.fnum(R.tag_value(self.text.tag_names(a), "ind"), 0.0)
        if R.tag_value(self.text.tag_names(a), "li"):
            return self.list_level(1 if d > 0 else -1)
        self.set_par("ind", max(0.0, cur + d) or None)

    def set_spacing(self, ls=None, sb=None, sa=None):
        if ls is not None:
            self.set_par("ls", ls)
        if sb is not None:
            self.set_par("sb", sb)
        if sa is not None:
            self.set_par("sa", sa)

    # ------------------------------------------------------------------ lists
    def _line_iter(self, a, b):
        """The start of each paragraph from a to b."""
        t = self.text
        line = self._par_start(a)
        while t.compare(line, "<", b):
            if not self._is_cont(line):
                yield line
            nxt = t.index("%s +1 line linestart" % line)
            if nxt == line or t.compare(nxt, ">=", "end"):
                break
            line = nxt

    def _marker_end(self, line):
        t = self.text
        r = t.tag_nextrange("lm", line, "%s lineend" % line)
        if r and t.compare(r[0], "==", line):
            return r[1]
        return None

    def toggle_list(self, kind):
        self._push_undo()
        t = self.text
        a, b = self._sel_lines()
        first = R.tag_value(t.tag_names(a), "li")
        remove = first is not None and first.startswith(kind)
        for line in list(self._line_iter(a, b)):
            me = self._marker_end(line)
            if me:
                t.delete(line, me)
            le = t.index("%s lineend +1c" % line)
            self._remove_key("li", line, le)
            if not remove:
                tg = "li:%s:0" % kind
                t.tag_add(tg, line, le)
                par = [n for n in t.tag_names(line) if R.is_par_tag(n)] or [tg]
                t.insert(line, "•\t", tuple(set(par + ["lm", tg])))
        self._renumber()
        self._after_format(a, t.index("%s lineend" % b))

    def list_level(self, d):
        t = self.text
        a, b = self._sel_lines()
        changed = False
        for line in list(self._line_iter(a, b)):
            li = R.tag_value(t.tag_names(line), "li")
            if not li:
                continue
            if not changed:
                self._push_undo()
                changed = True
            kind, _, lvl = li.partition(":")
            nl = max(0, min(5, int(lvl) + d))
            le = t.index("%s lineend +1c" % line)
            self._remove_key("li", line, le)
            t.tag_add("li:%s:%d" % (kind, nl), line, le)
        if changed:
            self._renumber()
            self._after_format(a, b)
        return changed

    def _renumber(self):
        t = self.text
        counters = {}
        line = "1.0"
        while True:
            li = R.tag_value(t.tag_names(line), "li") if not self._is_cont(line) else None
            if li is None and self._is_cont(line):
                pass                                   # (the rest of a list item beside a picture)
            elif li:
                kind, _, lvl = li.partition(":")
                lvl = int(lvl)
                for k in [k for k in counters if k > lvl]:
                    del counters[k]
                if kind == "num":
                    counters[lvl] = counters.get(lvl, 0) + 1
                    want = "%d.\t" % counters[lvl] if lvl % 2 == 0 else "%s.\t" % chr(96 + min(26, counters[lvl]))
                else:
                    counters.pop(lvl, None)
                    want = BULLETS[lvl % 3] + "\t"
                me = self._marker_end(line)
                have = t.get(line, me) if me else None
                if have != want:
                    par = [n for n in t.tag_names(line) if R.is_par_tag(n)]
                    if me:
                        t.delete(line, me)
                    t.insert(line, want, tuple(set(par + ["lm"])))
            else:
                counters.clear()
            nxt = t.index("%s +1 line linestart" % line)
            if nxt == line or t.compare(nxt, ">=", "end"):
                break
            line = nxt

    # ------------------------------------------------------------------ typing
    def _clear_pending(self):
        if self.pending:
            self.pending.clear()
            self._sync_ribbon()

    def _typing_tags(self, idx="insert"):
        t = self.text
        par = [n for n in t.tag_names("%s linestart" % idx) if R.is_par_tag(n)]
        if t.compare(idx, ">", "%s linestart" % idx):
            src = t.tag_names("%s -1c" % idx)
            if "lm" in src:
                src = t.tag_names(idx)
        else:
            src = t.tag_names(idx)
        nxt = t.tag_names(idx)          # typing just after a link isn't part of it; typing inside one is
        ch = [n for n in src if R.is_char_tag(n) and n not in ("lm", "meta") and not n.startswith(R.AUDIO)
              and (not n.startswith("link:") or n in nxt)]
        for k, v in self.pending.items():
            if k in R.CHAR_FLAGS:
                ch = [n for n in ch if n != k] + ([k] if v else [])
            else:
                ch = [n for n in ch if not n.startswith(k + ":")]
                if v not in (None, ""):
                    if k == "fs":
                        v = ("%.1f" % float(v)).rstrip("0").rstrip(".")
                    ch.append("%s:%s" % (k, v))
        return tuple(sorted(set(par + ch)))

    def _typing_undo(self, ch):
        """One undo step per burst of typing (like Word), plus one per new paragraph."""
        now = time.time()
        if now - self._last_type > 1.2 or ch == "\n":
            self._push_undo()
        self._last_type = now

    def _on_key(self, ev):
        ch = ev.char
        if not ch or ch < " " or ch == "\x7f" or (ev.state & 0x4 and not ev.state & 0x20000):
            return None
        if self.pictool and self.pictool.sel:      # typing goes on at the cursor; the picture stays
            self.pictool.deselect()
        t = self.text
        self._typing_undo(ch)
        if t.tag_ranges("sel"):
            try:
                t.delete("sel.first", "sel.last")
            except tk.TclError:
                pass
        if "lm" in t.tag_names("insert") and t.compare("insert", "==", "insert linestart"):
            me = self._marker_end(t.index("insert linestart"))
            if me:
                t.mark_set("insert", me)
        tags = self._typing_tags()
        t.insert("insert", ch, tags)
        for tg in tags:
            if tg.startswith(("fg:", "hl:")):
                self._color_tag(tg)
        t.see("insert")
        self._restyle("insert", "insert")
        self._spell_dirty("insert", "insert")
        return "break"

    def _on_return(self, ev):
        t = self.text
        self._push_undo()
        if t.tag_ranges("sel"):
            t.delete("sel.first", "sel.last")
        line = t.index("insert linestart")
        names = t.tag_names(line)
        li = R.tag_value(names, "li")
        if li:
            me = self._marker_end(line)
            body = t.get(me or line, "%s lineend" % line)
            if not body.strip():     # empty list item: end the list
                if me:
                    t.delete(line, me)
                self._remove_key("li", line, t.index("%s lineend +1c" % line))
                self._renumber()
                self._restyle(line, line)
                return "break"
        tags = self._typing_tags()
        t.insert("insert", "\n", tags)
        new_line = t.index("insert linestart")
        style = R.tag_value(names, "st", "normal")
        if style in ("title", "subtitle", "h1", "h2", "h3"):
            self._remove_key("st", new_line, t.index("%s lineend +1c" % new_line))
        if li:
            par = [n for n in t.tag_names(new_line) if R.is_par_tag(n)]
            t.insert(new_line, "•\t", tuple(set(par + ["lm"])))
            self._renumber()
        self.pending.clear()
        self._restyle(line, "insert")
        t.see("insert")
        return "break"

    def _on_tab(self, ev):
        if self.list_level(1):
            return "break"
        self._typing_undo("\t")
        self.text.insert("insert", "\t", self._typing_tags())
        return "break"

    def _delete_selected_picture(self):
        """Backspace / Delete while a picture is selected (clicked) removes that picture."""
        name = self.pictool.sel if self.pictool else None
        if not name:
            return False
        self.pictool.deselect()
        self.delete_image(name)
        return True

    def _on_backspace(self, ev):
        t = self.text
        if self._delete_selected_picture():
            return "break"
        if not t.tag_ranges("sel") and t.compare("insert", ">", "1.0") and "softnl" in t.tag_names("insert -1c"):
            t.mark_set("insert", "insert -1c")     # (skip the invisible break: delete the character you see)
        if not t.tag_ranges("sel"):
            line = t.index("insert linestart")
            me = self._marker_end(line)
            if me and t.compare("insert", "<=", me):
                self._push_undo()
                t.delete(line, me)
                self._remove_key("li", line, t.index("%s lineend +1c" % line))
                self._renumber()
                self._restyle(line, line)
                return "break"
        self._typing_undo("\n" if t.tag_ranges("sel") else "")
        T.later(self.frame, None, self._after_join)
        return None

    def _on_delete(self, ev):
        if self._delete_selected_picture():
            return "break"
        if not self.text.tag_ranges("sel") and "softnl" in self.text.tag_names("insert"):
            self.text.mark_set("insert", "insert +1c")
        self._typing_undo("\n" if self.text.tag_ranges("sel") else "")
        T.later(self.frame, None, self._after_join)
        return None

    def _after_join(self):
        """After two paragraphs merge, give the whole line the first paragraph's formatting."""
        t = self.text
        self._ver += 1
        line = t.index("insert linestart")
        le = t.index("%s lineend +1c" % line)
        want = [n for n in t.tag_names(line) if R.is_par_tag(n)]
        for tg in t.tag_names():
            if R.is_par_tag(tg) and tg not in want:
                t.tag_remove(tg, line, le)
        for tg in want:
            t.tag_add(tg, line, le)
        self._renumber()
        self._restyle(line, line)

    # ------------------------------------------------------------------ ribbon state
    def _sync_ribbon_soon(self):
        if self._rib_job:
            self.frame.after_cancel(self._rib_job)
        self._rib_job = T.later(self.frame, 120, self._sync_ribbon)

    def _sync_ribbon(self):
        self._rib_job = None
        t = self.text
        if not self.path:
            return
        idx = "sel.first" if self._sel() else ("insert-1c" if t.compare("insert", ">", "insert linestart") else "insert")
        try:
            names = t.tag_names(idx)
        except tk.TclError:
            return
        run = R._run_from_tags("", names)
        for k, v in self.pending.items():
            if k in R.CHAR_FLAGS:
                run[k] = v
            elif v:
                run[k] = float(v) if k == "fs" else v
        style = R.tag_value(t.tag_names("%s linestart" % idx), "st", "normal")
        fam, size, bold, italic = self.ctx.run_font(style, run)
        self.font_cb.set(fam)
        self.size_cb.set(("%.1f" % size).rstrip("0").rstrip("."))
        self.style_cb.set(R.STYLES.get(style, R.STYLES["normal"])["label"])
        for k, b in self.fbtn.items():
            on = bool(run.get(k)) or (k == "b" and bold) or (k == "i" and italic)
            b.configure(bg=T.ACCENT_DARK if on else T.PANEL)

    # ------------------------------------------------------------------ menus
    def _popup(self, m, widget):
        m.tk_popup(widget.winfo_rootx(), widget.winfo_rooty() + widget.winfo_height())

    def _color_menu(self):
        m = T.menu(self.root)
        self._fill_color(m)
        self._popup(m, self.color_btn)

    def _fill_color(self, m):
        for name, col in TEXT_COLORS:
            m.add_command(label=("■  " if col else "    ") + name, foreground=col or T.FG,
                          command=lambda c=col: self.set_char("fg", c))
        m.add_separator()

        def more():
            c = colorchooser.askcolor(parent=self.root, title="Text colour")
            if c and c[1]:
                self.set_char("fg", c[1])
        m.add_command(label="More colours…", command=more)

    def _hl_menu(self):
        m = T.menu(self.root)
        self._fill_hl(m)
        self._popup(m, self.hl_btn)

    def _fill_hl(self, m):
        for name, col in HIGHLIGHTS:
            m.add_command(label="■  " + name, foreground=col, command=lambda c=col: self.set_char("hl", c))
        m.add_separator()
        m.add_command(label="No highlight", command=lambda: self.set_char("hl", None))

    def _case_menu(self):
        m = T.menu(self.root)
        self._fill_case(m)
        m.tk_popup(self.root.winfo_pointerx(), self.root.winfo_pointery())

    def _fill_case(self, m):
        for label, mode in (("Sentence case.", "sentence"), ("lowercase", "lower"), ("UPPERCASE", "upper"),
                            ("Capitalize Each Word", "title"), ("tOGGLE cASE", "toggle")):
            m.add_command(label=label, command=lambda md=mode: self.change_case(md))

    def _spacing_menu(self):
        m = T.menu(self.root)
        self._fill_spacing(m)
        m.tk_popup(self.root.winfo_pointerx(), self.root.winfo_pointery())

    def _fill_spacing(self, m):
        for v in (1.0, 1.08, 1.15, 1.5, 2.0, 2.5, 3.0):
            m.add_command(label="Line spacing %s" % ("%.2f" % v).rstrip("0").rstrip("."),
                          command=lambda v=v: self.set_spacing(ls=v))
        m.add_separator()
        m.add_command(label="Add space before paragraph (12 pt)", command=lambda: self.set_spacing(sb=12))
        m.add_command(label="Remove space before paragraph", command=lambda: self.set_spacing(sb=0))
        m.add_command(label="Add space after paragraph (8 pt)", command=lambda: self.set_spacing(sa=8))
        m.add_command(label="Remove space after paragraph", command=lambda: self.set_spacing(sa=0))
        m.add_separator()
        m.add_command(label="First-line indent 0.5\"", command=lambda: self.set_par("fi", 0.5))
        m.add_command(label="No first-line indent", command=lambda: self.set_par("fi", None))
        m.add_command(label="Manuscript format (double-spaced, indented)",
                      command=lambda: (self.set_spacing(ls=2.0, sa=0), self.set_par("fi", 0.5)))

    def _symbol_menu(self):
        m = T.menu(self.root)
        self._fill_symbols(m)
        m.tk_popup(self.root.winfo_pointerx(), self.root.winfo_pointery())

    def _fill_symbols(self, m):
        for group, chars in SYMBOLS:
            sm = T.menu(m)
            for c in chars.split():
                sm.add_command(label=c, command=lambda c=c: self.insert_text(c))
            m.add_cascade(label=group, menu=sm)

    def _more_tools(self, widget):
        """Everything that isn't on the compact toolbar."""
        m = T.menu(self.root)

        def sub(label, fill):
            sm = T.menu(m)
            fill(sm)
            m.add_cascade(label=label, menu=sm)
        sub("Text colour", self._fill_color)
        sub("Highlight", self._fill_hl)
        sub("Change case", self._fill_case)
        m.add_command(label="Clear formatting   (Ctrl+Space)", command=self.clear_formatting)
        m.add_command(label="Format painter", command=self.start_painter)
        m.add_separator()

        def align(sm):
            for al, label in (("left", "Left   (Ctrl+L)"), ("center", "Centre   (Ctrl+E)"),
                              ("right", "Right   (Ctrl+R)"), ("justify", "Justify   (Ctrl+J)")):
                sm.add_command(label=label, command=lambda a=al: self.set_par("al", a))
        sub("Align", align)
        sub("Line & paragraph spacing", self._fill_spacing)
        m.add_command(label="Increase indent", command=lambda: self.indent(0.5))
        m.add_command(label="Decrease indent", command=lambda: self.indent(-0.5))
        m.add_command(label="Bullet list", command=lambda: self.toggle_list("bullet"))
        m.add_command(label="Numbered list", command=lambda: self.toggle_list("num"))
        m.add_separator()
        m.add_command(label="Find & replace\u2026   (Ctrl+F)", command=self.find_replace_dialog)
        m.add_command(label="Next spelling mistake   (F7)", command=self.spell_next)
        m.add_command(label="Thesaurus for the word at the cursor   (Shift+F7)", command=self.thesaurus_at_cursor)
        m.add_separator()

        def insert(sm):
            sm.add_command(label="Picture\u2026", command=self.insert_image_dialog)
            sm.add_command(label="Table\u2026", command=self.insert_table_dialog)
            sm.add_command(label="Page break   (Ctrl+Enter)", command=self.insert_page_break)
            sym = T.menu(sm)
            self._fill_symbols(sym)
            sm.add_cascade(label="Symbol", menu=sym)
            sm.add_command(label="Today's date", command=self.insert_date)
        sub("Insert", insert)
        m.add_separator()
        m.add_command(label="\u25cf Dictate here   (%s)" % VOICE_EDIT, command=lambda: self.app.start_in_note("edit", self))
        m.add_command(label="\u2702 Cut by voice   (%s)" % VOICE_CUT, command=lambda: self.app.start_in_note("cut", self))
        self._popup(m, widget)

    def insert_text(self, s):
        self._push_undo()
        t = self.text
        if t.tag_ranges("sel"):
            t.delete("sel.first", "sel.last")
        t.insert("insert", s, self._typing_tags())
        self._restyle("insert", "insert")
        self._mark_changed()
        t.focus_set()

    def insert_date(self):
        d = datetime.datetime.now()
        self.insert_text(d.strftime("%B %d, %Y").replace(" 0", " "))

    # ------------------------------------------------------------------ right click
    def _word_at(self, idx):
        t = self.text
        a = t.index("%s wordstart" % idx)
        b = t.index("%s wordend" % idx)
        w = t.get(a, b)
        m = re.match(r"[A-Za-zÀ-ɏ'’-]+", w)
        if not m:
            return None, None, None
        return w[:m.end()], a, t.index("%s +%dc" % (a, m.end()))

    WRAP_CHOICES = (("In line with text", None, None),
                    ("Square - text on the right", "square", "right"),
                    ("Square - text on the left", "square", "left"),
                    ("Square - text on the side with more room", "square", "largest"),
                    ("Top and bottom - text above and below only", "topbottom", None),
                    ("In front of text - the text takes no notice", "front", None))

    def picture_menu(self, name, x_root, y_root):
        """The right-click menu of a picture (in the text or floating)."""
        info = self.images[name]
        m = T.menu(self.root)
        m.add_command(label="Copy picture", font=T.UI_BOLD, command=lambda n=name: self.copy_image(n))
        m.add_separator()
        wm = T.menu(m)
        f = info.get("float") or {}
        for label, wrap, side in self.WRAP_CHOICES:
            on = (wrap is None and not f) or (f and f.get("wrap") == wrap and (side is None or f.get("text") == side))
            wm.add_command(label=("✓  " if on else "     ") + label,
                           command=lambda n=name, w=wrap, s=side: self.set_wrap(n, w, s))
        m.add_cascade(label="Text wrapping", menu=wm)
        pm = T.menu(m)
        for spot, label in nobu_float.FloatLayer.SPOTS:
            pm.add_command(label=label, command=lambda n=name, s=spot: self.place_on_page(n, s))
        m.add_cascade(label="Place on page", menu=pm)
        m.add_separator()
        for label, w in (("Small", 200), ("Medium", 340), ("Large", 520), ("Full page width", R.TEXT_W_PX)):
            m.add_command(label=label, command=lambda w=w, n=name: self.resize_image(n, w))
        m.add_command(label="Original size", command=lambda n=name: self.resize_image(n, 0))
        if info.get("h"):
            m.add_command(label="Original shape (undo stretching)", command=lambda n=name: self.resize_image(n, info["w"]))
        m.add_separator()
        m.add_command(label="Crop…", command=lambda n=name: self.crop_dialog(n))
        m.add_command(label="Open in picture viewer", command=lambda: open_path(abs_from_home(info["rel"])))
        m.add_command(label="Remove picture", command=lambda n=name: self.delete_image(n))
        m.tk_popup(x_root, y_root)
        return m

    def set_wrap(self, name, wrap, side=None):
        """Change how the text goes round a picture: wrap None = in line with the text (like a big letter),
        or a floating picture: "square" (side: "right" / "left" / "largest" = where the text goes),
        "topbottom" or "front". Returns the picture's (new) name."""
        info = self.images.get(name)
        if not info:
            return None
        t, fl = self.text, self.flow
        f = info.get("float")
        if wrap is None and not f:
            return name
        self._push_undo()
        if f and wrap:                                  # floating -> floating: just the style
            f["wrap"] = wrap
            if side:
                f["text"] = side
            self._mark_changed()
            fl.reflow()
            new = name
        elif wrap:                                      # in the text -> floating, right where it is now
            idx = t.index(name)
            anchor = fl.par_start(idx)
            k = self.img_scale()
            ix, iy = self._text_inset()
            g = self.pictool.geometry(name) if self.pictool else None
            if g:
                x = g[0] / k
                y = (g[1] + iy + fl.view_offset() - fl.ydoc(anchor)) / k
            else:
                x, y = 0, 0
            t.delete(idx, "%s +1c" % idx)
            self.images.pop(name, None)
            x = max(0, min(nobu_float.TEXT_W - info["w"], x))
            new = fl.add(info["rel"], info["w"], info.get("h"),
                         {"wrap": wrap, "text": side or "largest", "x": x, "y": max(0, y)}, anchor)
            self._mark_changed()
            fl.reflow()
        else:                                           # floating -> back in the text, at its paragraph
            idx = fl.par_start(t.index(name))
            fl.remove(name)
            new = self._add_image(info["rel"], idx, info["w"], info.get("h"))
            self._restyle(idx, idx)
            fl.reflow()
        if self.pictool:
            self.pictool.select(new)
        return new

    def place_on_page(self, name, spot):
        """Right-click > Place on page: a corner or the middle of a side of the page (a picture in a line of
        text comes loose first, with the text flowing round it). Returns the picture's (new) name."""
        if name not in self.images:
            return None
        if not self.images[name].get("float"):
            name = self.set_wrap(name, "square", "largest")
        else:
            self._push_undo()
        self.flow.place_on_page(name, spot)
        self._mark_changed()
        if self.pictool:
            self.pictool.select(name)
        return name

    def _nudge_picture(self, ev, dx, dy):
        """Arrow keys move a selected floating picture (8 pixels; with Shift, 1)."""
        name = self.pictool.sel if self.pictool else None
        if not name or not self.flow.is_float(name):
            if name:
                self.pictool.deselect()
            return None
        step = 1 if ev.state & 0x0001 else 8
        f = self.images[name]["float"]
        if not self.pictool.nudging:
            self._push_undo()
        self.pictool.nudging = True
        self.flow.move_to(name, f["x"] + dx * step, None, dy * step)
        self._mark_changed()
        return "break"

    def _on_right_click(self, ev):
        t = self.text
        name, _ix = self._image_at(ev.x, ev.y)
        if name and name in self.images:
            self.picture_menu(name, ev.x_root, ev.y_root)
            return "break"
        m = T.menu(self.root)
        idx = t.index("@%d,%d" % (ev.x, ev.y))
        if not self._sel() or not (t.compare("sel.first", "<=", idx) and t.compare(idx, "<", "sel.last")):
            t.mark_set("insert", idx)
            t.tag_remove("sel", "1.0", "end")
        link = self._link_at(idx)
        if link:
            url = link[5:]
            m.add_command(label="Open link", accelerator="Ctrl+click", font=T.UI_BOLD, command=lambda: self.open_link(url))
            m.add_command(label="Copy link address", command=lambda: self.copy_link(url))
            m.add_command(label="Remove link", command=lambda: self.remove_link(idx))
            m.add_separator()
        word, wa, wb = self._word_at(idx)
        if word and "sp_err" in t.tag_names(idx):
            sugg = self.app.speller.suggestions(word)
            for s in sugg:
                m.add_command(label=s, font=T.UI_BOLD, command=lambda s=s, a=wa, b=wb: self._replace_word(a, b, s))
            if not sugg:
                m.add_command(label="(no suggestions)", state="disabled")
            m.add_command(label="Add “%s” to spelling dictionary" % word,
                          command=lambda w=word: self._spell_add(w))
            m.add_command(label="Ignore all", command=lambda w=word: self._spell_ignore(w))
            m.add_separator()
        m.add_command(label="Cut", accelerator="Ctrl+X", command=self.cut)
        m.add_command(label="Copy", accelerator="Ctrl+C", command=self.copy)
        m.add_command(label="Paste", accelerator="Ctrl+V", command=self.paste)
        m.add_command(label="Paste as plain text", command=lambda: self.paste(plain=True))
        m.add_separator()
        if word:
            syn = T.menu(m)
            self._fill_synonyms(syn, word, wa, wb)
            m.add_cascade(label="Synonyms for “%s”" % word, menu=syn)
        m.add_command(label="Bold", command=lambda: self.toggle_flag("b"))
        m.add_command(label="Italic", command=lambda: self.toggle_flag("i"))
        m.add_command(label="Clear formatting", command=self.clear_formatting)
        m.add_separator()
        m.add_command(label="Insert picture…", command=self.insert_image_dialog)
        m.add_command(label="Insert table…", command=self.insert_table_dialog)
        m.add_separator()
        m.add_command(label="Find & replace…", accelerator="Ctrl+F", command=self.find_replace_dialog)
        m.add_command(label="Next spelling mistake", accelerator="F7", command=self.spell_next)
        m.add_command(label="Thesaurus…", accelerator="Shift+F7", command=self.thesaurus_at_cursor)
        m.add_separator()
        m.add_command(label="Dictate here   (%s)" % VOICE_EDIT, command=lambda: self.app.start_in_note("edit", self))
        m.add_command(label="Cut a passage by voice   (%s)" % VOICE_CUT, command=lambda: self.app.start_in_note("cut", self))
        try:
            sel = t.get("sel.first", "sel.last").strip()
        except tk.TclError:
            sel = word or ""
        if sel and len(sel.split()) <= 3 and len(sel) <= 40:
            m.add_command(label="Add “%s” to my pronunciation dictionary…" % sel,
                          command=lambda w=sel: self.app.open_dictionary(w))
        m.tk_popup(ev.x_root, ev.y_root)
        return "break"

    def _replace_word(self, a, b, new):
        self._push_undo()
        t = self.text
        tags = t.tag_names(a)
        t.delete(a, b)
        t.insert(a, new, tuple(x for x in tags if x not in ("sp_err", "sel")))
        self._restyle(a, a)
        self._mark_changed()

    def _fill_synonyms(self, menu, word, a, b):
        th = self.app.thesaurus
        res = th.lookup(word)
        if res is None:
            menu.add_command(label="(loading the thesaurus… try again in a moment)", state="disabled")
            th.ensure()
            return
        if not res:
            menu.add_command(label="(no synonyms found)", state="disabled")
            return
        n = 0
        for pos, syns in res[:6]:
            menu.add_command(label="— %s —" % pos, state="disabled")
            for s in syns[:8]:
                if s.lower() == word.lower():
                    continue
                rep = s[:1].upper() + s[1:] if word[:1].isupper() else s
                menu.add_command(label="    " + s, command=lambda r=rep: self._replace_word(a, b, r))
                n += 1
            if n > 30:
                break

    def thesaurus_at_cursor(self):
        word, a, b = self._word_at("insert" if self.text.compare("insert", "==", "insert wordstart") else "insert -1c")
        if not word:
            return
        m = T.menu(self.root)
        self._fill_synonyms(m, word, a, b)
        bb = self.text.bbox("insert")
        x = self.text.winfo_rootx() + (bb[0] if bb else 40)
        y = self.text.winfo_rooty() + (bb[1] + bb[3] if bb else 40)
        m.tk_popup(x, y)

    # ------------------------------------------------------------------ spell check
    def _spell_add(self, w):
        self.app.speller.add(w)
        self._spell_all()

    def _spell_ignore(self, w):
        self.app.speller.ignore(w)
        self._spell_all()

    def _spell_dirty(self, a, b):
        t = self.text
        span = (t.index("%s linestart" % a), t.index("%s lineend" % b))
        if not self._spell_queue or self._spell_queue[-1] != span:     # typing on one line: check it once
            self._spell_queue.append(span)
        if self._spell_job:
            self.frame.after_cancel(self._spell_job)
        self._spell_job = T.later(self.frame, 700, self._spell_run)

    def _spell_all(self):
        self._spell_queue = [("1.0", self.text.index("end-1c"))]
        self._spell_run()

    def _spell_run(self):
        self._spell_job = None
        sp = self.app.speller
        if not sp.ready:
            self._spell_job = T.later(self.frame, 1000, self._spell_run)
            return
        t = self.text
        budget = 400
        while self._spell_queue and budget > 0:
            a, b = self._spell_queue.pop(0)
            a = t.index(a)
            b = t.index(b)
            line = t.index("%s linestart" % a)
            while t.compare(line, "<=", b) and budget > 0:
                budget -= 1
                le = t.index("%s lineend" % line)
                t.tag_remove("sp_err", line, le)
                txt = t.get(line, le)
                has_objects = any(k in ("image", "window") for k, _, _ in t.dump(line, le, image=True, window=True))
                if not has_objects:
                    ln = line.split(".")[0]
                    me = self._marker_end(line)
                    skip = int(me.split(".")[1]) if me else 0     # list number / bullet
                    urls = [(s, e) for s, e, _u in R.find_urls(txt)] if "." in txt else []   # web addresses aren't words
                    for m in nobu_spell_words(txt):
                        budget -= 0.01
                        if m.start() < skip or any(s <= m.start() < e for s, e in urls):
                            continue
                        if not sp.known(m.group(0)):
                            t.tag_add("sp_err", "%s.%d" % (ln, m.start()), "%s.%d" % (ln, m.end()))
                nxt = t.index("%s +1 line linestart" % line)
                if nxt == line or t.compare(nxt, ">=", "end"):
                    break
                line = nxt
            if t.compare(line, "<", b) and budget <= 0:
                self._spell_queue.insert(0, (line, b))
        if self._spell_queue:
            self._spell_job = T.later(self.frame, 30, self._spell_run)

    def spell_next(self):
        t = self.text
        r = t.tag_nextrange("sp_err", "insert +1c") or t.tag_nextrange("sp_err", "1.0")
        if not r:
            self.app.set_status("No spelling mistakes found.")
            return
        t.tag_remove("sel", "1.0", "end")
        t.tag_add("sel", r[0], r[1])
        t.mark_set("insert", r[0])
        t.see(r[0])
        bb = t.bbox(r[0])
        if bb:                                  # show the suggestions right there, as a right-click would
            import types
            self._on_right_click(types.SimpleNamespace(
                x=bb[0] + 2, y=bb[1] + 2, x_root=t.winfo_rootx() + bb[0], y_root=t.winfo_rooty() + bb[1] + bb[3]))

    # ------------------------------------------------------------------ undo (snapshots: text + formatting)
    def _items_now(self):
        """The note's items. Reuses the copy made at the last quiet moment if nothing changed since."""
        v = self._version()
        if self._snap and self._snap[0] == v:
            return self._snap[1]
        items = self._range_items("1.0", "end-1c")
        self._snap = (v, items)
        return items

    def _snapshot(self):
        items = self._items_now()      # never modified afterwards, so it can be shared safely
        return (items, self.text.index("insert"), self.text.yview()[0])

    def _push_undo(self):
        if self._loading or not self.path:
            return
        try:
            self._undo.append(self._snapshot())
        except Exception:
            return
        # keep up to 80 steps, but not more than ~20 million characters of history (big notes)
        size = sum(len(it.get("t", "")) for snap in self._undo for it in snap[0]) if len(self._undo) > 20 else 0
        while len(self._undo) > 80 or (size > 20_000_000 and len(self._undo) > 5):
            gone = self._undo.pop(0)
            size -= sum(len(it.get("t", "")) for it in gone[0])
        self._redo.clear()

    def _restore(self, snap):
        items, ins, top = snap
        self._load_items(items)
        self.text.mark_set("insert", ins)
        self.text.yview_moveto(top)
        self._mark_changed()

    def undo(self):
        if not self._undo:
            return
        self._redo.append(self._snapshot())
        self._restore(self._undo.pop())

    def redo(self):
        if not self._redo:
            return
        self._undo.append(self._snapshot())
        self._restore(self._redo.pop())

    def _after_format(self, a, b):
        self._restyle(a, b)
        self._mark_changed()
        self._sync_ribbon()
        self._schedule_pages()

    # ------------------------------------------------------------------ clipboard
    def _range_items(self, a, b):
        t = self.text
        items, active = [], set(x for x in t.tag_names(a) if R.persistent(x))
        soft = "softnl" in t.tag_names(a)          # (invisible line breaks round floating pictures: never kept)
        for key, val, _ix in t.dump(a, b, text=True, tag=True, image=True, window=True, mark=True):
            if key == "tagon":
                active.add(val)
                soft = soft or val == "softnl"
            elif key == "tagoff":
                active.discard(val)
                if val == "softnl":
                    soft = False
            elif key == "mark" and self.flow.is_float(val):
                info = self.images[val]
                items.append(dict({"i": info["rel"], "w": info["w"], "float": dict(info["float"]), "g": []},
                                  **({"h": info["h"]} if info.get("h") else {})))
            elif key == "text" and soft:
                continue
            elif key == "text":
                g = sorted(x for x in active if R.persistent(x))
                if items and "t" in items[-1] and items[-1]["g"] == g:
                    items[-1]["t"] += val
                else:
                    items.append({"t": val, "g": g})
            elif key == "image" and val in self.images:
                info = self.images[val]
                items.append(dict({"i": info["rel"], "w": info["w"], "g": sorted(x for x in active if R.persistent(x))},
                                  **({"h": info["h"]} if info.get("h") else {})))
            elif key == "window":
                blk = self.blocks.get(val)
                if isinstance(blk, TableBlock):
                    items.append({"table": {"rows": blk.rows()}, "g": []})
                elif isinstance(blk, PageBreakBlock):
                    items.append({"pb": 1, "g": []})
        return items

    def copy(self, cut=False):
        s = self._sel()
        if not s:
            return
        items = self._range_items(*s)
        paras = R.items_to_paras(items)
        text = self.flow.plain(*s) if self.flow else self.text.get(*s)
        self.app.clip_items = (text, items)
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        pics = [it["i"] for it in items if "i" in it]
        alone = len(pics) == 1 and not any(it.get("t", "").strip() or "table" in it for it in items)
        try:
            src = (lambda rel: "file:///" + abs_from_home(rel).replace("\\", "/"))
            nobu_clip.set_rich(text, R.to_html(paras, self.ctx, img_src=src, for_word=True), R.to_rtf(paras, self.ctx),
                               picture=abs_from_home(pics[0]) if alone else None)   # just a picture: copy it as one
        except Exception:
            log.exception("rich copy failed")
        if cut:
            self._push_undo()
            gone = [n for n in (self.flow.names() if self.flow else [])      # floating pictures go with the text
                    if self.text.compare(s[0], "<=", n) and self.text.compare(n, "<", s[1])]
            self.text.delete(*s)
            for n in gone:
                self.flow.remove(n)
            self._after_join()
            self._mark_changed()

    def cut(self):
        self.copy(cut=True)

    def paste(self, plain=False):
        t = self.text
        try:
            text = self.root.clipboard_get()
        except tk.TclError:
            text = None
        items = None
        from_nobu = False              # copied from a Nobu note: its fonts are left alone
        if not plain:
            ci = getattr(self.app, "clip_items", None)
            if ci and text is not None and ci[0] == text:
                items = ci[1]
                from_nobu = True
            else:
                h = nobu_clip.get_html()
                if h:
                    try:
                        import nobu_importers
                        paras = R.html_to_paras(h, image_cb=lambda src: nobu_importers.fetch_image(src, self.path))
                        items = R.paras_to_items(paras)
                        if items and items[-1].get("t") == "\n" and "\n" not in (text or "")[-1:]:
                            items = items[:-1]
                    except Exception:
                        log.exception("html paste failed")
                        items = None
                if not self._has_words(items, text) and self.paste_image():
                    return
        if items is None:
            if text is None:
                self.paste_image()
                return
            self._push_undo()
            if t.tag_ranges("sel"):
                t.delete("sel.first", "sel.last")
            start = t.index("insert")
            t.insert("insert", text.replace("\r\n", "\n"), self._typing_tags())
            if not plain:
                self._autolink(start, t.index("insert"))
            self._finish_insert(start, t.index("insert"))
            return
        self._push_undo()
        if t.tag_ranges("sel"):
            t.delete("sel.first", "sel.last")
        start = t.index("insert")
        orig = items
        if not from_nobu:
            import nobu_pastefonts as PF
            items = PF.apply_rules(items, self.app.cfg.get("paste_font_rules") or {})
        t.mark_set("nobu_pa", start)            # the pasted text, in case the font window changes it again
        t.mark_gravity("nobu_pa", "left")
        self._insert_items(items, "insert")
        t.mark_set("nobu_pb", "insert")
        t.mark_gravity("nobu_pb", "left")
        self._autolink(start, t.index("insert"))
        self._finish_insert(start, t.index("insert"))
        if not from_nobu:
            self.pasted_fonts(orig, items)

    def pasted_fonts(self, orig, items):
        """After a paste from another program (orig: as copied, items: as changed by the writer's choices).
        The fonts of the last paste are remembered; a font that wasn't in it opens the font window.
        Fonts the computer doesn't have are looked up online (free ones only), unless Settings says not to."""
        import nobu_fontfetch as FF
        import nobu_pastefonts as PF
        cfg = self.app.cfg
        body = (self.ctx.body or "").lower()
        fams = [f for f in PF.families_in(orig) if f.lower() != body]
        win = None
        if fams:
            new = PF.fresh(fams, cfg.get("last_paste_fonts") or [])
            cfg.update(last_paste_fonts=[f.lower() for f in fams])    # emptied and refilled by each paste
            if new:
                win = self.font_win = PF.PasteFontsWindow(self, fams, lambda rules: self._repaste_fonts(orig, rules))
                import nobu_fonts
                have = {f.lower() for f in nobu_fonts.families(self.root)}
                rules = cfg.get("paste_font_rules") or {}
                for f in fams:
                    done = FF._tried.get(f.lower())
                    rule = rules.get(f.lower())
                    win.set_status(f, ("Changed into %s, as you chose before." % PF.describe(rule)) if rule else
                                   PF.fetch_status(*done) if done else
                                   "On this computer." if f.lower() in have else
                                   "Not on this computer - it shows in a similar font.")
        self._look_up_fonts(items, win)

    def _look_up_fonts(self, items, win=None):
        """Look for free copies of the fonts in items that this computer doesn't have (in the background).
        win: the font window, which shows the answers; without it they go to the status bar."""
        cfg = self.app.cfg
        if cfg.get("fetch_fonts", True) is False:
            return
        import nobu_fontfetch as FF
        fams = [f for f in FF.missing_families(items, self.root) if f.lower() not in FF._tried]
        if not fams:
            return
        install = cfg.get("install_fonts", True) is not False
        if win is not None:
            for f in fams:
                win.set_status(f, "Not on this computer - looking for a free copy…")
        else:
            self.app.set_status("Looking for a free copy of %s…" % ", ".join("“%s”" % f for f in fams))

        def work():
            results = [(f,) + tuple(FF.fetch(f, install=install)) for f in fams]
            self.app.ui(self._fonts_fetched, results, win)
        import threading
        threading.Thread(target=work, name="font-fetch", daemon=True).start()

    def _fonts_fetched(self, results, win=None):
        import nobu_fontfetch as FF
        import nobu_pastefonts as PF
        if any(r[1] == "downloaded" for r in results):
            for ed in self.app.ws.editors():
                try:
                    ed.refresh_fonts()
                except Exception:
                    log.exception("refresh fonts")
        self.app.set_status("")
        if win is not None and win.alive():
            for fam, outcome, detail in results:
                win.set_status(fam, PF.fetch_status(outcome, detail))
        elif any(r[1] == "downloaded" for r in results):
            self.app.set_status(FF.message([r for r in results if r[1] == "downloaded"]).replace("\n\n", "   "))

    def _repaste_fonts(self, orig, rules):
        """The font window's Apply: put the text just pasted in again, changed by the new choices (one undo step)."""
        import nobu_pastefonts as PF
        t = self.text
        try:
            a, b = t.index("nobu_pa"), t.index("nobu_pb")
        except tk.TclError:
            return
        if t.compare(a, ">=", b):
            return
        items = PF.apply_rules(orig, rules)
        self._push_undo()
        gone = [n for n in (self.flow.names() if self.flow else []) if t.compare(a, "<=", n) and t.compare(n, "<", b)]
        t.delete(a, b)
        for n in gone:
            self.flow.remove(n)
        t.mark_set("insert", a)
        self._insert_items(items, "insert")
        t.mark_set("nobu_pb", "insert")
        self._autolink(a, t.index("insert"))
        self._finish_insert(a, t.index("insert"))
        mine = {f.lower() for f in PF.families_in(orig)}
        done = ["%s → %s" % (r["name"], PF.describe(r)) for k, r in rules.items() if k in mine]
        self.app.set_status(("Pasted text changed: " + "; ".join(done)) if done else "Pasted text kept as it was.")
        self._look_up_fonts(items)

    def refresh_fonts(self):
        """A font was just added to the computer: text already shown in a stand-in font switches to it."""
        for f in self._fonts.values():
            f.configure(family=f.cget("family"))
        self._fill_fonts()

    @staticmethod
    def _has_words(items, text):
        """Is there real writing on the clipboard? "Copy image" in a web browser also gives the picture's
        web address (as text, and as HTML Nobu can't load offline) - then the picture itself should win."""
        if items is not None:
            return any(it.get("t", "").strip() or "i" in it or "table" in it for it in items)
        s = (text or "").strip()
        return bool(s) and not re.fullmatch(r"(https?|file)://\S+", s)

    def _finish_insert(self, a, b):
        self._renumber()
        self._restyle(a, b)
        self._spell_dirty(a, b)
        self._mark_changed()
        self._schedule_pages()
        self.text.see("insert")

    # ------------------------------------------------------------------ pictures
    def _next_img_name(self):
        self._img_counter += 1
        return "nobuimg%d" % self._img_counter

    def _text_inset(self):
        """place() inside the Text counts from inside its border and padding (the page margins); bbox() and
        dlineinfo() count from its corner. Returns (x, y) to subtract."""
        t = self.text
        px = lambda v: int(round(t.winfo_fpixels(v)))     # noqa: E731
        bd = px(t.cget("borderwidth")) + px(t.cget("highlightthickness"))
        return bd + px(t.cget("padx")), bd + px(t.cget("pady"))

    def _show_photo(self, name, photo):
        """Show a new picture image, in the text or (for a floating picture) on its own."""
        info = self.images[name]
        if info.get("float"):
            info["label"].configure(image=photo)
        else:
            self.text.image_configure(name, image=photo)
        info["photo"] = photo

    def img_scale(self):
        """Screen pixels per page pixel (pictures are measured in page pixels, 96 to the inch)."""
        return self.dpi / 96.0 * self.zoom

    def _make_photo(self, rel, width, height=None):
        """The picture as shown on the page: width (and height, if it was stretched) in page pixels.
        Returns (photo, width, height); height is None when the picture keeps its own shape."""
        img = nd.load_picture(rel)
        w0, h0 = img.size
        width = max(nobu_pictool.MIN_W, int(round(width or min(w0, 480))))
        height = max(nobu_pictool.MIN_H, int(round(height))) if height else None
        k = self.img_scale()
        dw = max(20, int(width * k))
        dh = max(10, int(height * k)) if height else max(1, round(h0 * dw / w0))
        return nobu_pictool.tk_photo(img.resize((dw, dh), Image.LANCZOS)), width, height

    def place_image(self, rel, width=None, index="insert", height=None):
        photo, width, height = self._make_photo(rel, width, height)
        name = self.text.image_create(index, image=photo, name=self._next_img_name(), padx=2, pady=4)
        self.images[name] = {"rel": rel, "w": width, "h": height, "photo": photo}
        return name

    def _add_image(self, rel, index="insert", width=None, height=None):
        """Put a picture (already in Images\\) into the page; it takes on the paragraph's alignment etc."""
        name = self.place_image(rel, width, index, height)
        for tg in self._typing_tags(index):
            if R.is_par_tag(tg):
                self.text.tag_add(tg, name)
        self._mark_changed()
        self._schedule_pages()
        return name

    def insert_image_file(self, src, index="insert"):
        if not self.path:
            return None
        try:
            self._push_undo()
            return self._add_image(nd.import_image(src, self.path), index)
        except Exception as e:
            log.exception("insert image failed")
            T.info(self.root, "Nobu Notes", "Could not add that picture.\n\n%s" % e)

    def insert_image_dialog(self):
        if not self.path:
            return
        files = filedialog.askopenfilenames(
            parent=self.root, title="Choose pictures",
            filetypes=[("Pictures", "*.png *.jpg *.jpeg *.gif *.bmp *.webp *.tif *.tiff"), ("All files", "*.*")])
        for fp in files:
            self.insert_image_file(fp)

    def paste_image(self):
        """Paste a picture from the clipboard: a screenshot, "Copy image" from a web page or another
        program, or picture files copied in File Explorer. False if there is no picture to paste."""
        if not self.path:
            return False
        try:
            from PIL import ImageGrab
            data = ImageGrab.grabclipboard()
        except Exception:
            data = None
        if data is None:
            return False
        if isinstance(data, (list, tuple)):
            files = [str(fp) for fp in data if str(fp).lower().endswith(IMG_EXTS)]
            if files and self.text.tag_ranges("sel"):
                self._push_undo()
                self.text.delete("sel.first", "sel.last")
            for fp in files:
                self.insert_image_file(fp)
            return bool(files)
        try:
            self._push_undo()
            if self.text.tag_ranges("sel"):
                self.text.delete("sel.first", "sel.last")
            self._add_image(nd.save_pil_image(data, self.path))
            self.text.see("insert")
            return True
        except Exception:
            log.exception("paste image failed")
            return False

    def _image_at(self, x, y):
        t = self.text
        idx = t.index("@%d,%d" % (x, y))
        try:
            d = t.dump(idx, t.index(idx + "+1c"), image=True)
        except tk.TclError:
            return None, None
        for key, val, ix in d:
            if key == "image":
                bb = t.bbox(ix)
                if bb and bb[0] <= x <= bb[0] + bb[2] and bb[1] <= y <= bb[1] + bb[3]:
                    return val, ix
        return None, None

    def _on_double_click(self, ev):
        name, _ = self._image_at(ev.x, ev.y)
        if name and name in self.images:
            self._open_picture(name)
            return "break"
        return None

    def _open_picture(self, name):
        """Open a picture in Windows' picture viewer."""
        info = self.images.get(name)
        if info:
            open_path(abs_from_home(info["rel"]))

    def move_image(self, name, dest):
        """Move a picture to dest (a place between two characters). It takes on the alignment etc. of the
        paragraph it lands in. Returns the picture's new name, or None if it didn't move."""
        t = self.text
        info = self.images.get(name)
        if not info:
            return None
        src = t.index(name)
        dest = t.index(dest)
        if t.compare(dest, "==", src) or t.compare(dest, "==", "%s +1c" % src):
            return None
        self._push_undo()
        t.mark_set("nobu_move", dest)
        t.delete(src, "%s +1c" % src)
        self.images.pop(name, None)
        new = self._add_image(info["rel"], "nobu_move", info["w"], info.get("h"))
        t.mark_unset("nobu_move")
        self._restyle(src, src)
        self._restyle(t.index(new), t.index(new))
        return new

    def resize_image(self, name, width, height=None, undo=True):
        """New size in page pixels. Without a height the picture keeps its own shape; width 0 = its real size."""
        info = self.images.get(name)
        if not info:
            return
        if undo:
            self._push_undo()
        if not width:
            with Image.open(abs_from_home(info["rel"])) as im:
                width = im.size[0]
        photo, w, h = self._make_photo(info["rel"], width, height)
        self._show_photo(name, photo)
        info.update(w=w, h=h)
        self._mark_changed()
        self._schedule_pages()
        if info.get("float"):
            self.flow.reflow()
        if self.pictool and self.pictool.sel == name:
            self.pictool.sync()

    def crop_image(self, name, box):
        """Keep only box = (left, top, right, bottom), in the picture's own pixels. The cropped picture is
        saved as a new file and the original is kept, so Ctrl+Z brings the whole picture back."""
        info = self.images.get(name)
        if not info or not self.path:
            return False
        img = nd.load_picture(info["rel"])
        W, H = img.size
        l, t, r, b = (int(round(v)) for v in box)
        l, t = max(0, min(l, W - 1)), max(0, min(t, H - 1))
        r, b = max(l + 1, min(r, W)), max(t + 1, min(b, H))
        if (l, t, r, b) == (0, 0, W, H):
            return False
        base, ext = os.path.splitext(os.path.basename(info["rel"]))
        base = re.sub(r"_cropped(_\d+)?$", "", base)
        ext = ".jpg" if ext.lower() in (".jpg", ".jpeg") else ".png"
        try:
            rel = nd.save_pil_image(img.crop((l, t, r, b)), self.path, base + "_cropped", ext)
        except Exception as e:
            log.exception("crop failed")
            T.info(self.root, "Nobu Notes", "Could not crop that picture.\n\n%s" % e)
            return False
        self._push_undo()
        h = info["h"] * (b - t) / H if info.get("h") else None          # the kept part stays the same scale
        photo, w, h = self._make_photo(rel, info["w"] * (r - l) / W, h)
        self._show_photo(name, photo)
        info.update(rel=rel, w=w, h=h)
        if info.get("float"):
            self.flow.schedule()
        self._mark_changed()
        self._schedule_pages()
        return True

    def copy_image(self, name):
        """Copy a picture so it can be pasted anywhere: into another note, Word, an email, Paint, a chat..."""
        info = self.images.get(name)
        if not info:
            return False
        items = [dict({"i": info["rel"], "w": info["w"], "g": []}, **({"h": info["h"]} if info.get("h") else {}))]
        paras = R.items_to_paras(items)
        src = (lambda rel: "file:///" + abs_from_home(rel).replace("\\", "/"))
        self.app.clip_items = None
        try:
            return nobu_clip.set_rich("", R.to_html(paras, self.ctx, img_src=src, for_word=True), R.to_rtf(paras, self.ctx),
                                      picture=abs_from_home(info["rel"]))
        except Exception:
            log.exception("copy picture failed")
            T.info(self.root, "Nobu Notes", "Could not copy that picture.")
            return False

    def crop_dialog(self, name):
        if name not in self.images:
            return None
        import nobu_crop
        return nobu_crop.CropWindow(self, name)

    def delete_image(self, name):
        self._push_undo()
        if self.flow.is_float(name):
            self.flow.remove(name)
            self._mark_changed()
            return
        t = self.text
        try:
            ix = t.index(name)
            t.delete(ix, ix + "+1c")
        except tk.TclError:
            pass
        self.images.pop(name, None)
        self._mark_changed()

    # ------------------------------------------------------------------ tables & page breaks
    def insert_table_dialog(self):
        if not self.path:
            return
        v = T.ask_string(self.root, "Insert table", "Size of the table (columns x rows):", "3 x 3")
        if not v:
            return
        m = re.match(r"\s*(\d+)\s*[x×*, ]\s*(\d+)", v)
        cols, rows = (int(m.group(1)), int(m.group(2))) if m else (3, 3)
        self._push_undo()
        self._insert_block("table", [[""] * max(1, min(cols, 12)) for _ in range(max(1, min(rows, 60)))])

    def insert_page_break(self):
        if not self.path:
            return
        self._push_undo()
        self._insert_block("pb", None)

    def _insert_block(self, kind, data, index="insert"):
        t = self.text
        idx = t.index(index)
        if t.compare(idx, ">", "%s linestart" % idx):
            t.insert(idx, "\n", self._typing_tags(idx))
            idx = t.index("%s +1c" % idx)
        blk = TableBlock(self, data) if kind == "table" else PageBreakBlock(self)
        t.window_create(idx, window=blk.frame, align="top")
        self.blocks[str(blk.frame)] = blk
        nxt = t.index("%s +1c" % idx)
        if t.get(nxt) != "\n" or t.compare(nxt, ">=", "end -1c"):
            t.insert(nxt, "\n")
        t.mark_set("insert", "%s +2c" % idx)
        self._mark_changed()
        self._schedule_pages()
        return blk

    def delete_block(self, blk):
        self._push_undo()
        t = self.text
        try:
            ix = t.index(blk.frame)
            t.delete(ix, "%s +1c" % ix)
        except tk.TclError:
            pass
        self.blocks.pop(str(blk.frame), None)
        self._mark_changed()
        self._schedule_pages()

    # ------------------------------------------------------------------ pagination
    def _schedule_pages(self):
        if self._page_job:
            self.frame.after_cancel(self._page_job)
        self._page_job = T.later(self.frame, 500, self._paginate)

    def _ypix(self, a, b):
        try:
            v = self.text.count(a, b, "update", "ypixels")
        except tk.TclError:
            return 0
        if isinstance(v, tuple):
            v = v[0]
        return int(v or 0)

    def _paginate(self):
        """Work out where each page starts. One layout pass, then per-line heights (fast even for a novel)."""
        self._page_job = None
        t = self.text
        if not self.path:
            return
        if not t.winfo_ismapped() or t.winfo_width() < self.px(2.0):
            # A tab that isn't showing is squashed to a pixel wide: every letter would be a line of its own,
            # and counting its "pages" froze Nobu at start (5 notes reopened). Count them when it's shown.
            self._pages_later = True
            return
        self._pages_later = False
        page_h = self.px(9.0)
        total = self._ypix("1.0", "end")          # (also brings the layout up to date)
        nlines = int(t.index("end-1c").split(".")[0])
        tops = [0] * (nlines + 2)
        acc = 0
        for i in range(1, nlines + 1):
            tops[i] = acc
            v = t.count("%d.0" % i, "%d.0" % (i + 1), "ypixels")
            acc += (v[0] if isinstance(v, tuple) else v) or 0
        tops[nlines + 1] = acc
        forced = []
        for name, blk in self.blocks.items():
            if isinstance(blk, PageBreakBlock):
                try:
                    ln = int(t.index(name).split(".")[0])
                    forced.append(tops[min(ln + 1, nlines + 1)])
                except tk.TclError:
                    pass
        forced.sort()

        def start_at(ys):
            """(index, top-y) of the first display line whose top is at or below ys."""
            ln = max(1, bisect.bisect_right(tops, ys, 1, nlines + 1) - 1)
            if tops[ln] >= ys:
                return "%d.0" % ln, tops[ln]
            def cnt(a, b, what):        # (layout is already up to date: no "update" needed)
                v = t.count(a, b, what)
                return (v[0] if isinstance(v, tuple) else v) or 0
            nch = cnt("%d.0" % ln, "%d.end" % ln, "indices")
            frac = (ys - tops[ln]) / float(max(1, tops[ln + 1] - tops[ln]))
            if nch > 2500:
                # Very long paragraph: Tk measures inside these slowly, so estimate by proportion
                # (accurate to about a line - pages here are a guide; Word/PDF lay out their own).
                idx = t.index("%d.%d display linestart" % (ln, min(nch, max(0, int(frac * nch)))))
                return idx, int(ys)
            # Normal paragraph: binary search over its display lines for the exact one.
            ndl = max(1, cnt("%d.0" % ln, "%d.0" % (ln + 1), "displaylines"))
            lo, hi = 1, ndl
            while lo < hi:
                mid = (lo + hi) // 2
                if tops[ln] + cnt("%d.0" % ln, "%d.0 + %d display lines" % (ln, mid), "ypixels") >= ys:
                    hi = mid
                else:
                    lo = mid + 1
            idx = t.index("%d.0 + %d display lines" % (ln, lo))
            if int(idx.split(".")[0]) != ln:
                return ("%d.0" % (ln + 1), tops[ln + 1]) if ln < nlines else (None, None)
            return idx, tops[ln] + cnt("%d.0" % ln, idx, "ypixels")

        for m in self.page_marks:
            t.mark_unset(m)
        self.page_marks = []
        y = 0
        while len(self.page_marks) < 3000:
            nxt_forced = next((f for f in forced if f > y), None)
            natural = y + page_h
            if nxt_forced is not None and nxt_forced <= natural:
                target = nxt_forced
            elif natural < total:
                target = natural
            else:
                break
            idx, ytop = start_at(target)
            if idx is None or ytop <= y:
                break
            name = "page%d" % (len(self.page_marks) + 2)
            t.mark_set(name, idx)
            t.mark_gravity(name, "left")
            self.page_marks.append(name)
            y = ytop
        self._update_page_bar()
        self._draw_gutters()

    def _count(self, a, b, what):
        v = self.text.count(a, b, what)
        if isinstance(v, tuple):
            v = v[0]
        return v or 0

    def _current_page(self):
        t = self.text
        top = t.index("@0,%d" % (self.px(1.0) // 2))
        p = 1
        for k, m in enumerate(self.page_marks, start=2):
            if t.compare(m, "<=", top):
                p = k
        return p

    def _update_page_bar(self):
        n = len(self.page_marks) + 1
        cur = self._current_page()
        self.page_lbl.configure(text="Page %d of %d" % (cur, n))
        for w in self.page_nav.winfo_children():
            w.destroy()
        pages = list(range(1, n + 1))
        if n > 15:
            keep = {1, n} | set(range(max(1, cur - 4), min(n, cur + 4) + 1))
            pages = sorted(keep)
        last = 0
        for p in pages:
            if p - last > 1:
                tk.Label(self.page_nav, text="…", bg=T.BG, fg=T.FAINT, font=T.UI_FONT).pack(side="left")
            b = tk.Button(self.page_nav, text=str(p), command=lambda p=p: self.goto_page(p), relief="flat", bd=0,
                          padx=7, pady=0, font=T.UI_FONT, cursor="hand2", highlightthickness=0,
                          bg=T.ACCENT_DARK if p == cur else T.PANEL, fg="white" if p == cur else T.FG,
                          activebackground=T.HOVER, activeforeground=T.FG)
            b.pack(side="left", padx=1)
            last = p
        if self.words_lbl.cget("text") == "":
            self._count_words()

    def _count_words(self):
        try:
            words = len(re.findall(r"\b[\w'’-]+\b", self.text.get("1.0", "end-1c")))
            self.words_lbl.configure(text="%s words" % format(words, ","))
        except Exception:
            pass

    def goto_page(self, p):
        t = self.text
        if p <= 1:
            t.yview_moveto(0)
            t.mark_set("insert", "1.0")
        else:
            m = self.page_marks[p - 2] if p - 2 < len(self.page_marks) else None
            if m:
                t.yview(m)
                t.mark_set("insert", m)
        self._update_page_bar()
        self._draw_gutters()
        t.focus_set()

    def _on_yscroll(self, a, b):
        self.vsb.set(a, b)
        if self.flow:                                  # floating pictures scroll with the page
            self.flow.place_all()
        if self.pictool and self.pictool.sel:          # the selected picture's frame scrolls with it
            self.pictool.sync_soon()
        if self._gut_job is None:
            self._gut_job = T.later(self.frame, 40, self._draw_gutters)

    def _schedule_gutters(self):
        if self._gut_job is None:
            self._gut_job = T.later(self.frame, 60, self._draw_gutters)

    def _draw_gutters(self):
        self._gut_job = None
        t = self.text
        for c in (self.gut_l, self.gut_r):
            c.delete("all")
        h = self.gut_l.winfo_height()
        marks = [("1.0", 1)] + [(m, k) for k, m in enumerate(self.page_marks, start=2)]
        for m, k in marks:
            try:
                info = t.dlineinfo(m)
            except tk.TclError:
                info = None
            if not info:
                continue
            y = info[1] - (self.px(0.35) if k > 1 else 0)
            if y < -20 or y > h + 20:
                continue
            for c, anchor, x in ((self.gut_l, "e", max(64, self.gut_l.winfo_width() - 8)), (self.gut_r, "w", 8)):
                if k > 1:
                    c.create_line(0, y, c.winfo_width(), y, fill=T.FAINT, dash=(4, 3))
                if c.winfo_width() >= 60:
                    c.create_text(x, y + 10, text="Page %d" % k, anchor=anchor, fill=T.FAINT, font=T.UI_FONT)
        cur = self._current_page()
        if self.page_lbl.cget("text") != "Page %d of %d" % (cur, len(self.page_marks) + 1):
            self._update_page_bar()

    # ------------------------------------------------------------------ audio links
    def _ensure_audio_tag(self, tag):
        t = self.text
        rel = tag[len(R.AUDIO):]
        t.tag_configure(tag, foreground=T.ACCENT, underline=True)
        t.tag_bind(tag, "<Button-1>", lambda e, r=rel: self._play(r))
        t.tag_bind(tag, "<Enter>", lambda e: t.config(cursor="hand2"))
        t.tag_bind(tag, "<Leave>", lambda e: t.config(cursor="xterm"))

    # ------------------------------------------------------------------ web links
    def _ensure_link_tag(self, tag):
        t = self.text
        if tag in self._styled:
            return
        self._styled.add(tag)
        self._sel_up = False
        t.tag_configure(tag, foreground=T.ACCENT, underline=True)
        t.tag_raise(tag)
        t.tag_bind(tag, "<Control-Button-1>", lambda e, u=tag[5:]: self.open_link(u))
        t.tag_bind(tag, "<Enter>", lambda e, u=tag[5:]: (t.config(cursor="hand2"),
                                                         self.app.set_status("Ctrl+click to open  %s" % u)))
        t.tag_bind(tag, "<Leave>", lambda e: t.config(cursor="xterm"))

    def open_link(self, url):
        """Opens in your web browser (that's a separate program - Nobu itself stays offline)."""
        if R.is_web_link(url):
            open_path(url)

    def _link_at(self, idx):
        for tg in self.text.tag_names(idx):
            if tg.startswith("link:"):
                return tg
        return None

    def _link_range(self, tag, idx):
        """Where the link at idx starts and ends."""
        t = self.text
        r = t.tag_prevrange(tag, "%s +1c" % idx)
        return (r[0], r[1]) if r else (idx, t.index("%s +1c" % idx))

    def remove_link(self, idx):
        tag = self._link_at(idx)
        if not tag:
            return
        self._push_undo()
        self.text.tag_remove(tag, *self._link_range(tag, idx))
        self._mark_changed()

    def copy_link(self, url):
        self.app.clip_items = None
        self.root.clipboard_clear()
        self.root.clipboard_append(url)

    def _autolink(self, a, b):
        """Make every web address written between a and b a link (unless it already is one)."""
        t = self.text
        text = "".join(v if k == "text" else "￼"          # (a picture or table counts as one character)
                       for k, v, _i in t.dump(a, b, text=True, image=True, window=True))
        for s, e, url in R.find_urls(text):
            i, j = t.index("%s +%dc" % (a, s)), t.index("%s +%dc" % (a, e))
            if any(self._link_at(t.index("%s +%dc" % (i, k))) for k in range(e - s)):
                continue
            tag = "link:" + url
            self._ensure_link_tag(tag)
            t.tag_add(tag, i, j)

    def _play(self, rel):
        p = abs_from_home(rel)
        if os.path.exists(p):
            open_path(p)
        else:
            T.info(self.root, "Nobu Notes", "That recording file was not found:\n%s" % p)

    # ------------------------------------------------------------------ serialization
    def serialize(self):
        d = {"format": "nobu-note", "version": 2, "items": self._items_now()}
        for k, v in self.meta.items():
            d.setdefault(k, v)
        return d

    def _insert_items(self, items, index):
        t = self.text
        t.mark_set("nobu_ins", index)
        t.mark_gravity("nobu_ins", "right")
        floats = []
        for it in items:
            tags = tuple(R.upgrade_tags(it.get("g", [])))
            for tg in tags:
                if tg.startswith(R.AUDIO):
                    self._ensure_audio_tag(tg)
                elif tg.startswith(("fg:", "hl:")):
                    self._color_tag(tg)
                elif tg.startswith("link:"):
                    self._ensure_link_tag(tg)
            if "t" in it:
                t.insert("nobu_ins", it["t"], tags)
            elif "i" in it and it.get("float") and self.flow:
                try:
                    floats.append(self.flow.add(it["i"], it.get("w"), it.get("h"), it["float"], "nobu_ins", "left"))
                except Exception:
                    log.warning("missing image %s", it.get("i"))
            elif "i" in it:
                try:
                    name = self.place_image(it["i"], it.get("w"), "nobu_ins", it.get("h"))
                    for tg in tags:
                        t.tag_add(tg, name)
                except Exception:
                    log.warning("missing image %s", it.get("i"))
                    t.insert("nobu_ins", "[missing picture: %s]" % os.path.basename(it.get("i", "")), ("meta",))
            elif "table" in it:
                blk = TableBlock(self, it["table"].get("rows"))
                t.window_create("nobu_ins", window=blk.frame, align="top")
                self.blocks[str(blk.frame)] = blk
            elif "pb" in it:
                blk = PageBreakBlock(self)
                t.window_create("nobu_ins", window=blk.frame, align="top")
                self.blocks[str(blk.frame)] = blk
        t.mark_set("insert", "nobu_ins")
        t.mark_unset("nobu_ins")
        for n in floats:                   # (pinned now; from here on they move down with their paragraph)
            t.mark_gravity(n, "right")

    def _load_items(self, items):
        t = self.text
        self._loading = True
        if self.pictool:
            self.pictool.deselect()
        if self.flow:
            self.flow.clear()
        try:
            t.delete("1.0", "end")
            for b in list(self.blocks.values()):
                try:
                    b.frame.destroy()
                except tk.TclError:
                    pass
            self.blocks.clear()
            self.images.clear()
            self._insert_items(items, "end-1c")
            self._restyle("1.0", "end")
        finally:
            self._loading = False
            self._ver += 1
            self._snap = None
            self.words_lbl.configure(text="")
        if self.flow:
            self.flow.schedule()

    def add_title(self, title):
        """Put a centred Title line at the top of the note (above the recording's date line)."""
        self._push_undo()
        t = self.text
        t.insert("1.0", title + "\n", ("st:title",))
        self._loaded_title = title
        self._restyle("1.0", "2.0")
        self._mark_changed()
        self._schedule_pages()

    # ------------------------------------------------------------------ files
    def load(self, path):
        if self.path and self.dirty:
            self.save()
        try:
            doc = nd.load_doc(path)
        except Exception as e:
            T.info(self.root, "Nobu Notes", "Could not open that note.\n\n%s" % e)
            return False
        self.hide_action()
        self.ctx = R.Ctx(getattr(self.app, "body_family", self.ctx.body),
                         getattr(self.app, "heading_family", self.ctx.heading), float(self.cfg["font_size"]))
        self._load_items(doc.get("items", []))
        self.meta = {k: v for k, v in doc.items() if k not in ("format", "version", "items")}
        self.path = path
        self._loaded_title = self.title_line()[1]
        self._undo.clear()
        self._redo.clear()
        self.text.edit_modified(False)
        self.dirty = False
        self.text.mark_set("insert", "1.0")
        self.text.yview_moveto(0)
        self._update_header()
        self.text.focus_set()
        self._sync_ribbon()
        self.app.speller.ensure()
        self._spell_all()
        self._schedule_pages()
        return True

    def close(self):
        if self.path and self.dirty:
            self.save()
        self.path = None
        self.meta = {}
        self._load_items([])
        self.text.edit_modified(False)
        self.dirty = False

    def path_changed(self, new_path):
        self.path = new_path
        self._update_header()

    def shutdown(self):
        """This editor is going away (its side-by-side pane or pop-out window closes)."""
        for k in [k for k in vars(self) if k.endswith("_job")]:
            job = getattr(self, k)
            if job:
                try:
                    self.frame.after_cancel(job)
                except Exception:
                    pass
                setattr(self, k, None)

    def save(self):
        if not self.path:
            return
        if self._save_job:
            self.frame.after_cancel(self._save_job)
            self._save_job = None
        try:
            nd.save_doc(self.path, self.serialize())
            self.text.edit_modified(False)
            self.dirty = False
            self._update_header()
        except Exception as e:
            log.exception("save failed")
            self.app.set_status("SAVE FAILED: %s" % e)

    def _on_modified(self, ev=None):
        if self.flow and self.flow.flowing:            # (text flowing round a picture is not an edit)
            return
        if self.text.edit_modified() and self.path and not self._loading:
            self._mark_changed()
            self.text.edit_modified(False)

    def _mark_changed(self):
        if not self.path or self._loading:
            return
        self._ver += 1
        if self._idle_job:
            self.frame.after_cancel(self._idle_job)
        self._idle_job = T.later(self.frame, 900, self._idle_work)
        was = self.dirty
        self.dirty = True
        if not was:
            self._update_header()
        if self._save_job:
            self.frame.after_cancel(self._save_job)
        self._save_job = T.later(self.frame, 3000, self._autosave)
        self._schedule_pages()
        if self.flow and (self.flow.names() or self.text.tag_ranges("softnl")):
            self.flow.edited(self.text.index("insert"))    # the text round floating pictures, right away

    def _idle_work(self):
        """While you pause: refresh the word count and keep a fresh copy of the note for undo/save."""
        self._idle_job = None
        if not self.path:
            return
        self._items_now()
        self._count_words()
        self._check_title()

    # ------------------------------------------------------------------ the title line <-> the note's name
    def title_line(self):
        """(start index, text) of the note's title: the first Title-style paragraph near the top."""
        t = self.text
        r = t.tag_nextrange("st:title", "1.0", "6.0")
        if not r:
            return None, None
        line = t.index(r[0] + " linestart")
        return line, t.get(line, line + " lineend").strip()

    def _check_title(self):
        """You edited the title on the page: rename the note to match (sidebar, lists, file)."""
        _line, txt = self.title_line()
        if txt is None or txt == self._loaded_title:
            return
        self._loaded_title = txt
        if txt and not lib.same_title(txt, self.path):
            self.app.title_edited(txt, self)

    def replace_title(self, old, new):
        """The note was renamed from outside: update the title on the page if it showed the old name."""
        line, txt = self.title_line()
        if line is None or txt != old:
            return
        t = self.text
        a = t.index(line + " linestart")
        b = t.index(line + " lineend")
        lead = len(t.get(a, b)) - len(t.get(a, b).lstrip())
        tags = [g for g in t.tag_names("%s+%dc" % (a, lead)) if R.persistent(g)]
        t.delete("%s+%dc" % (a, lead), b)
        t.insert("%s+%dc" % (a, lead), new, tuple(tags))
        self._restyle(a, a)
        self._loaded_title = new
        self._mark_changed()

    def _autosave(self):
        self._save_job = None
        if self.dirty:
            self.save()

    def _update_header(self, refit=True):
        if not self.path:
            return
        folder = os.path.dirname(self.path)
        inbox = lib.is_inbox(folder)
        self.where.config(text=("✉  Unassigned" if inbox else "▪  " + lib.crumbs(folder)))
        self.title.config(text=("• " if self.dirty else "") + lib.title(self.path))
        if refit and self.head.winfo_width() > 1:
            self._fit_head(self.head.winfo_width())      # a long title gets the room it needs
        if self.on_header:
            self.on_header()
        if inbox and not self._compact and not self._rib_compact:
            # (side-by-side pages: no banner, so the pages line up - the ✉ in the header says it)
            if not self.banner.winfo_ismapped():
                self.banner.pack(side="top", fill="x", padx=16, pady=(0, 2), before=self.rib_box)
        else:
            self.banner.pack_forget()

    def set_fonts(self, body, heading, size):
        self.ctx = R.Ctx(body, heading, float(size))
        if self.path:
            items = self.serialize()["items"]
            ins = self.text.index("insert")
            self._load_items(items)
            self.text.mark_set("insert", ins)

    # ------------------------------------------------------------------ word count & find/replace
    def word_count_dialog(self):
        t = self.text
        s = self._sel()
        txt = t.get(*s) if s else t.get("1.0", "end-1c")
        words = len(re.findall(r"\b[\w'’-]+\b", txt))
        paras = len([p for p in txt.split("\n") if p.strip()])
        T.info(self.root, "Word count", "%s\n\nPages\t\t%d\nWords\t\t%s\nCharacters (no spaces)\t%s\n"
               "Characters (with spaces)\t%s\nParagraphs\t\t%s" % (
                   "Selection" if s else "Whole note", len(self.page_marks) + 1, format(words, ","),
                   format(len(re.sub(r"\s", "", txt)), ","), format(len(txt), ","), format(paras, ",")))

    def find_replace_dialog(self):
        try:
            picked = self.text.get("sel.first", "sel.last")[:80]
        except tk.TclError:
            picked = ""
        if self._fr is not None and self._fr.winfo_exists():
            if picked and "\n" not in picked:
                self._fr_find.set(picked)          # Ctrl+F again with new words selected: look for those
            self._fr.lift()
            self._fr_entry.focus_set()
            self._fr_entry.select_range(0, "end")
            return
        w = self._fr = T.toplevel(self.root, "Find & replace")
        f = ttk.Frame(w, padding=14)
        f.pack(fill="both", expand=True)
        fv, rv = tk.StringVar(), tk.StringVar()
        self._fr_find = fv
        if "\n" not in picked:
            fv.set(picked)
        case, whole = tk.BooleanVar(), tk.BooleanVar()
        ttk.Label(f, text="Find").grid(row=0, column=0, sticky="w")
        fe = ttk.Entry(f, textvariable=fv, width=36)
        fe.grid(row=0, column=1, pady=3)
        ttk.Label(f, text="Replace with").grid(row=1, column=0, sticky="w")
        re_ = ttk.Entry(f, textvariable=rv, width=36)
        re_.grid(row=1, column=1, pady=3)
        self._fr_entry = fe
        ttk.Checkbutton(f, text="Match case", variable=case).grid(row=2, column=1, sticky="w")
        ttk.Checkbutton(f, text="Whole words only", variable=whole).grid(row=3, column=1, sticky="w")
        msg = ttk.Label(f, text="", style="Muted.TLabel")
        msg.grid(row=5, column=0, columnspan=2, sticky="w")

        def pattern():
            q = fv.get()
            if not q:
                return None
            p = re.escape(q)
            return r"\m%s\M" % p if whole.get() else p

        def find(start="insert"):
            p = pattern()
            if not p:
                return None
            t = self.text
            cnt = tk.IntVar()
            pos = t.search(p, start, stopindex="end", regexp=True, nocase=not case.get(), count=cnt)
            wrapped = not pos
            if wrapped:                       # carry on from the top
                pos = t.search(p, "1.0", stopindex="end", regexp=True, nocase=not case.get(), count=cnt)
            t.tag_remove("found", "1.0", "end")
            if not pos:
                msg.config(text="Not found.")
                return None
            end = "%s+%dc" % (pos, cnt.get())
            t.tag_remove("sel", "1.0", "end")
            t.tag_add("sel", pos, end)
            t.tag_add("found", pos, end)
            t.mark_set("insert", end)
            t.see(pos)
            msg.config(text="Reached the end - continued from the top." if wrapped and start != "1.0" else "")
            return pos, end

        def replace():
            s = self._sel()
            if s and self.text.tag_ranges("found"):
                self._push_undo()
                tags = self.text.tag_names(s[0])
                self.text.delete(*s)
                self.text.insert(s[0], rv.get(), tuple(x for x in tags if x not in ("sel", "found", "sp_err")))
                self._restyle(s[0], s[0])
                self._mark_changed()
            find()

        def replace_all():
            p = pattern()
            if not p:
                return
            t = self.text
            if not t.search(p, "1.0", stopindex="end", regexp=True, nocase=not case.get()):
                msg.config(text="Not found.")
                return
            self._push_undo()
            n = 0
            pos = "1.0"
            cnt = tk.IntVar()
            while True:
                pos = t.search(p, pos, stopindex="end", regexp=True, nocase=not case.get(), count=cnt)
                if not pos or cnt.get() == 0:
                    break
                end = "%s+%dc" % (pos, cnt.get())
                tags = t.tag_names(pos)
                t.delete(pos, end)
                t.insert(pos, rv.get(), tuple(x for x in tags if x not in ("sel", "found", "sp_err")))
                pos = "%s+%dc" % (pos, len(rv.get()))
                n += 1
                if n > 100000:
                    break
            self._restyle("1.0", "end")
            self._mark_changed()
            msg.config(text="Replaced %d." % n)

        b = ttk.Frame(f)
        b.grid(row=4, column=0, columnspan=2, pady=(10, 4), sticky="e")
        ttk.Button(b, text="Find next", style="Accent.TButton", command=find).pack(side="left", padx=3)
        ttk.Button(b, text="Replace", command=replace).pack(side="left", padx=3)
        ttk.Button(b, text="Replace all", command=replace_all).pack(side="left", padx=3)
        def close(_e=None):
            self.text.tag_remove("found", "1.0", "end")
            w.destroy()
        ttk.Button(b, text="Close", command=close).pack(side="left", padx=3)
        w.protocol("WM_DELETE_WINDOW", close)
        w.bind("<Escape>", close)
        fe.bind("<Return>", lambda e: find())
        re_.bind("<Return>", lambda e: replace())
        fe.focus_set()
        fe.select_range(0, "end")
        T.fit(w)

    # ------------------------------------------------------------------ drag & drop
    def _setup_dnd(self):
        try:
            from tkinterdnd2 import DND_FILES
            self.text.drop_target_register(DND_FILES)
            self.text.dnd_bind("<<DropEnter>>", self._drop_over)
            self.text.dnd_bind("<<DropPosition>>", self._drop_over)
            self.text.dnd_bind("<<DropLeave>>", lambda ev: self._drop_hint_off())
            self.text.dnd_bind("<<Drop>>", self._on_drop)
        except Exception:
            log.info("drag-and-drop not available; use the Picture button")

    def drop_hint_text(self, files):
        """What happens to files from Windows Explorer let go on this page."""
        pics = [f for f in files if f.lower().endswith(IMG_EXTS)]
        docs = [f for f in files if not f.lower().endswith(IMG_EXTS)]
        lines = []
        if pics or not files:
            lines.append("→  Picture%s go%s in the text at the blue line" % (("s", "") if len(pics) > 1 else ("", "es")))
        if docs or not files:
            folder = os.path.dirname(self.path) if self.path else None
            if folder:
                lines.append("→  Documents are imported as notes into:  %s" % (
                    "Unassigned" if lib.is_inbox(folder) else "“%s”" % lib.crumbs(folder)))
            elif docs:
                lines.append("✕  Documents can't go here (this note isn't saved in a folder)")
        return "\n".join(lines)

    def _drop_over(self, ev):
        from nobu_dragdrop import ExplorerHint, explorer_files
        t = self.text
        try:
            idx = t.index("@%d,%d" % (ev.x_root - t.winfo_rootx(), ev.y_root - t.winfo_rooty()))
            bb = t.bbox(idx)
            if self._drop_caret is None:
                self._drop_caret = tk.Frame(t, width=3, bg=T.ACCENT)
                self._drop_hint = ExplorerHint(self.root)
            if bb:
                self._drop_caret.place(x=bb[0] - 1, y=bb[1], width=3, height=max(bb[3], 12))
                self._drop_caret.lift()
            self._drop_hint.show(self.drop_hint_text(explorer_files(ev, self.root)), ev.x_root, ev.y_root)
        except tk.TclError:
            pass
        return ev.action

    def _drop_hint_off(self):
        if self._drop_caret is not None:
            self._drop_caret.place_forget()
            self._drop_hint.hide()

    def _on_drop(self, ev):
        self._drop_hint_off()
        try:
            files = self.root.tk.splitlist(ev.data)
            x = ev.x_root - self.text.winfo_rootx()
            y = ev.y_root - self.text.winfo_rooty()
            idx = self.text.index("@%d,%d" % (x, y))
            docs = [f for f in files if not f.lower().endswith(IMG_EXTS)]
            for fp in files:
                if fp.lower().endswith(IMG_EXTS):
                    self.insert_image_file(fp, idx)
                    idx = self.text.index("%s+1c" % idx)
            if docs and self.path:
                self.app.import_files(docs, os.path.dirname(self.path))
        except Exception:
            log.exception("drop failed")
        return "copy"

    # ------------------------------------------------------------------ voice editing (dictation / cut)
    def _show_action(self, text, buttons=()):
        for w in self.action_btns.winfo_children():
            w.destroy()
        self.action_lbl.config(text=text)
        for label, cmd, danger in buttons:
            b = tk.Button(self.action_btns, text=label, command=cmd, relief="flat", bd=0, padx=12, pady=3,
                          bg="#b23a3a" if danger else T.PANEL, fg="white" if danger else T.FG, activebackground="#c84848",
                          activeforeground="white", font=T.UI_BOLD if danger else T.UI_FONT, cursor="hand2")
            b.pack(side="left", padx=4)
        if not self.action.winfo_ismapped():
            self.action.pack(side="top", fill="x", padx=16, pady=(0, 2), before=self.rib_box)

    def hide_action(self):
        self.action.pack_forget()

    def begin_dictation(self):
        t = self.text
        s = self._sel()
        a, b = s if s else (t.index("insert"), t.index("insert"))
        t.mark_set("nobu_da", a)
        t.mark_gravity("nobu_da", "left")
        t.mark_set("nobu_db", b)
        t.mark_gravity("nobu_db", "right")
        t.tag_remove("dictspot", "1.0", "end")
        if a != b:
            t.tag_add("dictspot", a, b)
        self._show_action("●  Dictating%s…  Pause, or say “Nobu, end recording”, to finish."
                          % (" (will replace the highlighted text)" if a != b else " at the cursor"),
                          [("Stop   (Nobu, end recording)", lambda: self.app.stop_manual_record(), False)])

    def dictation_waiting(self):
        self._show_action("Transcribing your dictation…", [])

    def insert_dictation(self, note_path, paragraphs):
        text = " ".join(p for p in paragraphs if p).strip()
        same = self.path and os.path.normcase(self.path) == os.path.normcase(note_path or "")
        if text and same and self.cfg.get("confirm_edit") and "nobu_da" in self.text.mark_names():
            shown = text if len(text) <= 220 else text[:220] + "\u2026"
            self._show_action("Dictated: \u201c%s\u201d \u2014 insert it?" % shown, [
                ("Insert", lambda: self._insert_dictation_now(note_path, paragraphs), False),
                ("Discard", self._discard_dictation, True)])
            return
        self._insert_dictation_now(note_path, paragraphs)

    def _discard_dictation(self):
        t = self.text
        t.tag_remove("dictspot", "1.0", "end")
        for m in ("nobu_da", "nobu_db"):
            if m in t.mark_names():
                t.mark_unset(m)
        self.hide_action()
        self.app.set_status("Dictation discarded.")

    def _insert_dictation_now(self, note_path, paragraphs):
        t = self.text
        text = "\n".join(p for p in paragraphs if p)
        self.hide_action()
        t.tag_remove("dictspot", "1.0", "end")
        same = self.path and os.path.normcase(self.path) == os.path.normcase(note_path or "")
        if not text:
            self.app.set_status("Dictation: no words were recognised.")
            return
        if not same or "nobu_da" not in t.mark_names():
            nd.append_items_to_file(note_path, [{"t": text + "\n", "g": []}])
            self.app.set_status("Dictation added to the end of “%s”." % lib.title(note_path))
            return
        self._push_undo()
        a, b = t.index("nobu_da"), t.index("nobu_db")
        if t.compare(a, "<", b):
            t.delete(a, b)
        before = t.get(a + "-1c", a) if t.compare(a, ">", "1.0") else "\n"
        after = t.get(a, a + "+1c")
        if before not in (" ", "\n", "\t", "(", "\"", "“"):
            text = " " + text
        if after and after not in (" ", "\n", ".", ",", ";", ":", "!", "?", ")", "\"", "”"):
            text = text + " "
        t.insert(a, text, self._typing_tags(a))
        end = t.index("%s+%dc" % (a, len(text)))
        t.mark_set("insert", end)
        t.see(end)
        t.tag_add("justadded", a, end)
        self._added_job = T.later(t, 2500, lambda: t.tag_remove("justadded", "1.0", "end"))
        t.mark_unset("nobu_da", "nobu_db")
        self._finish_insert(a, end)
        self.app.set_status("Dictation inserted.")

    def _offset_index(self):
        segs, off = [], 0
        for _key, val, ix in self.text.dump("1.0", "end-1c", text=True):
            segs.append((off, ix, len(val)))
            off += len(val)

        def conv(o):
            lo, hi = 0, len(segs) - 1
            while lo < hi:
                mid = (lo + hi + 1) // 2
                if segs[mid][0] <= o:
                    lo = mid
                else:
                    hi = mid - 1
            start, ix, _n = segs[lo]
            return self.text.index("%s+%dc" % (ix, o - start))
        return conv if segs else (lambda o: "1.0")

    def find_passage(self, spoken):
        full = self.text.get("1.0", "end-1c")
        words = []
        for m in re.finditer(r"\S+", full):
            n = re.sub(r"[^a-z0-9]", "", m.group(0).lower())
            if n:
                words.append((m.start(), m.end(), n))
        r = [x for x in (re.sub(r"[^a-z0-9]", "", w.lower()) for w in spoken.split()) if x]
        if not r or not words:
            return None
        nw = [w[2] for w in words]
        m = len(r)
        sm = difflib.SequenceMatcher(None, nw, r, autojunk=False)
        votes = {}
        for blk in sm.get_matching_blocks():
            if blk.size:
                c = max(0, blk.a - blk.b)
                votes[c] = votes.get(c, 0) + blk.size
        for i, w in enumerate(nw):
            if w == r[0]:
                votes[i] = votes.get(i, 0) + 1
            if w == r[-1]:
                votes[max(0, i - m + 1)] = votes.get(max(0, i - m + 1), 0) + 1
        cands = sorted(votes, key=lambda c: -votes[c])[:8]
        rj = " ".join(r)
        best = (0.0, None)
        lo_len, hi_len = max(1, int(m * 0.7)), int(m * 1.3) + 2
        for c in cands:
            for ds in range(-3, 4):
                s0 = c + ds
                if s0 < 0 or s0 >= len(nw):
                    continue
                for L in range(lo_len, hi_len):
                    e0 = s0 + L
                    if e0 > len(nw):
                        break
                    sc = difflib.SequenceMatcher(None, " ".join(nw[s0:e0]), rj).ratio()
                    if sc > best[0]:
                        best = (sc, (s0, e0))
        if not best[1] or best[0] < 0.55:
            return None
        s0, e0 = best[1]
        a_off, b_off = words[s0][0], words[e0 - 1][1]
        if b_off < len(full) and full[b_off] == " ":
            b_off += 1
        conv = self._offset_index()
        return conv(a_off), conv(b_off), best[0]

    def propose_cut(self, note_path, spoken):
        t = self.text
        t.tag_remove("cutmatch", "1.0", "end")
        same = self.path and os.path.normcase(self.path) == os.path.normcase(note_path or "")
        if not same:
            self.app.set_status("Cut cancelled: the note was closed before Nobu finished listening.")
            return
        if not spoken.strip():
            self._show_action("Cut: no words were recognised. Try again and recite a few words of the passage.",
                              [("OK", self.hide_action, False)])
            return
        res = self.find_passage(spoken)
        if not res:
            self._show_action("Couldn't find a passage matching: “%s”" % spoken[:200],
                              [("OK", self.hide_action, False)])
            return
        a, b, score = res
        t.mark_set("nobu_ca", a)
        t.mark_set("nobu_cb", b)
        t.tag_add("cutmatch", a, b)
        t.see(a)
        if not self.cfg.get("confirm_cut", True):      # Settings: delete straight away (Ctrl+Z undoes)
            self._cut_job = T.later(self.frame, 350, self._do_cut)
            return
        self._show_action("Delete the highlighted passage?%s" % ("" if score > 0.8 else "  (closest match I found)"),
                          [("Delete", self._do_cut, True), ("Cancel", self._cancel_cut, False)])
        self.root.bind("<Escape>", lambda e: self._cancel_cut())

    def _do_cut(self):
        t = self.text
        try:
            a, b = t.index("nobu_ca"), t.index("nobu_cb")
        except tk.TclError:
            return self._cancel_cut()
        self._push_undo()
        t.delete(a, b)
        while t.compare(a, ">", "1.0") and t.get(a + "-1c", a) == " " and t.get(a, a + "+1c") in ("\n", ""):
            a = t.index(a + "-1c")
            t.delete(a, a + "+1c")
        if t.get(a + "-1c", a) == " " and t.get(a, a + "+1c") == " ":
            t.delete(a, a + "+1c")
        t.tag_remove("cutmatch", "1.0", "end")
        self.hide_action()
        self.root.unbind("<Escape>")
        self._after_join()
        self._mark_changed()
        self.app.set_status("Passage deleted. Press Ctrl+Z to bring it back.")

    def _cancel_cut(self):
        self.text.tag_remove("cutmatch", "1.0", "end")
        self.hide_action()
        self.root.unbind("<Escape>")

    def apply_dictionary(self, entries):
        import nobu_dictionary
        if not self.path or not entries:
            return 0
        self._push_undo()
        t = self.text
        segs = [(val, ix) for key, val, ix in t.dump("1.0", "end-1c", text=True)]
        changes = 0
        for val, ix in reversed(segs):
            new = nobu_dictionary.apply(val, entries)
            if new != val:
                tags = t.tag_names(ix)
                end = t.index("%s+%dc" % (ix, len(val)))
                t.delete(ix, end)
                t.insert(ix, new, tags)
                changes += 1
        if changes:
            self._restyle("1.0", "end")
            self._mark_changed()
        elif self._undo:
            self._undo.pop()                  # nothing changed: no empty undo step
        return changes


def nobu_spell_words(txt):
    import nobu_spell
    return nobu_spell.WORD_RE.finditer(txt)
