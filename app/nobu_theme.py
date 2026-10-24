"""Colour themes: colours, ttk styling, dark Windows title bars and small dark dialogs."""
import re
import sys
import tkinter as tk
from tkinter import ttk

GREEN = "#43b77a"
RED = "#ef5350"
AMBER = "#e0a33a"

# Colour themes (Settings > Appearance). Keys become module globals via set_theme().
THEMES = {
    "dark": dict(label="Dark (classic)", LIGHT=False,
                 BG="#1e1f22", SIDEBAR="#18191c", PANEL="#26282c", EDITOR="#212226", FIELD="#2c2e33",
                 BORDER="#34363c", FG="#e4e4e7", MUTED="#9a9ca3", FAINT="#6c6f77", ACCENT="#7aa2ff",
                 ACCENT_DARK="#3b5bab", SELECT="#2f4a7a", SELECT_FG="#ffffff", HOVER="#33363c", ALT="#2b2d32",
                 PAPER="#25262a", DESK="#17181b", INK="#e3e3e6", BANNER_BG="#2b2a1f", BANNER_FG="#e8d9a8",
                 ACTION_BG="#3a2326", ACTION_FG="#f3d6d6"),
    "midnight": dict(label="Midnight blue", LIGHT=False,
                     BG="#141a26", SIDEBAR="#0f141e", PANEL="#1b2333", EDITOR="#161d2b", FIELD="#202a3b",
                     BORDER="#2b3548", FG="#e2e8f4", MUTED="#94a1ba", FAINT="#5f6b83", ACCENT="#79b0ff",
                     ACCENT_DARK="#2f5ca8", SELECT="#28497f", SELECT_FG="#ffffff", HOVER="#26324a", ALT="#1f2839",
                     PAPER="#1a2232", DESK="#0b0f17", INK="#e4eaf6", BANNER_BG="#1f2a1c", BANNER_FG="#d9e8b8",
                     ACTION_BG="#3a2030", ACTION_FG="#f3d6e0"),
    "ember": dict(label="Ember (warm dark)", LIGHT=False,
                  BG="#1f1a16", SIDEBAR="#181410", PANEL="#2a231d", EDITOR="#221c17", FIELD="#322a23",
                  BORDER="#40362c", FG="#f0e6d8", MUTED="#b5a591", FAINT="#7f705d", ACCENT="#e8a75c",
                  ACCENT_DARK="#9a5f22", SELECT="#6b4520", SELECT_FG="#ffffff", HOVER="#3a3027", ALT="#2f2720",
                  PAPER="#2a221c", DESK="#120f0c", INK="#f2e8da", BANNER_BG="#33291a", BANNER_FG="#f0d9a0",
                  ACTION_BG="#40201c", ACTION_FG="#f8d8d0"),
    "forest": dict(label="Forest", LIGHT=False,
                   BG="#161d19", SIDEBAR="#111713", PANEL="#1e2822", EDITOR="#19221d", FIELD="#233029",
                   BORDER="#2f3d34", FG="#e1ece4", MUTED="#98ab9e", FAINT="#647a6b", ACCENT="#7fd19b",
                   ACCENT_DARK="#2f7a4c", SELECT="#285c3e", SELECT_FG="#ffffff", HOVER="#2a3830", ALT="#1c2620",
                   PAPER="#1d2721", DESK="#0c110e", INK="#e4efe7", BANNER_BG="#2b2a1a", BANNER_FG="#e8dca8",
                   ACTION_BG="#3a2224", ACTION_FG="#f3d6d6"),
    "parchment": dict(label="Parchment (light)", LIGHT=True,
                      BG="#efe6d2", SIDEBAR="#e3d6ba", PANEL="#e8dcc3", EDITOR="#f6efe0", FIELD="#fbf6ea",
                      BORDER="#c9b892", FG="#2c2418", MUTED="#6b5c45", FAINT="#958467", ACCENT="#8a5418",
                      ACCENT_DARK="#8a5418", SELECT="#d6bd8c", SELECT_FG="#1f180e", HOVER="#dccba7", ALT="#e1d4b8",
                      PAPER="#fbf6ea", DESK="#d4c4a2", INK="#2a2218", BANNER_BG="#f3e3b5", BANNER_FG="#5a4210",
                      ACTION_BG="#f2d0c8", ACTION_FG="#5a1a10"),
    "light": dict(label="Light", LIGHT=True,
                  BG="#f3f4f6", SIDEBAR="#e8eaee", PANEL="#ffffff", EDITOR="#ffffff", FIELD="#ffffff",
                  BORDER="#d2d6dd", FG="#1f2328", MUTED="#5b6270", FAINT="#8a919e", ACCENT="#2563d6",
                  ACCENT_DARK="#2563d6", SELECT="#cfe0ff", SELECT_FG="#0f1f3d", HOVER="#e3e7ee", ALT="#f5f6f8",
                  PAPER="#ffffff", DESK="#d8dce3", INK="#1b1b1b", BANNER_BG="#fff4cc", BANNER_FG="#5a4500",
                  ACTION_BG="#fde2e0", ACTION_FG="#6b1410"),
    "contrast": dict(label="High contrast", LIGHT=False,
                     BG="#000000", SIDEBAR="#000000", PANEL="#111111", EDITOR="#000000", FIELD="#111111",
                     BORDER="#ffffff", FG="#ffffff", MUTED="#e0e0e0", FAINT="#bdbdbd", ACCENT="#ffd400",
                     ACCENT_DARK="#0050c8", SELECT="#0050c8", SELECT_FG="#ffffff", HOVER="#333333", ALT="#141414",
                     PAPER="#000000", DESK="#1a1a1a", INK="#ffffff", BANNER_BG="#3a3000", BANNER_FG="#ffffff",
                     ACTION_BG="#5a0000", ACTION_FG="#ffffff"),
}
THEME = "dark"


