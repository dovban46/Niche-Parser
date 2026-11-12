"""Режисер: сценарій → біти (1-2 с кадр) з промптом картинки, рухом камери, переходом, обведенням, підписом, SFX.
Довгі сценарії ріжуться на частини (~110 слів) і плануються паралельно; склейка перевіряється дослівно."""

import re
from concurrent.futures import ThreadPoolExecutor

from . import core

CAST = {
    "shogun": "a round-faced shogun with a black topknot, small mustache, dot eyes, wearing a purple robe with gold patterns",
    "priest": "a bald Buddhist priest with a long grey eyebrow, wearing an orange saffron robe and prayer beads",
    "guard": "a stern samurai guard in a dark navy tabard and a plumed helmet, holding a spear",
    "townsman": "a plain townsman in a brown kimono with a white headband and a worried face",
    "dog": "a small tan Shiba-like dog with a white chest and a curled tail",
    "boy": "a small child prince in a pale blue kimono with a topknot",
}
SFX_TAGS = ["x_whoosh", "x_pop", "x_ding", "x_thud", "x_sting", "x_boom", "x_riser", "x_swish", "x_tick", "x_gasp",
            "x_record_scratch", "x_magic", "distant_bell", "war_drums", "horse_gallop", "army_march", "arrow_volley",
            "battle_cry", "wall_clash", "page_turn", "quill_scratch", "stone_impact", "fire_burst", "thunder_rumble"]
CAMS = ["push", "pull", "panl", "panr", "punch", "drift_up", "drift_down", "rack", "tilt", "snap", "hand", "crane", "pop"]   # 2026-11-10: +rack/tilt/snap/hand/crane (vary.py)
CHUNK_WORDS = 110
ANIM_ENABLED = False   # рішення 2026-10-22: без мікро-анімацій (менше кадрів), лише статичні кадри


def load_cast(slug: str | None = None) -> dict:
    """Персонажі відео: storage/jp_jobs/<slug>/cast.json (ключ → опис зовнішності), інакше стандартні."""
    if slug:
        c = core.load_json(core.job_dir(slug) / "cast.json")
        if c:
            return c
    return CAST


def _system(cast: dict, first: bool) -> str:
    return f"""You are the director of a YouTube history channel about Japan. The video is a fast illustrated montage: a new picture every 1-2.5 seconds, \
cleanly synced to the narration, with camera moves, an occasional hand-drawn ring around one detail, short stamp labels and sound effects. Tone: curious, a bit mischievous, honest.

Input: one PART of the narration. Output ONLY a JSON array of beats covering this part IN ORDER, without skipping or rewording a single word.
Each beat:
{{"t": "narration words of this beat, copied exactly (3-6 words, break at natural pauses; a short punchy sentence may be 2 words)",
 "img": "ONE concrete visual in English, a different composition every beat, max 40 words, no text/numbers/signs in the picture, no gore. Describe subject, action, setting, camera distance. Do NOT describe the art style, clothes of recurring characters or the era's modern objects.",
 "cast": ["keys of characters visible, from: {', '.join(cast)}"],
 "cam": "one of {', '.join(CAMS)}",
 "focus": "L|C|R  (where the main subject is in the frame)",
 "tr": "transition INTO this beat: cut|whip|flash|zoom  (cut by default)",
 "ring": null or "the ONE small, clearly visible object to circle (max 10 words)",
 "label": null or {{"text": "1-4 words CAPS (a year, a name, a number) taken from the narration", "kind": "stamp"}},
 "sfx": null or one of {', '.join(SFX_TAGS)},
 "anim": null or {{"loop": true|false, "poses": ["pose 2", "pose 3", "pose 4"]}}}}
{'The FIRST beat also has "hook": "2-3 CAPS words, the giant opening text, e.g. HURT A DOG?" (it must not repeat the whole narration).' if first else ''}

RULES
- Use about {{N}} beats for this part. Never two beats in a row with the same subject distance, cam or composition; vary people, places, objects, maps-like wide shots, close-ups of details.
- Characters recur: use the cast keys; the code adds their fixed looks. Crowds and extras are described in img.
- ring: AT MOST 1 beat in this part, only when ONE small separated object carries the point (never a person, hand or large area); usually null.
- label: 2-4 beats in this part (years, names, numbers). sfx: only about one per 4 seconds, matching the action (x_thud heavy fact, x_sting twist, x_gasp shock, x_riser before a reveal, \
x_record_scratch reversal, war_drums/army_march/horse_gallop/battle_cry/arrow_volley/wall_clash for battles, page_turn/quill_scratch for documents). whip max 2, flash max 1, zoom max 1 in this part.
- Pictures are made by an image model that keeps one simple cartoon style: describe subject, action, setting and distance in plain words; you MAY write "no people" or "empty" when needed. Max 3 main characters per picture (crowds = tiny distant figures); avoid extreme close-ups of hands or faces; objects can be shown alone.
- anim (frame-by-frame animation of ONE short physical action): you MUST use it for at least {{A}} beats in this part (about one beat in four or five; choose the most visual actions, even small ones like walking, looking around, kneeling, pointing, carrying), whenever one character visibly does a physical action in the words (walking, marching, running, thrusting a spear, aiming and firing, falling, bowing, throwing, carrying, riding, rowing). "img" is then the FIRST pose of the action (an extreme, clear pose) and "poses" are 3 more poses of the SAME scene; each pose is ONE short phrase starting "the same character and scene, but:" and says exactly how the body and weapon positions change, with BIG differences in arms, legs, body lean and weapon (not tiny shifts). "loop": true for cycles (walk, march, run, row, carry), false for one-shot actions (thrust, shoot, fall, throw, bow). Anim beats cover 4-8 narration words (about 2-3 seconds). Never anim a crowd, a landscape or an object. Use cam push/pull/panl/panr for anim beats. All other beats: anim null.
- The picture must show what the words say at that moment (literal or a clear visual metaphor). Legend must look like a story illustration, not proof."""


