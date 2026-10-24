"""Offline spell check (pyspellchecker, English) and thesaurus (WordNet-based, LibreOffice data)."""
import gzip
import json
import logging
import os
import re
import threading

from nobu_config import HOME

log = logging.getLogger("nobu.spell")
DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
PERSONAL = os.path.join(HOME, "spelling.json")
WORD_RE = re.compile(r"[A-Za-zÀ-ɏ]+(?:['’][A-Za-z]+)*")


class Speller:
    def __init__(self):
        self.ready = False
        self.sp = None
        self.personal = set()
        self.ignored = set()
        self.extra = set()          # words from the pronunciation dictionary
        self._load_personal()
        self._started = False

    def ensure(self):
        """Load the word list in the background the first time a note is opened (saves ~40 MB until needed)."""
        if not self._started:
            self._started = True
            threading.Thread(target=self._load, daemon=True).start()

    def _load(self):
        try:
            from spellchecker import SpellChecker
            self.sp = SpellChecker(language="en", distance=2)
            self.ready = True
        except Exception:
            log.exception("spell checker unavailable")

    def _load_personal(self):
        try:
            with open(PERSONAL, encoding="utf-8") as f:
                self.personal = set(json.load(f))
        except Exception:
            self.personal = set()

    def add(self, word):
        self.personal.add(word.lower())
        try:
            with open(PERSONAL, "w", encoding="utf-8") as f:
                json.dump(sorted(self.personal), f, indent=1)
        except OSError:
            pass

    def ignore(self, word):
        self.ignored.add(word.lower())

    def set_extra(self, words):
        s = set()
        for w in words:
            for part in WORD_RE.findall(w):
                s.add(part.lower())
        self.extra = s

    def known(self, word):
        w = word.lower().replace("’", "'")
        if not self.ready or len(w) < 2 or w in self.personal or w in self.ignored or w in self.extra:
            return True
        if word.isupper() and len(word) > 1:          # acronyms
            return True
        if w in self.sp.word_frequency.dictionary:
            return True
        if w.endswith("'s") and w[:-2] in self.sp.word_frequency.dictionary:
            return True
        return False

    def suggestions(self, word, n=6):
        if not self.ready:
            return []
        try:
            cands = self.sp.candidates(word.lower()) or set()
        except Exception:
            return []
        freq = self.sp.word_frequency.dictionary
        best = sorted(cands, key=lambda c: -freq.get(c, 0))[:n]
        if word[:1].isupper():
            best = [c[:1].upper() + c[1:] for c in best]
        return [c for c in best if c.lower() != word.lower()]


class Thesaurus:
    """Synonyms from the WordNet-based thesaurus. Instead of keeping all 146,000 entries in memory
    (~130 MB), the data is unpacked once to cache\thesaurus_en.dat and only a word -> position index
    is kept (~15 MB); each lookup reads just that entry from disk."""

    def __init__(self):
        self.idx = None
        self.loading = False
        self.path = os.path.join(HOME, "cache", "thesaurus_en.dat")

    def _load(self):
        src = os.path.join(DATA, "thesaurus_en.dat.gz")
        idx_path = self.path + ".index.json"
        try:
            stamp = str(os.path.getsize(src))
            if os.path.exists(idx_path) and os.path.exists(self.path):
                with open(idx_path, encoding="utf-8") as f:
                    saved = json.load(f)
                if saved.get("stamp") == stamp:
                    self.idx = saved["idx"]
                    return
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with gzip.open(src, "rb") as fi, open(self.path + ".tmp", "wb") as fo:
                fo.write(fi.read())
            os.replace(self.path + ".tmp", self.path)
            idx = {}
            with open(self.path, "rb") as f:
                f.readline()                       # encoding line
                while True:
                    pos = f.tell()
                    head = f.readline()
                    if not head:
                        break
                    word, _, n = head.decode("utf-8", "replace").rstrip("\n").rpartition("|")
                    idx.setdefault(word.lower(), pos)
                    for _ in range(int(n or 0) if n.isdigit() else 0):
                        f.readline()
            with open(idx_path, "w", encoding="utf-8") as f:
                json.dump({"stamp": stamp, "idx": idx}, f)
            self.idx = idx
        except Exception:
            log.exception("thesaurus unavailable")
            self.idx = {}

    def ensure(self, done=None):
        if self.idx is None and not self.loading:
            self.loading = True

            def run():
                self._load()
                self.loading = False
                if done:
                    done()
            threading.Thread(target=run, daemon=True).start()

    def _entry(self, w):
        pos = self.idx.get(w)
        if pos is None:
            return None
        meanings = []
        with open(self.path, "rb") as f:
            f.seek(pos)
            _word, _, n = f.readline().decode("utf-8", "replace").rstrip("\n").rpartition("|")
            for _ in range(int(n) if n.isdigit() else 0):
                parts = f.readline().decode("utf-8", "replace").rstrip("\n").split("|")
                pos_name = parts[0].strip("()")
                syns = [re.sub(r"\s*\((generic|similar|related|antonym)[^)]*\)", "", x).strip()
                        for x in parts[1:] if "(antonym)" not in x]
                meanings.append((pos_name, [x for x in syns if x]))
        return meanings

    def lookup(self, word):
        if self.idx is None:
            return None
        w = word.lower()
        try:
            res = self._entry(w)
            if res is None and w.endswith("s"):
                res = self._entry(w[:-1])
            if res is None and w.endswith("ed"):
                res = self._entry(w[:-2]) or self._entry(w[:-1])
            if res is None and w.endswith("ing"):
                res = self._entry(w[:-3]) or self._entry(w[:-3] + "e")
        except OSError:
            res = None
        return res or []
