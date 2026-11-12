"""Графічні накладки для монтажу (титул на початку, підпис-CTA), намальовані в Pillow як прозорі PNG на весь кадр.
ffmpeg лише плавно вмикає їх (fade + невеликий зсув). Так типографіка керована повністю: градієнт акцентного кольору,
розрядка літер, контур, тінь, свічення, орнаментний розділювач, затемнення під текстом для читабельності.

Колір: акцент береться з досьє теми (розділ "Accent colour"), інакше з поля accent обраного стилю — тож титул
відповідає епосі/темі (золото для середньовіччя, багряний для Риму тощо), а не є однаковим для всіх відео."""

import colorsys
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .config import OVERLAY_FONT

W, H = 1280, 720
_DEFAULT_ACCENT = (198, 149, 58)
_CREAM = (238, 232, 216)

_FONTS = "C:/Windows/Fonts/"
# (жирний заголовний, курсив для підзаголовка, звичайний); беремо перший набір, де всі файли існують
_FONT_SETS = [
    (_FONTS + "palab.ttf", _FONTS + "georgiai.ttf", _FONTS + "georgia.ttf"),
    (_FONTS + "georgiab.ttf", _FONTS + "georgiai.ttf", _FONTS + "georgia.ttf"),
    (_FONTS + "timesbd.ttf", _FONTS + "timesi.ttf", _FONTS + "times.ttf"),
    ("/System/Library/Fonts/Supplemental/Georgia Bold.ttf", "/System/Library/Fonts/Supplemental/Georgia Italic.ttf",
     "/System/Library/Fonts/Supplemental/Georgia.ttf"),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Italic.ttf",
     "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"),
]

# (дія — жирним акцентним кольором, уточнення — курсивом), мовою відео
CTA_TEXT = {
    "uk": ("ПІДПИШИСЬ НА КАНАЛ", "і постав лайк"),
    "en": ("SUBSCRIBE", "and leave a like"),
    "pl": ("SUBSKRYBUJ KANAŁ", "i zostaw łapkę w górę"),
    "de": ("KANAL ABONNIEREN", "und lass ein Like da"),
    "es": ("SUSCRÍBETE AL CANAL", "y deja tu like"),
    "it": ("ISCRIVITI AL CANALE", "e lascia un like"),
    "fr": ("ABONNE-TOI", "et laisse un like"),
}


def _font_paths() -> tuple[str, str, str] | None:
    if OVERLAY_FONT and Path(OVERLAY_FONT).is_file():
        return OVERLAY_FONT, OVERLAY_FONT, OVERLAY_FONT
    for bold, italic, regular in _FONT_SETS:
        if all(Path(p).is_file() for p in (bold, italic, regular)):
            return bold, italic, regular
    return None


def fonts_available() -> bool:
    return _font_paths() is not None


def palette(accent: str | None) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    """(світліший верх градієнта, базовий акцент). Темний акцент підсвітлюється зі збереженням відтінку й насиченості
    (багряний лишається багряним, а не рожевіє), щоб текст читався на темному тлі."""
    try:
        base = tuple(int(accent.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)) if accent else _DEFAULT_ACCENT
    except (ValueError, AttributeError):
        base = _DEFAULT_ACCENT
    h, sat, val = colorsys.rgb_to_hsv(*(c / 255 for c in base))
    base = tuple(int(c * 255) for c in colorsys.hsv_to_rgb(h, sat, max(val, 0.80)))
    top = tuple(min(255, int(c + (255 - c) * 0.5)) for c in base)
    return top, base


def _tracked_width(text: str, font: ImageFont.FreeTypeFont, tracking: int) -> int:
    return int(sum(font.getlength(ch) + tracking for ch in text) - tracking)


def _wrap(text: str, font: ImageFont.FreeTypeFont, tracking: int, max_width: int, max_lines: int) -> list[str] | None:
    """Переносить по словах так, щоб кожен рядок влазив у max_width; None — не вміщується в max_lines."""
    lines, current = [], ""
    for word in text.split():
        trial = f"{current} {word}".strip()
        if _tracked_width(trial, font, tracking) <= max_width or not current:
            current = trial
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    if len(lines) > max_lines or any(_tracked_width(l, font, tracking) > max_width for l in lines):
        return None
    return lines


