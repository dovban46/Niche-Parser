"""Серія Shorts «Life as a [роль]»: герой «ти» у костюмі ролі, RPG-інтерфейс (день, інвентар предметів, що вилітають у слот), гачок із фабрики гачків.
    python -m app.explainer.lifeas <slug> --role "Plague Doctor" --facts <файл> [--step hooks|plan|assets|voice|render|package|all]"""
from . import shorts as sh   # ВАЖЛИВО: першим (виставляє EXPLAINER_ORIENT=vertical до імпорту render)

import argparse
import json
from pathlib import Path

from ..providers.llm.anthropic_provider import AnthropicLLMProvider, _extract_json
from . import assets, director, hooks
from .character import EXPRS, POSES
from .produce import NL, _jload, _jsave, _wd, step_render, step_voice

from .casts import CASTS, DESC

_SYSTEM_T = """You write ORIGINAL YouTube Shorts for a new channel with the series "LIFE AS A [ROLE]": a second-person POV where the viewer IS the historical role.
Animated sticker-style cartoon, vertical 9:16. TARGET LENGTH 45-50 SECONDS (112-128 words, 40-50 beats of 2-4 words; never under 42 seconds) — short, because viewers who reach the end are what the algorithm rewards.

RETENTION ENGINEERING (this decides everything; the previous Short kept only ~40 percent, we want 60+):
1. Beat 1 = the CHOSEN HOOK verbatim. FIRST 5 SECONDS (the last Short fell to 28 percent because it opened on a calm portrait and then rewound through a black transition):
   - frame 0 is ACTION or CONFLICT (a threat, a slam, a prop flying in, an angry crowd), never a calm portrait or an establishing shot;
   - the story runs FORWARD in real time from beat 1: no cold open + "rewind", no flashback, no black/ink/iris transition in the first 5 seconds (use cut, whip, zoom or flash only);
   - beat 1 = a STAMP + shot "close" + a prop with anim "slam" or "spin_in" + sfx x_sting; beat 2 changes the shot and the background; beats 1-5 are at most 3 words each;
   - the viewer is addressed as "you" in beat 1 or 2 and is in danger or on a deadline by beat 3.
2. OPEN A LOOP by beat 4: a question or threat whose answer is withheld ("Touch it, and ...") and pay it off only in the last third. Never answer it early.
3. A NEW STIMULUS every ~1.2 s: new background, new shot size, big text, emoji, prop slam/spin, transition. Never two similar beats in a row.
4. ESCALATE: every 3-4 beats raise the stakes with a new fact or a reversal. No flat explanation, no definitions, no lists of gear.
5. INVOLVE THE VIEWER: exactly ONE decision beat with "choice" (two options, "pick" = which one the story takes) and a consequence beat right after it.
6. Pace changes: one beat of silence-like punch (1-2 words) before the biggest reveal.
7. PAYOFF at ~80 percent (the myth vs. what really happened, or the loop's answer), then end on a half-sentence that flows straight back into beat 1 so the Short loops. NEVER announce, promise or tease a next video, role or episode — not in narration, big text or description.
8. FACTS: nothing may be invented (use the fact sheet or common knowledge) but you MAY dramatise how it is told: vivid scenes, tension, humour, "you" details. Legends are told as legends. No gore, no bodies on screen; keep it a cartoon.

CAST (use these actor keys only; each looks different on purpose, never reuse one actor for a different character):
%(cast)s
Hero key is "you".

TOOLBOX FIELDS (use them; they make this Short look different from others):
 stamp "WORD" — a red stamp slams on screen (use on beat 1 and at most 2 more beats: "RECRUITED", "ORDERED", "TRAITOR"...)
 decree "short text (<=90 chars)" — a parchment decree types itself (at most 1 beat; an order from a ruler)
 choice ["OPT A","OPT B"] + pick 0/1 — the decision card (exactly 1 beat)
 counter [from, to, "LABEL"] — rolling number (at most 1 beat, only with a number from the fact sheet)
 circle true — a hand-drawn red circle around the first prop (at most 2 beats; the prop must be the thing being discussed)
 meters {"loyalty": 0-100, "fear": 0-100} — set on 6-9 beats where the story changes your standing (they animate)
 tilt number (-8..8) — dutch angle on tense beats (at most 3)
 burst true — sunburst behind the hero on the 3-4 strongest beats
 cta true — a SILENT like/subscribe sticker (about 2.5 s); put it on exactly ONE calm beat at 40-55 percent of the Short; the narration never mentions it
 day / gain — NOT used in this format
 Prop anims: use "slam" for heavy objects, "spin_in" for objects the hero grabs, "pop" otherwise.
 tr: "slash" (blade cut) for violent/decisive moments, "ink" (ink spill) for dark reveals and time jumps (NEVER in the first 5 beats), "whip"/"zoom" for place changes, "cut" otherwise.

OUTPUT: ONLY JSON {"title_working": "...", "backgrounds": {"key": "english prompt of ONE empty tall vertical place, 12-22 words, rich detail, clear ground in the lower middle"},
 "new_props": {"key": {"p": "english prompt of ONE object, 4-14 words", "float": true|false}}, "beats": [ ...30-38 beats... ]}
12-14 different backgrounds (change every ~3 beats). Reuse library props when they fit, add up to 12 new props.
Beat fields: t (2-3 words, hard max 4) · bg · who (a cast key or null) · pose · pose2 · expr · speak false · x (0.3-0.7) · x2 optional · props [[prop_key,x,y,h,anim]] up to 2 ·
big (<=3 words CAPS; on ~40 percent of beats) · emoji (one emoji, ~1 beat in 3) · shot ("wide"|"medium"|"close"|"insert", different every beat; use "insert" for props) · tr · sfx (<=4 tags in total; beat 1 may have "x_sting") + the toolbox fields.
Poses: %(poses)s. Expressions: %(exprs)s. Prop anims: %(anims)s. SFX tags: %(sfx)s.
Never write stage directions or ALL-CAPS words inside "t". Props must appear on the beat where they are named.
"""


