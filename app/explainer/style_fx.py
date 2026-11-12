"""Варіанти оформлення Shorts (щоб кожне відео виглядало інакше): HUD, плашка назви серії, прогрес-бар, кнопки «лайк/підписка», переходи, колір-ґрейди.
Вибір комбінації на відео — style_kit.pick(); тут лише малювання."""
import math
import random

import cv2
import numpy as np
from PIL import Image, ImageDraw

from . import short_fx as fx
from .render import GOLD, H, OUTLINE, W, YELLOW, _emoji_img, _font, ease_out, ease_out_back, smooth

RED = fx.RED
_DARK = (30, 22, 24, 230)


# ---------- назва серії ----------
def draw_title(ov: Image.Image, d: ImageDraw.ImageDraw, title: str, kind: str = "pill") -> None:
    if not title:
        return
    if kind == "plate":
        return draw_title_plate(ov, d, title)
    if kind == "tab":
        return draw_title_tab(ov, d, title)
    if kind == "ribbon":
        return draw_title_ribbon(ov, d, title)
    f = _font(44)
    tw = d.textlength(title, font=f)
    x0, y0 = 54, 100
    if kind == "tape":   # жовта малярна стрічка під нахилом
        layer = Image.new("RGBA", (int(tw) + 120, 110), (0, 0, 0, 0))
        ld = ImageDraw.Draw(layer)
        ld.rectangle((8, 20, layer.width - 8, 86), fill=(255, 214, 54, 255), outline=(*OUTLINE, 255), width=5)
        for i in range(0, layer.width, 36):
            ld.line((i, 20, i + 18, 86), fill=(235, 190, 30, 255), width=6)
        ld.text((60, 72), title, font=f, fill=(*OUTLINE, 255), anchor="ls")
        layer = layer.rotate(2.5, expand=True, resample=Image.BICUBIC)
        ov.alpha_composite(layer, (x0 - 20, y0 - 20))
    elif kind == "plain":   # просто білий напис із товстим контуром
        d.text((x0, y0 + 56), title, font=f, fill=(255, 255, 255, 255), stroke_width=8, stroke_fill=(*OUTLINE, 255), anchor="ls")
    else:
        d.rounded_rectangle((x0 - 6, y0 - 4, x0 + tw + 44, y0 + 70), radius=30, fill=(0, 0, 0, 70))
        d.rounded_rectangle((x0, y0, x0 + tw + 38, y0 + 64), radius=30, fill=(255, 255, 255, 255), outline=(*OUTLINE, 255), width=5)
        d.text((x0 + 19, y0 + 54), title, font=f, fill=(*OUTLINE, 255), anchor="ls")


# ---------- HUD зі значеннями ----------
def _vals(vals: dict, prev: dict, age: float, names: dict | None):
    q = smooth(min(age / 0.45, 1.0))
    out = []
    for key, col in (("loyalty", GOLD), ("fear", RED)):
        if key not in vals:
            continue
        v0, v1 = prev.get(key, vals[key]), vals[key]
        out.append(((names or {}).get(key, key.upper()), v0 + (v1 - v0) * q, col))
    return out


def _heart(d, cx, cy, r, fill, edge=(*OUTLINE, 255)) -> None:
    for off, col in ((5, edge), (0, fill)):
        rr = r + off
        d.ellipse((cx - rr, cy - rr * 0.95, cx + 0.05 * rr, cy + rr * 0.1), fill=col)
        d.ellipse((cx - 0.05 * rr, cy - rr * 0.95, cx + rr, cy + rr * 0.1), fill=col)
        d.polygon([(cx - rr * 0.97, cy - rr * 0.22), (cx + rr * 0.97, cy - rr * 0.22), (cx, cy + rr * 1.12)], fill=col)


def draw_hud_values(kind: str, d: ImageDraw.ImageDraw, vals: dict, prev: dict, age: float, names: dict | None) -> None:
    if kind == "tactical":
        return draw_hud_tactical(d, vals, prev, age, names)
    items = _vals(vals, prev, age, names)
    if not items:
        return
    if kind == "hearts":
        for n, (label, v, col) in enumerate(items):
            y = 250 + n * 118
            d.text((60, y - 34), label, font=_font(30), fill=(255, 255, 255, 255), stroke_width=6, stroke_fill=(*OUTLINE, 255), anchor="ls")
            if n == 0:
                for i in range(5):
                    on = v >= (i + 0.5) * 20
                    _heart(d, 96 + i * 82, y + 14, 30, (232, 44, 62, 255) if on else (70, 52, 58, 255))
            else:
                for i in range(10):
                    on = v >= (i + 0.5) * 10
                    d.rounded_rectangle((60 + i * 44, y - 4, 60 + i * 44 + 34, y + 40), radius=8, fill=(*col, 255) if on else _DARK, outline=(*OUTLINE, 255), width=4)
    elif kind == "dots":
        for n, (label, v, col) in enumerate(items):
            y = 236 + n * 66
            d.text((60, y + 14), label, font=_font(30), fill=(255, 255, 255, 255), stroke_width=6, stroke_fill=(*OUTLINE, 255), anchor="lm")
            for i in range(10):
                on = v >= (i + 0.5) * 10
                cx = 330 + i * 48
                d.ellipse((cx - 19, y - 5, cx + 19, y + 33), fill=(*col, 255) if on else _DARK, outline=(*OUTLINE, 255), width=4)
    elif kind == "thermo":
        top, bot = 250, 640
        for n, (label, v, col) in enumerate(items):
            x = 78 + n * 110
            d.rounded_rectangle((x - 24, top, x + 24, bot), radius=24, fill=_DARK, outline=(*OUTLINE, 255), width=5)
            fh = int((bot - top - 16) * max(min(v, 100), 0) / 100)
            d.rounded_rectangle((x - 17, bot - 8 - fh, x + 17, bot - 8), radius=17, fill=(*col, 255))
            d.ellipse((x - 44, bot - 6, x + 44, bot + 82), fill=(*col, 255), outline=(*OUTLINE, 255), width=5)
            d.text((x, bot + 118), label, font=_font(26), fill=(255, 255, 255, 255), stroke_width=6, stroke_fill=(*OUTLINE, 255), anchor="mm")
    elif kind == "rings":
        for n, (label, v, col) in enumerate(items):
            cx, cy, r = 120 + n * 200, 330, 70
            d.arc((cx - r, cy - r, cx + r, cy + r), 0, 360, fill=(30, 22, 24, 220), width=26)
            d.arc((cx - r, cy - r, cx + r, cy + r), -90, -90 + 360 * max(min(v, 100), 0.5) / 100, fill=(*col, 255), width=26)
            d.text((cx, cy + 2), f"{int(round(v))}", font=_font(46), fill=(255, 255, 255, 255), stroke_width=7, stroke_fill=(*OUTLINE, 255), anchor="mm")
            d.text((cx, cy + r + 44), label, font=_font(28), fill=(255, 255, 255, 255), stroke_width=6, stroke_fill=(*OUTLINE, 255), anchor="mm")


