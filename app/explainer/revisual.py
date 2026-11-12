"""Точкова переробка візуалу окремих розділів (текст і таймінги НЕЗМІННІ — озвучка вже є). Для розділів, де QA виявив
нудьгу: довгі серії одного фону, забагато мудреця/«study».
    python -m app.explainer.revisual <slug> 4 6 7"""
import sys
from concurrent.futures import ThreadPoolExecutor

from ..providers.llm.anthropic_provider import AnthropicLLMProvider, _extract_json
from . import assets, director
from .character import EXPRS, POSES
from .produce import _jload, _jsave, _wd, merged_catalog

NL = chr(10)

_RULES = director._FORMAT + """

TASK: RE-DIRECT the visuals of ONE section. The narration beats are FINAL (given with index i) — do not change, merge or split them. For EVERY beat return its visuals.
Output ONLY a JSON array with exactly one object per input beat, in order, each with "i" (echo the index) and the fields:
 bg (catalog key), who ("sage" | "you" | extra-actor key | null), pose (%(poses)s), pose2 (optional second pose for a mid-beat gesture change), expr (%(exprs)s),
 speak (true only for the sage narrator or a quoted line), x (0.15-0.85), x2 (optional, walking), face (1/-1 optional),
 props: optional [[prop_key, x, y, h(0.25-0.6), anim(%(anims)s)], ...] (max 2, other half from the actor), big (optional <=3 words CAPS, at most 1 beat in 4),
 cam (drift | punch | shake), tr (cut | whip | wipe | flash | iris), sfx (optional list, max 1, from %(sfx)s).

HARD RULES (the previous version of this section FAILED them — fix it):
- The sage appears in AT MOST @SAGE@ beats of this section (about 8 percent), never 2 in a row, only for a joke, a "wait for it" or a one-line summary. "study" background AT MOST 2 beats.
- USE AT LEAST @MINBG@ DIFFERENT BACKGROUNDS in this section; change the background every 2-4 beats; NEVER more than 4 consecutive beats on the same background; \
never two consecutive beats with the same bg + who + pose.
- Show, don't tell: act the story out with "you" and the extra actors, props/gods/creatures as big shots, establishing shots of places (who = null), big text for terms.
- SCENE LOGIC: characters only on solid ground — see each background's "ground x" ranges; a background marked NO GROUND is for who=null shots or props only. The background must physically fit the line.
- Props named in the narration must be on screen at that beat. Transitions: "cut" for at least 80 percent; whip/wipe/iris/flash only at changes of place. cam mostly "drift"; sfx about 1 per 12 beats.
""" % {"poses": ", ".join(POSES), "exprs": ", ".join(EXPRS), "anims": ", ".join(director.ANIMS), "sfx": ", ".join(director.SFX_OK)}


def revisual(slug: str, sections: list[int], log=print) -> None:
    wd = _wd(slug)
    sbp = wd / "storyboard.json"
    sb = _jload(sbp)
    if not (wd / "storyboard_pre_revisual.json").exists():
        _jsave(wd / "storyboard_pre_revisual.json", sb)
    design = _jload(wd / "design.json")
    bgs_all, props_all, actors_all = merged_catalog(design)
    walk = {k: assets.analyze_bg(k)["walkable"] for k in bgs_all if (assets.ASSET_ROOT / "bg" / f"{assets._slug(k)}.png").exists()}
    catalog = director.catalog_text(bgs_all, props_all, actors_all, walk)
    llm = AnthropicLLMProvider()
    n_sec = len(sb["sections"])

    def one(sec: int):
        beats = [b for b in sb["beats"] if b["sec"] == sec]
        n = len(beats)
        system = _RULES.replace("@SAGE@", str(max(2, round(n * 0.08)))).replace("@MINBG@", str(min(14, max(8, n // 4))))
        listing = NL.join(f"{i}: {b['t']}" for i, b in enumerate(beats))
        user = (f"SECTION {sec + 1}/{n_sec}: {sb['sections'][sec]}{NL}VIDEO TOPIC: {sb.get('topic', '')}{NL}{NL}{catalog}{NL}{NL}NARRATION BEATS (final):{NL}{listing}")
        for attempt in range(3):
            log(f"візуал розділу {sec + 1} ({n} бітів), спроба {attempt + 1} …")
            raw = llm._complete(system, user, 16000, effort="medium")
            try:
                data = _extract_json(raw)
            except Exception:  # noqa: BLE001
                continue
            if isinstance(data, list) and len(data) >= n * 0.9:
                return sec, data
        return sec, None

    with ThreadPoolExecutor(max_workers=3) as ex:
        results = dict(ex.map(one, sections))
    new_all: list[dict] = []
    for sec in range(n_sec):
        old = [b for b in sb["beats"] if b["sec"] == sec]
        res = results.get(sec) if sec in sections else None
        if res is None:
            new_all += old
            if sec in sections:
                log(f"розділ {sec + 1}: LLM не дав валідної відповіді — лишено старий")
            continue
        by_i = {int(v["i"]): v for v in res if isinstance(v, dict) and "i" in v}
        raw = []
        for i, b in enumerate(old):
            v = dict(by_i.get(i, {}))
            v["t"] = b["t"]
            raw.append(v)
        fixed, warns = director.sanitize(raw, bgs_all, props_all, actors_all)
        if len(fixed) != len(old):
            raise RuntimeError(f"розділ {sec + 1}: {len(fixed)} != {len(old)}")
        for o, f in zip(old, fixed):
            f.update({"s": o["s"], "e": o["e"], "words": o["words"], "sec": sec})
        new_all += fixed
        log(f"розділ {sec + 1}: попереджень {len(warns)}")
    sb["beats"] = new_all
    used_bg = {b["bg"] for b in new_all}
    used_props = {p[0] for b in new_all for p in b.get("props", [])}
    sb["backgrounds"] = {k: v for k, v in bgs_all.items() if k in used_bg}
    sb["props"] = {k: v for k, v in props_all.items() if k in used_props}
    used_actors = {b["who"] for b in new_all if b.get("who")} | {"sage", "you"}
    sb["actors"] = {k: v for k, v in actors_all.items() if k in used_actors}
    flo = [k for k, v in (design.get("props") or {}).items() if isinstance(v, dict) and v.get("float")]
    sb["prop_float"] = [k for k in flo if k in used_props]
    _jsave(sbp, sb)


if __name__ == "__main__":
    revisual(sys.argv[1], [int(x) for x in sys.argv[2:]])
