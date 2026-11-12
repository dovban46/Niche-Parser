"""Розділи (chapters) для опису YouTube: таймкоди початку кожної секції `## ...` сценарію у ГОТОВОМУ відео.
Початок секції знаходимо за першим абзацом секції серед озвучених сегментів (їхні start_ms уже відомі після
озвучки), додаємо зсув на тиху паузу перед першим словом. YouTube вимагає 0:00 першим, мінімум 3 розділи,
кожен щонайменше 10 с."""

import re

from .config import INTRO_SILENCE_SECONDS

_MIN_CHAPTER_S = 10
_INTRO_NAMES = {"introduction", "intro", "вступ"}


def _norm(text: str) -> list[str]:
    return re.findall(r"[a-zа-яіїєґ0-9']+", text.lower())


def _fmt(seconds: float) -> str:
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"


def build(script: str, segments: list[dict]) -> list[tuple[str, str]]:
    """[(таймкод, назва)] або [] якщо надійно розкласти не вдалось."""
    sections: list[tuple[str, list[str]]] = []
    title, buf = None, []
    for line in script.splitlines():
        if line.startswith("## "):
            if title is not None:
                sections.append((title, buf))
            title, buf = line[3:].strip(), []
        elif title is not None and line.strip():
            buf.append(line.strip())
    if title is not None:
        sections.append((title, buf))
    voiced = [s for s in segments if s.get("text") and s.get("start_ms") is not None]
    if len(sections) < 3 or not voiced:
        return []

    out: list[tuple[str, float]] = []
    cursor = 0
    for title, paragraphs in sections:
        head = _norm(paragraphs[0])[:6] if paragraphs else []
        found = None
        for i in range(cursor, len(voiced)):
            words = _norm(voiced[i]["text"])[:len(head)]
            if head and words == head:
                found = i
                break
        if found is None:
            continue  # секцію не вдалось прив'язати — пропускаємо, а не вгадуємо
        cursor = found
        out.append((title, voiced[found]["start_ms"] / 1000 + INTRO_SILENCE_SECONDS))
    if len(out) < 3:
        return []
    out[0] = (out[0][0], 0.0)  # YouTube: перший розділ завжди 0:00
    result, last = [], -1e9
    for title, start in out:
        if start - last < _MIN_CHAPTER_S:
            continue
        name = "Intro" if title.lower() in _INTRO_NAMES else title
        result.append((_fmt(start), name))
        last = start
    return result if len(result) >= 3 else []


def add_to_description(description: str, chapters: list[tuple[str, str]]) -> str:
    """Вставляє блок розділів перед рядком хештегів (якщо LLM його додала), інакше в кінець."""
    if not chapters:
        return description
    block = "Chapters:\n" + "\n".join(f"{ts} {name}" for ts, name in chapters)
    lines = description.rstrip().split("\n")
    if lines and lines[-1].lstrip().startswith("#"):
        return "\n".join(lines[:-1]).rstrip() + "\n\n" + block + "\n\n" + lines[-1]
    return description.rstrip() + "\n\n" + block
