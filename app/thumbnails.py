"""Прев'ю (thumbnail): окремий крок від кадрів відео — інші вимоги. Кадри відео мають бути "чистими"
(без тексту, без рамки — на них рухається камера). Прев'ю навпаки: статична картинка, де рамка не
заважає, а великий текст — половина сенсу. Конвенція ніші (з аналізу живих каналів у ancient_mysteries:
Trending Tales, Bible Truth Zone та ін. — див. пам'ять проєкту project_niche_research.md): ОДИН
драматичний силует чи артефакт на простому тлі + товстий білий текст капсом із чорним контуром на
пів кадру. Це не елегантна типографіка титулу відео (overlays.py) — тут навмисно грубіше й контрастніше,
так це виглядає в конкурентів і так клікається на фіді.
"""

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .styles import Style

_EVIDENCE_RED = (214, 30, 30, 255)

W, H = 1280, 720
_FONTS = "C:/Windows/Fonts/"
# Impact/Arial Black — товстий "плакатний" шрифт клікбейт-прев'ю; НЕ той самий, що елегантний Georgia
# титулу відео (overlays.py) — навмисно різні регістри одного бренду: витончено у відео, грубо на обкладинці.
_IMPACT_CANDIDATES = [_FONTS + "impact.ttf", _FONTS + "ariblk.ttf", _FONTS + "arialbd.ttf"]


def _impact_font(size: int) -> ImageFont.FreeTypeFont | None:
    for path in _IMPACT_CANDIDATES:
        if Path(path).is_file():
            return ImageFont.truetype(path, size)
    return None


def fonts_available() -> bool:
    return _impact_font(10) is not None


def build_thumbnail_prompt(style: Style, glossary: str, subject: str) -> str:
    """Композиція під конвенцію ніші: ОДНА постать/артефакт великим планом на простому тлі — не
    захаращена сцена (як у самих кадрах відео), бо на прев'ю деталі загублені на розмірі фіда (168x94px),
    важить лише силует і контраст. Нижня третина — порожня/темна під текст."""
    parts = [style.image_prefix]
    if glossary:
        # Глосарій (anthropic_provider.py) тепер — нумерований список КІЛЬКОХ візуальних етапів усієї
        # історії, не один абзац. Для прев'ю це МАЄ лишатись довідкою про епоху/вбрання ОДНОГО предмета
        # з `subject`, інакше генератор малює весь список як панельний колаж-інфографіку з підписами-
        # галіматнею на кожній панелі (підтверджено на job 12) — рівно те, чого прев'ю по конвенції ніші
        # не повинно мати (один артефакт, просте тло, без тексту в самому зображенні).
        parts.append(
            "Background era/accuracy reference only (do NOT illustrate this list, do NOT split the image "
            "into panels or a collage, do NOT draw any of these stage labels as captions — use only "
            "whichever detail matches the single Subject below, for correct period clothing/objects):\n"
            + glossary
        )
    parts.append(f"Subject, ONE single object or figure, large and centered or slightly off-center: {subject}")
    parts.append(
        "SIMPLE, UNCLUTTERED background — plain gradient sky, mist, or a single flat wall, not a busy "
        "scene, so the subject reads instantly at tiny thumbnail size. A SINGLE continuous image, never "
        "multiple panels, insets, or a collage. Bottom third of the frame darker and emptier — negative "
        "space reserved for large text overlay (added separately, do not draw any text, letters or "
        "captions yourself anywhere in the image). The subject fills at least 40% of the frame, is clearly brighter "
        "than the background and is lit by ONE vivid accent glow in the colour named in the Subject (cyan, gold or "
        "red) while everything else stays dark and muted. Strong rim lighting or glow outlining the subject for "
        "contrast at small size. Widescreen 16:9, fills the entire frame edge-to-edge, no border, no "
        "watermark. No blood, no gore. No close-up of a face — the subject is a silhouette, seen from "
        "behind, or an object/artifact, never a literal detailed human or divine face."
    )
    return "\n".join(parts)


