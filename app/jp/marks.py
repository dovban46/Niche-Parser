"""Виноски каналу «Хіба це можна їсти?» (2026-11-12): маркерні обведення й наліпки-примітки поверх кадру.
Стиль: ніби хтось малює червоним фломастером по картинці (коло, стрілка, хрест, галочка, підкреслення) і клеїть наліпку з коротким словом.
Це НОВИЙ вигляд монтажу порівняно з каналом про Японію (там був лише тонкий овал і штампи).

Поля біта (їх пише beatsrc із ключів beats_src):
    mark = {"kind": circle|arrow|cross|check|underline, "x": 0..1, "y": 0..1, "r": 0..1, "dir": градуси (для arrow)}
           координати в системі КАДРУ-КАРТИНКИ (частка ширини/висоти), тож позначка їде разом з камерою;
    note = {"text": "...", "x": 0..1, "y": 0..1, "color": red|green|blue|dark}   координати на ЕКРАНІ (частка ширини/висоти).
Біт може мати лише note (без позначки) або лише mark: «з текстом» і «без нього, лише обведено»."""

import math
from functools import lru_cache

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

COMIC = "C:/Windows/Fonts/comicbd.ttf"
INK_BGR = (24, 26, 34)
RED_BGR = (46, 64, 230)
GREEN_BGR = (90, 190, 60)
T0 = 0.22              # коли починається малювання в біті, с
TDRAW = 0.34           # скільки малюється, с
NOTE_COLORS = {"red": (214, 64, 46), "green": (36, 150, 60), "blue": (36, 98, 200), "dark": (34, 26, 24)}


def _pt(M, iw, ih, x, y):
    return M[0, 0] * x * iw + M[0, 2], M[1, 1] * y * ih + M[1, 2]


def _stroke(frame, pts, color, w):
    """Товстий штрих фломастера: темний контур під кольоровою лінією, круглі кінці."""
    if len(pts) < 2:
        return
    arr = np.array(pts, np.int32).reshape(-1, 1, 2)
    cv2.polylines(frame, [arr], False, INK_BGR, int(w + 8), cv2.LINE_AA)
    cv2.polylines(frame, [arr], False, color, int(w), cv2.LINE_AA)


def _circle_pts(cx, cy, a, b, q, seed):
    pts = []
    steps = 90
    for k in range(int(steps * q) + 1):
        th = -math.pi * 0.7 + 2 * math.pi * 1.07 * (k / steps)
        wob = 1 + 0.025 * math.sin(2 * th + seed) + 0.07 * (k / steps) ** 2     # недомальований кінець, рука трохи гуляє
        pts.append((cx + a * wob * math.cos(th), cy + b * wob * math.sin(th)))
    return pts


def _bez(p0, p1, p2, q, n=24):
    out = []
    for k in range(int(n * q) + 1):
        s = k / n
        out.append(((1 - s) ** 2 * p0[0] + 2 * (1 - s) * s * p1[0] + s * s * p2[0],
                    (1 - s) ** 2 * p0[1] + 2 * (1 - s) * s * p1[1] + s * s * p2[1]))
    return out


