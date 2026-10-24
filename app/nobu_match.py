"""Fuzzy matching of the spoken commands against what the small model heard.

The wake word is pronounced "no boo". Whisper writes that many ways
("No boo", "No, boo.", "Nobu", "Noboo", "Know Boo", "No Bu" ...), so we compare
the 1-2 words before "record this" / "end recording" against a set of known
spellings plus the ones learned from the user's own voice.

A "word" is any object with .text, .start, .end (seconds, relative to the audio
that was transcribed).
"""
import difflib
import re
from collections import namedtuple

Word = namedtuple("Word", "text start end")

ALIASES = {
    "noboo", "nobu", "nobo", "nobuu", "knobu", "knoboo", "knowboo", "knowbu", "nowboo", "nowbu",
    "nooboo", "noobu", "noboh", "nabu", "naboo", "newboo", "newbu", "nubu", "noboom", "noboot",
    "nobue", "nobuo", "novu", "novo", "nebu", "noeboo", "nobooh", "nobou", "noobo", "noobie",
    "nobody", "noble", "nobel", "noboe", "nubo", "nboo", "nobook",
}
TARGETS = ("noboo", "nobu")
STOPWORDS = {"the", "a", "an", "and", "i", "to", "of", "it", "so", "we", "you", "he", "she", "they",
             "um", "uh", "oh", "ok", "okay", "hey", "please", "now", "then", "just"}
_THIS = {"this", "that", "it", "dis", "thus", "these", "his", "is", "this's", "thiss", "diss"}
_STOP_VERBS = {"end", "stop", "finish", "and", "in", "n", "ended", "ending", "an"}


def norm(text):
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _tokens(words):
    out = []
    for w in words:
        t = norm(w.text)
        if t:
            out.append((t, float(w.start), float(w.end)))
    return out


def _ratio(a, b):
    return difflib.SequenceMatcher(None, a, b).ratio()


def wake_score(prev_tokens, extra=()):
    """How much the 1-2 tokens before the command look like 'No boo' (0..1).

    Returns (score, number_of_tokens_used)."""
    extra = set(extra)
    cands = []
    if len(prev_tokens) >= 1:
        cands.append((prev_tokens[-1], 1))
    if len(prev_tokens) >= 2:
        cands.append((prev_tokens[-2] + prev_tokens[-1], 2))
    best, used = 0.0, 0
    for c, n in cands:
        if c in extra:
            s = 1.0
        elif c in ALIASES:
            s = 0.95
        elif c in STOPWORDS or c in ("no", "not", "know", "now", "new", "nope", "nah"):
            s = 0.0
        elif not c.startswith(("n", "kn", "gn")):
            # "no boo" always starts with an n sound; avoids e.g. "do not" -> "donot"
            s = max(_ratio(c, e) for e in extra) - 0.05 if extra else 0.0
        else:
            s = max(_ratio(c, t) for t in TARGETS)
            if extra:
                s = max(s, max(_ratio(c, e) for e in extra) - 0.05)
        if s > best or (s == best and n > used):
            best, used = s, n
    return best, used


def _is_record(t):
    return t in ("record", "records", "recorded") or _ratio(t, "record") >= 0.8


def _find_pair(tokens, first_ok, second_ok):
    for i in range(len(tokens) - 1):
        if first_ok(tokens[i][0]) and second_ok(tokens[i + 1][0]):
            return i
    return -1


def match_wake(words, threshold=0.5, accept_bare=True, extra=()):
    """Look for 'No boo, record this'. Returns (matched, phrase_end_time, score)."""
    toks = _tokens(words)
    if not toks:
        return False, 0.0, 0.0
    # whisper sometimes glues words: "recordthis", "nobooRecord"
    for k, (t, s, e) in enumerate(toks):
        if t in ("recordthis", "recordthat"):
            score, _ = wake_score([p[0] for p in toks[max(0, k - 2):k]], extra)
            if score >= threshold or (accept_bare and len(toks) <= 2):
                return True, e, score
    i = _find_pair(toks, _is_record, lambda t: t in _THIS)
    if i < 0:
        return False, 0.0, 0.0
    prev = [p[0] for p in toks[max(0, i - 2):i]]
    score, _ = wake_score(prev, extra)
    end = toks[i + 1][2]
    if score >= threshold:
        return True, end, score
    if accept_bare and i == 0 and len(toks) <= 3:
        return True, end, score
    return False, 0.0, score