def _draw_tracked(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, font, tracking: int, fill) -> None:
    x, y = xy
    for ch in text:
        draw.text((x, y), ch, font=font, fill=fill)
        x += font.getlength(ch) + tracking


def _accent_text_layer(lines: list[str], font, tracking: int, line_height: int, center_x: int, top: int,
                       colors: tuple[tuple[int, int, int], tuple[int, int, int]], left: bool = False) -> Image.Image:
    """RGBA-шар: багаторядковий текст із вертикальним градієнтом акценту, контуром, тінню й свіченням."""
    c_top, c_bottom = colors
    mask = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(mask)
    for i, line in enumerate(lines):
        width = _tracked_width(line, font, tracking)
        x = center_x if left else center_x - width // 2  # left=True: center_x це ЛІВИЙ край тексту
        _draw_tracked(d, (x, top + i * line_height), line, font, tracking, 255)

    block_h = line_height * len(lines)
    grad = Image.linear_gradient("L").resize((W, block_h + 20))
    gold = Image.composite(Image.new("RGB", grad.size, c_bottom), Image.new("RGB", grad.size, c_top), grad)
    fill = Image.new("RGB", (W, H), c_bottom)
    fill.paste(gold, (0, top - 6))

    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    glow = mask.filter(ImageFilter.GaussianBlur(14)).point(lambda v: int(v * 0.55))
    layer.paste(Image.new("RGBA", (W, H), (*c_top, 255)), (0, 0), glow)
    shadow = mask.filter(ImageFilter.GaussianBlur(5)).point(lambda v: int(v * 0.85))
    layer.paste(Image.new("RGBA", (W, H), (0, 0, 0, 255)), (4, 6), shadow)
    outline = mask.filter(ImageFilter.MaxFilter(5))  # тонкий темний контур
    layer.paste(Image.new("RGBA", (W, H), (24, 14, 8, 255)), (0, 0), outline)
    layer.paste(fill, (0, 0), mask)
    return layer


