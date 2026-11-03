"""Secondary windows: first-run setup, settings, teach-my-voice, diagnostics, recording badge, tray icon."""
import logging
import math
import os
import queue
import statistics
import sys
import threading
import tkinter as tk
from tkinter import ttk

from PIL import Image, ImageDraw

import nobu_models
import nobu_theme as T
from nobu_config import LOGS_DIR, HEARD_DIR, STOP_PHRASE, WAKE_PHRASE

log = logging.getLogger("nobu.ui")


def level_pct(rms):
    db = 20 * math.log10(max(rms, 1.0) / 32768.0)
    return max(0.0, min(100.0, (db + 60.0) / 60.0 * 100.0)), db


def play_wav(path):
    if sys.platform.startswith("win"):
        try:
            import winsound
            winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)
            return
        except Exception:
            pass
    from nobu_editor import open_path
    open_path(path)


# ---------------------------------------------------------------- first-run setup
def model_line(c):
    """One line about a transcription model: how good, how big, what computer it needs."""
    return "%s.  %s download.  Needs %d GB memory (uses about %.1f GB) and %s." % (
        c["quality"].capitalize(), ("%.1f GB" % (c["size_mb"] / 1000.0)) if c["size_mb"] >= 1000 else
        "%d MB" % c["size_mb"], c["ram_gb"], c["uses_gb"], c["cpu"])


class ModelChooser:
    """First start: pick the transcription model (with what each needs). The best one this computer runs
    comfortably is ticked. run() waits for the answer: the model's name, or None (closed: quit for now)."""

    def __init__(self, root):
        self.root = root
        self.result = None
        self.done = False
        ram, cores = nobu_models.computer()
        self.best = nobu_models.recommend(ram, cores)
        self.choice = tk.StringVar(value=self.best)
        w = self.win = T.toplevel(root, "Nobu Notes — choose a speech model")
        w.protocol("WM_DELETE_WINDOW", self.cancel)
        f = ttk.Frame(w, padding=20)
        f.pack(fill="both", expand=True)
        ttk.Label(f, text="Welcome to Nobu Notes", style="H2.TLabel").pack(anchor="w")
        ttk.Label(f, wraplength=620, justify="left", style="Muted.TLabel", text=(
            "Choose how Nobu turns your speech into text. It's downloaded once, then everything works offline. "
            "A better model makes fewer mistakes but needs a stronger computer. You can change it later in "
            "Settings.")).pack(anchor="w", pady=(6, 4))
        ttk.Label(f, style="Muted.TLabel", text="This computer: %s memory, %d processor cores." % (
            ("%.0f GB" % ram) if ram else "unknown", cores)).pack(anchor="w", pady=(0, 10))
        self.buttons = {}
        for c in nobu_models.CHOICES:
            row = ttk.Frame(f)
            row.pack(fill="x", pady=4)
            title = c["title"] + ("   (recommended for this computer)" if c["name"] == self.best else "")
            b = ttk.Radiobutton(row, text=title, value=c["name"], variable=self.choice)
            b.pack(anchor="w")
            self.buttons[c["name"]] = b
            ttk.Label(row, text=model_line(c), style="Muted.TLabel", wraplength=600,
                      justify="left").pack(anchor="w", padx=(26, 0))
        ttk.Label(f, wraplength=620, justify="left", style="Muted.TLabel", text=(
            "A small extra model (about %d MB) that listens for “Nobu” is downloaded too."
            % nobu_models.DETECT_MB)).pack(anchor="w", pady=(10, 0))
        b = ttk.Frame(f)
        b.pack(anchor="e", pady=(14, 0))
        ttk.Button(b, text="Not now", command=self.cancel).pack(side="right", padx=(6, 0))
        ttk.Button(b, text="Download and start", style="Accent.TButton", command=self.ok).pack(side="right")
        w.bind("<Return>", lambda e: self.ok())
        w.bind("<Escape>", lambda e: self.cancel())
        T.fit(w)
        w.deiconify()
        w.lift()

    def ok(self):
        self.result = self.choice.get()
        self.done = True
        self.win.destroy()

    def cancel(self):
        self.result = None
        self.done = True
        self.win.destroy()

    def run(self):
        while not self.done:
            self.root.update()
            self.root.after(50)
        return self.result


class SetupWindow:
    """Downloads speech models. Blocks (own loop) until done."""

    def __init__(self, root, names):
        self.root = root
        self.names = names
        self.cancelled = False
        self.q = queue.Queue()
        w = self.win = T.toplevel(root, "Nobu Notes — downloading speech models", 580, 270)
        w.protocol("WM_DELETE_WINDOW", self._cancel)
        f = ttk.Frame(w, padding=20)
        f.pack(fill="both", expand=True)
        ttk.Label(f, text="Getting the offline speech models", style="H2.TLabel").pack(anchor="w")
        sizes = dict({c["name"]: c["size_mb"] for c in nobu_models.CHOICES}, **{"tiny.en": 75})
        mb = sum(sizes.get(n, 200) for n in names)
        ttk.Label(f, wraplength=530, justify="left", style="Muted.TLabel", text=(
            "This needs the internet once (about %d MB). After that Nobu Notes works completely offline. "
            "You can leave this window open and do something else." % mb)).pack(anchor="w", pady=(6, 14))
        self.bar = ttk.Progressbar(f, maximum=1000, length=530)
        self.bar.pack(fill="x")
        self.label = ttk.Label(f, text="Starting…", style="Muted.TLabel")
        self.label.pack(anchor="w", pady=8)
        ttk.Button(f, text="Cancel", command=self._cancel).pack(anchor="e", pady=(8, 0))
        T.fit(w)
        w.deiconify()
        w.lift()

    def _cancel(self):
        self.cancelled = True

    def _work(self):
        try:
            nobu_models.download(self.names, lambda d, t, l: self.q.put(("p", d, t, l)), lambda: self.cancelled)
            self.q.put(("ok",))
        except nobu_models.Cancelled:
            self.q.put(("cancel",))
        except Exception as e:
            log.exception("model download failed")
            self.q.put(("err", str(e)))

    def run(self):
        while True:
            self.cancelled = False
            threading.Thread(target=self._work, daemon=True).start()
            result = self._pump()
            if result in ("ok", "cancel"):
                self.win.destroy()
                return result == "ok"
            if not T.confirm(self.win, "Nobu Notes", "The download stopped:\n\n%s\n\nCheck your internet "
                             "connection and try again." % result, yes="Try again", no="Cancel"):
                self.win.destroy()
                return False

    def _pump(self):
        while True:
            try:
                while True:
                    m = self.q.get_nowait()
                    if m[0] == "p":
                        _, done, total, label = m
                        if total:
                            self.bar["value"] = 1000.0 * done / total
                        self.label.config(text="%s    (%.0f of %.0f MB)" % (label, done / 1e6, total / 1e6))
                    else:
                        return m[1] if m[0] == "err" else m[0]
            except queue.Empty:
                pass
            self.win.update()
            self.win.after(80)


# ---------------------------------------------------------------- shared meter widget
class Meters:
    """Two live bars: microphone after gain, and after the noise filter."""

    def __init__(self, parent, app):
        self.app = app
        f = self.frame = ttk.Frame(parent)
        ttk.Label(f, text="Microphone (after gain)", style="Muted.TLabel").grid(row=0, column=0, sticky="w")
        self.b1 = ttk.Progressbar(f, maximum=100, length=300, style="Level.Horizontal.TProgressbar")
        self.b1.grid(row=0, column=1, sticky="we", padx=8, pady=2)
        self.l1 = ttk.Label(f, text="", style="Muted.TLabel", width=16)
        self.l1.grid(row=0, column=2, sticky="w")
        ttk.Label(f, text="After noise filter", style="Muted.TLabel").grid(row=1, column=0, sticky="w")
        self.b2 = ttk.Progressbar(f, maximum=100, length=300, style="Level.Horizontal.TProgressbar")
        self.b2.grid(row=1, column=1, sticky="we", padx=8, pady=2)
        self.l2 = ttk.Label(f, text="", style="Muted.TLabel", width=16)
        self.l2.grid(row=1, column=2, sticky="w")
        f.columnconfigure(1, weight=1)
        self._tick()

    def _tick(self):
        try:
            if not self.frame.winfo_exists():
                return
        except tk.TclError:
            return
        e = self.app.engine
        g = 10 ** (float(self.app.cfg["mic_gain_db"]) / 20.0)
        p1, db1 = level_pct(e.raw_level * g)
        clip = e.peak * g >= 32000
        self.b1.config(value=p1, style="Hot.Horizontal.TProgressbar" if clip else "Level.Horizontal.TProgressbar")
        self.l1.config(text="TOO LOUD" if clip else "%.0f dB" % db1)
        p2, db2 = level_pct(e.level)
        self.b2.config(value=p2)
        talking = e.vad.speech
        self.l2.config(text=("%.0f dB  ● voice" % db2) if talking else "%.0f dB" % db2)
        T.later(self.frame, 120, self._tick)