def set_theme(name):
    """Pick the colour theme (before any window is built)."""
    global THEME
    THEME = name if name in THEMES else "dark"
    for k, v in THEMES[THEME].items():
        if k != "label":
            globals()[k] = v


set_theme("dark")


CUSTOM_KEYS = [("BG", "Window background"), ("SIDEBAR", "Sidebar"), ("PANEL", "Panels & toolbars"),
               ("FG", "Text"), ("MUTED", "Secondary text"), ("ACCENT", "Accent (links & buttons)"),
               ("SELECT", "Selection"), ("DESK", "Around the page"), ("PAPER", "Page"), ("INK", "Page text")]


def _lum(c):
    try:
        return (0.299 * int(c[1:3], 16) + 0.587 * int(c[3:5], 16) + 0.114 * int(c[5:7], 16)) / 255.0
    except Exception:
        return 0.0


def build_custom(colors, base="dark"):
    """A full theme from the 10 colours you pick (the rest are worked out from them)."""
    th = dict(THEMES.get(base, THEMES["dark"]))
    th.update({k: v for k, v in (colors or {}).items() if k in dict(CUSTOM_KEYS) and isinstance(v, str)})
    light = _lum(th["BG"]) > 0.5
    fg, panel = th["FG"], th["PANEL"]
    acc = th["ACCENT"]
    th.update(label="Custom", LIGHT=light, EDITOR=th["PAPER"], FIELD=mix(panel, fg, 0.06),
              BORDER=mix(panel, fg, 0.16), FAINT=mix(th["MUTED"], th["BG"], 0.35),
              ACCENT_DARK=acc if _lum(acc) < 0.55 else mix(acc, "#000000", 0.45),
              SELECT_FG="#ffffff" if _lum(th["SELECT"]) < 0.55 else "#111111",
              HOVER=mix(panel, fg, 0.10), ALT=mix(panel, fg, 0.04),
              BANNER_BG=mix(panel, "#e0c050", 0.22), BANNER_FG=fg,
              ACTION_BG=mix(panel, "#d04040", 0.25), ACTION_FG=fg)
    return th


