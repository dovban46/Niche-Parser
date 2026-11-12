"""Досьє теми — поверхнева (недорога) перевірка перед сценарієм: рамка, ключові факти, сторони й їхня тактика,
теза, міфи, а також візуальний гід і список заборонених для кадру анахронізмів. Зберігається як Markdown
(storage/jobs/{id}/script/dossier.md) — автор править його на чекпоінті. Далі з нього беруться: контекст для
сценарію й редактора, візуальний глосарій для кадрів, акцентний колір титулу."""

import re
from pathlib import Path

from .storage import JobStorage

DOSSIER_FILE = "dossier.md"

# Розділи, які НЕ йдуть у промпти сценарію: англомовні технічні (для кадрів) і колір.
_NON_SCRIPT_SECTIONS = ("Visual guide", "Forbidden in visuals", "Accent colour")


def dossier_path(storage: JobStorage) -> Path:
    return storage.script_dir() / DOSSIER_FILE


def read_dossier(storage: JobStorage) -> str:
    path = dossier_path(storage)
    return path.read_text(encoding="utf-8").strip() if path.exists() else ""


def section(md: str, heading: str) -> str:
    """Тіло розділу `## <heading…>` (порівняння за початком заголовка, без урахування регістру)."""
    pattern = re.compile(rf"^##\s+{re.escape(heading)}[^\n]*\n(.*?)(?=^##\s|\Z)", re.S | re.M | re.I)
    match = pattern.search(md)
    return match.group(1).strip() if match else ""


def visual_glossary(md: str) -> str:
    """Англомовний глосарій для промптів кадрів: візуальний гід + чого в кадрі бути не може."""
    guide = section(md, "Visual guide")
    forbidden = section(md, "Forbidden in visuals")
    parts = [guide] if guide else []
    if forbidden:
        parts.append(f"Must NOT appear in any frame: {forbidden}")
    return " ".join(" ".join(parts).split())


def accent_color(md: str) -> str | None:
    match = re.search(r"#[0-9A-Fa-f]{6}\b", section(md, "Accent colour"))
    return match.group(0).upper() if match else None


def topic_needs_attention(md: str) -> bool:
    """Чи позначив аналітик тему як таку, що потребує уточнення (⚠ у розділі «Перевірка теми»)."""
    return "⚠" in section(md, "Перевірка теми")[:40]


def for_script(md: str) -> str:
    """Досьє для промптів сценарію/редактора — без технічних англомовних розділів і кольору."""
    kept = []
    for block in re.split(r"(?m)^(?=##\s)", md):
        title = block.lstrip("# ").split("\n", 1)[0].strip()
        if block.strip() and not any(title.lower().startswith(s.lower()) for s in _NON_SCRIPT_SECTIONS):
            kept.append(block.strip())
    return "\n\n".join(kept)
