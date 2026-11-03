"""Every app file is valid Python and every module imports without errors."""
import _here  # finds the app and keeps the test away from your real notes
import glob, importlib, os, py_compile, tempfile, traceback
os.environ["NABU_HOME"] = tempfile.mkdtemp()

files = sorted(glob.glob(os.path.join(_here.APP, "nabu_*.py")))
bad = []
for f in files:
    try:
        py_compile.compile(f, cfile=os.path.join(_here.WORK, os.path.basename(f) + "c"), doraise=True)
    except py_compile.PyCompileError as e:
        bad.append(str(e))
print(("PASS  " if not bad else "FAIL  ") + "all %d files compile" % len(files) + ("" if not bad else "\n" + "\n".join(bad)))

nimp = []
for f in files:
    name = os.path.splitext(os.path.basename(f))[0]
    if name == "nabu_main":      # importing it starts the Windows set-up; the GUI tests cover it
        continue
    try:
        importlib.import_module(name)
    except Exception:
        nimp.append(name + "\n" + traceback.format_exc(limit=3))
print(("PASS  " if not nimp else "FAIL  ") + "every module imports" + ("" if not nimp else "\n" + "\n".join(nimp)))
print("RESULT %d/2 passed" % ((not bad) + (not nimp)))