# ---------- прогрес-бар ----------
def draw_progress(d: ImageDraw.ImageDraw, kind: str, frac: float, t: float) -> None:
    y = 76
    if kind == "sword":
        x0, x1 = 60, W - 60
        d.line((x0, y, x1, y), fill=(246, 214, 130, 70), width=5)
        hx = x0 + (x1 - x0) * frac
        d.line((x0, y, hx, y), fill=(246, 214, 130, 235), width=5)
        d.polygon([(hx + 34, y), (hx + 4, y - 7), (hx + 4, y + 7)], fill=(236, 238, 242, 255))
        d.line((hx + 2, y - 15, hx + 2, y + 15), fill=(214, 168, 64, 255), width=6)
        d.line((hx - 20, y, hx + 2, y), fill=(120, 76, 36, 255), width=6)
    elif kind == "dash":
        x0, x1 = 60, W - 60
        n = 36
        for i in range(n):
            xa = x0 + (x1 - x0) * i / n
            on = (i + 0.5) / n <= frac
            d.line((xa, y, xa + (x1 - x0) / n * 0.62, y), fill=(246, 240, 224, 235) if on else (246, 240, 224, 70), width=6)
        hx = x0 + (x1 - x0) * frac
        d.polygon([(hx + 16, y), (hx - 10, y - 10), (hx - 10, y + 10)], fill=(214, 60, 52, 255))
    elif kind == "thin":
        d.rectangle((60, 69, W - 60, 72), fill=(255, 255, 255, 60))
        d.rectangle((60, 69, 60 + max(6, int((W - 120) * frac)), 72), fill=(214, 168, 64, 235))
    elif kind == "fuse":
        x0, x1 = 60, W - 60
        head = x0 + (x1 - x0) * frac
        d.line((head, y, x1, y), fill=(214, 190, 140, 235), width=9)
        d.line((x0, y, head, y), fill=(60, 50, 48, 235), width=9)
        rnd = random.Random(int(t * 24))
        for i in range(9):
            a = i * 40 + rnd.uniform(0, 30)
            ln = rnd.uniform(14, 34)
            d.line((head, y, head + ln * math.cos(math.radians(a)), y + ln * math.sin(math.radians(a))), fill=(255, 176 + rnd.randint(0, 60), 40, 255), width=5)
        d.ellipse((head - 10, y - 10, head + 10, y + 10), fill=(255, 240, 150, 255))
    elif kind == "segments":
        n, gap = 14, 8
        sw = (W - 120 - gap * (n - 1)) / n
        for i in range(n):
            x = 60 + i * (sw + gap)
            fill_ = frac * n - i
            d.rounded_rectangle((x, y - 8, x + sw, y + 8), radius=6, fill=(0, 0, 0, 120))
            if fill_ > 0:
                d.rounded_rectangle((x, y - 8, x + sw * min(fill_, 1.0), y + 8), radius=6, fill=(*GOLD, 255))
    else:
        d.rounded_rectangle((60, 70, W - 60, 82), radius=6, fill=(0, 0, 0, 110))
        d.rounded_rectangle((60, 70, 60 + max(12, int((W - 120) * frac)), 82), radius=6, fill=(*GOLD, 255))


# ---------- «лайк / підписка» ----------
def _paste(ov: Image.Image, lay: Image.Image, fade: float, top: int, left: int = 0) -> None:
    if fade < 1.0:
        lay.putalpha(lay.getchannel("A").point(lambda v: int(v * fade)))
    ov.alpha_composite(lay, (left, top))


def _emo(ch: str, size: int):
    return fx._emoji_plain(ch, size)


def cta_bell(ov, d, age: float, total: float = 2.6) -> None:
    pin = ease_out_back(min(age / 0.35, 1.0), 1.8)
    fade = 1.0 if age < total - 0.3 else max((total - age) / 0.3, 0.0)
    lay = Image.new("RGBA", (W, 330), (0, 0, 0, 0))
    ld = ImageDraw.Draw(lay)
    sx = int((1 - min(pin, 1.0)) * 700)
    ld.rounded_rectangle((60 + sx + 6, 60 + 8, 760 + sx + 6, 240 + 8), radius=50, fill=(0, 0, 0, 110))
    ld.rounded_rectangle((60 + sx, 60, 760 + sx, 240), radius=50, fill=(255, 255, 255, 255), outline=(*OUTLINE, 255), width=7)
    ld.polygon([(740 + sx, 130), (820 + sx, 180), (740 + sx, 210)], fill=(255, 255, 255, 255), outline=(*OUTLINE, 255))
    ld.text((410 + sx, 118), "LIKE &", font=_font(60), fill=(*OUTLINE, 255), anchor="mm")
    ld.text((410 + sx, 186), "SUBSCRIBE", font=_font(66), fill=(206, 34, 46, 255), anchor="mm")
    ang = 28 * math.sin(max(age - 0.4, 0) * 15) * math.exp(-max(age - 0.4, 0) / 0.9)
    bell = _emo("🔔", 170)
    if bell is not None:
        b2 = bell.rotate(ang, resample=Image.BICUBIC, expand=True)
        lay.alpha_composite(b2, (int(890 + sx - b2.width / 2), int(160 - b2.height / 2)))
    if 0.4 < age < 1.6:
        q = (age - 0.4) / 1.2
        r = 80 + 120 * q
        ld.ellipse((890 + sx - r, 160 - r, 890 + sx + r, 160 + r), outline=(255, 214, 54, int(220 * (1 - q))), width=6)
    _paste(ov, lay, fade, int(H * 0.79) - 150)


def cta_pow(ov, d, age: float, total: float = 2.6) -> None:
    fade = 1.0 if age < total - 0.3 else max((total - age) / 0.3, 0.0)
    lay = Image.new("RGBA", (W, 360), (0, 0, 0, 0))
    ld = ImageDraw.Draw(lay)
    sc = 0.2 + 0.8 * ease_out_back(min(age / 0.3, 1.0), 2.4)
    cx, cy = 260, 180
    pts = []
    for i in range(24):
        r = (170 if i % 2 == 0 else 112) * sc
        a = math.radians(i * 15 + age * 25)
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    ld.polygon(pts, fill=(255, 222, 48, 255), outline=(206, 34, 46, 255), width=8)
    star = Image.new("RGBA", (360, 160), (0, 0, 0, 0))
    ImageDraw.Draw(star).text((180, 80), "LIKE!", font=_font(int(100 * sc)), fill=(*OUTLINE, 255), anchor="mm")
    star = star.rotate(8, resample=Image.BICUBIC, expand=True)
    lay.alpha_composite(star, (int(cx - star.width / 2), int(cy - star.height / 2)))
    if age > 0.9:
        q = smooth(min((age - 0.9) / 0.3, 1.0))
        x0 = int(W + 40 - q * (W - 400))
        ld.polygon([(x0, 150), (x0 + 520, 150), (x0 + 580, 220), (x0 + 520, 290), (x0, 290)], fill=(206, 34, 46, 255), outline=(*OUTLINE, 255))
        ld.text((x0 + 250, 222), "SUBSCRIBE", font=_font(72), fill=(255, 255, 255, 255), stroke_width=5, stroke_fill=(*OUTLINE, 255), anchor="mm")
        bell = _emo("🔔", 110)
        if bell is not None:
            b2 = bell.rotate(24 * math.sin((age - 0.9) * 16) * math.exp(-(age - 0.9) / 0.8), resample=Image.BICUBIC, expand=True)
            lay.alpha_composite(b2, (int(x0 + 520 - b2.width / 2), int(150 - b2.height / 2)))
    _paste(ov, lay, fade, int(H * 0.77) - 140)


_STRIP: dict = {}


