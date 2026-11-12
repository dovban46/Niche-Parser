"""Shorts (9:16, ≤45 с) у тому самому світі, що й довге відео, але як ОКРЕМИЙ оригінальний твір: власний сценарій (інший кут і структура, не нарізка),
власні вертикальні фони, ті самі персонажі/предмети з бібліотеки. Кінець підводить до повного відео («повна історія — на каналі»).
    python -m app.explainer.shorts <slug> --facts <файл фактів> --angle "кут" [--step plan|assets|voice|render|package|all]
Робоча тека: storage/explainer_jobs/<slug>/ ; видача: videos/<slug>/ (video.mp4, metadata.txt)."""
import os

os.environ["EXPLAINER_ORIENT"] = "vertical"   # ПЕРЕД імпортом render (константи роздільності читаються при імпорті; воркери успадковують)

import argparse
import json
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from ..config import VIDEOS_ROOT
from ..providers.llm.anthropic_provider import AnthropicLLMProvider, _extract_json
from . import assets, director
from .character import EXPRS, POSES
from .produce import NL, _jload, _jsave, _wd, step_render, step_voice

_SYSTEM = """You write ORIGINAL YouTube Shorts for the channel Forbidden Folio (forbidden texts and legends of antiquity; animated flat cartoon, vertical 9:16).
The Short is a standalone piece, NOT a cut of a long video: its own angle, its own wording, its own visuals. At its end it loops back to the hook.

RETENTION CRAFT (follow strictly):
- Beat 1 (0-1.5 s) = the HOOK: one concrete, surprising, TRUE claim from the fact sheet, <=7 words, a statement (not a question, not 'did you know', no greeting, no channel name).
  It must be visible on screen as big text at frame 0.
- Beats 2-6 (to ~8 s): raise the stakes and open a loop ("and the strange part is...", a number, a name) — never explain background first.
- Middle: 3 quick reveals, each one a new fact + a new picture; a pattern interrupt (new background, big text, sound) every ~1.5 s.
- Last 3 beats: payoff (the answer to the loop), then end on a half-sentence that flows into beat 1 so the Short loops. NEVER announce, promise or tease a next video, next role, next episode or 'coming soon' — not in narration, not in big text, not in description.
- Total narration 100-120 words = 36-44 s. Plain, vivid, spoken English, second person where natural. Absolutely no lies: nothing invented (claims must come from the fact sheet or be common knowledge) but you MAY dramatise how it is told.

OUTPUT: ONLY JSON {"title_working": "...", "hook": "...", "backgrounds": {"key_snake_case": "english prompt of ONE empty tall vertical place, 12-22 words, rich with detail and clear ground in the lower middle"},
 "beats": [ ...38-46 beats... ]}
VISUAL RICHNESS IS A HARD REQUIREMENT: the picture must feel busy and professional. Use 10-12 different backgrounds (change at least every 3 beats), 2 props in at least half of the beats,
an "emoji" on about one beat in three, big text on 40 percent of beats, and a different "shot" size on every beat.
Beat fields: t (2-3 words of narration, hard max 4) · bg (one of YOUR backgrounds) · who ("you" | "sage" | an actor key | null) · pose · pose2 (optional) · expr · speak (true only for sage) ·
x (0.3-0.7) · x2 optional · props [[prop_key, x, y, h, anim], ...] up to 2 (x 0.2-0.8; h 0.3-0.6; library keys only) · big (<=3 words CAPS) · emoji (ONE emoji that matches the words, optional) ·
shot ("wide" | "medium" | "close" | "insert" — close = face close-up for emotion, insert = close on the prop, medium = torso, wide = whole scene) ·
tr ("cut" | "whip" | "zoom" | "flash"; whip/zoom at changes of place) · sfx (optional tags; at most 4 in the whole Short; beat 1 may have "x_sting").
Poses: %(poses)s. Expressions: %(exprs)s. Prop anims: %(anims)s. SFX tags: %(sfx)s.
Never write stage directions or ALL-CAPS words inside "t". The sage (narrator) may appear at most 5 beats; the hero "you" and actors carry the story; props must appear on the beat where they are named.
""" % {"poses": ", ".join(POSES), "exprs": ", ".join(EXPRS), "anims": ", ".join(director.ANIMS), "sfx": ", ".join(director.SFX_OK)}