_EDIT = {"edit", "edits", "edited", "edith", "edict", "eddit", "editt", "addit", "edet"}
_CUT = {"cut", "cuts", "cutt", "kut", "cutting"}


# ---------------------------------------------------------------- learned phrases
# "Teach Nobu my voice" stores how the speech model writes each command when *you* say it
# (e.g. "nowgrouprecordthis"). Those exact-ish spellings are then accepted as the command.
SAMPLE_MIN_RATIO = 0.86


def phrase_key(words):
    return "".join(t for t, _, _ in _tokens(words))


def _sample_match(toks, samples, kinds):
    """Best (kind, start_i, end_i, ratio) of any 2-7 token window against learned samples."""
    best = (None, 0, 0, 0.0)
    if not samples or not toks:
        return best
    for kind in kinds:
        for smp in samples.get(kind, ()) or ():
            if len(smp) < 8:
                continue
            for i in range(len(toks)):
                joined = ""
                for j in range(i, min(len(toks), i + 7)):
                    joined += toks[j][0]
                    if len(joined) < len(smp) * 0.7:
                        continue
                    if len(joined) > len(smp) * 1.35:
                        break
                    r = _ratio(joined, smp)
                    if r > best[3]:
                        best = (kind, i, j, r)
    return best if best[3] >= SAMPLE_MIN_RATIO else (None, 0, 0, best[3])


def match_command(words, threshold=0.5, accept_bare=True, extra=(), in_note=False, samples=None):
    """Recognise 'No boo, record this' / 'edit this' / 'cut this'.

    edit/cut are only considered when in_note is True and always need the wake word.
    Returns (kind or None, phrase_end_time, score)."""
    toks = _tokens(words)
    if not toks:
        return None, 0.0, 0.0
    if in_note:
        best = (None, 0.0, 0.0)
        for kind, verbs, glued in (("edit", _EDIT, ("editthis", "editthat")), ("cut", _CUT, ("cutthis", "cutthat"))):
            for k, (t, s, e) in enumerate(toks):
                if t in glued:
                    score, _ = wake_score([p[0] for p in toks[max(0, k - 2):k]], extra)
                    if score >= threshold and score > best[2]:
                        best = (kind, e, score)
            i = _find_pair(toks, lambda t, v=verbs: t in v, lambda t: t in _THIS)
            if i >= 0:
                score, _ = wake_score([p[0] for p in toks[max(0, i - 2):i]], extra)
                if score >= threshold and score > best[2]:
                    best = (kind, toks[i + 1][2], score)
        if best[0]:
            return best
    ok, end, score = match_wake(words, threshold, accept_bare, extra)
    if ok:
        return "record", end, score
    kind, _i, j, r = _sample_match(toks, samples, ("edit", "cut", "record") if in_note else ("record",))
    if kind:
        return kind, toks[j][2], r
    return None, 0.0, score


def match_stop(words, threshold=0.5, accept_bare=True, extra=(), samples=None):
    """Look for 'No boo, end recording' (also 'stop recording').

    Returns (matched, cut_time, score); cut_time is where the command starts."""
    toks = _tokens(words)
    if len(toks) < 2:
        return False, 0.0, 0.0
    kind, i0, _j, r = _sample_match(toks, samples, ("stop",))
    if kind:
        return True, toks[i0][1], r
    i = _find_pair(
        toks,
        lambda t: t in _STOP_VERBS,
        lambda t: t.startswith("record") or _ratio(t, "recording") >= 0.75,
    )
    if i < 0:
        return False, 0.0, 0.0
    prev_t = toks[max(0, i - 2):i]
    score, used = wake_score([p[0] for p in prev_t], extra)
    if score >= threshold and prev_t:
        cut = prev_t[-used][1] if used and len(prev_t) >= used else toks[i][1]
        return True, cut, score
    if accept_bare and i == 0 and len(toks) <= 3 and toks[i][0] in ("end", "stop", "finish"):
        return True, toks[i][1], score
    return False, 0.0, score




