"""Фонова музика без ризику авторських претензій (Content ID).

Джерела за пріоритетом:
1) файли, які користувач сам поклав у storage/music_library/ (напр. з YouTube Audio Library — найбезпечніше);
2) власний процедурний ембієнт: ми синтезуємо його самі (numpy) — це оригінальний звук без жодного правовласника,
   тож Content ID йому нічого "впізнати". Генерується один раз і кешується в тій самій теці (_gen_*.wav).
Музика кладеться дуже тихо (MUSIC_LUFS нижче за голос) і ще притискається sidechain-ducking'ом під диктором
(audio_mix) — слів не перебиває. Чесне обмеження: я не можу її прослухати, лише виміряти; якість на слух
оцінює користувач."""

import subprocess
import wave
from pathlib import Path

import numpy as np

from .config import MUSIC_LUFS, STORAGE_ROOT
from .ffutil import error_tail, probe_duration, run_ffmpeg

SR = 44100
MUSIC_DIR = STORAGE_ROOT / "music_library"
_AUDIO_EXT = {".mp3", ".wav", ".m4a", ".ogg", ".flac"}
_TRACK_SECONDS = 150
_CROSSFADE_S = 6

_CHORDS = {
    "Dm": [50, 57, 62, 65], "Bb": [46, 53, 58, 62], "Gm": [43, 55, 58, 62], "Csus": [48, 55, 60, 65],
    "Am": [45, 57, 60, 64], "Eb": [51, 58, 63, 67], "A": [45, 52, 57, 61], "F": [53, 57, 60, 65],
}
_PROGRESSIONS = [
    ["Dm", "Bb", "Gm", "A", "Dm", "Eb", "Dm", "A"],
    ["Dm", "F", "Csus", "Am", "Bb", "Gm", "A", "Dm"],
    ["Dm", "Eb", "Dm", "Gm", "Bb", "Csus", "A", "Dm"],
]
_BELL_NOTES = [587.33, 698.46, 783.99, 880.0, 1174.66, 1396.91]  # D-мінорна пентатоніка, високий регістр


def _freq(midi: int) -> float:
    return 440.0 * 2 ** ((midi - 69) / 12)


def _pad(freqs: list[float], n: int, rng: np.random.Generator) -> np.ndarray:
    """Теплий падаючий акорд: по 2 розстроєні "пили" на ноту (суми гармонік), повільне вібрато."""
    t = np.arange(n) / SR
    vib = 1 + 0.0018 * np.sin(2 * np.pi * 0.23 * t + rng.uniform(0, 6.28))
    out = np.zeros(n, dtype=np.float32)
    for f in freqs:
        for cents in (-6.0, 5.0):
            phase = 2 * np.pi * np.cumsum(f * 2 ** (cents / 1200) * vib) / SR
            for h in range(1, 7):
                arg = np.mod(h * phase + rng.uniform(0, 6.28), 2 * np.pi).astype(np.float32)
                out += np.sin(arg) / h ** 1.4
    return out / (len(freqs) * 2)


def _bell(freq: float) -> np.ndarray:
    t = np.arange(int(7.0 * SR)) / SR
    mod = 3.5 * np.sin(2 * np.pi * freq * 3.5 * t) * np.exp(-t / 0.9)
    env = np.minimum(t / 0.006, 1.0) * np.exp(-t / 1.9)
    return (np.sin(2 * np.pi * freq * t + mod) * env).astype(np.float32)


def _lowpass(x: np.ndarray, cutoff: float) -> np.ndarray:
    spec = np.fft.rfft(x)
    freqs = np.fft.rfftfreq(len(x), 1 / SR)
    return np.fft.irfft(spec / (1 + (freqs / cutoff) ** 4), len(x)).astype(np.float32)


def _reverb(x: np.ndarray, rng: np.random.Generator, seconds: float = 3.8) -> np.ndarray:
    n_ir = int(seconds * SR)
    ir = rng.standard_normal(n_ir) * np.exp(-np.arange(n_ir) / (0.75 * SR))
    ir = _lowpass(ir.astype(np.float32), 3200)
    ir /= np.sqrt(np.sum(ir ** 2)) + 1e-9
    n = len(x) + n_ir - 1
    size = 1 << (n - 1).bit_length()
    y = np.fft.irfft(np.fft.rfft(x, size) * np.fft.rfft(ir, size), size)[:len(x)]
    return y.astype(np.float32)


