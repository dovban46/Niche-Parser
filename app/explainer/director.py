"""LLM-режисер explainer-а: (1) дизайн відео — розділи, ВЕЛИКИЙ каталог фонів/предметів/дійових осіб; (2) по розділу — біти
розкадрування (≤5 слів озвучки + візуал). Словник жорстко обмежений, відповідь валідується й виправляється кодом."""
from ..providers.llm.anthropic_provider import AnthropicLLMProvider, _extract_json
from .character import EXPRS, POSES

NL = chr(10)
HATS = ["none", "turban", "nemes", "red_crown", "white_crown", "persian_cap", "laurel", "hood", "headband", "wig"]
CAMS = ["punch", "drift", "shake"]
TRANS = ["cut", "whip", "flash", "iris", "wipe", "zoom", "slash", "ink", "glitch", "pixel", "push", "shutter", "tear", "sweep"]
ANIMS = ["pop", "bob", "none", "tilt_heavy", "balance", "chomp", "spin_in", "slam"]
SFX_OK = ["x_pop", "x_ding", "x_boing", "x_record_scratch", "x_sting", "x_magic", "x_gulp", "x_thud", "x_gasp", "x_tada",
          "x_tick", "page_turn", "quill_scratch", "book_thud", "distant_bell", "thunder_rumble", "stone_door", "torch_ignite", "wax_seal"]
WORDS_PER_SEC = 2.45

_FORMAT = """FORMAT. An animated explainer for the YouTube channel "Forbidden Folio" (niche: forbidden texts and legends of antiquity; \
ancient peoples only: Egypt, Mesopotamia, Persia, Greece, Rome, etc.). Flat cartoon style, one recurring avatar. Two modes mix freely:
 1. NARRATOR: the wise old bearded sage (actor key "sage") stands in his study (background "study") or ON LOCATION and speaks straight to the viewer; his mouth moves.
 2. SCENE: the viewer becomes the hero ("you", actor key "you") living through the events in second person, or other characters from the story act \
(extra actors); the narrator's voice continues over the scene (the actor's mouth stays closed unless he quotes a line).
 Plus PROP shots (no actor, one or two big objects/gods/creatures), ESTABLISHING shots (a place, who = null) and BIG TEXT (<=3 words) for key terms, numbers, jokes."""

_DESIGN_SYSTEM = _FORMAT + """

TASK 1: design the whole video from the dossier. Output ONLY JSON:
{"title_working": "...", "hook": "one sentence cold-open idea",
 "sections": [{"title": "<=6 words chapter title", "goal": "what this section must tell, with concrete facts to use (names, numbers, objects, steps)", "setting": "where it happens", "mode_mix": "e.g. mostly scene, some props"}],
 "backgrounds": {"key_snake_case": "english prompt of ONE EMPTY place (no people/characters/text), 12-25 words, concrete architecture/landscape, time of day"},
 "props": {"key_snake_case": {"p": "english prompt of ONE object/creature/god figure, full body, simple, 4-14 words", "float": true|false}},
 "actors": {"key": {"skin":[r,g,b],"hair":[r,g,b] or null,"beard":[r,g,b] or null,"style":"robe|kilt","robe":[r,g,b],"trim":[r,g,b],"hat":"%(hats)s","hat_color":[r,g,b],"brows":[r,g,b],"head_r":1.1}}}

Rules:
- Exactly %(n)d sections; section 1 opens with a cold-open hook, the last closes with a payoff, a short call to subscribe (never announce a next video).
- NEW BACKGROUNDS: at most %(nbg)d (reuse the library first, see below). Every place and moment of the story deserves its own truly matching, DISTINCT location: vary time of day (dawn, noon, dusk, starry night), \
interior/exterior, palette (warm sand, cool blue night, green marsh, red fire-lit, gold temple), composition and architecture. Always include "study" (cozy sage study with scrolls). \
Each background must have a clear solid GROUND/FLOOR in its lower third (a path, floor, sand, grass, stone, deck) — avoid scenes that are only water, sky or abyss; if you want a river or sea, \
make it a bank/shore/dock/boat-deck with ground in front.
- NEW PROPS: at most %(nprops)d — distinct recognisable story objects, gods, creatures, documents, tools, symbols. "float": true for things that hover/are held/small (heart, feather, amulets, sun disk, flame, scroll, \
coins, jewels), false for things that stand on the ground (statues, scales, chests, boats, thrones, altars, gates, jars, pyramids).
- ACTORS: %(nactors)d extra characters (priest, pharaoh, queen, soldier, scribe, farmer, noble, merchant, mourner...) — recognisable instantly by skin tone, clothes, hat and hair; keys "sage" and "you" already exist, do not define them.
- Be historically honest: only well-attested facts; flag uncertainty in the goal text; no invented quotes presented as real.
- Keys short english snake_case.
"""

