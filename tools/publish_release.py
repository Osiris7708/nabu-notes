"""Put the copy for other people on GitHub (private repository Osiris7708/nabu-notes): one release per version,
with the zip attached and that version's "what's new" text from README.txt.

    runtime\\python.exe tools\\publish_release.py      (make_share_copy.py --yes runs this by itself)

  * uploads the code (git push of main)
  * release "v<version>" titled "Nabu Notes <version>", notes = README's "NEW IN VERSION <version>" section,
    file Nabu-Notes-<version>.zip (the share zip from the Desktop)
  * the same version again (a rebuilt zip): its zip and notes are replaced, nothing is duplicated
Needs GitHub CLI, signed in once (gh auth login). Nothing personal goes up: the code is what git tracks
(.gitignore keeps notes, recordings, pictures and settings out) and the zip is the share copy.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ZIP = os.path.join(os.path.dirname(ROOT), "Nabu Notes - Share.zip")


def _exe(name, fallback):
    return shutil.which(name) or (fallback if os.path.isfile(fallback) else None)


GH = _exe("gh", r"C:\Program Files\GitHub CLI\gh.exe")
GIT = _exe("git", r"C:\Program Files\Git\cmd\git.exe")


def _run(*args):
    p = subprocess.run(list(args), cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return p.returncode, (p.stdout + p.stderr).strip()


def notes_for(version):
    """README.txt's "NEW IN VERSION <version>" section (without its heading)."""
    with open(os.path.join(ROOT, "README.txt"), encoding="utf-8") as f:
        text = f.read()
    m = re.search(r"^NEW IN VERSION %s\b[^\n]*\n-+\n(.*?)(?=^NEW IN VERSION |\Z)" % re.escape(version), text, re.M | re.S)
    body = m.group(1).strip() if m else "Nabu Notes %s." % version
    return ("Download **Nabu-Notes-%s.zip** below, unzip it and double-click NabuNotes.exe. Updating? Quit Nabu "
            "(tray icon > Quit), unzip over the old folder - notes and settings are kept.\n\n"
            "> **Windows or your antivirus may warn about NabuNotes.exe.** It's a small home-made program that "
            "isn't \"signed\" (signing costs money). If Windows says \"Windows protected your PC\", click **More "
            "info**, then **Run anyway**. Antivirus warnings about it are false alarms: all of the code is here to "
            "read.\n\n```\n%s\n```\n"
            % (version, body))


def publish(version=None):
    """Returns (ok, message)."""
    if version is None:
        sys.path.insert(0, os.path.join(ROOT, "app"))
        from nabu_config import VERSION as version
    if not GH or not GIT:
        return False, "GitHub CLI or git is not installed"
    code, out = _run(GH, "auth", "status")
    if code != 0:
        return False, "not signed in to GitHub (run: gh auth login)"
    if not os.path.isfile(ZIP):
        return False, "no share zip (run make_share_copy.py --yes first)"
    code, out = _run(GIT, "push", "origin", "main")
    if code != 0:
        return False, "could not upload the code: " + out[-300:]
    tag, title = "v" + version, "Nabu Notes " + version
    tmp = tempfile.mkdtemp(prefix="nabu-release-")
    try:
        asset = os.path.join(tmp, "Nabu-Notes-%s.zip" % version)
        shutil.copy2(ZIP, asset)
        notes = os.path.join(tmp, "notes.md")
        with open(notes, "w", encoding="utf-8") as f:
            f.write(notes_for(version))
        if _run(GH, "release", "view", tag)[0] == 0:          # the same version again: replace its zip and notes
            code, out = _run(GH, "release", "upload", tag, asset, "--clobber")
            if code == 0:
                code, out = _run(GH, "release", "edit", tag, "--title", title, "--notes-file", notes)
            what = "updated"
        else:
            code, out = _run(GH, "release", "create", tag, asset, "--title", title, "--notes-file", notes,
                             "--target", "main", "--latest")
            what = "published"
        if code != 0:
            return False, "GitHub refused the release: " + out[-300:]
        url = _run(GH, "release", "view", tag, "--json", "url", "--jq", ".url")[1]
        return True, "%s %s on GitHub: %s" % (what, title, url)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    ok, msg = publish()
    print(msg)
    sys.exit(0 if ok else 1)
