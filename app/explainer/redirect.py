"""Повторна візуальна режисура вже озвученого відео: текст і таймінги НЕЗМІННІ (озвучку не чіпаємо), змінюються лише
кадри — більше різноманітних локацій, предметів, дійових осіб; мудрець лише акцентами. Результат — оновлений storyboard.json.
    python -m app.explainer.redirect <slug> --step design|visuals|merge"""
import argparse
import json
import random
import shutil

from ..config import STORAGE_ROOT
from ..providers.llm.anthropic_provider import AnthropicLLMProvider, _extract_json
from . import director, samples
from .character import EXPRS, POSES
from .produce import _jload, _jsave, _wd, merged_catalog

NL = chr(10)

_DESIGN2 = """You are the art director of an animated explainer (flat cartoon style, one recurring wise old sage narrator, the viewer as hero "you").
The narration is FINAL and already recorded. The picture was too repetitive: too few places, the sage on screen too often, similar shots.
TASK: design a RICH, VARIED visual world for this narration. Output ONLY JSON:
{"backgrounds": {"key": "english prompt of an EMPTY place (no people/characters/text)"},
 "props": {"key": "english prompt of ONE object or ONE god/creature figure, full body, simple"},
 "actors": {"key": {"skin":[r,g,b],"hair":[r,g,b] or null,"beard":[r,g,b] or null,"style":"robe|kilt","robe":[r,g,b],"trim":[r,g,b],"hat":"%(hats)s","hat_color":[r,g,b],"brows":[r,g,b],"head_r":1.0}}}
Rules:
- NEW backgrounds: 16 (keys snake_case). Every place and moment the narration touches deserves its own truly matching location. Vary time of day (dawn, noon, dusk, night with stars), \
interior/exterior, palette (warm sand, cool blue night, green marsh, red fire-lit, gold temple), and composition. Examples of the kind of variety wanted (adapt to the narration): \
village by the Nile, fisherman's reed boat on the river, pyramids at dusk, temple courtyard with pylon, burial chamber with a sarcophagus, starry night sky of the goddess Nut, \
fire lake, gate of the Duat with guardians' statues, papyrus marsh, scribe's workshop, market street, throne dais of Osiris, sunrise horizon, dark void with a glowing path, cliff tombs of Thebes at night.
- Already existing backgrounds (do not redefine): %(bgs)s. Existing props: %(props)s. Existing actors: %(actors)s.
- NEW props: 14 — distinct, recognisable, story-relevant objects/creatures/gods (e.g. Thoth the ibis-headed scribe, Osiris on his throne, Horus falcon, Apophis serpent, heart scarab, \
papyrus scroll, pyramid, sun disk, boat, flames, gate, mask of Anubis, bread and beer, hoe and sickle) — only what the narration really mentions or can illustrate.
- NEW actors: 4 distinct characters usable as extras (scribe, guard/soldier, farmer, noble/pharaoh...). Clothes/hat must make them instantly recognisable.
- Keys short english snake_case; do not reuse existing keys.
""" % {"hats": "|".join(director.HATS), "bgs": "", "props": "", "actors": ""}

_VISUALS = director._FORMAT + """

TASK: RE-DIRECT the visuals of ONE section. The narration beats are FINAL (given with index i) — do not change, merge or split them. For EVERY beat return its visuals.
Output ONLY a JSON array with exactly one object per input beat, in order, each with "i" (echo the index) and the fields:
 bg (catalog key), who ("sage" | "you" | extra-actor key | null), pose (%(poses)s), pose2 (optional second pose: the gesture changes mid-beat; choose a DIFFERENT pose that fits), expr (%(exprs)s),
 speak (true only for the sage narrator or a quoted line), x (feet 0.15-0.85), x2 (optional, walking), face (1/-1 optional),
 props: optional [[prop_key, x, y(0.3-0.65), h(0.25-0.85), anim(%(anims)s)], ...], big (optional <=3 words CAPS), cam (drift | punch | shake), tr (cut | whip | wipe | flash | iris), sfx (optional list, max 1, from %(sfx)s).

GOALS AND HARD RULES:
- The sage is a SPICE, not the main picture: at most 15%% of the beats in this section, never more than 2 in a row, and only for a joke, an aside, a "wait for it" or a summary. \
When he appears, vary pose/pose2/expression and let him MOVE (walk in with x -> x2, point at props, lean in, whisper, laugh, cross arms). He may stand ON LOCATION in the scene's own background \
(not only in "study"); "study" at most 3 beats in this section.
- Everything else is SHOWN: dramatise the narration with scenes — the hero "you" and extra actors acting it out, props and gods as big picture shots, establishing shots of places (who = null), \
big text for key terms. Illustrate even asides with an image (a joke about a price list -> a market background with a prop). Prefer a concrete visual metaphor to talking heads.
- VARIETY: use at least 8 different backgrounds in this section; change the background at least every 3-4 beats on average; never more than 6 beats in a row on one background; \
never more than 2 consecutive beats with the same bg AND who AND pose. Spread x positions (0.2-0.8), alternate sides, use walking, running, sneaking, cheering, scared poses where the line fits.
- Every background you use MUST truly match the place/moment in the line. Props named in the narration must be on screen at that beat.
- Props: x 0.1-0.9 on the OPPOSITE half from the actor; at most 2 per beat. cam: mostly "drift"; "punch" for at most 1 beat in 10; "shake" only for impacts. Transitions: "cut" for >=70%%; whip/wipe/iris/flash only at changes of place.
- sfx: about 1 per 12 beats, only for reveals/jokes/impacts.
""" % {"poses": ", ".join(POSES), "exprs": ", ".join(EXPRS), "anims": ", ".join(director.ANIMS), "sfx": ", ".join(director.SFX_OK)}


