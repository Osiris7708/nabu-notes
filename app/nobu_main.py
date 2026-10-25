"""Nobu Notes - entry point. Run through NobuNotes.exe (which starts the bundled Python)."""
import os
import sys


def _bootstrap_windows():
    """Make the bundled runtime find its DLLs and Tcl/Tk data."""
    if os.name != "nt":
        return
    rt = os.path.dirname(os.path.abspath(sys.executable))
    extra = [os.path.join(rt, "Library", "bin"), os.path.join(rt, "Library", "usr", "bin"),
             os.path.join(rt, "Library", "mingw-w64", "bin"), rt, os.path.join(rt, "DLLs")]
    path_parts = []
    for d in extra:
        if os.path.isdir(d):
            try:
                os.add_dll_directory(d)
            except (OSError, AttributeError):
                pass
            path_parts.append(d)
    os.environ["PATH"] = os.pathsep.join(path_parts + [os.environ.get("PATH", "")])
    for var, sub in (("TCL_LIBRARY", "tcl8.6"), ("TK_LIBRARY", "tk8.6")):
        cand = os.path.join(rt, "Library", "lib", sub)
        if os.path.isdir(cand):
            os.environ[var] = cand
    sp = os.path.join(rt, "Lib", "site-packages")
    if os.path.isdir(sp) and sp not in sys.path:
        sys.path.append(sp)
    _unpack_addons(sp)
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass


def _unpack_addons(site_packages):
    """First start after an update: unpack the writing tools (Word/PDF export, spell check) and the font library."""
    import zipfile
    app_dir = os.path.dirname(os.path.abspath(__file__))
    setup = os.path.join(os.path.dirname(app_dir), "setup")
    jobs = [("addons-v4.zip", site_packages), ("fontlib-v43.zip", os.path.join(app_dir, "fonts", "lib"))]
    for name, dest in jobs:
        z = os.path.join(setup, name)
        marker = os.path.join(dest, ".unpacked-" + name)
        if not os.path.isfile(z) or os.path.isfile(marker):
            continue
        try:
            os.makedirs(dest, exist_ok=True)
            with zipfile.ZipFile(z) as zf:
                zf.extractall(dest)
            with open(marker, "w") as f:
                f.write(str(os.path.getsize(z)))
        except Exception:
            pass


_bootstrap_windows()
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import datetime  # noqa: E402
import logging  # noqa: E402
import logging.handlers  # noqa: E402
import queue  # noqa: E402
import socket  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402
import traceback  # noqa: E402

import nobu_config as C  # noqa: E402