# ---------------------------------------------------------------- settings
class SettingsDialog:
    LIVE = ("mic_gain_db", "noise_reduction", "speech_sensitivity")

    def __init__(self, root, app, cfg):
        self.app, self.cfg, self.root = app, cfg, root
        self.orig = {k: cfg[k] for k in self.LIVE}
        w = self.win = T.toplevel(root, "Nobu Notes — settings", 700, 600)
        w.protocol("WM_DELETE_WINDOW", self.cancel)
        # scrollable body (the settings are taller than many screens)
        body = ttk.Frame(w)
        body.pack(fill="both", expand=True)
        self.canvas = cv = tk.Canvas(body, bg=T.BG, highlightthickness=0, bd=0)
        vsb = ttk.Scrollbar(body, orient="vertical", command=cv.yview)
        cv.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        cv.pack(side="left", fill="both", expand=True)
        outer = ttk.Frame(cv, padding=18)
        self._outer_id = cv.create_window(0, 0, window=outer, anchor="nw")
        outer.bind("<Configure>", lambda e: cv.configure(scrollregion=cv.bbox("all")))
        cv.bind("<Configure>", lambda e: cv.itemconfigure(self._outer_id, width=e.width))
        w.bind("<MouseWheel>", lambda e: cv.yview_scroll(int(-e.delta / 120), "units"))
        w.bind("<Button-4>", lambda e: cv.yview_scroll(-3, "units"))
        w.bind("<Button-5>", lambda e: cv.yview_scroll(3, "units"))

        def section(text):
            ttk.Label(outer, text=text, style="H2.TLabel").pack(anchor="w", pady=(10, 4))

        def row():
            r = ttk.Frame(outer)
            r.pack(fill="x", pady=3)
            return r

        section("Microphone")
        r = row()
        ttk.Label(r, text="Device", width=22).pack(side="left")
        self.devs = self._input_devices()
        names = ["Windows default"] + [n for _, n in self.devs]
        self.mic = ttk.Combobox(r, values=names, state="readonly", width=44)
        cur, label = cfg["mic_device"], "Windows default"
        for i, n in self.devs:
            if i == cur:
                label = n
        self.mic.set(label)
        self.mic.pack(side="left", fill="x", expand=True)

        self.gain = tk.DoubleVar(value=float(cfg["mic_gain_db"]))
        self._slider(outer, "Gain", self.gain, -6, 30, self._gain_text, self._live)
        self.nr = tk.DoubleVar(value=float(cfg["noise_reduction"]))
        self._slider(outer, "Noise filter", self.nr, 0, 1, self._nr_text, self._live)
        ttk.Label(outer, style="Muted.TLabel", wraplength=600, text=(
            "The noise filter removes the steady sound of your room (fan, AC, hum). It keeps learning that "
            "sound by itself, every moment you're not talking, so a fan switched on or off is picked up within "
            "a second or two. Raise it until the background is quiet in the test playback; too high can make "
            "your voice sound thin.")).pack(anchor="w")
        self.orig_sound = tk.BooleanVar(value=cfg.get("transcribe_original", True) is not False)
        ttk.Checkbutton(outer, text="Transcribe from the natural sound (recommended: the speech model recognises "
                                    "words more accurately without the noise filter)",
                        variable=self.orig_sound).pack(anchor="w", pady=(4, 0))
        ttk.Label(outer, style="Muted.TLabel", wraplength=600, text=(
            "The noise filter is still used to listen for \u201cNobu\u201d commands. Untick this to keep "
            "noise-filtered sound in your recordings instead.")).pack(anchor="w")
        self.sens = tk.DoubleVar(value=float(cfg["speech_sensitivity"]))
        self._slider(outer, "Speech sensitivity", self.sens, 0, 1, self._sens_text, self._live)

        self.meters = Meters(outer, app)
        self.meters.frame.pack(fill="x", pady=(8, 4))
        r = row()
        ttk.Button(r, text="●  Record a 6-second test", command=self._test).pack(side="left")
        self.test_lbl = ttk.Label(r, text="", style="Muted.TLabel")
        self.test_lbl.pack(side="left", padx=6)

        section("Listening")
        r = row()
        ttk.Label(r, text="Stop after silence (s)", width=22).pack(side="left")
        self.silence = tk.DoubleVar(value=cfg["silence_stop_seconds"])
        ttk.Spinbox(r, from_=3, to=60, increment=1, textvariable=self.silence, width=6).pack(side="left")
        self.strict = tk.DoubleVar(value=cfg["wake_match_threshold"])
        self._slider(outer, "Wake word strictness", self.strict, 0.3, 0.8,
                     lambda v: "%.2f  (%s)" % (v, "forgiving" if v < 0.45 else "strict" if v > 0.62 else "normal"))
        r = row()
        ttk.Label(r, text="Wake word model", width=22).pack(side="left")
        self.dmodel = ttk.Combobox(r, values=["base.en", "tiny.en"], state="readonly", width=12)
        self.dmodel.set(cfg["detect_model"])
        self.dmodel.pack(side="left")
        ttk.Label(r, text="  base = better at hearing “Nobu”; tiny = lightest", style="Muted.TLabel").pack(side="left")
        self.bare = tk.BooleanVar(value=cfg["accept_bare_phrase"])
        ttk.Checkbutton(outer, text="Also accept just “record this” when “Nobu” is misheard",
                        variable=self.bare).pack(anchor="w", pady=2)
        self.cues = tk.BooleanVar(value=cfg["cue_sounds"])
        ttk.Checkbutton(outer, text="Beep when recording starts and stops", variable=self.cues).pack(anchor="w", pady=2)

        section("Dictation, cuts & shortcuts")
        r = row()
        ttk.Label(r, text="Dictation (edit) stops", width=22).pack(side="left")
        self._edit_opts = [(4, "after 4 s of quiet"), (6, "after 6 s of quiet"), (8, "after 8 s of quiet"),
                           (12, "after 12 s of quiet"), (20, "after 20 s of quiet"),
                           (0, "only when I say \u201cNobu, end recording\u201d or press the shortcut")]
        self.edit_end = ttk.Combobox(r, values=[t for _, t in self._edit_opts], state="readonly", width=52)
        cur = float(cfg.get("edit_silence_seconds", 8))
        self.edit_end.set(min(self._edit_opts, key=lambda o: abs(o[0] - cur) if cur else (0 if o[0] == 0 else 99))[1])
        self.edit_end.pack(side="left")
        self.confirm_cut = tk.BooleanVar(value=bool(cfg.get("confirm_cut", True)))
        ttk.Checkbutton(outer, text="Ask before deleting the passage found by \u201cNobu, cut this\u201d "
                                    "(off = delete straight away; Ctrl+Z still brings it back)",
                        variable=self.confirm_cut).pack(anchor="w", pady=2)
        self.confirm_edit = tk.BooleanVar(value=bool(cfg.get("confirm_edit", False)))
        ttk.Checkbutton(outer, text="Show what I dictated and let me confirm before it goes into the note",
                        variable=self.confirm_edit).pack(anchor="w", pady=2)
        ttk.Label(outer, style="Muted.TLabel", wraplength=600, text=(
            "Keyboard shortcuts work from any program. Press once to start, press again to stop. Click a shortcut "
            "to change it.")).pack(anchor="w", pady=(6, 2))
        self.hotkeys = {}
        for key, label in (("record", "Start / stop a recording"), ("edit", "Dictate into the open note"),
                           ("cut", "Cut a passage by voice")):
            r = row()
            ttk.Label(r, text=label, width=28).pack(side="left")
            var = tk.StringVar(value=cfg.get("hotkey_" + key) or "")
            self.hotkeys[key] = var
            ttk.Button(r, textvariable=var, width=16, command=lambda k=key: self._capture_hotkey(k)).pack(side="left")
            ttk.Button(r, text="None", command=lambda k=key, v=var: self._clear_hotkey(k, v)).pack(side="left", padx=6)

        section("Appearance")
        r = row()
        ttk.Label(r, text="Colour theme", width=22).pack(side="left")
        self._theme_keys = list(T.THEMES)
        self.theme = ttk.Combobox(r, values=[T.THEMES[k]["label"] for k in self._theme_keys], state="readonly",
                                  width=24)
        self.theme.set(T.THEMES.get(cfg.get("theme") or "dark", T.THEMES["dark"])["label"])
        self.theme.pack(side="left")
        ttk.Label(r, text="  (Nobu restarts to switch)", style="Muted.TLabel").pack(side="left")
        sw = tk.Frame(outer, bg=T.BG)
        sw.pack(anchor="w", pady=(2, 6))
        for k in self._theme_keys:     # little swatches: page colour + accent
            th = T.THEMES[k]
            c = tk.Canvas(sw, width=int(46 * T.ui_scale(w)), height=int(28 * T.ui_scale(w)), bg=th["BG"],
                          highlightthickness=1, highlightbackground=T.BORDER, cursor="hand2")
            cw, ch = int(46 * T.ui_scale(w)), int(28 * T.ui_scale(w))
            c.create_rectangle(0, 0, cw * 0.3, ch, fill=th["SIDEBAR"], outline="")
            c.create_rectangle(cw * 0.42, ch * 0.18, cw * 0.9, ch, fill=th["PAPER"], outline="")
            c.create_rectangle(cw * 0.05, ch * 0.2, cw * 0.25, ch * 0.4, fill=th["ACCENT"], outline="")
            c.pack(side="left", padx=(0, 6))
            c.bind("<Button-1>", lambda e, k=k: self.theme.set(T.THEMES[k]["label"]))
            c.bind("<Enter>", lambda e, t=th["label"]: self.theme_hint.config(text=t))
            c.bind("<Leave>", lambda e: self.theme_hint.config(text=""))
        self.theme_hint = ttk.Label(outer, text="", style="Muted.TLabel")
        self.theme_hint.pack(anchor="w")
        r = row()
        ttk.Button(r, text="\u270e  Make my own colours\u2026", command=lambda: ThemeEditor(self.root, self.app, self)
                   ).pack(side="left")
        ttk.Label(r, text="  (also: the colour of the drop highlight shown when dragging notes)",
                  style="Muted.TLabel").pack(side="left")

        section("Fonts")
        import nobu_fonts
        fams = nobu_fonts.families(root)
        r = row()
        ttk.Label(r, text="Note text font", width=22).pack(side="left")
        self.body_font = ttk.Combobox(r, values=fams, width=30)
        self.body_font.set(app.body_family)
        self.body_font.pack(side="left")
        r = row()
        ttk.Label(r, text="Headings & titles font", width=22).pack(side="left")
        self.head_font = ttk.Combobox(r, values=fams, width=30)
        self.head_font.set(app.heading_family)
        self.head_font.pack(side="left")
        r = row()
        ttk.Label(r, text="Interface font", width=22).pack(side="left")
        self.ui_font = ttk.Combobox(r, values=fams, width=30)
        self.ui_font.set(app.ui_family)
        self.ui_font.pack(side="left")
        ttk.Label(r, text="  (sidebar, folders, buttons; fully applies after restart)",
                  style="Muted.TLabel").pack(side="left")
        r = row()
        ttk.Label(r, text="Text size", width=22).pack(side="left")
        self.fsize = tk.IntVar(value=int(cfg["font_size"]))
        ttk.Spinbox(r, from_=9, to=28, increment=1, textvariable=self.fsize, width=6).pack(side="left")
        self.fetch_fonts = tk.BooleanVar(value=cfg.get("fetch_fonts", True) is not False)
        ttk.Checkbutton(outer, text="When I paste text in a font I don't have, download it if there's a free copy "
                        "(Google Fonts)", variable=self.fetch_fonts).pack(anchor="w", pady=2)
        ttk.Label(outer, style="Muted.TLabel", wraplength=600, text=(
            "To add your own fonts: Fonts\u2026 (toolbar or gear menu) > \u201c+ Add fonts\u2026\u201d. They work "
            "straight away.")).pack(anchor="w")

        section("Transcription & program")
        r = row()
        ttk.Label(r, text="Transcription model", width=22).pack(side="left")
        self.model = ttk.Combobox(r, values=[c["name"] for c in nobu_models.CHOICES], state="readonly", width=15)
        self.model.set(cfg["transcribe_model"])
        self.model.pack(side="left")
        ram, cores = nobu_models.computer()
        ttk.Label(outer, style="Muted.TLabel", wraplength=600, justify="left", text="\n".join(
            "%s: %s" % (c["name"], model_line(c)) for c in nobu_models.CHOICES) + (
            "\nThis computer: %.0f GB memory, %d cores (best fit: %s). A new model downloads once when you Save."
            % (ram, cores, nobu_models.recommend(ram, cores)))).pack(anchor="w")
        self.tray = tk.BooleanVar(value=cfg["close_to_tray"])
        ttk.Checkbutton(outer, text="Closing the window keeps listening in the system tray",
                        variable=self.tray).pack(anchor="w", pady=2)
        self.auto = tk.BooleanVar(value=cfg["autostart"])
        ttk.Checkbutton(outer, text="Start Nobu Notes (in the tray) when Windows starts",
                        variable=self.auto).pack(anchor="w", pady=2)
        self.reopen = tk.BooleanVar(value=cfg.get("reopen_notes", True) is not False)
        ttk.Checkbutton(outer, text="Reopen the notes I had open (with their pages and tabs) when Nobu starts",
                        variable=self.reopen).pack(anchor="w", pady=2)

        b = ttk.Frame(w, padding=(18, 8, 18, 14))
        b.pack(side="bottom", fill="x", before=body)
        ttk.Button(b, text="Teach Nobu my voice\u2026", command=self._save_then_teach).pack(side="left")
        ttk.Button(b, text="My dictionary\u2026", command=self._save_then_dict).pack(side="left", padx=6)
        ttk.Button(b, text="Cancel", command=self.cancel).pack(side="right", padx=(6, 0))
        ttk.Button(b, text="Save", style="Accent.TButton", command=self.save).pack(side="right")
        self._wheel_scrolls_page(outer, cv)
        outer.update_idletasks()
        cv.configure(width=outer.winfo_reqwidth(),
                     height=min(outer.winfo_reqheight(), w.winfo_screenheight() - 220))
        T.fit(w)

    # -- helpers
    @staticmethod
    def _wheel_scrolls_page(parent, cv):
        """The mouse wheel scrolls the settings page - it never changes a drop-down or number box
        that happens to be under the pointer."""
        def scroll(n):
            cv.yview_scroll(n, "units")
            return "break"
        stack = [parent]
        while stack:
            wdg = stack.pop()
            stack.extend(wdg.winfo_children())
            if isinstance(wdg, (ttk.Combobox, ttk.Spinbox, ttk.Scale)):
                wdg.bind("<MouseWheel>", lambda e: scroll(int(-e.delta / 120)))
                wdg.bind("<Button-4>", lambda e: scroll(-3))
                wdg.bind("<Button-5>", lambda e: scroll(3))

    def _slider(self, parent, label, var, lo, hi, fmt, on_change=None):
        r = ttk.Frame(parent)
        r.pack(fill="x", pady=3)
        ttk.Label(r, text=label, width=22).pack(side="left")
        lbl = ttk.Label(r, text=fmt(var.get()), width=22, style="Muted.TLabel")

        def changed(_v=None):
            lbl.config(text=fmt(var.get()))
            if on_change:
                on_change()
        ttk.Scale(r, from_=lo, to=hi, variable=var, command=changed).pack(side="left", fill="x", expand=True)
        lbl.pack(side="left", padx=(8, 0))
        return lbl

    @staticmethod
    def _gain_text(v):
        return "%+.0f dB" % round(v)

    @staticmethod
    def _nr_text(v):
        return "Off" if v < 0.03 else "%d%%" % round(v * 100)

    @staticmethod
    def _sens_text(v):
        return "%d%%  (%s)" % (round(v * 100), "picks up quiet voices" if v > 0.65 else
                               "ignores more sounds" if v < 0.35 else "balanced")

    def _live(self):
        self.cfg.set_temp(mic_gain_db=round(float(self.gain.get())), noise_reduction=round(float(self.nr.get()), 2),
                          speech_sensitivity=round(float(self.sens.get()), 2))
        self.app.engine.command("reconfigure")

    def _test(self):
        self.test_lbl.config(text="Recording… talk normally for 6 seconds")
        self.app.engine.command("test_record", seconds=6, path=os.path.join(LOGS_DIR, "mic_test.wav"))
        self.app.on_test_done = self._test_done

    def _test_done(self, path):
        try:
            self.test_lbl.config(text="Playing back what Nobu hears…")
            play_wav(path)
            T.later(self.test_lbl, 6500, lambda: self.test_lbl.config(text=""))
        except tk.TclError:
            pass

    def _input_devices(self):
        out = []
        try:
            import sounddevice as sd
            api = sd.query_hostapis(sd.default.hostapi)
            devs = sd.query_devices()
            for i in api["devices"]:
                if devs[i]["max_input_channels"] > 0:
                    out.append((i, devs[i]["name"]))
        except Exception:
            log.exception("could not list microphones")
        return out

    def _save_then_teach(self):
        self.save()
        self.app.root.after(50, self.app.open_teach)

    def _save_then_dict(self):
        self.save()
        self.app.root.after(50, self.app.open_dictionary)

    def _clear_hotkey(self, key, var):
        var.set("")
        self.cfg.update(**{"hotkey_" + key: ""})
        self.app.apply_hotkeys()
        self._hints()
        self.app._refresh_status()

    def _hints(self):
        for ed in self.app.ws.editors():
            ed.update_shortcut_hints()

    def _capture_hotkey(self, key):
        from nobu_hotkeys import combo_from_event, valid
        w = T.toplevel(self.win, "New shortcut")
        f = ttk.Frame(w, padding=22)
        f.pack(fill="both", expand=True)
        ttk.Label(f, text="Press the new shortcut now", style="H2.TLabel").pack(anchor="w")
        ttk.Label(f, text="Any single key (like F9, Insert, a number-pad key or even a letter), or a "
                          "combination like Ctrl+R.  Esc cancels.", style="Muted.TLabel",
                  wraplength=460, justify="left").pack(anchor="w", pady=(4, 10))
        shown = ttk.Label(f, text="\u2026", font=(T.UI_FAMILY, T.UI_SIZE + 6, "bold"))
        shown.pack(anchor="w")
        msg = ttk.Label(f, text="", style="Muted.TLabel", wraplength=460, justify="left")
        msg.pack(anchor="w", pady=(8, 0))
        ask = ttk.Frame(f)
        pending = {"combo": None}
        if hasattr(self.app, "hotkeys") and self.app.hotkeys:
            self.app.hotkeys.stop()              # so the current shortcuts can be pressed here

        def done():
            w.destroy()
            if hasattr(self.app, "hotkeys"):
                self.app.apply_hotkeys()
                self.app._refresh_status()

        def accept(combo):
            self.hotkeys[key].set(combo)
            self.cfg.update(**{"hotkey_" + key: combo})      # saved right away (kept after restarts)
            self._hints()
            T.later(w, 300, done)

        def use_anyway():
            if pending["combo"]:
                accept(pending["combo"])

        def pick_another():
            pending["combo"] = None
            ask.pack_forget()
            msg.config(text="Press another key\u2026")
            shown.config(text="\u2026")
        ttk.Button(ask, text="Use it anyway", style="Accent.TButton", command=use_anyway).pack(side="left")
        ttk.Button(ask, text="Pick another", command=pick_another).pack(side="left", padx=8)

        def press(ev):
            if ev.keysym == "Escape" and not (ev.state & 0x4):
                done()
                return "break"
            if pending["combo"]:
                return "break"                    # waiting for "Use it anyway" / "Pick another"
            combo = combo_from_event(ev)
            if not combo:
                return "break"
            shown.config(text=combo)
            ok, why, warn = valid(combo)
            others = [k for k, v in self.hotkeys.items() if k != key and v.get() == combo]
            if not ok:
                msg.config(text=why)
            elif others:
                msg.config(text="That shortcut is already used for another action.")
            elif warn:
                pending["combo"] = combo
                msg.config(text=warn)
                ask.pack(anchor="w", pady=(10, 0))
                T.fit(w)
            else:
                msg.config(text="")
                accept(combo)
            return "break"
        w.bind("<KeyPress>", press)
        w.protocol("WM_DELETE_WINDOW", done)
        T.fit(w)
        w.grab_set()
        w.focus_force()

    def cancel(self):
        self.cfg.set_temp(**self.orig)
        self.app.engine.command("reconfigure")
        self.win.destroy()

    def save(self):
        sel = self.mic.get()
        dev, name = None, ""
        for i, n in self.devs:
            if n == sel:
                dev, name = i, n
        old = (self.cfg["mic_device"], self.cfg["transcribe_model"], self.cfg["detect_model"])
        try:
            sil = max(3.0, min(60.0, float(self.silence.get())))
        except Exception:
            sil = 8.0
        self.cfg.update(
            mic_device=dev, mic_device_name=name, silence_stop_seconds=sil,
            mic_gain_db=round(float(self.gain.get())), noise_reduction=round(float(self.nr.get()), 2),
            speech_sensitivity=round(float(self.sens.get()), 2),
            wake_match_threshold=round(float(self.strict.get()), 2),
            accept_bare_phrase=bool(self.bare.get()), cue_sounds=bool(self.cues.get()),
            close_to_tray=bool(self.tray.get()), autostart=bool(self.auto.get()), reopen_notes=bool(self.reopen.get()),
            fetch_fonts=bool(self.fetch_fonts.get()), transcribe_original=bool(self.orig_sound.get()),
            transcribe_model=self.model.get(), detect_model=self.dmodel.get())
        self.orig = {k: self.cfg[k] for k in self.LIVE}
        models_changed = (old[1] != self.cfg["transcribe_model"] or old[2] != self.cfg["detect_model"])
        try:
            size = max(9, min(28, int(self.fsize.get())))
        except Exception:
            size = int(self.cfg["font_size"])
        fonts_changed = (self.body_font.get().strip() != self.app.body_family or
                         self.ui_font.get().strip() != self.app.ui_family or
                         self.head_font.get().strip() != self.app.heading_family or size != int(self.cfg["font_size"]))
        if fonts_changed:
            self.cfg.update(font_family=self.body_font.get().strip(), heading_font=self.head_font.get().strip(),
                            ui_font=self.ui_font.get().strip(), font_size=size)
        es = dict((t, v) for v, t in self._edit_opts).get(self.edit_end.get(), 8)
        hk = {"hotkey_" + k: v.get() for k, v in self.hotkeys.items()}
        hotkeys_changed = any(self.cfg.get(k) != v for k, v in hk.items())
        self.cfg.update(edit_silence_seconds=es, confirm_cut=bool(self.confirm_cut.get()),
                        confirm_edit=bool(self.confirm_edit.get()), **hk)
        labels = [T.THEMES[k]["label"] for k in self._theme_keys]
        new_theme = self._theme_keys[labels.index(self.theme.get())] if self.theme.get() in labels else "dark"
        theme_changed = new_theme != (self.cfg.get("theme") or "dark")
        if theme_changed:
            self.cfg.update(theme=new_theme)
        self.win.destroy()        # read every widget BEFORE this line
        self.app.apply_settings(mic_changed=(old[0] != dev), models_changed=models_changed)
        if hotkeys_changed:
            self.app.apply_hotkeys()
            self._hints()
            self.app._refresh_status()
        if fonts_changed:
            self.app.apply_fonts()
        if theme_changed and T.confirm(self.root, "Colour theme", "Restart Nobu now to switch to the \u201c%s\u201d theme?"
                                       % T.THEMES[new_theme]["label"], yes="Restart now", no="Later"):
            self.app.restart()