def generate_ambient(seed: int, out_path: Path, seconds: int = _TRACK_SECONDS) -> Path:
    """Оригінальний темний ембієнт (D-дорійський/фрігійський колорит): дрон, повільні акорди, рідкісні дзвони, реверб."""
    rng = np.random.default_rng(seed)
    n = seconds * SR
    prog = _PROGRESSIONS[seed % len(_PROGRESSIONS)]
    seg = n // len(prog)
    ov = 5 * SR
    mix = np.zeros(n, dtype=np.float32)
    for i, name in enumerate(prog):
        start = i * seg - ov
        length = seg + 2 * ov
        chord = _pad([_freq(m) for m in _CHORDS[name]], length, rng)
        win = np.ones(length, dtype=np.float32)
        ramp = np.sin(np.linspace(0, np.pi / 2, ov, dtype=np.float32)) ** 2
        win[:ov], win[-ov:] = ramp, ramp[::-1]
        a, b = max(0, start), min(n, start + length)
        mix[a:b] += (chord * win)[a - start:b - start]
    mix = _lowpass(mix, 2200)

    t = np.arange(n) / SR
    drone = (0.55 * np.sin(2 * np.pi * 36.71 * t) + 0.30 * np.sin(2 * np.pi * 73.42 * t + 1.1)) * (
        0.8 + 0.2 * np.sin(2 * np.pi * 0.05 * t))
    dry = 0.55 * mix + 0.20 * drone.astype(np.float32)

    bells_l = np.zeros(n, dtype=np.float32)
    bells_r = np.zeros(n, dtype=np.float32)
    pos = int(rng.uniform(8, 14) * SR)
    while pos < n - 8 * SR:
        bell = _bell(float(rng.choice(_BELL_NOTES))) * rng.uniform(0.05, 0.10)
        pan = rng.uniform(0.2, 0.8)
        bells_l[pos:pos + len(bell)] += bell * (1 - pan)
        bells_r[pos:pos + len(bell)] += bell * pan
        pos += int(rng.uniform(9, 22) * SR)

    left = dry + bells_l
    right = dry + bells_r
    left = 0.6 * left + 0.6 * _reverb(left, rng)
    right = 0.6 * right + 0.6 * _reverb(right, rng)
    stereo = np.stack([left, right], axis=1)
    fade = np.minimum(np.minimum(np.arange(n) / (6 * SR), (n - np.arange(n)) / (6 * SR)), 1.0).astype(np.float32)
    stereo *= fade[:, None]
    stereo *= 0.6 / (np.max(np.abs(stereo)) + 1e-9)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out_path), "wb") as wav:
        wav.setnchannels(2)
        wav.setsampwidth(2)
        wav.setframerate(SR)
        wav.writeframes((stereo * 32767).astype(np.int16).tobytes())
    return out_path


def _tracks(job_id: int) -> list[Path]:
    own = sorted(p for p in MUSIC_DIR.glob("*") if p.suffix.lower() in _AUDIO_EXT and not p.name.startswith("_gen_"))
    tracks = own or [
        (MUSIC_DIR / f"_gen_ambient_{seed}.wav") if (MUSIC_DIR / f"_gen_ambient_{seed}.wav").exists()
        else generate_ambient(seed, MUSIC_DIR / f"_gen_ambient_{seed}.wav")
        for seed in (1, 2, 3)
    ]
    k = job_id % len(tracks)
    return tracks[k:] + tracks[:k]  # різні відео починаються з різної композиції


def build_bed(job_id: int, total_s: float, out_path: Path) -> Path | None:
    """Склеює треки кросфейдом до потрібної довжини, вирівнює до MUSIC_LUFS (дуже тихо відносно голосу) і дає
    плавний вхід/вихід. None — якщо музику зібрати не вдалось (відео тоді збирається без неї)."""
    MUSIC_DIR.mkdir(parents=True, exist_ok=True)
    tracks = _tracks(job_id)
    chain: list[Path] = []
    covered, i = 0.0, 0
    while covered < total_s + _CROSSFADE_S and len(chain) < 24:
        track = tracks[i % len(tracks)]
        length = probe_duration(track) or _TRACK_SECONDS
        chain.append(track)
        covered += length - (_CROSSFADE_S if chain[1:] else 0)
        i += 1

    fmt = "aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo"
    args: list[str] = []
    for p in chain:
        args += ["-i", str(p)]
    parts = [f"[{k}:a]{fmt}[m{k}]" for k in range(len(chain))]
    last = "m0"
    for k in range(1, len(chain)):
        parts.append(f"[{last}][m{k}]acrossfade=d={_CROSSFADE_S}:c1=tri:c2=tri[x{k}]")
        last = f"x{k}"
    parts.append(
        f"[{last}]loudnorm=I={MUSIC_LUFS:g}:TP=-3:LRA=7,atrim=0:{total_s:.3f},asetpts=PTS-STARTPTS[bed]"
    )
    try:
        run_ffmpeg([*args, "-filter_complex", ";".join(parts), "-map", "[bed]", "-c:a", "aac", "-b:a", "160k", str(out_path)])
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"ffmpeg (музичне ложе): {error_tail(exc)}") from exc
    return out_path


