"""Сценарій, факти, cast і чернетка розкадровки через Claude API (рішення користувача 2026-10-27: писати сценарій через API, щоб не витрачати токени Claude Code).

python -m app.jp.writer <slug> "<тема/кут подачі>" [--words 1650] [--story]
Результат у storage/jp_jobs/<slug>/: script.txt, facts.txt, cast.json, era.txt, beats_src.txt, writer_raw.txt.
Далі як завжди: beatsrc.compile → voice.synthesize → beatsrc.merge(slug, 3.0) → flow.export."""

import argparse
import json
import re
import sys

import anthropic

from . import core, costs

MODEL = "claude-opus-5-5"
SFX = ("x_thud x_sting x_ding x_gasp x_riser x_pop x_boom x_record_scratch x_whoosh x_swish x_tick x_boing x_tada x_gulp x_magic "
       "war_drums army_march battle_cry arrow_volley bow_draw horse_gallop fire_burst thunder_rumble distant_bell page_turn quill_scratch "
       "wall_clash stone_impact stone_door amb_wind banner_flap siege_ladder battering_ram wax_seal book_thud")

SYSTEM = """You write narrated history videos for the English YouTube channel "Japan Through Time" (real stories from Japan's past, ancient to Edo period only, US audience, mostly men 25-44).
Research the topic with web search first (prefer Wikipedia and serious sources), then write. Never invent facts in a documentary: hedge disputed claims ("according to one account", "historians still argue"). In a STORY-format video (first person), the narrator and his personal details may be invented, but every big event, date and number must be real.

Script rules:
- About {words} words, plain spoken English, short sentences, one paragraph per line, no headings, no stage directions, no lists.
- The first 2 sentences are a strong hook (a concrete shocking fact or scene), a second twist at seconds 5-9, a complete satisfying ending (no teaser for another video, no "subscribe").
- Concrete details over abstractions: objects, numbers, names, places, small human moments.
- Numbers may be digits for years (1687); otherwise words.

Storyboard rules (BEATS section): split the WHOLE script into beats in exact order; the beat texts concatenated must reproduce the script word for word (same words, same punctuation). Each beat is 6-12 words (so each picture stays about 3 seconds); the first 6 beats are shorter (2-5 words, fast hook cuts).
One beat per line in this exact format:
<exact script fragment> || <picture description in English, max 35 words> || <cast keys comma-separated or empty> || <cam> <options>
- cam is one of: push pull panl panr punch drift_up drift_down. Vary them, never the same cam 3 times in a row.
- options (semicolon-separated, optional): sfx=<one of: {sfx}> (about one per 4 beats); label=<SHORT CAPS TEXT> on beats that name a person, place, year or number (about one per 6 beats); ch=<CHAPTER TITLE IN CAPS> on the first beat of each new part (6-9 chapters, not on beat 0); tr=ink on chapter beats; keep=1 on the first 6 beats; fx=slash on 2-4 strike moments; fx=impact on one climax beat; bars=1 on consecutive beats of one tense scene (duel, raid, ambush), 10-25 beats total.
- Picture descriptions: one clear scene, at most three main characters, simple flat cartoon illustration, varied shot sizes (close-ups, wide shots, objects, maps without text). Never: text, letters, signs with writing, modern objects, wires, empty streets as the main subject, gore (show violence by silhouette or aftermath). Use cast keys for recurring characters and describe them only by key.

Reply with exactly these sections and nothing else:
=== TITLE ===
<working title, max 70 characters>
=== ERA ===
<one line, e.g. "late 17th century Edo period (1680-1709)">
=== CAST ===
<JSON object: key -> look (age, face, hair, clothes, colors), 4-9 keys, lowercase keys>
=== FACTS ===
<SOLID facts used with sources; HEDGED claims; NOT USED; then a line "Sources:" with URLs>
=== SCRIPT ===
<the script>
=== BEATS ===
<the beats>"""


def _section(text: str, name: str) -> str:
    m = re.search(rf"=== {name} ===\s*\n(.*?)(?=\n=== [A-Z]+ ===|\Z)", text, re.S)
    if not m:
        raise ValueError(f"немає розділу {name}")
    return m.group(1).strip()


def write(slug: str, topic: str, words: int = 1650, story: bool = False, log=print) -> dict:
    d = core.job_dir(slug)
    d.mkdir(parents=True, exist_ok=True)
    costs.begin(slug)
    client = anthropic.Anthropic()
    user = f"Topic and angle: {topic}\nFormat: {'STORY (first-person narrator living through it)' if story else 'documentary narration'}.\nTarget length: about {words} words."
    log(f"Claude API ({MODEL}) пише сценарій: {topic}")
    with client.messages.stream(
        model=MODEL,
        max_tokens=64000,
        system=SYSTEM.format(words=words, sfx=SFX),
        output_config={"effort": "high"},
        tools=[{"type": "web_search_20260209", "name": "web_search", "max_uses": 5}],
        messages=[{"role": "user", "content": user}],
        extra_headers={"anthropic-beta": "server-side-fallback-2026-07-01"},
        extra_body={"fallbacks": "default"},
    ) as stream:
        resp = stream.get_final_message()
    if resp.stop_reason == "refusal":
        raise RuntimeError(f"відмова моделі: {resp.stop_details}")
    if resp.stop_reason == "max_tokens":
        raise RuntimeError("відповідь обрізана (max_tokens)")
    text = "\n".join(b.text for b in resp.content if b.type == "text").strip()
    (d / "writer_raw.txt").write_text(text, encoding="utf-8")
    u = resp.usage
    from ..providers.llm import usage
    usage.usage_tracker.record(MODEL, u.input_tokens, u.output_tokens)   # costs.begin перехоплює це й пише витрати
    log(f"токени: вхід {u.input_tokens}, вихід {u.output_tokens}")
    title = _section(text, "TITLE")
    (d / "era.txt").write_text(_section(text, "ERA"), encoding="utf-8")
    cast = json.loads(re.sub(r"^```(json)?|```$", "", _section(text, "CAST").strip(), flags=re.M).strip())
    core.save_json(d / "cast.json", cast)
    (d / "facts.txt").write_text(_section(text, "FACTS") + "\n", encoding="utf-8")
    script = "\n".join(l.strip() for l in _section(text, "SCRIPT").splitlines() if l.strip())
    (d / "script.txt").write_text(script + "\n", encoding="utf-8")
    beats = [l.strip() for l in _section(text, "BEATS").splitlines() if l.count("||") == 3]
    (d / "beats_src.txt").write_text("\n".join(beats) + "\n", encoding="utf-8")
    n_words = len(core.words_of(script))
    log(f"«{title}»: {n_words} слів, бітів {len(beats)}, cast {list(cast)}")
    return {"title": title, "words": n_words, "beats": len(beats), "usage": (u.input_tokens, u.output_tokens)}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("slug")
    ap.add_argument("topic")
    ap.add_argument("--words", type=int, default=1650)
    ap.add_argument("--story", action="store_true")
    a = ap.parse_args()
    print(write(a.slug, a.topic, a.words, a.story))