def register_custom(colors):
    if colors:
        THEMES["custom"] = build_custom(colors)
    else:
        THEMES.pop("custom", None)


def mix(c1, c2, t):
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(int(x + (y - x) * t) for x, y in zip(a, b))
UI_FAMILY = "Segoe UI"
UI_SIZE = 10
UI_FONT = (UI_FAMILY, UI_SIZE)
UI_BOLD = (UI_FAMILY, UI_SIZE, "bold")


def set_ui_family(family, size=11):
    """Font for the sidebar, folders, buttons and dialogs (set before building windows)."""
    global UI_FAMILY, UI_SIZE, UI_FONT, UI_BOLD
    UI_FAMILY, UI_SIZE = family, size
    UI_FONT = (family, size)
    UI_BOLD = (family, size, "bold")


def dark_titlebar(win):
    """Ask Windows 10/11 to draw this window's title bar dark."""
    if not sys.platform.startswith("win"):
        return
    try:
        import ctypes
        win.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(win.winfo_id()) or win.winfo_id()
        val = ctypes.c_int(0 if LIGHT else 1)
        for attr in (20, 19):
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(val), ctypes.sizeof(val)) == 0:
                break
    except Exception:
        pass


def apply(root, heading="Segoe UI"):
    root.configure(bg=BG)
    st = ttk.Style(root)
    try:
        st.theme_use("clam")
    except tk.TclError:
        pass
    st.configure(".", background=BG, foreground=FG, fieldbackground=FIELD, bordercolor=BORDER,
                 darkcolor=BG, lightcolor=BG, troughcolor=PANEL, focuscolor=ACCENT,
                 selectbackground=SELECT, selectforeground=FG, insertcolor=FG, font=UI_FONT)
    st.configure("TFrame", background=BG)
    st.configure("Side.TFrame", background=SIDEBAR)
    st.configure("Panel.TFrame", background=PANEL)
    st.configure("TLabel", background=BG, foreground=FG)
    st.configure("Side.TLabel", background=SIDEBAR, foreground=MUTED)
    st.configure("SideHead.TLabel", background=SIDEBAR, foreground=FAINT, font=(UI_FAMILY, UI_SIZE - 1, "bold"))
    st.configure("Panel.TLabel", background=PANEL, foreground=FG)
    st.configure("Muted.TLabel", background=BG, foreground=MUTED)
    st.configure("PanelMuted.TLabel", background=PANEL, foreground=MUTED)
    st.configure("SideHint.TLabel", background=SIDEBAR, foreground=FAINT, font=(UI_FAMILY, max(8, UI_SIZE - 2)))
    st.configure("Section.TLabel", background=BG, foreground=FAINT, font=(UI_FAMILY, UI_SIZE - 1, "bold"))
    st.configure("Title.TLabel", background=BG, foreground=FG, font=(heading, 24))
    st.configure("NoteTitle.TLabel", background=BG, foreground=FG, font=(heading, 21))
    st.configure("H2.TLabel", background=BG, foreground=FG, font=(UI_FAMILY, UI_SIZE + 4, "bold"))
    st.configure("PanelH2.TLabel", background=PANEL, foreground=FG, font=(UI_FAMILY, UI_SIZE + 3, "bold"))
    st.configure("TButton", background=PANEL, foreground=FG, bordercolor=BORDER, padding=(10, 5),
                 relief="flat", focusthickness=0)
    st.map("TButton", background=[("active", HOVER), ("pressed", SELECT), ("disabled", BG)],
           foreground=[("disabled", FAINT)])
    st.configure("Accent.TButton", background=ACCENT_DARK, foreground="white", bordercolor=ACCENT_DARK)
    st.map("Accent.TButton", background=[("active", mix(ACCENT_DARK, "#000000" if LIGHT else "#ffffff", 0.15)),
                                         ("pressed", mix(ACCENT_DARK, "#000000", 0.2))])
    st.configure("Danger.TButton", background="#5a2a2a", foreground="white", bordercolor="#5a2a2a")
    st.map("Danger.TButton", background=[("active", "#733434")])
    st.configure("Side.TButton", background=SIDEBAR, foreground=FG, bordercolor=SIDEBAR, padding=(8, 4))
    st.map("Side.TButton", background=[("active", HOVER)])
    st.configure("TCheckbutton", background=BG, foreground=FG, indicatorbackground=FIELD,
                 indicatorforeground=FG)
    st.map("TCheckbutton", background=[("active", BG)], indicatorbackground=[("selected", ACCENT_DARK)])
    st.configure("TRadiobutton", background=BG, foreground=FG, indicatorbackground=FIELD)
    st.map("TRadiobutton", background=[("active", BG)], indicatorbackground=[("selected", ACCENT_DARK)])
    st.configure("TEntry", fieldbackground=FIELD, foreground=FG, insertcolor=FG, bordercolor=BORDER, padding=4)
    st.configure("TSpinbox", fieldbackground=FIELD, foreground=FG, arrowcolor=FG, background=PANEL,
                 insertcolor=FG, bordercolor=BORDER)
    st.configure("TCombobox", fieldbackground=FIELD, foreground=FG, arrowcolor=FG, background=PANEL,
                 bordercolor=BORDER, padding=3)
    st.map("TCombobox", fieldbackground=[("readonly", FIELD)], foreground=[("readonly", FG)],
           selectbackground=[("readonly", FIELD)], selectforeground=[("readonly", FG)])
    root.option_add("*TCombobox*Listbox.background", FIELD)
    root.option_add("*TCombobox*Listbox.foreground", FG)
    root.option_add("*TCombobox*Listbox.selectBackground", SELECT)
    root.option_add("*TCombobox*Listbox.selectForeground", FG)
    root.option_add("*TCombobox*Listbox.font", UI_FONT)
    for cls in ("*TEntry.font", "*TCombobox.font", "*TSpinbox.font", "*Listbox.font", "*Entry.font", "*Spinbox.font"):
        root.option_add(cls, UI_FONT)
    st.configure("Horizontal.TScale", background=BG, troughcolor=FIELD, bordercolor=BORDER,
                 lightcolor=ACCENT, darkcolor=ACCENT)
    st.configure("Horizontal.TProgressbar", background=ACCENT, troughcolor=FIELD, bordercolor=BORDER,
                 lightcolor=ACCENT, darkcolor=ACCENT)
    st.configure("Level.Horizontal.TProgressbar", background=GREEN, troughcolor=FIELD,
                 lightcolor=GREEN, darkcolor=GREEN)
    st.configure("Hot.Horizontal.TProgressbar", background=RED, troughcolor=FIELD,
                 lightcolor=RED, darkcolor=RED)
    st.configure("Vertical.TScrollbar", background=PANEL, troughcolor=BG, bordercolor=BG,
                 arrowcolor=MUTED, lightcolor=PANEL, darkcolor=PANEL, gripcount=0)
    st.map("Vertical.TScrollbar", background=[("active", HOVER)])
    st.configure("TSeparator", background=BORDER)
    try:   # row heights from the real font height, so rows never overlap at any display scaling
        import tkinter.font as _tkf
        side_ls = _tkf.Font(root=root, font=(UI_FAMILY, UI_SIZE + 1)).metrics("linespace")
        list_ls = _tkf.Font(root=root, font=(UI_FAMILY, UI_SIZE)).metrics("linespace")
    except Exception:
        side_ls, list_ls = 20, 18
    st.configure("Treeview", background=SIDEBAR, fieldbackground=SIDEBAR, foreground=FG,
                 bordercolor=SIDEBAR, rowheight=int(side_ls * 1.65), font=(UI_FAMILY, UI_SIZE + 1))
    st.map("Treeview", background=[("selected", SELECT)], foreground=[("selected", SELECT_FG)])
    sc = ui_scale(root)
    st.configure("Treeview", indent=int(18 * sc), indicatorsize=int(13 * sc),
                 indicatormargins=(int(4 * sc), int(2 * sc), int(6 * sc), int(2 * sc)))
    st.configure("List.Treeview", background=PANEL, fieldbackground=PANEL, bordercolor=PANEL,
                 rowheight=int(list_ls * 2.1))   # about half a line of space between rows
    st.configure("Treeview.Heading", background=BG, foreground=MUTED, bordercolor=BG, relief="flat",
                 font=(UI_FAMILY, UI_SIZE - 1, "bold"))
    st.map("Treeview.Heading", background=[("active", BG)])
    st.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
    root.option_add("*Menu.background", PANEL)
    root.option_add("*Menu.foreground", FG)
    root.option_add("*Menu.activeBackground", SELECT)
    root.option_add("*Menu.activeForeground", SELECT_FG)
    root.option_add("*Menu.relief", "flat")
    root.option_add("*Menu.borderWidth", 0)
    root.option_add("*Menu.font", UI_FONT)
    return st


