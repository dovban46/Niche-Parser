"""Різноманітність монтажу Japan (2026-11-10, користувач: «зараз всі відео майже однакові, потрібно міняти»).

Після beatsrc.merge / озвучки і перед render:
1. Профіль відео (montage.json): градація, колір активного слова в субтитрах, частинки в повітрі, вигляд банера розділу.
   Береться комбінація, якої ще не було в попередніх відео (історія в storage/jp_jobs/_montage_history.json).
2. Біти: камери push/pull/panl/panr/punch/drift_* + rack (різкість за глибиною), tilt (голландський кут), snap (стоїть, потім
   різкий наїзд), hand (з рук), crane (від деталі до загального); переходи cut/whip/flash/zoom/ink + dissolve/burn/iris;
   look: mono (шок), sepia (легенда/спогад); grid: 2-4 біти-плитки на одному екрані («інвентар»: деталі броні, зброя).
   Поруч не стоять однакові камери; розділи відкриваються різними переходами, а не завжди ink.

    vary.apply(slug, grids=[(61, 64), ...], profile=None, seed=3)
Оригінал зберігається в beats_novary.json; повторний виклик стартує з нього. Ручні поля look/grid з beats_src лишаються."""

import itertools
import random
import re
from collections import Counter

from . import core

CAMS = ["push", "pull", "panl", "panr", "drift_up", "drift_down", "rack", "tilt", "snap", "hand", "crane"]
FACE = re.compile(r"close-up|face|eyes|staring|grin|frown|shout|scream", re.I)
WIDE = re.compile(r"\b(wide|aerial|overhead|high-angle|establishing|valley|field|army|armies|whole|panorama|from above)\b", re.I)
TENSE = re.compile(r"\b(charge|charging|volley|smoke|fire|firing|aim|aiming|enemy|battle|attack|run|running|fall|falling|dead|blood)", re.I)
SOFT = re.compile(r"\b(laugh|smil|sleep|asleep|gentle|quiet|calm|dawn|sunrise|memory|old man|grandfather|child)", re.I)
LEGEND = re.compile(r"\b(legend|scroll painting|old painting|memory|remembers|flashback|centuries ago|long ago)\b", re.I)

PROFILES = [dict(zip(("grade", "subs", "particles", "chapter"), c)) for c in itertools.product(
    ("warm", "cool", "dusk", "ink", "none"), ("yellow", "vermilion", "cream"), ("dust", "ash", "petals", "snow"), ("banner", "card"))]


def _dur(tl, i):
    return tl["beats"][i]["e"] - tl["beats"][i]["s"]


def pick_profile(slug: str, wish: dict | None = None, seed: int = 3) -> dict:
    """Профіль, що відрізняється від останніх відео хоча б трьома з чотирьох полів (wish = обов'язкові значення)."""
    hist_f = core.job_dir(slug).parent / "_montage_history.json"
    hist = core.load_json(hist_f, {})
    recent = [v for k, v in hist.items() if k != slug][-4:]
    rnd = random.Random(seed)
    cands = [p for p in PROFILES if all(p[k] == v for k, v in (wish or {}).items())]
    rnd.shuffle(cands)
    best = max(cands, key=lambda p: min([sum(p[k] != r.get(k) for k in p) for r in recent] or [4]))
    hist[slug] = best
    core.save_json(hist_f, hist)
    return best


HOOK_STYLES = ["caption", "seal", "flash", "stamp"]   # вигляд тексту-гачка перших секунд (render.draw_hook)


def pick_hook(slug: str, wish: str | None = None, seed: int = 3) -> str:
    """Стиль тексту-гачка, якого не було в 2 попередніх відео (користувач 2026-11-11: «текст зверху однаковий у кожному відео»).
    stamp = старий рядок штампів угорі (був у всіх відео до v22), тому його автоматично не беремо."""
    hist_f = core.job_dir(slug).parent / "_montage_history.json"
    hist = core.load_json(hist_f, {})
    recent = [v.get("hook", "stamp") for k, v in hist.items() if k != slug][-2:]
    style = wish or next((s for s in random.Random(seed).sample(HOOK_STYLES[:-1], 3) if s not in recent), "caption")
    hist.setdefault(slug, {})["hook"] = style
    core.save_json(hist_f, hist)
    return style


