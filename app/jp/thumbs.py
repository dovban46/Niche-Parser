"""Прев'ю: базова картинка Nano Banana через fal (ключ fal, не Google) із референсами стилю відео + наш текст (Impact, жовтий з обводкою).
Правила пакування: 2-3 слова CAPS, емоція, жодного спільного змістовного слова з назвою, верх кадру вільний під текст."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

from . import core

IMPACT = "C:/Windows/Fonts/impact.ttf"
W, H = 1280, 720
YELLOW = (255, 212, 40)

_COMMON = (
    "Use EXACTLY the same flat cartoon art style as the reference pictures (thick dark ink outlines, flat colors, woodblock-print comic look, "
    "round-faced characters with dot eyes) and the same recurring characters: the shogun (round face, black topknot, small mustache and goatee, "
    "purple robe with gold pattern), the small tan Shiba-like dog, the samurai guard in a dark navy tabard. 16:9 YouTube thumbnail, very bright "
    "saturated colors, strong contrast, ONE clear focal subject, huge exaggerated facial emotions, simple background, keep the top 30% of the "
    "picture calm and uncluttered. No text, no letters, no numbers, no watermark."
)

VERSIONS = [
    {"text": "DEATH FOR THIS?", "pos": "top", "one_line": 122,
     "prompt": "A terrified townsman with a white headband freezes mid-step with a raised wooden stick, a huge smug small tan Shiba dog sits proudly on a golden cushion "
               "in front of him, two stern samurai guards with spears stand behind the dog. Comedic fear versus smugness. " + _COMMON,
     "title": "The Shogun Who Made Japan Protect Every Stray Dog"},
    {"text": "THE LIE?", "pos": "top",
     "prompt": "Split composition. Left half: dark, desaturated angry crowd of townspeople pointing fingers at a scary giant shadow of the shogun. Right half: bright warm colors, "
               "the shogun with a gentle shy smile hugging a small tan Shiba dog, sparkles around them. A big red question mark in the center between the halves. " + _COMMON,
     "title": "The Dog Shogun: What Japan Got Wrong About Tsunayoshi"},
    {"text": "HE WAS RIGHT?", "pos": "top", "one_line": 122,
     "prompt": "Extreme close-up of the shogun's face with a proud confident smirk and one raised eyebrow, glowing golden light behind him, dozens of cute tan Shiba dogs "
               "crowding behind and beside him looking at the camera. " + _COMMON,
     "title": "Japan's Dog Shogun Housed Tens of Thousands of Strays"},
]


def _font(size: int, path: str | None = None) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path or IMPACT, size)


def overlay(base: Path, text: str, out: Path, one_line: int = 0, align: str = "center", lines_override: list | None = None, size_override: int = 0, y_override: int | None = None, font_path: str | None = None) -> None:
    """font_path: інший шрифт (кирилиця в Impact вузька й погано читається: для uk брати C:/Windows/Fonts/ariblk.ttf)."""
    im = Image.open(base).convert("RGB")
    s = max(W / im.width, H / im.height)
    im = im.resize((int(im.width * s) + 1, int(im.height * s) + 1), Image.LANCZOS)
    x, y = (im.width - W) // 2, (im.height - H) // 2
    im = im.crop((x, y, x + W, y + H))
    im = ImageEnhance.Color(im).enhance(1.12)
    im = ImageEnhance.Contrast(im).enhance(1.06)
    words = text.split()
    lines = [text] if len(text) <= 11 else [" ".join(words[:max(len(words) // 2, 1)]), " ".join(words[max(len(words) // 2, 1):])]
    if one_line:
        lines = [text]
    if lines_override:
        lines = lines_override
    size = size_override or one_line or (150 if len(lines) == 1 else 132)
    f = _font(size, font_path)
    limit = W - 120 if align == "center" else int(W * 0.56)
    while max(f.getlength(l) for l in lines) > limit:
        size -= 6
        f = _font(size, font_path)
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dr = ImageDraw.Draw(layer)
    y0 = y_override if y_override is not None else (10 if one_line else 26)
    for i, l in enumerate(lines):
        tw = f.getlength(l)
        px = (W - tw) / 2 if align == "center" else (44 if align == "left" else W - tw - 44)
        pos = (px, y0 + i * (size + 4))
        dr.text((pos[0] + 6, pos[1] + 8), l, font=f, fill=(0, 0, 0, 120), stroke_width=14, stroke_fill=(0, 0, 0, 120))
        dr.text(pos, l, font=f, fill=YELLOW + (255,), stroke_width=13, stroke_fill=(20, 14, 12, 255))
    im = Image.alpha_composite(im.convert("RGBA"), layer).convert("RGB")
    im.save(out, quality=93)


def versions_for(slug: str) -> list[dict]:
    """Версії прев'ю відео: storage/jp_jobs/<slug>/thumbs.json {"refs": [...], "common": "...", "versions": [...]}, інакше стандартні."""
    cfg = core.load_json(core.job_dir(slug) / "thumbs.json")
    if not cfg:
        return VERSIONS
    common = cfg.get("common", _COMMON)
    return [{**v, "prompt": v["prompt"] + " " + common} for v in cfg["versions"]]


