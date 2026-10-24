"""Keyboard shortcuts for recording, dictating and cutting.

On Windows they are registered system-wide (RegisterHotKey), so they work even when another
program is in front. Elsewhere (tests) they fall back to ordinary in-window key bindings.
A shortcut is stored as text like "Ctrl+Alt+R".
"""
import ctypes
import logging
import os
import threading

log = logging.getLogger("nobu.hotkeys")
IS_WIN = os.name == "nt"

MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, MOD_NOREPEAT = 0x1, 0x2, 0x4, 0x8, 0x4000
WM_HOTKEY, WM_QUIT = 0x0312, 0x0012
_SPECIAL_VK = {"SPACE": 0x20, "PAUSE": 0x13, "INSERT": 0x2D, "HOME": 0x24, "END": 0x23, "PRIOR": 0x21,
               "NEXT": 0x22, "PAGEUP": 0x21, "PAGEDOWN": 0x22, "SCROLL_LOCK": 0x91, "SCROLLLOCK": 0x91,
               "SCROLL": 0x91, "MENU": 0x5D, "APP": 0x5D,
               "KP_0": 0x60, "KP_1": 0x61, "KP_2": 0x62, "KP_3": 0x63, "KP_4": 0x64, "KP_5": 0x65, "KP_6": 0x66,
               "KP_7": 0x67, "KP_8": 0x68, "KP_9": 0x69, "KP_MULTIPLY": 0x6A, "KP_ADD": 0x6B, "KP_SUBTRACT": 0x6D,
               "KP_DECIMAL": 0x6E, "KP_DIVIDE": 0x6F,
               "GRAVE": 0xC0, "MINUS": 0xBD, "EQUAL": 0xBB, "BRACKETLEFT": 0xDB, "BRACKETRIGHT": 0xDD,
               "BACKSLASH": 0xDC, "SEMICOLON": 0xBA, "APOSTROPHE": 0xDE, "COMMA": 0xBC, "PERIOD": 0xBE,
               "SLASH": 0xBF}
_SPECIAL_VK.update({"UP": 0x26, "DOWN": 0x28, "LEFT": 0x25, "RIGHT": 0x27, "RETURN": 0x0D, "TAB": 0x09,
                    "ESCAPE": 0x1B, "BACKSPACE": 0x08, "DELETE": 0x2E})
# Single keys that need no warning: they don't type text and Windows doesn't need them.
SINGLE_OK = {"PAUSE", "SCROLLLOCK", "SCROLL_LOCK", "INSERT", "HOME", "END", "PAGEUP", "PAGEDOWN",
             "MENU", "APP"} | {"F%d" % i for i in range(1, 25)} | {k for k in _SPECIAL_VK if k.startswith("KP_")}
# Keys Windows itself depends on: allowed only together with Ctrl and/or Alt.
NEEDS_MOD = {"ESCAPE", "RETURN", "TAB", "BACKSPACE", "DELETE", "PRINT", "CAPS_LOCK", "NUM_LOCK"}
# Never allowed at all.
FORBIDDEN = {"SUPER_L", "SUPER_R", "WIN_L", "WIN_R"}
RESERVED = {"ALT+TAB", "ALT+F4", "CTRL+ESCAPE", "ALT+ESCAPE", "CTRL+ALT+DELETE", "CTRL+SHIFT+ESCAPE",
            "ALT+SPACE"}
# Tk keysym -> how we show it
_PRETTY = {"prior": "PageUp", "next": "PageDown", "space": "Space", "scroll_lock": "ScrollLock",
           "pause": "Pause", "insert": "Insert", "home": "Home", "end": "End", "app": "Menu", "menu": "Menu",
           "kp_insert": "KP_0", "kp_end": "KP_1", "kp_down": "KP_2", "kp_next": "KP_3", "kp_left": "KP_4",
           "kp_begin": "KP_5", "kp_right": "KP_6", "kp_home": "KP_7", "kp_up": "KP_8", "kp_prior": "KP_9",
           "kp_delete": "KP_Decimal"}


# With Shift held Tk names the symbol ("exclam"); a shortcut needs the key underneath it.
_SHIFTED = {"exclam": "1", "at": "2", "numbersign": "3", "dollar": "4", "percent": "5", "asciicircum": "6",
            "ampersand": "7", "asterisk": "8", "parenleft": "9", "parenright": "0", "underscore": "minus",
            "plus": "equal", "braceleft": "bracketleft", "braceright": "bracketright", "bar": "backslash",
            "colon": "semicolon", "quotedbl": "apostrophe", "less": "comma", "greater": "period",
            "question": "slash", "asciitilde": "grave", "quoteright": "apostrophe", "quoteleft": "grave"}


def combo_from_event(ev):
    """'Ctrl+Alt+R' from a Tk KeyPress event (None while only modifiers are held)."""
    ks = ev.keysym
    if ks in ("Control_L", "Control_R", "Alt_L", "Alt_R", "Shift_L", "Shift_R", "Meta_L", "Meta_R",
              "Super_L", "Super_R", "Win_L", "Win_R", "Caps_Lock", "Num_Lock", "ISO_Level3_Shift"):
        return None
    mods = []
    if ev.state & 0x4:
        mods.append("Ctrl")
    # On Windows Tk reports Alt as 0x20000 (0x8 there means Num Lock is on - not Alt!)
    if ev.state & (0x20000 if IS_WIN else 0x8):
        mods.append("Alt")
    if ev.state & 0x1:
        mods.append("Shift")
    ks = _SHIFTED.get(ks, ks)
    key = _PRETTY.get(ks.lower(), ks.upper() if len(ks) == 1 else ks)
    return "+".join(mods + [key])


