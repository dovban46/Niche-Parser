"""Контроль якості відео без перегляду «на око»: (1) контактні аркуші — кадр на кожну секунду з таймкодом (для візуального
огляду); (2) автоматичні перевірки геометрії: текст не перекриває героїв/предмети, герої стоять на ґрунті, ритм і камера.
    python -m app.explainer.qa <slug> --auto            # звіт у storage/explainer_jobs/<slug>/qa_report.txt
    python -m app.explainer.qa <slug> --sheets [--every 1.0] [--from 0 --to 120]"""
import argparse
import math
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .produce import _wd
from .render import FPS, H, W

NL = chr(10)


def sheets(video: Path, out_dir: Path, every: float = 1.0, t_from: float = 0.0, t_to: float | None = None,
           cols: int = 4, rows: int = 3, size=(426, 240)) -> list[Path]:
    """Кадри кожні `every` с → аркуші cols×rows із таймкодами. Повертає шляхи аркушів."""
    out_dir.mkdir(parents=True, exist_ok=True)
    tmp = out_dir / "_frames"
    tmp.mkdir(exist_ok=True)
    for f in tmp.glob("*.jpg"):
        f.unlink()
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(video)],
                               capture_output=True, text=True).stdout.strip())
    t_to = min(t_to or dur, dur)
    args = ["ffmpeg", "-y", "-loglevel", "error", "-ss", str(t_from), "-t", str(t_to - t_from), "-i", str(video),
            "-vf", f"fps=1/{every},scale={size[0]}:{size[1]}", "-q:v", "4", str(tmp / "f_%05d.jpg")]
    subprocess.run(args, check=True)
    frames = sorted(tmp.glob("f_*.jpg"))
    font = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 16)
    per = cols * rows
    paths = []
    for si in range(0, len(frames), per):
        sheet = Image.new("RGB", (size[0] * cols, size[1] * rows))
        for j, fp in enumerate(frames[si: si + per]):
            im = Image.open(fp)
            t = t_from + (si + j) * every
            d = ImageDraw.Draw(im)
            label = f"{int(t // 60)}:{int(t % 60):02d}"
            d.rectangle((0, 0, 52, 20), fill=(0, 0, 0))
            d.text((4, 2), label, font=font, fill=(255, 255, 0))
            sheet.paste(im, ((j % cols) * size[0], (j // cols) * size[1]))
        p = out_dir / f"sheet_{int(t_from + si * every):05d}.png"
        sheet.save(p)
        paths.append(p)
    for f in frames:
        f.unlink()
    return paths


def _overlap(a, b, shrink=0.08) -> float:
    mx, my = (b[2] - b[0]) * shrink, (b[3] - b[1]) * shrink * 0.75
    iw = min(a[2], b[2] - mx) - max(a[0], b[0] + mx)
    ih = min(a[3], b[3] - my) - max(a[1], b[1] + my)
    return iw * ih if iw > 0 and ih > 0 else 0.0


def auto_checks(folder: Path, step_s: float = 0.5) -> str:
    from .storyboard import load_timeline
    tl = load_timeline(folder)
    beats = tl.beats
    rep: list[str] = []
    n = len(beats)
    sage = sum(1 for b in beats if b.get("who") == "sage")
    runs, mx, cur = 0, 1, 1
    for i in range(1, n):
        if beats[i]["bg"] == beats[i - 1]["bg"]:
            cur += 1
            mx = max(mx, cur)
        else:
            cur = 1
            runs += 1
    rep.append(f"бітів {n}; шотів {len(tl.shots)} (≈{len(tl.shots) / (tl.total / 60):.0f}/хв, середній {tl.total / len(tl.shots):.2f} с)")
    rep.append(f"мудрець {sage} ({100 * sage / n:.0f}%); унікальних фонів {len({b['bg'] for b in beats})}; змін фону {runs}; найдовша серія одного фону {mx} бітів")
    rep.append(f"big-текстів {sum(1 for b in beats if b.get('big'))}; бітів із предметами {sum(1 for b in beats if b.get('props'))}")
    rep.append(f"корекції розкладки (ґрунт/предмети): {len(tl.layout_log)}")
    rep += ["  - " + x for x in tl.layout_log[:25]]

    big_bad, sub_bad = [], []
    f = 0
    total_frames = int(tl.total * FPS)
    while f < total_frames:
        t = f / FPS
        tl.frame(f)
        qa = tl.qa
        if qa["big"]:
            ov = qa["big"][4]
            if ov > 600:
                big_bad.append((t, round(ov)))
        if qa["sub"]:
            sb_ov = sum(_overlap(qa["sub"], r) for r in qa["rects"])
            if sb_ov > 400:
                sub_bad.append((t, round(sb_ov)))
        f += int(step_s * FPS)
    rep.append(f"великий текст перекриває героя/предмет: {len(big_bad)} моментів " + ", ".join(f"{int(t // 60)}:{int(t % 60):02d}" for t, _ in big_bad[:20]))
    rep.append(f"субтитри перекривають героя/предмет: {len(sub_bad)} моментів " + ", ".join(f"{int(t // 60)}:{int(t % 60):02d}" for t, _ in sub_bad[:20]))

    # камера: стрибки масштабу всередині серії
    jumps = 0
    prev = None
    for fi in range(0, total_frames, 2):
        t = fi / FPS
        idx, sh = tl.shot_at(t)
        z = tl._cam_params(sh[0], t)[0]
        if prev and prev[1] == tl.run_id[sh[0]] and abs(z - prev[0]) > 0.006:
            jumps += 1
        prev = (z, tl.run_id[sh[0]])
    rep.append(f"різких змін масштабу камери всередині серії: {jumps}")
    text = NL.join(rep)
    (folder / "qa_report.txt").write_text(text, encoding="utf-8")
    return text


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("slug")
    ap.add_argument("--auto", action="store_true")
    ap.add_argument("--sheets", action="store_true")
    ap.add_argument("--every", type=float, default=1.0)
    ap.add_argument("--from", dest="t_from", type=float, default=0.0)
    ap.add_argument("--to", dest="t_to", type=float, default=None)
    ap.add_argument("--video", default="video.mp4")
    a = ap.parse_args()
    wd = _wd(a.slug)
    if a.auto:
        print(auto_checks(wd))
    if a.sheets:
        ps = sheets(wd / a.video, wd / "qa_sheets", a.every, a.t_from, a.t_to)
        print(len(ps), "аркушів у", wd / "qa_sheets")


if __name__ == "__main__":
    main()