_BEATS_SYSTEM = _FORMAT + """

TASK 2: write ONE section of the video as a list of BEATS. Each beat is one on-screen shot of <=2 seconds: its narration is 2-5 words (hard max 6). \
Concatenated, the beats' "t" fields must read as one fluent, witty, concrete, punchy English voice-over (plain words, vivid facts, jokes, rhetorical questions; \
speak to "you"; no filler; sentences may span several beats; use commas/periods inside "t" so the voice phrases naturally).

Output ONLY a JSON array of beats. Beat fields:
 t: narration text (2-5 words)
 bg: background key from the catalog (MUST match the place of the story at that moment; "study" only for narrator beats)
 who: "sage" | "you" | an extra-actor key | null (prop/establishing shot)
 pose: one of %(poses)s
 pose2: optional second pose (the gesture changes mid-beat; DIFFERENT from pose)
 expr: one of %(exprs)s
 speak: true only if the visible actor is the one talking (sage always true; "you"/others only for quoted lines)
 x: actor feet position 0.15-0.85; x2: optional end x for walk/run/sneak poses; face: 1 or -1 (optional)
 props: optional list of [prop_key, x, y, h, anim]: x 0.1-0.9, y ignored for standing props, h = height 0.25-0.6 of the frame, anim one of %(anims)s. At most 2; put them on the OTHER half from the actor.
 big: optional <=3 words CAPS (key term / number / joke) — at most one beat in four
 cam: drift | punch | shake    tr: transition INTO this beat: cut | whip | flash | iris | wipe
 sfx: optional list with at most 1 tag from %(sfx)s

STYLE RULES (strict):
- The sage is a SPICE, not the main picture: at most 12%% of the beats of this section, never more than 2 in a row, only for a joke, an aside, a "wait for it" or a summary. \
When he appears vary pose/pose2/expression and let him MOVE (walk in, point at props, lean in, whisper, laugh, cross arms). He can stand ON LOCATION in the scene's own background; "study" at most 3 beats.
- Everything else is SHOWN: dramatise with scenes — the hero "you" and the extra actors acting it out, props/gods/creatures as big picture shots, establishing shots (who = null), big text. Prefer a concrete visual to talking heads.
- SCENE LOGIC (critical): a character may only stand on solid ground. Each background in the catalog lists "ground". If a background has NO GROUND, use it only for who = null shots or props. \
Characters must never walk on water, lava, air or inside furniture. Use a background that physically fits the action (a market scene for haggling, a shore for a river crossing, a corridor for walking). \
Never repeat the same bg+who+pose in 3 consecutive beats.
- VARIETY: at least 8 different backgrounds in this section; change the background about every 3-4 beats; never more than 6 beats in a row on one background; spread x positions, alternate sides, use walking/running/sneaking/kneeling/cowering poses where the line fits.
- Props named in the narration must be on screen at that beat. Do not stack props on top of the actor.
- Transitions: "cut" for >=75%% of beats; whip/wipe/iris/flash only at changes of place (max 1 per 12 beats). cam: mostly "drift"; "punch" at most 1 beat in 10; "shake" only for impacts. sfx: about 1 per 12 beats.
- NEVER write stage directions, labels or ALL-CAPS words inside "t" (no 'BIG TEXT moment', no 'EXCLUDED'): on-screen words go ONLY in the "big" field.
- RETENTION: end every section with an open loop ("But the strangest part comes next"), pay off earlier promises on time, no section may open by recapping the previous one,
  and never spend more than 40 seconds in a row on explanation without a concrete scene, number or twist. Source honesty: name the text/verse ("1 Enoch 22", "Genesis 6") when you cite it.
- Facts accurate and concrete (numbers, names, materials, steps). Mark real uncertainty honestly ("scholars debate", "we think"). Humour yes, fabrication no.
- Quotes of ancient texts must be real or clearly framed as an imagined line.
""" % {"poses": ", ".join(POSES), "exprs": ", ".join(EXPRS), "anims": ", ".join(ANIMS), "sfx": ", ".join(SFX_OK)}