# ---------------------------------------------------------------- your own colour theme
class ThemeEditor:
    def __init__(self, root, app, settings=None):
        from tkinter import colorchooser
        self.cc = colorchooser
        self.app, self.root, self.settings = app, root, settings
        start = app.cfg.get("custom_theme") or {}
        base = T.THEMES.get(T.THEME, T.THEMES["dark"])
        self.colors = {k: start.get(k) or base[k] for k, _ in T.CUSTOM_KEYS}
        w = self.win = T.toplevel(root, "My colours")
        f = ttk.Frame(w, padding=18)
        f.pack(fill="both", expand=True)
        ttk.Label(f, text="Make your own colour theme", style="H2.TLabel").pack(anchor="w")
        ttk.Label(f, text="Click a colour to change it. The preview shows how it will look.",
                  style="Muted.TLabel").pack(anchor="w", pady=(2, 8))
        r = ttk.Frame(f)
        r.pack(fill="x", pady=(0, 8))
        ttk.Label(r, text="Start from:").pack(side="left")
        keys = [k for k in T.THEMES if k != "custom"]
        cb = ttk.Combobox(r, values=[T.THEMES[k]["label"] for k in keys], state="readonly", width=22)
        cb.pack(side="left", padx=6)
        if T.THEME in keys:
            cb.set(T.THEMES[T.THEME]["label"])
        cb.bind("<<ComboboxSelected>>", lambda e: self._start_from(keys[cb.current()]))
        body = ttk.Frame(f)
        body.pack(fill="both", expand=True)
        grid = ttk.Frame(body)
        grid.pack(side="left", fill="y")
        self.swatches = {}
        for i, (k, label) in enumerate(T.CUSTOM_KEYS):
            ttk.Label(grid, text=label).grid(row=i, column=0, sticky="w", pady=3)
            sw = tk.Label(grid, text="      ", bg=self.colors[k], relief="solid", bd=1, cursor="hand2")
            sw.grid(row=i, column=1, padx=8)
            hx = ttk.Label(grid, text=self.colors[k], style="Muted.TLabel")
            hx.grid(row=i, column=2, sticky="w")
            sw.bind("<Button-1>", lambda e, k=k: self._pick(k))
            self.swatches[k] = (sw, hx)
        sc = T.ui_scale(w)
        self.pv = tk.Canvas(body, width=int(320 * sc), height=int(260 * sc), highlightthickness=1,
                            highlightbackground=T.BORDER)
        self.pv.pack(side="left", padx=(18, 0))
        # the shade that shows where a dragged note will land (saved straight away, works with any theme)
        dz = ttk.Frame(f)
        dz.pack(fill="x", pady=(14, 0))
        ttk.Label(dz, text="Drop highlight", font=T.UI_BOLD).grid(row=0, column=0, sticky="w")
        ttk.Label(dz, text="the shade that shows where a dragged note will land (changes right away, for every theme)",
                  style="Muted.TLabel").grid(row=0, column=1, columnspan=4, sticky="w", padx=(8, 0))
        self.drop_col = app.cfg.get("drop_color") or ""
        self._save_job = None
        self.drop_sw = tk.Label(dz, text="      ", bg=self.drop_col or self.colors["ACCENT"], relief="solid", bd=1,
                                cursor="hand2")
        self.drop_sw.grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.drop_sw.bind("<Button-1>", lambda e: self._pick_drop())
        ttk.Label(dz, text="Strength").grid(row=1, column=1, sticky="e", padx=(12, 4), pady=(6, 0))
        self.drop_alpha = tk.DoubleVar(value=float(app.cfg.get("drop_alpha") or 0.30))
        ttk.Scale(dz, from_=0.12, to=0.7, variable=self.drop_alpha, length=int(160 * sc),
                  command=lambda v: self._drop_changed()).grid(row=1, column=2, sticky="w", pady=(6, 0))
        ttk.Button(dz, text="Same as accent", command=self._reset_drop).grid(row=1, column=3, padx=(10, 0),
                                                                             pady=(6, 0))
        bar = ttk.Frame(w, padding=(18, 0, 18, 14))
        bar.pack(side="bottom", fill="x", before=f)
        ttk.Button(bar, text="Use these colours", style="Accent.TButton", command=self._save).pack(side="right")
        ttk.Button(bar, text="Cancel", command=self._close).pack(side="right", padx=8)
        w.protocol("WM_DELETE_WINDOW", self._close)
        self._preview()
        T.fit(w)
        w.grab_set()

    def _close(self):
        if self._save_job:                 # a drop-highlight change still waiting to be written
            self.win.after_cancel(self._save_job)
            self._store_drop()
        self.win.destroy()

    def _pick_drop(self):
        c = self.cc.askcolor(color=self.drop_col or self.colors["ACCENT"], parent=self.win, title="Drop highlight colour")
        if c and c[1]:
            self.drop_col = c[1].lower()
            self._drop_changed()

    def _reset_drop(self):
        self.drop_col = ""
        self._drop_changed()

    def _drop_changed(self):
        """Used right away (the next drag shows it); written to disk once the slider settles."""
        self.drop_sw.config(bg=self.drop_col or self.colors["ACCENT"])
        self.app.cfg.set_temp(drop_color=self.drop_col, drop_alpha=round(float(self.drop_alpha.get()), 2))
        if self._save_job:
            self.win.after_cancel(self._save_job)
        self._save_job = T.later(self.win, 400, self._store_drop)
        self._preview()

    def _store_drop(self):
        self._save_job = None
        self.app.cfg.save()

    def _start_from(self, key):
        th = T.THEMES[key]
        self.colors = {k: th[k] for k, _ in T.CUSTOM_KEYS}
        for k, (sw, hx) in self.swatches.items():
            sw.config(bg=self.colors[k])
            hx.config(text=self.colors[k])
        self._preview()

    def _pick(self, k):
        c = self.cc.askcolor(color=self.colors[k], parent=self.win, title="Choose a colour")
        if c and c[1]:
            self.colors[k] = c[1].lower()
            sw, hx = self.swatches[k]
            sw.config(bg=self.colors[k])
            hx.config(text=self.colors[k])
            self._preview()

    def _preview(self):
        th = T.build_custom(self.colors)
        c = self.pv
        c.delete("all")
        W, H = int(c.cget("width")), int(c.cget("height"))
        c.configure(bg=th["BG"])
        c.create_rectangle(0, 0, W * 0.3, H, fill=th["SIDEBAR"], outline="")
        c.create_text(12, 16, text="Nobu Notes", anchor="w", fill=th["FG"], font=(T.UI_FAMILY, 10, "bold"))
        for i, (txt, sel) in enumerate((("Home", False), ("Unassigned", True), ("My Book", False))):
            y = 44 + i * 24
            if sel:
                c.create_rectangle(4, y - 10, W * 0.3 - 4, y + 10, fill=th["SELECT"], outline="")
            c.create_text(14, y, text=txt, anchor="w", fill=th["SELECT_FG"] if sel else th["FG"],
                          font=(T.UI_FAMILY, 9))
        c.create_text(14, H - 40, text="secondary text", anchor="w", fill=th["MUTED"], font=(T.UI_FAMILY, 8))
        c.create_rectangle(10, H - 26, W * 0.3 - 10, H - 8, fill=th["ACCENT_DARK"], outline="")
        c.create_text(W * 0.15, H - 17, text="Record", fill="#ffffff", font=(T.UI_FAMILY, 8))
        c.create_rectangle(W * 0.3, 0, W, 34, fill=th["PANEL"], outline="")
        c.create_text(W * 0.33, 17, text="B  I  U   Styles", anchor="w", fill=th["FG"], font=(T.UI_FAMILY, 9))
        c.create_rectangle(W * 0.3, 34, W, H, fill=th["DESK"], outline="")
        c.create_rectangle(W * 0.4, 44, W * 0.92, H, fill=th["PAPER"], outline="")
        c.create_text(W * 0.66, 64, text="Chapter One", fill=th["INK"], font=(T.UI_FAMILY, 11, "bold"))
        for i in range(5):
            c.create_line(W * 0.45, 86 + i * 16, W * 0.87 - (30 if i == 4 else 0), 86 + i * 16, fill=th["INK"])
        c.create_text(W * 0.45, H - 20, text="a link", anchor="w", fill=th["ACCENT"], font=(T.UI_FAMILY, 9))
        # the drop highlight over the right half of the page, as it will look
        dc = self.drop_col or th["ACCENT"]
        a = float(self.drop_alpha.get())
        c.create_rectangle(W * 0.66, 44, W * 0.92, H, fill=T.mix(th["PAPER"], dc, a), outline="")
        c.create_text(W * 0.79, H / 2, text="drop\nhere", fill=th["INK"], font=(T.UI_FAMILY, 8), justify="center")

    def _save(self):
        self.app.cfg.update(custom_theme=dict(self.colors))
        T.register_custom(self.colors)
        self._close()
        st = self.settings
        if st and st.win.winfo_exists():
            # keep everything else changed in Settings, and switch its theme choice to "Custom"
            if "custom" not in st._theme_keys:
                st._theme_keys.append("custom")
            st.theme.configure(values=[T.THEMES[k]["label"] for k in st._theme_keys])
            st.theme.set(T.THEMES["custom"]["label"])
            st.save()             # saves all settings and offers the restart
            return
        self.app.cfg.update(theme="custom")
        if T.confirm(self.root, "My colours", "Restart Nobu now to use your colours?", yes="Restart now",
                     no="Later"):
            self.app.restart()


