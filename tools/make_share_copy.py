"""Build the copy of Nabu Notes to give to other people: the program only, none of your writing.

    runtime\\python.exe tools\\make_share_copy.py          shows what it would do
    runtime\\python.exe tools\\make_share_copy.py --yes    replaces "Nabu Notes - Share" and its .zip on the Desktop,
                                                          then puts the zip on GitHub as that version's release
                                                          (tools\\publish_release.py; add --no-github to skip it)

What goes in: NabuNotes.exe, README.txt, LICENSE, THIRD-PARTY-NOTICES.txt, the debug .bat, the app's code, icon, thesaurus and base fonts,
and the setup zips (runtime + the add-on and font zips nabu_main unpacks). What never goes in: Notes,
Recordings, Images, config.json, cache, logs, your own fonts, the downloaded speech models, the unpacked
runtime, tests, tools, git history and CLAUDE.md.
"""
import glob
import os
import re
import shutil
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARENT = os.path.dirname(ROOT)
NAME = "Nabu Notes - Share"
DEST = os.path.join(PARENT, NAME)
ZIP = DEST + ".zip"


def wanted():
    """(source, path inside the share folder) for every file to copy."""
    app = os.path.join(ROOT, "app")
    out = []
    def add(src, rel):
        if not os.path.isfile(src):
            sys.exit("Missing: %s" % src)
        out.append((src, rel))
    for f in ("NabuNotes.exe", "README.txt", "LICENSE", "THIRD-PARTY-NOTICES.txt", "Debug - show errors.bat"):
        add(os.path.join(ROOT, f), f)
    for f in sorted(glob.glob(os.path.join(app, "nabu_*.py"))) + [os.path.join(app, "nabu_icon.png")]:
        add(f, os.path.join("app", os.path.basename(f)))
    for sub in ("data", "fonts"):                     # app/fonts: the base fonts only, not the unpacked lib/
        for f in sorted(glob.glob(os.path.join(app, sub, "*"))):
            if os.path.isfile(f):
                add(f, os.path.join("app", sub, os.path.basename(f)))
    # the setup zips nabu_main actually unpacks (so old versions are left behind)
    main = open(os.path.join(app, "nabu_main.py"), encoding="utf-8").read()
    zips = sorted(set(re.findall(r'"((?:addons|fontlib)-v\w+\.zip)"', main)))
    if len(zips) < 2:
        sys.exit("Could not find the add-on zip names in nabu_main.py")
    parts = sorted(glob.glob(os.path.join(ROOT, "setup", "runtime.zip.0*")))
    if not parts:
        sys.exit("Missing setup\\runtime.zip.001 ...")
    for f in [os.path.join(ROOT, "setup", z) for z in zips] + parts:
        add(f, os.path.join("setup", os.path.basename(f)))
    return out


def main(argv):
    sys.path.insert(0, os.path.join(ROOT, "app"))
    from nabu_config import VERSION
    files = wanted()
    size = sum(os.path.getsize(s) for s, _ in files)
    print("Nabu Notes %s: %d files, %.0f MB" % (VERSION, len(files), size / 1e6))
    print("  folder: %s\n  zip:    %s" % (DEST, ZIP))
    if os.path.normcase(os.path.abspath(DEST)) == os.path.normcase(ROOT):
        sys.exit("Refusing: the share folder would be this install.")
    if "--yes" not in argv:
        print("Nothing changed. Run again with --yes to build it.")
        return 0

    tmp = DEST + ".new"
    shutil.rmtree(tmp, ignore_errors=True)
    for src, rel in files:
        d = os.path.join(tmp, rel)
        os.makedirs(os.path.dirname(d), exist_ok=True)
        shutil.copy2(src, d)
    shutil.rmtree(DEST, ignore_errors=True)
    os.replace(tmp, DEST)

    ztmp = ZIP + ".new"
    with zipfile.ZipFile(ztmp, "w", zipfile.ZIP_DEFLATED) as z:
        for _, rel in files:
            already_packed = rel.endswith(".zip") or ".zip.0" in rel
            z.write(os.path.join(DEST, rel), NAME + "/" + rel.replace(os.sep, "/"),
                    compress_type=zipfile.ZIP_STORED if already_packed else zipfile.ZIP_DEFLATED)
    with zipfile.ZipFile(ztmp) as z:
        bad = z.testzip()
        if bad:
            sys.exit("The new zip is damaged at %s; the old zip was kept." % bad)
    os.replace(ztmp, ZIP)
    print("Done: %s and %s are now version %s." % (NAME, os.path.basename(ZIP), VERSION))
    if "--no-github" not in argv:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import publish_release
        ok, msg = publish_release.publish(VERSION)
        print(("GitHub: " if ok else "GitHub: not updated - ") + msg)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
