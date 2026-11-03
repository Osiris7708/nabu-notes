"""Paths and settings for Nobu Notes. Everything lives next to the program."""
import json
import os
import threading

VERSION = "4.9.5"


def _find_home():
    h = os.environ.get("NOBU_HOME")
    if h:
        return os.path.abspath(h)
    return os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))


HOME = _find_home()
NOTES_DIR = os.path.join(HOME, "Notes")              # the library: one sub-folder per project
INBOX_DIR = os.path.join(NOTES_DIR, "Unassigned")    # new transcripts land here
TRASH_DIR = os.path.join(NOTES_DIR, ".trash")
RECORDINGS_DIR = os.path.join(HOME, "Recordings")
IMAGES_DIR = os.path.join(HOME, "Images")
MODELS_DIR = os.path.join(HOME, "models")
LOGS_DIR = os.path.join(HOME, "logs")
HEARD_DIR = os.path.join(LOGS_DIR, "heard")
CONFIG_PATH = os.path.join(HOME, "config.json")
EXE_PATH = os.path.join(HOME, "NobuNotes.exe")

WAKE_PHRASE = "Nobu, record this"
STOP_PHRASE = "Nobu, end recording"
CONFIG_VERSION = 2

DEFAULTS = {
    "silence_stop_seconds": 8.0,
    "mic_device": None,            # None = Windows default microphone
    "mic_device_name": "",
    "mic_gain_db": 0.0,            # digital gain before everything else
    "noise_reduction": 0.6,        # 0 = off, 1 = strongest (for listening/detection)
    "transcribe_original": True,   # recordings keep the natural sound (more accurate transcripts)
    "speech_sensitivity": 0.5,     # 0..1, higher = treats quieter sounds as speech
    "wake_match_threshold": 0.5,   # lower = more forgiving about how "No boo" is heard
    "accept_bare_phrase": True,    # accept just "record this" if "No boo" was misheard
    "wake_aliases": [],            # learned by "Teach Nobu my voice"
    "cue_sounds": True,
    "close_to_tray": True,
    "autostart": False,
    "custom_vocabulary": "",       # names/places to help the transcriber
    "transcribe_model": "medium.en",
    "detect_model": "base.en",
    "detect_prompt": "",           # advanced: bias text for the wake-word model
    "cpu_threads": 0,              # 0 = automatic
    "unload_model_minutes": 5,
    "max_record_minutes": 180,
    "paragraph_gap_seconds": 2.0,
    "font_size": 12,
    "font_family": "IM FELL English",   # note text
    "heading_font": "Eagle Lake",       # headings & titles (free OFL font by Astigmatic; shareable)
    "ui_font": "Grenze",                # sidebar, folders, buttons, settings
    "save_heard_clips": False,
    "debug": False,
    "geometry": "",
    "maximized": False,
    "sidebar_width": 0,             # 0 = automatic
    "open_tabs": [],                # the notes that were open (pages and their tabs), reopened next start
    "reopen_notes": True,           # Settings: reopen those notes when Nobu starts
    "zoom": "Fit width",
    "theme": "dark",
    "custom_theme": {},             # your own colours (Settings > Appearance > Custom)
    "phrase_samples": {},           # how the speech model writes each command in your voice (Teach)
    "edit_silence_seconds": 8,      # dictation ("Nobu, edit this") stops after this much quiet; 0 = never
    "confirm_cut": True,            # ask before deleting a passage found by "Nobu, cut this"
    "confirm_edit": False,          # show dictated text for approval before inserting it
    "hotkey_record": "Ctrl+Alt+R",  # start/stop a recording (works from any program)
    "hotkey_edit": "Ctrl+Alt+E",    # start/stop dictating into the open note
    "hotkey_cut": "Ctrl+Alt+X",     # cut a passage by voice in the open note
    "install_fonts": True,          # also install Nobu's fonts into Windows (for Word etc.)
    "import_keep_fonts": True,
    "fetch_fonts": True,            # pasted text in a font you don't have: download it if it's free (Google Fonts)
    "paste_font_rules": {},         # pasted font (lower case) -> what it changes into (see nobu_pastefonts)
    "last_paste_fonts": [],         # the fonts of the last paste (a fresh font opens the font window)
    "export_format": "docx",
    "export_dir": "",
    "export_page_numbers": True,
    "recent_notes": [],             # recently opened notes (Home > Recent)
    "drop_color": "",               # shade showing where a dragged note lands ("" = the accent colour)
    "drop_alpha": 0.30,             # how strong that shade is (0.12 - 0.7)
}


def ensure_dirs():
    for d in (NOTES_DIR, INBOX_DIR, RECORDINGS_DIR, IMAGES_DIR, MODELS_DIR, LOGS_DIR):
        os.makedirs(d, exist_ok=True)


class Config:
    def __init__(self, path=CONFIG_PATH):
        self.path = path
        self._lock = threading.RLock()
        self._data = dict(DEFAULTS)
        self.load()

    def load(self):
        with self._lock:
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    saved = json.load(f)
            except FileNotFoundError:
                saved = {}
            except Exception:
                try:
                    os.replace(self.path, self.path + ".broken")
                except OSError:
                    pass
                saved = {}
            if not isinstance(saved, dict):
                saved = {}
            if int(saved.get("config_version", 1)) < 2:
                saved = self._migrate_v1(saved)
            self._data.update({k: v for k, v in saved.items() if k != "config_version"})

    @staticmethod
    def _migrate_v1(old):
        keep = ("silence_stop_seconds", "mic_device", "mic_device_name", "cue_sounds", "close_to_tray",
                "autostart", "custom_vocabulary", "transcribe_model", "cpu_threads", "font_size",
                "font_family", "geometry")
        new = {k: old[k] for k in keep if k in old}
        if old.get("wake_match_threshold") is not None:
            new["wake_match_threshold"] = max(0.4, min(0.6, float(old["wake_match_threshold"])))
        return new

    def save(self):
        with self._lock:
            out = {"config_version": CONFIG_VERSION}
            out.update({k: v for k, v in self._data.items() if k not in DEFAULTS or DEFAULTS[k] != v})
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(out, f, indent=2, ensure_ascii=False)
            os.replace(tmp, self.path)

    def get(self, key, default=None):
        with self._lock:
            return self._data.get(key, DEFAULTS.get(key, default))

    def __getitem__(self, key):
        return self.get(key)

    def set_temp(self, **kw):
        """Change values in memory only (live preview in Settings)."""
        with self._lock:
            self._data.update(kw)

    def update(self, **kw):
        with self._lock:
            self._data.update(kw)
            self.save()

    def threads(self):
        n = int(self.get("cpu_threads") or 0)
        if n > 0:
            return n
        return max(1, min(8, (os.cpu_count() or 4) - 1))


def model_dir(name):
    return os.path.join(MODELS_DIR, name)


def rel_to_home(path):
    try:
        return os.path.relpath(path, HOME).replace("\\", "/")
    except ValueError:
        return path.replace("\\", "/")


def abs_from_home(rel):
    if os.path.isabs(rel):
        return rel
    return os.path.normpath(os.path.join(HOME, rel))
