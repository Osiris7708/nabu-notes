"""Voice commands: wake/stop phrase matching, and the recording engine's decisions
(when to start, when to stop, teach mode, second listen, keeping the natural sound).
The transcriber is faked, so no speech model is needed. The engine parts need a real
recording of the wake phrase (see _here.voice_sample) and are skipped without one."""
import _here  # finds the app and keeps the test away from your real notes
import os, tempfile, time, wave
os.environ["NOBU_HOME"] = tempfile.mkdtemp()
import numpy as np
import nobu_config as C
import nobu_audio as A
from nobu_match import Word, match_wake, match_stop, learn_aliases

OK = []
def check(name, cond, info=""):
    OK.append(bool(cond))
    print(("PASS  " if cond else "FAIL  ") + name + ("" if cond else "   -> %s" % (info,)))

def W(s, t0=0.0, dt=0.3):
    out, t = [], t0
    for x in s.split():
        out.append(Word(x, t, t + dt - 0.05)); t += dt
    return out

# ------------------------------------------------------------ phrase matching (no audio needed)
yes = ["No boo, record this.", "No, boo. Record this.", "Nobu record this", "Noboo, record this", "Know Boo record this",
       "No Bu, record this", "Now boo, record this", "Hey, no boo, record this.", "Record this.", "No book record this",
       "Number, record this", "Noble, record this", "Nope record this", "No boo. Record these.", "Nobooh record this"]
KNOWN_MISSES = {"Number, record this", "Nope record this"}      # too far from "Nobu" - accepted on purpose
no = ["I will record this later", "Please record the meeting", "No boo, end recording", "The record this year was broken",
      "no record of this", "Do not record this", "and record this"]
misses = {s for s in yes if not match_wake(W(s))[0]}
check("wake phrase heard in all its usual mishearings", misses <= KNOWN_MISSES, misses - KNOWN_MISSES)
check("ordinary sentences never start a recording", not [s for s in no if match_wake(W(s))[0]],
      [s for s in no if match_wake(W(s))[0]])
sy = ["No boo, end recording.", "No, boo, end recording", "Nobu stop recording",
      "and the dragon fell. No boo, end recording", "End recording", "Know boo and recording"]
sn = ["She said end recording was not the way", "the end of the recording"]
check("stop phrase heard", not [s for s in sy if not match_stop(W(s))[0]], [s for s in sy if not match_stop(W(s))[0]])
check("ordinary sentences never stop a recording", not [s for s in sn if match_stop(W(s))[0]])
check("stop phrase at the end of a sentence is found", match_stop(W("and the dragon fell. No boo, end recording"))[0])
check("Teach learns a new way of saying Nobu", learn_aliases(W("Gnu Boo, record this")) == ["boo", "gnuboo"]
      and learn_aliases(W("Noobah record this")) == ["noobah"] and learn_aliases(W("the record this")) == [])
check("...and uses it", match_wake(W("Gnu Boo, record this"), extra=["gnuboo"])[0])

# ------------------------------------------------------------ the engine, fed with real sound
sample = _here.voice_sample()
if not sample:
    print("SKIP  engine checks: no voice recording found (see tests/_here.py)")
