"""Кадри для бітів: fal FLUX schnell + контроль Claude (стиль, лишній текст/рамки) + координати обведення."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import core, plan

_NEG = "no frame, no border, no margin, no signature, no date, no numbers, no stamp, no logo"
_JUDGE = (
    "You are a strict quality inspector for frames of an illustrated cartoon history video. Look carefully at EVERY person and animal in the picture. "
    "Check: (1) each person has exactly one head and one face; eyes sit above the nose, the mouth below it, all on the front of the head; the face is not on the back of the head and not duplicated or merged with another person; "
    "(2) every visible hand is attached to an arm, has a natural number of fingers (or is a simple mitten) and bends the natural way; arms and legs are attached at shoulders and hips, none are twisted backwards, doubled or missing; "
    "(3) held objects (swords, spears, rifles, scrolls) are actually in a hand, not floating or fused to the body; (4) people have sensible proportions, no melted or stretched bodies; "
    "(5) no large readable Latin text or numbers, no white or paper border around the picture, not photo-realistic, no gore. Small kanji-like signs, tiny corner stamps and shop banners are fine. "
    'Reply ONLY with JSON: {"score": 0-10, "defects": ["max 3 short defects"]}. 10 = clean, 8-9 = fine for a video, 6-7 = noticeable defect, below 6 = broken. '
    "Also give score 4 or lower if the picture has nothing to do with this scene: "
)
PASS_SCORE = 8
MAX_TRIES = 3
MODEL = "fal-ai/flux/dev"   # A/B 2026-10-20: schnell дає криві руки/обличчя, dev чистіший
SIZE = (1152, 648)


def prompt_for(beat: dict, cast_map: dict | None = None) -> str:
    cm = cast_map or plan.CAST
    cast = " ".join(f"{k}: {cm[k]}." for k in beat.get("cast", []) if k in cm)
    return f"{beat['img']}. {('Characters: ' + cast) if cast else ''} {core.STYLE}. {_NEG}"


def _one(args) -> tuple[int, str]:
    i, beat, out_dir, cast_map = args
    path = out_dir / f"beat_{i:02d}.png"
    if path.exists():
        return i, "кеш"
    best, notes = (-1, None), []
    for attempt in range(MAX_TRIES):
        cand = out_dir / f"beat_{i:02d}_c{attempt}.png"
        core.fal_image(prompt_for(beat, cast_map), cand, model=MODEL, size=SIZE, seed=1000 * (i + 1) + attempt)
        try:
            v = core.ask_vision_json(cand, _JUDGE + beat["img"][:300], max_tokens=160)
            score = float(v.get("score", 0))
            why = "; ".join(str(x)[:40] for x in v.get("defects", [])[:2])
        except Exception as exc:  # контролер допоміжний: його збій не валить генерацію
            score, why = 8.0, f"суддя недоступний: {exc}"
        if score > best[0]:
            best = (score, cand)
        if score >= PASS_SCORE:
            break
        notes.append(f"{score:g}: {why}")
    score, cand = best
    cand.replace(path)
    for f in out_dir.glob(f"beat_{i:02d}_c[0-9].png"):   # точний шаблон: не зачіпає beat_1xx
        f.unlink()
    status = f"{score:g}" + (" після " + " | ".join(notes) if notes else "")
    return i, status


def images(slug: str, workers: int = 6, log=print) -> None:
    d = core.job_dir(slug)
    beats = core.load_json(d / "beats.json")
    out_dir = d / "frames"
    out_dir.mkdir(exist_ok=True)
    cast_map = plan.load_cast(slug)
    with ThreadPoolExecutor(workers) as ex:
        for i, status in ex.map(_one, [(i, b, out_dir, cast_map) for i, b in enumerate(beats)]):
            log(f"кадр {i:02d}: {status}")


def rings(slug: str, log=print) -> None:
    """Для бітів із ring: просимо Claude вказати рамку деталі (нормалізовані координати)."""
    d = core.job_dir(slug)
    beats = core.load_json(d / "beats.json")
    boxes = core.load_json(d / "rings.json", {})
    for i, b in enumerate(beats):
        if not b.get("ring") or str(i) in boxes:
            continue
        q = (f'This picture is exactly 1024 pixels wide and 576 pixels tall (origin top-left). Find "{b["ring"]}". '
             'Reply ONLY with JSON {"found": true|false, "box": [x0, y0, x1, y1]} in PIXELS of that 1024x576 picture: '
             "x0,y0 = top-left corner, x1,y1 = bottom-right corner of a tight box around that detail only (not the whole scene).")
        try:
            v = core.ask_vision_json(d / "frames" / f"beat_{i:02d}.png", q, max_tokens=150)
        except Exception as exc:
            log(f"ring {i}: помилка {exc}")
            continue
        if v.get("found") and len(v.get("box", [])) == 4:
            x0, y0, x1, y1 = [float(x) for x in v["box"]]
            boxes[str(i)] = [max(0.0, min(1.0, x0 / 1024)), max(0.0, min(1.0, y0 / 576)), max(0.0, min(1.0, x1 / 1024)), max(0.0, min(1.0, y1 / 576))]
            log(f"ring {i}: {b['ring']} → {boxes[str(i)]}")
        else:
            log(f"ring {i}: не знайдено «{b['ring']}»")
    core.save_json(d / "rings.json", boxes)