def _system(cast: str) -> str:
    desc = chr(10).join(f" {k}: {v}" for k, v in DESC.get(cast, {}).items())
    return _SYSTEM_T % {"cast": desc, "poses": ", ".join(POSES), "exprs": ", ".join(EXPRS), "anims": ", ".join(director.ANIMS), "sfx": ", ".join(director.SFX_OK)}


def step_hooks(slug: str, role: str, facts: str, log=print) -> list[dict]:
    wd = _wd(slug)
    f = wd / "hooks.json"
    if f.exists():
        return _jload(f)
    llm = AnthropicLLMProvider()
    log("фабрика гачків: 10 кандидатів → оцінка …")
    ranked = hooks.best_hooks(llm, f"Life as a {role} (what the myth gets wrong)", facts, log=log)
    _jsave(f, ranked)
    return ranked


def step_plan(slug: str, role: str, facts: str, series: str, hook_index: int = 0, log=print, cast: str = "plague", hud: str = "inventory",
              grade: str = "", music: int = 1, angle: str = "") -> dict:
    wd = _wd(slug)
    out = wd / "design.json"
    if out.exists():
        return _jload(out)
    ranked = _jload(wd / "hooks.json")
    hook = ranked[hook_index]
    lib = assets.library()
    props = {k: v["p"] for k, v in lib["prop"].items()}
    ACTORS = CASTS[cast]
    pcat = NL.join(f"  {k}: {v[:56]}" for k, v in props.items())
    user = (f"ROLE: Life as a {role}{NL}CHOSEN HOOK (beat 1, verbatim): {hook['text']}{NL}HOOK FRAME 0: {hook.get('frame0', '')}{NL}HOOK BIG TEXT: {hook.get('big', '')}{NL}{NL}"
            f"FACT SHEET (the only allowed facts):{NL}{facts}{NL}{NL}PROP LIBRARY (reuse when it fits):{NL}{pcat}{NL}{NL}ACTOR KEYS: {', '.join(ACTORS)}{NL}{NL}STORY ANGLE / OUTLINE (follow it):{NL}{angle}")
    llm = AnthropicLLMProvider()
    data = None
    for attempt in range(4):
        try:
            data = _extract_json(llm._complete(_system(cast), user, 16000, effort="medium"))
        except Exception as exc:  # noqa: BLE001
            log(f"спроба {attempt + 1}: {str(exc)[:80]}")
            data = None
            continue
        if isinstance(data, dict) and len(data.get("beats", [])) >= 24:
            nw = sum(len(str(b.get("t", "")).split()) for b in data["beats"])
            if 104 <= nw <= 135:
                break
            log(f"спроба {attempt + 1}: {nw} слів — треба 112-128")
            user = user.split(NL + NL + "CORRECTION:")[0] + NL + NL + f"CORRECTION: previous draft had {nw} words. HARD LIMIT 112-128 total. Cut facts or merge beats; keep the hook, the loop, the decision, the payoff."
            data = None
    if not data:
        raise RuntimeError("lifeas: LLM не дав валідний план")
    new_props = {k: v for k, v in (data.get("new_props") or {}).items() if isinstance(v, dict) and v.get("p")}
    all_props = dict(props)
    all_props.update({k: v["p"] for k, v in new_props.items()})
    bgs = dict(data["backgrounds"])
    beats, warns = director.sanitize(data["beats"], bgs, all_props, ACTORS)
    for b in beats:
        b["sec"], b["cam"], b["speak"] = 0, "drift", False
        b["tr"] = b["tr"] if b["tr"] in ("cut", "whip", "zoom", "flash", "slash", "ink", "glitch", "pixel", "push", "shutter", "tear", "sweep") else "cut"
    for i_, b in enumerate(beats[:6]):   # перші ~5 с: без чорних/повільних переходів (урок s03: 28 відсотків)
        if b.get("tr") in ("ink", "iris", "wipe") or (i_ < 3 and b.get("tr") == "slash"):
            b["tr"] = "whip" if i_ % 2 else "zoom"
    beats[0]["tr"] = "cut"
    beats[0]["shot"] = "close"
    for pr in beats[0].get("props", []):
        if len(pr) > 4 and pr[4] in ("pop", "bob", "none"):
            pr[4] = "slam"
    beats[0]["t"] = hook["text"]
    beats[0]["big"] = (hook.get("big") or " ".join(hook["text"].upper().split()[:3]))
    beats[0]["sfx"] = ["x_sting"]
    beats[0]["burst"] = True
    beats[0].setdefault("stamp", (beats[0].get("big") or "WARNING").split()[0][:12])
    for raw, b in zip(data["beats"], beats):   # поля, яких санітайзер не знає
        for k in ("day", "gain", "burst", "stamp", "decree", "choice", "pick", "counter", "circle", "meters", "tilt", "cta"):
            if raw.get(k) not in (None, "", [], {}):
                b[k] = raw[k]
    used = {p[0] for b in beats for p in b.get("props", [])}
    words = sum(len(b["t"].split()) for b in beats)
    design = {"fresh": True, "format": "short", "series": series, "topic": f"Life as a {role}", "title_working": data.get("title_working", series),
              "sections": [{"title": data.get("title_working", series)}], "backgrounds": bgs,
              "hud": hud, "grade": grade, "music": music, "cast": cast,
              "props": {k: {"p": all_props[k], "float": (new_props.get(k, {}).get("float") if k in new_props
                                                         else assets._load_index()["prop"].get(k, {}).get("float", False))} for k in used},
              "actors": {k: v for k, v in ACTORS.items()}}
    _jsave(wd / "beats.json", beats)
    _jsave(out, design)
    (wd / "script.txt").write_text(" ".join(b["t"] for b in beats), encoding="utf-8")
    log(f"план: {len(beats)} бітів, {words} слів (≈{words / director.WORDS_PER_SEC:.0f} с), фонів {len(bgs)}, нових предметів {len([k for k in used if k in new_props])}, попереджень {len(warns)}")
    return design


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("slug")
    ap.add_argument("--role", default="Plague Doctor")
    ap.add_argument("--series", default="")
    ap.add_argument("--facts")
    ap.add_argument("--hook", type=int, default=0)
    ap.add_argument("--step", default="all")
    ap.add_argument("--cast", default="plague")
    ap.add_argument("--hud", default="inventory")
    ap.add_argument("--grade", default="")
    ap.add_argument("--music", type=int, default=1)
    ap.add_argument("--angle", default="")
    a = ap.parse_args()
    series = a.series or f"LIFE AS A {a.role.upper()}"
    facts = Path(a.facts).read_text(encoding="utf-8") if a.facts else ""
    steps = ["hooks", "plan", "assets", "voice", "render", "package", "ship"] if a.step == "all" else [a.step]
    for st in steps:
        if st == "hooks":
            step_hooks(a.slug, a.role, facts)
        elif st == "plan":
            step_plan(a.slug, a.role, facts, series, a.hook, cast=a.cast, hud=a.hud, grade=a.grade, music=a.music, angle=a.angle)
        elif st == "assets":
            sh.step_assets(a.slug)
        elif st == "voice":
            step_voice(a.slug)
        elif st == "render":
            from . import qa_chars
            qa_chars.assert_cast(_jload(_wd(a.slug) / "design.json").get("cast", "plague"))
            step_render(a.slug)
        elif st == "package":
            sh.step_package(a.slug)
        elif st == "ship":   # стиснення в videos/<slug>/video.mp4 + перевірка перед публікацією (FAIL = не публікувати)
            from .yt import ship_check
            ship_check.finalize(a.slug)
            raise SystemExit(ship_check.main(a.slug))


if __name__ == "__main__":
    main()
