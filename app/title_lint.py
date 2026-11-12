"""Евристичний лінтер заголовка YouTube-відео: без LLM, без мережі, чистий Python.

Адаптовано з title.py (MIT) — https://github.com/Jakeschincariol/youtube-agent-skill
(skills/yt-package). Перевіряє те, що реально ламає CTR: обрізання в desktop-пошуку (~60 симв.)
і мобільній стрічці (~40 симв.), капслок-спам, розпливчасті прикметники замість конкретики,
відсутність числа/дати/імені, порожній перед (перші слова — самі стоп-слова).

Викликається в stages/metadata_generate.py одразу після генерації title_options — сортує
варіанти за оцінкою, лишає LLM-варіанти без змін (нічого не переписує й не відкидає).
"""

import re
from dataclasses import dataclass, field

_DESKTOP_CUT = 60  # символів, де desktop-пошук обрізає заголовок
_MOBILE_CUT = 40  # символів, видимих у мобільній стрічці
_HARD_LIMIT = 100  # жорсткий ліміт YouTube

_VAGUE_WORDS = {
    "amazing", "incredible", "insane", "crazy", "huge", "massive", "ultimate", "best",
    "powerful", "secret", "revolutionary", "mindblowing", "epic", "perfect", "complete",
    "everything", "неймовірний", "неймовірно", "шокуючий", "приголомшливий", "найкращий",
    "секретний", "таємничий", "абсолютно", "грандіозний",
}
_STOP_WORDS = {
    "the", "a", "an", "of", "for", "to", "in", "on", "and", "or", "is", "are", "with",
    "your", "you", "my", "i", "this", "that", "it", "how", "what", "why",
}


def _words(text: str) -> list[str]:
    return re.findall(r"[a-zа-яїієґ0-9']+", text.lower())


@dataclass
class TitleLint:
    title: str
    chars: int
    score: int
    issues: list[tuple[str, str]] = field(default_factory=list)
    good: list[str] = field(default_factory=list)


def check(title: str, thumb: str | None = None) -> TitleLint:
    t = title.strip()
    n = len(t)
    issues: list[tuple[str, str]] = []
    good: list[str] = []

    if n > _HARD_LIMIT:
        issues.append(("length", f"{n} символів — жорсткий ліміт YouTube {_HARD_LIMIT}"))
    elif n > _DESKTOP_CUT:
        issues.append(("length", f"{n} символів — desktop-пошук обрізає біля {_DESKTOP_CUT}"))
    else:
        good.append(f"{n} символів, вкладається в desktop-обрізання ({_DESKTOP_CUT})")

    if n > _MOBILE_CUT:
        head = t[:_MOBILE_CUT].rsplit(" ", 1)[0]
        issues.append(("mobile", f'у мобільній стрічці видно приблизно "{head}..." — перевір, чи лишається суть'))

    caps = [w for w in t.split() if len(w) > 2 and w.isupper()]
    if len(caps) > 2:
        issues.append(("shouting", f"{len(caps)} слів капслоком — межа перед «схоже на спам» це два"))
    elif caps:
        good.append(f"{len(caps)} слово капслоком для акценту")

    vague = [w for w in _words(t) if w in _VAGUE_WORDS]
    if vague:
        issues.append(("vague", f"{', '.join(sorted(set(vague)))} — заміни на число, ім'я чи дату"))

    numbers = re.findall(r"\d[\d,.]*%?", t)
    if numbers:
        good.append(f"є конкретна цифра ({', '.join(numbers[:3])})")
    else:
        issues.append(("no-number", "немає числа, дати чи імені — найнадійніший окремий фікс"))

    if t.rstrip().endswith("?"):
        good.append("відкрите питання в заголовку")

    front = [w for w in _words(t)[:3] if w not in _STOP_WORDS]
    if not front:
        issues.append(("front-load", "перші три слова — самі стоп-слова, суть треба присунути на початок"))

    if thumb:
        tw, hw = set(_words(t)) - _STOP_WORDS, set(_words(thumb)) - _STOP_WORDS
        shared = tw & hw
        if shared:
            issues.append(("duplicate", f"прев'ю повторює заголовок словами {', '.join(sorted(shared))} — "
                                         "прев'ю має казати те, чого немає в заголовку"))
        else:
            good.append("прев'ю й заголовок несуть різні слова")
        thumb_words = _words(thumb)
        if len(thumb_words) > 4:
            issues.append(("thumb-length", f"{len(thumb_words)} слів на прев'ю — межа для читабельності на фіді це три"))

    score = max(0, min(100, 100 - 14 * len(issues) + 4 * len(good)))
    return TitleLint(title=t, chars=n, score=score, issues=issues, good=good)


def rank(titles: list[str], thumb: str | None = None) -> list[TitleLint]:
    """Лінтить усі варіанти й сортує від найкращого — вихідний список title_options не змінює."""
    return sorted((check(t, thumb) for t in titles), key=lambda r: -r.score)


def to_dict(result: TitleLint) -> dict:
    return {
        "title": result.title, "chars": result.chars, "score": result.score,
        "issues": [{"code": code, "message": msg} for code, msg in result.issues],
        "good": result.good,
    }