def _strip(unit: int = 560) -> Image.Image:
    im = _STRIP.get(unit)
    if im is None:
        n = 6
        im = Image.new("RGBA", (unit * n, 100), (0, 0, 0, 0))
        dd = ImageDraw.Draw(im)
        for i in range(n):
            x = i * unit
            lk, bl = _emo("👍", 64), _emo("🔔", 64)
            if i % 2 == 0:
                if lk is not None:
                    im.alpha_composite(lk, (x + 10, 18))
                dd.text((x + 96, 50), "LIKE", font=_font(58), fill=(255, 255, 255, 255), anchor="lm")
            else:
                if bl is not None:
                    im.alpha_composite(bl, (x + 10, 18))
                dd.text((x + 96, 50), "SUBSCRIBE", font=_font(58), fill=(255, 214, 54, 255), anchor="lm")
        _STRIP[unit] = im
    return im


def cta_ticker(ov, d, age: float, total: float = 2.8) -> None:
    slide = smooth(min(age / 0.25, 1.0)) * (1.0 if age < total - 0.25 else max((total - age) / 0.25, 0.0))
    if slide <= 0.01:
        return
    y = int(H * 0.80) + int((1 - slide) * 200)
    lay = Image.new("RGBA", (W, 130), (0, 0, 0, 0))
    ld = ImageDraw.Draw(lay)
    ld.rectangle((0, 12, W, 118), fill=(18, 18, 24, 240))
    ld.rectangle((0, 12, W, 22), fill=(206, 34, 46, 255))
    ld.rectangle((0, 108, W, 118), fill=(206, 34, 46, 255))
    strip = _strip()
    off = int(age * 560) % (560 * 2)
    row = Image.new("RGBA", (W, 100), (0, 0, 0, 0))
    for k in range(-1, 4):
        row.alpha_composite(strip.crop((0, 0, 560 * 2, 100)), (k * 1120 - off, 0)) if -1120 < k * 1120 - off < W else None
    lay.alpha_composite(row, (0, 18))
    ov.alpha_composite(lay, (0, y))


def cta_cursor(ov, d, age: float, total: float = 2.8) -> None:
    pin = ease_out_back(min(age / 0.3, 1.0), 1.6)
    fade = 1.0 if age < total - 0.3 else max((total - age) / 0.3, 0.0)
    lay = Image.new("RGBA", (W, 330), (0, 0, 0, 0))
    ld = ImageDraw.Draw(lay)
    done = age > 1.45
    bx0, by0, bw, bh = 240, 110, 600, 130
    sc = max(pin, 0.05)
    cxm, cym = bx0 + bw / 2, by0 + bh / 2
    box = (cxm - bw / 2 * sc, cym - bh / 2 * sc, cxm + bw / 2 * sc, cym + bh / 2 * sc)
    ld.rounded_rectangle((box[0] + 6, box[1] + 8, box[2] + 6, box[3] + 8), radius=65, fill=(0, 0, 0, 110))
    ld.rounded_rectangle(box, radius=65, fill=(88, 88, 96, 255) if done else (230, 30, 40, 255), outline=(*OUTLINE, 255), width=6)
    ld.text((cxm + 36, cym + 4), "Subscribed" if done else "Subscribe", font=_font(int(66 * sc)), fill=(255, 255, 255, 255), anchor="mm")
    bell = _emo("🔔", 84)
    if bell is not None and sc > 0.5:
        b2 = bell.rotate(26 * math.sin(max(age - 1.45, 0) * 18) * math.exp(-max(age - 1.45, 0) / 0.7) if done else 0, resample=Image.BICUBIC, expand=True)
        lay.alpha_composite(b2, (int(bx0 + 60 - b2.width / 2), int(cym - b2.height / 2)))
    # курсор їде до кнопки, клік на 1.35 с
    q = smooth(min(max((age - 0.35) / 1.0, 0.0), 1.0))
    mx, my = 40 + (cxm + 120 - 40) * q, 30 + (cym + 30 - 30) * q
    s = 1.8 * (0.82 if 1.3 < age < 1.5 else 1.0)
    cur = [(0, 0), (0, 38), (10, 29), (17, 44), (24, 41), (17, 26), (31, 26)]
    ld.polygon([(mx + x * s, my + y * s) for x, y in cur], fill=(255, 255, 255, 255), outline=(*OUTLINE, 255))
    if 1.35 < age < 1.95:
        r = (age - 1.35) / 0.6
        ld.ellipse((mx - 20 - 90 * r, my - 20 - 90 * r, mx + 20 + 90 * r, my + 20 + 90 * r), outline=(255, 255, 255, int(230 * (1 - r))), width=6)
    _paste(ov, lay, fade, int(H * 0.79) - 120)


CTAS = {"bell": cta_bell, "pow": cta_pow, "ticker": cta_ticker, "cursor": cta_cursor}


# ---------- переходи ----------
def glitch_transition(a: np.ndarray, b: np.ndarray, p: float, seed: int = 0) -> np.ndarray:
    base = (a if p < 0.5 else b).copy()
    w = 1 - abs(2 * p - 1)
    rnd = random.Random(int(p * 40) + seed * 7)
    for _ in range(7):
        y0 = rnd.randint(0, H - 80)
        hh = rnd.randint(30, 180)
        dx = int(rnd.uniform(-1, 1) * 140 * w)
        base[y0: y0 + hh] = np.roll(base[y0: y0 + hh], dx, axis=1)
    return fx.chroma_ab(base, 6 + 22 * w)


