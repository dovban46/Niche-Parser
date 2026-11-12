"""Автоперевірка персонажів: для кожного актора × пози × фази руху силует має бути ОДНИМ суцільним тілом
(відірвані чоботи/ноги/руки дають 2+ компоненти). Запуск: python -m app.explainer.qa_chars [cast ...]"""
import sys

import cv2
import numpy as np

from . import character as ch
from .casts import CASTS
from .storyboard import actor_kwargs

PHASES = [i * 0.4 for i in range(16)]   # повний цикл ходьби (sin) у 16 кроків
MIN_AREA = 250                          # px² відірваного шматка, що вже вважається багом


def check_actor(spec: "ch.CharacterSpec", poses=None, h: int = 360) -> list[tuple[str, float, int]]:
    bad = []
    for pose in (poses or sorted(ch.POSES)):
        walking = ch.POSES[pose].get("walk", False)
        for ph in (PHASES if walking else PHASES[:3]):
            img, _ = ch.render(spec, pose, "neutral", 0, ph, 1, h, False)
            a = np.asarray(img.getchannel("A")) > 40
            a = cv2.dilate(a.astype(np.uint8), np.ones((5, 5), np.uint8))
            n, lab, stats, _ = cv2.connectedComponentsWithStats(a, connectivity=8)
            parts = [s[cv2.CC_STAT_AREA] for s in stats[1:] if s[cv2.CC_STAT_AREA] >= MIN_AREA]
            if len(parts) > 1:
                bad.append((pose, ph, len(parts)))
                break
    return bad


UPRIGHT = ("stand", "walk", "run", "sneak", "carry", "talk_a", "talk_b", "shrug", "point_left", "point_right", "wave", "present", "idea", "think", "whisper", "hands_hips", "arms_wide")


def check_feet(spec: "ch.CharacterSpec", h: int = 400) -> list[str]:
    """Для tunic/armor/frock без плаща: у нижній смузі силуету рівно ДВА чоботи (не злиплі, не перехрещені, не відірвані), ступні на однаковій
    висоті ±12% (піднята нога ≤ підйому кроку) і між ними є просвіт."""
    if spec.style not in ("tunic", "armor", "frock") or spec.cape:
        return []
    import dataclasses
    spec = dataclasses.replace(spec, item=None)   # жердина вил/посоха зливається з чобітьми — це предмет, не ноги
    bad = []
    for pose in UPRIGHT:
        walking = ch.POSES[pose].get("walk", False)
        for ph in (PHASES if walking else PHASES[:2]):
            img, _ = ch.render(spec, pose, "neutral", 0, ph, 1, h, False)
            a = np.asarray(img.getchannel("A")) > 40
            ys = np.where(a.any(axis=1))[0]
            if len(ys) == 0:
                continue
            y1 = ys.max()
            strip = np.zeros_like(a)
            strip[max(y1 - int(0.07 * h), 0): y1 + 1] = a[max(y1 - int(0.07 * h), 0): y1 + 1]
            n, lab, stats, _ = cv2.connectedComponentsWithStats(strip.astype(np.uint8), connectivity=8)
            parts = [st for st in stats[1:] if st[cv2.CC_STAT_AREA] >= 40]
            if len(parts) != 2:
                bad.append(f"{pose}@{ph:.1f}:{len(parts)} boots")
                break
    return bad


def assert_cast(cast: str, log=print) -> None:
    """Викликається перед рендером: зламані персонажі не потрапляють у відео."""
    problems = []
    for k, v in CASTS[cast].items():
        spec = ch.CharacterSpec(**actor_kwargs(v))
        for b in check_actor(spec) + check_feet(spec):
            problems.append(f"{cast}/{k}: {b}")
    if problems:
        sep = chr(10) + "  "
        raise RuntimeError("зламані персонажі, рендер зупинено:" + sep + sep.join(map(str, problems[:12])))
    log(f"перевірка персонажів «{cast}»: ок")


def main() -> int:
    casts = sys.argv[1:] or list(CASTS)
    total = 0
    for c in casts:
        for k, v in CASTS[c].items():
            spec = ch.CharacterSpec(**actor_kwargs(v))
            bad = check_actor(spec)
            feet = check_feet(spec)
            total += len(bad) + len(feet)
            if feet:
                print(f"FEET {c}/{k} [{spec.style}]", "; ".join(feet[:6]))
            print(f"{'FAIL' if bad else 'ok  '} {c}/{k} [{spec.style}]", ", ".join(f"{p}@{ph:.1f}" for p, ph, _ in bad[:8]))
    print("відірвані частини:", total)
    return 1 if total else 0


if __name__ == "__main__":
    raise SystemExit(main())