def step_design(slug: str, log=print) -> dict:
    wd = _wd(slug)
    out = wd / "design2.json"
    if out.exists():
        return _jload(out)
    sb = _jload(wd / "storyboard.json")
    design = _jload(wd / "design.json")
    bgs, props, actors = merged_catalog(design)
    system = _DESIGN2.replace("Already existing backgrounds (do not redefine): .", "Already existing backgrounds (do not redefine): " + ", ".join(bgs) + ".")
    system = system.replace("Existing props: .", "Existing props: " + ", ".join(props) + ".").replace("Existing actors: .", "Existing actors: " + ", ".join(actors) + ".")
    script = (wd / "script.txt").read_text(encoding="utf-8")
    llm = AnthropicLLMProvider()
    raw = llm._complete(system, "NARRATION (final):" + NL + script, 9000, effort="medium")
    data = _extract_json(raw)
    if not isinstance(data, dict):
        raise RuntimeError("design2: не JSON")
    _jsave(out, data)
    return data


def catalogs(wd):
    design = _jload(wd / "design.json")
    d2 = _jload(wd / "design2.json")
    bgs, props, actors = merged_catalog(design)
    bgs.update(d2.get("backgrounds") or {})
    props.update(d2.get("props") or {})
    for k, v in (d2.get("actors") or {}).items():
        if k not in actors and isinstance(v, dict):
            actors[k] = v
    return bgs, props, actors


def step_visuals(slug: str, log=print) -> None:
    from concurrent.futures import ThreadPoolExecutor
    wd = _wd(slug)
    sb = _jload(wd / "storyboard.json" if not (wd / "storyboard_v1.json").exists() else wd / "storyboard_v1.json")
    bgs, props, actors = catalogs(wd)
    catalog = director.catalog_text(bgs, props, actors)
    llm = AnthropicLLMProvider()
    (wd / "visuals").mkdir(exist_ok=True)
    n_sec = len(sb["sections"])

    def one(sec: int):
        f = wd / "visuals" / f"{sec:02d}.json"
        if f.exists():
            return None
        beats = [b for b in sb["beats"] if b["sec"] == sec]
        listing = NL.join(f"{i}: {b['t']}" for i, b in enumerate(beats))
        user = (f"SECTION {sec + 1}/{n_sec}: {sb['sections'][sec]}{NL}VIDEO TOPIC: {sb.get('topic', '')}{NL}{NL}{catalog}{NL}{NL}"
                f"NARRATION BEATS (final):{NL}{listing}")
        for attempt in range(3):
            log(f"візуали розділу {sec + 1}/{n_sec} ({len(beats)} бітів), спроба {attempt + 1} …")
            raw = llm._complete(_VISUALS, user, 16000, effort="medium")
            try:
                data = _extract_json(raw)
            except Exception:  # noqa: BLE001
                (wd / "visuals" / f"{sec:02d}.raw{attempt}.txt").write_text(raw, encoding="utf-8")
                continue
            if isinstance(data, list) and len(data) >= len(beats) * 0.9:
                _jsave(f, data)
                return None
        return f"розділ {sec + 1}: не вдалось отримати валідний JSON"

    with ThreadPoolExecutor(max_workers=3) as ex:
        errs = [e for e in ex.map(one, range(n_sec)) if e]
    if errs:
        raise RuntimeError("; ".join(errs))


