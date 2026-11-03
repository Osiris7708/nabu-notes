"""Open notes: tabs, side-by-side pages and pop-out windows.

The page area holds one or more "pages" (panes) next to each other. Each page has a row of tabs -
one per open note - and shows one of them.

  * Opening a note adds a tab to the page you're working in (or brings it forward if it's open).
  * Drag a tab (or a note from the sidebar / a folder list)
      - onto the LEFT or RIGHT part of a page ... it snaps there as a new page beside it
      - onto the middle of a page / its tabs .... it becomes a tab of that page
      - well away from the Nobu window ......... it opens in its own window
    A soft blue shadow shows where it will land.
  * A pop-out window comes back the same way (drag its name), or drag the window by its title bar
    to the left / right edge of Nobu's page area.
  * The grab bars between pages: drag to resize, double-click to make them even.
  * The note you're in is the "active" one: dictation and voice commands go there.
"""
import logging
import os
import sys
import time
import tkinter as tk
from tkinter import ttk

import nobu_library as lib
import nobu_theme as T

log = logging.getLogger("nobu.workspace")

MAX_PANES = 6
MAX_TABS = 12          # per page; past that, the tab you haven't looked at for longest closes (saved)


def _mouse_down():
    """Is the (primary) mouse button held right now? None where that can't be known."""
    if not sys.platform.startswith("win"):
        return None
    try:
        import ctypes
        u = ctypes.windll.user32
        u.GetAsyncKeyState.restype = ctypes.c_short
        vk = 0x02 if u.GetSystemMetrics(23) else 0x01        # SM_SWAPBUTTON -> right button is primary
        return bool(u.GetAsyncKeyState(vk) & 0x8000)
    except Exception:
        return None


def _same(a, b):
    return bool(a and b) and os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def _rect(w):
    return w.winfo_rootx(), w.winfo_rooty(), w.winfo_width(), w.winfo_height()


def _inside(xr, yr, r, mx=0, my=0):
    return r[0] - mx <= xr < r[0] + r[2] + mx and r[1] - my <= yr < r[1] + r[3] + my


class Pane:
    """One page in the page area: a row of tabs and the note being shown."""

    def __init__(self, ws):
        self.ws = ws
        self.box = tk.Frame(ws.area, bg=T.BG, highlightthickness=0, bd=0)
        self.strip = tk.Frame(self.box, height=3, bg=T.BG)
        self.strip.pack(side="top", fill="x")
        self.tabbar = tk.Frame(self.box, bg=T.BG)
        self.tabbar.pack(side="top", fill="x", padx=(12, 12), pady=(2, 0))
        self.ctl = tk.Frame(self.tabbar, bg=T.BG)
        self.ctl.pack(side="right")
        self.tabs_fr = tk.Frame(self.tabbar, bg=T.BG)
        self.tabs_fr.pack(side="left", fill="x", expand=True)
        self.tabs_fr.bind("<Configure>", lambda e: ws._label_tabs(self))
        self.line = tk.Frame(self.box, height=1, bg=T.BORDER)
        self.line.pack(side="top", fill="x", padx=12)
        self.body = tk.Frame(self.box, bg=T.BG)
        self.body.pack(side="top", fill="both", expand=True)
        self.eds = []            # the notes open in this page (its tabs), left to right
        self.cur = None          # the one being shown
        self.tabw = {}           # editor -> (frame, label, close mark, top line)
        self.used = {}           # editor -> last time shown


class PopOut:
    def __init__(self, ws, geom=None):
        from nobu_editor import NoteEditor
        self.ws = ws
        root = ws.root
        w = self.win = tk.Toplevel(root, bg=T.BG)
        try:
            w.iconphoto(False, root._nobu_icon)  # noqa
        except Exception:
            pass
        T.dark_titlebar(w)
        if geom:
            w.geometry(geom)
        self.ed = NoteEditor(w, ws.app, ws.app.cfg)
        self.ed.frame.pack(fill="both", expand=True)
        w.protocol("WM_DELETE_WINDOW", lambda: ws.close_popout(self))
        # dragging this window (by its title bar) to the edge of Nobu's page snaps it back in
        self.geom = None
        self.watch = None
        self.seen_down = False
        self.ignore_until = time.time() + 1.0
        w.bind("<Configure>", lambda e: ws._popout_configure(self, e), add="+")
        # voice commands ("Nobu, edit this") follow the window you're in
        w.bind("<FocusIn>", lambda e: ws.app._update_note_context(), add="+")
        w.bind("<FocusOut>", lambda e: ws.root.after(50, ws.app._update_note_context), add="+")

    def retitle(self):
        try:
            self.win.title((lib.title(self.ed.path) if self.ed.path else "Note") + "  —  Nobu Notes")
        except tk.TclError:
            pass