# ---------------------------------------------------------------- teach my voice
class TeachWindow:
    """Learn how the speech model hears *your* voice saying each command, then let you test them."""
    STEPS = [("record", "Nobu, record this", 3), ("stop", "Nobu, end recording", 3),
             ("edit", "Nobu, edit this", 2), ("cut", "Nobu, cut this", 2)]

    def __init__(self, root, app):
        self.app, self.root = app, root
        self.stage = "intro"          # intro -> noise -> phrase (index) -> test -> done
        self.idx = 0
        self.count = 0
        self.aliases = []
        self.samples = {k: [] for k, _, _ in self.STEPS}
        self.rms = []
        w = self.win = T.toplevel(root, "Teach Nobu your voice", 700, 600)
        w.protocol("WM_DELETE_WINDOW", self.close)
        f = ttk.Frame(w, padding=22)
        f.pack(fill="both", expand=True)
        self.head = ttk.Label(f, text="Teach Nobu your voice", style="Title.TLabel")
        self.head.pack(anchor="w")
        self.body = ttk.Label(f, text="", wraplength=640, justify="left")
        self.body.pack(anchor="w", pady=(10, 10))
        self.big = tk.Label(f, text="", bg=T.PANEL, fg=T.FG, font=(T.UI_FAMILY, 20, "bold"), pady=18)
        self.big.pack(fill="x", pady=6)
        self.progress = ttk.Label(f, text="", style="Muted.TLabel")
        self.progress.pack(anchor="w")
        self.meters = Meters(f, app)
        self.meters.frame.pack(fill="x", pady=6)
        self.log = tk.Text(f, height=7, bg=T.PANEL, fg=T.FG, relief="flat", font=("Consolas", 10),
                           state="disabled", highlightthickness=0)
        self.log.pack(fill="both", expand=True, pady=6)
        self.log.tag_configure("ok", foreground=T.GREEN)
        self.log.tag_configure("bad", foreground=T.AMBER)
        b = ttk.Frame(f)
        b.pack(side="bottom", fill="x", pady=(8, 0), before=self.head)
        self.btn = ttk.Button(b, text="Start", style="Accent.TButton", command=self.next)
        self.btn.pack(side="right")
        self.skip = ttk.Button(b, text="Skip this phrase", command=self._skip)
        ttk.Button(b, text="Close", command=self.close).pack(side="right", padx=6)
        self.body.config(text=(
            "About two minutes. Nobu first listens to your room for a few seconds. Then you say each voice "
            "command a few times - record, end, edit and cut - and Nobu remembers exactly how it hears you say "
            "them. At the end you can test them all.\n\n"
            "Tips: say each phrase in one go, the way you normally would, then pause until the counter moves on. "
            "It's fine if it hears you slightly wrong - that's what it learns from."))
        self.big.config(text="Press Start when you are ready")
        T.fit(w)

    # ------------------------------------------------------------ flow
    def _log(self, line, tag=None):
        self.log.config(state="normal")
        self.log.insert("end", line + "\n", (tag,) if tag else ())
        self.log.see("end")
        self.log.config(state="disabled")

    def next(self):
        if self.stage == "intro":
            self.stage = "noise"
            self.btn.config(state="disabled")
            self.app.engine.command("teach", on=True)
            self.app.engine.command("relearn_noise")
            self.body.config(text="Please stay quiet while Nobu learns the background noise of your room.")
            self._count(4)
        elif self.stage == "phrase":
            self._phrase_done()
        elif self.stage == "test":
            self._finish()

    def _count(self, n):
        if n <= 0:
            self._log("Room noise learned (about %.0f dB)." % self.app.engine.frontend.noise_level_db())
            self.stage, self.idx, self.count = "phrase", 0, 0
            self.skip.pack(side="right", padx=6)
            self._show_phrase()
            return
        self.big.config(text="Quiet please\u2026  %d" % n)
        T.later(self.win, 1000, self._count, n - 1)

    def _show_phrase(self):
        kind, phrase, n = self.STEPS[self.idx]
        what = {"record": "starts a recording", "stop": "ends a recording or dictation",
                "edit": "dictates into the open note", "cut": "deletes a passage you then read out"}[kind]
        self.body.config(text="Say the phrase below, then pause. (It %s.)" % what)
        self.big.config(text="Say:  \u201c%s\u201d" % phrase)
        self.progress.config(text="Phrase %d of %d  \u00b7  %d of %d times" % (self.idx + 1, len(self.STEPS),
                                                                            self.count + 1, n))

    def _skip(self):
        if self.stage == "phrase":
            self._phrase_done()

    def _phrase_done(self):
        self.idx += 1
        self.count = 0
        if self.idx >= len(self.STEPS):
            self._start_test()
        else:
            self._show_phrase()

    def _start_test(self):
        self.stage = "test"
        self.skip.pack_forget()
        self.btn.config(state="normal", text="Finish")
        self.body.config(text=(
            "Now try them out. Say any of the four phrases - Nobu shows what it recognised, using what it just "
            "learned. If one keeps failing, say it a couple more times here: it keeps learning. Press Finish "
            "when you're happy."))
        self.big.config(text="Try any phrase")
        self.progress.config(text="")

    # ------------------------------------------------------------ hearing
    def on_heard(self, text, aliases, rms, words=None):
        import nobu_match as M
        words = words or []
        if self.stage == "phrase":
            kind, phrase, n = self.STEPS[self.idx]
            self.rms.append(rms)
            self._learn(kind, words)
            self._log("Heard: \u201c%s\u201d" % (text or "(nothing clear)"))
            self.count += 1
            if self.count >= n:
                self._phrase_done()
            else:
                self._show_phrase()
        elif self.stage == "test":
            got = self._recognise(words)
            if got:
                self._log("\u2714  %s   \u2190  \u201c%s\u201d" % (got, text), "ok")
                self.big.config(text="\u2714  " + got)
            else:
                self._log("\u2718  not recognised   \u2190  \u201c%s\u201d" % (text or "(nothing clear)"), "bad")
                self.big.config(text="Not recognised - try again")
                # learn from a miss when it is clearly one of the phrases with a misheard part
                key = M.phrase_key(words)
                for kind, phrase, _n in self.STEPS:
                    if M._ratio(key, M.norm(phrase.replace("Nobu", "noboo"))) >= 0.6:
                        self._learn(kind, words)
                        break

    def _learn(self, kind, words):
        import nobu_match as M
        for a in M.learn_aliases(words, kind):
            if a not in self.aliases:
                self.aliases.append(a)
        key = M.phrase_key(words)
        toks = len([w for w in words if M.norm(w.text)])
        if 6 <= len(key) <= 40 and toks <= 7 and key not in self.samples[kind]:
            self.samples[kind].append(key)

    def _merged(self):
        cfg = self.app.cfg
        old_al = list(cfg["wake_aliases"] or [])
        aliases = (self.aliases + [a for a in old_al if a not in self.aliases])[:30]
        old_s = cfg.get("phrase_samples") or {}
        samples = {}
        for k, _p, _n in self.STEPS:
            new = self.samples.get(k, [])
            samples[k] = (new + [x for x in old_s.get(k, []) if x not in new])[:10]
        return aliases, samples

    def _recognise(self, words):
        import nobu_match as M
        cfg = self.app.cfg
        aliases, samples = self._merged()
        args = (cfg["wake_match_threshold"], cfg["accept_bare_phrase"], tuple(aliases))
        ok, _t, _s = M.match_stop(words, *args, samples=samples)
        if ok:
            return "end recording"
        kind, _t, _s = M.match_command(words, *args, in_note=True, samples=samples)
        return {"record": "record this", "edit": "edit this", "cut": "cut this"}.get(kind)

    def _finish(self):
        self.app.engine.command("teach", on=False)
        cfg = self.app.cfg
        aliases, samples = self._merged()
        cfg.update(wake_aliases=aliases, phrase_samples=samples)
        cur_gain = float(cfg["mic_gain_db"])
        med = statistics.median(self.rms) if self.rms else 0
        suggest = cur_gain
        if med > 0:
            suggest = max(-6, min(24, round(cur_gain + 20 * math.log10(3000.0 / med))))
        self.stage = "done"
        self.big.config(text="All done \u2714")
        learned = sum(len(v) for v in self.samples.values())
        msg = "Nobu learned %d way%s you say its commands%s." % (
            learned, "" if learned == 1 else "s",
            (" and these spellings of \u201cNobu\u201d: " + ", ".join(self.aliases[:8])) if self.aliases else "")
        if abs(suggest - cur_gain) >= 3:
            msg += ("\n\nYour voice is coming in %s. Suggested gain: %+d dB (now %+d dB)."
                    % ("quietly" if suggest > cur_gain else "loud", suggest, cur_gain))
            self.suggest = suggest
            self.btn.config(state="normal", text="Use %+d dB gain and finish" % suggest, command=self._apply_gain)
        else:
            msg += "\n\nYour microphone level looks good."
            self.btn.config(state="normal", text="Close", command=self.close)
        self.body.config(text=msg)

    def _apply_gain(self):
        self.app.cfg.update(mic_gain_db=self.suggest)
        self.app.engine.command("reconfigure")
        self.close()

    def close(self):
        if self.stage in ("phrase", "test") and any(self.samples.values()):
            aliases, samples = self._merged()          # keep what was learned even if closed early
            self.app.cfg.update(wake_aliases=aliases, phrase_samples=samples)
        self.app.engine.command("teach", on=False)
        self.app.teach_win = None
        self.win.destroy()


