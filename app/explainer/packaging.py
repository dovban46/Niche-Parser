"""Пари «прев'ю + назва»: працюють як одне речення. Прев'ю дає емоцію/інтригу (2-3 слова), назва — конкретику, ставки й
ключове слово для пошуку; значущі слова між ними НЕ повторюються. Пара перевіряється кодом (лінт), а не лише промптом."""
import json
import re

from ..providers.llm.anthropic_provider import _extract_json
from .character import EXPRS, POSES

NL = chr(10)
_STOP = set("a an the of to in on at for and or but is are was were be been it its this that these those you your yours i we they he she him her "
            "his their our my me as by with from into over under up down out not no yes do does did how why what who when where which will can "
            "could would should than then so if just only more most one two three all any every here there now still ever never".split())

_SYSTEM = """You are the packaging chief of a YouTube channel about forbidden texts and legends of antiquity (animated cartoon explainer, \
a wise sage narrator, stories told to "you"). Create 3 DIFFERENT packages. A package = THUMBNAIL TEXT + TITLE + thumbnail picture spec; \
they are read as ONE sentence in the feed.

WHAT THE DATA SAYS (scan of 24 queries, EN/US, last 90 days): the only strong demand cluster in this niche is CLAIM TITLES about a named ancient text:
 - "The Book of Enoch Says 7 Abilities Were Removed From The Human Body — And One Is ..." (743k views, channel 2 months old, 4k subs)
 - "Book of Enoch and the Watchers' Plan to Take the Earth" (640k) · "The Book of Jubilees Reveals What Genesis Left Out" (65k, 430 subs)
 - "The Book of Enoch Says We Got Hell Wrong — What It Describes Is Shocking" (204k)
Generic topic titles ("Egyptian afterlife explained", "Sumerian mythology", "Dead Sea Scrolls explained") get 100-500 views. So: the TITLE is a specific
CLAIM taken from the text itself, starting with or containing the searchable name of the text/legend (Book of Enoch, Nephilim, Watchers, Jubilees, Book of the Dead...)
in the first 40 characters, plus a number or a concrete twist. Our promise is HONEST: what the text actually says, no ancient-aliens speculation,
no invented quotes — the title must be defensible from the script.
Winning thumbnails of the niche: saturated golden/warm colours, ONE big expressive subject, 1-2 words of text (e.g. "ALTERED", "THEY CAN'T COME BACK"),
high contrast. Dark muted engravings underperform.

HARD RULES
1. DIVISION OF LABOUR. Thumbnail text = emotional hook, 1-3 words CAPS (a verdict, a threat, a number). Title = the claim + searchable name + stakes.
2. NO DUPLICATION. Thumbnail text and title share NO meaningful word (ignore articles/pronouns/prepositions; same-root words count as the same).
3. Title: 45-75 characters, natural English, no ALL CAPS, at most one number, never clickbait that the script cannot back up; no "You Won't Believe".
4. Picture: ONE big expressive character (sage, hero "you" or an extra actor) + at most ONE strong object, from the catalog; the picture supports the hook.
   The sage mascot in at least one of three.
5. Three packages differ in angle (e.g. fear / curiosity / authority) and use different claims or different phrasing of the same claim.

Output ONLY JSON: {"packages": [{"thumb_text": "...", "title": "...", "alt_titles": ["...", "..."], "why": "how the pair works, one sentence",
 "visual": {"bg": key, "who": key, "expr": "%(exprs)s", "pose": "%(poses)s", "prop": key or null, "side": "left"|"right", "glow": "gold"|"cyan"|"red"}}]}
(alt_titles obey rules 2-3 against the same thumbnail text.)
""" % {"exprs": "|".join(EXPRS), "poses": "|".join(POSES)}


def _tokens(text: str) -> set[str]:
    out = set()
    for w in re.findall(r"[a-z']+", text.lower()):
        w = w.strip("'")
        if w in _STOP or len(w) < 3:
            continue
        for suf in ("ing", "ed", "es", "s", "ly"):
            if w.endswith(suf) and len(w) - len(suf) >= 4:
                w = w[: -len(suf)]
                break
        out.add(w[:6])   # грубий корінь: curse/cursed/curses → curse
    return out


def shared_words(thumb_text: str, title: str) -> set[str]:
    return _tokens(thumb_text) & _tokens(title)


def validate(pkgs: list[dict], sb: dict) -> list[str]:
    issues = []
    for i, p in enumerate(pkgs):
        t = p.get("thumb_text", "")
        if not (2 <= len(t.split()) <= 3):
            issues.append(f"пакет {i + 1}: текст прев'ю має бути 2-3 слова ('{t}')")
        for title in [p.get("title", "")] + list(p.get("alt_titles", [])):
            sh = shared_words(t, title)
            if sh:
                issues.append(f"пакет {i + 1}: збіг слів {sorted(sh)} між '{t}' і '{title}'")
            if not (35 <= len(title) <= 80):
                issues.append(f"пакет {i + 1}: довжина назви {len(title)} ('{title}')")
        v = p.get("visual", {})
        if v.get("bg") not in sb["backgrounds"] or v.get("who") not in sb["actors"]:
            issues.append(f"пакет {i + 1}: невідомий фон/актор у visual")
    return issues


def build_packages(llm, script: str, sb: dict, log=print) -> list[dict]:
    catalog = (f"BACKGROUNDS: {', '.join(sb['backgrounds'])}{NL}PROPS: {', '.join(sb['props'])}{NL}ACTORS: {', '.join(sb['actors'])}")
    user = f"VIDEO TOPIC: {sb.get('topic', '')}{NL}SECTIONS: {' | '.join(sb['sections'])}{NL}{NL}{catalog}{NL}{NL}NARRATION:{NL}{script[:7000]}"
    feedback = ""
    pkgs: list[dict] = []
    for attempt in range(3):
        raw = llm._complete(_SYSTEM, user + feedback, 3500, effort="medium")
        try:
            data = _extract_json(raw)
            pkgs = data["packages"] if isinstance(data, dict) else data
        except Exception:  # noqa: BLE001
            continue
        issues = validate(pkgs, sb)
        log(f"пакети (спроба {attempt + 1}): проблем {len(issues)}")
        if not issues:
            return pkgs
        feedback = NL + NL + "FIX THESE PROBLEMS and return the full JSON again:" + NL + NL.join(issues)
    # лишаємо лише чисті пакети; решту чистимо від альтернативних назв із збігом
    clean = []
    for p in pkgs:
        t = p.get("thumb_text", "")
        titles = [x for x in [p.get("title", "")] + list(p.get("alt_titles", [])) if x and not shared_words(t, x)]
        if titles and p.get("visual", {}).get("bg") in sb["backgrounds"] and p["visual"].get("who") in sb["actors"]:
            p["title"], p["alt_titles"] = titles[0], titles[1:]
            clean.append(p)
    return clean
