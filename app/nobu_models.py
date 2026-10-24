"""One-time download of the offline speech models (needs internet once)."""
import json
import logging
import os
import time

import requests

from nobu_config import MODELS_DIR, model_dir

log = logging.getLogger("nobu.models")

REPOS = {
    "tiny.en": "Systran/faster-whisper-tiny.en",
    "base.en": "Systran/faster-whisper-base.en",
    "small.en": "Systran/faster-whisper-small.en",
    "medium.en": "Systran/faster-whisper-medium.en",
    # the newest, most accurate model faster-whisper supports (multilingual, used in English mode)
    "large-v3-turbo": "mobiuslabsgmbh/faster-whisper-large-v3-turbo",
}
MARKER = ".nobu_complete"
SKIP = {".gitattributes", "README.md"}


def is_ready(name):
    d = model_dir(name)
    return os.path.exists(os.path.join(d, MARKER)) and os.path.exists(os.path.join(d, "model.bin"))


def missing(names):
    return [n for n in names if not is_ready(n)]


class Cancelled(Exception):
    pass


def _list_files(repo, session):
    r = session.get("https://huggingface.co/api/models/%s?blobs=true" % repo, timeout=30)
    r.raise_for_status()
    files = []
    for s in r.json().get("siblings", []):
        name = s.get("rfilename")
        if not name or name in SKIP or "/" in name:
            continue
        files.append((name, int(s.get("size") or 0)))
    if not any(n == "model.bin" for n, _ in files):
        raise RuntimeError("model.bin not found in %s" % repo)
    return files


def _download_file(repo, name, size, dest_dir, session, progress, cancel):
    final = os.path.join(dest_dir, name)
    if os.path.exists(final) and (size == 0 or os.path.getsize(final) == size):
        progress(size or os.path.getsize(final), name)
        return
    part = final + ".part"
    url = "https://huggingface.co/%s/resolve/main/%s" % (repo, name)
    for attempt in range(6):
        have = os.path.getsize(part) if os.path.exists(part) else 0
        if size and have > size:
            os.remove(part)
            have = 0
        if size and have == size:
            break
        headers = {"Range": "bytes=%d-" % have} if have else {}
        try:
            with session.get(url, headers=headers, stream=True, timeout=60) as r:
                if r.status_code == 416:
                    break
                r.raise_for_status()
                mode = "ab" if (have and r.status_code == 206) else "wb"
                if mode == "wb":
                    have = 0
                done = have
                with open(part, mode) as f:
                    for chunk in r.iter_content(chunk_size=1024 * 256):
                        if cancel():
                            raise Cancelled()
                        if chunk:
                            f.write(chunk)
                            done += len(chunk)
                            progress(done, name)
            if not size or os.path.getsize(part) == size:
                break
        except Cancelled:
            raise
        except Exception as e:  # network hiccup: wait and resume
            log.warning("download of %s interrupted: %s", name, e)
            time.sleep(min(30, 3 * (attempt + 1)))
    if size and os.path.getsize(part) != size:
        raise RuntimeError("Download of %s did not finish" % name)
    os.replace(part, final)


def _download(names, progress, cancel=lambda: False):
    """progress(done_bytes, total_bytes, label). Raises on failure."""
    os.makedirs(MODELS_DIR, exist_ok=True)
    session = requests.Session()
    session.headers["User-Agent"] = "NobuNotes/1.0"
    plan = []
    total = 0
    for n in names:
        repo = REPOS[n]
        files = _list_files(repo, session)
        plan.append((n, repo, files))
        total += sum(s for _, s in files)
    base = 0
    for n, repo, files in plan:
        d = model_dir(n)
        os.makedirs(d, exist_ok=True)
        for fname, size in files:
            def cb(done, label, base=base, n=n):
                progress(base + done, total, "%s: %s" % (n, label))
            _download_file(repo, fname, size, d, session, cb, cancel)
            base += size
        with open(os.path.join(d, MARKER), "w") as f:
            json.dump({"repo": repo, "time": time.time()}, f)
    progress(total, total, "done")


def download(names, progress, cancel=lambda: False):
    """The only time Nobu goes online: fetching the speech models (download only, nothing is sent)."""
    import nobu_offline
    with nobu_offline.allow_downloads():
        return _download(names, progress, cancel)
