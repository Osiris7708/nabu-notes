"""Speech to text with faster-whisper, fully offline.

Detector: tiny model, used on short bursts to spot the spoken commands.
Transcriber: bigger model, used once per finished recording; unloaded again
after a few idle minutes so it does not hog memory.
"""
import gc
import logging
import os
import queue
import re
import threading
import time
import wave

import numpy as np

from nabu_config import model_dir
import nabu_dictionary
from nabu_match import Word

log = logging.getLogger("nabu.stt")


def _load_model(name, threads):
    from faster_whisper import WhisperModel
    return WhisperModel(model_dir(name), device="cpu", compute_type="int8",
                        cpu_threads=threads, num_workers=1)


def _words_from_segments(segments):
    out = []
    for seg in segments:
        ws = getattr(seg, "words", None)
        if ws:
            for w in ws:
                out.append(Word(w.word, float(w.start), float(w.end)))
        else:
            toks = seg.text.split()
            if toks:
                span = max(0.01, seg.end - seg.start) / len(toks)
                for i, t in enumerate(toks):
                    out.append(Word(t, seg.start + i * span, seg.start + (i + 1) * span))
    return out


class Detector:
    def __init__(self, cfg):
        self.cfg = cfg
        self.model = None
        self.lock = threading.Lock()

    def reload(self):
        with self.lock:
            self.model = None

    def warm(self):
        with self.lock:
            if self.model is None:
                self.model = _load_model(self.cfg["detect_model"], 2)

    def detect(self, audio_int16, prompt=None):
        with self.lock:
            if self.model is None:
                self.model = _load_model(self.cfg["detect_model"], 2)
            audio = audio_int16.astype(np.float32) / 32768.0
            kw = {}
            prompt = (prompt or self.cfg["detect_prompt"] or "").strip()
            if prompt:
                kw["initial_prompt"] = prompt
            segs, _ = self.model.transcribe(
                audio, language="en", beam_size=1, best_of=1, temperature=0.0,
                condition_on_previous_text=False, word_timestamps=True,
                vad_filter=False, without_timestamps=False, **kw)
            return _words_from_segments(segs)


def load_audio(path):
    if path.lower().endswith(".wav"):
        try:
            return read_wav(path)
        except Exception:
            pass
    from faster_whisper import decode_audio
    return decode_audio(path, sampling_rate=16000)


def level(audio):
    """Bring quiet recordings up to a healthy level (never louder than needed, never clipped).
    The speech model hears soft voices more reliably this way; loud recordings are left alone."""
    if not len(audio):
        return audio
    peak = float(np.percentile(np.abs(audio[::8]), 99.9))     # (every 8th sample is plenty to judge the level)
    if 0 < peak < 0.35:
        audio = np.clip(audio * min(6.0, 0.5 / peak), -1.0, 1.0).astype(np.float32)
    return audio


# How every recording is decoded. Accuracy first, but nothing that slows normal recordings down:
#  * hotwords: your dictionary names are suggested to the model in EVERY 30-second window
#    (a plain "prompt" only reaches the first 30 seconds),
#  * temperature fallback: if a stretch comes out garbled or stuck repeating itself, that stretch
#    (only) is decoded again more freely - free when nothing goes wrong,
#  * voice detection keeps natural pauses inside sentences and pads word edges, so the first and
#    last sounds of a phrase aren't clipped.
DECODE = dict(language="en", beam_size=5, best_of=5, patience=1.0, temperature=[0.0, 0.2, 0.4, 0.6, 0.8],
              compression_ratio_threshold=2.4, log_prob_threshold=-1.0, no_speech_threshold=0.6,
              condition_on_previous_text=False, vad_filter=True,
              vad_parameters=dict(threshold=0.4, min_silence_duration_ms=900, speech_pad_ms=400))


def read_wav(path):
    with wave.open(path, "rb") as w:
        n = w.getnframes()
        raw = w.readframes(n)
        ch = w.getnchannels()
    a = np.frombuffer(raw, dtype=np.int16)
    if ch > 1:
        a = a.reshape(-1, ch).mean(axis=1).astype(np.int16)
    return a.astype(np.float32) / 32768.0


_NB = r"(?:nabu|naboo|nah?\W*boo|nah?\W*bu|nab\W*boo|gnaboo|knaboo|nabo|navu)"
_STOP_ANY = re.compile(r"[\s,;:\-]*\b" + _NB + r"\b[\s,.!?;:\-]*(?:end|stop)\s+(?:the\s+)?recording\b\W*", re.I)
_CMD_ANY = re.compile(r"(?:^|(?<=[\s.,!?;:]))(?:hey\s+)?" + _NB + r"\W+(?:record|edit|cut)\s+(?:this|that)\b\W*", re.I)
_WAKE_HEAD = re.compile(r"^\W*(?:(?:hey\s+)?" + _NB + r"\W+)?(?:record|edit|cut)\s+(?:this|that)\b\W*", re.I)