def _library_catalog(src_slug: str) -> tuple[dict, dict]:
    lib = assets.library()
    props = {k: v["p"] for k, v in lib["prop"].items()}
    actors = {"sage": {}}
    sbp = _wd(src_slug) / "storyboard.json"
    if sbp.exists():
        for k, v in _jload(sbp)["actors"].items():
            actors[k] = v
    from .samples import ACTORS
    actors.setdefault("you", ACTORS["you"])
    return props, actors


def step_plan(slug: str, facts_file: Path, angle: str, actor_src: str, log=print) -> dict:
    wd = _wd(slug)
    out = wd / "design.json"
    if out.exists():
        return _jload(out)
    props, actors = _library_catalog(actor_src)
    facts = Path(facts_file).read_text(encoding="utf-8")
    pcat = NL.join(f"  {k}: {v[:60]}" for k, v in props.items())
    user = (f"ANGLE OF THIS SHORT: {angle}{NL}{NL}FACT SHEET (the only allowed facts):{NL}{facts}{NL}{NL}PROP LIBRARY (use these keys only):{NL}{pcat}{NL}{NL}"
            f"ACTOR KEYS: {', '.join(actors)}")
    llm = AnthropicLLMProvider()
    data = None
    for attempt in range(4):
        try:
            raw = llm._complete(_SYSTEM, user, 16000, effort="medium")
            data = _extract_json(raw)
        except Exception as exc:  # noqa: BLE001
            log(f"спроба {attempt + 1}: {str(exc)[:80]}")
            continue
        if isinstance(data, dict) and len(data.get("beats", [])) >= 20:
            nw = sum(len(str(b.get("t", "")).split()) for b in data["beats"])
            if 95 <= nw <= 128:
                break
            log(f"спроба {attempt + 1}: {nw} слів — треба 95-115")
            user = user.split(NL + NL + "CORRECTION:")[0] + (NL + NL + f"CORRECTION: your previous draft had {nw} words. HARD LIMIT 100-120 words in total "
                   "(about 40-44 beats of 2-3 words). Cut whole facts: keep ONLY the hook, the verse quote, the source of the quote, the one reason it is missing, the Ethiopia twist, "
                   "Drop genealogies, Bruce, Qumran and the debate.")
            data = None
    if not data:
        raise RuntimeError("shorts: LLM не дав валідний план")
    bgs = dict(data["backgrounds"])
    beats, warns = director.sanitize(data["beats"], bgs, props, actors)
    for b in beats:
        b["sec"] = 0
        b["tr"] = b["tr"] if b["tr"] in ("cut", "whip") else "cut"
        b["cam"] = "drift"
    if beats and not beats[0].get("big"):
        beats[0]["big"] = " ".join(beats[0]["t"].upper().split()[:3])
    if beats and not beats[0].get("sfx"):
        beats[0]["sfx"] = ["x_sting"]
    used_props = {p[0] for b in beats for p in b.get("props", [])}
    words = sum(len(b["t"].split()) for b in beats)
    design = {"fresh": True, "topic": data.get("title_working", slug), "title_working": data.get("title_working", slug),
              "hook": data.get("hook", ""), "format": "short",
              "sections": [{"title": data.get("title_working", "Short")}],
              "backgrounds": bgs,
              "props": {k: {"p": props[k], "float": assets._load_index()["prop"].get(k, {}).get("float", False)} for k in used_props},
              "actors": {k: v for k, v in actors.items() if k in {b["who"] for b in beats if b.get("who")} | {"sage", "you"} and k not in ("sage", "you")}}
    _jsave(wd / "beats.json", beats)
    _jsave(out, design)
    log(f"план: {len(beats)} бітів, {words} слів (≈{words / director.WORDS_PER_SEC:.0f} с), фонів {len(bgs)}, попереджень {len(warns)}")
    (wd / "script.txt").write_text(" ".join(b["t"] for b in beats), encoding="utf-8")
    return design


