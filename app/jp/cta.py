"""CTA «Like · Comment · Share · SUBSCRIBE» внизу праворуч на t секунді (типово 15 с), ~5,5 с.
Відтворено 2026-11-12 у worktree Japan, бо оригінал жив у video-factory-survival, якого більше немає.
Джерело: <video>_nocta.mp4, якщо він є (повторний запуск не накладає CTA двічі; після перерендеру nocta ВИДАЛИТИ),
інакше сам video.mp4 перейменовується на *_nocta.mp4. Результат пишеться у video.mp4.
python -m app.jp.cta <video.mp4> [t]"""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
SFX = ROOT / "storage" / "sfx_library"
W, H, FPS, DUR = 1280, 720, 30, 5.5
RED = (225, 38, 32)
FONT = "C:/Windows/Fonts/arialbd.ttf"


def _ease_back(p: float, s: float = 1.7) -> float:
    p -= 1
    return p * p * ((s + 1) * p + s) + 1


def _icon(kind: str, size: int = 64) -> Image.Image:
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    if kind == "like":                      # кулак з великим пальцем угору
        d.rectangle((6, 28, 18, 58), fill=RED)
        d.rounded_rectangle((22, 26, 56, 58), 6, fill=RED)
        d.polygon([(24, 28), (34, 6), (42, 8), (40, 28)], fill=RED)
    elif kind == "comment":                 # хмарка-повідомлення
        d.rounded_rectangle((6, 10, 58, 46), 8, fill=RED)
        d.polygon([(16, 44), (30, 44), (14, 58)], fill=RED)
    else:                                   # вигнута стрілка «поділитися»
        d.arc((8, 18, 60, 70), 200, 300, fill=RED, width=10)
        d.polygon([(40, 8), (60, 24), (38, 36)], fill=RED)
    return im


def _frame(t: float) -> Image.Image:
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    f = ImageFont.truetype(FONT, 20)
    fb = ImageFont.truetype(FONT, 26)
    fade = 1.0 if t < DUR - 0.6 else max(0.0, (DUR - t) / 0.6)
    items = [("like", "Like"), ("comment", "Comment"), ("share", "Share")]
    x0, y0 = 770, 66          # угорі праворуч: унизу CTA налазив на субтитри (v23)
    for k, (kind, label) in enumerate(items):
        q = (t - 0.25 * k) / 0.35
        if q <= 0:
            continue
        sc = max(0.01, _ease_back(min(q, 1.0)))
        if kind == "like" and 2.6 < t < 3.0:     # «натискання» лайка
            sc *= 1.25
        ic = _icon(kind).resize((max(1, int(64 * sc)), max(1, int(64 * sc))), Image.LANCZOS)
        cx = x0 + k * 110
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        layer.alpha_composite(ic, (int(cx - ic.width / 2), int(y0 - ic.height / 2)))
        ImageDraw.Draw(layer).text((cx, y0 + 46), label, font=f, fill=RED + (255,), anchor="mm",
                                   stroke_width=2, stroke_fill=(255, 255, 255, 200))
        a = min(1.0, q * 3) * fade
        layer.putalpha(layer.getchannel("A").point(lambda v: int(v * a)))
        im.alpha_composite(layer)
    q = (t - 1.0) / 0.35
    if q > 0:                                   # кнопка SUBSCRIBE з дзвіночком
        sc = max(0.01, _ease_back(min(q, 1.0)))
        bw, bh = int(216 * sc), int(52 * sc)
        btn = Image.new("RGBA", (216, 52), (0, 0, 0, 0))
        bd = ImageDraw.Draw(btn)
        bd.rectangle((0, 0, 215, 51), fill=RED + (255,))
        bd.text((14, 26), "SUBSCRIBE", font=fb, fill=(255, 255, 255, 255), anchor="lm")
        bd.ellipse((186, 16, 202, 34), fill=(255, 255, 255, 255))
        bd.rectangle((184, 30, 204, 34), fill=(255, 255, 255, 255))
        if t > 2.2:                             # «натиснуто»: сіра кнопка
            bd.rectangle((0, 0, 215, 51), fill=(90, 90, 90, 255))
            bd.text((14, 26), "SUBSCRIBED", font=ImageFont.truetype(FONT, 21), fill=(255, 255, 255, 255), anchor="lm")
        btn = btn.resize((max(1, bw), max(1, bh)), Image.LANCZOS)
        a = min(1.0, q * 3) * fade
        btn.putalpha(btn.getchannel("A").point(lambda v: int(v * a)))
        im.alpha_composite(btn, (int(1165 - bw / 2), int(y0 - bh / 2)))
    return im


def apply(video: Path, t: float = 15.0) -> Path:
    video = Path(video)
    nocta = video.with_name(video.stem + "_nocta.mp4")
    if not nocta.exists():
        shutil.move(str(video), str(nocta))
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        for i in range(int(DUR * FPS)):
            _frame(i / FPS).save(td / f"c_{i:04d}.png")
        pops = [(SFX / "x_pop.mp3", t), (SFX / "x_pop.mp3", t + 0.25), (SFX / "x_pop.mp3", t + 0.5), (SFX / "x_click.mp3", t + 2.2)]
        pops = [(p, tt) for p, tt in pops if p.exists()]
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(nocta), "-framerate", str(FPS), "-i", str(td / "c_%04d.png")]
        for p, _ in pops:
            cmd += ["-i", str(p)]
        fc = f"[1:v]setpts=PTS+{t}/TB[c];[0:v][c]overlay=0:0:eof_action=pass[v]"
        if pops:
            mix = "".join(f"[{k + 2}:a]adelay={int(tt * 1000)}|{int(tt * 1000)},volume=0.6[s{k}];" for k, (_, tt) in enumerate(pops))
            fc += ";" + mix + "[0:a]" + "".join(f"[s{k}]" for k in range(len(pops))) + f"amix=inputs={len(pops) + 1}:normalize=0:duration=first[a]"
            cmd += ["-filter_complex", fc, "-map", "[v]", "-map", "[a]"]
        else:
            cmd += ["-filter_complex", fc, "-map", "[v]", "-map", "0:a"]
        cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", str(video)]
        subprocess.run(cmd, check=True)
    return video


if __name__ == "__main__":
    print(apply(Path(sys.argv[1]), float(sys.argv[2]) if len(sys.argv) > 2 else 15.0))
