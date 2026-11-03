"""Personal pronunciation dictionary (fantasy names and other words).

Each entry: {"word": "Kryptik", "sounds": ["kripke", "crip tick"]}
 - "word" is the spelling you want.
 - "sounds" are the ways the speech model wrote it when you said it (learned from your
   recorded samples, or typed by hand). Any of them in a transcript is replaced by "word".
The words are also given to the speech model as a hint, so it often spells them right
by itself.
"""
import difflib
import json
import os
import re
import threading

from nabu_config import HOME

PATH = os.path.join(HOME, "dictionary.json")
_lock = threading.RLock()

# Very common words that must never be auto-learned as a "sounds like" (would cause havoc).
COMMON = set("""
a an the and or but if then so of to in on at by for with from as is are was were be been being
i you he she it we they me him her us them my your his its our their this that these those there here
what who whom which when where why how all any each few more most some such no nor not only own same
than too very can will just do does did done have has had having go goes went gone get got make made
say said see saw seen come came know knew think thought take took look want give use find tell ask
work seem feel try leave call good new first last long great little old right big high different small
large next early young important few public bad same able up down out over under again further once
off away back still even also well now way day man men woman women time year people thing things one
two three crypt creep key king kin cake cave queen lord lady light dark fire stone water earth air
frog jinn gin elemental realm shell summon crystal crystals
""".split())


def load():
    with _lock:
        try:
            with open(PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return [e for e in data if isinstance(e, dict) and e.get("word")]
        except FileNotFoundError:
            pass
        except Exception:
            try:
                os.replace(PATH, PATH + ".broken")
            except OSError:
                pass
        return []


def save(entries):
    with _lock:
        tmp = PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(entries, f, indent=2, ensure_ascii=False)
        os.replace(tmp, PATH)


def norm(s):
    return " ".join(re.findall(r"[a-z0-9']+", (s or "").lower())).replace("'", "")


def is_common(sound):
    toks = norm(sound).split()
    return bool(toks) and all(t in COMMON for t in toks)


def sounds_from_heard(word, heard_text):
    """Turn what the model wrote for a sample into a 'sounds like' entry (or None)."""
    h = norm(heard_text)
    if not h or h == norm(word):
        return None
    if len(h.split()) > 4:        # the sample picked up other speech
        return None
    return h


def prompt_words(entries):
    return ", ".join(e["word"] for e in entries)


def _pattern(sound):
    toks = [re.escape(t) for t in norm(sound).split()]
    if not toks:
        return None
    # allow punctuation/hyphens/apostrophes between the pieces: "Crip-tick", "crip, tick"
    body = r"[\s\-,.']*".join(toks)
    return re.compile(r"(?<![\w'])" + body + r"(?![\w])", re.I)


def apply(text, entries):
    """Replace learned sound-alikes (and wrong capitalisation) with your spellings."""
    if not text or not entries:
        return text
    pairs = []
    for e in entries:
        word = e["word"].strip()
        if not word:
            continue
        pairs.append((word, word))
        for snd in e.get("sounds", []):
            if snd:
                pairs.append((snd, word))
    pairs.sort(key=lambda p: -len(p[0]))
    for snd, word in pairs:
        pat = _pattern(snd)
        if pat is None:
            continue
        text = pat.sub(word, text)
    # Gentle fuzzy pass for capitalised words the model invented (names usually are capitalised)
    targets = {}
    for e in entries:
        for k in [e["word"]] + list(e.get("sounds", [])):
            nk = norm(k).replace(" ", "")
            if len(nk) >= 5:
                targets[nk] = e["word"]

    def fix(m):
        w = m.group(0)
        nw = norm(w)
        if len(nw) < 5 or nw in COMMON:
            return w
        best, best_r = None, 0.0
        for k, word in targets.items():
            r = difflib.SequenceMatcher(None, nw, k).ratio()
            if r > best_r:
                best, best_r = word, r
        return best if best and best_r >= 0.86 else w
    if targets:
        text = re.sub(r"(?<![\w'])[A-Z][a-zA-Z]{3,}(?![\w])", fix, text)
    return text