def _norm(w: str) -> str:
    return re.sub(r"[^a-z0-9']", "", w.lower())


def validate(beats: list[dict], script: str) -> list[str]:
    errs = []
    want = [_norm(w) for w in core.words_of(script)]
    got = [_norm(w) for b in beats for w in core.words_of(b["t"])]
    if want != got:
        for i, (a, b) in enumerate(zip(want, got)):
            if a != b:
                errs.append(f"слова розходяться на позиції {i}: сценарій «{a}» ≠ біти «{b}»")
                break
        else:
            errs.append(f"різна кількість слів: сценарій {len(want)}, біти {len(got)}")
    return errs


def split_chunks(script: str, target: int = CHUNK_WORDS) -> list[str]:
    """Групи цілих рядків сценарію по ~target слів (межа завжди на кінці рядка = абзацу)."""
    chunks, cur, n = [], [], 0
    for line in (l.strip() for l in script.splitlines()):
        if not line:
            continue
        w = len(core.words_of(line))
        if cur and n + w > target * 1.35:
            chunks.append("\n".join(cur))
            cur, n = [], 0
        cur.append(line)
        n += w
        if n >= target:
            chunks.append("\n".join(cur))
            cur, n = [], 0
    if cur:
        chunks.append("\n".join(cur))
    return chunks


def _plan_chunk(args) -> list[dict]:
    i, text, prev_text, cast, first, secs_per_beat = args
    n_words = len(core.words_of(text))
    n_beats = max(int(n_words / (secs_per_beat * 2.5)), 6)
    system = _system(cast, first).replace("{N}", str(n_beats)).replace("{A}", str(max(round(n_beats * 0.24), 2)))
    if not ANIM_ENABLED:
        system += " - anim: ALWAYS null. Animations are disabled; every beat is ONE static picture."
    user = "NARRATION PART:\n" + text
    if prev_text:
        user += "\n\nTHE PREVIOUS PART (context only, do not cover it again):\n" + prev_text[-500:]
    feedback = ""
    for attempt in range(4):
        try:
            beats = core.ask_json(system, user + feedback, max_tokens=12000, effort="low")
            errs = validate(beats, text)
        except Exception as exc:   # битий JSON від моделі: повторюємо
            errs = [f"invalid JSON ({str(exc)[:80]})"]
        if not errs:
            return beats
        feedback = "\n\nYOUR PREVIOUS ANSWER WAS REJECTED: " + "; ".join(errs) + ". Copy the narration words exactly, in order."
    raise RuntimeError(f"частина {i}: режисер не покрив сценарій дослівно: " + "; ".join(errs))