class Workspace:
    def __init__(self, parent, app):
        self.app = app
        self.root = app.root
        sc = T.ui_scale(self.root)
        self.sc = sc
        self.gw = max(12, int(12 * sc))              # grab bar width (same as the sidebar's)
        self.min_w = int(300 * sc)
        self.margin = int(48 * sc)
        self.frame = ttk.Frame(parent)
        bar = self.bar = tk.Frame(self.frame, bg=T.BG)
        ttk.Button(bar, text="⇤  Join into one page", command=self.close_others).pack(side="right", padx=(4, 16))
        ttk.Button(bar, text="⇔  Even widths", command=self.even).pack(side="right", padx=4)
        self.bar_lbl = tk.Label(bar, text="", bg=T.BG, fg=T.MUTED, font=T.UI_FONT, anchor="w")
        self.bar_lbl.pack(side="left", padx=(18, 0), fill="x", expand=True)
        self.area = tk.Frame(self.frame, bg=T.BG)
        self.area.pack(side="top", fill="both", expand=True)
        self.area.bind("<Configure>", lambda e: self._layout())
        self.panes, self.fracs, self.sashes = [], [], []
        self.popouts = []
        self.active = None
        self.cur_pane = None
        self._snap_win = None
        self._snap_rect = None       # where the shade is now (None = hidden)
        self._snap_look = None       # (colour, strength) the shade window was made with
        self._drag = None
        self._ghost = None
        self._ghost_lbl = None
        self._prev_esc = ""
        # stands in as "the editor" while no note is open anywhere (never shown)
        from nobu_editor import NoteEditor
        self._holder = tk.Frame(self.frame)
        self.blank = NoteEditor(self._holder, app, app.cfg)
        self._activate(None)

    # ------------------------------------------------------------ queries
    def editors(self):
        return [ed for p in self.panes for ed in p.eds] + [po.ed for po in self.popouts]

    def editors_for(self, path):
        return [ed for ed in self.editors() if _same(ed.path, path)]

    def popout_of(self, ed):
        for po in self.popouts:
            if po.ed is ed:
                return po
        return None

    def pane_of(self, ed):
        for p in self.panes:
            if ed in p.eds:
                return p
        return None

    def is_popped(self, ed):
        return self.popout_of(ed) is not None

    def has_open(self):
        return any(p.eds for p in self.panes)

    def save_all(self):
        for ed in self.editors():
            if ed.path and ed.dirty:
                ed.save()

    # ------------------------------------------------------------ activation
    def _activate(self, ed):
        if ed is None:
            ed = self.cur_pane.cur if (self.cur_pane in self.panes and self.cur_pane.cur) else None
        if ed is None:
            for p in self.panes:
                if p.cur:
                    ed = p.cur
                    break
        self.active = ed
        self.app.editor = ed if ed is not None else self.blank
        p = self.pane_of(ed) if ed is not None else None
        if p is not None:
            self.cur_pane = p
        elif self.cur_pane not in self.panes:
            self.cur_pane = self.panes[0] if self.panes else None
        for q in self.panes:
            q.strip.configure(bg=T.ACCENT if (q is self.cur_pane and len(self.panes) > 1) else T.BG)
        try:
            self.app._update_note_context()
        except Exception:
            pass

    def _hook(self, ed):
        """Clicking or typing in a note makes it the active one; its name at the top can be dragged too."""
        def act(_e=None, ed=ed):
            if self.active is not ed:
                self._activate(ed)
        ed.text.bind("<FocusIn>", act, add="+")
        for w in (ed.head, ed.desk, ed.text, ed.ribbon):
            w.bind("<ButtonPress-1>", act, add="+")
        for w in (ed.where, ed.title):
            w.configure(cursor="fleur")
            w.bind("<ButtonPress-1>", lambda e, ed=ed: self._tab_press(e, ed), add="+")
            w.bind("<B1-Motion>", lambda e, ed=ed: self._tab_motion(e, ed), add="+")
            w.bind("<ButtonRelease-1>", lambda e, ed=ed: self._tab_release(e, ed), add="+")
        for seq in ("<Control-w>", "<Control-W>"):            # (W too: Caps Lock on)
            ed.text.bind(seq, lambda e, ed=ed: (self.close_editor(ed), "break")[1])
        ed.text.bind("<Control-Next>", lambda e, ed=ed: (self._cycle(ed, 1), "break")[1])
        ed.text.bind("<Control-Prior>", lambda e, ed=ed: (self._cycle(ed, -1), "break")[1])
        ed.text.bind("<Control-Tab>", lambda e, ed=ed: (self._cycle(ed, 1), "break")[1])
        for seq in ("<Control-Shift-Tab>", "<Control-ISO_Left_Tab>"):
            try:
                ed.text.bind(seq, lambda e, ed=ed: (self._cycle(ed, -1), "break")[1])
            except tk.TclError:
                pass
        ed.on_header = lambda ed=ed: self._header_changed(ed)

    def _header_changed(self, ed):
        po = self.popout_of(ed)
        if po:
            po.retitle()
            return
        p = self.pane_of(ed)
        if p:
            self._label_tabs(p)

    def _cycle(self, ed, d):
        p = self.pane_of(ed)
        if p and len(p.eds) > 1:
            self.show_tab(p, p.eds[(p.eds.index(ed) + d) % len(p.eds)])

    # ------------------------------------------------------------ pages (panes)
    def _add_pane(self, index):
        p = Pane(self)
        n = len(self.panes) + 1
        share = 1.0 / n
        self.fracs = [f * (1 - share) for f in self.fracs]
        index = max(0, min(index, len(self.panes)))
        self.panes.insert(index, p)
        self.fracs.insert(index, share)
        self._pane_controls(p)
        self._rebuild()
        return p

    def _remove_pane(self, pane):
        if pane not in self.panes:
            return
        for ed in list(pane.eds):
            self._drop_tab(pane, ed, close=True)
        i = self.panes.index(pane)
        self.panes.pop(i)
        self.fracs.pop(i)
        tot = sum(self.fracs) or 1.0
        self.fracs = [x / tot for x in self.fracs]
        try:
            pane.box.destroy()
        except tk.TclError:
            pass
        if self.cur_pane is pane:
            self.cur_pane = self.panes[min(i, len(self.panes) - 1)] if self.panes else None
        self._rebuild()
        keep = self.active
        if keep is not None and self.pane_of(keep) is None and not self.is_popped(keep):
            keep = None
        self._activate(keep)

    def _rebuild(self):
        for s in self.sashes:
            s.destroy()
        self.sashes = []
        for i in range(len(self.panes) - 1):
            c = tk.Canvas(self.area, width=self.gw, bg=T.BG, highlightthickness=0, bd=0, cursor="sb_h_double_arrow")
            c.bind("<Configure>", lambda e, c=c: self._draw_sash(c))
            c.bind("<Enter>", lambda e, c=c: self._draw_sash(c, True))
            c.bind("<Leave>", lambda e, c=c: self._draw_sash(c, False))
            c.bind("<B1-Motion>", lambda e, i=i: self._drag_sash(e, i))
            c.bind("<Double-Button-1>", lambda e: self.even())
            self.sashes.append(c)
        for p in self.panes:
            if p.cur is not None:
                self._ribbon_policy(p.cur)
        self._refresh_bar()
        self._layout()

    def _draw_sash(self, c, hot=False):
        try:
            c.delete("all")
            h, w = c.winfo_height(), int(c.cget("width"))
            c.configure(bg=T.HOVER if hot else T.BG)
            c.create_line(w // 2, 0, w // 2, h, fill=T.ACCENT if hot else T.BORDER, width=2 if hot else 1)
            for k in range(-3, 4):
                y = h // 2 + k * max(6, w // 2)
                c.create_oval(w // 2 - 2, y - 2, w // 2 + 2, y + 2, fill=T.ACCENT if hot else T.FAINT, outline="")
        except tk.TclError:
            pass

    def _layout(self):
        W, H = self.area.winfo_width(), self.area.winfo_height()
        if W < 10 or H < 10 or not self.panes:
            return
        n = len(self.panes)
        avail = max(n, W - (n - 1) * self.gw)
        x = 0
        for i, p in enumerate(self.panes):
            w = avail - sum(int(round(f * avail)) for f in self.fracs[:-1]) if i == n - 1 \
                else int(round(self.fracs[i] * avail))
            p.box.place(x=x, y=0, width=max(1, w), height=H)
            x += w
            if i < n - 1:
                self.sashes[i].place(x=x, y=0, width=self.gw, height=H)
                self.area.tk.call("raise", str(self.sashes[i]))
                x += self.gw
        for p in self.panes:
            if p.cur is not None:
                p.cur._check_rib_soon()

    def _drag_sash(self, ev, i):
        W = self.area.winfo_width()
        n = len(self.panes)
        avail = max(1, W - (n - 1) * self.gw)
        x = ev.x_root - self.area.winfo_rootx()
        left_start = sum(self.fracs[:i]) * avail + i * self.gw
        pair = self.fracs[i] + self.fracs[i + 1]
        lo = min(self.min_w / avail, pair / 2)
        new_left = (x - left_start - self.gw / 2.0) / avail
        new_left = max(lo, min(pair - lo, new_left))
        self.fracs[i], self.fracs[i + 1] = new_left, pair - new_left
        self._layout()

    def even(self):
        n = len(self.panes)
        if n:
            self.fracs = [1.0 / n] * n
            self._layout()

    def _refresh_bar(self):
        if len(self.panes) > 1:
            self.bar_lbl.configure(text="%d pages side by side  ·  drag a tab to a page's left / right side to snap "
                                        "it there, or onto its middle to join it" % len(self.panes))
            if not self.bar.winfo_ismapped():
                self.bar.pack(side="top", fill="x", pady=(6, 0), before=self.area)
        else:
            self.bar.pack_forget()

    # ------------------------------------------------------------ tabs
    def _pane_controls(self, p):
        from nobu_editor import _btn

        def add(text, cmd, tip):
            b = _btn(p.ctl, text, cmd, tip=tip, bg=T.BG, font=(T.UI_FAMILY, T.UI_SIZE + 1))
            b.configure(padx=7)
            b.pack(side="left", padx=1)
            return b
        add("☰", lambda: p.cur and self.toggle_ribbon(p.cur), "All tools / fewer tools")
        b = add("⧉", None, "Open another note on a new page beside this one")
        b.configure(command=lambda b=b: p.cur and self.side_menu(b, p.cur))
        add("⇱", lambda: p.cur and self.pop_out(p.cur), "Give this note its own window "
            "(or drag its tab out of Nobu)")

    def toggle_ribbon(self, ed):
        """☰: switch this page between all tools and the compact toolbar."""
        ed._rib_choice = "full" if ed.ribbon_compact() else "compact"
        ed.set_compact_ribbon(ed._rib_choice == "compact")

    def _ribbon_policy(self, ed):
        """Pages side by side get the compact toolbar (style, font, size / bold, italic, underline + "More
        tools"); a single page or its own window gets all tools. ☰ switches between the two."""
        choice = getattr(ed, "_rib_choice", None)
        if choice in ("full", "compact"):
            ed.set_compact_ribbon(choice == "compact")
        else:
            ed.set_compact_ribbon(not self.is_popped(ed) and len(self.panes) > 1)

    def _tab_widget(self, p, ed):
        f = tk.Frame(p.tabs_fr, bg=T.BG, cursor="hand2", highlightthickness=0)
        top = tk.Frame(f, height=2, bg=T.BG)
        top.pack(side="top", fill="x")
        lbl = tk.Label(f, text="", bg=T.BG, fg=T.MUTED, font=T.UI_FONT, padx=10, pady=4, anchor="w", cursor="hand2")
        lbl.pack(side="left")
        x = tk.Label(f, text="✕", bg=T.BG, fg=T.FAINT, font=(T.UI_FAMILY, max(8, T.UI_SIZE - 1)), padx=6,
                     cursor="hand2")
        x.pack(side="left")
        for w in (f, lbl, top):
            w.bind("<ButtonPress-1>", lambda e, ed=ed: self._tab_press(e, ed))
            w.bind("<B1-Motion>", lambda e, ed=ed: self._tab_motion(e, ed))
            w.bind("<ButtonRelease-1>", lambda e, ed=ed: self._tab_release(e, ed))
            w.bind("<Button-2>", lambda e, ed=ed: self.close_editor(ed))
            w.bind("<Button-3>", lambda e, ed=ed: self._tab_menu(e, ed))
            w.bind("<Enter>", lambda e, ed=ed: self._tab_hover(ed, True))
            w.bind("<Leave>", lambda e, ed=ed: self._tab_hover(ed, False))
        x.bind("<Button-1>", lambda e, ed=ed: (self.close_editor(ed), "break")[1])
        x.bind("<Enter>", lambda e, x=x: x.configure(fg=T.FG))
        x.bind("<Leave>", lambda e, x=x: x.configure(fg=T.FAINT))
        p.tabw[ed] = (f, lbl, x, top)
        return f

    def _tab_hover(self, ed, on):
        p = self.pane_of(ed)
        if not p or ed not in p.tabw or ed is p.cur:
            return
        bg = T.HOVER if on else T.BG
        for w in p.tabw[ed]:
            try:
                w.configure(bg=bg)
            except tk.TclError:
                pass

    def _label_tabs(self, p):
        """Tab texts and colours; long names are shortened so every tab fits."""
        if not p.eds:
            return
        try:
            import tkinter.font as tkf
            avg = max(5.0, tkf.Font(font=T.UI_FONT).measure("abcdefghij") / 10.0)
        except Exception:
            avg = 7.0
        width = max(100, p.tabs_fr.winfo_width())
        per = width / float(len(p.eds)) - 44
        chars = int(max(4, min(36, per / avg)))
        for ed in p.eds:
            f, lbl, x, top = p.tabw[ed]
            name = lib.title(ed.path) if ed.path else "(closed)"
            if len(name) > chars:
                name = name[:max(1, chars - 1)] + "…"
            on = ed is p.cur
            bg = T.PANEL if on else T.BG
            try:
                lbl.configure(text=("• " if ed.dirty else "") + name, bg=bg, fg=T.FG if on else T.MUTED)
                f.configure(bg=bg)
                x.configure(bg=bg)
                top.configure(bg=T.ACCENT if on else bg)
            except tk.TclError:
                pass

    def _pack_tabs(self, p):
        for ed in p.eds:
            p.tabw[ed][0].pack_forget()
        for ed in p.eds:
            p.tabw[ed][0].pack(side="left", padx=(0, 2))
        self._label_tabs(p)

    def _new_tab(self, p, index=None):
        """A new, empty editor as a tab of page p."""
        from nobu_editor import NoteEditor
        ed = NoteEditor(p.body, self.app, self.app.cfg)
        self._hook(ed)
        self._tab_widget(p, ed)
        if index is None:
            index = (p.eds.index(p.cur) + 1) if p.cur in p.eds else len(p.eds)
        p.eds.insert(max(0, min(index, len(p.eds))), ed)
        return ed

    def show_tab(self, p, ed):
        if p.cur is not None and p.cur is not ed:
            try:
                p.cur.frame.pack_forget()
            except tk.TclError:
                pass
        p.cur = ed
        p.used[ed] = time.time()
        if not ed.frame.winfo_manager():
            ed.frame.pack(in_=p.body, fill="both", expand=True)
        self._ribbon_policy(ed)
        self._pack_tabs(p)
        self._activate(ed)
        ed._check_rib_soon()
        try:
            if self.root.focus_get() is not None:     # (only when Nobu has the keyboard)
                ed.text.focus_set()                   # typing, Ctrl+W... now go to this tab
        except (tk.TclError, KeyError):
            pass

    def _drop_tab(self, p, ed, close=True):
        """Take a tab off its page (saving the note unless it was already handed over)."""
        if ed not in p.eds:
            return
        if close:
            try:
                ed.close()
            except Exception:
                log.exception("closing a tab")
        ed.shutdown()
        i = p.eds.index(ed)
        p.eds.remove(ed)
        p.used.pop(ed, None)
        w = p.tabw.pop(ed, None)
        if w:
            w[0].destroy()
        try:
            ed.frame.destroy()
        except tk.TclError:
            pass
        if p.cur is ed:
            p.cur = None
            if p.eds:
                self.show_tab(p, p.eds[min(i, len(p.eds) - 1)])
        else:
            self._pack_tabs(p)

    def _trim(self, p):
        while len(p.eds) > MAX_TABS:
            old = min((e for e in p.eds if e is not p.cur), key=lambda e: p.used.get(e, 0))
            self._drop_tab(p, old, close=True)

    def _tab_menu(self, ev, ed):
        p = self.pane_of(ed)
        m = T.menu(self.root)
        m.add_command(label="Close   (Ctrl+W)", command=lambda: self.close_editor(ed))
        if p and len(p.eds) > 1:
            m.add_command(label="Close the other tabs", command=lambda: self.close_other_tabs(ed))
        m.add_separator()
        if p and len(self.panes) < MAX_PANES and (len(p.eds) > 1 or len(self.panes) > 1):
            m.add_command(label="Put on a new page on the right", command=lambda: self.split(ed, self.panes.index(p) + 1))
            m.add_command(label="Put on a new page on the left", command=lambda: self.split(ed, self.panes.index(p)))
        m.add_command(label="Give it its own window", command=lambda: self.pop_out(ed))
        m.add_separator()
        m.add_command(label="Rename…", command=lambda: ed.path and self.app.rename_note(ed.path))
        m.tk_popup(ev.x_root, ev.y_root)

    def close_other_tabs(self, ed):
        p = self.pane_of(ed)
        if not p:
            return
        for e in list(p.eds):
            if e is not ed:
                self._drop_tab(p, e, close=True)
        self.show_tab(p, ed)

    def side_menu(self, widget, ed):
        """Pick a note to open on a new page beside this one: others in the same folder, the rest of the
        same book / campaign, and recent ones."""
        app = self.app
        m = T.menu(self.root)
        open_now = {os.path.normcase(e.path) for e in self.editors() if e.path}
        here, book, top = [], [], None
        if ed.path:
            folder = os.path.dirname(ed.path)
            here = [p for p in lib.notes_in(folder) if os.path.normcase(p) not in open_now][:25]
            top = lib.book_of(folder)
            if top and len(here) < 25:
                book = [p for p in lib.all_notes(top) if os.path.normcase(p) not in open_now and p not in here]
                book = book[:25 - len(here)]
        recent = [p for p in app.recent_notes()
                  if os.path.normcase(p) not in open_now and p not in here and p not in book][:12]
        groups = (("In this folder", here), ("Elsewhere in \u201c%s\u201d" % (lib.folder_name(top) if top else ""), book),
                  ("Recent", recent))
        for title, group in groups:
            if not group:
                continue
            if m.index("end") is not None:
                m.add_separator()
            m.add_command(label=title, state="disabled")
            for p in group:
                m.add_command(label="    " + lib.title(p)[:70], command=lambda p=p: app.open_note(p, side=True, beside=ed))
        if m.index("end") is not None:
            m.add_separator()
        m.add_command(label="Tip: drag any note from the sidebar or a folder list onto the left or right", state="disabled")
        m.add_command(label="part of a page to open it there.", state="disabled")
        m.tk_popup(widget.winfo_rootx(), widget.winfo_rooty() + widget.winfo_height())

    # ------------------------------------------------------------ opening, moving, closing
    def open(self, path, side=False, index=None, beside=None, pane=None, tab_index=None):
        """Show a note. side=True: on a new page (beside the active one, or at `index`).
        pane=...: as a tab of that page. Otherwise: as a new tab of the page you're working in.
        A note that is already open is brought forward (or moved, if a place was asked for)."""
        for ed in self.editors():
            if _same(ed.path, path):
                po = self.popout_of(ed)
                if po:
                    if side or pane is not None:
                        return self.dock(po, index=self._side_index(index, beside) if side else None,
                                         pane=pane, tab_index=tab_index)
                    po.win.deiconify()
                    po.win.lift()
                    self._activate(ed)
                    return ed
                p = self.pane_of(ed)
                if side and len(p.eds) > 1 and len(self.panes) < MAX_PANES:
                    return self.split(ed, self._side_index(index, beside))   # move it to the asked-for place
                if pane is not None and pane in self.panes and pane is not p:
                    return self.move_tab(ed, pane, tab_index)
                self.show_tab(p, ed)
                return ed
        if side and self.has_open() and len(self.panes) < MAX_PANES:
            p = self._add_pane(self._side_index(index, beside))
            ed = self._new_tab(p)
            if not ed.load(path):
                self._drop_tab(p, ed, close=False)
                self._remove_pane(p)
                return None
            self.show_tab(p, ed)
            return ed
        if side and self.has_open():
            self.app.set_status("Up to %d pages fit side by side - it opened as a tab instead." % MAX_PANES)
        p = pane if pane in self.panes else (self.cur_pane if self.cur_pane in self.panes else None)
        if p is None:
            p = self.panes[0] if self.panes else self._add_pane(0)
        ed = self._new_tab(p, tab_index)
        if not ed.load(path):
            self._drop_tab(p, ed, close=False)
            if not p.eds and len(self.panes) > 1:
                self._remove_pane(p)
            return None
        self.show_tab(p, ed)
        self._trim(p)
        return ed

    def _side_index(self, index, beside=None):
        if index is not None:
            return index
        ref = self.pane_of(beside) if beside is not None else self.cur_pane
        return (self.panes.index(ref) + 1) if ref in self.panes else len(self.panes)

    @staticmethod
    def _transfer(src, dst):
        """Move an open note into another editor, keeping its place and its undo history."""
        if src.dirty:
            src.save()
        path = src.path
        ins = src.text.index("insert")
        top = src.text.yview()[0]
        undo, redo = list(src._undo), list(src._redo)
        rib = getattr(src, "_rib_choice", None)
        src.close()
        if not dst.load(path):
            return False
        dst._undo[:] = undo
        dst._redo[:] = redo
        dst._rib_choice = rib
        try:
            dst.text.mark_set("insert", ins)
        except tk.TclError:
            pass
        T.later(dst.text, 60, dst.text.yview_moveto, top)
        return True

    def _busy(self, ed):
        app = self.app
        if app.state == "recording" and getattr(app, "cmd_editor", None) is ed:
            app.set_status("Finish dictating first (say “Nobu, end recording” or press Stop).")
            return True
        return False

    def move_tab(self, ed, dst, index=None):
        """Put an open note (a tab, or a pop-out window) into page dst, as a tab at `index`."""
        if self._busy(ed):
            return ed
        src = self.pane_of(ed)
        if src is dst:                                     # just a new place in the same row of tabs
            if index is not None:
                i = dst.eds.index(ed)
                dst.eds.remove(ed)
                if index > i:
                    index -= 1
                dst.eds.insert(max(0, min(index, len(dst.eds))), ed)
            self.show_tab(dst, ed)
            return ed
        new = self._new_tab(dst, index if index is not None else len(dst.eds))
        if not self._transfer(ed, new):
            self._drop_tab(dst, new, close=False)
            return None
        po = self.popout_of(ed)
        if po:
            self._discard_popout(po)
        elif src is not None:
            self._drop_tab(src, ed, close=False)
            if not src.eds:
                self._remove_pane(src)
        self.show_tab(dst, new)
        self._trim(dst)
        return new

    def split(self, ed, index):
        """Put an open note on a new page at position `index` (0 = far left)."""
        src = self.pane_of(ed)
        if src is not None and len(src.eds) == 1 and len(self.panes) == 1:
            return ed                                       # it's already the only page
        if len(self.panes) >= MAX_PANES:
            self.app.set_status("Up to %d pages fit side by side." % MAX_PANES)
            return ed
        p = self._add_pane(index)
        new = self.move_tab(ed, p)
        if not p.eds:
            self._remove_pane(p)
        return new

    def close_editor(self, ed):
        """Close a note wherever it is (tab or its own window); it is saved first."""
        po = self.popout_of(ed)
        if po:
            self.close_popout(po)
            return
        p = self.pane_of(ed)
        if not p:
            return
        folder = os.path.dirname(ed.path) if ed.path else None
        self._drop_tab(p, ed, close=True)
        if not p.eds:
            if len(self.panes) > 1:
                self._remove_pane(p)
            else:
                self._activate(None)
                self.app.workspace_emptied(folder)
        else:
            self._activate(p.cur if self.active is ed or self.active is None else self.active)

    def close_others(self):
        """Join every page into the one you're working in (as tabs)."""
        keep = self.cur_pane if self.cur_pane in self.panes else (self.panes[0] if self.panes else None)
        if keep is None:
            return
        for p in list(self.panes):
            if p is not keep:
                for ed in list(p.eds):
                    self.move_tab(ed, keep)
        for p in list(self.panes):
            if p is not keep and not p.eds:
                self._remove_pane(p)
        for ed in keep.eds:
            ed._rib_choice = None
        if keep.cur:
            self.show_tab(keep, keep.cur)

    # ------------------------------------------------------------ pop-out windows
    def pop_out(self, ed, x=None, y=None):
        if ed is None or not ed.path or self.is_popped(ed) or self._busy(ed):
            return None
        p = self.pane_of(ed)
        sc = self.sc
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        base = p.box if p else self.area
        w = max(int(700 * sc), min(base.winfo_width() + 40, int(1000 * sc)))
        h = min(sh - 80, max(int(700 * sc), self.area.winfo_height() + 60))
        w = min(w, sw - 20)
        if x is None:
            x, y = base.winfo_rootx() + 60, max(0, base.winfo_rooty() - 20)
        else:
            x, y = x - w // 3, y - 20
        x = max(0, min(x, sw - w))
        y = max(0, min(y, sh - h - 40))
        po = PopOut(self, "%dx%d+%d+%d" % (w, h, x, y))
        self.popouts.append(po)
        self._hook(po.ed)
        if not self._transfer(ed, po.ed):
            self.close_popout(po)
            return None
        po.retitle()
        self._popout_controls(po)
        self._ribbon_policy(po.ed)
        if p is not None:
            folder = os.path.dirname(po.ed.path)
            self._drop_tab(p, ed, close=False)
            if not p.eds:
                if len(self.panes) > 1:
                    self._remove_pane(p)
                else:
                    self.app.workspace_emptied(folder)
        self._activate(po.ed)
        po.win.lift()
        po.ed.text.focus_set()
        self.app.set_status("“%s” has its own window now. Drag its name back onto Nobu's page (or press ⇲) "
                            "to put it back." % lib.title(po.ed.path))
        return po.ed

    def open_popout(self, path, x=None, y=None):
        """Open a note straight into its own window (dragged out of the sidebar or a list)."""
        for ed in self.editors_for(path):
            if self.is_popped(ed):
                self.popout_of(ed).win.lift()
                return ed
            return self.pop_out(ed, x, y) or ed
        was = self.app.view
        ed = self.open(path)
        if ed is None:
            return None
        new = self.pop_out(ed, x, y) or ed
        if was is not self.frame and self.app.view is self.frame and not self.has_open():
            self.app._show(was)
        return new

    def _popout_controls(self, po):
        from nobu_editor import _btn
        box = po.ed.pane_btns
        for w in box.winfo_children():
            w.destroy()

        def add(text, cmd, tip):
            b = _btn(box, text, cmd, tip=tip, bg=T.BG, font=(T.UI_FAMILY, T.UI_SIZE + 1))
            b.configure(padx=7)
            b.pack(side="left", padx=1)
            return b
        add("☰", lambda: self.toggle_ribbon(po.ed), "All tools / fewer tools")
        add("⇲", lambda: self.dock(po), "Put this note back into Nobu's main window (as a tab)")

    def _discard_popout(self, po):
        po.ed.shutdown()
        if po in self.popouts:
            self.popouts.remove(po)
        try:
            po.win.destroy()
        except tk.TclError:
            pass

    def close_popout(self, po):
        if po not in self.popouts:
            return
        try:
            po.ed.close()
        except Exception:
            log.exception("closing pop-out")
        self._discard_popout(po)
        if self.active is po.ed:
            self._activate(None)

    def dock(self, po, index=None, pane=None, tab_index=None):
        """Bring a pop-out back: on a new page at `index`, or as a tab of `pane` (default: the page you're
        working in)."""
        if po not in self.popouts or self._busy(po.ed):
            return None
        path = po.ed.path
        if index is not None and self.has_open() and len(self.panes) < MAX_PANES:
            dst = self._add_pane(index)
        else:
            dst = pane if pane in self.panes else (self.cur_pane if self.cur_pane in self.panes else None)
            if dst is None:
                dst = self.panes[0] if self.panes else self._add_pane(0)
        new = self.move_tab(po.ed, dst, tab_index)
        if not dst.eds:
            self._remove_pane(dst)
        self.app.show_workspace(path)
        return new

    # ------------------------------------------------------------ where would a dropped note go?
    def _near_main(self, xr, yr):
        try:
            return _inside(xr, yr, _rect(self.root), self.margin, self.margin)
        except tk.TclError:
            return False

    def _pane_at(self, xr, yr):
        for p in self.panes:
            if _inside(xr, yr, _rect(p.box)):
                return p
        return None

    def target(self, xr, yr, src=None):
        """Where a note dragged to this screen point would go. src = the open note dragged by its tab
        (None for notes dragged from the sidebar or a folder list). Returns a dict with kind:
          out   - its own window              split - a new page at `index` (side left / right)
          tab   - a tab of `pane` at `index`  open  - (a folder list is showing) side left / right / center
        and `rect`, the screen area to shade. None = nothing would happen."""
        if not self._near_main(xr, yr):
            return {"kind": "out", "rect": None}
        popped = src is not None and self.is_popped(src)
        if self.app.view is not self.frame or not self.has_open():
            if src is not None and not popped:
                return None
            try:
                c = _rect(self.app.content)
            except tk.TclError:
                return None
            if not _inside(xr, yr, (c[0], c[1], c[2] + self.margin, c[3])):
                return None
            rel = (xr - c[0]) / float(max(1, c[2]))
            side = "left" if rel < 0.3 else ("right" if rel > 0.7 else "center")
            if not self.has_open():
                side = "center"
            half = c[2] // 2
            rect = {"left": (c[0], c[1], half, c[3]), "right": (c[0] + c[2] - half, c[1], half, c[3]),
                    "center": c}[side]
            return {"kind": "open", "side": side, "rect": rect}
        a = _rect(self.area)
        if not (a[1] - self.margin <= yr <= a[1] + a[3] + self.margin):
            return None
        if xr < a[0]:
            pane, zone = self.panes[0], "left"
        elif xr >= a[0] + a[2]:
            pane, zone = self.panes[-1], "right"
        else:
            pane = self._pane_at(xr, yr)
            if pane is None:                          # on a grab bar: the gap between two pages
                x = xr - a[0]
                i = sum(1 for p in self.panes if x > p.box.winfo_x() + p.box.winfo_width() / 2.0)
                if i >= len(self.panes):
                    pane, zone = self.panes[-1], "right"
                else:
                    pane, zone = self.panes[i], "left"
            else:
                tb = _rect(pane.tabbar)
                b = _rect(pane.box)
                if yr < tb[1] + tb[3] + 4:
                    zone = "tab"
                else:
                    rel = (xr - b[0]) / float(max(1, b[2]))
                    zone = "left" if rel < 0.28 else ("right" if rel > 0.72 else "center")
        sp = self.pane_of(src) if src is not None else None
        b = _rect(pane.box)
        body = _rect(pane.body)
        if zone in ("left", "right"):
            if sp is pane and len(sp.eds) == 1:
                return None                           # it already fills this page
            if len(self.panes) < MAX_PANES:
                half = b[2] // 2
                i = self.panes.index(pane) + (1 if zone == "right" else 0)
                rect = (b[0] if zone == "left" else b[0] + b[2] - half, b[1], half, b[3])
                return {"kind": "split", "index": i, "pane": pane, "rect": rect, "side": zone}
            zone = "center"
        if zone == "tab":
            if sp is pane and len(sp.eds) == 1:
                return None
            idx = len(pane.eds)
            for i, e in enumerate(pane.eds):
                f = pane.tabw[e][0]
                if xr < f.winfo_rootx() + f.winfo_width() / 2.0:
                    idx = i
                    break
            return {"kind": "tab", "pane": pane, "index": idx, "rect": body}
        if sp is pane:
            return None                               # dropped back where it was
        return {"kind": "tab", "pane": pane, "index": None, "rect": body}

    def describe(self, t, name):
        if not t:
            return name
        k = t["kind"]
        if k == "out":
            return "⇱  Own window:  " + name
        if k in ("split", "open") and t.get("side") == "left":
            return "◧  Open on the left:  " + name
        if k in ("split", "open") and t.get("side") == "right":
            return "◨  Open on the right:  " + name
        if k == "open":
            return "→  Open:  " + name
        return "→  Open as a tab here:  " + name

    def drop_notes(self, t, paths, xr=None, yr=None):
        """Notes dragged from the sidebar or a folder list were let go: open them where they landed."""
        notes = [p for p in paths if os.path.isfile(p)][:MAX_TABS]
        if not notes or not t:
            return
        app = self.app
        k = t["kind"]
        if k == "out":
            for i, p in enumerate(notes[:4]):
                self.open_popout(p, (xr or 200) + 30 * i, (yr or 200) + 30 * i)
            return
        if k == "open":
            if t["side"] == "center" or not self.has_open():
                for p in notes:
                    app.open_note(p)
                return
            k, t = "split", dict(t, index=0 if t["side"] == "left" else len(self.panes))
        if k == "split" and len(self.panes) < MAX_PANES:
            first = app.open_note(notes[0], side=True, index=t["index"])
            p = self.pane_of(first) if first is not None else None
            for q in notes[1:]:
                app.open_note(q, pane=p)
            return
        pane = t.get("pane")
        idx = t.get("index")
        for i, q in enumerate(notes):
            app.open_note(q, pane=pane, tab_index=None if idx is None else idx + i)

    # ------------------------------------------------------------ the blue shadow
    def drop_colour(self):
        """(colour, strength) of the shade - Settings > Appearance > My colours > Drop highlight."""
        cfg = self.app.cfg
        col = cfg.get("drop_color") or T.ACCENT
        try:
            alpha = max(0.1, min(0.8, float(cfg.get("drop_alpha") or 0.30)))
        except (TypeError, ValueError):
            alpha = 0.30
        return col, alpha

    def show_drop(self, t, above=None):
        """Shade where a dragged note will land. Only touches the window when the place actually
        changes (moving the mouse within the same spot does nothing), so it never flickers."""
        rect = t.get("rect") if isinstance(t, dict) else t
        if rect is not None:
            rect = tuple(int(v) for v in rect)
        if rect == self._snap_rect:
            return
        self._snap_rect = rect
        if rect is None:
            if self._snap_win is not None:
                try:
                    self._snap_win.withdraw()
                except tk.TclError:
                    self._snap_win = None
            return
        col, alpha = self.drop_colour()
        if self._snap_win is None or self._snap_look != (col, alpha):
            if self._snap_win is not None:
                try:
                    self._snap_win.destroy()
                except tk.TclError:
                    pass
            g = self._snap_win = tk.Toplevel(self.root, bg=col)
            g.withdraw()
            g.overrideredirect(True)
            try:
                g.attributes("-topmost", True)
                g.attributes("-alpha", alpha)
            except tk.TclError:
                pass
            self._snap_look = (col, alpha)
        g = self._snap_win
        x, y, w, h = rect
        g.geometry("%dx%d+%d+%d" % (max(8, w), max(8, h), x, y))
        if g.state() != "normal":
            g.deiconify()
            for top in (self._ghost, above):       # the label under the mouse stays on top of the shade
                if top is not None:
                    try:
                        top.lift()
                    except tk.TclError:
                        pass

    # ------------------------------------------------------------ dragging a pop-out window by its title bar
    def _popout_configure(self, po, e):
        if e.widget is not po.win:
            return
        try:
            g = (po.win.winfo_x(), po.win.winfo_y(), po.win.winfo_width(), po.win.winfo_height())
        except tk.TclError:
            return
        old, po.geom = po.geom, g
        if old is None or time.time() < po.ignore_until:
            return
        if g[2:] != old[2:]:                 # being resized, not moved
            return
        if g[:2] != old[:2] and po.watch is None:
            po.seen_down = False
            po.watch = self.root.after(40, lambda: self._watch_popout(po))

    def _edge_target(self, xr, yr):
        """A pop-out window's pointer at the very left / right edge of the page area."""
        if self.app.view is not self.frame or not self.has_open():
            try:
                c = _rect(self.app.content)
            except tk.TclError:
                return None
        else:
            c = _rect(self.area)
        m = self.margin
        if not (c[1] <= yr <= c[1] + c[3]):
            return None
        half = c[2] // 2
        n = len(self.panes) if self.has_open() else 0
        if c[0] - m <= xr <= c[0] + int(m * 1.5):
            return {"kind": "split" if n else "open", "index": 0, "side": "left", "rect": (c[0], c[1], half, c[3])}
        if c[0] + c[2] - int(m * 1.5) <= xr <= c[0] + c[2] + m:
            return {"kind": "split" if n else "open", "index": n, "side": "right",
                    "rect": (c[0] + c[2] - half, c[1], half, c[3])}
        return None

    def _watch_popout(self, po):
        po.watch = None
        if po not in self.popouts:
            self.show_drop(None)
            return
        down = _mouse_down()
        if down is None:                     # can't tell when the drag ends here: no snapping
            return
        try:
            xr, yr = self.root.winfo_pointerxy()
        except tk.TclError:
            return
        t = self._edge_target(xr, yr)
        if down:
            po.seen_down = True
            self.show_drop(t)
            po.watch = self.root.after(60, lambda: self._watch_popout(po))
            return
        self.show_drop(None)
        if t and po.seen_down:
            self.root.after(10, lambda: self._land_popout(po, t))

    def _land_popout(self, po, t):
        k = t["kind"]
        if k == "split":
            self.dock(po, index=t["index"])
        elif k == "tab":
            self.dock(po, pane=t.get("pane"), tab_index=t.get("index"))
        elif k == "open" and t.get("side") in ("left", "right") and self.has_open():
            self.dock(po, index=0 if t["side"] == "left" else len(self.panes))
        else:
            self.dock(po)

    # ------------------------------------------------------------ dragging a tab (or a note's name)
    def _tab_press(self, ev, ed):
        p = self.pane_of(ed)
        if p is not None and p.cur is not ed:
            self.show_tab(p, ed)
        elif self.active is not ed:
            self._activate(ed)
        self._drag = {"ed": ed, "x": ev.x_root, "y": ev.y_root, "moving": False}

    def _tab_motion(self, ev, ed):
        d = self._drag
        if not d or d["ed"] is not ed or not ed.path:
            return
        if not d["moving"]:
            if abs(ev.x_root - d["x"]) + abs(ev.y_root - d["y"]) < 10:
                return
            d["moving"] = True
            g = self._ghost = tk.Toplevel(self.root)
            g.overrideredirect(True)
            g.attributes("-topmost", True)
            try:
                g.attributes("-alpha", 0.92)
            except tk.TclError:
                pass
            self._ghost_lbl = tk.Label(g, text="", bg=T.ACCENT_DARK, fg="#ffffff", font=T.UI_FONT, padx=10, pady=5)
            self._ghost_lbl.pack()
            self._prev_esc = self.root.bind("<Escape>")
            self.root.bind("<Escape>", self._cancel_tab_drag)
        self._ghost.geometry("+%d+%d" % (ev.x_root + 14, ev.y_root + 12))
        t = self.target(ev.x_root, ev.y_root, ed)
        name = lib.title(ed.path)[:50]
        if t and t["kind"] == "out" and self.is_popped(ed):
            self._ghost_lbl.configure(text="Move window:  " + name)
        else:
            self._ghost_lbl.configure(text=self.describe(t, name))
        self.show_drop(t)

    def _end_tab_drag(self):
        if self._ghost:
            self._ghost.destroy()
            self._ghost = None
            self.root.bind("<Escape>", self._prev_esc or "")
        self.show_drop(None)

    def _cancel_tab_drag(self, _e=None):
        """Esc while dragging a tab: nothing moves."""
        self._drag = None
        self._end_tab_drag()
        self.app.set_status("Drag cancelled.")
        return "break"

    def _tab_release(self, ev, ed):
        d, self._drag = self._drag, None
        self._end_tab_drag()
        if not d or not d["moving"] or d["ed"] is not ed:
            return
        t = self.target(ev.x_root, ev.y_root, ed)
        if not t:
            return
        po = self.popout_of(ed)
        k = t["kind"]
        if k == "out":
            if po:
                try:
                    po.ignore_until = time.time() + 1.0
                    po.win.geometry("+%d+%d" % (max(0, ev.x_root - 120), max(0, ev.y_root - 20)))
                except tk.TclError:
                    pass
            else:
                self.root.after(10, lambda: self.pop_out(ed, ev.x_root, ev.y_root))
            return
        if po:
            self.root.after(10, lambda: self._land_popout(po, t))
            return
        if k == "split":
            self.root.after(10, lambda: self.split(ed, t["index"]))
        elif k == "tab":
            self.root.after(10, lambda: self.move_tab(ed, t["pane"], t["index"]))