def later(widget, ms, fn, *args):
    """Run fn(*args) after ms milliseconds (None = when idle) - unless widget has been closed by then.
    The timer belongs to the main window, so a closed window never leaves a dangling timer behind
    (Tk could otherwise later run some other command that reused its name)."""
    def run():
        try:
            if widget.winfo_exists():
                fn(*args)
        except tk.TclError:
            pass
    root = widget._root()
    return root.after_idle(run) if ms is None else root.after(ms, run)


_popups = []


def menu(parent):
    """A menu in Nobu's colours. Right-click / drop-down menus are made fresh each time, so the ones
    already closed are cleared away here (only one can be open at once) instead of piling up."""
    m = tk.Menu(parent, tearoff=0, bg=PANEL, fg=FG, activebackground=SELECT,
                activeforeground=SELECT_FG, bd=0, relief="flat", font=UI_FONT)
    if not isinstance(parent, tk.Menu):          # (a sub-menu goes with its menu)
        keep = []
        for old in _popups:
            try:
                if old.winfo_ismapped():
                    keep.append(old)
                else:
                    old.destroy()
            except tk.TclError:
                pass
        _popups[:] = keep + [m]
    return m


def ui_scale(widget):
    """Windows display scaling (1.0 at 100%, 1.25 at 125%, 1.5 at 150% ...)."""
    try:
        return max(1.0, float(widget.winfo_fpixels("1i")) / 96.0)
    except Exception:
        return 1.0