def apply(slug: str, grids: list[tuple[int, int]] | None = None, profile: dict | None = None, seed: int = 3, hook_n: int = 8) -> dict:
    d = core.job_dir(slug)
    src = d / "beats_novary.json"
    beats = core.load_json(src) if src.exists() else core.load_json(d / "beats.json")
    core.save_json(src, beats)
    tl = core.load_json(d / "timeline.json")
    rnd = random.Random(seed)
    n = len(beats)
    hook_wish = (profile or {}).get("hook")
    prof = dict(pick_profile(slug, {k: v for k, v in (profile or {}).items() if k != "hook"} or None, seed))
    prof["hook"] = pick_hook(slug, hook_wish, seed)
    core.save_json(d / "montage.json", prof)

    # 1) плитки-«інвентар»
    in_grid = {i for i, b in enumerate(beats) if b.get("grid")}
    for k, (a, z) in enumerate(grids or []):
        for i in range(a, z + 1):
            beats[i]["grid"] = f"g{k}"
            in_grid.add(i)
    for i in in_grid:
        beats[i]["cam"], beats[i]["tr"] = "push", "cut"

    # 2) вигляд: легенда/спогад -> sepia; шокові удари -> mono (кожен другий, не частіше ніж раз на 12 бітів)
    last_mono = -99
    for i, b in enumerate(beats):
        if i in in_grid or b.get("look"):
            continue
        if LEGEND.search(b["img"]):
            b["look"] = "sepia"
        elif b["cam"] == "punch" and b.get("sfx") in ("x_sting", "x_thud", "x_boom", "x_gasp") and i - last_mono >= 12 and i >= hook_n:
            if rnd.random() < 0.5:
                b["look"] = "mono"
                last_mono = i

    # 3) переходи: розділи по черзі ink/burn/iris/dissolve; м'які моменти dissolve; вхід/вихід sepia через dissolve
    ch_tr = ["ink", "burn", "iris", "dissolve"]
    rnd.shuffle(ch_tr)
    k = 0
    for i, b in enumerate(beats):
        if not i or i in in_grid:
            continue
        if b.get("chapter"):
            b["tr"] = ch_tr[k % len(ch_tr)]
            k += 1
        elif b.get("look") == "sepia" or beats[i - 1].get("look") == "sepia":
            b["tr"] = "dissolve"
        elif b.get("tr", "cut") == "cut" and SOFT.search(b["img"]) and rnd.random() < 0.5:
            b["tr"] = "dissolve"

    # 4) камери
    for i, b in enumerate(beats):
        if i in in_grid or b["cam"] == "punch":
            continue
        txt, cam = b["img"], b["cam"]
        if WIDE.search(txt) and rnd.random() < 0.45:
            cam = "crane"
        elif FACE.search(txt) and rnd.random() < 0.6:
            cam = rnd.choice(["rack", "hand"])
        elif TENSE.search(txt) and rnd.random() < 0.4:
            cam = rnd.choice(["tilt", "hand"])
        elif cam == "push" and _dur(tl, i) >= 2.4 and rnd.random() < 0.4:
            cam = "snap"
        elif cam == "push" and rnd.random() < 0.35:
            cam = rnd.choice(["rack", "drift_up", "panr", "panl", "pull"])
        b["cam"] = cam
    for i in range(1, n):                       # punch лише як акцент: два punch поспіль -> другий інший прийом
        b, prev = beats[i], beats[i - 1]
        if i >= hook_n and i not in in_grid and b["cam"] == "punch" and prev["cam"] == "punch" and not b.get("fx"):
            b["cam"] = rnd.choice(["snap", "hand", "rack", "push", "tilt"] if TENSE.search(b["img"]) else ["snap", "hand", "rack", "push", "pull"])
    for i in range(1, n):
        b, prev = beats[i], beats[i - 1]
        if i in in_grid or b["cam"] == "punch":
            continue
        if b["cam"] == prev["cam"]:
            opts = [c for c in CAMS if c != prev["cam"] and (i + 1 >= n or c != beats[i + 1]["cam"])]
            b["cam"] = rnd.choice(opts)

    # 5) гачок: кожен план інший прийом
    hook_mix = [("hand", "cut"), ("snap", "whip"), ("punch", "flash"), ("tilt", "cut"), ("crane", "burn"),
                ("pull", "whip"), ("punch", "cut"), ("rack", "dissolve")]
    for i in range(min(hook_n, n)):
        if i in in_grid:
            continue
        cam, tr = hook_mix[(i + seed) % len(hook_mix)]
        if beats[i]["cam"] == "punch":
            cam = "punch"
        beats[i]["cam"], beats[i]["tr"] = cam, (tr if i else "cut")

    core.save_json(d / "beats.json", beats)
    st = {"profile": prof, "cam": Counter(b["cam"] for b in beats), "tr": Counter(b.get("tr", "cut") for b in beats),
          "look": Counter(b.get("look") for b in beats if b.get("look")), "grid_beats": len(in_grid),
          "same_cam_in_row": sum(1 for i in range(1, n) if beats[i]["cam"] == beats[i - 1]["cam"] and beats[i]["cam"] != "punch")}
    print(st)
    return st
