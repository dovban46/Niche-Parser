"""Ручна розкадровка без API (рішення 2026-10-23, v04): я пишу beats_src.txt, потім compile → озвучка → merge до середнього біта.

Формат beats_src.txt: один біт на рядок
    дослівний фрагмент сценарію || опис кадру англійською || cast1,cast2 || cam k=v;k=v
cam: push|pull|panl|panr|punch|drift_up|drift_down; ключі: sfx, label, ch (розділ), tr, focus, hook (штампи через |),
hook_t (секунди штампів через |, після озвучки), keep (біт не зливати: швидкі плани гачка),
day (лічильник DAY N з цього біта), fx (slash|impact), bars (кінорамка).
Порядок:  beatsrc.compile(slug) → voice.synthesize(slug) → beatsrc.merge(slug, 2.2) → flow.export(slug)."""

import statistics as st

from . import core, plan
from .voice import TAIL_S


def compile(slug: str) -> list[dict]:
    """beats_src.txt → beats.json (перевірка слів проти сценарію, ключів cast і назв sfx)."""
    d = core.job_dir(slug)
    beats = []
    for ln in (d / "beats_src.txt").read_text(encoding="utf-8").splitlines():
        if not ln.strip():
            continue
        t, img, cast, rest = [x.strip() for x in ln.split("||")]
        cam, _, opts = rest.partition(" ")
        o = dict(kv.split("=", 1) for kv in opts.split(";") if kv)
        b = {"t": t, "img": img, "cast": [c for c in cast.split(",") if c], "cam": cam, "focus": o.get("focus", "C"),
             "tr": o.get("tr", "cut"), "ring": None, "label": {"text": o["label"], "kind": "stamp"} if "label" in o else None,
             "sfx": o.get("sfx"), "anim": None}
        if "ch" in o:
            b["chapter"] = o["ch"]
        if "keep" in o:
            b["keep"] = True
        if "day" in o:
            b["day"] = int(o["day"])          # лічильник днів (формат «N днів у…»): біт, з якого починається день
        if "fx" in o:
            b["fx"] = o["fx"]
        if "bars" in o:
            b["bars"] = True
        if "look" in o:
            b["look"] = o["look"]            # mono | sepia (2026-11-10, див. vary.py)
        if "mark" in o:            # mark=circle@0.7,0.45,0.14  |  arrow@x,y,r,dir  (координати в кадрі-картинці, 0..1)
            kind, _, nums = o["mark"].partition("@")
            v = [float(x) for x in nums.split(",")] if nums else [0.5, 0.5, 0.14]
            b["mark"] = {"kind": kind, "x": v[0], "y": v[1], "r": v[2] if len(v) > 2 else 0.14}
            if len(v) > 3:
                b["mark"]["dir"] = v[3]
        if "note" in o:            # note=ХЛОР?  noteat=0.5,0.15 (екран)  notec=red|green|blue|dark
            nx, ny = [float(x) for x in o.get("noteat", "0.5,0.15").split(",")]
            b["note"] = {"text": o["note"], "x": nx, "y": ny, "color": o.get("notec", "red")}
        if "grid" in o:
            b["grid"] = o["grid"]            # назва серії плиток «інвентар», 2-4 біти підряд
        if "hook" in o:
            b = {"hook": o["hook"], **b}
            if "hook_t" in o:
                b["hook_t"] = [float(x) for x in o["hook_t"].split("|")]
        beats.append(b)
    cast = plan.load_cast(slug)
    errs = plan.validate(beats, (d / "script.txt").read_text(encoding="utf-8"))
    errs += [f"біт {i}: невідомий cast {c}" for i, b in enumerate(beats) for c in b["cast"] if c not in cast]
    errs += [f"біт {i}: невідомий mark {b['mark']['kind']}" for i, b in enumerate(beats) if b.get("mark") and b["mark"]["kind"] not in ("circle", "arrow", "cross", "check", "underline")]
    lib = {p.stem for p in (d.parents[1] / "sfx_library").glob("*.mp3")}
    errs += [f"біт {i}: невідомий sfx {b['sfx']}" for i, b in enumerate(beats) if b["sfx"] and b["sfx"] not in lib]
    errs += [f"біт {i}: невідома камера {b['cam']}" for i, b in enumerate(beats) if b["cam"] not in plan.CAMS]
    if errs:
        raise ValueError("\n".join(errs))
    core.save_json(d / "beats.json", beats)
    print(f"біти: {len(beats)}")
    return beats


def _spans(beats):
    out, k = [], 0
    for b in beats:
        n = len(core.words_of(b["t"]))
        out.append((k, k + n - 1))
        k += n
    return out


def _times(beats, words):
    sp, res = _spans(beats), []
    for i, (f, _) in enumerate(sp):
        s = 0.0 if i == 0 else words[f]["s"] - 0.02
        e = words[sp[i + 1][0]]["s"] - 0.02 if i + 1 < len(sp) else words[-1]["e"] + TAIL_S
        res.append((round(max(s, 0.0), 3), round(e, 3)))
    return res


def merge(slug: str, target: float = 2.2) -> list[dict]:
    """Після озвучки: зливає найкоротші сусідні біти (не через межу абзацу/розділу), доки середній біт < target с.
    Лишає кадр довшого біта; оригінал зберігається в beats_raw.json; перераховує timeline.beats."""
    d = core.job_dir(slug)
    beats, tl = core.load_json(d / "beats.json"), core.load_json(d / "timeline.json")
    words, para = tl["words"], {l["word"] for l in tl["lines"]}
    n_target = round((words[-1]["e"] + TAIL_S) / target)
    core.save_json(d / "beats_raw.json", beats)
    while len(beats) > n_target:
        du = [e - s for s, e in _times(beats, words)]
        sp, best = _spans(beats), None
        for i in range(len(beats) - 1):
            b2 = beats[i + 1]
            if b2.get("chapter") or b2.get("hook") or b2.get("day") is not None or sp[i + 1][0] in para or beats[i].get("keep") or b2.get("keep"):
                continue
            if best is None or du[i] + du[i + 1] < best[0]:
                best = (du[i] + du[i + 1], i)
        if best is None:
            break
        i = best[1]
        a, b = beats[i], beats[i + 1]
        m = dict(a if du[i] >= du[i + 1] else b)
        m["t"] = a["t"] + " " + b["t"]
        for k in ("hook", "chapter", "day", "hook_t"):
            if a.get(k):
                m[k] = a[k]
            else:
                m.pop(k, None)
        m["tr"] = a["tr"]
        m["label"] = m.get("label") or a.get("label") or b.get("label")
        m["sfx"] = m.get("sfx") or a.get("sfx") or b.get("sfx")
        beats[i:i + 2] = [m]
    assert not plan.validate(beats, (d / "script.txt").read_text(encoding="utf-8"))
    core.save_json(d / "beats.json", beats)
    tl["beats"] = [{"first": f, "last": l, "s": s, "e": e} for (f, l), (s, e) in zip(_spans(beats), _times(beats, words))]
    core.save_json(d / "timeline.json", tl)
    du = [e - s for s, e in _times(beats, words)]
    print(f"біти: {len(beats)}, середній {st.mean(du):.2f} с, медіана {st.median(du):.2f}, мін {min(du):.2f}, макс {max(du):.2f}")
    return beats
