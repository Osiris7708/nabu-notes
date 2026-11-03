"""Microphone listening, wake-phrase handling and recording.

Signal path:  mic -> Frontend (gain, hum/rumble filter, noise reduction)
              -> SpeechDetector (neural VAD)  -> state machine below.
The speech model is only asked to listen to short bursts of real speech, so in a
quiet (or steadily noisy) room the program is essentially idle.
"""
import collections
import datetime
import logging
import os
import queue
import threading
import time
import wave

import numpy as np

from nabu_dsp import Frontend, SpeechDetector
from nabu_match import consistent, learn_aliases, match_command, match_stop, near_miss, words_text

log = logging.getLogger("nabu.audio")

SR = 16000
BLOCK = 800                 # 50 ms
BLOCK_S = BLOCK / SR
HANG_BLOCKS = 14            # 0.7 s of quiet ends an utterance (for command checks)
PREROLL_BLOCKS = 10         # 0.5 s kept from before speech starts
EARLY_BLOCKS = 80           # 4 s: check for the wake phrase even if speech continues
MIN_SPEECH_BLOCKS = 5       # ignore sounds shorter than 0.25 s
STOP_TAIL_BLOCKS = 90       # look at the last 4.5 s of an utterance for the stop phrase
MAX_REC_UTTER_BLOCKS = 240  # keep 12 s for stop-phrase checking
TEACH_MAX_BLOCKS = 140      # 7 s
TEACH_HANG_BLOCKS = 22      # while teaching, a 1.1 s pause ends a phrase (so "Nabu ... record this" stays one)
CAPTURE_MAX_BLOCKS = 120    # 6 s for a dictionary pronunciation sample
# A second, more careful listen for things that sounded *almost* like a command: the small
# model is told which words to expect, which fixes most "said it twice" moments.
WAKE_HINT = "Nabu, record this. Nabu, edit this. Nabu, cut this."
STOP_HINT = "Nabu, end recording."


class Block(np.ndarray):
    """50 ms of cleaned sound; .light is the same 50 ms as originally heard (no noise reduction)."""
    light = None


def write_wav(path, data):
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(np.asarray(data, np.int16).tobytes())


