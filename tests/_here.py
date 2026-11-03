"""Shared set-up, imported first by every test.

- Finds the app folder next to this tests folder and puts it on the import path.
- On Windows, does what nabu_main does at start so the bundled runtime finds its DLLs and Tcl/Tk.
- Moves into a fresh scratch folder, so files a test writes (out/, shots/) never land in the project.
Each test also points NABU_HOME at its own empty temp folder: your real Notes, Recordings and
config.json are never read or changed.
"""
import os
import sys
import tempfile

TESTS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TESTS)
APP = os.path.join(ROOT, "app")
if APP not in sys.path:
    sys.path.insert(0, APP)


def _bootstrap_windows():
    if os.name != "nt":
        return
    rt = os.path.dirname(os.path.abspath(sys.executable))
    dirs = [os.path.join(rt, "Library", "bin"), os.path.join(rt, "Library", "usr", "bin"),
            os.path.join(rt, "Library", "mingw-w64", "bin"), rt, os.path.join(rt, "DLLs")]
    found = [d for d in dirs if os.path.isdir(d)]
    for d in found:
        try:
            os.add_dll_directory(d)
        except (OSError, AttributeError):
            pass
    os.environ["PATH"] = os.pathsep.join(found + [os.environ.get("PATH", "")])
    for var, sub in (("TCL_LIBRARY", "tcl8.6"), ("TK_LIBRARY", "tk8.6")):
        cand = os.path.join(rt, "Library", "lib", sub)
        if os.path.isdir(cand):
            os.environ[var] = cand
    sp = os.path.join(rt, "Lib", "site-packages")
    if os.path.isdir(sp) and sp not in sys.path:
        sys.path.append(sp)


_bootstrap_windows()

WORK = tempfile.mkdtemp(prefix="nabu-test-")
os.chdir(WORK)
os.makedirs("out", exist_ok=True)

# Screenshots are off unless NABU_TEST_SHOTS names a folder to save them in.
SHOTS = os.environ.get("NABU_TEST_SHOTS", "")


def shot(name, wait=0.0):
    import time
    time.sleep(wait)          # older tests rely on this pause to let the window settle
    if not SHOTS:
        return
    try:
        from PIL import ImageGrab
        os.makedirs(SHOTS, exist_ok=True)
        ImageGrab.grab().save(os.path.join(SHOTS, name + ".png"))
    except Exception:
        pass


# A real recording of "Nabu, record this" used by the voice tests. Your own first recording is
# used if it is still there; you can also drop any 16 kHz mono WAV of yourself saying the phrase
# at tests/samples/voice.wav. Tests that need it are skipped when neither exists.
def voice_sample():
    for p in (os.path.join(TESTS, "samples", "voice.wav"),
              os.path.join(ROOT, "Recordings", "Nabu Notes", "2026-10-21_09-28-28.wav")):
        if os.path.isfile(p):
            return p
    return None