def step_assets(slug: str, log=print) -> None:
    wd = _wd(slug)
    design = _jload(wd / "design.json")

    def gen(kv):
        k, v = kv
        try:
            assets.ensure_bgv(k, v, log=lambda *_: None)
            assets.analyze_bg(k, kind="bgv")
            return None
        except Exception as exc:  # noqa: BLE001
            return f"{k}: {exc}"
    with ThreadPoolExecutor(max_workers=4) as ex:
        errs = [e for e in ex.map(gen, design["backgrounds"].items()) if e]
    for e in errs:
        log("  ! " + e)
    if errs:
        raise RuntimeError("не всі вертикальні фони згенеровано")
    for k in design["props"]:
        if not (assets.ASSET_ROOT / "prop" / f"{assets._slug(k)}.png").exists():
            assets.ensure_prop(k, design["props"][k]["p"], log=lambda *_: None)
    walk = {k: assets.analyze_bg(k, kind="bgv")["walkable"] for k in design["backgrounds"]}
    log("вертикальні фони без ґрунту: " + (", ".join(k for k, w in walk.items() if not w) or "немає"))


def step_package(slug: str, link_placeholder: str = "[LINK TO THE FULL VIDEO]", log=print) -> Path:
    wd = _wd(slug)
    design = _jload(wd / "design.json")
    script = (wd / "script.txt").read_text(encoding="utf-8")
    llm = AnthropicLLMProvider()
    system = ("You package a YouTube Short (vertical, ~40 s) for a channel about forbidden texts and legends of antiquity. Output ONLY JSON: "
              '{"titles": [3 titles, each <=55 characters, hook-first, specific, honest (never say a text was banned unless the script says so), no ALL CAPS, no hashtags in titles], '
              '"description": "2 short lines: the hook sentence and one line of context, then 3 hashtags including #Shorts. NEVER mention a link, a full video, a next video or a follow-up", '
              '"pinned_comment": "one question that makes people answer in the comments", "tags": ["10 short tags"]}')
    raw = llm._complete(system, f"SHORT SCRIPT:{NL}{script}", 1500, effort="low")
    meta = _extract_json(raw)
    dest = VIDEOS_ROOT / slug
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(wd / "video.mp4", dest / "video.mp4")
    lines = ["НАЗВИ (≤55 символів)", "=" * 20] + [f"{i}. {t}  ({len(t)})" for i, t in enumerate(meta["titles"], 1)]
    lines += ["", "ОПИС", "=" * 4, meta["description"], "", "ЗАКРІПЛЕНИЙ КОМЕНТАР", "=" * 4, meta["pinned_comment"], "",
              "ТЕГИ", "=" * 4, ", ".join(meta["tags"]), "", "СЦЕНАРІЙ", "=" * 4, script]
    (dest / "metadata.txt").write_text(NL.join(lines), encoding="utf-8")
    log(f"видача: {dest}")
    return dest


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("slug")
    ap.add_argument("--facts")
    ap.add_argument("--angle", default="")
    ap.add_argument("--actors-from", default="e03-enoch-four-chambers", help="job, з якого брати визначення акторів")
    ap.add_argument("--step", default="all")
    a = ap.parse_args()
    steps = ["plan", "assets", "voice", "render", "package"] if a.step == "all" else [a.step]
    for st in steps:
        if st == "plan":
            step_plan(a.slug, Path(a.facts), a.angle, a.actors_from)
        elif st == "assets":
            step_assets(a.slug)
        elif st == "voice":
            step_voice(a.slug)
        elif st == "render":
            step_render(a.slug)
        elif st == "package":
            step_package(a.slug)


if __name__ == "__main__":
    main()