CANON = {"record": ("noboorecordthis", "noburecordthis"), "edit": ("nobooeditthis", "nobueditthis"),
         "cut": ("noboocutthis", "nobucutthis"), "stop": ("nobooendrecording", "nobuendrecording",
                                                         "nobustoprecording")}


def _best_window(toks, targets):
    best = 0.0
    for tgt in targets:
        for i in range(len(toks)):
            joined = ""
            for j in range(i, min(len(toks), i + 7)):
                joined += toks[j][0]
                if len(joined) > len(tgt) * 1.4:
                    break
                if len(joined) >= len(tgt) * 0.6:
                    best = max(best, _ratio(joined, tgt))
    return best


def near_miss(words, extra=(), stop=False, samples=None, in_note=False):
    """Did this sound *almost* like a command? Then it is worth a second, more careful listen.
    Judged by how close the words are to a command phrase (or to how you said it when teaching),
    so ordinary talk never gets a second listen - which keeps the hinted listen from 'hearing'
    a command that wasn't said."""
    toks = _tokens(words)
    if not toks or len(toks) > 14:
        return False
    kinds = ("stop",) if stop else (("record", "edit", "cut") if in_note else ("record",))
    targets = [t for k in kinds for t in CANON[k]] + [x for k in kinds for x in (samples or {}).get(k, ()) or ()]
    return _best_window(toks, targets) >= 0.5


def consistent(first, second):
    """Is the second (hinted) listen a believable re-hearing of the first? Rejects the model just
    repeating the hint, or looping on a sound ('Oof. Oof. Oof...')."""
    a, b = _tokens(first), _tokens(second)
    if not b or len(b) > len(a) + 4:
        return False
    counts = {}
    for t, _, _ in b:
        counts[t] = counts.get(t, 0) + 1
    if max(counts.values()) > 3:
        return False
    return _ratio("".join(t for t, _, _ in a), "".join(t for t, _, _ in b)) >= 0.45


def learn_aliases(words, kind="record"):
    """From an utterance of the wake/stop phrase, return the spellings of 'No boo' it contains."""
    toks = [t for t, _, _ in _tokens(words)]
    if not toks:
        return []
    idx = None
    for k, t in enumerate(toks):
        if kind == "edit" and (t in _EDIT or t in ("editthis", "editthat") or _ratio(t, "edit") >= 0.75):
            idx = k
            break
        if kind == "cut" and (t in _CUT or t in ("cutthis", "cutthat")):
            idx = k
            break
        if kind == "stop" and (t.startswith("record") or _ratio(t, "recording") >= 0.75):
            idx = k - 1 if k > 0 and toks[k - 1] in _STOP_VERBS else k     # "nobu END recording"
            break
        if kind == "record" and (_is_record(t) or t.startswith("record") or t in ("recordthis", "recordthat")):
            idx = k
            break
        if t in ("end", "stop") and k + 1 < len(toks) and toks[k + 1].startswith("record"):
            idx = k
            break
    if idx is None and kind in ("edit", "cut"):
        return []          # the verb itself was misheard: only the whole-phrase sample is learned
    prev = toks[:idx] if idx is not None else toks[:2]
    prev = prev[-2:]
    out = []
    if prev:
        if prev[-1] not in STOPWORDS and len(prev[-1]) >= 3:
            out.append(prev[-1])
        if len(prev) == 2:
            out.append(prev[0] + prev[1])
    return [a for a in out if a and a not in STOPWORDS]


def words_text(words):
    return " ".join(w.text.strip() for w in words).strip()
