"""Microphone clean-up and speech detection.

Frontend: gain -> rumble/hum high-pass -> adaptive spectral noise reduction.
  Made for steady noise (PC fans, AC, electrical hum). The noise profile is
  learned continuously from the moments when nobody is speaking.
SpeechDetector: Silero neural voice-activity detector (bundled with
  faster-whisper), behind a cheap energy gate so it only runs when there is sound.
All of it costs well under 1% of one CPU core.
"""
import logging
import os

import numpy as np

log = logging.getLogger("nobu.dsp")

SR = 16000
N_FFT = 512
HOP = 256


class Frontend:
    def __init__(self, gain_db=0.0, noise_reduction=0.6):
        self.win = np.sqrt(np.hanning(N_FFT + 1)[:N_FFT]).astype(np.float32)
        freqs = np.arange(N_FFT // 2 + 1) * SR / N_FFT
        # high-pass: remove hum fundamental and rumble (< ~80 Hz), gentle ramp to 120 Hz
        self.hp = np.clip((freqs - 60.0) / 60.0, 0.0, 1.0).astype(np.float32)
        self.hist = np.zeros(N_FFT - HOP, np.float32)
        self.ola = np.zeros(N_FFT, np.float32)
        self.ola2 = np.zeros(N_FFT, np.float32)     # the "original" sound: gain + hum filter only
        self.inbuf = np.zeros(0, np.float32)
        self.noise = None
        self.g_prev = np.ones(N_FFT // 2 + 1, np.float32)
        self.frames = 0
        self.speech = False          # set by the speech detector (feedback)
        self.raw_level = 0.0
        self.set_params(gain_db, noise_reduction)

    def set_params(self, gain_db, noise_reduction):
        self.gain_db = float(gain_db)
        self.gain = float(10 ** (self.gain_db / 20.0))
        self.strength = float(min(1.0, max(0.0, noise_reduction)))

    def reset_noise(self):
        self.noise = None
        self.frames = 0

    def noise_level_db(self):
        """Rough loudness of the learned background noise (dBFS)."""
        if self.noise is None:
            return -90.0
        p = float(np.sum(self.noise)) / (np.sum(self.win ** 2) * N_FFT / 2)
        return 10 * np.log10(max(p, 1e-12))

    def process2(self, raw_int16):
        """(cleaned, original) - the same stretch of sound with and without noise reduction.
        Detection uses the cleaned sound; recordings keep the original, because the speech model
        recognises words more accurately in natural sound than in noise-reduced sound."""
        x = raw_int16.astype(np.float32) / 32768.0
        if len(x):
            self.raw_level = float(np.sqrt(np.mean(x * x))) * 32768.0
        x = x * self.gain
        self.inbuf = np.concatenate([self.inbuf, x]) if len(self.inbuf) else x
        out, out2 = [], []
        while len(self.inbuf) >= HOP:
            hop, self.inbuf = self.inbuf[:HOP], self.inbuf[HOP:]
            frame = np.concatenate([self.hist, hop])
            self.hist = frame[HOP:]
            a, b = self._frame(frame)
            out.append(a)
            out2.append(b)
        if not out:
            return np.zeros(0, np.int16), np.zeros(0, np.int16)
        y = np.concatenate(out)
        y2 = np.concatenate(out2)
        return (np.clip(y * 32768.0, -32768, 32767).astype(np.int16),
                np.clip(y2 * 32768.0, -32768, 32767).astype(np.int16))

    def _frame(self, frame):
        X = np.fft.rfft(frame * self.win)
        P = (X.real * X.real + X.imag * X.imag).astype(np.float32) + 1e-12
        self.frames += 1
        if self.noise is None:
            self.noise = P.copy()
        elif self.frames < 20:                   # learn quickly at start-up (~0.3 s)
            self.noise = 0.8 * self.noise + 0.2 * P
        else:
            if not self.speech:
                self.noise = 0.95 * self.noise + 0.05 * P
            else:
                # while speaking, only let the estimate creep down (never learn the voice)
                self.noise = np.minimum(self.noise, 0.995 * self.noise + 0.005 * P)
        g = self.hp.copy()
        s = self.strength
        if s > 0:
            over = 1.0 + 2.5 * s
            gmin = 10 ** (-(6.0 + 24.0 * s) / 20.0)
            G = 1.0 - over * self.noise / P
            G = np.clip(G, gmin, 1.0)
            G = np.convolve(G, np.array([0.25, 0.5, 0.25], np.float32), mode="same")
            G = 0.6 * G + 0.4 * self.g_prev        # smoothing -> fewer "watery" artefacts
            G = np.clip(G, gmin, 1.0).astype(np.float32)
            self.g_prev = G
            g = g * G
        y = np.fft.irfft(X * g, n=N_FFT).astype(np.float32) * self.win
        y2 = np.fft.irfft(X * self.hp, n=N_FFT).astype(np.float32) * self.win
        return self._ola(self.ola, y), self._ola(self.ola2, y2)

    @staticmethod
    def _ola(buf, y):
        """Overlap-add one frame into buf (in place) and return the finished hop."""
        buf += y
        out = buf[:HOP].copy()
        buf[:-HOP] = buf[HOP:]
        buf[-HOP:] = 0.0
        return out


def _silero_path():
    try:
        import faster_whisper
        p = os.path.join(os.path.dirname(faster_whisper.__file__), "assets", "silero_vad_v6.onnx")
        if os.path.exists(p):
            return p
        import glob
        c = glob.glob(os.path.join(os.path.dirname(faster_whisper.__file__), "assets", "silero*.onnx"))
        return c[0] if c else None
    except Exception:
        return None


class _Silero:
    CH = 512
    CTX = 64

    def __init__(self, path):
        import onnxruntime
        o = onnxruntime.SessionOptions()
        o.inter_op_num_threads = 1
        o.intra_op_num_threads = 1
        o.enable_cpu_mem_arena = False
        o.log_severity_level = 4
        self.sess = onnxruntime.InferenceSession(path, providers=["CPUExecutionProvider"], sess_options=o)
        self.reset()

    def reset(self):
        self.h = np.zeros((1, 1, 128), np.float32)
        self.c = np.zeros((1, 1, 128), np.float32)
        self.ctx = np.zeros(self.CTX, np.float32)
        self.buf = np.zeros(0, np.float32)

    def push(self, x):
        self.buf = np.concatenate([self.buf, x])
        probs = []
        while len(self.buf) >= self.CH:
            ch, self.buf = self.buf[:self.CH], self.buf[self.CH:]
            inp = np.concatenate([self.ctx, ch])[None, :].astype(np.float32)
            out, self.h, self.c = self.sess.run(None, {"input": inp, "h": self.h, "c": self.c})
            self.ctx = ch[-self.CTX:]
            probs.append(float(np.ravel(out)[0]))
        return probs


class SpeechDetector:
    """push(int16 block of 50 ms) -> True while someone is speaking."""

    def __init__(self, sensitivity=0.5):
        self.set_sensitivity(sensitivity)
        self.speech = False
        self.level = 0.0
        self.prob = 0.0
        self.quiet_blocks = 0
        self.floor = None
        self.model = None
        self.kind = "energy"
        p = _silero_path()
        if p:
            try:
                self.model = _Silero(p)
                self.kind = "neural"
            except Exception:
                log.exception("Silero VAD unavailable, using energy detector")

    def set_sensitivity(self, s):
        self.sensitivity = float(min(1.0, max(0.0, s)))
        self.thr_on = 0.75 - 0.5 * self.sensitivity
        self.thr_off = max(0.1, self.thr_on - 0.2)

    def push(self, blk):
        x = blk.astype(np.float32) / 32768.0
        rms = float(np.sqrt(np.mean(x * x))) * 32768.0 if len(x) else 0.0
        self.level = rms
        if self.floor is None:
            self.floor = max(rms, 5.0)
        if not self.speech:
            a = 0.2 if rms < self.floor else 0.01
            self.floor = max(3.0, self.floor + (rms - self.floor) * a)
        # Energy gate: only wake the neural detector when there is some sound
        gate = max(25.0, self.floor * 1.8) * (1.4 - 0.8 * self.sensitivity)
        if self.model is not None:
            if rms < gate and not self.speech:
                self.quiet_blocks += 1
                if self.quiet_blocks == 20:
                    self.model.reset()
                self.prob = 0.0
            else:
                self.quiet_blocks = 0
                probs = self.model.push(x)
                if probs:
                    self.prob = max(probs)
        else:
            ratio = rms / max(self.floor, 1.0)
            self.prob = float(min(1.0, max(0.0, (ratio - 1.5) / 3.0)))
        if self.speech:
            self.speech = self.prob > self.thr_off
        else:
            self.speech = self.prob > self.thr_on
        return self.speech