def design(llm: AnthropicLLMProvider, topic: str, dossier: str, n_sections: int, nbg: int = 14, nprops: int = 16, nactors: int = 4, log=print,
           library: dict | None = None) -> dict:
    system = _DESIGN_SYSTEM % {"hats": "|".join(HATS), "n": n_sections, "nbg": nbg, "nprops": nprops, "nactors": nactors}
    lib = library or {"bg": {}, "prop": {}}
    if lib["bg"] or lib["prop"]:
        short = lambda d: NL.join(f"  {k}: {v['p'][:70]}" for k, v in d.items())
        system += (NL + "EXISTING LIBRARY (already drawn, FREE to reuse, same flat style). REUSE these whenever the place/object fits the story; create NEW ones "
                   "only for things that are missing. Add one more JSON field \"reuse\": {\"backgrounds\": [keys], \"props\": [keys]} listing every library key "
                   "you want in this video (do NOT re-describe them in backgrounds/props). TARGET FOR VARIETY: the video must end up with at least 26 DIFFERENT backgrounds and 30 DIFFERENT props in total "
                   "(library + new) — pick generously from the library, unused library items are free, and every picked item must plausibly fit a scene of the story (symbolic/establishing shots are fine)." + NL + "LIBRARY BACKGROUNDS:" + NL + short(lib["bg"])
                   + NL + "LIBRARY PROPS:" + NL + short(lib["prop"]))
    user = f"TOPIC: {topic}{NL}{NL}DOSSIER (verified framing, facts to rely on):{NL}{dossier}"
    raw = llm._complete(system, user, 14000, effort="medium")
    data = _extract_json(raw)
    if not isinstance(data, dict) or "sections" not in data:
        raise RuntimeError("режисер: неправильний формат дизайну")
    data["fresh"] = True
    reuse = data.get("reuse") or {}
    data.setdefault("backgrounds", {})
    data.setdefault("props", {})
    reused_bg = reused_pr = 0
    for k in reuse.get("backgrounds", []):
        if k in lib["bg"] and k not in data["backgrounds"]:
            data["backgrounds"][k] = lib["bg"][k]["p"]
            reused_bg += 1
    for k in reuse.get("props", []):
        if k in lib["prop"] and k not in data["props"]:
            data["props"][k] = {"p": lib["prop"][k]["p"], "float": lib["prop"][k].get("float", False)}
            reused_pr += 1
    data["reuse_stats"] = {"bg": reused_bg, "props": reused_pr}
    return data


def catalog_text(backgrounds: dict, props: dict, actors: dict, walk: dict | None = None) -> str:
    lines = []
    for k in backgrounds:
        if walk is not None and k in walk:
            w = walk[k]
            g = "NO GROUND — who=null/props only" if not w else "ground x " + ", ".join(f"{a:.2f}-{b:.2f}" for a, b in w)
            lines.append(f"  {k} [{g}]")
        else:
            lines.append(f"  {k}")
    return ("BACKGROUNDS (use only these keys; x ranges = where characters may stand):" + NL + NL.join(lines) + NL
            + "PROP KEYS: " + ", ".join(props) + NL + "ACTOR KEYS: " + ", ".join(actors)
            + " (sage = narrator, you = the viewer as hero)")


