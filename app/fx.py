"""Процедурні накладки для монтажу — рахуються локально (numpy), нічого не коштують і не мають авторських
прав: це наш власний згенерований шар. Довші статичні плани (бюджетне рішення 2026-10-03: кадр показується ~6с)
"оживляє" пил у променях світла, що повільно пливе поверх усього відео."""

import subprocess
from pathlib import Path

import numpy as np

W, H, FPS = 1280, 720, 24
LOOP_SECONDS = 24  # ціле число циклів синусоїд за період → шов петлі непомітний


def _sprite(radius: float) -> np.ndarray:
    size = int(radius * 6) | 1
    ax = np.arange(size) - size // 2
    xx, yy = np.meshgrid(ax, ax)
    sigma = max(radius / 1.5, 0.8)
    return np.exp(-(xx ** 2 + yy ** 2) / (2 * sigma ** 2)).astype(np.float32)


def ensure_dust_loop(path: Path) -> Path:
    """Чорне тло з теплими частинками-пилинками, що плавають; поверх відео накладається режимом screen."""
    if path.exists() and path.stat().st_size > 10_000:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(11)
    n = 95
    motes = []
    for _ in range(n):
        depth = rng.random()  # 0 — далека дрібна пилинка, 1 — близька велика розмита
        motes.append({
            "x0": rng.uniform(0, W), "y0": rng.uniform(0, H),
            "ax": rng.uniform(25, 130) * (0.5 + depth), "ay": rng.uniform(18, 90) * (0.5 + depth),
            "kx": int(rng.integers(1, 3)), "ky": int(rng.integers(1, 3)),
            "px": rng.uniform(0, 2 * np.pi), "py": rng.uniform(0, 2 * np.pi),
            "alpha": rng.uniform(0.25, 0.85) * (1.0 - 0.35 * depth),
            "tw": int(rng.integers(1, 4)), "pt": rng.uniform(0, 2 * np.pi),
            "sprite": _sprite(1.3 + 4.2 * depth ** 1.6),
        })
    warm = np.array([1.0, 0.93, 0.80], dtype=np.float32)

    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
           "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", str(path)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    total = LOOP_SECONDS * FPS
    try:
        for f in range(total):
            t = f / FPS
            phase = 2 * np.pi * t / LOOP_SECONDS
            canvas = np.zeros((H, W), dtype=np.float32)
            for m in motes:
                x = m["x0"] + m["ax"] * np.sin(m["kx"] * phase + m["px"])
                y = m["y0"] + m["ay"] * np.sin(m["ky"] * phase + m["py"])
                a = m["alpha"] * (0.55 + 0.45 * np.sin(m["tw"] * phase + m["pt"]))
                spr = m["sprite"]
                s = spr.shape[0]
                x0, y0 = int(round(x)) - s // 2, int(round(y)) - s // 2
                sx0, sy0 = max(0, -x0), max(0, -y0)
                ex, ey = min(s, W - x0), min(s, H - y0)
                if ex <= sx0 or ey <= sy0:
                    continue
                canvas[y0 + sy0:y0 + ey, x0 + sx0:x0 + ex] += spr[sy0:ey, sx0:ex] * a
            canvas = np.clip(canvas, 0, 1)
            frame = (canvas[..., None] * warm * 255).astype(np.uint8)
            proc.stdin.write(frame.tobytes())
    finally:
        proc.stdin.close()
        proc.wait()
    if proc.returncode != 0:
        path.unlink(missing_ok=True)
        raise RuntimeError("ffmpeg не зміг зібрати петлю пилу")
    return path