C.ensure_dirs()
_logfile = os.path.join(C.LOGS_DIR, "nobu.log")
_h = logging.handlers.RotatingFileHandler(_logfile, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
_h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
logging.basicConfig(level=logging.INFO, handlers=[_h])
log = logging.getLogger("nobu")
logging.getLogger("faster_whisper").setLevel(logging.WARNING)   # don't log every speech burst (less disk writing)
import nobu_offline  # noqa: E402

nobu_offline.install()   # Nobu's own internet access is blocked (other programs are not affected)
if sys.stdout is None:
    sys.stdout = open(os.path.join(C.LOGS_DIR, "stdout.txt"), "a", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.path.join(C.LOGS_DIR, "stderr.txt"), "a", encoding="utf-8")

import tkinter as tk  # noqa: E402
from tkinter import filedialog, messagebox, ttk  # noqa: E402

import nobu_library as lib  # noqa: E402
import nobu_theme as T  # noqa: E402

PORT = 47651


def _fatal(title, text):
    try:
        r = tk.Tk()
        r.withdraw()
        messagebox.showerror(title, text)
        r.destroy()
    except Exception:
        pass


def _fmt_dt(d):
    """Oct 21, 2026   3:05 PM"""
    return "%s %d, %d   %d:%02d %s" % (d.strftime("%b"), d.day, d.year, (d.hour % 12) or 12, d.minute,
                                         "AM" if d.hour < 12 else "PM")


def _fmt_when(path):
    name = os.path.basename(path)
    try:
        d = datetime.datetime.strptime(name[:16], "%Y-%m-%d %H.%M")
    except ValueError:
        d = datetime.datetime.fromtimestamp(os.path.getmtime(path))
    return _fmt_dt(d)


class App:
    def __init__(self, tray_only=False):
        self.tray_only = tray_only
        self.cfg = C.Config()
        self.uiq = queue.Queue()
        self.tray = None
        self.settings_win = None
        self.diag_win = None
        self.teach_win = None
        self.on_test_done = None
        self.sample_cb = None
        self.sample_timer = None
        self.dict_win = None
        self._cache_job = None
        self.tutorial_win = None
        self.font_win = None
        self.cmd_note = None
        self.cmd_editor = None
        self._tree_click = None       # the sidebar row pressed (opened when the button comes up)
        self.hotkeys = None
        self.state = "idle"
        self.quitting = False
        self.told_tray = False
        self.view = None
        self.current_project = None
        self.clip_items = None
        self.root = self._make_root()
        self.root.withdraw()
        self.root.report_callback_exception = self._tk_error
        import nobu_fonts
        nobu_fonts.load_private()
        self.body_family = nobu_fonts.pick(self.root, self.cfg["font_family"], nobu_fonts.BODY_FALLBACKS)
        self.heading_family = nobu_fonts.pick(self.root, self.cfg["heading_font"], nobu_fonts.HEADING_FALLBACKS)
        self.ui_family = nobu_fonts.pick(self.root, self.cfg["ui_font"], nobu_fonts.UI_FALLBACKS)
        T.set_ui_family(self.ui_family, 11 if self.ui_family != "Segoe UI" else 10)
        T.register_custom(self.cfg.get("custom_theme"))
        T.set_theme(self.cfg.get("theme") or "dark")
        log.info("fonts: text=%s headings=%s interface=%s", self.body_family, self.heading_family, self.ui_family)
        T.apply(self.root, self.heading_family)
        self._set_window_icon()
        import nobu_spell
        self.speller = nobu_spell.Speller()
        self.thesaurus = nobu_spell.Thesaurus()
        self._migrate_vocabulary()
        self._refresh_spell_words()
        if self.cfg.get("install_fonts", True) is not False:
            self.install_fonts_background()

    def _migrate_vocabulary(self):
        """The old Settings box 'Names & unusual words' did a subset of what My dictionary does.
        Its words move into the dictionary (as plain spellings) and the box is gone."""
        vocab = (self.cfg.get("custom_vocabulary") or "").strip()
        if not vocab:
            return
        try:
            import re as _re
            import nobu_dictionary
            entries = nobu_dictionary.load()
            have = {e["word"].lower() for e in entries}
            for w in _re.split(r"[,;\n]+", vocab):
                w = w.strip()
                if w and w.lower() not in have:
                    entries.append({"word": w, "sounds": []})
                    have.add(w.lower())
            nobu_dictionary.save(entries)
            self.cfg.update(custom_vocabulary="")
            log.info("moved the Settings vocabulary into My dictionary")
        except Exception:
            log.exception("vocabulary migration")

    def _refresh_spell_words(self):
        try:
            import nobu_dictionary
            self.speller.set_extra([e["word"] for e in nobu_dictionary.load()])
        except Exception:
            log.exception("dictionary words for spell check")

    def install_fonts_background(self, force=False):
        """Install Nobu's fonts for this Windows user so Word & co. show the same fonts (no admin needed)."""
        import nobu_fonts

        def run():
            try:
                n = nobu_fonts.install_into_windows(force=force)
                if n:
                    self.ui(lambda: self.set_status("Installed %d font files into Windows - Word and other programs "
                                                    "can use them now." % n))
            except Exception:
                log.exception("font install failed")
        threading.Thread(target=run, daemon=True).start()

    # ------------------------------------------------------------ setup
    def _make_root(self):
        try:
            from tkinterdnd2 import TkinterDnD
            return TkinterDnD.Tk()
        except Exception:
            log.info("drag-and-drop support not loaded", exc_info=True)
            return tk.Tk()

    def _set_window_icon(self):
        try:
            art = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nobu_icon.png")
            if os.path.exists(art):
                self._icon_img = tk.PhotoImage(file=art)
            else:                       # (the drawn stand-in, if the icon file is missing)
                from nobu_pictool import tk_photo
                from nobu_ui import make_icon
                self._icon_img = tk_photo(make_icon("idle"))
            self.root._nobu_icon = self._icon_img
            self.root.iconphoto(True, self._icon_img)
        except Exception:
            pass

    def _tk_error(self, exc, val, tb):
        log.error("UI error:\n%s", "".join(traceback.format_exception(exc, val, tb)))

    def run(self):
        from nobu_models import missing
        need = missing([self.cfg["detect_model"], self.cfg["transcribe_model"]])
        if need:
            from nobu_ui import SetupWindow
            if not SetupWindow(self.root, need).run():
                if missing([self.cfg["detect_model"]]) and not missing(["tiny.en"]):
                    self.cfg.update(detect_model="tiny.en")      # fall back to what we already have
                if missing([self.cfg["detect_model"], self.cfg["transcribe_model"]]):
                    return
        from nobu_audio import Engine, recover_partial_recordings
        from nobu_transcribe import Detector, Transcriber
        from nobu_ui import Badge

        lib.migrate_trash()
        moved = lib.migrate_legacy()
        if moved:
            log.info("moved %d older notes into Unassigned", len(moved))
        self._build_window()
        self.badge = Badge(self.root)
        self.detector = Detector(self.cfg)
        self.transcriber = Transcriber(self.cfg, lambda n, **kw: self.ui(self._tx_event, n, kw))
        self.engine = Engine(self.cfg, self.detector, lambda n, **kw: self.ui(self._engine_event, n, kw),
                             C.RECORDINGS_DIR, heard_dir=C.HEARD_DIR,
                             commands_dir=os.path.join(C.LOGS_DIR, "commands"))
        threading.Thread(target=self._warm, daemon=True).start()
        self.engine.start()
        self.apply_hotkeys()
        self._start_tray()
        self.apply_autostart()
        self._start_instance_listener()
        recover_partial_recordings(C.RECORDINGS_DIR)
        self.refresh_library()
        self.show_home()
        try:
            self._restore_session()
        except Exception:
            log.exception("reopening last session's notes")
        if not self.tray_only or self.tray is None:
            self.show_window()
        self.root.after(150, self._pump)
        self.root.after(2500, self._offer_pending)
        self._refresh_status()
        self._tick_meter()
        self.root.mainloop()

    def _warm(self):
        try:
            self.detector.warm()
        except Exception:
            log.exception("could not load the wake-phrase model")
            self.ui(lambda: self.set_status("Could not load the speech model - see logs\\nobu.log"))

    # ------------------------------------------------------------ main window
    def _build_window(self):
        r = self.root
        r.title("Nobu Notes")
        sc = T.ui_scale(r)
        sw, sh = r.winfo_screenwidth(), r.winfo_screenheight()
        r.minsize(min(int(760 * sc), sw - 40), min(int(500 * sc), sh - 80))
        r.geometry(self._fit_geometry(self.cfg["geometry"], sw, sh, sc))
        if self.cfg.get("maximized"):
            try:
                r.state("zoomed")
            except tk.TclError:
                pass
        r.protocol("WM_DELETE_WINDOW", self.on_close_window)
        r.bind_all("<Control-n>", lambda e: self.new_note())

        sw = self.cfg.get("sidebar_width") or int(270 * T.ui_scale(r))
        side = self.side = ttk.Frame(r, style="Side.TFrame", width=sw)
        side.pack(side="left", fill="y")
        side.pack_propagate(False)
        # drag this edge to make the sidebar wider or narrower
        # a wide, easy-to-grab handle (the whole strip is draggable, with grip dots in the middle)
        gw = max(12, int(12 * T.ui_scale(r)))
        sash = self.sash = tk.Canvas(r, width=gw, bg=T.SIDEBAR, highlightthickness=0, bd=0,
                                     cursor="sb_h_double_arrow")
        sash.pack(side="left", fill="y")

        def draw_sash(_e=None, hot=False):
            sash.delete("all")
            h, w = sash.winfo_height(), int(sash.cget("width"))
            sash.configure(bg=T.HOVER if hot else T.SIDEBAR)
            sash.create_line(w - 1, 0, w - 1, h, fill=T.ACCENT if hot else T.BORDER, width=2 if hot else 1)
            for k in range(-3, 4):
                y = h // 2 + k * max(6, gw // 2)
                sash.create_oval(w // 2 - 2, y - 2, w // 2 + 2, y + 2, fill=T.ACCENT if hot else T.FAINT, outline="")
        sash.bind("<Configure>", draw_sash)
        sash.bind("<Enter>", lambda e: draw_sash(hot=True))
        sash.bind("<Leave>", lambda e: draw_sash(hot=False))
        sash.bind("<B1-Motion>", self._drag_sidebar)
        sash.bind("<ButtonRelease-1>", lambda e: self.cfg.update(sidebar_width=int(self.side.cget("width"))))
        sash.bind("<Double-Button-1>", lambda e: self._fit_sidebar())
        main = self.main = ttk.Frame(r)
        main.pack(side="left", fill="both", expand=True)

        # --- sidebar header
        hd = ttk.Frame(side, style="Side.TFrame", padding=(16, 16, 16, 8))
        hd.pack(fill="x")
        self.brand = tk.Label(hd, text="Nobu Notes", bg=T.SIDEBAR, fg=T.FG, font=(self.heading_family, 20))
        self.brand.pack(anchor="w")
        pill = tk.Frame(hd, bg=T.SIDEBAR)
        pill.pack(anchor="w", pady=(6, 0))
        self.pill_dot = tk.Label(pill, text="●", bg=T.SIDEBAR, fg=T.GREEN, font=("Segoe UI", 10))
        self.pill_dot.pack(side="left")
        self.pill_txt = tk.Label(pill, text="Listening", bg=T.SIDEBAR, fg=T.MUTED, font=(T.UI_FAMILY, T.UI_SIZE))
        self.pill_txt.pack(side="left", padx=4)

        # --- nav
        self.nav = ttk.Treeview(side, show="tree", selectmode="browse", height=3)
        self.nav.pack(fill="x", padx=8, pady=(8, 2))
        self.nav.insert("", "end", iid="home", text="  \u2302   Home")
        self.nav.insert("", "end", iid="inbox", text="  \u2709   Unassigned")
        self.nav.insert("", "end", iid="trash", text="  \u267b   Trash")
        self.nav.bind("<<TreeviewSelect>>", self._on_nav)
        # a click always goes there, even if that entry already looks selected
        self.nav.bind("<ButtonPress-1>", lambda e: setattr(self.nav, "_mouse", self.nav.identify_row(e.y) or None))
        self.nav.bind("<ButtonRelease-1>", self._nav_click)
        self.nav.bind("<Button-3>", self._nav_right)

        ph = ttk.Frame(side, style="Side.TFrame", padding=(16, 12, 8, 2))
        ph.pack(fill="x")
        ttk.Label(ph, text="BOOKS & CAMPAIGNS", style="SideHead.TLabel").pack(side="left")
        tk.Button(ph, text=" + ", command=self.new_project, bg=T.SIDEBAR, fg=T.MUTED, relief="flat", bd=0,
                  activebackground=T.HOVER, activeforeground=T.FG, font=("Segoe UI", 13), padx=6,
                  cursor="hand2").pack(side="right")

        bottom = ttk.Frame(side, style="Side.TFrame", padding=(12, 8, 12, 12))
        bottom.pack(side="bottom", fill="x")
        self.side_meter = ttk.Progressbar(bottom, maximum=100, style="Level.Horizontal.TProgressbar")
        self.side_meter.pack(fill="x", pady=(0, 8))
        bb = ttk.Frame(bottom, style="Side.TFrame")
        bb.pack(fill="x")
        self.rec_btn = ttk.Button(bb, text="●  Record", style="Accent.TButton", command=self.toggle_manual_record)
        self.rec_btn.pack(side="left", fill="x", expand=True)
        self.pause_btn = ttk.Button(bb, text="❚❚", width=4, command=self.toggle_pause)
        self.pause_btn.pack(side="left", padx=(6, 0))
        self.gear_btn = ttk.Button(bb, text="⚙", width=4, command=self._gear_menu)
        self.gear_btn.pack(side="left", padx=(6, 0))
        self.rec_hint = ttk.Label(bottom, text="", style="SideHint.TLabel")
        self.rec_hint.pack(anchor="w", pady=(4, 0))

        tf = ttk.Frame(side, style="Side.TFrame")
        tf.pack(fill="both", expand=True, padx=8)
        # Shift-click / Ctrl-click select several (for colours, moving, deleting...)
        self.tree = ttk.Treeview(tf, show="tree", selectmode="extended")
        sb = ttk.Scrollbar(tf, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self._on_tree)
        self.tree.bind("<<TreeviewOpen>>", self._on_tree_open)
        self.tree.bind("<ButtonPress-1>", self._tree_press)
        self.tree.bind("<B1-Motion>", lambda e: self.dragdrop._motion(e, self.tree))
        self.tree.bind("<ButtonRelease-1>", self._tree_release)
        self.tree.bind("<Double-Button-1>", self._tree_double)
        self.tree.bind("<Button-2>", self._tree_middle)
        self.tree.bind("<Button-3>", self._on_tree_right)
        self.tree.bind("<Return>", lambda e: self._tree_navigate(self.tree.focus()))
        self.tree.tag_configure("empty", foreground=T.FAINT)

        # --- content
        self.status = ttk.Label(main, text="", style="Muted.TLabel", padding=(18, 4, 18, 8))
        self.status.pack(side="bottom", fill="x")
        self.progress = ttk.Progressbar(main, mode="determinate", maximum=100)
        self.content = ttk.Frame(main)
        self.content.pack(side="top", fill="both", expand=True)
        from nobu_workspace import Workspace
        self.editor = None
        self.ws = Workspace(self.content, self)      # sets self.editor (the note you're working in)
        self.home = self._build_home(self.content)
        self.inbox = self._build_list_view(self.content, inbox=True)
        self.projview = self._build_list_view(self.content, inbox=False)
        self.trashview = self._build_trash_view(self.content)
        from nobu_dragdrop import DragDrop
        self.dragdrop = DragDrop(self)
        self.root.bind("<FocusIn>", lambda e: self._update_note_context(), add="+")
        self.root.bind("<FocusOut>", lambda e: self.root.after(50, self._update_note_context), add="+")

    @staticmethod
    def _fit_geometry(saved, sw, sh, sc):
        """Saved window size/position, shrunk and moved so it fits this screen (any resolution)."""
        import re as _re
        m = _re.match(r"(\d+)x(\d+)([+-]-?\d+)?([+-]-?\d+)?", saved or "")
        if m:
            w, h = int(m.group(1)), int(m.group(2))
            x = int((m.group(3) or "+0").replace("+-", "-").replace("+", ""))
            y = int((m.group(4) or "+0").replace("+-", "-").replace("+", ""))
        else:
            w, h = int(1250 * sc), int(800 * sc)
            x, y = (sw - w) // 2, (sh - h) // 3
        w, h = min(w, sw - 20), min(h, sh - 60)
        x = max(0, min(x, sw - w))
        y = max(0, min(y, sh - h - 40))
        return "%dx%d+%d+%d" % (w, h, x, y)

    def restart(self):
        """Start a fresh copy of Nobu (it waits for this one to close), then quit."""
        import subprocess
        try:
            flags = (0x00000008 | 0x00000200) if os.name == "nt" else 0   # DETACHED_PROCESS | NEW_PROCESS_GROUP
            subprocess.Popen([sys.executable, os.path.abspath(__file__), "--restart"], creationflags=flags,
                             close_fds=True)
        except Exception:
            log.exception("restart failed")
            T.info(self.root, "Nobu Notes", "Please close Nobu (tray icon > Quit) and open it again.")
            return
        self.quit()

    def _drag_sidebar(self, ev):
        w = ev.x_root - self.side.winfo_rootx()
        w = max(int(170 * T.ui_scale(self.root)), min(int(self.root.winfo_width() * 0.6), w))
        self.side.configure(width=w)

    def _fit_sidebar(self):
        """Double-click the edge: make the sidebar just wide enough for the longest name."""
        import tkinter.font as tkf
        f = tkf.Font(font=(T.UI_FAMILY, T.UI_SIZE + 1))
        widest = 0

        def walk(iid, depth):
            nonlocal widest
            for c in self.tree.get_children(iid):
                widest = max(widest, f.measure(self.tree.item(c, "text")) + 16 * (depth + 1))
                if self.tree.item(c, "open"):
                    walk(c, depth + 1)
        walk("", 0)
        w = max(int(220 * T.ui_scale(self.root)), min(int(self.root.winfo_width() * 0.6), widest + 60))
        self.side.configure(width=w)
        self.cfg.update(sidebar_width=w)

    def _gear_menu(self):
        m = T.menu(self.root)
        m.add_command(label="Microphone, noise & settings…", command=self.open_settings)
        m.add_command(label="Teach Nobu my voice…", command=self.open_teach)
        m.add_command(label="My dictionary (names & spellings)…", command=self.open_dictionary)
        m.add_command(label="What is it hearing?…", command=self.open_diagnostics)
        m.add_command(label="Fonts…", command=self.open_font_browser)
        m.add_command(label="How to use Nobu (tutorial)…", command=self.open_tutorial)
        m.add_separator()
        m.add_command(label="Import documents…", command=lambda: self.import_dialog())
        m.add_command(label="Transcribe an audio file…", command=self.transcribe_file_dialog)
        m.add_command(label="Open Recordings folder", command=lambda: self._open(C.RECORDINGS_DIR))
        m.add_command(label="Open log file", command=lambda: self._open(_logfile))
        m.add_separator()
        m.add_command(label="Hide to tray", command=self.hide_window)
        m.add_command(label="Quit Nobu Notes", command=self.quit)
        b = self.gear_btn
        m.tk_popup(b.winfo_rootx(), b.winfo_rooty() - 13 * 26)

    @staticmethod
    def _inside(path, folder):
        if not path or not folder:
            return False
        a, b = os.path.normcase(os.path.abspath(path)), os.path.normcase(os.path.abspath(folder))
        return a == b or a.startswith(b + os.sep)

    # ------------------------------------------------------------ open notes (one or several)
    def editors_for(self, path):
        return self.ws.editors_for(path)

    def _note_showing(self):
        """Is a note on screen (main window or its own window) and the one being worked in?"""
        ed = self.editor
        return bool(ed and ed.path and (self.view is self.ws.frame or self.ws.is_popped(ed)))

    def show_workspace(self, path=None):
        self._show(self.ws.frame)
        if path:
            self._reveal(path)

    def workspace_emptied(self, folder):
        """The last note in the main window was closed or popped out: show its folder instead."""
        if self.view is not self.ws.frame:
            return
        if folder and os.path.isdir(folder) and not lib.is_inbox(folder):
            self.show_project(folder)
        elif folder and lib.is_inbox(folder):
            self.show_inbox()
        else:
            self.show_home()

    def recent_notes(self):
        out = []
        for r in self.cfg.get("recent_notes") or []:
            p = C.abs_from_home(r)
            if os.path.isfile(p) and p not in out:
                out.append(p)
        return out

    def _remember(self, path, old=None):
        rel = C.rel_to_home(path)
        lst = [r for r in (self.cfg.get("recent_notes") or []) if r != rel and (old is None or r != C.rel_to_home(old))]
        if old is not None and C.rel_to_home(old) not in (self.cfg.get("recent_notes") or []):
            return
        self.cfg.update(recent_notes=([rel] + lst)[:30])

    def _repath(self, old, new):
        """A note moved or was renamed: every window showing it follows."""
        for ed in self.editors_for(old):
            ed.path_changed(new)
        self._remember(new, old=old)

    def _rebase_open_note(self, old_folder, new_folder):
        """Keep open notes (and the current folder) pointing at the right place after a folder moves."""
        for ed in self.ws.editors():
            if ed.path and self._inside(ed.path, old_folder):
                ed.path_changed(os.path.join(new_folder, os.path.relpath(ed.path, old_folder)))
        if self.current_project and self._inside(self.current_project, old_folder):
            self.current_project = os.path.normpath(os.path.join(new_folder, os.path.relpath(self.current_project, old_folder)))

    @staticmethod
    def _open(p):
        from nobu_editor import open_path
        open_path(p)

    # --- home view
    def _build_home(self, parent):
        # the home page scrolls, so nothing is ever cut off on small or low-resolution screens
        outer = ttk.Frame(parent)
        canvas = tk.Canvas(outer, bg=T.BG, highlightthickness=0, bd=0)
        vsb = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        canvas.pack(side="left", fill="both", expand=True)
        f = ttk.Frame(canvas, padding=(40, 34))
        win = canvas.create_window(0, 0, window=f, anchor="nw")

        def relayout(_e=None):
            canvas.itemconfigure(win, width=canvas.winfo_width())
            canvas.configure(scrollregion=(0, 0, canvas.winfo_width(), f.winfo_reqheight()))
            if f.winfo_reqheight() > canvas.winfo_height() + 2:
                if not vsb.winfo_ismapped():
                    vsb.pack(side="right", fill="y", before=canvas)
            else:
                vsb.pack_forget()
                canvas.yview_moveto(0)
        canvas.bind("<Configure>", relayout)
        f.bind("<Configure>", relayout)

        here = str(outer)

        def wheel(ev):
            """The wheel scrolls the home page wherever the mouse is on it (also over its buttons)."""
            if vsb.winfo_ismapped() and (str(ev.widget) + ".").startswith(here + "."):
                canvas.yview_scroll(-1 if (getattr(ev, "delta", 0) > 0 or ev.num == 4) else 1, "units")
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            outer.bind_all(seq, wheel, add="+")
        ttk.Label(f, text="Nobu Notes", style="Title.TLabel").pack(anchor="w")
        ttk.Label(f, text="Say “%s” and start talking. Say “%s”, or stay quiet for a few "
                          "seconds, to finish." % (C.WAKE_PHRASE, C.STOP_PHRASE), style="Muted.TLabel",
                  wraplength=760).pack(anchor="w", pady=(4, 0))
        ttk.Label(f, text="(Tip: “Nobu” is said “no-boo”.)", style="Muted.TLabel").pack(anchor="w", pady=(2, 14))
        priv = tk.Frame(f, bg=T.PANEL, highlightthickness=0)
        priv.pack(fill="x", pady=(0, 20))
        tk.Frame(priv, width=4, bg=T.GREEN).pack(side="left", fill="y")
        pin = tk.Frame(priv, bg=T.PANEL, padx=14, pady=10)
        pin.pack(side="left", fill="x", expand=True)
        tk.Label(pin, text="✔  100% local and private", bg=T.PANEL, fg=T.GREEN, font=T.UI_BOLD,
                 anchor="w").pack(anchor="w")
        self.privacy_lbl = tk.Label(
            pin, bg=T.PANEL, fg=T.MUTED, font=T.UI_FONT, anchor="w", justify="left", wraplength=900,
            text="Your recordings, transcripts and notes are made and stored only on this computer, in your "
                 "Nobu Notes folder. Speech recognition runs here, with no account and no cloud. Nobu also blocks "
                 "its own internet access while it runs (other programs on your computer are not affected); "
                 "the only exception is the one-time download of the speech models, which only downloads.")
        self.privacy_lbl.pack(anchor="w", fill="x")
        link = tk.Label(pin, text="How is this checked?", bg=T.PANEL, fg=T.ACCENT, font=T.UI_FONT, cursor="hand2")
        link.pack(anchor="w", pady=(4, 0))
        link.bind("<Button-1>", lambda e: self._privacy_details())
        priv.bind("<Configure>", lambda e: self.privacy_lbl.config(wraplength=max(300, e.width - 60)))

        cards = ttk.Frame(f)
        cards.pack(fill="x")

        def card(col):
            c = ttk.Frame(cards, style="Panel.TFrame", padding=18)
            c.grid(row=0, column=col, sticky="nsew", padx=(0 if col == 0 else 8, 0))
            cards.columnconfigure(col, weight=1, uniform="c")
            return c

        c1 = card(0)
        ttk.Label(c1, text="Listening", style="PanelH2.TLabel").pack(anchor="w")
        self.home_state = ttk.Label(c1, text="", style="PanelMuted.TLabel", wraplength=300)
        self.home_state.pack(anchor="w", pady=(6, 12))
        self.home_rec = ttk.Button(c1, text="●  Record now", style="Accent.TButton", command=self.toggle_manual_record)
        self.home_rec.pack(anchor="w")
        self.home_rec_hint = ttk.Label(c1, text="", style="PanelMuted.TLabel")
        self.home_rec_hint.pack(anchor="w", pady=(3, 0))

        c2 = card(1)
        ttk.Label(c2, text="Unassigned", style="PanelH2.TLabel").pack(anchor="w")
        self.home_inbox = ttk.Label(c2, text="", style="PanelMuted.TLabel", wraplength=300)
        self.home_inbox.pack(anchor="w", pady=(6, 12))
        ttk.Button(c2, text="Review transcripts", command=self.show_inbox).pack(anchor="w")

        c3 = card(2)
        ttk.Label(c3, text="Books & campaigns", style="PanelH2.TLabel").pack(anchor="w")
        self.home_proj = ttk.Label(c3, text="", style="PanelMuted.TLabel", wraplength=300)
        self.home_proj.pack(anchor="w", pady=(6, 12))
        ttk.Button(c3, text="+  New project", command=self.new_project).pack(anchor="w")

        ttk.Label(f, text="Recently edited", style="H2.TLabel").pack(anchor="w", pady=(28, 6))
        self.recent = ttk.Frame(f)
        self.recent.pack(fill="x")

        ttk.Label(f, text="Tune it to your voice and room", style="H2.TLabel").pack(anchor="w", pady=(26, 6))
        tb = ttk.Frame(f)
        tb.pack(anchor="w")
        ttk.Button(tb, text="Teach Nobu my voice", command=self.open_teach).pack(side="left")
        ttk.Button(tb, text="My dictionary", command=self.open_dictionary).pack(side="left", padx=8)
        ttk.Button(tb, text="Microphone & noise filter", command=self.open_settings).pack(side="left", padx=8)
        ttk.Button(tb, text="What is it hearing?", command=self.open_diagnostics).pack(side="left")

        ttk.Label(f, text="Writing", style="H2.TLabel").pack(anchor="w", pady=(26, 6))
        wb = ttk.Frame(f)
        wb.pack(anchor="w")
        ttk.Button(wb, text="Import documents…", command=lambda: self.import_dialog()).pack(side="left")
        ttk.Button(wb, text="Fonts…", command=self.open_font_browser).pack(side="left", padx=8)

        ttk.Label(f, text="Help", style="H2.TLabel").pack(anchor="w", pady=(26, 4))
        tut = tk.Label(f, text="How to use Nobu — the full tutorial", bg=T.BG, fg=T.ACCENT,
                       font=(T.UI_FAMILY, T.UI_SIZE + 1), cursor="hand2")
        tut.pack(anchor="w")
        tut.bind("<Button-1>", lambda e: self.open_tutorial())
        ttk.Label(f, text="Recording phrases, voice editing, the dictionary, drag & drop, exporting, "
                          "troubleshooting…", style="Muted.TLabel").pack(anchor="w", pady=(2, 0))
        return outer

    def open_tutorial(self):
        from nobu_help import TutorialWindow
        w = self.tutorial_win
        if w and w.win.winfo_exists():
            w.win.lift()
            return
        self.tutorial_win = TutorialWindow(self.root)

    def _privacy_details(self):
        n = len(nobu_offline.blocked)
        T.info(self.root, "Local and private", (
            "• Recording, noise filtering, wake-word detection and transcription all run on this PC "
            "(speech models in the “models” folder).\n"
            "• Audio is saved in “Recordings” and notes in “Notes”, both inside your Nobu Notes folder.\n"
            "• Nobu has a built-in network guard: while Nobu runs, any attempt by Nobu itself to connect to the "
            "internet is refused. The only exception is the speech-model download (first start, or changing "
            "models in Settings).\n"
            "• The guard lives inside Nobu only. It does not touch Windows, your firewall or any other program - "
            "your browser, games and everything else use the internet exactly as before.\n"
            "• Spell check, thesaurus, fonts, import and export all work offline too.\n"
            "• Any blocked attempt is written to logs\\nobu.log.\n\n"
            "Connections by Nobu that were blocked this session: %d" % n))

    def _fill_home(self):
        n = lib.inbox_count()
        self.home_inbox.config(text=("%d transcript%s waiting to be filed." % (n, "" if n == 1 else "s")) if n
                               else "Nothing waiting. New transcripts appear here.")
        projs = lib.projects()
        self.home_proj.config(text=("%d project%s." % (len(projs), "" if len(projs) == 1 else "s")) if projs
                              else "Make a folder for each book or campaign, then file transcripts into it.")
        for w in self.recent.winfo_children():
            w.destroy()
        # recently opened notes plus the newest transcripts (no need to look through the whole library)
        notes = list(dict.fromkeys(self.recent_notes() + lib.notes_in(C.INBOX_DIR)[:6]))
        notes.sort(key=lambda p: lib.note_info(p)["mtime"], reverse=True)
        if not notes:
            ttk.Label(self.recent, text="No notes yet.", style="Muted.TLabel").pack(anchor="w")
        for p in notes[:6]:
            where = "Unassigned" if lib.is_inbox(os.path.dirname(p)) else os.path.basename(os.path.dirname(p))
            row = tk.Label(self.recent, text="%s    ·  %s" % (lib.title(p), where), anchor="w", bg=T.BG,
                           fg=T.ACCENT, font=T.UI_FONT, cursor="hand2", pady=6, padx=4)
            row.pack(anchor="w", fill="x")
            row.bind("<Enter>", lambda e, r=row: r.configure(bg=T.HOVER))
            row.bind("<Leave>", lambda e, r=row: r.configure(bg=T.BG))
            row.bind("<Button-1>", lambda e, p=p: self.open_note(p))

    # --- list view (inbox / project)
    def _build_list_view(self, parent, inbox):
        f = ttk.Frame(parent, padding=(28, 22, 28, 10))
        f._inbox = inbox
        top = ttk.Frame(f)
        top.pack(fill="x")
        f._title = ttk.Label(top, text="Unassigned" if inbox else "", style="Title.TLabel")
        f._title.pack(side="left")
        btns = ttk.Frame(top)
        btns.pack(side="right")
        f._sub = ttk.Label(f, text="", style="Muted.TLabel", wraplength=800)
        f._sub.pack(anchor="w", pady=(2, 12))
        bar = ttk.Frame(f)
        bar.pack(fill="x", pady=(0, 8))
        if inbox:
            f._move = ttk.Button(bar, text="Move selected to project ▾", style="Accent.TButton",
                                 command=lambda: self.move_menu(f._move, self._selected(f)))
            ttk.Button(bar, text="+  New note", command=lambda: self.new_note(C.INBOX_DIR)).pack(side="left", padx=(0, 6))
            f._move.pack(side="left")
            ttk.Button(bar, text="Delete", command=lambda: self._delete_selected(f)).pack(side="left", padx=6)
            ttk.Button(bar, text="\u21e7  Export / share…",
                       command=lambda: self.export_dialog([p for p in self._selected(f) if os.path.isfile(p)])
                       ).pack(side="right")
            ttk.Button(bar, text="Import…", command=lambda: self.import_dialog(C.INBOX_DIR)).pack(side="right", padx=6)
        else:
            ttk.Button(bar, text="+  New note", style="Accent.TButton", command=self.new_note).pack(side="left")
            ttk.Button(bar, text="+  New sub-folder", command=self.new_subfolder).pack(side="left", padx=(6, 0))
            ttk.Button(bar, text="\u21e7  Export / share…", style="Accent.TButton",
                       command=lambda: self.export_dialog([p for p in self._selected(f) if os.path.isfile(p)],
                                                          self.current_project)).pack(side="right")
            ttk.Button(bar, text="Import documents…", command=lambda: self.import_dialog()).pack(side="right", padx=6)
            ttk.Button(btns, text="Rename", command=self.rename_project).pack(side="left", padx=4)
            ttk.Button(btns, text="Open folder", command=lambda: self._open(self.current_project)).pack(side="left", padx=4)
            ttk.Button(btns, text="Delete", style="Danger.TButton", command=self.delete_project).pack(side="left", padx=4)
        box = ttk.Frame(f, style="Panel.TFrame")
        box.pack(fill="both", expand=True)
        tv = ttk.Treeview(box, columns=("when", "preview"), show="headings", style="List.Treeview",
                          selectmode="extended")
        sc = T.ui_scale(parent)
        tv.heading("when", text="  DATE" if inbox else "  EDITED", anchor="w")
        tv.heading("preview", text="TRANSCRIPT" if inbox else "NOTE", anchor="center")
        tv.column("when", width=int(215 * sc), minwidth=int(180 * sc), stretch=False, anchor="w")
        tv.column("preview", width=int(600 * sc), stretch=True, anchor="center")
        tv.tag_configure("alt", background=T.ALT)
        sb = ttk.Scrollbar(box, orient="vertical", command=tv.yview)
        tv.configure(yscrollcommand=sb.set)
        tv.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        tv.bind("<Double-1>", lambda e: self._list_double(f, e))
        tv.bind("<ButtonRelease-1>", lambda e: self._list_release(f, e), add="+")
        tv.bind("<Return>", lambda e: self._open_selected(f))
        tv.bind("<Button-2>", lambda e: self._list_middle(f, e))
        tv.bind("<Delete>", lambda e: self._delete_selected(f))
        tv.bind("<Button-3>", lambda e: self._list_menu(f, e))
        f._tv = tv
        self._list_dnd(tv, f)
        f._empty = ttk.Label(box, text="", style="PanelMuted.TLabel", padding=20)
        return f

    def _color_tag(self, tv, color):
        if not color:
            return None
        tg = "c:" + color
        done = tv.__dict__.setdefault("_colors", set())
        if tg not in done:
            tv.tag_configure(tg, foreground=color)
            done.add(tg)
        return tg

    def _fill_list(self, f, folder):
        """Fill a folder / Unassigned list. Big folders are filled a few hundred rows at a time,
        so the window never freezes, however many notes there are."""
        tv = f._tv
        same = getattr(f, "_shown", None) == folder
        keep_sel = list(tv.selection()) if same else []
        keep_y = tv.yview()[0] if same else 0.0
        token = object()
        f._fill_token = token
        f._shown = folder
        tv.delete(*tv.get_children())
        subs, notes = lib.contents(folder)
        if f._inbox:
            subs = []
        tv.tag_configure("folder", foreground=T.ACCENT)
        rows = {"n": 0}

        def tags(color, extra=()):
            t = list(extra)
            if rows["n"] % 2:
                t.append("alt")
            ct = self._color_tag(tv, color)
            if ct:
                t.append(ct)
            return tuple(t)
        for d in subs:
            n, inner = lib.count_notes(d)
            desc = "%d note%s" % (n, "" if n == 1 else "s") + (", %d sub-folder%s" % (inner, "" if inner == 1 else "s") if inner else "")
            col = lib.folder_color(d)
            tv.insert("", "end", iid=d, values=("  Folder", "\u25b8  %s   \u2014  %s" % (os.path.basename(d), desc)),
                      tags=tags(col, () if col else ("folder",)))
            rows["n"] += 1

        def add(batch):
            for p in batch:
                info = lib.note_info(p)
                pv = info["preview"][:90] + ("\u2026" if len(info["preview"]) > 90 else "")
                when_dt = datetime.datetime.fromtimestamp(info["mtime"] or 0)
                if f._inbox:
                    when = _fmt_when(p)
                    text = pv or lib.title(p)
                    if not lib.is_auto_named(p):
                        text = lib.title(p) + ("    \u00b7    " + pv if pv else "")
                else:
                    when = _fmt_dt(when_dt)
                    text = lib.title(p) + ("    \u00b7    " + pv if pv else "")
                if not tv.exists(p):
                    tv.insert("", "end", iid=p, values=("  " + when, text), tags=tags(info["color"]))
                    rows["n"] += 1

        def restore():
            sel = [i for i in keep_sel if tv.exists(i)]
            if sel:
                tv.selection_set(sel)
            if keep_y:
                tv.yview_moveto(keep_y)

        def more(start):
            if getattr(f, "_fill_token", None) is not token:
                return               # the list was refilled meanwhile
            try:
                add(notes[start:start + 400])
            except tk.TclError:
                return
            if start + 400 < len(notes):
                self.root.after(1, lambda: more(start + 400))
            else:
                restore()
        first = 250
        add(notes[:first])
        if len(notes) > first:
            self.root.after(1, lambda: more(first))
        else:
            restore()
        if notes or subs:
            f._empty.place_forget()
        else:
            f._empty.config(text="Nothing waiting. Click \u201c+ New note\u201d to write one, or say \u201c%s\u201d to "
                                 "record one." % C.WAKE_PHRASE
                            if f._inbox else "This folder is empty. Click \u201cNew note\u201d or \u201cNew sub-folder\u201d, "
                            "or move transcripts here from Unassigned.")
            f._empty.place(relx=0.5, rely=0.3, anchor="center")
        if f._inbox:
            f._sub.config(text="%d note%s. Double-click to open (or right-click > Open side by side). Select several "
                               "with Ctrl/Shift-click to move them into a book or campaign." % (
                                   len(notes), "" if len(notes) == 1 else "s"))
        else:
            f._title.config(text=lib.crumbs(folder))
            parts = ["%d note%s" % (len(notes), "" if len(notes) == 1 else "s")]
            if subs:
                parts.append("%d sub-folder%s" % (len(subs), "" if len(subs) == 1 else "s"))
            if not lib.is_top_level(folder):
                parts.append("inside \u201c%s\u201d" % lib.crumbs(os.path.dirname(folder)))
            f._sub.config(text="   \u00b7   ".join(parts))

    @staticmethod
    def _selected(f):
        return [p for p in f._tv.selection() if os.path.exists(p)]

    def _open_selected(self, f):
        sel = self._selected(f)
        if sel:
            self._open_item(sel[0])

    def _open_item(self, p, side=False):
        if os.path.isdir(p):
            self.show_project(p)
            self._reveal(p)
        elif os.path.isfile(p):
            self.open_note(p, side=side)

    def _list_double(self, f, ev):
        """Double-click: open exactly the row under the mouse - when the button comes up, so a quick
        click-then-drag still drags (Windows calls that a double-click too)."""
        tv = f._tv
        f._dbl = None
        if tv.identify_region(ev.x, ev.y) == "heading":
            return "break"
        row = tv.identify_row(ev.y)
        if row and os.path.exists(row):
            if ev.state & 0x4:                # Ctrl: add / remove
                if row in tv.selection():
                    tv.selection_remove(row)
                else:
                    tv.selection_add(row)
                return "break"
            if ev.state & 0x1:                # Shift: extend from the last clicked row
                kids = list(tv.get_children())
                anchor = tv.focus() if tv.focus() in kids else row
                i, j = sorted((kids.index(anchor), kids.index(row)))
                tv.selection_set(kids[i:j + 1])
                return "break"
            if row not in tv.selection():
                tv.selection_set(row)
            f._dbl = row
            self.dragdrop._press(ev, tv)
        return "break"

    def _list_release(self, f, ev):
        row, f._dbl = getattr(f, "_dbl", None), None
        if row and not (self.dragdrop.dragging or self.dragdrop.cancelled) and f._tv.identify_row(ev.y) == row \
                and os.path.exists(row):
            self.root.after(1, lambda: self._open_item(row))

    def _list_middle(self, f, ev):
        row = f._tv.identify_row(ev.y)
        if row and os.path.isfile(row):
            self.open_note(row, side=True)

    def open_side_by_side(self, paths):
        notes = [p for p in paths if os.path.isfile(p)][:6]
        for i, p in enumerate(notes):
            self.open_note(p, side=(i > 0 or self._note_showing()))

    def _delete_selected(self, f):
        self.trash_notes(self._selected(f))

    def trash_notes(self, paths):
        """Move notes (and their audio) to the Trash. Recoverable, so no question asked."""
        n = 0
        for p in paths:
            if not os.path.exists(p):
                continue
            for ed in self.editors_for(p):
                self.ws.close_editor(ed)
            lib.to_trash(p)
            n += 1
        self.refresh_library()
        if n:
            self.set_status("Moved %d item%s to Trash (with audio). Restore them from Trash if needed."
                            % (n, "" if n == 1 else "s"))

    def _list_menu(self, f, ev):
        tv = f._tv
        row = tv.identify_row(ev.y)
        if not row:
            folder = C.INBOX_DIR if f._inbox else self.current_project
            m = T.menu(self.root)
            m.add_command(label="+  New note\u2026", command=lambda: self.new_note(folder))
            if not f._inbox:
                m.add_command(label="+  New sub-folder\u2026", command=lambda: self.new_subfolder(folder))
            m.add_command(label="Import documents\u2026", command=lambda: self.import_dialog(folder))
            m.tk_popup(ev.x_root, ev.y_root)
            return
        if row not in tv.selection():
            tv.selection_set(row)
        sel = self._selected(f)
        if not sel:
            return
        m = T.menu(self.root)
        notes = [x for x in sel if os.path.isfile(x)]
        if len(sel) == 1 and os.path.isdir(sel[0]):
            m.add_command(label="Open", command=lambda: self._open_item(sel[0]))
            m.add_command(label="New note in it\u2026", command=lambda: self.new_note(sel[0]))
            m.add_command(label="New sub-folder in it\u2026", command=lambda: self.new_subfolder(sel[0]))
            m.add_command(label="Rename\u2026", command=lambda: self.rename_project(sel[0]))
        elif len(sel) == 1:
            m.add_command(label="Open", command=lambda: self.open_note(sel[0]))
            m.add_command(label="Open side by side", command=lambda: self.open_note(sel[0], side=True))
            m.add_command(label="Open in its own window", command=lambda: self.open_note(sel[0], popout=True))
            m.add_command(label="Rename\u2026", command=lambda: self.rename_note(sel[0]))
        elif notes:
            m.add_command(label="Open %d notes side by side" % min(6, len(notes)),
                          command=lambda: self.open_side_by_side(notes))
        mv = T.menu(m)
        self._fill_move_menu(mv, sel)
        m.add_cascade(label="Move %sto\u2026" % ("%d items " % len(sel) if len(sel) > 1 else ""), menu=mv)
        m.add_cascade(label="Colour label", menu=self._color_menu(m, sel))
        if len(sel) == 1 and os.path.isdir(sel[0]):
            m.add_command(label="Export / share this folder\u2026", command=lambda: self.export_dialog([], sel[0]))
            m.add_command(label="Import documents into it\u2026", command=lambda: self.import_dialog(sel[0]))
        else:
            m.add_command(label="Export / share\u2026", command=lambda: self.export_dialog(
                [x for x in sel if os.path.isfile(x)]))
        m.add_separator()
        if any(os.path.isdir(x) for x in sel):
            m.add_command(label="Delete (move to Trash)\u2026", command=lambda: self._trash_mixed(sel))
        else:
            m.add_command(label="Delete (move to Trash)", command=lambda: self.trash_notes(sel))
        m.tk_popup(ev.x_root, ev.y_root)

    def _trash_mixed(self, paths):
        folders = [x for x in paths if os.path.isdir(x)]
        notes = [x for x in paths if not os.path.isdir(x)]
        n = sum(len(lib.all_notes(d)) for d in folders)
        if folders and not T.confirm(self.root, "Delete", "Move %d folder%s (with %d note%s inside) to the Trash?"
                                     % (len(folders), "" if len(folders) == 1 else "s", n, "" if n == 1 else "s"),
                                     yes="Move to Trash", danger=True):
            return
        for d in folders:
            for ed in self.ws.editors():
                if ed.path and self._inside(ed.path, d):
                    self.ws.close_editor(ed)
            lib.to_trash(d)
        self.trash_notes(notes)
        self.refresh_library()

    # --- trash view
    def _build_trash_view(self, parent):
        f = ttk.Frame(parent, padding=(28, 22, 28, 10))
        ttk.Label(f, text="Trash", style="Title.TLabel").pack(anchor="w")
        f._sub = ttk.Label(f, text="", style="Muted.TLabel", wraplength=800)
        f._sub.pack(anchor="w", pady=(2, 12))
        bar = ttk.Frame(f)
        bar.pack(fill="x", pady=(0, 8))
        ttk.Button(bar, text="Empty trash", command=self.empty_trash).pack(side="right")
        box = ttk.Frame(f, style="Panel.TFrame")
        box.pack(fill="both", expand=True)
        tv = ttk.Treeview(box, columns=("when", "what", "kind"), show="headings", style="List.Treeview",
                          selectmode="extended")
        tv.heading("when", text="DELETED", anchor="w")
        tv.heading("what", text="ITEM", anchor="w")
        tv.heading("kind", text="CONTAINS", anchor="w")
        tv.column("when", width=150, stretch=False)
        tv.column("what", width=480)
        tv.column("kind", width=200, stretch=False)
        sb = ttk.Scrollbar(box, orient="vertical", command=tv.yview)
        tv.configure(yscrollcommand=sb.set)
        tv.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        tv.bind("<Button-3>", self._trash_menu)
        tv.bind("<Delete>", lambda e: self.purge_items(self._trash_sel()))
        f._tv = tv
        f._empty = ttk.Label(box, text="The trash is empty.", style="PanelMuted.TLabel", padding=20)
        return f

    def _fill_trash(self):
        f = self.trashview
        tv = f._tv
        tv.delete(*tv.get_children())
        items = lib.trash_items()
        for b, info in items:
            try:
                when = datetime.datetime.fromisoformat(info.get("deleted", "")).strftime("%b %d, %I:%M %p").replace(" 0", " ")
            except ValueError:
                when = ""
            na = len([a for a in info.get("audio", []) if a["name"].lower().endswith(".wav")])
            kind = ("Book / campaign" if info.get("type") == "project" else "Note") + (
                "  + %d recording%s" % (na, "" if na == 1 else "s") if na else "")
            tv.insert("", "end", iid=b, values=(when, info.get("name", os.path.basename(b)), kind))
        f._sub.config(text="%d item%s. Deleted notes keep their audio here. Right-click an item to Restore it (back "
                           "where it was) or Delete it permanently (to the Windows Recycle Bin). Ctrl/Shift-click "
                           "to select several first." % (len(items), "" if len(items) == 1 else "s"))
        if items:
            f._empty.place_forget()
        else:
            f._empty.place(relx=0.5, rely=0.3, anchor="center")
        self.nav.item("trash", text="  \u267b   Trash" + ("    (%d)" % len(items) if items else ""))

    def _trash_sel(self):
        return [b for b in self.trashview._tv.selection() if os.path.isdir(b)]

    def _trash_menu(self, ev):
        tv = self.trashview._tv
        row = tv.identify_row(ev.y)
        m = T.menu(self.root)
        if not row:
            if tv.get_children():
                m.add_command(label="Empty trash\u2026", command=self.empty_trash)
                m.tk_popup(ev.x_root, ev.y_root)
            return
        if row not in tv.selection():
            tv.selection_set(row)
        sel = self._trash_sel()
        n = len(sel)
        what = "" if n == 1 else " (%d items)" % n
        m.add_command(label="Restore" + what, command=lambda: self.restore_items(sel))
        m.add_separator()
        m.add_command(label="Delete permanently" + what + " (to Recycle Bin)", command=lambda: self.purge_items(sel))
        m.tk_popup(ev.x_root, ev.y_root)

    def restore_items(self, bundles):
        n = 0
        for b in bundles:
            try:
                lib.restore(b)
                n += 1
            except Exception as e:
                log.exception("restore failed")
                T.info(self.root, "Nobu Notes", "Could not restore that item:\n%s" % e)
        self.refresh_library()
        if n:
            self.set_status("Restored %d item%s." % (n, "" if n == 1 else "s"))

    def purge_items(self, bundles):
        if not bundles:
            return
        ok = lib.to_recycle_bin(bundles)
        self.refresh_library()
        self.set_status("Sent %d item%s to the Recycle Bin." % (len(bundles), "" if len(bundles) == 1 else "s")
                        if ok else "Some items could not be moved to the Recycle Bin.")

    def empty_trash(self):
        items = [b for b, _ in lib.trash_items()]
        if not items:
            return
        if T.confirm(self.root, "Empty trash", "Send all %d item%s in the Trash to the Windows Recycle Bin?"
                     % (len(items), "" if len(items) == 1 else "s"), yes="Empty trash", danger=True):
            self.purge_items(items)

    def show_trash(self):
        self.ws.save_all()
        self._fill_trash()
        self._show(self.trashview)
        self._select_nav("trash")

    # ------------------------------------------------------------ navigation
    def _show(self, frame):
        for w in (self.ws.frame, self.home, self.inbox, self.projview, self.trashview):
            if w is not frame:
                w.pack_forget()
        if not frame.winfo_ismapped():
            frame.pack(fill="both", expand=True)
        self.view = frame
        self._update_note_context()

    def _update_note_context(self):
        """'edit this' / 'cut this' only work while a note is open and Nobu's window is in front."""
        try:
            on = bool(self._note_showing() and (self.root.state() == "normal" or self.ws.is_popped(self.editor))
                      and self.root.focus_displayof() is not None)
        except Exception:
            on = False
        if getattr(self, "engine", None) is not None:
            self.engine.note_open = on

    def show_home(self):
        self.ws.save_all()
        self._fill_home()
        self._show(self.home)
        self._select_nav("home")

    def show_inbox(self):
        self.ws.save_all()
        self._fill_list(self.inbox, C.INBOX_DIR)
        self._show(self.inbox)
        self._select_nav("inbox")

    def show_project(self, folder):
        self.ws.save_all()
        self.current_project = folder
        self._fill_list(self.projview, folder)
        self._show(self.projview)
        self.nav.selection_remove(self.nav.selection())

    def open_note(self, path, side=False, index=None, beside=None, popout=False, pane=None, tab_index=None):
        """Open a note as a tab of the page you're working in. side=True: on a new page beside it;
        pane=...: as a tab of that page; popout=True: in its own window. A note that is already open
        is simply brought to the front."""
        if not path or not os.path.isfile(path):
            return None
        self._refresh_spell_words()
        if popout:
            ed = self.ws.open_popout(path)
        else:
            ed = self.ws.open(path, side=side, index=index, beside=beside, pane=pane, tab_index=tab_index)
        if ed is None:
            return None
        if not self.ws.is_popped(ed):
            self._show(self.ws.frame)
        self.root.after(150, lambda p=path: self._maybe_ask_title(p))
        self._remember(path)
        folder = os.path.dirname(path)
        if not lib.is_inbox(folder):
            self.current_project = folder
        self._reveal(path)
        return ed

    def _reveal(self, path):
        """Show where a note or folder is: open its folders in the sidebar and highlight it."""
        if lib.is_inbox(os.path.dirname(path)) or lib.is_inbox(path):
            self._select_nav("inbox")
            return
        chain = []
        d = path if os.path.isdir(path) else os.path.dirname(path)
        while d and not lib.is_top_level(d) and len(chain) < 40:
            chain.append(d)
            nd = os.path.dirname(d)
            if nd == d:
                break
            d = nd
        chain.append(d)
        for folder in reversed(chain):
            if self.tree.exists(folder):
                self._tree_open(folder, True)
        if self.tree.exists(path):
            self._quiet_select(self.tree, path)
            self.nav.selection_remove(self.nav.selection())

    def _maybe_ask_title(self, path):
        """A recording that still has its automatic date name: ask for a proper title."""
        eds = self.editors_for(path)
        if not eds:
            return
        ed = eds[0]
        if not lib.is_auto_named(path) or ed.meta.get("titled") or not lib.note_info(path)["audio"]:
            return
        suggestion = " ".join(lib.preview(path, 200).split()[:6]).rstrip(".,;:!?\u2026")
        w = T.toplevel(self.root, "Name this recording")
        f = ttk.Frame(w, padding=18)
        f.pack(fill="both", expand=True)
        ttk.Label(f, text="Give this recording a title", style="H2.TLabel").pack(anchor="w")
        ttk.Label(f, text="It becomes the note's name and a centred title at the top of the page.",
                  style="Muted.TLabel").pack(anchor="w", pady=(2, 10))
        v = tk.StringVar(value=suggestion)
        e = ttk.Entry(f, textvariable=v, width=48, font=(T.UI_FAMILY, T.UI_SIZE + 2))
        e.pack(fill="x")
        e.select_range(0, "end")
        e.focus_set()
        res = {"v": None}

        def done(choice):
            res["v"] = choice
            w.destroy()
        bar = ttk.Frame(w, padding=(18, 0, 18, 16))
        bar.pack(side="bottom", fill="x", before=f)
        ttk.Button(bar, text="Save title", style="Accent.TButton", command=lambda: done("save")).pack(side="right")
        ttk.Button(bar, text="Later", command=lambda: done("later")).pack(side="right", padx=8)
        ttk.Button(bar, text="Don't ask for this note", command=lambda: done("never")).pack(side="left")
        e.bind("<Return>", lambda ev: done("save"))
        w.bind("<Escape>", lambda ev: done("later"))
        T.fit(w)
        w.grab_set()
        w.wait_window()
        if not ed.path or os.path.normcase(ed.path) != os.path.normcase(path):
            return
        if res["v"] == "never":
            ed.meta["titled"] = True
            ed.save()
        elif res["v"] == "save" and v.get().strip():
            title = v.get().strip()
            ed.meta["titled"] = True
            ed.add_title(title)
            ed.save()
            try:
                new = lib.rename_note(path, title)
                self._repath(path, new)
            except Exception as ex:
                log.exception("rename after title")
                T.info(self.root, "Nobu Notes", "The title was added, but the note couldn't be renamed:\n%s" % ex)
            self.refresh_library()
            if ed.path and self.tree.exists(ed.path):
                self._quiet_select(self.tree, ed.path)

    def _quiet_select(self, tv, iid):
        tv._quiet = True
        tv.selection_set(iid)
        tv.see(iid)
        self.root.after_idle(lambda: setattr(tv, "_quiet", False))

    def _select_nav(self, iid):
        self._quiet_select(self.nav, iid)
        self.tree.selection_remove(self.tree.selection())

    def _nav_go(self, iid):
        self.tree.selection_remove(self.tree.selection())
        if iid == "home":
            self.show_home()
        elif iid == "trash":
            self.show_trash()
        elif iid == "inbox":
            self.show_inbox()

    def _on_nav(self, _e=None):
        """Keyboard (arrow keys) in Home / Unassigned / Trash. Mouse clicks are handled on release."""
        if getattr(self.nav, "_quiet", False) or getattr(self.nav, "_mouse", None):
            return
        sel = self.nav.selection()
        if sel:
            self._nav_go(sel[0])

    def _nav_click(self, ev):
        pressed, self.nav._mouse = getattr(self.nav, "_mouse", None), None
        row = self.nav.identify_row(ev.y)
        if row and row == pressed and not self.dragdrop.dragging:
            self._quiet_select(self.nav, row)
            self._nav_go(row)

    def _nav_right(self, ev):
        row = self.nav.identify_row(ev.y)
        m = T.menu(self.root)
        if row == "inbox":
            m.add_command(label="Open Unassigned", command=self.show_inbox)
            m.add_command(label="+  New note in Unassigned\u2026", command=lambda: self.new_note(C.INBOX_DIR))
            m.add_command(label="Import documents into Unassigned\u2026", command=lambda: self.import_dialog(C.INBOX_DIR))
        elif row == "trash":
            m.add_command(label="Open Trash", command=self.show_trash)
            m.add_command(label="Empty trash\u2026", command=self.empty_trash)
        elif row == "home":
            m.add_command(label="Open Home", command=self.show_home)
        else:
            return
        m.tk_popup(ev.x_root, ev.y_root)

    # --- the Books & campaigns tree.  Only folders you have opened are filled in, so it stays quick
    #     however many notes there are.  Click = open, Shift/Ctrl-click = select several.
    def _tree_navigate(self, iid):
        if not iid or iid.startswith(("empty:", "lazy:")):
            return
        self.nav.selection_remove(self.nav.selection())
        if os.path.isdir(iid):
            self._tree_open(iid, True)
            if not (self.view is self.projview and self.current_project and
                    os.path.normcase(self.current_project) == os.path.normcase(iid)):
                self.show_project(iid)
        elif os.path.exists(iid):
            self.open_note(iid)

    def _on_tree(self, _e=None):
        """Keyboard selection only - mouse clicks open things when the button is released."""
        tv = self.tree
        if getattr(tv, "_quiet", False) or getattr(tv, "_mouse", False):
            return
        sel = tv.selection()
        if len(sel) == 1:
            self._tree_navigate(sel[0])

    def _in_toggle_zone(self, iid, x):
        """The open/close target: the triangle and the folder mark in front of the name."""
        tv = self.tree
        depth, p = 0, tv.parent(iid)
        while p:
            depth += 1
            p = tv.parent(p)
        sc = T.ui_scale(self.root)
        try:
            indent = int(float(str(ttk.Style(self.root).lookup("Treeview", "indent") or 18 * sc)))
        except ValueError:
            indent = int(18 * sc)
        if not hasattr(self, "_zone_mark_w"):
            import tkinter.font as tkf
            self._zone_mark_w = tkf.Font(font=(T.UI_FAMILY, T.UI_SIZE + 1)).measure(" \u25aa ")
        return x <= depth * indent + int(23 * sc) + self._zone_mark_w + 2

    def _tree_press(self, ev):
        tv = self.tree
        tv._mouse = True
        self._tree_click = None
        row = tv.identify_row(ev.y)
        if not row:
            if not ev.state & 0x5:
                tv.selection_remove(tv.selection())
            return "break"
        if row.startswith(("empty:", "lazy:")):
            return "break"
        if os.path.isdir(row) and self._in_toggle_zone(row, ev.x):
            self._zone_toggle(row)
            return "break"
        if ev.state & 0x5:               # Shift / Ctrl: add to the selection, don't open anything
            return None
        self._tree_click = row
        self.dragdrop._press(ev, tv)
        return None

    def _tree_release(self, ev):
        tv = self.tree
        dragged = self.dragdrop._release(ev, tv) == "break"
        row, self._tree_click = self._tree_click, None
        self.root.after_idle(lambda: setattr(tv, "_mouse", False))
        if self.dragdrop.cancelled:
            return "break"
        if dragged and not (row and tv.identify_row(ev.y) == row):
            return "break"                 # (a "drag" that ends on the same row was just a shaky click)
        if row and tv.identify_row(ev.y) == row:
            if row not in tv.selection():
                self._quiet_select(tv, row)
            if os.path.isdir(row) and tv.item(row, "open"):
                self._zone_toggle(row)          # clicking an open folder's name closes it again
            elif os.path.isdir(row):
                last = getattr(tv, "_last_toggle", (None, 0.0))
                if last[0] == row and time.time() - last[1] < 0.2:
                    return None                 # a bounce right after closing it
                tv._last_toggle = (row, time.time())
                self._tree_navigate(row)        # opens it and shows what's inside
            else:
                self._tree_navigate(row)
        return None

    def _zone_toggle(self, row):
        """Open/close a folder from its triangle. Two clicks closer together than 0.2 s are one click
        (a bounce), anything slower toggles again - so quick open-then-close works."""
        tv = self.tree
        last = getattr(tv, "_last_toggle", (None, 0.0))
        if last[0] == row and time.time() - last[1] < 0.2:
            return
        tv._last_toggle = (row, time.time())
        self._tree_open(row, not tv.item(row, "open"))

    def _tree_double(self, ev):
        """Windows reports any 2nd press within half a second as a double-click - even a Ctrl-click or
        the start of a drag. So treat it like a normal press, except that it never closes a folder."""
        tv = self.tree
        row = tv.identify_row(ev.y)
        if not row or row.startswith(("empty:", "lazy:")):
            return "break"
        if os.path.isdir(row) and self._in_toggle_zone(row, ev.x):
            self._zone_toggle(row)
            return "break"
        tv._mouse = True
        if ev.state & 0x4:                    # Ctrl: add / remove this one
            if row in tv.selection():
                tv.selection_remove(row)
            else:
                tv.selection_add(row)
            return "break"
        if ev.state & 0x1:                    # Shift: extend the selection to here
            self._tree_extend(row)
            return "break"
        self._tree_click = row                # opens on release (a folder only ever opens) - or drags
        self.dragdrop._press(ev, tv)
        return "break"

    def _tree_extend(self, row):
        tv = self.tree
        order = []

        def walk(parent):
            for i in tv.get_children(parent):
                order.append(i)
                if tv.item(i, "open"):
                    walk(i)
        walk("")
        anchor = tv.focus() or (tv.selection()[0] if tv.selection() else row)
        if anchor not in order or row not in order:
            tv.selection_set(row)
            return
        a, b = sorted((order.index(anchor), order.index(row)))
        tv.selection_set([i for i in order[a:b + 1] if not i.startswith(("empty:", "lazy:"))])

    def _tree_middle(self, ev):
        row = self.tree.identify_row(ev.y)
        if row and os.path.isfile(row):
            self.open_note(row, side=True)

    def _tree_open(self, iid, state=True):
        tv = self.tree
        if not tv.exists(iid):
            return
        if state:
            self._tree_fill_if_needed(iid)
        tv.item(iid, open=state)

    def _on_tree_open(self, _e=None):
        iid = self.tree.focus()
        if iid:
            self._tree_fill_if_needed(iid)

    def _tree_fill_if_needed(self, folder):
        tv = self.tree
        kids = tv.get_children(folder)
        if len(kids) == 1 and kids[0].startswith("lazy:"):
            tv.delete(kids[0])
            depth, p = 0, tv.parent(folder)
            while p:
                depth += 1
                p = tv.parent(p)
            self._tree_fill(folder, depth, set())

    def _tree_add_folder(self, parent_iid, folder, depth, opened):
        tv = self.tree
        ct = self._color_tag(tv, lib.folder_color(folder))
        is_open = folder in opened
        tv.insert(parent_iid, "end", iid=folder, text=" " + ("\u25aa  " if depth == 0 else "\u25b8  ")
                  + os.path.basename(folder), open=is_open, tags=("folder",) + ((ct,) if ct else ()))
        if is_open:
            self._tree_fill(folder, depth, opened)
        elif lib.has_children(folder):
            tv.insert(folder, "end", iid="lazy:" + folder, text="")
        else:
            tv.insert(folder, "end", iid="empty:" + folder, text="  (empty)", tags=("empty",))

    def _tree_fill(self, folder, depth, opened):
        tv = self.tree
        subs, notes = lib.contents(folder)
        for sub in subs:
            self._tree_add_folder(folder, sub, depth + 1, opened)
        unknown = []
        for p in notes:
            info = lib.cached_info(p)
            ct = self._color_tag(tv, info["color"]) if info else None
            tv.insert(folder, "end", iid=p, text="  " + lib.title(p), tags=(ct,) if ct else ())
            if info is None:
                unknown.append(p)
        if not notes and not subs:
            tv.insert(folder, "end", iid="empty:" + folder, text="  (empty)", tags=("empty",))
        if unknown:                    # names show at once; colour labels of notes not seen before follow
            T.later(tv, 1, self._tree_colors_later, unknown)

    def _tree_colors_later(self, paths):
        """Colour labels for sidebar notes Nobu hasn't read before, a batch at a time (a folder of thousands
        of notes opens at once instead of freezing while every note is opened)."""
        tv = self.tree
        for p in paths[:60]:
            if tv.exists(p):
                ct = self._color_tag(tv, lib.note_info(p)["color"])
                if ct:
                    tv.item(p, tags=(ct,))
        if paths[60:]:
            T.later(tv, 1, self._tree_colors_later, paths[60:])

    def _tree_selection(self):
        return [i for i in self.tree.selection() if not i.startswith(("empty:", "lazy:")) and os.path.exists(i)]

    def _on_tree_right(self, ev):
        tv = self.tree
        iid = tv.identify_row(ev.y)
        if not iid or iid.startswith(("empty:", "lazy:")):
            m = T.menu(self.root)
            m.add_command(label="New project\u2026", command=self.new_project)
            m.tk_popup(ev.x_root, ev.y_root)
            return
        sel = self._tree_selection()
        if iid not in sel:
            self._quiet_select(tv, iid)       # just highlight it - don't open anything
            sel = [iid]
        if len(sel) > 1:
            self._tree_bulk_menu(sel, ev)
            return
        m = T.menu(self.root)
        if os.path.isdir(iid):
            m.add_command(label="Open", command=lambda: self._tree_navigate(iid))
            m.add_command(label="New note here\u2026", command=lambda: self.new_note(iid))
            m.add_command(label="New sub-folder here\u2026", command=lambda: self.new_subfolder(iid))
            m.add_command(label="Rename\u2026", command=lambda: self.rename_project(iid))
            if not lib.is_top_level(iid):
                mv = T.menu(m)
                self._fill_move_menu(mv, [iid], with_inbox=False)
                m.add_cascade(label="Move to", menu=mv)
            m.add_command(label="Show in Windows Explorer", command=lambda: self._open(iid))
            m.add_separator()
            m.add_cascade(label="Colour label", menu=self._color_menu(m, [iid]))
            m.add_command(label="Import documents here\u2026", command=lambda: self.import_dialog(iid))
            m.add_command(label="Export / share this folder\u2026", command=lambda: self.export_dialog([], iid))
            m.add_separator()
            m.add_command(label="Delete (move to Trash)\u2026", command=lambda: self.delete_project(iid))
        else:
            m.add_command(label="Open", command=lambda: self.open_note(iid))
            m.add_command(label="Open side by side", command=lambda: self.open_note(iid, side=True))
            m.add_command(label="Open in its own window", command=lambda: self.open_note(iid, popout=True))
            m.add_command(label="Rename\u2026", command=lambda: self.rename_note(iid))
            mv = T.menu(m)
            self._fill_move_menu(mv, [iid])
            m.add_cascade(label="Move to", menu=mv)
            m.add_command(label="Export / share\u2026", command=lambda: self.export_dialog([iid]))
            m.add_cascade(label="Colour label", menu=self._color_menu(m, [iid]))
            m.add_separator()
            m.add_command(label="Delete (move to Trash)", command=lambda: self.delete_note(iid))
        m.tk_popup(ev.x_root, ev.y_root)

    def _tree_bulk_menu(self, sel, ev):
        """Several items selected (Shift/Ctrl-click): act on all of them at once."""
        notes = [x for x in sel if os.path.isfile(x)]
        folders = [x for x in sel if os.path.isdir(x)]
        what = []
        if folders:
            what.append("%d folder%s" % (len(folders), "" if len(folders) == 1 else "s"))
        if notes:
            what.append("%d note%s" % (len(notes), "" if len(notes) == 1 else "s"))
        m = T.menu(self.root)
        m.add_command(label="Selected: " + " and ".join(what), state="disabled")
        m.add_separator()
        m.add_cascade(label="Colour label (all %d)" % len(sel), menu=self._color_menu(m, sel))
        if notes:
            m.add_command(label="Open %d notes side by side" % min(6, len(notes)),
                          command=lambda: self.open_side_by_side(notes))
        movable = [x for x in sel if not (os.path.isdir(x) and lib.is_top_level(x))]
        if movable:
            mv = T.menu(m)
            self._fill_move_menu(mv, movable, with_inbox=not folders)
            m.add_cascade(label="Move %d item%s to" % (len(movable), "" if len(movable) == 1 else "s"), menu=mv)
        if notes:
            m.add_command(label="Export / share the %d notes\u2026" % len(notes), command=lambda: self.export_dialog(notes))
        m.add_separator()
        m.add_command(label="Delete all %d (move to Trash)\u2026" % len(sel), command=lambda: self._trash_mixed(sel))
        m.add_command(label="Clear selection", command=lambda: self.tree.selection_remove(self.tree.selection()))
        m.tk_popup(ev.x_root, ev.y_root)

    def refresh_library(self):
        tv = self.tree
        opened = set()

        def collect(parent):
            for i in tv.get_children(parent):
                if tv.item(i, "open"):
                    opened.add(i)
                    collect(i)
        collect("")
        sel = tv.selection()
        top = tv.yview()[0]
        tv.delete(*tv.get_children())
        projs = lib.projects()
        for proj in projs:
            self._tree_add_folder("", proj, 0, opened)
        if not projs:
            tv.insert("", "end", iid="empty:root", text="  Click + to add a book or campaign", tags=("empty",))
        keep = [s for s in sel if tv.exists(s)]
        if keep:
            tv._quiet = True
            tv.selection_set(keep)            # no "see": nothing is opened or scrolled by a refresh
            self.root.after_idle(lambda: setattr(tv, "_quiet", False))
        tv.yview_moveto(top)
        n = lib.inbox_count()
        self.nav.item("inbox", text="  \u2709   Unassigned" + ("    (%d)" % n if n else ""))
        tn = lib.trash_count()
        self.nav.item("trash", text="  \u267b   Trash" + ("    (%d)" % tn if tn else ""))
        if self.view is self.trashview:
            self._fill_trash()
        if self.view is self.inbox:
            self._fill_list(self.inbox, C.INBOX_DIR)
        elif self.view is self.projview and self.current_project and os.path.isdir(self.current_project):
            self._fill_list(self.projview, self.current_project)
        elif self.view is self.home:
            self._fill_home()
        self._save_cache_soon()

    def _save_cache_soon(self):
        if self._cache_job:
            self.root.after_cancel(self._cache_job)
        self._cache_job = self.root.after(5000, self._save_cache)

    def _save_cache(self):
        self._cache_job = None
        threading.Thread(target=lib.save_cache, daemon=True).start()

    # ------------------------------------------------------------ library actions
    def new_project(self):
        name = T.ask_string(self.root, "New project", "Name of the book, campaign or project:")
        if not name:
            return None
        try:
            p = lib.create_project(name)
        except Exception as e:
            T.info(self.root, "Nobu Notes", str(e))
            return None
        self.current_project = p
        self.refresh_library()
        self.show_project(p)
        self._quiet_select(self.tree, p)
        return p

    def new_subfolder(self, parent=None):
        parent = parent or self.current_project
        if not parent or not os.path.isdir(parent):
            return
        name = T.ask_string(self.root, "New sub-folder", "Name of the new folder inside \u201c%s\u201d\n"
                            "(e.g. Characters, Locations, Chapter 1, Session notes):" % os.path.basename(parent))
        if not name:
            return
        try:
            p = lib.create_folder(parent, name)
        except Exception as e:
            T.info(self.root, "Nobu Notes", str(e))
            return
        self.current_project = p
        self.refresh_library()
        self.show_project(p)
        if self.tree.exists(p):
            self.tree.see(p)
            self._quiet_select(self.tree, p)

    def new_note(self, folder=None):
        """A blank note to type into (no speaking needed). Goes where you are: the open folder,
        the folder of the note you're in, or Unassigned."""
        if not folder:
            if self.view is self.projview and self.current_project and os.path.isdir(self.current_project):
                folder = self.current_project
            elif self._note_showing():
                folder = os.path.dirname(self.editor.path)
            else:
                folder = C.INBOX_DIR
        name = T.ask_string(self.root, "New note", "Title for the new note in \u201c%s\u201d:\n"
                            "(any characters are fine, even quotation marks and /)" % (
                                "Unassigned" if lib.is_inbox(folder) else lib.crumbs(folder)))
        if not name or not name.strip():
            return
        p = lib.create_note(folder, name)
        self.refresh_library()
        self.open_note(p)

    def rename_project(self, folder=None):
        folder = folder or self.current_project
        if not folder:
            return
        name = T.ask_string(self.root, "Rename", "New name for \u201c%s\u201d:" % os.path.basename(folder),
                            os.path.basename(folder))
        if not name:
            return
        try:
            new = lib.rename_project(folder, name)
        except Exception as e:
            T.info(self.root, "Nobu Notes", str(e))
            return
        self._rebase_open_note(folder, new)
        self.refresh_library()
        if self.view is self.projview:
            self.show_project(new)

    def delete_project(self, folder=None):
        folder = folder or self.current_project
        if not folder:
            return
        n = len(lib.all_notes(folder))
        if not T.confirm(self.root, "Delete", "Move \u201c%s\u201d and everything in it (%d note%s, with their audio) "
                         "to the Trash?\n\nYou can restore it from Trash." % (os.path.basename(folder), n, "" if n == 1 else "s"),
                         yes="Move to Trash", danger=True):
            return
        for ed in self.ws.editors():
            if ed.path and self._inside(ed.path, folder):
                self.ws.close_editor(ed)
        parent = os.path.dirname(folder)
        lib.to_trash(folder)
        if not lib.is_top_level(folder) and os.path.isdir(parent):
            self.current_project = parent
            self.refresh_library()
            self.show_project(parent)
            return
        self.current_project = None
        self.refresh_library()
        self.show_home()

    def rename_note(self, path):
        name = T.ask_string(self.root, "Rename note", "New name (any characters are fine):", lib.title(path))
        if not name or not name.strip():
            return
        eds = self.editors_for(path)
        for ed in eds:
            if ed.dirty:
                ed.save()
        old = lib.title(path)
        try:
            new = lib.rename_note(path, name, sync_title=not eds)
        except Exception as e:
            T.info(self.root, "Nobu Notes", "Could not rename the note:\n%s" % e)
            return
        self._repath(path, new)
        for ed in eds:
            ed.replace_title(old, " ".join(name.split()))      # keep the title on the page in step
        self.refresh_library()

    def title_edited(self, text, ed=None):
        """The title on the page was changed: rename the note to match."""
        ed = ed or self.editor
        if not ed.path:
            return
        old = ed.path
        try:
            new = lib.rename_note(ed.path, text)
        except Exception:
            log.exception("rename from title")
            return
        if new != old:
            ed.meta["titled"] = True
            self._repath(old, new)
            self.refresh_library()
            if self.tree.exists(new):
                self._quiet_select(self.tree, new)
            self.set_status("Renamed the note to \u201c%s\u201d to match its title." % lib.title(new))

    def delete_note(self, path):
        self.trash_notes([path])

    def _fill_move_menu(self, m, paths, with_inbox=True):
        skip = [x for x in paths if os.path.isdir(x)]

        def add(menu, folder, top):
            if any(self._inside(folder, d) for d in skip):
                return
            subs = [x for x in lib.subfolders(folder) if not any(self._inside(x, d) for d in skip)]
            label = ("\u25aa  " if top else "\u25b8  ") + os.path.basename(folder)
            if subs:
                sm = T.menu(menu)
                sm.add_command(label="Into \u201c%s\u201d itself" % os.path.basename(folder),
                               command=lambda d=folder: self.move_notes(paths, d))
                sm.add_separator()
                for sub in subs:
                    add(sm, sub, False)
                sm.add_separator()
                sm.add_command(label="+  New sub-folder here\u2026", command=lambda d=folder: self._move_new(paths, d))
                menu.add_cascade(label=label, menu=sm)
            else:
                menu.add_command(label=label, command=lambda d=folder: self.move_notes(paths, d))
        projs = lib.projects()
        for proj in projs:
            add(m, proj, True)
        if projs:
            m.add_separator()
        m.add_command(label="+  New project\u2026", command=lambda: self._move_new(paths))
        if with_inbox and not skip:
            m.add_command(label="\u2709  Back to Unassigned", command=lambda: self.move_notes(paths, C.INBOX_DIR))

    def move_menu(self, widget, paths):
        paths = [p for p in paths if p]
        if not paths:
            T.info(self.root, "Nobu Notes", "Select one or more transcripts first.")
            return
        m = T.menu(self.root)
        self._fill_move_menu(m, paths)
        m.tk_popup(widget.winfo_rootx(), widget.winfo_rooty() + widget.winfo_height())

    def _move_new(self, paths, parent=None):
        if parent:
            name = T.ask_string(self.root, "New sub-folder", "Name of the new folder inside \u201c%s\u201d:"
                                % os.path.basename(parent))
        else:
            name = T.ask_string(self.root, "New project", "Name of the book, campaign or project:")
        if not name:
            return
        try:
            d = lib.create_folder(parent, name) if parent else lib.create_project(name)
        except Exception as e:
            T.info(self.root, "Nobu Notes", str(e))
            return
        self.move_notes(paths, d)

    def move_notes(self, paths, folder):
        moved = 0
        for p in paths:
            if not os.path.exists(p):
                continue
            try:
                if os.path.isdir(p):
                    new = lib.move_item(p, folder)
                    self._rebase_open_note(p, new)
                else:
                    for ed in self.editors_for(p):
                        if ed.dirty:
                            ed.save()
                    new = lib.move_item(p, folder)
                    self._repath(p, new)
                moved += 1
            except Exception as e:
                T.info(self.root, "Nobu Notes", str(e))
        if not lib.is_inbox(folder):
            self.current_project = folder
        self.refresh_library()
        dest = "Unassigned" if lib.is_inbox(folder) else "\u201c%s\u201d" % lib.crumbs(folder)
        if moved:
            self.set_status("Moved %d item%s to %s." % (moved, "" if moved == 1 else "s", dest))
        if self._note_showing() and self.tree.exists(self.editor.path):
            self._quiet_select(self.tree, self.editor.path)

    # ------------------------------------------------------------ UI thread plumbing
    def ui(self, fn, *a):
        self.uiq.put((fn, a))

    def _pump(self):
        try:
            while True:
                fn, a = self.uiq.get_nowait()
                try:
                    fn(*a)
                except Exception:
                    log.exception("ui callback failed")
        except queue.Empty:
            pass
        if not self.quitting:
            self.root.after(150, self._pump)

    def _tick_meter(self):
        if self.quitting:
            return
        shown = False
        try:
            shown = bool(self.root.winfo_viewable())
            if shown:
                from nobu_ui import level_pct
                self.side_meter["value"] = level_pct(self.engine.level)[0]
        except Exception:
            pass
        self.root.after(150 if shown else 1000, self._tick_meter)   # (keeps going even after a hiccup)

    def set_status(self, msg):
        self.status.config(text=msg)

    def show_progress(self, fraction=None):
        if fraction is None:
            self.progress.pack_forget()
            return
        if not self.progress.winfo_ismapped():
            self.progress.pack(side="bottom", fill="x", padx=18, before=self.status)
        self.progress["value"] = fraction * 100

    # ------------------------------------------------------------ window / tray
    def show_window(self):
        r = self.root
        r.deiconify()
        r.lift()
        T.dark_titlebar(r)
        try:
            r.focus_force()
        except tk.TclError:
            pass

    def _remember_window(self):
        """Window size and place, whether it was maximised, and the notes that are open."""
        r = self.root
        try:
            zoomed = r.state() == "zoomed"
        except tk.TclError:
            zoomed = False
        kw = {"maximized": zoomed, "open_tabs": self._session()}
        if not zoomed and r.state() == "normal":
            kw["geometry"] = r.geometry()      # (a maximised window keeps the size it returns to)
        self.cfg.update(**kw)

    def _session(self):
        """The notes open now, page by page; notes in their own windows count as tabs of the last page."""
        pages = []
        for p in self.ws.panes:
            tabs = [C.rel_to_home(ed.path) for ed in p.eds if ed.path]
            if tabs:
                cur = C.rel_to_home(p.cur.path) if p.cur is not None and p.cur.path else tabs[0]
                pages.append({"tabs": tabs, "cur": cur})
        pops = [C.rel_to_home(po.ed.path) for po in self.ws.popouts if po.ed.path]
        if pops and pages:
            pages[-1]["tabs"] += pops
        elif pops:
            pages.append({"tabs": pops, "cur": pops[0]})
        return pages

    def _restore_session(self):
        """Reopen the notes that were open last time (Settings > Reopen my notes). True if any opened."""
        from nobu_workspace import MAX_PANES, MAX_TABS
        if self.cfg.get("reopen_notes", True) is False:
            return False
        ws, first_pane = self.ws, None
        for pg in (self.cfg.get("open_tabs") or [])[:MAX_PANES]:
            if not isinstance(pg, dict):
                continue
            paths = [C.abs_from_home(r) for r in pg.get("tabs") or []]
            paths = [p for p in dict.fromkeys(paths) if os.path.isfile(p) and not ws.editors_for(p)][:MAX_TABS]
            if not paths:
                continue
            ed = ws.open(paths[0], side=ws.has_open(), index=len(ws.panes))
            pane = ws.pane_of(ed) if ed is not None else None
            if pane is None:
                continue
            for p in paths[1:]:
                ws.open(p, pane=pane)
            cur = [e for e in pane.eds if e.path and C.rel_to_home(e.path) == pg.get("cur")]
            ws.show_tab(pane, cur[0] if cur else pane.eds[0])
            first_pane = first_pane or pane
        if first_pane is None:
            return False
        ws.show_tab(first_pane, first_pane.cur)
        self._show(ws.frame)
        if self.editor is not None and self.editor.path:
            self._reveal(self.editor.path)
        return True

    def hide_window(self):
        self.ws.save_all()
        self._remember_window()
        if self.tray is None:
            self.root.iconify()
            return
        self.root.withdraw()
        if not self.told_tray:
            self.told_tray = True
            self.notify("Still listening", "Nobu Notes is in the system tray. Say “%s” any time." % C.WAKE_PHRASE)

    def on_close_window(self):
        if self.cfg["close_to_tray"] and self.tray is not None:
            self.hide_window()
        else:
            self.quit()

    def _start_tray(self):
        try:
            import pystray
            from nobu_ui import make_icon
            M, I = pystray.Menu, pystray.MenuItem
            menu = M(
                I("Open Nobu Notes", lambda i, it: self.ui(self.show_window), default=True),
                I(lambda it: "Stop recording" if self.state == "recording" else "Start recording now",
                  lambda i, it: self.ui(self.toggle_manual_record)),
                I(lambda it: "Resume listening" if self.state == "paused" else "Pause listening",
                  lambda i, it: self.ui(self.toggle_pause)),
                M.SEPARATOR,
                I("Settings…", lambda i, it: self.ui(self._show_and(self.open_settings))),
                M.SEPARATOR,
                I("Quit", lambda i, it: self.ui(self.quit)),
            )
            self.tray = pystray.Icon("NobuNotes", make_icon("idle"), "Nobu Notes", menu)
            self.tray.run_detached()
        except Exception:
            log.exception("system tray unavailable")
            self.tray = None

    def _show_and(self, fn):
        def go():
            self.show_window()
            fn()
        return go

    def _update_tray(self):
        if self.tray is None:
            return
        try:
            from nobu_ui import make_icon
            busy = self.transcriber.pending() > 0
            self.tray.icon = make_icon(self.state, busy)
            tip = {"idle": "Listening for “%s”" % C.WAKE_PHRASE, "recording": "Recording…",
                   "paused": "Paused", "nomic": "No microphone found"}.get(self.state, "Nobu Notes")
            if busy:
                tip += " (transcribing)"
            self.tray.title = ("Nobu Notes — " + tip)[:120]
            self.tray.update_menu()
        except Exception:
            pass

    def notify(self, title, msg):
        if self.tray is not None:
            try:
                self.tray.notify(msg, title)
            except Exception:
                pass

    # ------------------------------------------------------------ single instance
    def _start_instance_listener(self):
        s = self._server

        def loop():
            while True:
                try:
                    conn, _ = s.accept()
                    data = conn.recv(16)
                    conn.close()
                    if data.startswith(b"show"):
                        self.ui(self.show_window)
                except Exception:
                    return
        threading.Thread(target=loop, daemon=True).start()

    # ------------------------------------------------------------ engine / transcriber events
    def _beep(self, kind):
        if not self.cfg["cue_sounds"] or os.name != "nt":
            return
        seq = [(988, 90), (1319, 130)] if kind == "start" else [(988, 90), (659, 160)]

        def play():
            try:
                import winsound
                for f, d in seq:
                    winsound.Beep(f, d)
            except Exception:
                pass
        threading.Thread(target=play, daemon=True).start()

    def _engine_event(self, name, kw):
        mode = kw.get("mode", "record")
        if name == "state":
            self.state = kw["state"]
            self._refresh_status()
            self._update_tray()
        elif name == "recording_started":
            self._beep("start")
            self.badge.show(mode)
            if mode in ("edit", "cut"):
                self.cmd_editor = self.editor
                self.cmd_note = self.editor.path
                if mode == "edit":
                    self.editor.begin_dictation()
                else:
                    self.editor._show_action("\u2702  Recite the passage you want to cut, then pause\u2026",
                                             [("Stop", self.stop_manual_record, False)])
                self.set_status("Dictating\u2026" if mode == "edit" else "Listening for the passage to cut\u2026")
            else:
                self.set_status("Recording\u2026")
        elif name == "quiet":
            self.badge.set_quiet(kw["seconds_left"])
        elif name == "recording_finished":
            self._beep("stop")
            self.badge.hide()
            if mode in ("edit", "cut"):
                self.transcriber.submit(kw["path"], kw.get("started"), mode=mode, note=self.cmd_note)
                if mode == "edit":
                    self._cmd_ed().dictation_waiting()
                else:
                    self._cmd_ed()._show_action("Finding that passage\u2026", [])
            else:
                self.transcriber.submit(kw["path"], kw.get("started"))
                self.set_status("Saved %s (%.0f s). Transcribing\u2026" % (os.path.basename(kw["path"]), kw["seconds"]))
        elif name == "recording_discarded":
            self._beep("stop")
            self.badge.hide()
            if mode in ("edit", "cut"):
                self._cmd_ed().hide_action()
                self._cmd_ed().text.tag_remove("dictspot", "1.0", "end")
            self.set_status("Stopped - no speech was heard.")
        elif name == "teach_heard":
            if self.teach_win:
                self.teach_win.on_heard(kw["text"], kw["aliases"], kw["speech_rms"], kw.get("words"))
        elif name == "captured":
            if self.sample_cb:
                self.transcriber.submit_sample(kw["path"], kw.get("tag") or "")
        elif name == "test_done":
            cb, self.on_test_done = self.on_test_done, None
            if cb:
                cb(kw["path"])
        elif name == "error":
            self.set_status(kw["message"])
            log.error(kw["message"])

    def _tx_event(self, name, kw):
        mode = kw.get("mode", "record")
        if name == "queued":
            self._update_tray()
        elif name == "loading_model":
            self.set_status("Loading the transcription model\u2026")
        elif name == "progress":
            if mode == "record":
                self.show_progress(kw["fraction"])
                self.set_status("Transcribing\u2026 %d%%" % int(kw["fraction"] * 100))
        elif name == "sample_done":
            cb, self.sample_cb = self.sample_cb, None
            if self.sample_timer:
                self.root.after_cancel(self.sample_timer)
                self.sample_timer = None
            if cb:
                cb(kw.get("heard") or [])
        elif name == "done" and mode == "edit":
            self._cmd_ed(kw.get("note")).insert_dictation(kw.get("note"), kw["paragraphs"])
            self.refresh_library()
        elif name == "done" and mode == "cut":
            self._cmd_ed(kw.get("note")).propose_cut(kw.get("note"), " ".join(kw["paragraphs"]))
        elif name == "done":
            try:
                p = lib.make_inbox_note(kw.get("started"), kw["path"], kw["paragraphs"])
                self.set_status("New transcript in Unassigned: \u201c%s\u201d" % lib.title(p))
                self.notify("Transcript ready", "\u201c%s\u201d is waiting in Unassigned." % lib.title(p)[:80])
            except Exception:
                log.exception("could not create inbox note")
                self.set_status("Transcribed, but could not create the note. The text is saved next to the audio file.")
            if self.transcriber.pending() <= 1:
                self.show_progress(None)
            self.refresh_library()
            self._update_tray()
        elif name == "failed":
            self.show_progress(None)
            if mode == "sample":
                cb, self.sample_cb = self.sample_cb, None
                if cb:
                    cb(None)
                return
            if mode in ("edit", "cut"):
                self._cmd_ed(kw.get("note")).hide_action()
            self.set_status("Transcription failed: %s (the audio is safe in the Recordings folder)" % kw["message"])
            self.notify("Transcription failed", kw["message"][:200])
            self._update_tray()

    def _cmd_ed(self, note=None):
        """The open note a dictation / cut belongs to (it may have moved to another window meanwhile)."""
        note = note or self.cmd_note
        if note:
            eds = self.editors_for(note)
            if eds:
                return eds[0]
        ed = self.cmd_editor
        if ed is not None and ed in self.ws.editors():
            return ed
        return self.editor

    # --- in-note commands & dictionary samples
    def start_in_note(self, kind, ed=None):
        if ed is not None and ed is not self.editor:
            self.ws._activate(ed)
        if not self._note_showing():
            T.info(self.root, "Nobu Notes", "Open a note first.")
            return
        if self.state == "recording":
            self.stop_manual_record()
            return
        if self.state != "idle":
            T.info(self.root, "Nobu Notes", "Listening is paused or the microphone is unavailable.")
            return
        self.engine.command("start_recording", mode=kind)

    def capture_sample(self, word, cb):
        os.makedirs(os.path.join(C.LOGS_DIR, "samples"), exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(C.LOGS_DIR, "samples", "%s_%s.wav" % (lib.safe_name(word, "word"), stamp))
        self.sample_cb = cb
        self.engine.command("capture", path=path, tag=word)
        if self.sample_timer:
            self.root.after_cancel(self.sample_timer)

        def timeout():
            self.sample_timer = None
            if self.sample_cb is cb and not self.transcriber.busy and self.transcriber.pending() == 0:
                self.engine.command("cancel_capture")
                self.sample_cb = None
                cb(None)
        self.sample_timer = self.root.after(9000, timeout)

    # --- keyboard shortcuts
    def apply_hotkeys(self):
        from nobu_hotkeys import Hotkeys
        if self.hotkeys is None:
            self.hotkeys = Hotkeys(self, self._on_hotkey)
        self.hotkeys.apply({k: self.cfg.get("hotkey_" + k) or "" for k in ("record", "edit", "cut")})
        if self.hotkeys.failed:
            self.set_status("Shortcut %s is already used by another program - pick another in Settings."
                            % ", ".join(self.hotkeys.failed))

    def _on_hotkey(self, name):
        """Ctrl+Alt+R / E / X (or your own): press once to start, again to stop."""
        if self.state == "recording":
            self.stop_manual_record()
            return
        if name == "record":
            self.start_manual_record()
            return
        if not self.root.winfo_viewable() and not self.ws.is_popped(self.editor):
            self.show_window()
        if not self.editor.path:
            self.set_status("Open a note first, then press the shortcut to %s." % (
                "dictate into it" if name == "edit" else "cut a passage by voice"))
            return
        if not self._note_showing():
            self.open_note(self.editor.path)
        self.start_in_note(name)

    # --- colour labels (shown only in the sidebar and folder lists, never inside a note)
    def _color_menu(self, parent, paths):
        m = T.menu(parent)
        # one column per colour family, so 40 colours fit on screen
        for fam, cols in lib.COLOR_FAMILIES:
            for i, (name, col) in enumerate(cols):
                m.add_command(label="\u25a0  " + name, foreground=col, activeforeground=col,
                              columnbreak=1 if (i == 0 and fam != lib.COLOR_FAMILIES[0][0]) else 0,
                              command=lambda c=col: self.set_color(paths, c))
        m.add_command(label="\u2026  Custom colour\u2026", columnbreak=1, command=lambda: custom())
        m.add_command(label="\u2715  No colour", command=lambda: self.set_color(paths, None))

        def custom():
            from tkinter import colorchooser
            c = colorchooser.askcolor(parent=self.root, title="Colour label")
            if c and c[1]:
                self.set_color(paths, c[1])
        return m

    def set_color(self, paths, color):
        for p in paths:
            try:
                if os.path.isdir(p):
                    lib.set_folder_color(p, color)
                elif os.path.isfile(p):
                    eds = self.editors_for(p)
                    for ed in eds:
                        if color:
                            ed.meta["color"] = color
                        else:
                            ed.meta.pop("color", None)
                        ed.save()
                    if not eds:
                        lib.set_note_color(p, color)
            except Exception as e:
                log.exception("colour label")
                T.info(self.root, "Nobu Notes", "Could not set the colour:\n%s" % e)
        self.refresh_library()

    # --- writing: export / import / fonts
    def export_dialog(self, paths=None, folder=None):
        from nobu_share import ExportDialog
        paths = [p for p in (paths or []) if p]
        if not paths and not folder:
            if self._note_showing():
                paths = [self.editor.path]
            elif self.current_project:
                folder = self.current_project
        if not paths and not folder:
            T.info(self.root, "Export / share", "Open a note, or select notes or a folder, then export.")
            return
        ExportDialog(self, paths, folder)

    def import_dialog(self, folder=None):
        from nobu_share import import_dialog
        if folder is None:
            # into the folder you're looking at; otherwise Unassigned (never a folder you merely visited earlier)
            if self.view is self.projview and self.current_project and os.path.isdir(self.current_project):
                folder = self.current_project
            elif self._note_showing() and not lib.is_inbox(os.path.dirname(self.editor.path)):
                folder = os.path.dirname(self.editor.path)
            else:
                folder = C.INBOX_DIR
        import_dialog(self, folder)

    def import_files(self, files, folder):
        from nobu_share import import_files
        import_files(self, files, folder)

    def open_font_browser(self):
        from nobu_share import FontBrowser
        w = self.font_win
        if w and w.win.winfo_exists():
            w.win.lift()
            return
        self.font_win = FontBrowser(self)

    def _list_dnd(self, tv, f):
        """Drop documents onto a list to import them there."""
        try:
            from tkinterdnd2 import DND_FILES
            tv.drop_target_register(DND_FILES)

            def drop(ev):
                files = list(self.root.tk.splitlist(ev.data))
                folder = C.INBOX_DIR if f._inbox else self.current_project
                if folder:
                    self.root.after(10, lambda: self.import_files(files, folder))
                return "copy"
            tv.dnd_bind("<<Drop>>", drop)
        except Exception:
            pass

    def open_dictionary(self, prefill=None):
        from nobu_ui import DictionaryWindow
        if self.dict_win and self.dict_win.win.winfo_exists():
            self.dict_win.win.lift()
            if prefill:
                self.dict_win.add(prefill)
            return
        self.dict_win = DictionaryWindow(self.root, self, prefill)

    def _refresh_status(self):
        st = self.state
        col = {"idle": T.GREEN, "recording": T.RED, "paused": T.FAINT, "nomic": T.AMBER}.get(st, T.FAINT)
        txt = {"idle": "Listening", "recording": "Recording…",
               "paused": "Paused", "nomic": "No microphone", "stopped": "Stopped"}.get(st, st)
        self.pill_dot.config(fg=col)
        self.pill_txt.config(text=txt)
        self.rec_btn.config(text="■  Stop" if st == "recording" else "●  Record")
        self.pause_btn.config(text="▶" if st == "paused" else "❚❚")
        self.home_rec.config(text="■  Stop recording" if st == "recording" else "●  Record now")
        sc = self.cfg.get("hotkey_record") or ""
        hint = "(%s%s)" % (C.STOP_PHRASE if st == "recording" else C.WAKE_PHRASE, ("  \u00b7  " + sc) if sc else "")
        self.rec_hint.config(text=hint)
        self.home_rec_hint.config(text=hint)
        detail = {"idle": "Say “%s” any time. It stops after %d seconds of quiet, or when you say "
                          "“%s”." % (C.WAKE_PHRASE, int(self.cfg["silence_stop_seconds"]), C.STOP_PHRASE),
                  "recording": "Recording now…", "paused": "Listening is paused. Press ▶ to resume.",
                  "nomic": "No microphone could be opened. Check Settings."}.get(st, "")
        self.home_state.config(text=detail)

    # ------------------------------------------------------------ commands
    def start_manual_record(self):
        self.engine.command("start_recording")

    def stop_manual_record(self):
        self.engine.command("stop_recording")

    def toggle_manual_record(self):
        if self.state == "recording":
            self.stop_manual_record()
        else:
            self.start_manual_record()

    def toggle_pause(self):
        self.engine.command("resume" if self.state == "paused" else "pause")

    def open_settings(self):
        from nobu_ui import SettingsDialog
        if self.settings_win and self.settings_win.win.winfo_exists():
            self.settings_win.win.lift()
            return
        self.settings_win = SettingsDialog(self.root, self, self.cfg)

    def open_teach(self):
        from nobu_ui import TeachWindow
        if self.teach_win and self.teach_win.win.winfo_exists():
            self.teach_win.win.lift()
            return
        self.teach_win = TeachWindow(self.root, self)

    def open_diagnostics(self):
        from nobu_ui import DiagnosticsWindow
        if self.diag_win and self.diag_win.win.winfo_exists():
            self.diag_win.win.lift()
            return
        self.diag_win = DiagnosticsWindow(self.root, self)

    def apply_fonts(self):
        """Switch fonts live after they are changed in Settings."""
        import nobu_fonts
        self.body_family = nobu_fonts.pick(self.root, self.cfg["font_family"], nobu_fonts.BODY_FALLBACKS)
        self.heading_family = nobu_fonts.pick(self.root, self.cfg["heading_font"], nobu_fonts.HEADING_FALLBACKS)
        self.ui_family = nobu_fonts.pick(self.root, self.cfg["ui_font"], nobu_fonts.UI_FALLBACKS)
        T.set_ui_family(self.ui_family, 11 if self.ui_family != "Segoe UI" else 10)
        T.apply(self.root, self.heading_family)
        self.brand.config(font=(self.heading_family, 20))
        self.pill_txt.config(font=(T.UI_FAMILY, T.UI_SIZE))
        for ed in self.ws.editors():
            ed.set_fonts(self.body_family, self.heading_family, int(self.cfg["font_size"]))

    def apply_settings(self, mic_changed=False, models_changed=False):
        self.engine.command("reconfigure", reopen=mic_changed)
        self.apply_autostart()
        if models_changed:
            from nobu_models import missing
            need = missing([self.cfg["detect_model"], self.cfg["transcribe_model"]])
            if need:
                from nobu_ui import SetupWindow
                if not SetupWindow(self.root, need).run():
                    self.cfg.update(transcribe_model="medium.en", detect_model="tiny.en")
            self.detector.reload()
        self._refresh_status()
        self.set_status("Settings saved.")

    def apply_autostart(self):
        if os.name != "nt":
            return
        try:
            import winreg
            exe = os.environ.get("NOBU_EXE") or C.EXE_PATH
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                 r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE)
            if self.cfg["autostart"] and os.path.exists(exe):
                winreg.SetValueEx(key, "NobuNotes", 0, winreg.REG_SZ, '"%s" --tray' % exe)
            else:
                try:
                    winreg.DeleteValue(key, "NobuNotes")
                except FileNotFoundError:
                    pass
            winreg.CloseKey(key)
        except Exception:
            log.exception("could not update autostart")

    def transcribe_file_dialog(self):
        p = filedialog.askopenfilename(
            parent=self.root, title="Choose an audio file to transcribe",
            filetypes=[("Audio", "*.wav *.mp3 *.m4a *.flac *.ogg *.wma *.aac"), ("All files", "*.*")])
        if p:
            self.transcriber.submit(p, None)
            self.set_status("Transcribing \u201c%s\u201d\u2026 it will appear in Unassigned." % os.path.basename(p))

    def _offer_pending(self):
        todo = []
        for dp, _d, files in os.walk(C.RECORDINGS_DIR):
            for f in sorted(files):
                if f.lower().endswith(".wav") and not os.path.exists(os.path.join(dp, f[:-4] + ".txt")):
                    todo.append(os.path.join(dp, f))
        if not todo:
            return
        if not T.confirm(self.root, "Nobu Notes", "%d recording(s) have no transcript yet (probably from when the "
                         "program was closed).\n\nTranscribe them now? They will appear in Unassigned.\n\n(If you skip "
                         "them, you can still transcribe one later: \u2699 > Transcribe an audio file.)" % len(todo),
                         yes="Transcribe", no="Skip them"):
            for p in todo:
                try:
                    open(p[:-4] + ".txt", "w").close()
                except OSError:
                    pass
            return
        for p in todo:
            try:
                started = datetime.datetime.strptime(os.path.basename(p)[:19], "%Y-%m-%d_%H-%M-%S")
            except ValueError:
                started = None
            self.transcriber.submit(p, started)

    # ------------------------------------------------------------ quit
    def quit(self):
        if self.quitting:
            return
        self.quitting = True
        try:
            self.hotkeys.stop()
        except Exception:
            pass
        try:
            self._remember_window()
        except Exception:
            log.exception("remembering the window")
        try:
            self.engine.shutdown()
        except Exception:
            log.exception("engine shutdown")
        try:
            self.ws.save_all()
        except Exception:
            log.exception("final save")
        try:
            lib.save_cache(prune=True)
        except Exception:
            pass
        if self.tray is not None:
            try:
                self.tray.stop()
            except Exception:
                pass
        try:
            self.root.destroy()
        except Exception:
            pass
        os._exit(0)


def _claim_instance():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", PORT))
        s.listen(2)
        return s
    except OSError:
        try:
            c = socket.create_connection(("127.0.0.1", PORT), timeout=2)
            c.sendall(b"show")
            c.close()
        except OSError:
            pass
        return None


def main():
    tray_only = "--tray" in sys.argv
    if "--restart" in sys.argv:          # wait for the old copy to finish closing
        srv = None
        for _ in range(60):
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                s.bind(("127.0.0.1", PORT))
                s.listen(2)
                srv = s
                break
            except OSError:
                s.close()
                time.sleep(0.25)
        if srv is None:
            return
    else:
        srv = _claim_instance()
    if srv is None:
        return
    try:
        app = App(tray_only=tray_only)
        app._server = srv
        log.info("Nobu Notes %s starting (home=%s)", C.VERSION, C.HOME)
        app.run()
    except Exception:
        log.exception("fatal error")
        _fatal("Nobu Notes", "Nobu Notes hit a problem and had to stop.\n\nDetails were saved to:\n%s\n\n%s"
               % (_logfile, traceback.format_exc()[-800:]))


if __name__ == "__main__":
    main()