def _postprocess(beats: list[dict]) -> None:
    """Страховка від того, що модель могла проігнорувати: не більше 2 мудреців поспіль; камера без частих punch."""
    run = 0
    for b in beats:
        run = run + 1 if b["who"] == "sage" else 0
        if run > 2:
            b["who"], b["speak"], b["pose2"] = None, False, None
            b.pop("pose2", None)
            run = 0
    last_punch = -99
    for i, b in enumerate(beats):
        if b["cam"] == "punch":
            if i - last_punch < 8:
                b["cam"] = "drift"
            else:
                last_punch = i
    # фірмові переходи — рідкісний акцент: wipe не частіше ніж раз на 22 біти, whip — раз на 14
    last = {"wipe": -99, "whip": -99, "iris": -99, "flash": -99}
    gap = {"wipe": 22, "whip": 14, "iris": 20, "flash": 25}
    for i, b in enumerate(beats):
        t = b["tr"]
        if t in last:
            if i - last[t] < gap[t] or any(i - last[o] < 5 for o in last if last[o] > -99):
                b["tr"] = "cut"
            else:
                last[t] = i
    # великий текст — теж не підряд (інакше екран перевантажений разом із субтитрами)
    for i, b in enumerate(beats[1:], 1):
        if b.get("big") and beats[i - 1].get("big"):
            b.pop("big")
    # перехід без підстав — на cut, коли фон не змінився
    for i, b in enumerate(beats[1:], 1):
        if b["tr"] != "cut" and b["bg"] == beats[i - 1]["bg"] and b["tr"] in ("whip", "wipe", "iris"):
            b["tr"] = "cut"


def step_merge(slug: str, log=print) -> dict:
    wd = _wd(slug)
    sbp = wd / "storyboard.json"
    if not (wd / "storyboard_v1.json").exists():
        shutil.copyfile(sbp, wd / "storyboard_v1.json")
    sb = _jload(wd / "storyboard_v1.json")
    bgs, props, actors = catalogs(wd)
    new_beats, warns = [], []
    for sec in range(len(sb["sections"])):
        old = [b for b in sb["beats"] if b["sec"] == sec]
        vis = _jload(wd / "visuals" / f"{sec:02d}.json")
        by_i = {int(v["i"]): v for v in vis if isinstance(v, dict) and "i" in v}
        raw = []
        for i, b in enumerate(old):
            v = dict(by_i.get(i, {}))
            if not v:
                warns.append(f"розділ {sec + 1}, біт {i}: немає візуалу")
            v["t"] = b["t"]
            raw.append(v)
        fixed, w = director.sanitize(raw, bgs, props, actors)
        # sanitize може пропустити порожні; тут довжини збігаються (t задано завжди)
        if len(fixed) != len(old):
            raise RuntimeError(f"розділ {sec + 1}: {len(fixed)} != {len(old)}")
        for o, f in zip(old, fixed):
            f.update({"s": o["s"], "e": o["e"], "words": o["words"], "sec": sec})
            for k in ("pose2",):
                pass
            new_beats.append(f)
        warns += w
    # pose2: sanitize його не знає — переносимо з сирого JSON за індексами
    k = 0
    for sec in range(len(sb["sections"])):
        old = [b for b in sb["beats"] if b["sec"] == sec]
        vis = _jload(wd / "visuals" / f"{sec:02d}.json")
        by_i = {int(v["i"]): v for v in vis if isinstance(v, dict) and "i" in v}
        for i in range(len(old)):
            p2 = (by_i.get(i) or {}).get("pose2")
            nb = new_beats[k]
            if p2 in POSES and nb.get("who") and p2 != nb["pose"]:
                nb["pose2"] = p2
            k += 1
    _postprocess(new_beats)
    used_bg = {b["bg"] for b in new_beats}
    used_props = {p[0] for b in new_beats for p in b.get("props", [])}
    sb["beats"] = new_beats
    sb["backgrounds"] = {k: v for k, v in bgs.items() if k in used_bg}
    sb["props"] = {k: v for k, v in props.items() if k in used_props}
    used_actors = {b["who"] for b in new_beats if b.get("who")} | {"sage", "you"}
    sb["actors"] = {k: v for k, v in actors.items() if k in used_actors}
    _jsave(sbp, sb)
    n = len(new_beats)
    sage = sum(1 for b in new_beats if b.get("who") == "sage")
    log(f"бітів {n}; мудрець {sage} ({100 * sage / n:.0f}%); фонів {len(used_bg)}; предметів {len(used_props)}; актори {sorted(used_actors)}")
    log(f"study: {sum(1 for b in new_beats if b['bg'] == 'study')}; зі сценами (who != sage): {n - sage}; попереджень {len(warns)}")
    for w in warns[:12]:
        log("  ! " + w)
    return sb


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("slug")
    ap.add_argument("--step", required=True)
    a = ap.parse_args()
    if a.step == "design":
        d = step_design(a.slug)
        print("bg:", list(d.get("backgrounds", {})))
        print("props:", list(d.get("props", {})))
        print("actors:", list(d.get("actors", {})))
    elif a.step == "visuals":
        step_visuals(a.slug)
    elif a.step == "merge":
        step_merge(a.slug)


if __name__ == "__main__":
    main()