# ---------------------------------------------------------------- diagnostics
class DiagnosticsWindow:
    def __init__(self, root, app):
        self.app = app
        w = self.win = T.toplevel(root, "Nobu Notes — what is it hearing?", 720, 520)
        f = ttk.Frame(w, padding=14)
        f.pack(fill="both", expand=True)
        self.state = ttk.Label(f, text="", style="H2.TLabel")
        self.state.pack(anchor="w")
        Meters(f, app).frame.pack(fill="x", pady=6)
        ttk.Label(f, wraplength=680, style="Muted.TLabel", text=(
            "Each time you speak, the line below shows what the wake-word model heard and whether it counted "
            "(✔). If “Nobu” comes out as something odd, run “Teach Nobu my voice” or lower the "
            "strictness in Settings. Detector: %s." % ("neural (Silero)" if app.engine.vad.kind == "neural"
                                                       else "energy (fallback)"))).pack(anchor="w")
        self.box = tk.Text(f, height=14, state="disabled", wrap="word", font=("Consolas", 10), bg=T.PANEL,
                           fg=T.FG, relief="flat", highlightthickness=0)
        self.box.pack(fill="both", expand=True, pady=6)
        r = ttk.Frame(f)
        r.pack(side="bottom", fill="x", before=self.state)
        self.save_var = tk.BooleanVar(value=app.cfg["save_heard_clips"])
        ttk.Checkbutton(r, text="Save what it hears (logs\\heard) for troubleshooting", variable=self.save_var,
                        command=lambda: app.cfg.update(save_heard_clips=bool(self.save_var.get()))).pack(side="left")
        from nobu_editor import open_path
        ttk.Button(r, text="Open folder", command=lambda: (os.makedirs(HEARD_DIR, exist_ok=True),
                                                         open_path(HEARD_DIR))).pack(side="right")
        self._shown = None
        T.fit(w)
        self._tick()

    def _tick(self):
        try:
            if not self.win.winfo_exists():
                return
        except tk.TclError:
            return
        e = self.app.engine
        names = {"idle": "● Listening for “%s”" % WAKE_PHRASE,
                 "recording": "● RECORDING — say “%s” to finish" % STOP_PHRASE,
                 "paused": "Paused", "nomic": "No microphone available", "stopped": "Stopped"}
        self.state.config(text=names.get(e.state, e.state))
        dets = list(e.detections)
        if dets != self._shown:            # only redraw when something new was heard (keeps your scroll place)
            self._shown = dets
            lines = ["%s  %-5s %s  “%s”   (match %.2f)" % (ts, kind, "✔" if ok else "·", text, score)
                     for ts, kind, text, ok, score in reversed(dets)]
            self.box.config(state="normal")
            self.box.delete("1.0", "end")
            self.box.insert("1.0", "\n".join(lines) or "(nothing heard yet - say something)")
            self.box.config(state="disabled")
        T.later(self.win, 500, self._tick)