def write_section(llm: AnthropicLLMProvider, design_data: dict, idx: int, catalog: str, dossier: str, prev_tail: list[dict],
                  target_words: int, log=print, facts: str = "", prev_text: str = "") -> list[dict]:
    sec = design_data["sections"][idx]
    n_sec = len(design_data["sections"])
    role = ""
    if idx == 0:
        role = (
            "This is the OPENING and it decides the channel's fate: ~60% of viewers leave in the first 30 seconds. HOOK RULES: "
            "(1) beat 1 = the single most startling CONCRETE claim of the source text (a named text/verse/number), <=5 words, spoken as a statement, not a question; "
            "(2) beats 2-7 escalate: who/where, what is at stake, one open question the viewer needs answered; "
            "(3) by beat ~8 promise a numbered payoff ('By the end you will know all four' / 'and the last one changes everything') and make it real later; "
            "(4) NO greeting, NO channel name, NO 'in this video', NO 'welcome', NO history lecture or definitions before the hook; "
            "(5) the first 4 shots are SCENES or props showing the claim (who = you / actor / null), NOT the sage in his study; the sage first appears after beat 8; "
            "(6) keep a new twist, number or reveal every ~15 seconds in the first minute. ")
    if idx == n_sec - 1:
        role += "This is the FINAL section: land the payoff, then a one-line call to subscribe in the sage's voice. NEVER announce or tease a next video. "
    tail = ""
    if prev_text:
        tail = NL + "EVERYTHING ALREADY SAID IN EARLIER SECTIONS (do NOT repeat any of these facts or sentences; refer back at most in a few words): " + prev_text[-6000:]
    elif prev_tail:
        tail = NL + "PREVIOUS BEATS (continue seamlessly, do not repeat): " + " | ".join(b["t"] for b in prev_tail)
    if facts:
        tail = NL + NL + "FACT SHEET (the ONLY allowed facts; do not invent others):" + NL + facts + tail
    user = (f"VIDEO: {design_data.get('title_working', '')}{NL}SECTION {idx + 1}/{n_sec}: {sec['title']}{NL}GOAL: {sec['goal']}{NL}"
            f"SETTING: {sec.get('setting', '')}{NL}MODE MIX: {sec.get('mode_mix', '')}{NL}{role}"
            f"TARGET: about {target_words} words of narration (~{round(target_words / 4.6)} beats).{NL}{NL}{catalog}{NL}{NL}"
            f"DOSSIER:{NL}{dossier[:6000]}{tail}")
    for attempt in range(3):
        raw = llm._complete(_BEATS_SYSTEM, user, 16000, effort="medium")
        try:
            data = _extract_json(raw)
        except Exception:  # noqa: BLE001
            continue
        if isinstance(data, list) and data:
            return data
    raise RuntimeError(f"режисер: розділ {idx + 1} — не JSON-список бітів")


def sanitize(beats: list[dict], backgrounds: dict, props: dict, actors: dict) -> tuple[list[dict], list[str]]:
    """Виправляє все, що модель могла вигадати поза словником; повертає (біти, попередження)."""
    warns, out = [], []
    bgs = set(backgrounds)
    default_bg = "study" if "study" in bgs else next(iter(bgs))
    prev_bg = default_bg
    for i, b in enumerate(beats):
        if not isinstance(b, dict) or not str(b.get("t", "")).strip():
            continue
        c = {"t": " ".join(str(b["t"]).split())}
        bg = b.get("bg")
        if bg not in bgs:
            warns.append(f"біт '{c['t']}': невідомий фон {bg!r} → {prev_bg}")
            bg = prev_bg
        c["bg"] = prev_bg = bg
        who = b.get("who")
        if who is not None and who not in actors:
            warns.append(f"біт '{c['t']}': невідомий актор {who!r} → null")
            who = None
        c["who"] = who
        c["pose"] = b.get("pose") if b.get("pose") in POSES else "stand"
        if who and b.get("pose2") in POSES and b.get("pose2") != c["pose"]:
            c["pose2"] = b["pose2"]
        c["expr"] = b.get("expr") if b.get("expr") in EXPRS else "neutral"
        c["speak"] = True if who == "sage" else bool(b.get("speak")) and bool(who)
        try:
            c["x"] = min(max(float(b.get("x", 0.5)), 0.12), 0.88)
            if b.get("x2") is not None:
                c["x2"] = min(max(float(b["x2"]), 0.12), 0.88)
        except (TypeError, ValueError):
            c["x"] = 0.5
        if b.get("face") in (1, -1):
            c["face"] = b["face"]
        pl = []
        for p in b.get("props") or []:
            try:
                key, px, py, ph, anim = p[0], float(p[1]), float(p[2]), float(p[3]), (p[4] if len(p) > 4 else "pop")
            except (TypeError, ValueError, IndexError):
                continue
            if key not in props:
                warns.append(f"біт '{c['t']}': невідомий предмет {key!r}")
                continue
            pl.append([key, min(max(px, 0.08), 0.92), min(max(py, 0.25), 0.7), min(max(ph, 0.2), 0.7), anim if anim in ANIMS else "pop"])
        if pl:
            c["props"] = pl[:2]
        if b.get("big"):
            c["big"] = " ".join(str(b["big"]).upper().split()[:3])
        if isinstance(b.get("emoji"), str) and 0 < len(b["emoji"].strip()) <= 4:
            c["emoji"] = b["emoji"].strip()
        if b.get("shot") in ("wide", "medium", "close", "insert"):
            c["shot"] = b["shot"]
        for k_ in ("day", "gain"):
            if isinstance(b.get(k_), str) and b[k_].strip():
                c[k_] = b[k_].strip()[:12]
        if b.get("burst"):
            c["burst"] = True
        if isinstance(b.get("stamp"), str) and b["stamp"].strip():
            c["stamp"] = b["stamp"].strip().upper()[:16]
        if isinstance(b.get("decree"), str) and b["decree"].strip():
            c["decree"] = b["decree"].strip()[:110]
        if isinstance(b.get("choice"), list) and len(b["choice"]) >= 2:
            c["choice"] = [str(x).upper()[:12] for x in b["choice"][:2]]
            c["pick"] = int(b.get("pick", 0)) if str(b.get("pick", 0)).isdigit() else 0
        if isinstance(b.get("counter"), list) and len(b["counter"]) >= 2:
            try:
                c["counter"] = [int(b["counter"][0]), int(b["counter"][1]), str(b["counter"][2]).upper()[:18] if len(b["counter"]) > 2 else ""]
            except (TypeError, ValueError):
                pass
        if b.get("circle"):
            c["circle"] = True
        if isinstance(b.get("meters"), dict):
            c["meters"] = {k: max(0, min(100, int(v))) for k, v in b["meters"].items() if k in ("loyalty", "fear") and isinstance(v, (int, float))}
        if isinstance(b.get("tilt"), (int, float)):
            c["tilt"] = max(-9.0, min(9.0, float(b["tilt"])))
        c["cam"] = b.get("cam") if b.get("cam") in CAMS else "drift"
        c["tr"] = b.get("tr") if b.get("tr") in TRANS else "cut"
        tags = [t for t in (b.get("sfx") or []) if t in SFX_OK][:1]
        if tags:
            c["sfx"] = tags
        if len(c["t"].split()) > 7:
            warns.append(f"довгий біт ({len(c['t'].split())} слів): {c['t']}")
        out.append(c)
    postprocess(out)
    return out, warns