def pixel_transition(a: np.ndarray, b: np.ndarray, p: float) -> np.ndarray:
    base = a if p < 0.5 else b
    w = 1 - abs(2 * p - 1)
    blk = 4 + int(w * 70)
    small = cv2.resize(base, (max(W // blk, 2), max(H // blk, 2)), interpolation=cv2.INTER_AREA)
    return cv2.resize(small, (W, H), interpolation=cv2.INTER_NEAREST)


def push_transition(a: np.ndarray, b: np.ndarray, p: float) -> np.ndarray:
    off = int(smooth(p) * H)
    canvas = np.concatenate([a, b], axis=0)[off: off + H]
    return canvas


# ---------- колір-ґрейди ----------
def grade_warm(f: np.ndarray) -> np.ndarray:
    return fx.vignette(np.clip(f.astype(np.float32) * np.array([1.07, 1.0, 0.86], np.float32), 0, 255).astype(np.uint8), 0.35)


def grade_cool(f: np.ndarray) -> np.ndarray:
    return fx.vignette(np.clip(f.astype(np.float32) * np.array([0.88, 0.99, 1.1], np.float32), 0, 255).astype(np.uint8), 0.35)


def grade_vhs(f: np.ndarray, t: float) -> np.ndarray:
    out = fx.chroma_ab(f, 3).astype(np.float32)
    out[::3] *= 0.82
    rnd = np.random.RandomState(int(t * 24) % 997)
    out += rnd.normal(0, 7, out.shape[:2])[..., None]
    band = int((t * 160) % H)
    out[band: band + 14] = np.roll(out[band: band + 14], 14, axis=1)
    return np.clip(out, 0, 255).astype(np.uint8)


# ================= «Серйозний» набір (військові/історичні теми) =================
_MONO: dict = {}


def _mono(size: int):
    from PIL import ImageFont
    f = _MONO.get(size)
    if f is None:
        f = _MONO[size] = ImageFont.truetype("C:/Windows/Fonts/consolab.ttf", size)
    return f


def draw_title_plate(ov, d, title: str) -> None:
    """Тонка напівпрозора планка з оливковою смугою й моноширинним написом (як у документальних титрах)."""
    if not title:
        return
    f = _mono(30)
    tw = d.textlength(title.upper(), font=f)
    x0, y0 = 54, 104
    d.rectangle((x0, y0, x0 + tw + 46, y0 + 52), fill=(10, 12, 10, 175))
    d.rectangle((x0, y0, x0 + 8, y0 + 52), fill=(138, 154, 92, 255))
    d.text((x0 + 26, y0 + 36), title.upper(), font=f, fill=(236, 236, 226, 255), anchor="ls")


def draw_hud_tactical(d: ImageDraw.ImageDraw, vals: dict, prev: dict, age: float, names: dict | None) -> None:
    items = _vals(vals, prev, age, names)
    for n, (label, v, col) in enumerate(items):
        y = 190 + n * 62
        x0, w = 54, 380
        d.text((x0, y + 20), label.upper(), font=_mono(24), fill=(226, 226, 214, 255), anchor="ls")
        bx = x0 + 190
        d.rectangle((bx, y + 2, bx + w - 190, y + 24), outline=(226, 226, 214, 210), width=2)
        fill_w = int((w - 190 - 6) * max(min(v, 100), 0) / 100)
        accent = (214, 168, 64, 255) if n == 0 else (200, 84, 64, 255)
        d.rectangle((bx + 3, y + 5, bx + 3 + fill_w, y + 21), fill=accent)
        d.text((bx + w - 190 + 14, y + 22), f"{int(round(v)):02d}", font=_mono(22), fill=(226, 226, 214, 230), anchor="ls")


def cta_lower(ov, d, age: float, total: float = 2.8) -> None:
    """Спокійна нижня плашка «як на телебаченні»: виїжджає зліва, тримається, виїжджає назад."""
    t_in = smooth(min(age / 0.4, 1.0))
    t_out = smooth(min(max((age - (total - 0.4)) / 0.4, 0.0), 1.0))
    off = int((1 - t_in + t_out) * -700)
    lay = Image.new("RGBA", (W, 140), (0, 0, 0, 0))
    ld = ImageDraw.Draw(lay)
    ld.rectangle((0 + off, 14, 700 + off, 126), fill=(10, 12, 10, 220))
    ld.rectangle((0 + off, 14, 14 + off, 126), fill=(196, 40, 40, 255))
    ld.text((50 + off, 62), "SUBSCRIBE", font=_mono(46), fill=(240, 240, 230, 255), anchor="ls")
    ld.text((50 + off, 104), "LIKE  |  NOTIFICATIONS ON", font=_mono(26), fill=(200, 200, 188, 255), anchor="ls")
    lk = _emo("👍", 44)
    if lk is not None:
        lay.alpha_composite(lk, (int(610 + off), 50))
    ov.alpha_composite(lay, (0, int(H * 0.79)))


CTAS["lower"] = cta_lower


def grade_film(f: np.ndarray, t: float) -> np.ndarray:
    """Плівка: приглушені кольори, м'який контраст, зерно, виражена віньєтка."""
    x = f.astype(np.float32)
    g = x.mean(axis=2, keepdims=True)
    x = g + (x - g) * 0.62
    x = (x - 128) * 1.08 + 128
    x *= np.array([1.03, 1.0, 0.94], np.float32)
    rnd = np.random.RandomState(int(t * 24) % 991)
    x += rnd.normal(0, 5.5, x.shape[:2])[..., None]
    return fx.vignette(np.clip(x, 0, 255).astype(np.uint8), 0.55)


# ================= Сучасна військова естетика: нічне бачення, тепловізор, фідер дрона =================
def look_nvg(f: np.ndarray, t: float) -> np.ndarray:
    """Нічне бачення: яскравість → зелена гама, шум, скан-лінії, круглий «тубус»."""
    g = cv2.cvtColor(f, cv2.COLOR_RGB2GRAY).astype(np.float32)
    g = np.clip((g - 20) * 1.5 + 30, 0, 255)
    rnd = np.random.RandomState(int(t * 30) % 977)
    g += rnd.normal(0, 14, g.shape)
    g[::4] *= 0.86
    out = np.stack([g * 0.28, g * 1.0, g * 0.34], axis=2)
    h, w = g.shape
    yy, xx = np.ogrid[:h, :w]
    rr = np.sqrt(((xx - w / 2) / (w * 0.62)) ** 2 + ((yy - h / 2) / (h * 0.46)) ** 2)
    mask = np.clip(1.35 - rr, 0.0, 1.0) ** 0.8
    return np.clip(out * mask[..., None], 0, 255).astype(np.uint8)


def look_thermal(f: np.ndarray, t: float) -> np.ndarray:
    """Тепловізор: сіра яскравість → палітра INFERNO (світле = гаряче), шум і легкі смуги."""
    g = cv2.cvtColor(f, cv2.COLOR_RGB2GRAY)
    g = cv2.GaussianBlur(g, (0, 0), 1.6)
    g = cv2.normalize(g, None, 20, 255, cv2.NORM_MINMAX)
    rnd = np.random.RandomState(int(t * 24) % 983)
    g = np.clip(g.astype(np.float32) + rnd.normal(0, 7, g.shape), 0, 255).astype(np.uint8)
    col = cv2.applyColorMap(g, cv2.COLORMAP_INFERNO)[..., ::-1]
    col[::3] = (col[::3] * 0.9).astype(np.uint8)
    return col


def draw_feed(d: ImageDraw.ImageDraw, t: float, name: str = "UAV-2") -> None:
    """Екранний фідер: кутові рамки, REC, таймкод, умовна висота/швидкість (без прицілу)."""
    c = (235, 235, 225, 210)
    m, L = 64, 70
    for sx, sy in ((m, 150), (W - m, 150), (m, H - 330), (W - m, H - 330)):
        dx = L if sx < W / 2 else -L
        dy = L if sy < H / 2 else -L
        d.line((sx, sy, sx + dx, sy), fill=c, width=5)
        d.line((sx, sy, sx, sy + dy), fill=c, width=5)
    if int(t * 2) % 2 == 0:
        d.ellipse((W - 250, 168, W - 226, 192), fill=(220, 40, 40, 255))
    d.text((W - 214, 190), "REC", font=_mono(30), fill=c, anchor="ls")
    sec = int(t * 1.0) + 4 * 60 + 12
    d.text((m + 8, 210), f"{name}  04:{sec // 60 % 60:02d}:{sec % 60:02d}", font=_mono(26), fill=c, anchor="ls")
    d.text((m + 8, H - 346), f"ALT {1180 + int(t * 7):,} FT   SPD 48 KT", font=_mono(24), fill=c, anchor="ls")


def cta_lower_r(ov, d, age: float, total: float = 2.8) -> None:
    """Те саме нижня плашка, але справа (інший вигляд для різних відео)."""
    t_in = smooth(min(age / 0.4, 1.0))
    t_out = smooth(min(max((age - (total - 0.4)) / 0.4, 0.0), 1.0))
    off = int((1 - t_in + t_out) * 760)
    lay = Image.new("RGBA", (W, 140), (0, 0, 0, 0))
    ld = ImageDraw.Draw(lay)
    x0 = W - 640
    ld.rectangle((x0 + off, 14, W + off, 126), fill=(12, 12, 10, 222))
    ld.rectangle((W - 12 + off, 14, W + off, 126), fill=(196, 40, 40, 255))
    ld.text((x0 + 36 + off, 64), "SUBSCRIBE", font=_mono(44), fill=(240, 236, 224, 255), anchor="ls")
    ld.text((x0 + 36 + off, 104), "FOR MORE HISTORY  |  LIKE", font=_mono(25), fill=(196, 192, 180, 255), anchor="ls")
    ov.alpha_composite(lay, (0, int(H * 0.79)))


CTAS["lower_r"] = cta_lower_r


def grade_sepia(f: np.ndarray, t: float) -> np.ndarray:
    """Сепія: теплий коричневий тон, виражена віньєтка, зерно, ледь помітне мерехтіння."""
    g = cv2.cvtColor(f, cv2.COLOR_RGB2GRAY).astype(np.float32)
    g = (g - 128) * 1.1 + 128
    flick = 1.0 + 0.04 * np.sin(t * 17) + 0.02 * np.sin(t * 41)
    out = np.stack([g * 1.06, g * 0.93, g * 0.74], axis=2) * flick
    rnd = np.random.RandomState(int(t * 24) % 991)
    out += rnd.normal(0, 7, g.shape)[..., None]
    return fx.vignette(np.clip(out, 0, 255).astype(np.uint8), 0.6)


def look_oldfilm(f: np.ndarray, t: float) -> np.ndarray:
    """Архівна плівка: чорно-біле з жовтизною, вертикальні подряпини, крапки, дрижання кадру."""
    g = cv2.cvtColor(f, cv2.COLOR_RGB2GRAY).astype(np.float32)
    g = (g - 110) * 1.25 + 120
    rnd = np.random.RandomState(int(t * 24) % 983)
    g += rnd.normal(0, 12, g.shape)
    h, w = g.shape
    for _ in range(4):
        x = rnd.randint(0, w)
        g[:, x: x + 2] += rnd.uniform(25, 60)
    for _ in range(18):
        y, x = rnd.randint(0, h), rnd.randint(0, w)
        g[y: y + 4, x: x + 4] = rnd.choice([20, 235])
    out = np.stack([g * 1.0, g * 0.95, g * 0.82], axis=2)
    dx, dy = rnd.randint(-3, 4), rnd.randint(-3, 4)
    out = np.roll(np.roll(out, dx, axis=1), dy, axis=0)
    return fx.vignette(np.clip(out, 0, 255).astype(np.uint8), 0.65)



# ================= «Секретне досьє»: ярлик папки, липкий папірець =================
def draw_title_tab(ov, d, title: str) -> None:
    """Ярличок картонної папки у верхньому лівому куті: «FILE: …» друкарським шрифтом."""
    if not title:
        return
    f = ImageFont_courier(30)
    tw = d.textlength(title.upper(), font=f)
    x0, y0 = 54, 104
    d.polygon([(x0, y0 + 56), (x0 + 14, y0), (x0 + tw + 56, y0), (x0 + tw + 74, y0 + 56)], fill=(214, 184, 120, 255), outline=(60, 44, 24, 255))
    d.text((x0 + 36, y0 + 40), title.upper(), font=f, fill=(46, 34, 20, 255), anchor="ls")


def ImageFont_courier(size: int):
    from PIL import ImageFont
    return ImageFont.truetype("C:/Windows/Fonts/courbd.ttf", size)


def cta_postit(ov, d, age: float, total: float = 2.8) -> None:
    """Жовтий липкий папірець шльопається на кадр: рукописне «LIKE + SUBSCRIBE», галочка домальовується, пін угорі."""
    from PIL import ImageFont
    pin = ease_out_back(min(age / 0.28, 1.0), 2.0)
    fade = 1.0 if age < total - 0.3 else max((total - age) / 0.3, 0.0)
    if pin <= 0.02:
        return
    n = 460
    lay = Image.new("RGBA", (n + 40, n + 40), (0, 0, 0, 0))
    ld = ImageDraw.Draw(lay)
    ld.rectangle((26, 30, n + 6, n + 10), fill=(0, 0, 0, 90))
    ld.rectangle((16, 16, n - 4, n - 4), fill=(255, 226, 92, 255))
    ld.polygon([(n - 80, n - 4), (n - 4, n - 84), (n - 4, n - 4)], fill=(236, 200, 60, 255))
    f1, f2 = ImageFont.truetype("C:/Windows/Fonts/Inkfree.ttf", 86), ImageFont.truetype("C:/Windows/Fonts/Inkfree.ttf", 58)
    ld.text((n // 2, 120), "Like", font=f1, fill=(40, 36, 30, 255), anchor="mm")
    ld.text((n // 2, 200), "+ Subscribe", font=f1, fill=(176, 30, 30, 255), anchor="mm")
    p = smooth(min(max((age - 0.45) / 0.5, 0.0), 1.0))
    if p > 0:
        pts = [(100, 330), (170, 392), (340, 262)]
        total_len = math.dist(pts[0], pts[1]) + math.dist(pts[1], pts[2])
        run = p * total_len
        L1 = math.dist(pts[0], pts[1])
        seg1 = min(run, L1) / L1
        ld.line((pts[0], (pts[0][0] + (pts[1][0] - pts[0][0]) * seg1, pts[0][1] + (pts[1][1] - pts[0][1]) * seg1)), fill=(30, 120, 60, 255), width=16)
        if run > L1:
            seg2 = (run - L1) / math.dist(pts[1], pts[2])
            ld.line((pts[1], (pts[1][0] + (pts[2][0] - pts[1][0]) * seg2, pts[1][1] + (pts[2][1] - pts[1][1]) * seg2)), fill=(30, 120, 60, 255), width=16)
    ld.ellipse((n // 2 - 22, 4, n // 2 + 22, 48), fill=(196, 40, 40, 255), outline=(60, 10, 10, 255), width=4)
    lay = lay.rotate(-6 + (1 - min(pin, 1.0)) * 14, resample=Image.BICUBIC, expand=True)
    sc = max(min(pin, 1.15), 0.05)
    lay = lay.resize((int(lay.width * sc), int(lay.height * sc)), Image.BILINEAR)
    lay.putalpha(lay.getchannel("A").point(lambda v: int(v * fade)))
    ov.alpha_composite(lay, (int(W - lay.width - 40), int(H * 0.50)))


CTAS["postit"] = cta_postit


# ================= «Геральдика»: стрічка-титул, сувій із воском, меч у прогресі =================
def _serif(size: int):
    from PIL import ImageFont
    return ImageFont.truetype("C:/Windows/Fonts/georgiab.ttf", size)


def draw_title_ribbon(ov, d, title: str) -> None:
    """Малинова стрічка з вирізами на кінцях і золотим написом."""
    if not title:
        return
    f = _serif(34)
    tw = d.textlength(title.upper(), font=f)
    x0, y0, h = 60, 102, 64
    x1 = x0 + tw + 80
    d.polygon([(x0 - 26, y0), (x0 + 12, y0), (x1 - 12, y0), (x1 + 26, y0), (x1 + 6, y0 + h / 2), (x1 + 26, y0 + h), (x1 - 12, y0 + h), (x0 + 12, y0 + h), (x0 - 26, y0 + h), (x0 - 6, y0 + h / 2)],
              fill=(150, 26, 40, 255), outline=(236, 196, 96, 255))
    d.text((x0 + 40, y0 + h - 18), title.upper(), font=f, fill=(246, 214, 130, 255), anchor="ls")


def cta_scroll(ov, d, age: float, total: float = 2.8) -> None:
    """Сувій розгортається від держака, напис «SUBSCRIBE», потім воскова печатка шльопається в куті."""
    fade = 1.0 if age < total - 0.3 else max((total - age) / 0.3, 0.0)
    open_p = smooth(min(age / 0.45, 1.0))
    wsc, hsc = 760, 220
    lay = Image.new("RGBA", (wsc + 140, hsc + 140), (0, 0, 0, 0))
    ld = ImageDraw.Draw(lay)
    cx = (wsc + 140) / 2
    half = wsc / 2 * open_p
    ld.rectangle((cx - half + 10, 76, cx + half + 10, 76 + hsc), fill=(0, 0, 0, 90))
    ld.rectangle((cx - half, 70, cx + half, 70 + hsc), fill=(232, 214, 170, 255), outline=(120, 84, 40, 255), width=5)
    for sx in (-1, 1):
        ld.rounded_rectangle((cx + sx * half - 16, 52, cx + sx * half + 16, 90 + hsc), radius=14, fill=(120, 76, 36, 255), outline=(60, 34, 14, 255), width=4)
    if open_p > 0.85:
        ld.text((cx, 70 + hsc / 2 - 14), "SUBSCRIBE", font=_serif(86), fill=(110, 24, 30, 255), anchor="mm")
        ld.text((cx, 70 + hsc / 2 + 56), "FOR MORE BATTLES", font=_serif(36), fill=(70, 50, 28, 255), anchor="mm")
    if age > 1.2:
        q = ease_out_back(min((age - 1.2) / 0.22, 1.0), 2.4)
        r = int(58 * max(q, 0.05))
        sx0, sy0 = cx + wsc / 2 - 40, 70 + hsc - 6
        ld.ellipse((sx0 - r, sy0 - r, sx0 + r, sy0 + r), fill=(160, 24, 30, 255), outline=(96, 12, 16, 255), width=5)
        ld.ellipse((sx0 - r * 0.66, sy0 - r * 0.66, sx0 + r * 0.66, sy0 + r * 0.66), outline=(214, 70, 70, 255), width=3)
        ld.text((sx0, sy0), "★", font=_serif(int(54 * max(q, 0.05))), fill=(236, 120, 110, 255), anchor="mm")
    lay.putalpha(lay.getchannel("A").point(lambda v: int(v * fade)))
    ov.alpha_composite(lay, (int(W / 2 - lay.width / 2), int(H * 0.775) - 70))


CTAS["scroll"] = cta_scroll



# ================= «Флот»: хук-текст, жетон, кільватер, радіограма, радарна розгортка =================
def draw_hook(ov, d, text: str, age: float, total: float = 1.9) -> None:
    """Величезний хук-текст на нульовому кадрі (до 3 рядків, видно перші ~1.9 с): впадає зверху, тримається, зникає."""
    if age < 0 or age > total:
        return
    from .render import _font
    lines = [l for l in text.upper().split("|")] if "|" in text else text.upper().split(" ")
    if "|" not in text and len(lines) > 3:
        half = (len(lines) + 1) // 2
        lines = [" ".join(lines[:half]), " ".join(lines[half:])]
    fade = 1.0 if age < total - 0.3 else max((total - age) / 0.3, 0.0)
    drop = (1.0 - min(ease_out_back(min(age / 0.22, 1.0), 1.8), 1.0)) * -260
    size = 150
    f = _font(size)
    wmax = max(d.textlength(l, font=f) for l in lines)
    if wmax > W * 0.9:
        size = int(size * W * 0.9 / wmax)
        f = _font(size)
    y = int(H * 0.17 + drop)
    lay = Image.new("RGBA", (W, int(len(lines) * size * 1.12) + 80), (0, 0, 0, 0))
    ld = ImageDraw.Draw(lay)
    for i, l in enumerate(lines):
        cy = 40 + i * size * 1.12 + size / 2
        ld.text((W / 2 + 6, cy + 8), l, font=f, fill=(0, 0, 0, 170), anchor="mm", stroke_width=14, stroke_fill=(0, 0, 0, 170))
        ld.text((W / 2, cy), l, font=f, fill=(250, 246, 232, 255), anchor="mm", stroke_width=12, stroke_fill=(10, 10, 12, 255))
        if i == len(lines) - 1:
            ld.rectangle((W / 2 - 150, cy + size * 0.56, W / 2 + 150, cy + size * 0.56 + 12), fill=(206, 34, 46, 255))
    lay.putalpha(lay.getchannel("A").point(lambda v: int(v * fade)))
    ov.alpha_composite(lay, (0, y))


def draw_title_dogtag(ov, d, title: str) -> None:
    """Металевий жетон з ланцюжком у верхньому лівому куті."""
    if not title:
        return
    f = ImageFont_courier(28)
    tw = d.textlength(title.upper(), font=f)
    x0, y0, h = 66, 96, 70
    d.line((x0 - 6, y0 + 4, x0 - 36, y0 - 40), fill=(170, 172, 178, 255), width=5)
    d.rounded_rectangle((x0 + 5, y0 + 6, x0 + tw + 96, y0 + h + 6), radius=24, fill=(0, 0, 0, 110))
    d.rounded_rectangle((x0, y0, x0 + tw + 90, y0 + h), radius=24, fill=(188, 192, 198, 255), outline=(96, 100, 108, 255), width=4)
    d.ellipse((x0 + 14, y0 + h / 2 - 8, x0 + 30, y0 + h / 2 + 8), fill=(40, 44, 50, 255), outline=(96, 100, 108, 255), width=3)
    d.text((x0 + 50, y0 + h / 2 + 10), title.upper(), font=f, fill=(34, 38, 44, 255), anchor="ls")


_old_title = draw_title


def draw_title(ov, d, title: str, kind: str = "pill") -> None:   # noqa: F811
    if kind == "dogtag":
        return draw_title_dogtag(ov, d, title)
    if kind == "line":
        return draw_title_line(ov, d, title)
    return _old_title(ov, d, title, kind)


_old_progress = draw_progress


def draw_progress(d, kind: str, frac: float, t: float) -> None:   # noqa: F811
    if kind == "wake":
        x0, x1, y = 60, W - 60, 78
        d.line((x0, y, x1, y), fill=(120, 170, 200, 60), width=4)
        hx = x0 + (x1 - x0) * frac
        for k in range(26):   # піна кільватера
            xx = hx - 18 - k * 20
            if xx < x0:
                break
            d.ellipse((xx - 4, y - 3 + math.sin(t * 6 + k) * 3, xx + 4, y + 5 + math.sin(t * 6 + k) * 3), fill=(236, 244, 250, max(40, 230 - k * 9)))
        d.polygon([(hx - 40, y + 4), (hx + 26, y + 4), (hx + 40, y - 8), (hx - 30, y - 8)], fill=(176, 184, 192, 255))
        d.rectangle((hx - 14, y - 20, hx + 8, y - 8), fill=(150, 158, 166, 255))
        d.line((hx - 2, y - 32, hx - 2, y - 20), fill=(150, 158, 166, 255), width=3)
        return
    return _old_progress(d, kind, frac, t)


def cta_radiogram(ov, d, age: float, total: float = 2.9) -> None:
    """Радіограма виїжджає справа: чорна шапка, друкований текст «STOP LIKE STOP SUBSCRIBE STOP», штамп RECEIVED."""
    t_in = smooth(min(age / 0.35, 1.0))
    t_out = smooth(min(max((age - (total - 0.35)) / 0.35, 0.0), 1.0))
    off = int((1 - t_in + t_out) * 900)
    lay = Image.new("RGBA", (W, 330), (0, 0, 0, 0))
    ld = ImageDraw.Draw(lay)
    x0 = 90 + off
    ld.rectangle((x0 + 8, 24, x0 + 908, 318), fill=(0, 0, 0, 100))
    ld.rectangle((x0, 16, x0 + 900, 306), fill=(236, 226, 190, 255), outline=(120, 100, 60, 255), width=4)
    ld.rectangle((x0, 16, x0 + 900, 80), fill=(20, 20, 20, 255))
    ld.text((x0 + 36, 62), "RADIOGRAM", font=ImageFont_courier(44), fill=(236, 226, 190, 255), anchor="ls")
    n = int(len("LIKE  STOP") + min(max(age - 0.3, 0.0) * 22, 40))
    full = ["STOP LIKE STOP", "SUBSCRIBE STOP"]
    left = n
    y = 160
    for ln in full:
        seg = ln[:max(left, 0)]
        ld.text((x0 + 36, y), seg, font=ImageFont_courier(58), fill=(30, 26, 20, 255), anchor="ls")
        left -= len(ln)
        y += 80
    if age > 1.3:
        q = ease_out_back(min((age - 1.3) / 0.2, 1.0), 2.2)
        r = max(q, 0.05)
        st = Image.new("RGBA", (360, 120), (0, 0, 0, 0))
        sd = ImageDraw.Draw(st)
        sd.rounded_rectangle((6, 6, 354, 114), radius=14, outline=(190, 30, 36, 255), width=7)
        sd.text((180, 62), "RECEIVED", font=ImageFont_courier(50), fill=(190, 30, 36, 255), anchor="mm")
        st = st.rotate(-8, expand=True, resample=Image.BICUBIC).resize((int(st.width * r), int(st.height * r)))
        lay.alpha_composite(st, (x0 + 520, 150))
    ov.alpha_composite(lay, (0, int(H * 0.755)))


CTAS["radiogram"] = cta_radiogram


def sweep_transition(a: np.ndarray, b: np.ndarray, p: float) -> np.ndarray:
    """Радарна розгортка: кут від центру відкриває кадр B, на межі — світла лінія."""
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    ang = (np.arctan2(yy - H / 2, xx - W / 2) + math.pi / 2) % (2 * math.pi)
    cur = p * 2 * math.pi
    m = ang < cur
    out = np.where(m[..., None], b, a)
    edge = (np.abs(ang - cur) < 0.05)[..., None]
    return np.where(edge, np.array([170, 255, 190], np.uint8), out).astype(np.uint8)



# ================= «Постер»: дуотон, силует, капсула CTA, титул-лінія, таймер =================
PALETTES = {
    "duo_red": [(8, 10, 22), (192, 46, 42), (250, 232, 196)],
    "duo_teal": [(6, 16, 24), (32, 126, 134), (242, 226, 192)],
    "duo_gold": [(14, 10, 6), (198, 128, 36), (250, 236, 192)],
}


def grade_duotone(f: np.ndarray, name: str) -> np.ndarray:
    """Градієнтна карта по яскравості: тіні → середній колір → світла. Один фірмовий колір на все (фото, діаграми, персонажі)."""
    pal = np.array(PALETTES.get(name, PALETTES["duo_red"]), np.float32)
    g = cv2.cvtColor(f, cv2.COLOR_RGB2GRAY).astype(np.float32) / 255.0
    g = np.clip((g - 0.04) * 1.12, 0, 1)
    lo = np.clip(g * 2.0, 0, 1)[..., None]
    hi = np.clip(g * 2.0 - 1.0, 0, 1)[..., None]
    out = pal[0] * (1 - lo) + pal[1] * lo
    out = out * (1 - hi) + pal[2] * hi
    return fx.vignette(np.clip(out, 0, 255).astype(np.uint8), 0.45)


def sprite_silhouette(img: Image.Image) -> Image.Image:
    """Стиль «силует»: темна заливка з приглушеними деталями й світлою крайовою підсвіткою (персонаж як вирізка у кадрі)."""
    arr = np.asarray(img.convert("RGBA")).astype(np.float32)
    a = arr[..., 3] / 255.0
    lum = (arr[..., 0] * 0.3 + arr[..., 1] * 0.59 + arr[..., 2] * 0.11) / 255.0
    base = 16 + (lum - 0.5) * 46
    rgb = np.stack([base, base + 2, base + 6], axis=2)
    alpha8 = (a > 0.5).astype(np.uint8)
    er = cv2.erode(alpha8, np.ones((7, 7), np.uint8))
    edge = (alpha8 - er).astype(np.float32)
    h, w = edge.shape
    yy, xx = np.mgrid[0:h, 0:w]
    side = np.clip(1.0 - xx / max(w, 1), 0.0, 1.0) * 0.8 + 0.2   # сильніше з лівого боку (джерело світла)
    rim = (edge * side)[..., None]
    rgb = rgb * (1 - rim) + np.array([236, 214, 170], np.float32) * rim
    out = np.dstack([np.clip(rgb, 0, 255), arr[..., 3]]).astype(np.uint8)
    return Image.fromarray(out, "RGBA")


def draw_title_line(ov, d, title: str) -> None:
    """Мінімальний титул: тонка червона лінія та спеціальний напис малими капітелями без плашки."""
    if not title:
        return
    f = _serif(30)
    d.text((64, 128), title.upper(), font=f, fill=(246, 240, 226, 255), anchor="ls")
    tw = d.textlength(title.upper(), font=f)
    d.rectangle((64, 138, 64 + tw, 143), fill=(212, 52, 44, 255))


def draw_progress_player(d, frac: float, t: float, total: float) -> None:
    """Прогрес як у плеєрі: тонка лінія та таймкод «0:07 / 0:28» праворуч."""
    d.rectangle((60, 70, W - 60, 74), fill=(255, 255, 255, 60))
    d.rectangle((60, 70, 60 + max(6, int((W - 120) * frac)), 74), fill=(212, 52, 44, 255))
    cur = int(t)
    tot = int(total)
    d.text((W - 60, 112), f"{cur // 60}:{cur % 60:02d} / {tot // 60}:{tot % 60:02d}", font=ImageFont_courier(26), fill=(246, 240, 226, 220), anchor="rs")


def cta_capsule(ov, d, age: float, total: float = 2.8) -> None:
    """Темна капсула знизу по центру: дзвіночок хитається, кільце заповнюється, червона кнопка перетворюється на «SUBSCRIBED»."""
    pin = ease_out_back(min(age / 0.3, 1.0), 1.7)
    fade = 1.0 if age < total - 0.3 else max((total - age) / 0.3, 0.0)
    if pin <= 0.02:
        return
    lay = Image.new("RGBA", (W, 200), (0, 0, 0, 0))
    ld = ImageDraw.Draw(lay)
    w0, h0 = 740, 120
    cx, cy = W / 2, 100
    s = max(min(pin, 1.1), 0.05)
    ld.rounded_rectangle((cx - w0 / 2 * s, cy - h0 / 2 * s, cx + w0 / 2 * s, cy + h0 / 2 * s), radius=60, fill=(16, 16, 20, 235), outline=(255, 255, 255, 80), width=3)
    done = age > 1.5
    bell = _emo("🔔", int(64 * s))
    if bell is not None:
        ang = 24 * math.sin(max(age - 0.35, 0) * 17) * math.exp(-max(age - 0.35, 0) / 0.8)
        b2 = bell.rotate(ang, resample=Image.BICUBIC, expand=True)
        lay.alpha_composite(b2, (int(cx - w0 / 2 * s + 34), int(cy - b2.height / 2)))
    p = smooth(min(max((age - 0.5) / 0.9, 0.0), 1.0))
    ld.arc((cx - w0 / 2 * s + 118, cy - 26, cx - w0 / 2 * s + 170, cy + 26), -90, -90 + 360 * p, fill=(212, 52, 44, 255), width=7)
    ld.text((cx - 20, cy + 2), "SUBSCRIBED" if done else "Follow for more true stories", font=ImageFont_courier(40 if not done else 44), fill=(246, 240, 226, 255), anchor="mm")
    if done:
        ld.ellipse((cx + w0 / 2 * s - 94, cy - 30, cx + w0 / 2 * s - 34, cy + 30), fill=(46, 160, 90, 255))
        ld.line((cx + w0 / 2 * s - 80, cy + 2, cx + w0 / 2 * s - 66, cy + 16, cx + w0 / 2 * s - 46, cy - 14), fill=(255, 255, 255, 255), width=8)
    lay.putalpha(lay.getchannel("A").point(lambda v: int(v * fade)))
    ov.alpha_composite(lay, (0, int(H * 0.77)))


CTAS["capsule"] = cta_capsule


# ================= «Креслення» (BLUEPRINT): синій дуотон, табличка зі стенсилем, заклепки замість прогресу, наряд-замовлення CTA =================
PALETTES["duo_blue"] = [(4, 12, 30), (28, 88, 150), (214, 236, 250)]
_CY = (120, 214, 255, 255)


def draw_title_stencil(ov, d, title: str) -> None:
    """Сталева табличка із заклепками й циановим трафаретним написом у верхньому лівому куті."""
    if not title:
        return
    f = ImageFont_courier(30)
    tw = d.textlength(title.upper(), font=f)
    x0, y0, h = 60, 92, 72
    x1 = x0 + tw + 86
    d.rectangle((x0 + 5, y0 + 6, x1 + 5, y0 + h + 6), fill=(0, 0, 0, 110))
    d.rectangle((x0, y0, x1, y0 + h), fill=(10, 30, 54, 240), outline=_CY, width=3)
    for rx in (x0 + 14, x1 - 14):
        for ry in (y0 + 14, y0 + h - 14):
            d.ellipse((rx - 5, ry - 5, rx + 5, ry + 5), fill=(120, 150, 176, 255), outline=(20, 40, 60, 255), width=2)
    d.text((x0 + 43, y0 + h / 2 + 11), title.upper(), font=f, fill=_CY, anchor="ls")


def draw_progress_rivets(d, frac: float, t: float) -> None:
    """Шов обшивки: ряд заклепок, що по одній «нагріваються» до циану."""
    n = 28
    x0, x1, y = 70, W - 70, 80
    d.line((x0 - 10, y, x1 + 10, y), fill=(120, 150, 176, 70), width=3)
    on = int(n * frac)
    for i in range(n):
        cx = x0 + (x1 - x0) * i / (n - 1)
        if i < on:
            col, rim = _CY, (20, 60, 90, 255)
        elif i == on:
            pulse = 0.5 + 0.5 * math.sin(t * 9)
            col, rim = (int(120 + 100 * pulse), int(214 + 20 * pulse), 255, 255), (20, 60, 90, 255)
        else:
            col, rim = (96, 116, 136, 190), (20, 30, 44, 255)
        d.ellipse((cx - 8, y - 8, cx + 8, y + 8), fill=col, outline=rim, width=2)


def cta_workorder(ov, d, age: float, total: float = 2.9) -> None:
    """Наряд-замовлення виїжджає знизу: пункти LIKE і SUBSCRIBE по черзі відмічаються галочкою, штамп APPROVED."""
    t_in = smooth(min(age / 0.35, 1.0))
    t_out = smooth(min(max((age - (total - 0.35)) / 0.35, 0.0), 1.0))
    off = int((1 - t_in + t_out) * 420)
    lay = Image.new("RGBA", (W, 330), (0, 0, 0, 0))
    ld = ImageDraw.Draw(lay)
    x0 = 120
    y0 = 14 + off
    ld.rectangle((x0 + 8, y0 + 8, x0 + 848, y0 + 300), fill=(0, 0, 0, 100))
    ld.rectangle((x0, y0, x0 + 840, y0 + 292), fill=(10, 30, 54, 245), outline=_CY, width=4)
    ld.rectangle((x0, y0, x0 + 840, y0 + 62), fill=(28, 88, 150, 255))
    ld.text((x0 + 28, y0 + 46), "WORK ORDER  CV-5", font=ImageFont_courier(40), fill=(214, 236, 250, 255), anchor="ls")
    for i, label in enumerate(("LIKE", "SUBSCRIBE")):
        yy = y0 + 100 + i * 86
        ld.rectangle((x0 + 34, yy, x0 + 90, yy + 56), outline=_CY, width=4)
        ld.text((x0 + 124, yy + 46), label, font=ImageFont_courier(52), fill=(214, 236, 250, 255), anchor="ls")
        k = smooth(min(max((age - (0.5 + i * 0.5)) / 0.3, 0.0), 1.0))
        if k > 0:
            ld.line((x0 + 42, yy + 30, x0 + 42 + 14 * k, yy + 30 + 14 * k), fill=(110, 230, 150, 255), width=9)
            if k > 0.5:
                ld.line((x0 + 56, yy + 44, x0 + 56 + 26 * (k - 0.5) * 2, yy + 44 - 34 * (k - 0.5) * 2), fill=(110, 230, 150, 255), width=9)
    if age > 1.7:
        q = ease_out_back(min((age - 1.7) / 0.2, 1.0), 2.2)
        r = max(q, 0.05)
        st = Image.new("RGBA", (330, 110), (0, 0, 0, 0))
        sd = ImageDraw.Draw(st)
        sd.rounded_rectangle((6, 6, 324, 104), radius=12, outline=(120, 232, 160, 255), width=7)
        sd.text((165, 56), "APPROVED", font=ImageFont_courier(46), fill=(120, 232, 160, 255), anchor="mm")
        st = st.rotate(8, expand=True, resample=Image.BICUBIC).resize((int(st.width * r), int(st.height * r)))
        lay.alpha_composite(st, (x0 + 470, y0 + 130 + off * 0))
    ov.alpha_composite(lay, (0, int(H * 0.755)))


CTAS["workorder"] = cta_workorder

_prev_title = draw_title


def draw_title(ov, d, title: str, kind: str = "pill") -> None:   # noqa: F811
    if kind == "stencil":
        return draw_title_stencil(ov, d, title)
    return _prev_title(ov, d, title, kind)


_prev_progress = draw_progress


def draw_progress(d, kind: str, frac: float, t: float) -> None:   # noqa: F811
    if kind == "rivets":
        return draw_progress_rivets(d, frac, t)
    return _prev_progress(d, kind, frac, t)
