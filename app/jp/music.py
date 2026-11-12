"""Безкоштовна «японська» музична підкладка без авторських прав: щипкові ноти у пентатоніці Хірадзьоші (на кшталт кото),
низький дрон і рідкісні удари тайко. Генерується кодом (numpy), без зовнішніх семплів."""

import wave
from pathlib import Path

import numpy as np

SR = 44100
# Hirajoshi від D: D E F A Bb (півтони 0,2,3,7,8) у кількох октавах
_SCALE = [0, 2, 3, 7, 8]
_D3 = 146.83


def _note_freqs() -> list[float]:
    out = []
    for octv in range(0, 3):
        for s in _SCALE:
            out.append(_D3 * 2 ** ((s + 12 * octv) / 12))
    return out


def _pluck(freq: float, dur: float, rng: np.random.Generator, amp: float) -> np.ndarray:
    n = int(SR * dur)
    t = np.arange(n) / SR
    bend = 1 + 0.028 * np.exp(-t / 0.035)            # «осі» кото: нота трохи згинається вниз на атаці
    phase = 2 * np.pi * np.cumsum(freq * bend) / SR
    sig = np.zeros(n)
    for h, (a, tau) in enumerate([(1.0, 0.9), (0.55, 0.55), (0.33, 0.35), (0.2, 0.22), (0.12, 0.15)], start=1):
        sig += a * np.sin(h * phase * (1 + 0.0007 * h * h)) * np.exp(-t / tau)
    click = rng.standard_normal(n) * np.exp(-t / 0.004) * 0.35   # удар медіатора
    sig = (sig + click) * np.minimum(t / 0.002, 1.0)
    return amp * sig / 2.2


def _taiko(dur: float = 1.6, amp: float = 0.9) -> np.ndarray:
    n = int(SR * dur)
    t = np.arange(n) / SR
    f = 42 + 60 * np.exp(-t / 0.06)
    body = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.35)
    skin = np.random.default_rng(3).standard_normal(n) * np.exp(-t / 0.02) * 0.25
    return amp * (body + skin)


def make(path: Path, total_s: float, hits_s: list[float] | None = None, seed: int = 7, bpm: float = 78) -> Path:
    rng = np.random.default_rng(seed)
    n = int(SR * (total_s + 1.0))
    out = np.zeros(n)
    freqs = _note_freqs()
    step = 60.0 / bpm / 2            # восьма
    idx = 5
    t = 0.0
    while t < total_s:
        density = 0.52 + 0.18 * np.sin(2 * np.pi * t / 70.0 + seed)   # хвилі щільності з періодом ~70 с
        if rng.random() < density:
            idx = int(np.clip(idx + rng.choice([-2, -1, -1, 0, 1, 1, 2, 3]), 0, len(freqs) - 1))
            note = _pluck(freqs[idx], 2.4, rng, amp=0.55 + 0.25 * rng.random())
            i0 = int(t * SR)
            seg = note[: max(min(len(note), n - i0), 0)]
            out[i0:i0 + len(seg)] += seg
        t += step * (1 if rng.random() < 0.8 else 2)
    tt = np.arange(n) / SR
    drone = 0.10 * np.sin(2 * np.pi * 73.42 * tt) + 0.06 * np.sin(2 * np.pi * 110.0 * tt + 0.7)
    drone *= 0.75 + 0.25 * np.sin(2 * np.pi * 0.11 * tt)
    out += drone
    for h in (hits_s or []):
        hit = _taiko()
        i0 = int(h * SR)
        seg = hit[: max(min(len(hit), n - i0), 0)]
        out[i0:i0 + len(seg)] += seg
    # легка «кімната»: два відлуння
    for delay, g in ((0.19, 0.28), (0.37, 0.16)):
        d = int(delay * SR)
        out[d:] += out[:-d] * g
    out *= np.minimum(tt / 0.6, 1.0) * np.minimum(np.maximum(total_s + 1.0 - tt, 0) / 1.6, 1.0)
    out = out / max(np.abs(out).max(), 1e-6) * 0.8
    stereo = np.stack([out, np.roll(out, 90)], axis=1)       # ~2 мс різниці каналів: легка ширина
    data = (np.clip(stereo, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes(data.tobytes())
    return path