def postprocess(beats: list[dict]) -> None:
    """Страховка від того, що модель могла проігнорувати."""
    run = 0
    for b in beats:   # не більше 2 мудреців поспіль
        run = run + 1 if b["who"] == "sage" else 0
        if run > 2:
            b["who"], b["speak"] = None, False
            b.pop("pose2", None)
            run = 0
    last_punch = -99
    for i, b in enumerate(beats):   # punch рідкісний
        if b["cam"] == "punch":
            if i - last_punch < 8:
                b["cam"] = "drift"
            else:
                last_punch = i
    last = {"wipe": -99, "whip": -99, "iris": -99, "flash": -99}   # фірмові переходи — рідкісний акцент
    gap = {"wipe": 22, "whip": 14, "iris": 20, "flash": 25}
    for i, b in enumerate(beats):
        t = b["tr"]
        if t in last:
            same_bg = i > 0 and b["bg"] == beats[i - 1]["bg"]
            if same_bg or i - last[t] < gap[t] or any(i - last[o] < 5 for o in last if last[o] > -99):
                b["tr"] = "cut"
            else:
                last[t] = i
    # не більше одного «порожнього» кадру (без героя й предметів) поспіль: другий і далі отримують героя
    poses = ["stand", "talk_a", "point_right", "think", "shrug", "idea", "present", "talk_b"]
    streak = 0
    for i, b in enumerate(beats):
        if not b.get("who") and not b.get("props"):
            streak += 1
            if streak >= 2:
                b["who"] = "sage" if b["bg"] == "study" else "you"
                b["speak"] = b["who"] == "sage"
                b["pose"], b["expr"] = poses[i % len(poses)], "neutral"
                b["x"] = 0.3 if i % 2 else 0.7
                streak = 0
        else:
            streak = 0
    for i, b in enumerate(beats[1:], 1):   # великий текст не підряд і не частіше ніж кожен 3-й біт
        if b.get("big") and any(beats[j].get("big") for j in range(max(0, i - 2), i)):
            b.pop("big")