def draw_mark(frame, b, lt, M, size, seed=0):
    m = b.get("mark")
    if not m:
        return
    q = (lt - T0) / TDRAW
    if q <= 0:
        return
    q = min(q, 1.0)
    iw, ih = size
    cx, cy = _pt(M, iw, ih, m["x"], m["y"])
    rad = m.get("r", 0.12) * iw * M[0, 0]
    w = 11
    kind = m["kind"]
    if kind == "circle":
        pulse = 1 + 0.04 * math.sin((lt - T0) * 8) if q >= 1 else 1
        _stroke(frame, _circle_pts(cx, cy, rad * 1.1 * pulse, rad * 0.86 * pulse, q, seed), RED_BGR, w)
    elif kind == "arrow":
        ang = math.radians(m.get("dir", 225))          # звідки летить стрілка: 225 = зверху ліворуч
        L = rad * 2.3
        sx, sy = cx + math.cos(ang) * L, cy - math.sin(ang) * L
        gap = rad * 0.55
        tx, ty = cx + math.cos(ang) * gap, cy - math.sin(ang) * gap          # кінчик не лізе в об'єкт
        mx, my = (sx + tx) / 2 + (ty - sy) * 0.22, (sy + ty) / 2 - (tx - sx) * 0.22
        pts = _bez((sx, sy), (mx, my), (tx, ty), q)
        _stroke(frame, pts, RED_BGR, w)
        if q >= 0.95:
            d = math.atan2(ty - my, tx - mx)
            for da in (2.55, -2.55):
                _stroke(frame, [(tx, ty), (tx + math.cos(d + da) * rad * 0.62, ty + math.sin(d + da) * rad * 0.62)], RED_BGR, w)
    elif kind == "cross":
        s = rad * 0.9
        _stroke(frame, [(cx - s, cy - s), (cx - s + 2 * s * min(q * 2, 1), cy - s + 2 * s * min(q * 2, 1))], RED_BGR, w + 3)
        if q > 0.5:
            r2 = (q - 0.5) * 2
            _stroke(frame, [(cx + s, cy - s), (cx + s - 2 * s * r2, cy - s + 2 * s * r2)], RED_BGR, w + 3)
    elif kind == "check":
        s = rad * 0.9
        pts = [(cx - s, cy), (cx - s * 0.3, cy + s * 0.7), (cx + s, cy - s * 0.8)]
        k = q * 2
        seg = [pts[0], (pts[0][0] + (pts[1][0] - pts[0][0]) * min(k, 1), pts[0][1] + (pts[1][1] - pts[0][1]) * min(k, 1))]
        if k > 1:
            k2 = k - 1
            seg += [(pts[1][0] + (pts[2][0] - pts[1][0]) * k2, pts[1][1] + (pts[2][1] - pts[1][1]) * k2)]
        _stroke(frame, seg, GREEN_BGR, w + 3)
    elif kind == "underline":
        n = 40
        pts = [(cx - rad + 2 * rad * (i / n), cy + 5 * math.sin(i / n * 9 + seed)) for i in range(int(n * q) + 1)]
        _stroke(frame, pts, RED_BGR, w)


@lru_cache(maxsize=None)
def note_sprite(text: str, color: str) -> np.ndarray:
    """Наліпка: біла, з товстим темним контуром і тінню, слово фломастером (Comic Sans Bold), трохи нахилена."""
    f = ImageFont.truetype(COMIC, 66)
    tw = f.getlength(text)
    pad = 26
    wd, ht = int(tw + pad * 2), 66 + pad * 2
    im = Image.new("RGBA", (wd + 60, ht + 60), (0, 0, 0, 0))
    dr = ImageDraw.Draw(im)
    dr.rounded_rectangle((34, 36, 34 + wd, 36 + ht), 22, fill=(0, 0, 0, 80))
    dr.rounded_rectangle((26, 26, 26 + wd, 26 + ht), 22, fill=(255, 255, 255, 255), outline=(34, 26, 24, 255), width=7)
    dr.text((26 + pad, 26 + pad - 12), text, font=f, fill=NOTE_COLORS.get(color, NOTE_COLORS["red"]) + (255,))
    return np.asarray(im.rotate(-3.5, resample=Image.BICUBIC, expand=True))


def draw_note(frame, b, lt, blit, ease_out_back, W, H):
    n = b.get("note")
    if not n:
        return
    q = (lt - 0.12) / 0.26
    if q <= 0:
        return
    sp = note_sprite(n["text"], n.get("color", "red"))
    sc = max(0.3, 0.6 + 0.4 * ease_out_back(min(q, 1.0)))
    blit(frame, sp, n.get("x", 0.5) * W, n.get("y", 0.15) * H, scale=sc, alpha=min(q * 3, 1.0))


def draw(frame, b, lt, M, size, blit, ease_out_back, W, H, seed=0):
    draw_mark(frame, b, lt, M, size, seed)
    draw_note(frame, b, lt, blit, ease_out_back, W, H)