# ---------------------------------------------------------------- recording badge
class Badge:
    def __init__(self, root):
        w = self.win = tk.Toplevel(root)
        w.overrideredirect(True)
        w.attributes("-topmost", True)
        try:
            w.attributes("-alpha", 0.94)
        except tk.TclError:
            pass
        f = tk.Frame(w, bg=T.PANEL, padx=14, pady=8, highlightthickness=1, highlightbackground=T.BORDER)
        f.pack()
        tk.Label(f, text="●", fg=T.RED, bg=T.PANEL, font=("Segoe UI", 14)).pack(side="left")
        self.lbl = tk.Label(f, text="", fg=T.FG, bg=T.PANEL, font=(T.UI_FAMILY, T.UI_SIZE + 1))
        self.lbl.pack(side="left", padx=8)
        self.mode = "record"
        self.set_quiet(None)
        w.withdraw()

    def set_quiet(self, left):
        mode = self.mode
        what = {"edit": "Dictating into your note", "cut": "Recite the passage to cut"}.get(mode, "Recording")
        if left is None:
            self.lbl.config(text="%s\u2026   say \u201c%s\u201d or pause to finish" % (what, STOP_PHRASE)
                            if mode != "record" else "Recording\u2026   say \u201c%s\u201d to finish" % STOP_PHRASE)
        elif left <= 0:
            self.lbl.config(text="Finishing\u2026")
        else:
            self.lbl.config(text="%s\u2026   quiet \u2014 stopping in %d s unless you keep talking" % (what, left))
        try:
            if self.win.winfo_viewable():
                self._place()
        except tk.TclError:
            pass

    def _place(self):
        w = self.win
        w.update_idletasks()
        w.geometry("+%d+%d" % ((w.winfo_screenwidth() - w.winfo_reqwidth()) // 2, 12))

    def show(self, mode="record"):
        self.mode = mode
        self.set_quiet(None)
        self._place()
        self.win.deiconify()
        self.win.lift()

    def hide(self):
        self.win.withdraw()


# ---------------------------------------------------------------- tray icon
COLORS = {"idle": T.GREEN, "recording": T.RED, "paused": "#8a8a8a", "nomic": T.AMBER, "busy": T.AMBER,
          "stopped": "#8a8a8a"}


_icon_base = []


def make_icon(state="idle", busy=False):
    col = COLORS["busy"] if (busy and state == "idle") else COLORS.get(state, T.GREEN)
    if not _icon_base:                 # the artwork is loaded once; each state just adds its dot
        art = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nobu_icon.png")
        try:
            im = Image.open(art).convert("RGBA").resize((64, 64), Image.LANCZOS)
        except Exception:
            im = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
            d = ImageDraw.Draw(im)
            d.rounded_rectangle((4, 4, 60, 60), radius=14, fill="#26303b")
            d.line((19, 44, 19, 20, 45, 44, 45, 20), fill="white", width=6, joint="curve")
        _icon_base.append(im)
    im = _icon_base[0].copy()
    ImageDraw.Draw(im).ellipse((40, 40, 62, 62), fill=col, outline="white", width=2)
    return im


# ---------------------------------------------------------------- pronunciation dictionary
class DictionaryWindow:
    def __init__(self, root, app, prefill=None):
        import nobu_dictionary as D
        self.D, self.app, self.root = D, app, root
        self.entries = D.load()
        w = self.win = T.toplevel(root, "Nobu Notes — my dictionary", 760, 560)
        f = ttk.Frame(w, padding=18)
        f.pack(fill="both", expand=True)
        ttk.Label(f, text="My dictionary", style="Title.TLabel").pack(anchor="w")
        ttk.Label(f, style="Muted.TLabel", wraplength=710, justify="left", text=(
            "Add names and words the way you want them spelled (characters, places, spells…). "
            "Record yourself saying each one a couple of times: Nobu learns how the speech model hears "
            "you, and from then on swaps those sound-alikes for your spelling in every new transcript, "
            "dictation and cut. The words are also given to the model as a hint.")).pack(anchor="w", pady=(4, 12))
        quick = ttk.Frame(f)
        quick.pack(fill="x", pady=(0, 10))
        ttk.Label(quick, text="New word:", style="H2.TLabel").pack(side="left")
        self.quick = tk.StringVar()
        qe = ttk.Entry(quick, textvariable=self.quick, width=28, font=(T.UI_FAMILY, 13))
        qe.pack(side="left", padx=8)
        qe.bind("<Return>", lambda e: self._quick_add())
        ttk.Button(quick, text="+  Add & record how I say it", style="Accent.TButton",
                   command=self._quick_add).pack(side="left")
        qe.focus_set()
        b = ttk.Frame(f)
        b.pack(side="bottom", fill="x", pady=(10, 0))
        box = ttk.Frame(f, style="Panel.TFrame")
        box.pack(fill="both", expand=True)
        self.tv = ttk.Treeview(box, columns=("word", "heard"), show="headings", style="List.Treeview",
                               selectmode="extended", height=8)
        self.tv.heading("word", text="SPELLING", anchor="w")
        self.tv.heading("heard", text="HEARD AS", anchor="w")
        self.tv.column("word", width=200, stretch=False)
        self.tv.column("heard", width=480)
        self.tv.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(box, orient="vertical", command=self.tv.yview)
        sb.pack(side="right", fill="y")
        self.tv.configure(yscrollcommand=sb.set)
        self.tv.bind("<Double-1>", lambda e: self.edit())
        self.tv.bind("<Delete>", lambda e: self.remove())
        self.tv.bind("<Button-3>", self._menu)
        self.empty = ttk.Label(box, text="No words yet. Type one above (e.g. a character's name) and press Add,\n"
                               "or right-click here.", style="PanelMuted.TLabel", padding=20, justify="center")
        self.empty.bind("<Button-3>", self._menu)
        self.empty.bind("<Double-1>", lambda e: self.add())
        ttk.Button(b, text="+  Add word", command=self.add).pack(side="left")
        ttk.Button(b, text="Edit / record", command=self.edit).pack(side="left", padx=6)
        ttk.Button(b, text="Remove", command=self.remove).pack(side="left")
        ttk.Button(b, text="Fix the open note now", command=self.apply_open).pack(side="right")
        self.refresh()
        T.fit(w)
        if prefill:
            T.later(w, 100, self.add, prefill)

    def _quick_add(self):
        word = self.quick.get().strip()
        self.quick.set("")
        self.add(word)

    def _menu(self, ev):
        row = self.tv.identify_row(ev.y) if ev.widget is self.tv else ""
        if row and row not in self.tv.selection():
            self.tv.selection_set(row)
        m = T.menu(self.win)
        m.add_command(label="Add a word\u2026", command=self.add)
        if row:
            m.add_command(label="Edit / record samples\u2026", command=self.edit)
            m.add_command(label="Remove", command=self.remove)
        m.tk_popup(ev.x_root, ev.y_root)

    def refresh(self):
        self.tv.delete(*self.tv.get_children())
        if self.entries:
            self.empty.place_forget()
        else:
            self.empty.place(relx=0.5, rely=0.45, anchor="center")
        for e in sorted(self.entries, key=lambda e: e["word"].lower()):
            self.tv.insert("", "end", iid=e["word"], values=(e["word"], ", ".join(e.get("sounds", [])) or
                                                             "(no samples yet)"))

    def _find(self, word):
        for e in self.entries:
            if e["word"] == word:
                return e
        return None

    def add(self, prefill=""):
        WordDialog(self, None, prefill)

    def edit(self):
        sel = self.tv.selection()
        if sel:
            WordDialog(self, self._find(sel[0]))

    def remove(self):
        sel = set(self.tv.selection())
        if not sel:
            return
        if not T.confirm(self.win, "My dictionary", "Remove %s from your dictionary?" % (
                "\u201c%s\u201d" % next(iter(sel)) if len(sel) == 1 else "these %d words" % len(sel)),
                yes="Remove", no="Keep", danger=True):
            return
        self.entries = [e for e in self.entries if e["word"] not in sel]
        self.D.save(self.entries)
        self.refresh()

    def store(self, old_word, entry):
        self.entries = [e for e in self.entries if e["word"] not in (old_word, entry["word"])]
        self.entries.append(entry)
        self.D.save(self.entries)
        self.refresh()

    def apply_open(self):
        if not self.app.editor.path:
            self.app.set_status("Open a note first - then this fixes the words in it.")
            return
        n = self.app.editor.apply_dictionary(self.entries)
        self.app.set_status("Dictionary: %d change%s made in the open note." % (n, "" if n == 1 else "s"))


class WordDialog:
    SAMPLES = 3

    def __init__(self, parent, entry=None, prefill=""):
        self.parent, self.app, self.D = parent, parent.app, parent.D
        self.old = entry["word"] if entry else None
        self.sounds = list(entry.get("sounds", [])) if entry else []
        self.count = 0
        w = self.win = T.toplevel(parent.win, "Dictionary word", 620, 520)
        w.protocol("WM_DELETE_WINDOW", self.close)
        f = ttk.Frame(w, padding=18)
        f.pack(fill="both", expand=True)
        ttk.Label(f, text="Spelling you want", style="H2.TLabel").pack(anchor="w")
        self.word = tk.StringVar(value=(entry["word"] if entry else prefill))
        e = ttk.Entry(f, textvariable=self.word, width=40, font=(T.UI_FAMILY, 13))
        e.pack(anchor="w", pady=(4, 14))
        e.focus_set()
        ttk.Label(f, text="Teach Nobu how you say it", style="H2.TLabel").pack(anchor="w")
        ttk.Label(f, style="Muted.TLabel", wraplength=570, text=(
            "Click Record, then say just the word (or name) once, clearly, the way you will when "
            "dictating. Do it two or three times.")).pack(anchor="w")
        r = ttk.Frame(f)
        r.pack(fill="x", pady=8)
        self.rec_btn = ttk.Button(r, text="●  Record sample 1", style="Accent.TButton", command=self.record)
        self.rec_btn.pack(side="left")
        self.msg = ttk.Label(r, text="", style="Muted.TLabel", wraplength=400)
        self.msg.pack(side="left", padx=10)
        ttk.Label(f, text="Nobu will replace these with your spelling:", style="Muted.TLabel").pack(anchor="w", pady=(8, 2))
        lb = ttk.Frame(f)
        lb.pack(fill="both", expand=True)
        self.lb = tk.Listbox(lb, height=4, bg=T.PANEL, fg=T.FG, selectbackground=T.SELECT, relief="flat",
                             highlightthickness=0, font=T.UI_FONT, activestyle="none")
        self.lb.pack(side="left", fill="both", expand=True)
        side = ttk.Frame(lb)
        side.pack(side="left", fill="y", padx=(8, 0))
        ttk.Button(side, text="Remove", command=self.remove_sound).pack(fill="x")
        add = ttk.Frame(f)
        add.pack(side="bottom", fill="x", pady=(8, 0), before=f.winfo_children()[0])
        ttk.Label(add, text="Or type a sound-alike:").pack(side="left")
        self.typed = tk.StringVar()
        te = ttk.Entry(add, textvariable=self.typed, width=24)
        te.pack(side="left", padx=6)
        te.bind("<Return>", lambda e: self.add_typed())
        ttk.Button(add, text="Add", command=self.add_typed).pack(side="left")
        b = ttk.Frame(f)
        b.pack(side="bottom", fill="x", pady=(14, 0), before=add)
        ttk.Button(b, text="Cancel", command=self.close).pack(side="right", padx=(6, 0))
        ttk.Button(b, text="Save word", style="Accent.TButton", command=self.save).pack(side="right")
        e.bind("<Return>", lambda _e: self.save())
        self._fill()
        T.fit(w)

    def _fill(self):
        self.lb.delete(0, "end")
        for s in self.sounds:
            self.lb.insert("end", s)

    def remove_sound(self):
        for i in reversed(self.lb.curselection()):
            del self.sounds[i]
        self._fill()

    def add_typed(self):
        s = self.D.norm(self.typed.get())
        if s and s not in self.sounds and s != self.D.norm(self.word.get()):
            self.sounds.append(s)
            self._fill()
        self.typed.set("")

    def record(self):
        word = self.word.get().strip()
        if not word:
            self.msg.config(text="Type the spelling first.")
            return
        self.rec_btn.config(state="disabled")
        self.msg.config(text="Listening… say “%s” now." % word)
        self.app.capture_sample(word, self._heard)

    def _heard(self, heard):
        try:
            if not self.win.winfo_exists():
                return
        except tk.TclError:
            return
        word = self.word.get().strip()
        self.count += 1
        self.rec_btn.config(state="normal", text="●  Record sample %d" % (self.count + 1)
                            if self.count < self.SAMPLES else "●  Record another sample")
        if heard is None:
            self.msg.config(text="Didn't hear anything. Click Record and say the word.")
            self.count -= 1
            return
        notes = []
        for h in heard:
            snd = self.D.sounds_from_heard(word, h)
            if snd is None:
                if self.D.norm(h) == self.D.norm(word):
                    notes.append("“%s” (spelled right)" % h.strip(" ."))
                else:
                    notes.append("“%s” (too long, ignored)" % h[:40])
            elif self.D.is_common(snd):
                notes.append("“%s” (a common word, so not added automatically - type it below if you "
                             "really want it replaced)" % snd)
            else:
                if snd not in self.sounds:
                    self.sounds.append(snd)
                notes.append("“%s” ✔ learned" % snd)
        self._fill()
        self.msg.config(text="Heard: " + "; ".join(notes) if notes else "Heard nothing clear.")

    def save(self):
        word = self.word.get().strip()
        if not word:
            self.msg.config(text="Type the spelling first.")
            return
        self.parent.store(self.old, {"word": word, "sounds": self.sounds})
        self.close()

    def close(self):
        self.app.engine.command("cancel_capture")
        self.win.destroy()