def make(slug: str, force: bool = False, secs_per_beat: float = 2.0, workers: int = 4, log=print) -> list[dict]:
    d = core.job_dir(slug)
    out = d / "beats.json"
    if out.exists() and not force:
        return core.load_json(out)
    script = (d / "script.txt").read_text(encoding="utf-8")
    cast = load_cast(slug)
    chunks = split_chunks(script)
    jobs = [(i, c, chunks[i - 1] if i else "", cast, i == 0, secs_per_beat) for i, c in enumerate(chunks)]
    log(f"режисер: {len(chunks)} частин")
    with ThreadPoolExecutor(workers) as ex:
        parts = list(ex.map(_plan_chunk, jobs))
    beats = [b for p in parts for b in p if core.words_of(b.get("t", ""))]
    # глобальні обмеження: обведень не частіше ніж раз на ~30 с (≈ 1 на 75 слів), перший біт без переходу
    since, words = 10**9, 0
    for b in beats:
        words += len(core.words_of(b["t"]))
        since += len(core.words_of(b["t"]))
        if b.get("ring"):
            if since < 75:
                b["ring"] = None
            else:
                since = 0
    for b in beats:
        if not ANIM_ENABLED:
            b["anim"] = None
        if b.get("cam") not in CAMS:
            b["cam"] = "push"
        an = b.get("anim")
        if an and (not isinstance(an, dict) or len(an.get("poses") or []) < 2):
            b["anim"] = None
        elif an:
            an["poses"] = [str(x) for x in an["poses"][:3]]
            an["loop"] = bool(an.get("loop"))
    # анімації ≤ ~25% слів, інакше зайві стають статикою
    total_w = sum(len(core.words_of(b["t"])) for b in beats)
    used = 0
    for b in beats:
        if b.get("anim"):
            w = len(core.words_of(b["t"]))
            if used + w > total_w * 0.26:
                b["anim"] = None
            else:
                used += w
    beats[0]["tr"] = "cut"
    core.save_json(out, beats)
    log(f"біти: {len(beats)}, слів {words}")
    return beats


_ANIM_SYSTEM = """You help a director turn some static cartoon pictures into short frame-by-frame animations (3-4 poses of the same scene).
You get a numbered list of beats: narration words, picture description, characters. Choose beats where ONE character can visibly perform a physical action that matches the words \
(walking, marching, running, thrusting, aiming and firing, falling, bowing, kneeling, throwing, carrying, riding, pointing, eating, building). Skip crowds, landscapes, objects, maps, documents.
For each chosen beat return: "id", "img" (the FIRST pose of the action as one clear picture description of max 40 words, same scene as before, an extreme pose), "loop" (true for cycles like walk/march/run/carry, false for one-shot actions) \
and "poses": 3 more poses, each ONE short phrase starting "the same character and scene, but:" with BIG visible changes of arms, legs, body lean and weapon.
Reply ONLY with a JSON array of such objects, at most {N} of them, spread over the whole list."""


def add_anim(slug: str, target: float = 0.22, log=print) -> int:
    """Добирає анімаційні біти до ~target частки слів: окремий дешевий прохід по статичних бітах із людьми."""
    d = core.job_dir(slug)
    beats = core.load_json(d / "beats.json")
    total_w = sum(len(core.words_of(b["t"])) for b in beats)
    have = sum(len(core.words_of(b["t"])) for b in beats if b.get("anim"))
    need_w = int(total_w * target) - have
    if need_w <= 0:
        return 0
    cand = [i for i, b in enumerate(beats) if not b.get("anim") and b.get("cast") and not b.get("ring")]
    added = 0
    for k in range(0, len(cand), 70):
        group = cand[k:k + 70]
        lines = "\n".join(f"{i}: [{beats[i]['t']}] | {beats[i]['img']} | cast={','.join(beats[i]['cast'])}" for i in group)
        n = max(int(need_w / (len(cand) / len(group)) / 6), 3)
        try:
            res = core.ask_json(_ANIM_SYSTEM.replace("{N}", str(n)), lines, max_tokens=6000, effort="low")
        except Exception as exc:
            log(f"anim-прохід: помилка {exc}")
            continue
        for r in res:
            try:
                i = int(r["id"])
            except Exception:
                continue
            if i not in group or beats[i].get("anim") or len(r.get("poses", [])) < 2:
                continue
            w = len(core.words_of(beats[i]["t"]))
            if have + w > total_w * (target + 0.03):
                continue
            if r.get("img"):
                beats[i]["img"] = str(r["img"])
            beats[i]["anim"] = {"loop": bool(r.get("loop")), "poses": [str(x) for x in r["poses"][:3]]}
            if beats[i].get("cam") not in ("push", "pull", "panl", "panr"):
                beats[i]["cam"] = "push"
            have += w
            added += 1
    core.save_json(d / "beats.json", beats)
    log(f"anim: додано {added}, частка слів {round(100 * have / total_w)}%")
    return added