def parse(combo):
    """'Ctrl+Alt+R' -> (mods list, key)  (key as written)."""
    if not combo:
        return [], ""
    parts = [p.strip() for p in combo.split("+") if p.strip()]
    return parts[:-1], parts[-1] if parts else ""


def to_win(combo):
    mods, key = parse(combo)
    m = MOD_NOREPEAT
    for x in mods:
        m |= {"CTRL": MOD_CONTROL, "ALT": MOD_ALT, "SHIFT": MOD_SHIFT, "WIN": MOD_WIN}.get(x.upper(), 0)
    k = key.upper()
    if len(k) == 1 and (k.isalpha() or k.isdigit()):
        vk = ord(k)
    elif k.startswith("F") and k[1:].isdigit() and 1 <= int(k[1:]) <= 24:
        vk = 0x6F + int(k[1:])
    else:
        vk = _SPECIAL_VK.get(k.replace(" ", "_"))
    return (m, vk) if vk else None


def to_tk(combo):
    mods, key = parse(combo)
    if not key:
        return None
    tkmods = [{"CTRL": "Control", "ALT": "Alt", "SHIFT": "Shift"}.get(m.upper(), m) for m in mods]
    k = key.lower() if len(key) == 1 else {"PageUp": "Prior", "PageDown": "Next", "Space": "space",
                                           "ScrollLock": "Scroll_Lock", "Menu": "App"}.get(key, key)
    return "<%s>" % "-".join(tkmods + ["KeyPress", k])


def valid(combo):
    """(ok, problem, warning).

    Any single key is allowed. Keys Windows depends on (Esc, Enter, Tab, Backspace, Delete...)
    need Ctrl and/or Alt. Keys that normally type something get a warning first, because a
    shortcut takes the key over in every program while Nobu runs."""
    mods, key = parse(combo)
    if not key:
        return False, "Press a key (alone, or with Ctrl / Alt).", ""
    k = key.upper().replace(" ", "_")
    up = "+".join([m.upper() for m in mods] + [k])
    if k in FORBIDDEN:
        return False, "The Windows key can't be used - Windows needs it.", ""
    if up in RESERVED:
        return False, "%s is a Windows shortcut - please pick something else." % combo, ""
    strong = any(m.upper() in ("CTRL", "ALT") for m in mods)
    if k in NEEDS_MOD and not strong:
        return False, ("%s is needed by Windows and every program, so use it with Ctrl or Alt "
                       "(for example Ctrl+%s), or pick another key." % (key, key)), ""
    if IS_WIN and to_win(combo) is None:
        return False, "That key can't be used as a shortcut - please try another.", ""
    warn = ""
    if not strong and k not in SINGLE_OK:
        warn = ("While Nobu is running, %s will work as this shortcut everywhere - in other programs and "
                "games it won't type or do its normal job." % combo)
    return True, "", warn


class Hotkeys:
    """Owns the shortcuts. on_fire(name) is called on the Tk thread (through app.ui)."""

    def __init__(self, app, on_fire):
        self.app = app
        self.on_fire = on_fire
        self.thread = None
        self.tid = None
        self.failed = []
        self._tk_bound = []

    def apply(self, mapping):
        """mapping: {name: 'Ctrl+Alt+R' or ''}."""
        self.stop()
        mapping = {k: v for k, v in mapping.items() if v}
        if IS_WIN:
            self._start_win(mapping)
        else:
            root = self.app.root
            for name, combo in mapping.items():
                seq = to_tk(combo)
                if seq:
                    try:
                        root.bind_all(seq, lambda e, n=name: (self.on_fire(n), "break")[1])
                        self._tk_bound.append(seq)
                    except Exception:
                        log.warning("could not bind %s", combo)

    def stop(self):
        root = self.app.root
        for seq in self._tk_bound:
            try:
                root.unbind_all(seq)
            except Exception:
                pass
        self._tk_bound = []
        if self.thread and self.tid:
            ctypes.windll.user32.PostThreadMessageW(self.tid, WM_QUIT, 0, 0)
            self.thread.join(timeout=2)
        self.thread = None
        self.tid = None

    def _start_win(self, mapping):
        ready = threading.Event()
        self.failed = []

        def run():
            from ctypes import wintypes
            u32 = ctypes.windll.user32
            k32 = ctypes.windll.kernel32
            self.tid = k32.GetCurrentThreadId()
            ids = {}
            for i, (name, combo) in enumerate(mapping.items(), start=1):
                w = to_win(combo)
                if not w or not u32.RegisterHotKey(None, i, w[0], w[1]):
                    self.failed.append(combo)
                    log.warning("shortcut %s is not available (maybe another program uses it)", combo)
                    continue
                ids[i] = name
            ready.set()
            msg = wintypes.MSG()
            while u32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == WM_HOTKEY and msg.wParam in ids:
                    self.app.ui(self.on_fire, ids[msg.wParam])
            for i in ids:
                u32.UnregisterHotKey(None, i)

        self.thread = threading.Thread(target=run, name="nobu-hotkeys", daemon=True)
        self.thread.start()
        ready.wait(2)
