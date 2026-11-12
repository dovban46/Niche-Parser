"""Графічні «рішення» монтажу Shorts, які відрізняють одне відео від іншого: штамп, вибір («OBEY / RUN»), указ, що друкується,
рукописне коло-виноска, лічильник, шкали «ЛОЯЛЬНІСТЬ / СТРАХ», хроматична аберація на ударах, нарізні переходи (slash, ink).
Кожна функція малює на RGBA-шарі накладок (PIL) або повертає новий кадр (numpy). Час `age` — секунди від початку біта."""
import math
import random

import cv2
import numpy as np
from PIL import Image, ImageDraw

from .render import W, H, GOLD, OUTLINE, YELLOW, _font, _emoji_img, ease_out, ease_out_back, smooth

RED = (206, 34, 46)


def draw_stamp(ov: Image.Image, d: ImageDraw.ImageDraw, text: str, age: float) -> None:
    """Червоний штамп вдаряє по кадру: зі збільшення 3.4× → 1× за 0.17 с, коротка тремтіння, далі лишається."""
    if age < 0:
        return
    p = min(age / 0.17, 1.0)
    base = 150
    tw0 = d.textlength(text, font=_font(base))
    if tw0 > W * 0.66:   # штамп з урахуванням нахилу й рамки завжди вміщується в кадр (без обрізання по краях)
        base = int(base * W * 0.66 / tw0)
    sc = 1.0 + 2.4 * (1 - ease_out(p)) ** 1.5
    sc = min(sc, 1.0 + 0.9 * W * 0.66 / max(tw0 * base / 150, 1))   # стартове збільшення теж не виходить за кадр
    f = _font(int(base * sc))
    tw = d.textlength(text, font=f)
    pad = 60
    layer = Image.new("RGBA", (int(tw) + pad * 2, int(base * sc) + pad * 2), (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    ld.rounded_rectangle((8, 8, layer.width - 8, layer.height - 8), radius=28, outline=(*RED, 255), width=int(14 * sc))
    ld.text((layer.width / 2, layer.height / 2 + 6), text, font=f, fill=(*RED, 255), anchor="mm")
    layer = layer.rotate(-9, expand=True, resample=Image.BICUBIC)
    a = layer.getchannel("A").point(lambda v: int(v * (0.35 + 0.65 * p)))
    layer.putalpha(a)
    jitter = (random.Random(int(age * 60)).uniform(-6, 6), random.Random(int(age * 60) + 7).uniform(-6, 6)) if 0.17 < age < 0.45 else (0, 0)
    ov.alpha_composite(layer, (int(W / 2 - layer.width / 2 + jitter[0]), int(H * 0.27 - layer.height / 2 + jitter[1])))


SERIOUS = False      # виставляється стилем відео (render_short.apply_style)


def draw_choice(ov: Image.Image, d: ImageDraw.ImageDraw, options: list[str], pick: int, age: float, dur: float) -> None:
    """Два великі стікер-кнопки: з'являються по черзі, потім «палець» натискає обрану; вона вистрибує, інша гасне."""
    if not options:
        return
    cols = [(255, 214, 54), (122, 214, 255)]
    tap_t = max(dur * 0.55, 0.9)
    for i, opt in enumerate(options[:2]):
        t_in = 0.12 + 0.16 * i
        if age < t_in:
            continue
        p = ease_out_back((age - t_in) / 0.22, 2.0)
        chosen = i == pick and age > tap_t
        dim = (i != pick) and age > tap_t
        sc = max(p, 0.02) * (1.12 + 0.05 * math.sin((age - tap_t) * 22) if chosen else 1.0)
        f = _font(int(96 * sc))
        tw = d.textlength(opt, font=f)
        bw, bh = int(tw + 120), int(150 * sc)
        cx, cy = W / 2, H * (0.30 + 0.17 * i)
        alpha = 110 if dim else 255
        d.rounded_rectangle((cx - bw / 2 + 8, cy - bh / 2 + 12, cx + bw / 2 + 8, cy + bh / 2 + 12), radius=40, fill=(0, 0, 0, int(alpha * 0.4)))
        if SERIOUS:   # темна пластина з бурштиновою рамкою замість яскравих кнопок
            fill_c, edge_c, txt_c = (22, 26, 20), ((214, 168, 64) if (i == pick and age > tap_t) else (150, 150, 138)), (238, 234, 220)
            d.rounded_rectangle((cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2), radius=10, fill=(*fill_c, int(alpha * 0.92)), outline=(*edge_c, alpha), width=5)
            d.text((cx, cy + int(30 * sc)), opt, font=f, fill=(*txt_c, alpha), anchor="ms")
        else:
            d.rounded_rectangle((cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2), radius=40, fill=(*cols[i], alpha), outline=(*OUTLINE, alpha), width=8)
            d.text((cx, cy + int(30 * sc)), opt, font=f, fill=(*OUTLINE, alpha), anchor="ms")
    if age > tap_t - 0.35 and not SERIOUS:   # палець-курсор їде до обраної кнопки
        em = _emoji_img("👆", int(0.2 * W))
        if em is not None:
            q = smooth((age - (tap_t - 0.35)) / 0.35)
            tx, ty = W * 0.74, H * (0.30 + 0.17 * pick) + 40
            sx, sy = W * 0.95, H * 0.7
            px, py = sx + (tx - sx) * q, sy + (ty - sy) * q - (14 if age > tap_t else 0)
            ov.alpha_composite(em, (int(px - em.width / 2), int(py - em.height / 2)))


def draw_decree(ov: Image.Image, d: ImageDraw.ImageDraw, text: str, age: float, dur: float) -> None:
    """Пергаментний указ, текст якого друкується по літері."""
    p_in = ease_out_back(min(age / 0.28, 1.0), 1.4)
    if p_in <= 0.02:
        return
    w, h = int(W * 0.88), int(H * 0.20)
    x0, y0 = int(W / 2 - w / 2), int(H * 0.50)
    panel = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    pd = ImageDraw.Draw(panel)
    pd.rounded_rectangle((0, 0, w - 1, h - 1), radius=34, fill=(244, 226, 184, 255), outline=(*OUTLINE, 255), width=8)
    for k in range(3):
        pd.line([(36, 40 + k * 4), (w - 36, 40 + k * 4)], fill=(190, 150, 90, 120), width=2) if k == 0 else None
    shown = int(len(text) * min(max((age - 0.25) / max(dur * 0.7, 0.4), 0.0), 1.0))
    f = _font(66)
    words, lines, cur = text[:shown].split(" "), [], ""
    for wd in words:
        if pd.textlength((cur + " " + wd).strip(), font=f) > w - 90:
            lines.append(cur)
            cur = wd
        else:
            cur = (cur + " " + wd).strip()
    lines.append(cur)
    for li, ln in enumerate(lines[:3]):
        pd.text((44, 30 + li * 78), ln, font=f, fill=(70, 38, 28, 255), anchor="la")
    seal = (w - 90, h - 56)
    pd.ellipse((seal[0] - 38, seal[1] - 38, seal[0] + 38, seal[1] + 38), fill=(*RED, 255), outline=(*OUTLINE, 255), width=5)
    pd.ellipse((seal[0] - 16, seal[1] - 16, seal[0] + 16, seal[1] + 16), outline=(255, 210, 210, 255), width=4)
    sc = 0.7 + 0.3 * p_in
    panel = panel.resize((int(w * sc), int(h * sc)), Image.BILINEAR).rotate(-2.5, expand=True, resample=Image.BICUBIC)
    ov.alpha_composite(panel, (int(W / 2 - panel.width / 2), int(y0 + (1 - p_in) * 120)))


def draw_circle(d: ImageDraw.ImageDraw, rect: tuple, age: float) -> None:
    """Рукописне червоне коло навколо предмета: домальовується за 0.35 с і трохи «тремтить»."""
    x0, y0, x1, y1 = rect
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    rx, ry = (x1 - x0) / 2 * 0.78 + 26, (y1 - y0) / 2 * 0.78 + 26
    p = min(max(age - 0.12, 0) / 0.35, 1.0)
    n = int(70 * p)
    rnd = random.Random(5)
    pts = []
    for i in range(n + 1):
        a = -math.pi / 2 + 2 * math.pi * (i / 70) * 1.08
        wob = 1 + 0.035 * math.sin(a * 3 + 1.2) + rnd.uniform(-0.01, 0.01)
        pts.append((cx + rx * wob * math.cos(a) * (1 + 0.04 * i / 70), cy + ry * wob * math.sin(a)))
    if len(pts) > 1:
        d.line(pts, fill=(0, 0, 0, 90), width=20, joint="curve")
        d.line(pts, fill=(*RED, 255), width=13, joint="curve")


def draw_counter(d: ImageDraw.ImageDraw, spec: list, age: float, dur: float) -> None:
    a, b, label = spec[0], spec[1], (spec[2] if len(spec) > 2 else "")
    p = smooth(min(age / max(dur * 0.8, 0.5), 1.0))
    val = int(a + (b - a) * p)
    txt = f"{val:,}"
    f = _font(190)
    tw = d.textlength(txt, font=f)
    cx, cy = W / 2, H * 0.19
    pulse = 1 + 0.06 * math.sin(age * 18) * (1 - p)
    f = _font(int(190 * pulse))
    d.text((cx + 8, cy + 8), txt, font=f, fill=(0, 0, 0, 140), anchor="mm", stroke_width=22, stroke_fill=(0, 0, 0, 140))
    d.text((cx, cy), txt, font=f, fill=(255, 255, 255, 255), anchor="mm", stroke_width=22, stroke_fill=(255, 255, 255, 255))
    d.text((cx, cy), txt, font=f, fill=(*YELLOW, 255), anchor="mm", stroke_width=9, stroke_fill=(*OUTLINE, 255))
    if label:
        f2 = _font(64)
        d.text((cx, cy + 118), label, font=f2, fill=(255, 255, 255, 255), anchor="mm", stroke_width=10, stroke_fill=(*OUTLINE, 255))


def draw_meters(d: ImageDraw.ImageDraw, vals: dict, prev: dict, age: float, names: dict | None = None) -> None:
    """Шкали ЛОЯЛЬНІСТЬ (золото) і СТРАХ (червоне): значення плавно їдуть від попереднього біта до нового."""
    q = smooth(min(age / 0.45, 1.0))
    y = 190
    for name, col in (("LOYALTY", GOLD), ("FEAR", RED)):
        if name.lower() not in vals:
            continue
        v0, v1 = prev.get(name.lower(), vals[name.lower()]), vals[name.lower()]
        v = v0 + (v1 - v0) * q
        x0, w, h = 54, 520, 44
        d.rounded_rectangle((x0 - 4, y - 4, x0 + w + 4, y + h + 4), radius=24, fill=(0, 0, 0, 120))
        d.rounded_rectangle((x0, y, x0 + w, y + h), radius=22, fill=(30, 22, 24, 230), outline=(*OUTLINE, 255), width=4)
        fw = max(int(w * v / 100), 10)
        d.rounded_rectangle((x0 + 3, y + 3, x0 + fw - 3, y + h - 3), radius=19, fill=(*col, 255))
        d.text((x0 + 18, y + h / 2 + 1), (names or {}).get(name.lower(), name), font=_font(30), fill=(*OUTLINE, 255), anchor="lm")
        y += 64


def chroma_ab(frame: np.ndarray, amount: float) -> np.ndarray:
    """RGB-розщеплення: червоний канал вправо, синій вліво (на ударах/штампах)."""
    if amount < 0.8:
        return frame
    a = int(round(amount))
    out = frame.copy()
    out[:, a:, 0] = frame[:, :-a, 0]
    out[:, :-a, 2] = frame[:, a:, 2]
    return out


def vignette(frame: np.ndarray, strength: float = 0.5) -> np.ndarray:
    h, w = frame.shape[:2]
    key = (h, w, strength)
    m = _VIG.get(key)
    if m is None:
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        dd = np.sqrt(((xx - w / 2) / (w / 2)) ** 2 + ((yy - h * 0.45) / (h * 0.62)) ** 2)
        m = _VIG[key] = (1.0 - strength * np.clip(dd - 0.45, 0, 1) ** 1.3)[..., None].astype(np.float32)
    return np.clip(frame.astype(np.float32) * m, 0, 255).astype(np.uint8)


_VIG: dict = {}


def slash_transition(a: np.ndarray, b: np.ndarray, p: float) -> np.ndarray:
    """Діагональний «удар мечем»: стара картинка розрізається по діагоналі, половини розсуваються й відкривають нову; по розрізу біла лінія."""
    h, w = a.shape[:2]
    out = b.copy()
    e = smooth(p)
    off = int(e * w * 0.7)
    yy, xx = np.mgrid[0:h, 0:w]
    side = (yy - h * 0.5) * 0.55 - (xx - w * 0.5) * 1.0   # діагональ
    up = side < 0
    # верхня-ліва половина зсувається вліво-вгору, нижня-права вправо-вниз
    M1 = np.float32([[1, 0, -off], [0, 1, -int(off * 0.25)]])
    M2 = np.float32([[1, 0, off], [0, 1, int(off * 0.25)]])
    a1 = cv2.warpAffine(a, M1, (w, h), borderValue=(0, 0, 0))
    a2 = cv2.warpAffine(a, M2, (w, h), borderValue=(0, 0, 0))
    m1 = cv2.warpAffine((up * 255).astype(np.uint8), M1, (w, h), borderValue=0) > 127
    m2 = cv2.warpAffine(((~up) * 255).astype(np.uint8), M2, (w, h), borderValue=0) > 127
    out[m1] = a1[m1]
    out[m2] = a2[m2]
    line = np.abs(side) < (10 + 28 * (1 - e))
    glow = max(0.0, 1.0 - e * 1.2)
    out[line & (e < 0.85)] = (255, 255, 255)
    return cv2.addWeighted(out, 1.0, np.full_like(out, 255), 0.18 * glow, 0)


def ink_transition(a: np.ndarray, b: np.ndarray, p: float, seed: int = 3) -> np.ndarray:
    """Червоно-чорне чорнило розповзається з точки й заливає кадр, потім відкриває нову сцену."""
    h, w = a.shape[:2]
    rng = np.random.default_rng(seed)
    key = ("ink", h, w, seed)
    noise = _INK.get(key)
    if noise is None:
        n = rng.random((h // 24 + 2, w // 24 + 2)).astype(np.float32)
        noise = cv2.resize(cv2.GaussianBlur(n, (0, 0), 1.2), (w, h), interpolation=cv2.INTER_CUBIC)
        _INK[key] = noise
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    dist = np.sqrt((xx - w * 0.5) ** 2 + (yy - h * 0.55) ** 2) / (math.hypot(w, h) * 0.55)
    field = dist + (noise - 0.5) * 0.35
    r1 = smooth(min(p / 0.5, 1.0)) * 1.25            # чорнило заливає
    r2 = smooth(max((p - 0.5) / 0.5, 0.0)) * 1.25    # відкриває нову
    ink = field < r1
    show_b = field < r2
    out = np.where(show_b[..., None], b, np.where(ink[..., None], np.array([18, 6, 10], np.uint8), a)).astype(np.uint8)
    edge = (np.abs(field - r1) < 0.025) & ~show_b
    out[edge] = (150, 20, 32)
    return out


_INK: dict = {}


_PLAIN: dict = {}


def _emoji_plain(ch: str, size: int):
    """Емодзі без білого «стікерного» ореолу (для кнопок на кольоровій плашці)."""
    key = (ch, size)
    im = _PLAIN.get(key)
    if im is None:
        from PIL import ImageFont
        font = ImageFont.truetype("C:/Windows/Fonts/seguiemj.ttf", 109)
        tmp = Image.new("RGBA", (160, 160), (0, 0, 0, 0))
        ImageDraw.Draw(tmp).text((20, 8), ch, font=font, embedded_color=True)
        bb = tmp.getbbox()
        if not bb:
            return None
        tmp = tmp.crop(bb)
        k = size / max(tmp.size)
        im = _PLAIN[key] = tmp.resize((max(int(tmp.width * k), 2), max(int(tmp.height * k), 2)), Image.LANCZOS)
    return im


def draw_cta(ov: Image.Image, d: ImageDraw.ImageDraw, age: float, total: float = 2.6) -> None:
    """Беззвучна плашка «лайк + підписка»: вистрибує знизу, палець тапає ЛАЙК, потім ПІДПИСКА стає «SUBSCRIBED» і дзвіночок трясеться; зникає."""
    if age < 0 or age > total:
        return
    pin = ease_out_back(min(age / 0.32, 1.0), 1.9)
    fade = 1.0 if age < total - 0.3 else max((total - age) / 0.3, 0.0)
    cy = int(H * 0.80 + (1 - min(pin, 1.0)) * 140)
    lay = Image.new("RGBA", (W, 300), (0, 0, 0, 0))
    ld = ImageDraw.Draw(lay)
    f = _font(58)
    like_tap = 0.85 < age < 1.15
    sub_on = age > 1.5
    # LIKE
    lx0, ly0, lw, lh = 70, 70, 400, 128
    sc = 1.0 + (0.14 if like_tap else 0.0)
    cx, cyy = lx0 + lw / 2, ly0 + lh / 2
    box = (cx - lw / 2 * sc, cyy - lh / 2 * sc, cx + lw / 2 * sc, cyy + lh / 2 * sc)
    ld.rounded_rectangle((box[0] + 6, box[1] + 8, box[2] + 6, box[3] + 8), radius=44, fill=(0, 0, 0, 110))
    ld.rounded_rectangle(box, radius=44, fill=(255, 255, 255, 255) if age < 0.85 else (122, 200, 255, 255), outline=(*OUTLINE, 255), width=6)
    ld.text((cx + 46, cyy + 4), "LIKE", font=f, fill=(*OUTLINE, 255), anchor="mm")
    e = _emoji_plain("👍", int(84 * sc))
    if e is not None:
        lay.alpha_composite(e, (int(box[0] + 26), int(cyy - e.height / 2)))
    # SUBSCRIBE
    sx0, sw = 520, 490
    scol = (206, 34, 46) if not sub_on else (150, 150, 158)
    wob = math.sin(age * 40) * 8 if 1.5 < age < 2.1 else 0
    ld.rounded_rectangle((sx0 + 6, ly0 + 8, sx0 + sw + 6, ly0 + lh + 8), radius=44, fill=(0, 0, 0, 110))
    ld.rounded_rectangle((sx0, ly0, sx0 + sw, ly0 + lh), radius=44, fill=(*scol, 255), outline=(*OUTLINE, 255), width=6)
    ld.text((sx0 + sw / 2 + 36, ly0 + lh / 2 + 4), "SUBSCRIBED" if sub_on else "SUBSCRIBE", font=_font(50 if sub_on else 54), fill=(255, 255, 255, 255), anchor="mm")
    bell = _emoji_plain("🔔", 74)
    if bell is not None:
        bell = bell.rotate(wob * 2.2, resample=Image.BICUBIC, expand=True)
        lay.alpha_composite(bell, (int(sx0 + 22), int(ly0 + lh / 2 - bell.height / 2)))
    # палець: з'являється, тапає LIKE (0.85 с), їде до SUBSCRIBE (1.5 с)
    if 0.35 < age < 1.95:
        if age < 1.0:
            fx_, fy_ = lx0 + 250, ly0 + 100
        else:
            q = smooth(min((age - 1.0) / 0.4, 1.0))
            fx_, fy_ = lx0 + 250 + (sx0 + 330 - lx0 - 250) * q, ly0 + 100
        tap = 14 if (0.85 < age < 1.1 or 1.5 < age < 1.7) else 0
        hand = _emoji_plain("👆", 110)
        if hand is not None:
            lay.alpha_composite(hand, (int(fx_ - hand.width / 2), int(fy_ + 18 + tap)))
    a = lay.getchannel("A").point(lambda v: int(v * fade))
    lay.putalpha(a)
    ov.alpha_composite(lay, (0, cy - 150))