def _wrap_upper(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    words = text.upper().split()
    lines, current = [], ""
    for word in words:
        trial = f"{current} {word}".strip()
        if font.getlength(trial) <= max_width or not current:
            current = trial
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def render_clickbait_text(text: str, out: Path, accent: str | None = None,
                          highlight: tuple[int, int, int] | None = None) -> bool:
    """Товстий білий текст капсом із чорним контуром на нижній третині кадру — конвенція ніші, не
    елегантна типографіка overlays.render_title_card (та для відео, ця — для прев'ю)."""
    if not text.strip():
        return False
    max_width = W - 100
    size = 150
    font = lines = None
    while size >= 60:
        f = _impact_font(size)
        if f is None:
            return False
        wrapped = _wrap_upper(text, f, max_width)
        if len(wrapped) <= 3 and all(f.getlength(l) <= max_width for l in wrapped):
            font, lines = f, wrapped
            break
        size -= 8
    if font is None:
        return False

    line_h = int(size * 1.08)
    block_h = line_h * len(lines)
    bottom_margin = 56
    top = H - bottom_margin - block_h

    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    # Темна підкладка під текстом для читабельності на будь-якому фоні (крім чорного контуру самих літер).
    backdrop = Image.new("L", (W, H), 0)
    ImageDraw.Draw(backdrop).rectangle((0, top - 24, W, H), fill=130)
    canvas.paste(Image.new("RGBA", (W, H), (0, 0, 0, 255)), (0, 0), backdrop.filter(ImageFilter.GaussianBlur(30)))

    d = ImageDraw.Draw(canvas)
    stroke = max(6, size // 14)
    ivory = (250, 246, 232, 255)  # тепліший за чисто білий — менш "різко" на темних гравюрах
    for i, line in enumerate(lines):
        width = font.getlength(line)
        x, y = (W - width) / 2, top + i * line_h
        words = line.split(" ")
        last_line = i == len(lines) - 1
        for k, word in enumerate(words):
            color = (*highlight, 255) if (highlight and last_line and k == len(words) - 1) else ivory
            d.text((x, y), word, font=font, fill=color, stroke_width=stroke, stroke_fill=(0, 0, 0, 255))
            x += font.getlength(word + " ")
    canvas.save(out, format="PNG")
    return True


def add_evidence_mark(
    src: Path, out: Path, circle_center: tuple[int, int], circle_radius: tuple[int, int],
    arrow_from: tuple[int, int],
) -> None:
    """Червоне коло + стрілка на конкретну деталь кадру — перевірений прийом ніші (живі канали типу
    Velum Mysteries на цій самій темі: 67 тис. переглядів на 107 підписниках саме з таким прийомом,
    див. пам'ять project_niche_research.md). Координати підбираються вручну під конкретне згенероване
    зображення (autodetect "де саме артефакт" ненадійний), тому це окрема функція, а не крок пайплайна."""
    img = Image.open(src).convert("RGBA")
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    cx, cy = circle_center
    rx, ry = circle_radius
    bbox = (cx - rx, cy - ry, cx + rx, cy + ry)
    d.ellipse(bbox, outline=_EVIDENCE_RED, width=10)
    d.ellipse((cx - rx - 4, cy - ry - 4, cx + rx + 4, cy + ry + 4), outline=(*_EVIDENCE_RED[:3], 140), width=4)

    end = (cx + rx - 10, cy - ry + 40)
    d.line([arrow_from, end], fill=_EVIDENCE_RED, width=10)
    angle = math.atan2(end[1] - arrow_from[1], end[0] - arrow_from[0])
    head_len = 34
    for da in (-0.45, 0.45):
        hx = end[0] - head_len * math.cos(angle + da)
        hy = end[1] - head_len * math.sin(angle + da)
        d.line([end, (hx, hy)], fill=_EVIDENCE_RED, width=10)

    Image.alpha_composite(img, overlay).convert("RGB").save(out, format="PNG")