def _backdrop(center_y: int, width: int, height: int, strength: int = 150) -> Image.Image:
    """М'яке овальне затемнення під текстом — читабельність на світлих кадрах."""
    mask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(mask).ellipse((W // 2 - width, center_y - height, W // 2 + width, center_y + height), fill=strength)
    mask = mask.filter(ImageFilter.GaussianBlur(70))
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    layer.paste(Image.new("RGBA", (W, H), (0, 0, 0, 255)), (0, 0), mask)
    return layer


def _divider(layer: Image.Image, cx: int, y: int, color: tuple[int, int, int], half: int = 150) -> None:
    d = ImageDraw.Draw(layer)
    for sign in (-1, 1):  # лінії, що тонішають до країв
        for step in range(half - 16):
            alpha = int(235 * (1 - step / (half - 16)))
            x = cx + sign * (14 + step)
            d.line([(x, y), (x, y + 1)], fill=(*color, alpha), width=1)
    d.polygon([(cx, y - 7), (cx + 8, y), (cx, y + 8), (cx - 8, y)], fill=(*color, 235))
    d.polygon([(cx, y - 3), (cx + 4, y), (cx, y + 4), (cx - 4, y)], fill=(24, 14, 8, 255))


def _split_title(title: str) -> tuple[str, str]:
    for sep in (": ", " — ", " – ", " | "):
        if sep in title:
            main, sub = title.split(sep, 1)
            return main.strip(), sub.strip()
    return title.strip(), ""


def _render_lower_third(title: str, out: Path, accent: str | None) -> bool:
    """Підпис унизу ліворуч: тонка акцентна лінія, назва капсом, підзаголовок курсивом, м'яке затемнення зліва."""
    bold_path, italic_path, _ = _font_paths()
    colors = palette(accent)
    main, sub = _split_title(title)
    main = main.upper()
    lines = font = None
    tracking = 3
    for size in (60, 54, 48, 42, 38):
        f = ImageFont.truetype(bold_path, size)
        tracking = max(2, size // 16)
        wrapped = _wrap(main, f, tracking, 860, 2)
        if wrapped:
            lines, font = wrapped, f
            break
    if lines is None:
        font = ImageFont.truetype(bold_path, 36)
        tracking = 2
        lines = textwrap.wrap(main, 38)[:3]
    line_h = int(font.size * 1.16)
    sub_font = ImageFont.truetype(italic_path, 28)
    sub_lines = (_wrap(sub, sub_font, 0, 840, 2) or textwrap.wrap(sub, 62)[:2]) if sub else []
    total_h = 22 + line_h * len(lines) + (14 + 36 * len(sub_lines) if sub_lines else 0)
    left, top = 76, H - 96 - total_h

    scrim = Image.new("L", (W, H), 0)
    sd = ImageDraw.Draw(scrim)
    for x in range(0, 1000, 4):  # горизонтальний градієнт: темніше біля лівого краю
        sd.rectangle((x, top - 70, x + 4, H), fill=int(185 * (1 - x / 1000) ** 1.4))
    scrim = scrim.filter(ImageFilter.GaussianBlur(26))
    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    canvas.paste(Image.new("RGBA", (W, H), (0, 0, 0, 255)), (0, 0), scrim)
    d = ImageDraw.Draw(canvas)
    d.rectangle((left, top, left + 120, top + 4), fill=(*colors[1], 255))
    canvas.alpha_composite(_accent_text_layer(lines, font, tracking, line_h, left, top + 22, colors, left=True))
    d = ImageDraw.Draw(canvas)
    y = top + 22 + line_h * len(lines) + 12
    for line in sub_lines:
        d.text((left + 2, y + 2), line, font=sub_font, fill=(0, 0, 0, 200))
        d.text((left, y), line, font=sub_font, fill=(*_CREAM, 255))
        y += 36
    canvas.save(out, format="PNG")
    return True


def render_title_card(title: str, out: Path, accent: str | None = None, variant: str = "centered") -> bool:
    """Титульна плашка: головний заголовок великими літерами, орнамент, підзаголовок курсивом. False — немає шрифтів.
    variant="lower_third" — скромніший підпис унизу ліворуч (інший початок відео, ніж велика картка по центру)."""
    paths = _font_paths()
    if paths is None:
        return False
    if variant == "lower_third":
        return _render_lower_third(title, out, accent)
    bold_path, italic_path, _ = paths
    colors = palette(accent)
    main, sub = _split_title(title)
    main = main.upper()

    lines = font = None
    tracking = 5
    for size in (84, 76, 68, 60, 54, 48):
        f = ImageFont.truetype(bold_path, size)
        tracking = max(3, size // 14)
        wrapped = _wrap(main, f, tracking, 1040, 2)
        if wrapped:
            lines, font = wrapped, f
            break
    if lines is None:  # дуже довга назва: пишемо як є найменшим кеглем у 3 рядки
        font = ImageFont.truetype(bold_path, 44)
        tracking = 3
        lines = [l for l in textwrap.wrap(main, 34)][:3]

    line_h = int(font.size * 1.18)
    block_h = line_h * len(lines)
    sub_lines: list[str] = []
    sub_font = ImageFont.truetype(italic_path, 32)
    if sub:
        sub_lines = _wrap(sub, sub_font, 0, 980, 2) or textwrap.wrap(sub, 60)[:2]
    total_h = block_h + (40 + 42 * len(sub_lines) if sub_lines else 0)
    top = (H - total_h) // 2 - 20

    canvas = _backdrop(top + total_h // 2, 560, total_h // 2 + 90)
    canvas.alpha_composite(_accent_text_layer(lines, font, tracking, line_h, W // 2, top, colors))
    if sub_lines:
        _divider(canvas, W // 2, top + block_h + 14, colors[1])
        d = ImageDraw.Draw(canvas)
        y = top + block_h + 36
        for line in sub_lines:
            width = sub_font.getlength(line)
            d.text((W // 2 - width / 2 + 2, y + 2), line, font=sub_font, fill=(0, 0, 0, 200))  # тінь
            d.text((W // 2 - width / 2, y), line, font=sub_font, fill=(*_CREAM, 255))
            y += 42
    canvas.save(out, format="PNG")
    return True


def _bell_icon(d: ImageDraw.ImageDraw, cx: int, cy: int, size: int, fill) -> None:
    """Силует дзвіночка: купол зверху, корпус, що РОЗШИРЮЄТЬСЯ донизу (форма дзвону), ширший
    розтруб-обідок, язичок, вушко зверху. (Попередня версія звужувала корпус донизу — виходив
    кривий несиметричний блоб замість дзвону.)"""
    r = size / 2
    top = cy - r * 0.95
    dome_bottom = cy - r * 0.25
    body_bottom = cy + r * 0.65
    d.pieslice((cx - r * 0.62, top, cx + r * 0.62, top + r * 1.4), 180, 360, fill=fill)
    d.polygon(
        [(cx - r * 0.62, dome_bottom), (cx + r * 0.62, dome_bottom),
         (cx + r, body_bottom), (cx - r, body_bottom)],
        fill=fill,
    )
    d.ellipse((cx - r * 1.05, body_bottom - r * 0.18, cx + r * 1.05, body_bottom + r * 0.18), fill=fill)
    d.ellipse((cx - r * 0.14, body_bottom + r * 0.05, cx + r * 0.14, body_bottom + r * 0.32), fill=fill)
    d.rounded_rectangle((cx - r * 0.13, top - r * 0.32, cx + r * 0.13, top + r * 0.08), radius=2, fill=fill)


def render_subscribe_button(language: str, out: Path, accent: str | None = None) -> bool:
    """Кнопка-підписка (не бічна плашка з текстом): заокруглена "pill" з дзвіночком і написом, по центру
    внизу кадру — ближче до того, як подібні елементи виглядають у CapCut/готових шаблонах, і зчитується
    як кнопка, а не інформаційна панель. Пульсацію додає video_assemble (scale у часі), тут — статична
    картинка з м'яким зовнішнім світінням під пульс."""
    paths = _font_paths()
    if paths is None:
        return False
    bold_path, _, _ = paths
    c_top, c_bottom = palette(accent)
    kicker, _ = CTA_TEXT.get(language, CTA_TEXT["en"])
    font = ImageFont.truetype(bold_path, 30)
    track = 3
    icon_size = 34
    text_w = _tracked_width(kicker, font, track)
    pad_x, gap = 40, 16
    width = pad_x * 2 + icon_size + gap + text_w
    height = 64
    cx, cy = W // 2, H - 90

    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    # зовнішнє світіння (м'яке гало під пульс) + тінь під кнопкою
    glow = Image.new("L", (W, H), 0)
    ImageDraw.Draw(glow).rounded_rectangle(
        (cx - width // 2 - 10, cy - height // 2 - 10, cx + width // 2 + 10, cy + height // 2 + 10),
        radius=height // 2 + 10, fill=140,
    )
    canvas.paste(Image.new("RGBA", (W, H), (*c_bottom, 255)), (0, 0), glow.filter(ImageFilter.GaussianBlur(16)))
    shadow = Image.new("L", (W, H), 0)
    ImageDraw.Draw(shadow).rounded_rectangle(
        (cx - width // 2, cy - height // 2 + 6, cx + width // 2, cy + height // 2 + 6), radius=height // 2, fill=160,
    )
    canvas.paste(Image.new("RGBA", (W, H), (0, 0, 0, 255)), (0, 0), shadow.filter(ImageFilter.GaussianBlur(8)))

    d = ImageDraw.Draw(canvas)
    x0, y0, x1, y1 = cx - width // 2, cy - height // 2, cx + width // 2, cy + height // 2
    # градієнтна заливка кнопки акцентним кольором (як у titlecard — зверху світліше)
    fill_grad = Image.linear_gradient("L").resize((width, height))
    grad_rgb = Image.composite(Image.new("RGB", (width, height), c_top), Image.new("RGB", (width, height), c_bottom), fill_grad)
    mask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(mask).rounded_rectangle((x0, y0, x1, y1), radius=height // 2, fill=255)
    button_rgba = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    button_rgba.paste(grad_rgb, (x0, y0))
    canvas.paste(button_rgba, (0, 0), mask)
    d.rounded_rectangle((x0, y0, x1, y1), radius=height // 2, outline=(255, 255, 255, 90), width=2)

    icon_cx = x0 + pad_x
    _bell_icon(d, icon_cx, cy - 2, icon_size, (24, 14, 8, 255))
    tx = icon_cx + icon_size // 2 + gap
    _draw_tracked(d, (tx + 1, cy - font.size // 2 + 2), kicker, font, track, (0, 0, 0, 130))
    _draw_tracked(d, (tx, cy - font.size // 2), kicker, font, track, (24, 14, 8, 255))
    canvas.save(out, format="PNG")
    return True