else:
    SR = 16000
    with wave.open(sample) as w:
        raw = np.frombuffer(w.readframes(w.getnframes()), np.int16)
    NOISE = raw[:int(2.8 * SR)]; SPEECH = raw[int(4.25 * SR):int(5.45 * SR)]
    def noise(sec):
        n = int(sec * SR); return np.tile(NOISE, n // len(NOISE) + 1)[:n]
    def talk(sec, gap=0.35):
        out = []
        while sum(map(len, out)) < sec * SR:
            out += [SPEECH, noise(gap)]
        return np.concatenate(out)[:int(sec * SR)]
    class FakeDet:
        """Stands in for the speech model: returns scripted words; 'prompted' = the second listen."""
        def __init__(s, script, script_p=()):
            s.script, s.script_p, s.calls = list(script), list(script_p), []
        def detect(s, audio, prompt=None):
            s.calls.append((round(len(audio) / SR, 2), bool(prompt)))
            q = s.script_p if prompt else s.script
            return q.pop(0) if q else []
    def engine(det, cfgkw={}):
        C.ensure_dirs(); cfg = C.Config(path=os.path.join(C.HOME, "c.json")); cfg._data.update(cfgkw)
        ev = []
        eng = A.Engine(cfg, det, lambda n, **k: ev.append((n, k)), C.RECORDINGS_DIR, start_stream=False)
        return eng, ev
    def feed(eng, audio):
        pend = np.zeros(0, np.int16)
        for i in range(0, len(audio), 800):
            pend = np.concatenate([pend, eng.frontend.process2(audio[i:i + 800])[0]])
            while len(pend) >= 800:
                b, pend = pend[:800], pend[800:]; eng.process_block(b)
    def run(parts, script, script_p=(), cfgkw={}):
        det = FakeDet(script, script_p); eng, ev = engine(det, cfgkw); feed(eng, np.concatenate(parts))
        return ev, det, eng
    def finished(ev):
        return [k for n, k in ev if n == "recording_finished"]
    def secs(k):
        with wave.open(k["path"]) as w:
            return w.getnframes() / w.getframerate()
    WK = lambda: W("No boo, record this", 0.5, 0.4)

    ev, det, eng = run([noise(2), SPEECH, noise(1.0), talk(20), noise(10)], [WK()])
    f = finished(ev)
    check("20 s of talking is not cut short", len(f) == 1 and f[0]["reason"] == "silence" and secs(f[0]) >= 20,
          [(k["reason"], secs(k)) for k in f])
    check("the countdown is shown before stopping on silence",
          [k["seconds_left"] for n, k in ev if n == "quiet"][:6] == [5, 4, 3, 2, 1, 0])

    ev, det, eng = run([noise(2), SPEECH, noise(1.0), talk(5), noise(2.5), talk(5), noise(3), talk(4), noise(10)], [WK()])
    f = finished(ev)
    check("thinking pauses do not stop a recording", len(f) == 1 and secs(f[0]) >= 20, [(k["reason"], secs(k)) for k in f])

    ev, det, eng = run([noise(2), SPEECH, noise(1), talk(6), noise(1.2), SPEECH, noise(1.5)],
                       [WK(), W("blah"), W("No boo end recording", 0, 0.3)])
    f = finished(ev)
    check("saying the stop phrase stops the recording", len(f) == 1 and f[0]["reason"] == "phrase", f)

    ev, det, eng = run([noise(30)], [])
    check("background noise alone never wakes the speech model", not ev and not det.calls, (ev, det.calls))

    det = FakeDet([W("Gnu boo record this")]); eng, ev = engine(det); eng._command("teach", {"on": True})
    feed(eng, np.concatenate([noise(2), SPEECH, noise(1.5)]))
    check("Teach Nobu my voice hears the phrase", [n for n, k in ev] == ["teach_heard"]
          and ev[0][1].get("aliases") == ["boo", "gnuboo"], ev)

    ev, det, eng = run([noise(2), SPEECH, noise(1.0), talk(3), noise(10)], [W("Now grew, wreck or this", 0.5, 0.4)], [WK()])
    check("a misheard wake phrase gets a second listen that catches it",
          any(n == "recording_started" for n, k in ev) and any(p for _, p in det.calls), det.calls)

    ev, det, eng = run([noise(2), SPEECH, noise(1.0), talk(3), noise(10)], [W("Now group wreck it this", 0.5, 0.4)], [],
                       {"phrase_samples": {"record": ["nowgroupwreckitthis"]}})
    check("a phrase learned in Teach is accepted straight away",
          any(n == "recording_started" for n, k in ev) and not any(p for _, p in det.calls), det.calls)

    det = FakeDet([]); eng, ev = engine(det, {"edit_silence_seconds": 0}); eng._start_recording([], "edit")
    feed(eng, np.concatenate([talk(3), noise(15)]))
    check("edit recordings with the silence stop off keep going", eng.rec is not None and not finished(ev))

    ev, det, eng = run([noise(2), talk(3), noise(3)], [W("so the weather was lovely today")], [])
    check("ordinary chatter is ignored (no second listen)", not ev and not any(p for _, p in det.calls), (ev, det.calls))

    # the natural sound is kept for transcribing when "transcribe_original" is on
    rng = np.random.default_rng(1)
    fan = rng.normal(0, 700, SR * 12).astype(np.int16)
    def mix(sp):
        return np.clip(fan[:len(sp)].astype(np.int32) + sp.astype(np.int32), -32768, 32767).astype(np.int16)
    class Silent:
        def detect(s, a, prompt=None): return []
    bg = {}
    for orig in (True, False):
        C.ensure_dirs(); cfg = C.Config(path=os.path.join(C.HOME, "c%d.json" % orig))
        cfg._data.update(noise_reduction=1.0, transcribe_original=orig, silence_stop_seconds=30)
        ev = []
        eng = A.Engine(cfg, Silent(), lambda n, **k: ev.append((n, k)), C.RECORDINGS_DIR, start_stream=False)
        eng.start()
        eng.command("start_recording", mode="record")
        audio = np.concatenate([fan[:SR * 3], mix(np.tile(SPEECH, 3)), fan[:SR * 3]])
        for i in range(0, len(audio), 800):
            eng.feed(audio[i:i + 800])
        time.sleep(1.5); eng.command("stop_recording"); time.sleep(1.0)
        f = finished(ev); eng.shutdown()
        if f:
            with wave.open(f[0]["path"]) as w:
                d = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float64)
            bg[orig] = np.sqrt(np.mean(d[SR // 2: SR * 2] ** 2))
    check("noise filter on: the recording is cleaned; 'keep natural sound' keeps it as heard",
          len(bg) == 2 and bg[True] > 5 * bg[False], bg)

print("RESULT %d/%d passed" % (sum(OK), len(OK)))