def generate_pulse(seed: int, out_path: Path, seconds: int = 75, bpm: int = 104, root_hz=(55.0, 55.0, 65.41, 49.0), pad_hz=(110.0, 130.81, 164.81, 220.0)) -> Path:
    """Ритмічне темне «пульсуюче» ложе для Shorts (синтез numpy, без правовласників): м'який kick на кожну долю, глухий бас, тихий хет,
    повільний мінорний падб. Орієнтир темпу — напруга/таємниця; гучність далі доводить loudnorm і ducking під голосом."""
    rng = np.random.default_rng(seed)
    n = seconds * SR
    beat = 60.0 / bpm
    out = np.zeros(n, dtype=np.float32)
    t_k = np.arange(int(0.34 * SR)) / SR
    kick = (np.sin(2 * np.pi * (46 * t_k + 70 * (1 - np.exp(-t_k * 38)) / 38 * 0 + 74 * np.exp(-t_k * 26) / 26 * 26 * 0)) * 0).astype(np.float32)
    freq = 46 + 84 * np.exp(-t_k * 24)
    phase = 2 * np.pi * np.cumsum(freq) / SR
    kick = (np.sin(phase) * np.exp(-t_k * 9.5)).astype(np.float32)
    t_h = np.arange(int(0.06 * SR)) / SR
    hat = (rng.standard_normal(len(t_h)) * np.exp(-t_h * 70)).astype(np.float32)
    hat = hat - np.convolve(hat, np.ones(6) / 6, mode="same")        # грубий high-pass
    roots = [33, 33, 36, 31]                                          # A1, A1, C2, G1 (MIDI-ish -> Hz нижче)
    bars = int(seconds / (beat * 4)) + 1
    for k in range(int(seconds / beat)):
        pos = int(k * beat * SR)
        if pos + len(kick) < n:
            out[pos:pos + len(kick)] += 0.85 * kick * (1.0 if k % 4 == 0 else 0.7)
        hp = int((k + 0.5) * beat * SR)
        if hp + len(hat) < n:
            out[hp:hp + len(hat)] += 0.12 * hat
    for b in range(bars):
        f = root_hz[b % 4]
        a = int(b * beat * 4 * SR)
        z = min(n, a + int(beat * 4 * SR))
        if z <= a:
            break
        tt = np.arange(z - a) / SR
        env = np.minimum(tt / 0.05, 1.0) * np.exp(-tt * 0.55)
        out[a:z] += (0.38 * np.sin(2 * np.pi * f * tt) + 0.14 * np.sin(2 * np.pi * 2 * f * tt)).astype(np.float32) * env.astype(np.float32)
    # падб: A-мінорний тріад, дуже тихо
    tt = np.arange(n) / SR
    pad = sum(np.sin(2 * np.pi * fr * tt + rng.uniform(0, 6.28)) for fr in pad_hz) / 4
    pad *= (0.5 + 0.5 * np.sin(2 * np.pi * tt / (beat * 8))) * 0.10
    out += _lowpass(pad.astype(np.float32), 1800)
    fade = np.minimum(np.minimum(np.arange(n) / (0.2 * SR), (n - np.arange(n)) / (2 * SR)), 1.0).astype(np.float32)
    out *= fade
    out *= 0.7 / (np.max(np.abs(out)) + 1e-9)
    stereo = np.stack([out, out], axis=1)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out_path), "wb") as wav:
        wav.setnchannels(2)
        wav.setsampwidth(2)
        wav.setframerate(SR)
        wav.writeframes((stereo * 32767).astype(np.int16).tobytes())
    return out_path


def build_short_bed(total_s: float, out_path: Path, lufs: float = -27.0, variant: int = 1) -> Path | None:
    """Ложе для Shorts: ритмічний пульс, одразу з 0-ї секунди (без довгого fade-in), loudnorm до lufs."""
    src = MUSIC_DIR / f"_gen_pulse_{variant}.wav"
    if not src.exists():
        if variant == 2:   # «темна балада»: D-мінор, повільніше, глибший бас
            generate_pulse(2, src, bpm=88, root_hz=(36.71, 36.71, 43.65, 32.70), pad_hz=(73.42, 87.31, 110.0, 146.83))
        else:
            generate_pulse(1, src)
    try:
        run_ffmpeg(["-stream_loop", "-1", "-i", str(src), "-af",
                    f"atrim=0:{total_s:.3f},asetpts=PTS-STARTPTS,loudnorm=I={lufs:g}:TP=-3:LRA=7,afade=t=in:d=0.15,afade=t=out:st={max(total_s - 1.5, 0):.3f}:d=1.5",
                    "-c:a", "aac", "-b:a", "160k", str(out_path)])
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"ffmpeg (ложе Shorts): {error_tail(exc)}") from exc
    return out_path