def _anchor(parent):
    """The window you're working in (Nobu's main window, a note in its own window, a dialog...):
    new windows open over it - on the same monitor - instead of in the middle of the main screen."""
    try:
        f = parent.focus_get()
        top = f.winfo_toplevel() if f is not None else None
        if top is not None and top.winfo_viewable() and not top.overrideredirect():
            return top
    except Exception:
        pass
    try:
        top = parent.winfo_toplevel()
        return top if top.winfo_viewable() else None
    except Exception:
        return None


def _place_over(win, W, H, dy=4):
    """Top-left corner for a W x H window centred over the window it was opened from."""
    sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
    a = getattr(win, "_nobu_over", None)
    try:
        if a is not None and a.winfo_exists() and a.winfo_viewable() and a.winfo_width() > 50:
            ax, ay, aw, ah = a.winfo_rootx(), a.winfo_rooty(), a.winfo_width(), a.winfo_height()
            x, y = ax + (aw - W) // 2, ay + max(0, (ah - H) // dy)
            if 0 <= ax and ax + aw <= sw + 50:          # on the main screen: keep it fully on screen
                x, y = max(0, min(x, sw - W)), max(0, min(y, sh - H - 40))
            return x, y
    except tk.TclError:
        pass
    return max(0, (sw - W) // 2), max(0, (sh - H) // dy)


def fit(win):
    """Make a window at least as big as its contents (so no button is ever cut off),
    but never bigger than the screen; it opens over the window it came from."""
    try:
        win.update_idletasks()
        rw, rh = win.winfo_reqwidth(), win.winfo_reqheight()
        m = re.match(r"(\d+)x(\d+)", win.geometry())
        cw, ch = (int(m.group(1)), int(m.group(2))) if m else (rw, rh)
        sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
        W = min(max(cw, rw), sw - 40)
        H = min(max(ch, rh), sh - 90)
        win.geometry("%dx%d+%d+%d" % ((W, H) + _place_over(win, W, H)))
        win.minsize(min(rw, W), min(rh, H))
    except Exception:
        pass


def toplevel(root, title, w=None, h=None, modal=False):
    win = tk.Toplevel(root, bg=BG)
    win.title(title)
    if w and h:
        k = ui_scale(root)
        win.geometry("%dx%d" % (int(w * k), int(h * k)))
    try:
        win.iconphoto(False, root._nobu_icon)  # noqa
    except Exception:
        pass
    win._nobu_over = _anchor(root)
    win.transient(root if root.winfo_viewable() else None)
    dark_titlebar(win)
    if modal:
        win.grab_set()
    return win


def _center(win):
    win.update_idletasks()
    win.geometry("+%d+%d" % _place_over(win, win.winfo_reqwidth(), win.winfo_reqheight(), dy=3))


def ask_string(parent, title, prompt, initial=""):
    res = {"v": None}
    win = toplevel(parent, title)
    f = ttk.Frame(win, padding=18)
    f.pack(fill="both", expand=True)
    ttk.Label(f, text=prompt).pack(anchor="w")
    var = tk.StringVar(value=initial)
    e = ttk.Entry(f, textvariable=var, width=44)
    e.pack(fill="x", pady=(8, 14))
    e.select_range(0, "end")
    e.focus_set()
    b = ttk.Frame(f)
    b.pack(anchor="e")

    def ok(*_):
        res["v"] = var.get().strip() or None
        win.destroy()
    ttk.Button(b, text="Cancel", command=win.destroy).pack(side="right", padx=(6, 0))
    ttk.Button(b, text="OK", style="Accent.TButton", command=ok).pack(side="right")
    e.bind("<Return>", ok)
    win.bind("<Escape>", lambda _e: win.destroy())
    _center(win)
    win.grab_set()
    win.wait_window()
    return res["v"]


def confirm(parent, title, text, yes="OK", no="Cancel", danger=False):
    res = {"v": False}
    win = toplevel(parent, title)
    f = ttk.Frame(win, padding=18)
    f.pack(fill="both", expand=True)
    ttk.Label(f, text=text, wraplength=420, justify="left").pack(anchor="w", pady=(0, 16))
    b = ttk.Frame(f)
    b.pack(anchor="e")

    def done(v):
        res["v"] = v
        win.destroy()
    nb = None
    if no:
        nb = ttk.Button(b, text=no, command=lambda: done(False))
        nb.pack(side="right", padx=(6, 0))
    yb = ttk.Button(b, text=yes, style="Danger.TButton" if danger else "Accent.TButton", command=lambda: done(True))
    yb.pack(side="right")

    def enter(_e):
        """Enter presses the highlighted button. For deleting, that's the safe one until you Tab to the other."""
        w = win.focus_get()
        if isinstance(w, ttk.Button):
            w.invoke()
        else:
            done(not (danger and nb is not None))
    win.bind("<Escape>", lambda _e: done(False))
    win.bind("<Return>", enter)
    _center(win)
    win.grab_set()
    (nb if danger and nb is not None else yb).focus_set()
    win.wait_window()
    return res["v"]


def info(parent, title, text):
    confirm(parent, title, text, yes="OK", no=None)