def _clean_paragraphs(paras):
    """Safety net: drop the spoken commands wherever they slipped into the audio."""
    out = []
    for i, p in enumerate(paras or []):
        p = _STOP_ANY.sub(" ", p)
        p = _CMD_ANY.sub(" ", p)
        if i == 0:
            p = _WAKE_HEAD.sub("", p)
        p = re.sub(r"\s{2,}", " ", p).strip()
        if p and re.search(r"\w", p):
            out.append(p[0].upper() + p[1:] if i == 0 else p)
    return out


class Transcriber:
    """Background worker. on_event(name, **kw) is called from its thread.

    Jobs: normal recordings (-> note), "edit" dictation (-> cursor), "cut" passages
    (-> search & delete), and dictionary "sample" clips (-> learn how a word is heard)."""

    def __init__(self, cfg, on_event):
        self.cfg = cfg
        self.on_event = on_event
        self.q = queue.Queue()
        self.model = None
        self.model_name = None
        self.last_used = time.time()
        self.busy = False
        self.thread = threading.Thread(target=self._run, name="nabu-transcriber", daemon=True)
        self.thread.start()

    def submit(self, wav_path, started=None, **extra):
        self.q.put((wav_path, started, extra))
        self.on_event("queued", path=wav_path, pending=self.q.qsize() + (1 if self.busy else 0), **extra)

    def submit_sample(self, wav_path, word, tag=None):
        self.q.put((wav_path, None, {"mode": "sample", "word": word, "tag": tag}))

    def pending(self):
        return self.q.qsize() + (1 if self.busy else 0)

    def shutdown(self):
        self.q.put(None)

    def _ensure_model(self):
        name = self.cfg["transcribe_model"]
        if self.model is None or self.model_name != name:
            self.model = None
            gc.collect()
            self.on_event("loading_model", name=name)
            self.model = _load_model(name, self.cfg.threads())
            self.model_name = name

    def _run(self):
        while True:
            try:
                job = self.q.get(timeout=30)
            except queue.Empty:
                mins = float(self.cfg["unload_model_minutes"])
                if self.model is not None and time.time() - self.last_used > mins * 60:
                    self.model = None
                    gc.collect()
                    log.info("transcription model unloaded (idle)")
                continue
            if job is None:
                return
            wav_path, started, extra = job
            self.busy = True
            try:
                if extra.get("mode") == "sample":
                    self._sample(wav_path, extra)
                else:
                    self._do(wav_path, started, extra)
            except Exception as e:
                log.exception("transcription failed")
                self.on_event("failed", path=wav_path, message=str(e), **extra)
            finally:
                self.busy = False
                self.last_used = time.time()

    def _prompt(self, entries):
        return (nabu_dictionary.prompt_words(entries)[:600] or None) if entries else None

    def _sample(self, wav_path, extra):
        """Transcribe a pronunciation sample with and without the hint, report what was heard."""
        self._ensure_model()
        audio = level(load_audio(wav_path))
        heard = []
        for prompt in (None, extra["word"]):
            kw = dict(language="en", beam_size=5, temperature=0.0, condition_on_previous_text=False,
                      vad_filter=False, without_timestamps=True)
            if prompt:
                kw["initial_prompt"] = prompt
            segs, _ = self.model.transcribe(audio, **kw)
            txt = " ".join(x.text.strip() for x in segs).strip()
            if txt and txt not in heard:
                heard.append(txt)
        self.on_event("sample_done", path=wav_path, heard=heard, **extra)

    def _do(self, wav_path, started, extra):
        mode = extra.get("mode", "record")
        self._ensure_model()
        audio = level(load_audio(wav_path))
        duration = len(audio) / 16000.0
        entries = nabu_dictionary.load()
        kw = dict(DECODE)
        prompt = self._prompt(entries)
        if prompt:
            kw["hotwords"] = prompt          # applies to the whole recording, not just its start
        segments, _info = self.model.transcribe(audio, **kw)
        gap = float(self.cfg["paragraph_gap_seconds"])
        paras, cur, last_end = [], [], None
        for seg in segments:
            t = seg.text.strip()
            if not t:
                continue
            if last_end is not None and seg.start - last_end >= gap and cur and mode != "cut":
                paras.append(" ".join(cur))
                cur = []
            cur.append(t)
            last_end = seg.end
            if duration > 0:
                self.on_event("progress", path=wav_path, fraction=min(1.0, seg.end / duration), mode=mode)
        if cur:
            paras.append(" ".join(cur))
        paras = _clean_paragraphs(paras)
        paras = [nabu_dictionary.apply(p, entries) for p in paras]
        if mode != "cut":
            try:
                with open(os.path.splitext(wav_path)[0] + ".txt", "w", encoding="utf-8") as f:
                    f.write("\n\n".join(paras) + "\n")
            except OSError:
                log.exception("could not write transcript text file")
        else:
            try:
                os.remove(wav_path)
            except OSError:
                pass
        self.on_event("done", path=wav_path, paragraphs=paras, started=started, seconds=duration, **extra)