class Engine:
    """Listens, reacts to the wake phrase, records, and reports events."""

    def __init__(self, cfg, detector, on_event, recordings_root, start_stream=True, heard_dir=None,
                 commands_dir=None):
        self.cfg = cfg
        self.detector = detector
        self.on_event = on_event
        self.recordings_root = recordings_root
        self.heard_dir = heard_dir
        self.commands_dir = commands_dir or recordings_root
        self.note_open = False      # set by the app: a note is open & visible -> edit/cut allowed
        self.capture = None         # dictionary sample capture
        self._use_stream = start_stream
        self.q = queue.Queue()
        self.thread = None
        self.stream = None
        self.stream_sr = SR
        self.state = "idle"        # idle | recording | paused | nomic | stopped
        self.frontend = Frontend(cfg["mic_gain_db"], cfg["noise_reduction"])
        self.vad = SpeechDetector(cfg["speech_sensitivity"])
        self.preroll = collections.deque(maxlen=PREROLL_BLOCKS)
        self.u = None
        self.rec = None
        self.teach = False
        self.test = None
        self.level = 0.0
        self.raw_level = 0.0
        self.peak = 0
        self.detections = collections.deque(maxlen=40)
        self.last_block_time = time.time()
        self.next_retry = 0.0
        self._running = False
        self._last_quiet_emit = None

    # ------------------------------------------------------------ helpers
    def _emit(self, name, **kw):
        try:
            self.on_event(name, **kw)
        except Exception:
            log.exception("event handler failed: %s", name)

    def _set_state(self, st):
        if st != self.state:
            self.state = st
            self._emit("state", state=st)

    def _aliases(self):
        return tuple(self.cfg["wake_aliases"] or ())

    def _samples(self):
        return self.cfg.get("phrase_samples") or {}

    def _note_detection(self, kind, words, matched, score, audio=None):
        text = words_text(words)
        self.detections.append((time.strftime("%H:%M:%S"), kind, text, bool(matched), round(float(score), 2)))
        if self.cfg["debug"]:
            log.info("detect[%s] %r matched=%s score=%.2f", kind, text, matched, score)
        if audio is not None and self.cfg["save_heard_clips"] and self.heard_dir:
            try:
                os.makedirs(self.heard_dir, exist_ok=True)
                stamp = time.strftime("%Y%m%d_%H%M%S")
                name = "%s_%s_%s.wav" % (stamp, kind, "yes" if matched else "no")
                write_wav(os.path.join(self.heard_dir, name), audio)
                with open(os.path.join(self.heard_dir, "heard.txt"), "a", encoding="utf-8") as f:
                    f.write("%s\t%s\t%s\t%.2f\t%s\n" % (name, kind, matched, score, text))
                files = sorted(x for x in os.listdir(self.heard_dir) if x.endswith(".wav"))
                for old in files[:-200]:
                    os.remove(os.path.join(self.heard_dir, old))
            except Exception:
                log.exception("could not save heard clip")

    def _detect(self, blocks, prompt=None):
        if not blocks:
            return [], None
        audio = np.concatenate(blocks)
        x = audio.astype(np.float32)
        peak = float(np.max(np.abs(x))) if len(x) else 0.0
        if 0 < peak < 16000:   # level the clip so quiet voices are heard as well as loud ones
            x = x * min(8.0, 16000.0 / peak)
        try:
            if prompt:
                return self.detector.detect(x.astype(np.int16), prompt=prompt), audio
            return self.detector.detect(x.astype(np.int16)), audio
        except Exception:
            log.exception("detector failed")
            return [], audio

    # ------------------------------------------------------------ lifecycle
    def start(self):
        if self._running:
            return
        self._running = True
        self.thread = threading.Thread(target=self._run, name="nabu-engine", daemon=True)
        self.thread.start()
        if self._use_stream:
            self.q.put(("cmd", "open", {}))

    def shutdown(self):
        if not self._running:
            return
        self.q.put(("cmd", "quit", {}))
        if self.thread:
            self.thread.join(timeout=15)
        self._close_stream()

    def command(self, name, **kw):
        self.q.put(("cmd", name, kw))

    def feed(self, block):
        """Feed raw int16 mono audio at 16 kHz (tests; the mic callback does the same)."""
        self.q.put(("a", block))

    # ------------------------------------------------------------ microphone
    def _open_stream(self):
        if not self._use_stream:
            return
        try:
            import sounddevice as sd
        except Exception as e:
            self._emit("error", message="Audio library failed to load: %s" % e)
            self._set_state("nomic")
            return
        dev = self.cfg["mic_device"]
        if dev in ("", "default"):
            dev = None
        if dev is not None:
            try:
                want = self.cfg["mic_device_name"] or ""
                devs = sd.query_devices()
                if not (0 <= int(dev) < len(devs)) or (want and devs[int(dev)]["name"] != want):
                    dev = None
                    for i, d in enumerate(devs):
                        if d["max_input_channels"] > 0 and d["name"] == want:
                            dev = i
                            break
            except Exception:
                dev = None
        last_err = None
        for sr in (SR, None):
            try:
                use_sr = sr
                if use_sr is None:
                    info = sd.query_devices(dev, "input")
                    use_sr = int(info["default_samplerate"])
                bs = int(use_sr * BLOCK_S)
                self.stream = sd.InputStream(
                    samplerate=use_sr, channels=1, dtype="int16", blocksize=bs,
                    device=dev, callback=self._callback, latency="high")
                self.stream.start()
                self.stream_sr = use_sr
                self.last_block_time = time.time()
                log.info("microphone open at %s Hz (device=%s, detector=%s)", use_sr, dev, self.vad.kind)
                if self.state in ("nomic", "stopped"):
                    self._set_state("idle")
                return
            except Exception as e:  # noqa
                last_err = e
                self.stream = None
        self.next_retry = time.time() + 5
        log.warning("cannot open microphone: %s", last_err)
        if self.state != "nomic":
            self._emit("error", message="Cannot open the microphone: %s" % last_err)
        self._set_state("nomic")

    def _close_stream(self):
        s, self.stream = self.stream, None
        if s is not None:
            try:
                s.stop()
                s.close()
            except Exception:
                pass

    def _callback(self, indata, frames, time_info, status):
        blk = indata[:, 0].copy()
        if self.stream_sr != SR:
            blk = self._resample(blk, self.stream_sr)
        self.q.put(("a", blk))

    @staticmethod
    def _resample(blk, sr):
        if sr % SR == 0:
            f = sr // SR
            n = (len(blk) // f) * f
            return blk[:n].reshape(-1, f).mean(axis=1).astype(np.int16)
        n_out = int(len(blk) * SR / sr)
        xs = np.linspace(0, len(blk) - 1, n_out)
        return np.interp(xs, np.arange(len(blk)), blk.astype(np.float32)).astype(np.int16)

    # ------------------------------------------------------------ main loop
    def _run(self):
        pending = np.zeros(0, dtype=np.int16)
        lpending = np.zeros(0, dtype=np.int16)
        while True:
            try:
                item = self.q.get(timeout=1.0)
            except queue.Empty:
                self._watchdog()
                continue
            try:
                if item[0] == "a":
                    self.last_block_time = time.time()
                    if self.state in ("paused", "stopped"):
                        continue
                    raw = item[1]
                    self.peak = int(np.max(np.abs(raw.astype(np.int32)))) if len(raw) else 0
                    clean, light = self.frontend.process2(raw)
                    self.raw_level = self.frontend.raw_level
                    pending = np.concatenate([pending, clean]) if len(pending) else clean
                    lpending = np.concatenate([lpending, light]) if len(lpending) else light
                    while len(pending) >= BLOCK:
                        blk = pending[:BLOCK].view(Block)
                        blk.light = lpending[:BLOCK]
                        pending, lpending = pending[BLOCK:], lpending[BLOCK:]
                        self.process_block(blk)
                else:
                    if item[1] == "quit":
                        if self.rec:
                            self._finish("quit")
                        self._set_state("stopped")
                        self._running = False
                        return
                    self._command(item[1], item[2])
            except Exception:
                log.exception("engine error")

    def _watchdog(self):
        if not self._use_stream or self.state in ("paused", "stopped"):
            return
        now = time.time()
        if self.stream is None and now >= self.next_retry:
            self._open_stream()
        elif self.stream is not None and now - self.last_block_time > 4.0:
            log.warning("no audio for 4 s, reopening the microphone")
            self._close_stream()
            self._open_stream()

    def _command(self, name, kw):
        if name == "open":
            self._open_stream()
        elif name == "pause":
            if self.rec:
                self._finish("manual")
            self._close_stream()
            self.u = None
            self._set_state("paused")
        elif name == "resume":
            self._set_state("idle")
            self._open_stream()
        elif name == "reconfigure":
            self.frontend.set_params(self.cfg["mic_gain_db"], self.cfg["noise_reduction"])
            self.vad.set_sensitivity(self.cfg["speech_sensitivity"])
            if kw.get("reopen") and self.state != "paused":
                self._close_stream()
                self._open_stream()
        elif name == "relearn_noise":
            self.frontend.reset_noise()
        elif name == "teach":
            self.teach = bool(kw.get("on"))
            self.u = None
        elif name == "capture":
            self.capture = {"path": kw["path"], "tag": kw.get("tag")}
            self.u = None
        elif name == "cancel_capture":
            self.capture = None
        elif name == "test_record":
            self.test = {"blocks": [], "need": int(kw.get("seconds", 6) / BLOCK_S), "path": kw["path"]}
        elif name == "start_recording":
            if not self.rec and self.state == "idle":
                self._start_recording([], kw.get("mode", "record"))
        elif name == "stop_recording":
            if self.rec:
                self._finish("manual")

    # ------------------------------------------------------------ block logic
    def process_block(self, blk):
        speech = self.vad.push(blk)
        self.frontend.speech = speech or self.vad.prob > 0.3
        self.level = self.vad.level
        if self.test is not None:
            t = self.test
            t["blocks"].append(blk)
            if len(t["blocks"]) >= t["need"]:
                self.test = None
                try:
                    write_wav(t["path"], np.concatenate(t["blocks"]))
                    self._emit("test_done", path=t["path"])
                except Exception as e:
                    self._emit("error", message="Test recording failed: %s" % e)
            return
        if self.rec is not None:
            self._rec_block(blk, speech)
        else:
            self._idle_block(blk, speech)

    def _idle_block(self, blk, speech):
        u = self.u
        if u is None:
            if not speech:
                self.preroll.append(blk)
                return
            self.u = {
                "items": [(b, False) for b in self.preroll] + [(blk, True)],
                "sil": 0, "speech": 1, "checked": False, "ignore": False,
            }
            self.preroll.clear()
            return
        if u["ignore"]:
            u["sil"] = 0 if speech else u["sil"] + 1
            if u["sil"] >= HANG_BLOCKS:
                self.u = None
            return
        u["items"].append((blk, speech))
        if speech:
            u["sil"] = 0
            u["speech"] += 1
        else:
            u["sil"] += 1
        n = len(u["items"])
        ended = u["sil"] >= (TEACH_HANG_BLOCKS if self.teach else HANG_BLOCKS)
        if self.capture is not None:
            if (ended and u["speech"] >= MIN_SPEECH_BLOCKS) or n >= CAPTURE_MAX_BLOCKS:
                self._finish_capture(u)
                self.u = None if ended else dict(u, ignore=True, items=[])
            elif ended:
                self.u = None
            return
        limit = TEACH_MAX_BLOCKS if self.teach else EARLY_BLOCKS
        if not u["checked"] and not ended and n >= limit:
            u["checked"] = True
            if self.teach:
                self._teach_heard(u, limit)
                u["ignore"], u["items"] = True, []
                return
            if self._try_wake(u, EARLY_BLOCKS):
                return
            u["ignore"], u["items"] = True, []
            return
        if ended:
            self.u = None
            if not u["checked"] and u["speech"] >= MIN_SPEECH_BLOCKS:
                u["checked"] = True
                if self.teach:
                    self._teach_heard(u, n)
                else:
                    self._try_wake(u, min(n, EARLY_BLOCKS + 10))

    def _finish_capture(self, u):
        c, self.capture = self.capture, None
        items = u["items"]
        last = max([i for i, (_, f) in enumerate(items) if f] or [len(items) - 1])
        blocks = [b for b, _ in items[:last + 1 + 6]]
        try:
            write_wav(c["path"], np.concatenate(blocks))
            self._emit("captured", path=c["path"], tag=c.get("tag"))
        except Exception as e:
            self._emit("error", message="Could not save the sample: %s" % e)

    def _teach_heard(self, u, nblocks):
        blocks = [b for b, _ in u["items"][:nblocks]]
        sp = [b for b, f in u["items"][:nblocks] if f]
        words, audio = self._detect(blocks)
        x = np.concatenate(sp).astype(np.float32) if sp else np.zeros(1, np.float32)
        rms = float(np.sqrt(np.mean(x * x)))
        self._note_detection("teach", words, False, 0.0, audio)
        self._emit("teach_heard", words=words, text=words_text(words),
                   aliases=learn_aliases(words), speech_rms=rms)

    def _try_wake(self, u, nblocks):
        items = u["items"]
        window = [b for b, _ in items[:nblocks]]
        words, audio = self._detect(window)
        args = (self.cfg["wake_match_threshold"], self.cfg["accept_bare_phrase"], self._aliases())
        kind, end_t, score = match_command(words, *args, in_note=self.note_open, samples=self._samples())
        if not kind and near_miss(words, self._aliases(), samples=self._samples(), in_note=self.note_open):
            first = words
            again, _a = self._detect(window, prompt=WAKE_HINT)
            if consistent(first, again):
                kind, end_t, score = match_command(again, *args, in_note=self.note_open, samples=self._samples())
                if kind:
                    words = again
            log.info("second listen: %r -> %r (%s)", words_text(first), words_text(again)[:120],
                     kind or "no command")
        self._note_detection(kind or "wake", words, bool(kind), score, audio)
        if kind:
            log.info("command %s heard as %r (score %.2f)", kind, words_text(words), score)
        if not kind:
            return False
        first_blk = min(len(items), int(end_t * SR) // BLOCK)
        remaining = items[first_blk:]
        self.u = None
        self._start_recording(remaining, kind)
        return True

    # ------------------------------------------------------------ recording
    def _start_recording(self, replay_items, mode="record"):
        folder = self.commands_dir if mode == "cut" else self.recordings_root
        os.makedirs(folder, exist_ok=True)
        stamp = datetime.datetime.now()
        base = stamp.strftime("%Y-%m-%d_%H-%M-%S") + ("_cut" if mode == "cut" else "")
        path = os.path.join(folder, base + ".wav")
        k = 2
        while os.path.exists(path) or os.path.exists(path + ".part"):
            path = os.path.join(folder, "%s_%d.wav" % (base, k))
            k += 1
        part = open(path + ".part", "wb")
        self.rec = {
            "path": path, "part": part, "samples": 0, "flags": [], "speech": 0,
            "quiet": 0, "u": None, "started": stamp, "mode": mode,
        }
        self._last_quiet_emit = None
        self.preroll.clear()
        self._set_state("recording")
        self._emit("recording_started", path=path, mode=mode)
        for b, f in replay_items:
            if self.rec is None:
                break
            self._rec_block(b, f)

    def _rec_block(self, blk, speech):
        r = self.rec
        if r is None:
            return
        keep = blk.light if (self.cfg.get("transcribe_original", True) and getattr(blk, "light", None) is not None) else blk
        r["part"].write(np.asarray(keep, np.int16).tobytes())
        r["samples"] += len(blk)
        # For the "stop after silence" timer, be generous: anything that might be
        # voice (even a soft word) counts as talking.
        talking = speech or self.vad.prob > 0.2
        r["flags"].append(bool(talking))
        if talking:
            r["speech"] += 1
            r["quiet"] = 0
        else:
            r["quiet"] += 1
        ru = r["u"]
        if ru is None:
            if speech:
                r["u"] = {"start": r["samples"] - len(blk), "blocks": [blk], "sil": 0, "speech": 1}
        else:
            ru["blocks"].append(blk)
            if speech:
                ru["sil"] = 0
                ru["speech"] += 1
            else:
                ru["sil"] += 1
            if len(ru["blocks"]) > MAX_REC_UTTER_BLOCKS:
                drop = len(ru["blocks"]) - MAX_REC_UTTER_BLOCKS
                ru["blocks"] = ru["blocks"][drop:]
                ru["start"] += drop * BLOCK
            if ru["sil"] >= HANG_BLOCKS:
                r["u"] = None
                if self._check_stop(r, ru):
                    return
        if self.rec is None:
            return
        quiet_s = r["quiet"] * BLOCK_S
        limit = float(self.cfg["silence_stop_seconds"])
        if r["mode"] == "cut":
            limit = min(limit, 4.0)
        elif r["mode"] == "edit":
            es = float(self.cfg.get("edit_silence_seconds", limit))
            limit = es if es > 0 else float("inf")      # 0 = only the stop phrase / shortcut ends dictation
        left = limit - quiet_s
        shown = int(left + 0.999) if (quiet_s >= 3.0 and left != float("inf")) else None
        if shown != self._last_quiet_emit:
            self._last_quiet_emit = shown
            self._emit("quiet", seconds_left=shown)
        if quiet_s >= limit:
            self._finish("silence")
        elif r["samples"] / SR > float(self.cfg["max_record_minutes"]) * 60:
            self._finish("max")

    def _check_stop(self, r, ru):
        if ru["speech"] < 10:
            return False
        tail = ru["blocks"][-STOP_TAIL_BLOCKS:]
        tail_start = ru["start"] + (len(ru["blocks"]) - len(tail)) * BLOCK
        words, audio = self._detect(tail)
        args = (self.cfg["wake_match_threshold"], self.cfg["accept_bare_phrase"], self._aliases())
        ok, cut_t, score = match_stop(words, *args, samples=self._samples())
        if not ok and near_miss(words, self._aliases(), stop=True, samples=self._samples()):
            first = words
            again, _a = self._detect(tail, prompt=STOP_HINT)
            if consistent(first, again):
                ok, cut_t, score = match_stop(again, *args, samples=self._samples())
                if ok:
                    words = again
            log.info("second listen (stop): %r -> %r (%s)", words_text(first), words_text(again)[:120],
                     "stop" if ok else "no")
        self._note_detection("stop", words, ok, score, audio)
        if not ok:
            return False
        cut = tail_start + int(cut_t * SR) - int(0.1 * SR)
        self._finish("phrase", end=max(0, cut))
        return True

    def _finish(self, reason, end=None):
        r, self.rec = self.rec, None
        if r is None:
            return
        try:
            r["part"].close()
        except Exception:
            pass
        part = r["path"] + ".part"
        try:
            data = np.fromfile(part, dtype=np.int16)
        except Exception:
            data = np.zeros(0, dtype=np.int16)
        total = len(data)
        end = total if end is None else min(total, end)
        flags = r["flags"]
        nb = min(len(flags), end // BLOCK + 1)
        last = -1
        for i in range(nb - 1, -1, -1):
            if flags[i]:
                last = i
                break
        if last >= 0:
            end = min(end, (last + 1) * BLOCK + int(0.8 * SR))
        data = data[:end]
        speech_s = r["speech"] * BLOCK_S
        self.u = None
        self.preroll.clear()
        self._emit("quiet", seconds_left=None)
        if self.state == "recording":
            self._set_state("idle")
        if speech_s < 0.5 or len(data) < SR // 2:
            try:
                os.remove(part)
            except OSError:
                pass
            self._emit("recording_discarded", reason="no speech heard", path=r["path"], mode=r["mode"])
            return
        try:
            write_wav(r["path"], data)
            os.remove(part)
        except Exception as e:
            log.exception("could not write wav")
            self._emit("error", message="Could not save the recording: %s" % e)
            return
        log.info("recording saved: %s (%.1f s, reason=%s)", r["path"], len(data) / SR, reason)
        self._emit("recording_finished", path=r["path"], seconds=len(data) / SR,
                   reason=reason, started=r["started"], mode=r["mode"])


def recover_partial_recordings(root):
    """Turn leftover .part files (crash/power loss) into playable wavs."""
    fixed = []
    for dirpath, _dirs, files in os.walk(root):
        for f in files:
            if f.endswith(".wav.part"):
                p = os.path.join(dirpath, f)
                try:
                    data = np.fromfile(p, dtype=np.int16)
                    if len(data) >= SR // 2:
                        write_wav(p[:-5], data)
                        fixed.append(p[:-5])
                    os.remove(p)
                except Exception:
                    log.exception("could not recover %s", p)
    return fixed