def make(slug: str, log=print) -> list[Path]:
    d = core.job_dir(slug)
    td = d / "thumbs"
    td.mkdir(exist_ok=True)
    cfg = core.load_json(d / "thumbs.json")
    ref_names = cfg["refs"] if cfg else ["beat_07.png", "beat_13.png", "beat_25.png"]
    refs = [d / "frames" / n for n in ref_names]
    versions = versions_for(slug)
    outs = []
    for i, v in enumerate(versions, start=1):
        base = td / f"base_{i}.png"
        if not base.exists():
            try:
                core.fal_edit(v["prompt"], refs, base)
                log(f"прев'ю {i}: Nano Banana (fal) ok")
            except Exception as exc:
                log(f"прев'ю {i}: Nano Banana недоступний ({exc}); пробую FLUX dev")
                core.fal_image(v["prompt"].replace("the same recurring characters", "characters"), base, model="fal-ai/flux/dev", size=(1344, 768))
        out = td / f"thumbnail_{i}.jpg"
        overlay(base, v["text"], out, v.get("one_line", 0), v.get("align", "center"), v.get("lines"), v.get("size", 0), v.get("y"))
        outs.append(out)
    return outs


def split_days(left: Path, right: Path, out: Path, left_text: str = "DAY 1", right_text: str = "DAY 30",
               lx: float = 0.5, rx: float = 0.5, tag: str = "") -> Path:
    """Прев'ю формату «N днів у…» як у Beanie Survives / Nobody Gets In: дві половини (ліва світла, права темна, той самий герой),
    тонка біла похила межа, зверху «DAY 1» білим і «DAY N» червоним (Impact, чорний контур); tag = необов'язкова плашка внизу праворуч.
    lx/rx: горизонтальний центр героя на вихідних кадрах (частка ширини), за ним вирізається половина."""
    W, H = 1280, 720
    half = W // 2 + 40

    def cut(path: Path, cx: float) -> Image.Image:
        im = Image.open(path).convert("RGB")
        im = im.resize((int(im.width * H / im.height), H))
        x0 = int(min(max(cx * im.width - half / 2, 0), im.width - half))
        return im.crop((x0, 0, x0 + half, H))

    a, b = cut(left, lx), cut(right, rx)
    canvas = Image.new("RGB", (W, H))
    canvas.paste(a, (0, 0))
    mask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(mask).polygon([(W // 2 + 30, 0), (W, 0), (W, H), (W // 2 - 30, H)], fill=255)
    big = Image.new("RGB", (W, H))
    big.paste(b, (W - half, 0))
    canvas.paste(big, (0, 0), mask)
    dr = ImageDraw.Draw(canvas)
    dr.line([(W // 2 + 30, 0), (W // 2 - 30, H)], fill=(255, 255, 255), width=12)
    f = _font(150)
    for text, cx, fill in ((left_text, W * 0.25, (255, 255, 255)), (right_text, W * 0.75, (225, 35, 30))):
        if not text:                     # прев'ю без тексту (рішення користувача для v03, 2026-10-27)
            continue
        tw = f.getlength(text)
        dr.text((cx - tw / 2, 14), text, font=f, fill=fill, stroke_width=10, stroke_fill=(15, 12, 10))
    if tag:
        tf = _font(54)
        tw = tf.getlength(tag)
        x1, y1 = W - 30, H - 30
        box = (x1 - tw - 44, y1 - 84, x1, y1)
        dr.rounded_rectangle((box[0] + 6, box[1] + 6, box[2] + 6, box[3] + 6), 10, fill=(0, 0, 0))
        dr.rounded_rectangle(box, 10, fill=(250, 238, 212), outline=(200, 40, 30), width=6)
        dr.text((box[0] + 22, box[1] + 10), tag, font=tf, fill=(200, 40, 30))
    canvas.save(out, quality=92)
    return out


def add_arrow(src: Path, out: Path, x0: float = 0.40, x1: float = 0.62, y: float = 0.66, color=(225, 30, 25), scale: float = 1.0) -> Path:
    """Велика червона вигнута стрілка з чорним контуром між половинами прев'ю «до → після» (частки ширини/висоти)."""
    import math
    im = Image.open(src).convert("RGB")
    W, H = im.size
    S = 3                                                   # малюємо в 3x і зменшуємо: згладжені краї
    layer = Image.new("RGBA", (W * S, H * S), (0, 0, 0, 0))
    dr = ImageDraw.Draw(layer)
    ax, bx, cy = x0 * W * S, x1 * W * S, y * H * S
    lift = 0.10 * H * S
    pts = []
    for k in range(41):
        t = k / 40
        pts.append((ax + (bx - ax) * t, cy - lift * math.sin(math.pi * t) + (0.04 * H * S) * t))
    tip = pts[-1]
    dx, dy = tip[0] - pts[-4][0], tip[1] - pts[-4][1]
    ang = math.atan2(dy, dx)
    head_len, head_w = 0.075 * W * S * scale, 0.065 * W * S * scale
    base = (tip[0] - head_len * math.cos(ang), tip[1] - head_len * math.sin(ang))
    nx, ny = -math.sin(ang), math.cos(ang)
    head = [(tip[0] + 0.25 * head_len * math.cos(ang), tip[1] + 0.25 * head_len * math.sin(ang)),
            (base[0] + nx * head_w / 2, base[1] + ny * head_w / 2), (base[0] - nx * head_w / 2, base[1] - ny * head_w / 2)]
    body = [p for p in pts if math.hypot(p[0] - tip[0], p[1] - tip[1]) > head_len * 0.8]
    wid = int(0.032 * W * S * scale)
    for col, extra in (((15, 12, 10, 255), int(0.016 * W * S * scale)), (tuple(color) + (255,), 0)):
        dr.line(body, fill=col, width=wid + extra, joint="curve")
        r = (wid + extra) / 2
        dr.ellipse((body[0][0] - r, body[0][1] - r, body[0][0] + r, body[0][1] + r), fill=col)
        if extra:
            cx_ = sum(p[0] for p in head) / 3
            cy_ = sum(p[1] for p in head) / 3
            grow = [(cx_ + (px - cx_) * 1.18, cy_ + (py - cy_) * 1.18) for px, py in head]
            dr.polygon(grow, fill=col)
        else:
            dr.polygon(head, fill=col)
    layer = layer.resize((W, H), Image.LANCZOS)
    im.paste(layer, (0, 0), layer)
    im.save(out, quality=93)
    return out
