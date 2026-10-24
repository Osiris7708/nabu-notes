"""Run Nobu's tests and print a short pass/fail summary.

    runtime\\python.exe tests\\run_tests.py            every test (about 10 minutes; windows will flash up)
    runtime\\python.exe tests\\run_tests.py --quick    only the fast tests that open no windows
    runtime\\python.exe tests\\run_tests.py audit 49   only tests whose names contain these words

Each test runs on its own in a throw-away folder; your real notes and settings are never touched.
The full output of the last run is saved in tests\\last-run\\. Exit code 0 means everything passed.
"""
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))

# name: (opens windows?, what it checks)
TESTS = {
    "test_compile": (False, "every file is valid Python and imports"),
    "test_offline": (False, "Nobu cannot reach the internet"),
    "test_voice":   (False, "wake/stop phrases and the recording engine"),
    "test_export":  (False, "export to Word, PDF, EPUB, web page and text, then import back"),
    "test_audit":   (True,  "every button, slider, menu entry and dialog does its job"),
    "test_49":      (True,  "v4.9: even tabs, toolbar, highlight colours"),
    "test_48":      (True,  "v4.8: side-by-side pages, pop-outs, snapping, drag and drop"),
    "test_47w":     (True,  "v4.7: workspace tabs and panes"),
    "test_47v":     (True,  "v4.7: new note, multi-select, lazy sidebar, import"),
    "test_47":      (True,  "v4.7: adding fonts, hotkey capture"),
    "test_462":     (True,  "single-key shortcuts and how they are saved"),
    "test_46":      (True,  "v4.6: Teach, renaming, fonts"),
    "test_44":      (True,  "v4.4: inbox, dictionary"),
    "test_gui":     (True,  "a full writing session: formatting, images, tables, export"),
    "test_ops":     (True,  "editor actions: undo, copy/paste, lists, saving"),
    "test_cache":   (True,  "the editor notices every kind of change before saving"),
    "test_tut":     (True,  "the tutorial window opens"),
}
TIMEOUT = 600


def nobu_running():
    try:
        socket.create_connection(("127.0.0.1", 47651), timeout=0.5).close()
        return True
    except OSError:
        return False


# Optional add-ons the app already copes without (they exist in the Windows runtime, not on test machines
# without it). Their "not installed" message is expected and not a failure.
OPTIONAL = ("pystray", "sounddevice", "tkinterdnd2")


def real_errors(out):
    n = out.count("Traceback (most recent call last)")
    ok = sum(out.count("ModuleNotFoundError: No module named '%s'" % m) for m in OPTIONAL)
    return n > ok


def verdict(code, out):
    """'pass' / 'FAIL' and a one-line reason."""
    m = re.findall(r"RESULT (\d+)/(\d+) passed", out)
    tb = real_errors(out)
    fails = [l.strip() for l in out.splitlines() if l.startswith("FAIL  ")]
    if m:
        a, b = map(int, m[-1])
        if a == b and not tb:
            return "pass", "%d/%d checks" % (a, b)
        why = fails[0][6:] if fails else ("an error was raised" if tb else "")
        return "FAIL", "%d/%d checks - %s" % (a, b, why)
    if code != 0:
        return "FAIL", "stopped with exit code %s" % code
    if tb:
        return "FAIL", "an error was raised"
    return "pass", "ran without errors"


def main(argv):
    quick = "--quick" in argv
    words = [a for a in argv if not a.startswith("--")]
    names = [n for n, (gui, _) in TESTS.items()
             if (not quick or not gui) and (not words or any(w in n for w in words))]
    if not names:
        print("No tests match", words); return 2
    if any(TESTS[n][0] for n in names) and nobu_running():
        print("Nobu Notes is running. Quit it first (right-click the tray icon > Quit),\n"
              "because the window tests use the same shortcuts and one-copy check.")
        return 2

    logs = os.path.join(HERE, "last-run")
    shutil.rmtree(logs, ignore_errors=True); os.makedirs(logs)
    scratch = tempfile.mkdtemp(prefix="nobu-tests-")
    env = dict(os.environ, PYTHONNOUSERSITE="1", PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1",
               TMP=scratch, TEMP=scratch, TMPDIR=scratch)
    env.pop("NOBU_HOME", None)

    results, t_all = [], time.time()
    for n in names:
        print("%-14s %s ..." % (n, TESTS[n][1]), end="", flush=True)
        t = time.time()
        try:
            p = subprocess.run([sys.executable, os.path.join(HERE, n + ".py")], cwd=HERE, env=env,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=TIMEOUT)
            code, out = p.returncode, p.stdout.decode("utf-8", "replace")
        except subprocess.TimeoutExpired as e:
            code, out = "timeout", (e.stdout or b"").decode("utf-8", "replace") + "\n(gave up after %d s)" % TIMEOUT
        with open(os.path.join(logs, n + ".txt"), "w", encoding="utf-8") as f:
            f.write(out)
        v, why = verdict(code, out)
        if code == "timeout":
            v, why = "FAIL", "took longer than %d s" % TIMEOUT
        results.append((n, v, why))
        print("\r%-14s %-4s  %s  (%.0f s)%s" % (n, v, why, time.time() - t, " " * 20))

    shutil.rmtree(scratch, ignore_errors=True)
    bad = [r for r in results if r[1] != "pass"]
    print("\n%d of %d tests passed in %.0f s." % (len(results) - len(bad), len(results), time.time() - t_all))
    if bad:
        print("Failed: %s\nFull output is in %s" % (", ".join(r[0] for r in bad), logs))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
