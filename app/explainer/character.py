"""Процедурний аватар v2 (стиль «ink explainer»): велика яйцеподібна голова, «локшинні» вигнуті руки з округлими долонями,
дзвоноподібний одяг зі складками, шия, плечі, м'яке клітинне затінення (cel shading), тонший контур. Один риг малює мудреця
й будь-яких інших дійових осіб (змінюються лише параметри CharacterSpec); пози/вирази/стани рота безкоштовні, рот рухається за
реальною гучністю озвучки. Малюється в одиницях висоти 1000 (ноги на y≈1000), з суперсемплінгом.

API: render(spec, pose, expr, mouth, phase, facing, height_px, blink) -> (RGBA-спрайт, (anchor_x, anchor_y)); якір = центр стоп."""

import math
from dataclasses import dataclass
from functools import lru_cache

from PIL import Image, ImageChops, ImageDraw

OUT = (34, 26, 24, 255)
LW = 9   # товщина контуру, од.
SS = 2   # суперсемплінг
# Полотно в одиницях: x -250..1250, y -260..1060 (руки вгору, жести, штаб)
X0, Y0, CW, CH = -250, -260, 1500, 1320


@dataclass(frozen=True)
class CharacterSpec:
    skin: tuple = (236, 190, 150)
    hair: tuple | None = (245, 242, 235)      # None — лисий без бокового волосся
    beard: tuple | None = (248, 246, 240)     # None — без бороди
    beard_len: float = 260
    robe: tuple = (62, 96, 170)
    trim: tuple = (232, 186, 70)
    style: str = "robe"                         # robe | kilt
    hat: str = "none"                           # none|turban|nemes|red_crown|white_crown|persian_cap|laurel|hood|headband|wig
    head_r: float = 1.1                         # масштаб голови
    brows: tuple = (250, 248, 244)
    hat_color: tuple = (240, 235, 220)
    glow: bool = False
    mask: bool = False                          # чумний лікар: шкіряна маска з дзьобом і окулярами (обличчя не малюється)
    mask_color: tuple = (150, 104, 64)
    gloss: bool = False                         # «стікерний» глянець: блік на голові/одязі, рум'янець
    # --- «епохальний» гардероб другорядних героїв ---
    mustache: tuple | None = None
    mustache_style: str = "droop"               # droop | handlebar | thin
    hair_style: str = "side"                    # side (боки) | short (чубчик) | long (до плечей) | bun
    cape: tuple | None = None                   # плащ позаду тіла
    legs: tuple = (58, 50, 54)                  # штани (tunic/armor)
    boots: tuple = (88, 58, 40)
    item: str = ""                              # "" | spear | sword | scimitar | torch | banner | pitchfork | cup
    fur: bool = False                           # хутряний комір (kaftan/tunic)
    steel: tuple = (172, 180, 194)
    fangs: bool = False                         # гострі ікла (Дракула)
    eye_color: tuple | None = None              # колір зіниць (червоні очі)
    high_collar: bool = False                   # високий комір-плащ за головою (класичний Дракула)
    glasses: bool = False
    face: str | None = None                     # 'operator': безлике спорядження (шолом, окуляри, балаклава)
    glove: tuple | None = None                  # колір рукавичок (руки)
    gear: bool = False                          # плитоноска з підсумками поверх тулуба
    wings: bool = False                         # крила гусара: віяло пір'я за спиною
    serious: bool = False                       # дорослі риси: менші очі, суворі брови, без рум'янців/усмішки
    pumpkin: bool = False                       # голова-гарбуз: ребра й хвостик
    straw: bool = False                         # солом'яні пучки на шиї й щиколотках (опудало)
    stitches: bool = False                      # шви на лобі й щоці (Франкенштейн)
    widow_peak: bool = False                    # зачіска «вдовиний мис»: чубчик із V-вирізом


SAGE = CharacterSpec()

STEEL_DARK = (96, 104, 120)


# ---------- пози: (upper, fore) кутів руки від "вниз" (0), 90 = горизонтально назовні, 180 = вгору ----------
POSES = {
    "stand":      dict(l=(12, 8), r=(12, 8)),
    "talk_a":     dict(l=(14, 10), r=(70, 150)),
    "talk_b":     dict(l=(60, 120), r=(60, 120)),
    "point_right": dict(l=(12, 8), r=(98, 100)),
    "point_up":   dict(l=(12, 8), r=(150, 175)),
    "shrug":      dict(l=(55, 140), r=(55, 140), shoulders=-18),
    "think":      dict(l=(12, 8), r=(40, 200), front=True),
    "cheer":      dict(l=(150, 175), r=(150, 175)),
    "scared":     dict(l=(35, 195), r=(35, 195), front=True),
    "hold_scroll": dict(l=(40, 175), r=(40, 175), front=True, item="scroll"),
    "hold_staff": dict(l=(12, 8), r=(30, 40), item="staff"),
    "walk":       dict(l=(25, 15), r=(25, 15), walk=True),
    "run":        dict(l=(55, 110), r=(55, 110), walk=True, lean=8, speed=2.0),
    "bow":        dict(l=(10, 6), r=(10, 6), lean=22),
    "wave":       dict(l=(12, 8), r=(150, 118)),
    "arms_wide":  dict(l=(100, 85), r=(100, 85)),
    "facepalm":   dict(l=(12, 8), r=(30, 205), front=True, lean=5),
    "cross_arms": dict(l=(22, -105), r=(22, -105), front=True),
    "hands_hips": dict(l=(52, -40), r=(52, -40)),
    "idea":       dict(l=(12, 8), r=(62, 168)),
    "whisper":    dict(l=(12, 8), r=(34, -150), front=True, lean=4),
    "laugh":      dict(l=(22, -85), r=(22, -85), front=True, shake=True, lean=-4),
    "point_left": dict(l=(98, 100), r=(12, 8)),
    "present":    dict(l=(70, 120), r=(30, 40)),
    "lean_in":    dict(l=(30, 80), r=(26, 24), lean=9),
    "sneak":      dict(l=(20, 30), r=(20, 30), walk=True, lean=-6, speed=0.8),
    "kneel":      dict(l=(30, 60), r=(30, 60), drop=150),
    "cower":      dict(l=(150, 215), r=(150, 215), front=True, drop=110, lean=6),
    "carry":      dict(l=(42, 100), r=(42, 100), front=True),
    "bow_deep":   dict(l=(14, 6), r=(14, 6), lean=34, drop=40),
}

EXPRS = {
    #            eyes     brows      mouth_idle (коли не говорить)
    "neutral":   ("dot",   "neutral", "closed"),
    "happy":     ("happy", "raised",  "smile"),
    "surprised": ("wide",  "raised",  "o"),
    "worried":   ("dot",   "worried", "frown"),
    "angry":     ("dot",   "angry",   "frown"),
    "smug":      ("half",  "neutral", "smile"),
    "sleepy":    ("closed", "sad",    "closed"),
    "scared":    ("wide",  "worried", "o"),
    "thinking":  ("dot",   "raised",  "closed"),
}


def _sh(c, f):
    return tuple(max(0, min(255, int(v * f))) for v in c[:3]) + (255,)


_shade = _sh


class _Canvas:
    def __init__(self, k: float):
        self.k = k
        self.img = Image.new("RGBA", (int(CW * k), int(CH * k)), (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.img)

    def pt(self, x, y):
        return ((x - X0) * self.k, (y - Y0) * self.k)

    def _dot(self, x, y, r, fill):
        px, py = self.pt(x, y)
        rr = r * self.k
        self.d.ellipse((px - rr, py - rr, px + rr, py + rr), fill=fill)

    def poly(self, pts, fill, outline=True, width=LW):
        p = [self.pt(x, y) for x, y in pts]
        if outline:
            self.d.line(p + [p[0]], fill=OUT, width=int(width * self.k * 2), joint="curve")
            for q in p:
                r = width * self.k
                self.d.ellipse((q[0] - r, q[1] - r, q[0] + r, q[1] + r), fill=OUT)
        self.d.polygon(p, fill=fill)

    def ellipse(self, cx, cy, rx, ry, fill, outline=True, width=LW):
        if outline:
            self.d.ellipse((*self.pt(cx - rx - width, cy - ry - width), *self.pt(cx + rx + width, cy + ry + width)), fill=OUT)
        self.d.ellipse((*self.pt(cx - rx, cy - ry), *self.pt(cx + rx, cy + ry)), fill=fill)

    def line(self, pts, width, fill, outline=True, ow=LW):
        p = [self.pt(x, y) for x, y in pts]
        if outline:
            w = int((width + 2 * ow) * self.k)
            self.d.line(p, fill=OUT, width=w, joint="curve")
            for q in (p[0], p[-1]):
                r = w / 2
                self.d.ellipse((q[0] - r, q[1] - r, q[0] + r, q[1] + r), fill=OUT)
        w2 = int(width * self.k)
        self.d.line(p, fill=fill, width=w2, joint="curve")
        for q in (p[0], p[-1]):
            r = w2 / 2
            self.d.ellipse((q[0] - r, q[1] - r, q[0] + r, q[1] + r), fill=fill)

    def arc(self, box, a0, a1, width, fill=OUT):
        (x0, y0), (x1, y1) = self.pt(box[0], box[1]), self.pt(box[2], box[3])
        self.d.arc((x0, y0, x1, y1), a0, a1, fill=fill, width=int(width * self.k))

    # --- «локшина»: плавна вигнута кінцівка зі звуженням ---
    @staticmethod
    def bezier(S, E, W, n=26):
        C = (2 * E[0] - (S[0] + W[0]) / 2, 2 * E[1] - (S[1] + W[1]) / 2)
        out = []
        for i in range(n + 1):
            t = i / n
            a, b, c = (1 - t) ** 2, 2 * (1 - t) * t, t * t
            out.append((a * S[0] + b * C[0] + c * W[0], a * S[1] + b * C[1] + c * W[1]))
        return out

    def noodle(self, S, E, W, w0, w1, fill, ow=LW, shade=None):
        pts = self.bezier(S, E, W)
        n = len(pts) - 1
        radii = [(w0 + (w1 - w0) * i / n) / 2 for i in range(n + 1)]
        for (x, y), r in zip(pts, radii):
            self._dot(x, y, r + ow, OUT)
        for (x, y), r in zip(pts, radii):
            self._dot(x, y, r, fill)
        if shade:
            def mask(md, P):
                for (x, y), r in zip(pts, radii):
                    px, py = P(x, y)
                    rr = r * self.k
                    md.ellipse((px - rr, py - rr, px + rr, py + rr), fill=255)
            xs, ys = [p[0] for p in pts], [p[1] for p in pts]
            self.crescent(mask, (min(xs) - w0, min(ys) - w0, max(xs) + w0, max(ys) + w0), shade, (7, 6))
        return pts

    # --- клітинне затінення: півмісяць із нижньо-правого боку форми ---
    def crescent(self, draw_mask, bbox, color, off=(16, 13)):
        x0, y0 = self.pt(bbox[0] - 20, bbox[1] - 20)
        x1, y1 = self.pt(bbox[2] + 20, bbox[3] + 20)
        x0, y0 = int(max(x0, 0)), int(max(y0, 0))
        x1, y1 = int(min(x1, self.img.width)), int(min(y1, self.img.height))
        if x1 <= x0 or y1 <= y0:
            return
        m = Image.new("L", (x1 - x0, y1 - y0), 0)
        draw_mask(ImageDraw.Draw(m), lambda x, y: (self.pt(x, y)[0] - x0, self.pt(x, y)[1] - y0))
        sh = ImageChops.offset(m, -int(off[0] * self.k), -int(off[1] * self.k))
        cres = ImageChops.subtract(m, sh)
        self.img.paste(Image.new("RGBA", m.size, color), (x0, y0), cres)

    def shine(self, cx, cy, rx, ry, alpha=110, angle=-25, color=(255, 255, 255)):
        """М'який блік: еліпс, обрізаний по вже намальованій формі (не вилазить за контур)."""
        x0, y0 = self.pt(cx - rx, cy - ry)
        x1, y1 = self.pt(cx + rx, cy + ry)
        w, h = max(int(x1 - x0), 4), max(int(y1 - y0), 4)
        lay = Image.new("RGBA", (w + 4, h + 4), (0, 0, 0, 0))
        ImageDraw.Draw(lay).ellipse((2, 2, w + 1, h + 1), fill=(*color, alpha))
        lay = lay.rotate(angle, expand=True, resample=Image.BICUBIC)
        px, py = int(x0 - (lay.width - w) / 2), int(y0 - (lay.height - h) / 2)
        if px < 0 or py < 0 or px + lay.width > self.img.width or py + lay.height > self.img.height:
            return
        under = self.img.crop((px, py, px + lay.width, py + lay.height)).getchannel("A")
        lay.putalpha(ImageChops.multiply(lay.getchannel("A"), under))
        self.img.alpha_composite(lay, (px, py))

    def shaded_ellipse(self, cx, cy, rx, ry, fill, shade, width=LW, off=(16, 13)):
        self.ellipse(cx, cy, rx, ry, fill, width=width)

        def mask(md, P):
            md.ellipse((*P(cx - rx, cy - ry), *P(cx + rx, cy + ry)), fill=255)
        self.crescent(mask, (cx - rx, cy - ry, cx + rx, cy + ry), shade, off)

    def shaded_poly(self, pts, fill, shade, width=LW, off=(16, 13)):
        self.poly(pts, fill, width=width)

        def mask(md, P):
            md.polygon([P(x, y) for x, y in pts], fill=255)
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        self.crescent(mask, (min(xs), min(ys), max(xs), max(ys)), shade, off)


def _limb(S, side, u, f, lu=175, lf=165):
    sgn = -1 if side == "l" else 1
    ex = S[0] + sgn * lu * math.sin(math.radians(u))
    ey = S[1] + lu * math.cos(math.radians(u))
    wx = ex + sgn * lf * math.sin(math.radians(f))
    wy = ey + lf * math.cos(math.radians(f))
    return (ex, ey), (wx, wy)


def _draw_arm(cv: _Canvas, spec: CharacterSpec, S, side, u, f):
    """Вигнута рука: рукав (або голі руки в kilt), манжета, округла долоня з великим пальцем."""
    sgn = -1 if side == "l" else 1
    e, w = _limb(S, side, u, f)
    clothed = spec.style in ("robe", "tunic", "armor", "kaftan", "frock")
    robe = (*spec.robe, 255) if clothed else (*spec.skin, 255)
    w0, w1 = (60, 46) if clothed else (46, 36)
    pts = cv.noodle(S, e, w, w0, w1, robe, shade=_sh(robe[:3], 0.8))
    if clothed:
        a, b = pts[-8], pts[-1]
        cv.line([a, b], w1 - 4, (*spec.trim, 255), outline=False)
    # долоня: «рукавичка» + великий палець
    dx, dy = w[0] - pts[-3][0], w[1] - pts[-3][1]
    L = math.hypot(dx, dy) or 1
    ux, uy = dx / L, dy / L
    hx, hy = w[0] + ux * 16, w[1] + uy * 16
    skin = (*spec.skin, 255)
    cv.ellipse(hx - uy * sgn * 20 + ux * 6, hy + ux * sgn * 20 + uy * 6, 15, 15, skin, width=7)   # великий палець
    cv.shaded_ellipse(hx, hy, 30, 28, skin, _sh(spec.skin, 0.84), width=7, off=(7, 6))
    return (hx, hy)


def _draw_plague_head(cv: _Canvas, spec: CharacterSpec, expr: str, blink: bool, bob: float):
    """Маска чумного лікаря: коричнева шкіра, великі скляні окуляри, довгий дзьоб, ремінці. Емоції — через брови-зморшки й зіниці.
    Усе масштабується spec.head_r («стікерна» велика голова)."""
    r = spec.head_r
    cx, cy = 500, 185 + bob - (r - 1.0) * 70
    X = lambda dx: cx + dx * r
    Y = lambda dy: cy + dy * r
    mc = (*spec.mask_color, 255)
    eyes, brows, _ = EXPRS.get(expr, EXPRS["neutral"])
    cv.ellipse(cx, Y(128), 98 * r, 34 * r, (34, 32, 40, 255), width=8)                     # комір-шарф
    cv.shaded_ellipse(cx, cy, 126 * r, 140 * r, mc, _sh(spec.mask_color, 0.74), off=(18, 14))
    cv.line([(X(-120), Y(-20)), (X(-126), Y(60))], 9, (70, 46, 28, 255), outline=False)
    cv.line([(X(120), Y(-20)), (X(126), Y(60))], 9, (70, 46, 28, 255), outline=False)
    n = 16
    left, right = [], []
    for i in range(n + 1):
        t = i / n
        half = (44 * (1 - t) ** 0.85 + 7 * t) * r
        sway = 10 * math.sin(t * 2.2) * r
        y = Y(6 + t * 182)
        left.append((cx - half + sway, y))
        right.append((cx + half + sway, y))
    beak = left + right[::-1]
    cv.shaded_poly(beak, (*_sh(spec.mask_color, 1.08)[:3], 255), _sh(spec.mask_color, 0.66), off=(14, 8))
    cv.line([(X(4), Y(14)), (X(12), Y(150))], 7, _sh(spec.mask_color, 1.22), outline=False)
    for sx in (-1, 1):
        cv.ellipse(X(sx * 15), Y(78), 7, 11, (40, 26, 18, 255), outline=False)
    for sx in (-1, 1):
        ex, ey = X(sx * 60), Y(-34)
        cv.ellipse(ex, ey, 46 * r, 46 * r, (34, 28, 26, 255), width=7)
        cv.ellipse(ex, ey, 34 * r, 34 * r, (226, 240, 248, 255), outline=False)
        if blink or eyes == "closed":
            cv.line([(ex - 28 * r, ey + 4), (ex + 28 * r, ey + 4)], 9, (34, 28, 26, 255), outline=False)
        else:
            pr = (17 if eyes in ("wide",) else 12) * r
            cv.ellipse(ex + sx * 2, ey + 3, pr, pr, (30, 24, 24, 255), outline=False)
            cv._dot(ex + sx * 2 + 6, ey - 4, 5, (255, 255, 255, 255))
        cv.shine(ex - 10 * r, ey - 14 * r, 14 * r, 8 * r, 170, -30)
    cfg = {"neutral": (0, 0), "raised": (-14, 0), "worried": (-6, -16), "angry": (8, 18), "sad": (0, -10)}
    dy, tilt = cfg.get(brows, (0, 0))
    for sx in (-1, 1):
        x_in, x_out = X(sx * 24), X(sx * 96)
        y_in = Y(-96) + dy + max(tilt, 0) * 0.9
        y_out = Y(-96) + dy - max(tilt, 0) * 0.6 + max(-tilt, 0) * 0.7
        cv.line([(x_in, y_in), (x_out, y_out)], 15, (46, 30, 20, 255), ow=5)
    if spec.gloss:
        cv.shine(X(-56), Y(-100), 46 * r, 18 * r, 110, -20)


def _straw(cv: "_Canvas", x: float, y: float, n: int = 7, spread: float = 56, ln: float = 46) -> None:
    """Пучок соломи, що стирчить з-під одягу."""
    col = (236, 204, 96, 255)
    for i in range(n):
        f = i / max(n - 1, 1) - 0.5
        cv.line([(x + f * spread * 0.4, y), (x + f * spread * 1.4, y - ln * (0.7 + 0.5 * ((i * 5) % 3) / 2))], 7, col, outline=False)


def _draw_operator_head(cv: _Canvas, spec: CharacterSpec, expr: str, blink: bool, bob: float):
    """Сучасний оператор: балаклава, балістичний шолом із рейками, захисні окуляри. Без мультяшних рис обличчя; емоції — лише нахилом брів-козирка."""
    r = spec.head_r
    cx, cy = 500, 185 + bob - (r - 1.0) * 70
    X = lambda dx: cx + dx * r
    Y = lambda dy: cy + dy * r
    mc = spec.mask_color or (34, 36, 34)
    hc = spec.hat_color
    cv.ellipse(cx, Y(120), 92 * r, 40 * r, (*_sh(mc, 0.9)[:3], 255), width=8)                          # горловина/гейтер
    cv.shaded_ellipse(cx, cy, 120 * r, 140 * r, (*mc, 255), _sh(mc, 0.7), off=(16, 12))              # балаклава
    cv.line([(X(-8), Y(20)), (X(-4), Y(60))], 6, _sh(mc, 1.4), outline=False)                         # перенісся
    cv.line([(X(-50), Y(100)), (X(50), Y(100))], 5, _sh(mc, 0.55), outline=False)                     # шов біля підборіддя
    # шолом: купол, окантовка, рейки, кріплення ПНБ
    cv.shaded_ellipse(cx, Y(-62), 148 * r, 96 * r, (*hc, 255), _sh(hc, 0.68), width=8, off=(14, 10))
    cv.shaded_poly([(X(-146), Y(-40)), (X(146), Y(-40)), (X(138), Y(-14)), (X(-138), Y(-14))], (*_sh(hc, 0.82)[:3], 255), _sh(hc, 0.6), width=7, off=(8, 6))
    for sx in (-1, 1):
        cv.shaded_poly([(X(sx * 146), Y(-52)), (X(sx * 168), Y(-48)), (X(sx * 168), Y(6)), (X(sx * 146), Y(8))], (40, 42, 40, 255), (22, 24, 22, 255), width=6, off=(5, 4))
    cv.shaded_poly([(X(-30), Y(-92)), (X(30), Y(-92)), (X(24), Y(-58)), (X(-24), Y(-58))], (30, 32, 32, 255), (16, 18, 18, 255), width=6, off=(5, 4))
    cv.line([(X(-60), Y(-118)), (X(60), Y(-118))], 7, _sh(hc, 1.25), outline=False)
    if spec.gloss:
        cv.shine(X(-52), Y(-100), 46 * r, 14 * r, 90, -18)
    # окуляри: ремінь + два скла
    cv.line([(X(-134), Y(-4)), (X(134), Y(-4))], 22 * r, (24, 26, 26, 255), ow=5)
    tint = spec.eye_color or (214, 150, 52)
    for sx in (-1, 1):
        ex, ey = X(sx * 52), Y(-6)
        cv.ellipse(ex, ey, 46 * r, 34 * r, (20, 22, 24, 255), width=7)
        if blink:
            cv.line([(ex - 36 * r, ey), (ex + 36 * r, ey)], 7, (12, 12, 14, 255), outline=False)
        else:
            cv.ellipse(ex, ey, 38 * r, 26 * r, (*tint, 255), outline=False)
            cv.shine(ex - 12 * r, ey - 8 * r, 18 * r, 7 * r, 150, -20)
    brows = EXPRS.get(expr, EXPRS["neutral"])[1]
    if brows in ("angry", "worried"):   # нахил верху окулярів передає напругу
        cv.line([(X(-96), Y(-28 + (10 if brows == "angry" else -4))), (X(96), Y(-28 + (10 if brows == "angry" else -4)))], 5, (12, 12, 14, 255), outline=False)


def _draw_head(cv: _Canvas, spec: CharacterSpec, expr: str, mouth: int, blink: bool, bob: float, look: float = 0.0):
    if spec.face == "operator":
        _draw_operator_head(cv, spec, expr, blink, bob)
        return
    if spec.mask:
        _draw_plague_head(cv, spec, expr, blink, bob)
        return
    skin = (*spec.skin, 255)
    hr = spec.head_r
    cx, cy = 500, 185 + bob
    eyes, brows, idle = EXPRS.get(expr, EXPRS["neutral"])
    if blink and eyes in ("dot", "wide", "half"):
        eyes = "closed"
    # вуха
    cv.ellipse(cx - 134 * hr, cy + 14, 20, 30, _sh(spec.skin, 0.96), width=7)
    cv.ellipse(cx + 134 * hr, cy + 14, 20, 30, _sh(spec.skin, 0.96), width=7)
    if spec.hair:
        hair = (*spec.hair, 255)
        if spec.hair_style == "long":
            cv.ellipse(cx, cy + 70 * hr, 158 * hr, 196 * hr, hair, width=7)
            cv.ellipse(cx - 118 * hr, cy + 150 * hr, 50, 118, hair, width=7)
            cv.ellipse(cx + 118 * hr, cy + 150 * hr, 50, 118, hair, width=7)
        elif spec.hair_style == "bun":
            cv.ellipse(cx, cy - 170 * hr, 62, 52, hair, width=7)
        cv.ellipse(cx - 126 * hr, cy + 6, 40, 70, hair, width=7)
        cv.ellipse(cx + 126 * hr, cy + 6, 40, 70, hair, width=7)
    # голова — яйце (вужче вгорі, ширше внизу)
    cv.shaded_ellipse(cx, cy, 134 * hr, 152 * hr, skin, _sh(spec.skin, 0.85), off=(18, 14))
    if spec.gloss:
        cv.shine(cx - 52 * hr, cy - 96 * hr, 54 * hr, 24 * hr, 120, -28)
    if spec.pumpkin:
        rib = _sh(spec.skin, 0.68)
        for a_ in (-104, -52, 52, 104):
            pts_ = [(cx + a_ * hr * math.sqrt(max(1 - t_ * t_, 0.0)) * 1.0, cy + 148 * hr * t_) for t_ in [i_ / 10 - 1 for i_ in range(21)]]
            cv.line(pts_, 6, rib, outline=False)
        cv.poly([(cx - 16, cy - 146 * hr), (cx + 16, cy - 146 * hr), (cx + 24, cy - 196 * hr), (cx - 6, cy - 210 * hr)], (96, 128, 54, 255), width=6)
        cv.ellipse(cx + 40, cy - 168 * hr, 34, 16, (110, 150, 62, 255), width=5)
    if spec.hair and spec.hair_style in ("short", "long", "bun"):   # чубчик над лобом
        hc_ = (*spec.hair, 255)
        top = []
        for a in range(200, 341, 10):
            ar = math.radians(a)
            top.append((cx + 138 * hr * math.cos(ar), cy + 156 * hr * math.sin(ar)))
        low = [(cx + 138 * hr * math.cos(math.radians(a)) * 0.98, cy - 58 * hr + 40 * math.sin(math.radians(a))) for a in range(340, 199, -10)]
        if spec.widow_peak:   # V-виріз у центрі лоба
            mid = len(low) // 2
            low[mid - 1: mid + 2] = [(cx - 40 * hr, low[mid][1] - 4), (cx, low[mid][1] + 58 * hr), (cx + 40 * hr, low[mid][1] - 4)]
        cv.shaded_poly(top + low, hc_, _sh(spec.hair, 0.78), off=(10, 8), width=6)
    # борода
    if spec.beard:
        bc = (*spec.beard, 255)
        L = spec.beard_len + (26 if mouth >= 2 else (12 if mouth == 1 else 0))
        pts = []
        steps = 18
        for i in range(steps + 1):
            t = i / steps
            w = 146 * hr * (1 - t) ** 0.6
            pts.append((cx - w, cy + 60 + t * L))
        for i in range(steps, -1, -1):
            t = i / steps
            w = 146 * hr * (1 - t) ** 0.6
            pts.append((cx + w, cy + 60 + t * L))
        cv.shaded_poly(pts, bc, _sh(spec.beard, 0.86), off=(14, 12))
        sh = _sh(spec.beard, 0.74)
        for off in (-55, 0, 55):
            cv.line([(cx + off * .7, cy + 135), (cx + off * .35, cy + 60 + L * .74)], 6, sh, outline=False)
    # рот
    my = cy + 112 + (4 if mouth >= 2 else 0)
    shapes = {0: None, 1: (30, 14), 2: (40, 26), 3: (46, 38)} if spec.beard else {0: None, 1: (28, 12), 2: (36, 24), 3: (42, 34)}
    st = shapes.get(mouth)
    if mouth == 0:
        if idle == "smile":
            cv.arc((cx - 46, my - 40, cx + 46, my + 22), 20, 160, 8, OUT)
        elif idle == "frown":
            cv.arc((cx - 40, my - 6, cx + 40, my + 50), 200, 340, 8, OUT)
        elif idle == "o":
            cv.ellipse(cx, my + 8, 16, 20, (110, 40, 44, 255), width=7)
        else:
            cv.line([(cx - 32, my + 2), (cx + 32, my + 2)], 7, OUT, outline=False)
    else:
        rx, ry = st
        cv.ellipse(cx, my + ry * .35, rx, ry, (96, 34, 40, 255), width=7)
        if mouth >= 3:
            cv.ellipse(cx, my + ry * .85, rx * .6, ry * .4, (214, 96, 104, 255), outline=False)
    if spec.fangs:   # ікла: два білих трикутники, видно завжди (і при закритому роті)
        fy = my - 6 + (0 if mouth else 4)
        for sx in (-1, 1):
            cv.poly([(cx + sx * 12, fy), (cx + sx * 34, fy), (cx + sx * 23, fy + 34 + 4 * min(mouth, 2))], (252, 250, 244, 255), width=5)
    # ніс
    cv.shaded_ellipse(cx, cy + 34 * hr, 30, 27, _sh(spec.skin, 0.96), _sh(spec.skin, 0.78), width=7, off=(8, 7))
    if spec.gloss:   # рум'янець
        cv.shine(cx - 88 * hr, cy + 38, 26, 15, 105, 0, color=(255, 110, 120))
        cv.shine(cx + 88 * hr, cy + 38, 26, 15, 105, 0, color=(255, 110, 120))
    # вуса
    if spec.beard:
        bc = (*spec.beard, 255)
        for s in (-1, 1):
            cv.poly([(cx + s * 4, cy + 72), (cx + s * 48, cy + 68), (cx + s * 98, cy + 90), (cx + s * 82, cy + 118),
                     (cx + s * 36, cy + 102)], bc, width=7)
    if spec.mustache and not spec.beard:
        mc_ = (*spec.mustache, 255)
        for sx in (-1, 1):
            if spec.mustache_style == "handlebar":
                cv.poly([(cx + sx * 4, cy + 70), (cx + sx * 56, cy + 62), (cx + sx * 112, cy + 82), (cx + sx * 134, cy + 62),
                         (cx + sx * 126, cy + 100), (cx + sx * 76, cy + 104), (cx + sx * 36, cy + 98)], mc_, width=7)
            elif spec.mustache_style == "thin":
                cv.line([(cx + sx * 6, cy + 76), (cx + sx * 70, cy + 84)], 9, mc_, ow=4)
            else:   # droop: опущені вуса
                cv.poly([(cx + sx * 4, cy + 68), (cx + sx * 52, cy + 62), (cx + sx * 98, cy + 80), (cx + sx * 108, cy + 150),
                         (cx + sx * 80, cy + 120), (cx + sx * 40, cy + 100)], mc_, width=7)
    # очі: біле з контуром, зіниця зі зміщенням погляду, блік, повіка
    ey = cy - 30 * hr
    for s in (-1, 1):
        ex = cx + s * 52 * hr
        if eyes in ("dot", "wide", "half"):
            rx, ry = (25, 29) if eyes == "wide" else (22, 26)
            if spec.serious:
                rx, ry = rx * 0.74, ry * 0.7
            cv.ellipse(ex, ey, rx, ry, (255, 255, 255, 255), width=6)
            pr = 11 if eyes != "wide" else 9
            if spec.serious:
                pr = 8
            px = ex + look * 8
            cv.ellipse(px, ey + 2, pr, pr + 3, (*spec.eye_color, 255) if spec.eye_color else OUT, outline=False)
            cv._dot(px + 4, ey - 4, 4, (255, 255, 255, 255))
            if eyes == "half":
                cv.poly([(ex - rx - 4, ey - ry - 4), (ex + rx + 4, ey - ry - 4), (ex + rx + 4, ey - 2), (ex - rx - 4, ey - 2)],
                        skin, width=1)
                cv.line([(ex - rx, ey - 2), (ex + rx, ey - 2)], 7, OUT, outline=False)
        elif eyes == "happy":
            cv.arc((ex - 22, ey - 16, ex + 22, ey + 24), 200, 340, 8, OUT)
        else:
            cv.line([(ex - 20, ey + 4), (ex + 20, ey + 4)], 7, OUT, outline=False)
    if spec.stitches:
        sc_ = (40, 30, 34, 255)
        x0_, y0_ = cx - 60 * hr, cy - 98 * hr
        cv.line([(x0_, y0_), (x0_ + 120 * hr, y0_ - 6)], 7, sc_, outline=False)
        for k_ in range(5):
            xk = x0_ + 12 * hr + k_ * 24 * hr
            cv.line([(xk, y0_ - 14), (xk + 3, y0_ + 10)], 6, sc_, outline=False)
        cv.line([(cx + 62 * hr, cy + 10 * hr), (cx + 104 * hr, cy + 50 * hr)], 7, sc_, outline=False)
        for k_ in range(3):
            xk, yk = cx + (70 + k_ * 14) * hr, cy + (16 + k_ * 14) * hr
            cv.line([(xk - 10, yk + 10), (xk + 12, yk - 10)], 6, sc_, outline=False)
    if spec.glasses:
        for sx in (-1, 1):
            cv.ellipse(cx + sx * 52 * hr, cy - 30 * hr, 40, 40, (255, 255, 255, 0), width=5)
        cv.line([(cx - 14 * hr, cy - 34 * hr), (cx + 14 * hr, cy - 34 * hr)], 6, OUT, outline=False)
    bcol = (*spec.brows, 255)
    by = cy - 78 * hr
    cfg = {"neutral": (0, 0), "raised": (-16, 0), "worried": (-6, -18), "angry": (8, 20), "sad": (0, -12)}
    dy, tilt = cfg.get(brows, (0, 0))
    for s in (-1, 1):
        x_in, x_out = cx + s * 20 * hr, cx + s * 96 * hr
        y_in = by + dy + (tilt if tilt > 0 else 0) * 0.9
        y_out = by + dy - (tilt if tilt > 0 else 0) * 0.6 + (-tilt if tilt < 0 else 0) * 0.7
        cv.line([(x_in, y_in + (7 if spec.serious else 0)), (x_out, y_out + (7 if spec.serious else 0))], 22 if spec.serious else 17, bcol, ow=6)
    if spec.beard:
        for i, w in enumerate((70, 52)):
            cv.arc((cx - w, cy - 142 + i * 18, cx + w, cy - 110 + i * 18), 205, 335, 4, _sh(spec.skin, 0.8))


class _HatScale:
    """Проксі полотна: масштабує всі координати капелюха від центра голови на spec.head_r — капелюхи були намальовані для head_r=1
    і при великій «стікерній» голові (1.4-1.6) налазили на очі."""

    def __init__(self, cv: "_Canvas", r: float, cx: float, cy: float):
        self._cv, self.r, self.cx, self.cy = cv, r, cx, cy

    def _p(self, x, y):
        return (self.cx + (x - self.cx) * self.r, self.cy + (y - self.cy) * self.r)

    def __getattr__(self, name):
        return getattr(self._cv, name)

    def poly(self, pts, fill, outline=True, width=LW):
        self._cv.poly([self._p(x, y) for x, y in pts], fill, outline, width)

    def shaded_poly(self, pts, fill, shade, width=LW, off=(16, 13)):
        self._cv.shaded_poly([self._p(x, y) for x, y in pts], fill, shade, width, (off[0] * self.r, off[1] * self.r))

    def ellipse(self, cx, cy, rx, ry, fill, outline=True, width=LW):
        x, y = self._p(cx, cy)
        self._cv.ellipse(x, y, rx * self.r, ry * self.r, fill, outline, width)

    def shaded_ellipse(self, cx, cy, rx, ry, fill, shade, width=LW, off=(16, 13)):
        x, y = self._p(cx, cy)
        self._cv.shaded_ellipse(x, y, rx * self.r, ry * self.r, fill, shade, width, (off[0] * self.r, off[1] * self.r))

    def line(self, pts, width, fill, outline=True, ow=LW):
        self._cv.line([self._p(x, y) for x, y in pts], width * self.r, fill, outline, ow)

    def shine(self, cx, cy, rx, ry, alpha=110, angle=-25, color=(255, 255, 255)):
        x, y = self._p(cx, cy)
        self._cv.shine(x, y, rx * self.r, ry * self.r, alpha, angle, color)


def _draw_hat(cv: _Canvas, spec: CharacterSpec, bob: float):
    if spec.hat != "plague" and spec.head_r != 1.0:
        cv = _HatScale(cv, spec.head_r, 500, 185 + bob)
    cx, cy = 500, 175 + bob
    hc = (*spec.hat_color, 255)
    gold, blue = (*spec.trim, 255), (40, 70, 150, 255)
    h = spec.hat
    if h == "turban":
        cv.ellipse(cx, cy - 128, 146, 78, hc)
        cv.ellipse(cx - 30, cy - 168, 82, 50, _shade(spec.hat_color, 0.93))
        cv.line([(cx - 120, cy - 122), (cx + 110, cy - 146)], 8, _shade(spec.hat_color, 0.82), outline=False)
        cv.ellipse(cx + 8, cy - 150, 16, 16, gold, width=5)
    elif h == "nemes":
        pts = [(cx - 150, cy - 70), (cx - 100, cy - 150), (cx + 100, cy - 150), (cx + 150, cy - 70), (cx + 190, cy + 140),
               (cx + 120, cy + 150), (cx + 118, cy - 10), (cx - 118, cy - 10), (cx - 120, cy + 150), (cx - 190, cy + 140)]
        cv.poly(pts, blue)
        for i in range(5):
            y = cy - 120 + i * 30
            cv.line([(cx - 128, y), (cx + 128, y)], 9, gold, outline=False)
        cv.poly([(cx - 20, cy - 150), (cx + 20, cy - 150), (cx + 14, cy - 215), (cx - 14, cy - 215)], gold, width=9)
    elif h == "red_crown":
        cv.poly([(cx - 100, cy - 90), (cx + 100, cy - 90), (cx + 80, cy - 170), (cx + 20, cy - 175), (cx + 22, cy - 280),
                 (cx - 22, cy - 280), (cx - 30, cy - 170)], (200, 58, 52, 255))
    elif h == "white_crown":
        cv.poly([(cx - 105, cy - 92), (cx + 105, cy - 92), (cx + 78, cy - 220), (cx, cy - 290), (cx - 78, cy - 220)], (244, 240, 228, 255))
    elif h == "persian_cap":
        cv.poly([(cx - 116, cy - 70), (cx + 116, cy - 70), (cx + 96, cy - 250), (cx + 30, cy - 270), (cx - 30, cy - 270),
                 (cx - 96, cy - 250)], (150, 60, 70, 255))
        cv.line([(cx - 114, cy - 82), (cx + 114, cy - 82)], 18, gold, outline=False)
    elif h == "laurel":
        for s in (-1, 1):
            for i in range(5):
                a = math.radians(200 + s * (i * 16))
                px, py = cx + s * (95 + i * 12), cy - 84 + i * 14
                cv.ellipse(px, py, 30, 14, (96, 150, 70, 255), width=7)
    elif h == "hood":
        outer = [(cx + 172 * math.cos(math.radians(an)), cy - 20 + 196 * math.sin(math.radians(an))) for an in range(180, 361, 10)]
        outer = [(cx - 176, cy + 130)] + outer + [(cx + 176, cy + 130)]
        inner = [(cx + 120 * math.cos(math.radians(an)), cy - 10 + 156 * math.sin(math.radians(an))) for an in range(360, 179, -10)]
        inner = [(cx + 118, cy + 130)] + inner[1:-1] + [(cx - 118, cy + 130)]
        cv.shaded_poly(outer + inner, (*spec.robe, 255), _sh(spec.robe, 0.7), off=(14, 10))
    elif h == "wig":
        cv.poly([(cx - 150, cy + 70), (cx - 146, cy - 60), (cx - 80, cy - 150), (cx + 80, cy - 150), (cx + 146, cy - 60),
                 (cx + 150, cy + 70), (cx + 112, cy + 70), (cx + 108, cy - 52), (cx, cy - 92), (cx - 108, cy - 52), (cx - 112, cy + 70)],
                (34, 30, 36, 255))
    elif h == "plague":
        ink = (26, 24, 32, 255)
        r = spec.head_r
        cy = cy - (r - 1.0) * 70
        cv.shaded_ellipse(cx, cy - 150 * r, 104 * r, 70 * r, ink, (56, 52, 66, 255), width=8, off=(10, 8))
        cv.ellipse(cx, cy - 96 * r, 212 * r, 40 * r, ink, width=9)
        cv.line([(cx - 104 * r, cy - 112 * r), (cx + 104 * r, cy - 112 * r)], 22, (150, 108, 56, 255), outline=False)
        cv.shine(cx - 70 * r, cy - 170 * r, 34 * r, 12 * r, 120, -18)
    elif h == "fur_hat":
        fur = hc
        cv.shaded_poly([(cx - 108, cy - 92), (cx + 108, cy - 92), (cx + 96, cy - 250), (cx - 96, cy - 250)], fur, _sh(spec.hat_color, 0.72), off=(14, 8))
        for i in range(7):
            cv.ellipse(cx - 90 + i * 30, cy - 252, 22, 20, fur, width=6)
        cv.ellipse(cx, cy - 98, 132, 30, _sh(spec.hat_color, 0.86), width=8)
        cv.line([(cx - 104, cy - 130), (cx + 104, cy - 130)], 16, gold, outline=False)
    elif h == "kettle":
        st = (*spec.steel, 255)
        cv.shaded_ellipse(cx, cy - 128, 116, 76, st, (*STEEL_DARK, 255), width=8, off=(12, 9))
        cv.ellipse(cx, cy - 92, 196, 32, st, width=9)
        cv.shine(cx - 50, cy - 160, 40, 14, 150, -20)
        cv.ellipse(cx, cy - 190, 11, 11, (*STEEL_DARK, 255), width=5)
    elif h == "spiked":
        st = (*spec.steel, 255)
        cv.shaded_poly([(cx - 120, cy - 84), (cx + 120, cy - 84), (cx + 70, cy - 200), (cx + 12, cy - 290), (cx - 12, cy - 290), (cx - 70, cy - 200)], st,
                       (*STEEL_DARK, 255), off=(14, 8))
        cv.ellipse(cx, cy - 300, 12, 20, gold, width=6)
        cv.line([(cx - 118, cy - 98), (cx + 118, cy - 98)], 18, gold, outline=False)
        cv.shine(cx - 40, cy - 190, 20, 40, 130, 20)
    elif h == "feather_cap":
        cv.shaded_ellipse(cx, cy - 138, 118, 82, hc, _sh(spec.hat_color, 0.7), width=8, off=(12, 9))
        cv.line([(cx - 114, cy - 96), (cx + 114, cy - 100)], 26, (60, 50, 44, 255), ow=8)
        cv.ellipse(cx + 40, cy - 112, 18, 18, (214, 36, 52, 255), width=6)
        cv.ellipse(cx + 40, cy - 112, 6, 6, (255, 220, 224, 255), outline=False)
        cv.poly([(cx + 40, cy - 124), (cx + 150, cy - 230), (cx + 176, cy - 210), (cx + 120, cy - 150), (cx + 70, cy - 110)], (250, 248, 240, 255), width=6)
    elif h == "coif":
        cv.shaded_poly([(cx - 152, cy + 40), (cx - 140, cy - 100), (cx - 80, cy - 168), (cx, cy - 184), (cx + 80, cy - 168), (cx + 140, cy - 100), (cx + 152, cy + 40),
                        (cx + 120, cy + 20), (cx + 112, cy - 70), (cx, cy - 100), (cx - 112, cy - 70), (cx - 120, cy + 20)], hc, _sh(spec.hat_color, 0.82), off=(12, 8))
    elif h == "straw":
        cv.ellipse(cx, cy - 92, 236, 40, (232, 196, 100, 255), width=9)
        cv.shaded_ellipse(cx, cy - 138, 104, 62, (240, 206, 112, 255), (200, 160, 70, 255), width=8, off=(10, 8))
        cv.line([(cx - 100, cy - 112), (cx + 100, cy - 112)], 14, (150, 60, 50, 255), outline=False)
    elif h == "bork":
        cv.shaded_poly([(cx - 100, cy - 90), (cx + 100, cy - 90), (cx + 84, cy - 270), (cx - 84, cy - 270)], hc, _sh(spec.hat_color, 0.8), off=(12, 8))
        cv.ellipse(cx, cy - 270, 84, 22, _sh(spec.hat_color, 1.0), width=7)
        cv.poly([(cx + 84, cy - 250), (cx + 160, cy - 230), (cx + 168, cy - 90), (cx + 100, cy - 100)], hc, width=7)
        cv.ellipse(cx - 6, cy - 150, 26, 36, gold, width=6)
    elif h == "crown_spike":
        cv.poly([(cx - 104, cy - 96), (cx + 104, cy - 96), (cx + 104, cy - 150), (cx + 62, cy - 124), (cx + 31, cy - 190), (cx, cy - 130), (cx - 31, cy - 190),
                 (cx - 62, cy - 124), (cx - 104, cy - 150)], gold)
        for k_ in (-1, 0, 1):
            cv.ellipse(cx + k_ * 54, cy - 108, 9, 9, (214, 36, 52, 255), outline=False)
    elif h == "witch":
        ink = (*spec.hat_color, 255)
        cv.shaded_poly([(cx - 104, cy - 96), (cx + 104, cy - 96), (cx + 62, cy - 250), (cx + 70, cy - 330), (cx + 10, cy - 392), (cx - 34, cy - 260)], ink, _sh(spec.hat_color, 0.6), off=(14, 8))
        cv.ellipse(cx, cy - 96, 214, 34, ink, width=8)
        cv.line([(cx - 100, cy - 128), (cx + 100, cy - 128)], 24, (112, 58, 130, 255), outline=False)
        cv.poly([(cx - 22, cy - 150), (cx + 22, cy - 150), (cx + 22, cy - 104), (cx - 22, cy - 104)], (236, 190, 70, 255), width=5)
    elif h == "dixie":   # білий матроський «dixie cup»: купол + відвернутий угору облямівок
        ink = (*spec.hat_color, 255)
        dark = _sh(spec.hat_color, 0.78)
        cv.shaded_ellipse(cx, cy - 124, 112, 72, ink, dark, width=8, off=(10, 8))
        cv.shaded_ellipse(cx, cy - 92, 148, 26, ink, dark, width=8, off=(8, 6))
        cv.line([(cx - 120, cy - 100), (cx + 120, cy - 100)], 8, _sh(spec.hat_color, 0.62), outline=False)
    elif h == "szyszak":   # шишак: сталевий купол з носовою планкою й пером
        ink = (*spec.hat_color, 255)
        dark = _sh(spec.hat_color, 0.62)
        cv.shaded_ellipse(cx, cy - 118, 128, 84, ink, dark, width=8, off=(12, 9))
        cv.line([(cx, cy - 76), (cx, cy + 40)], 14, ink, ow=6)            # носова планка
        cv.line([(cx - 124, cy - 104), (cx + 124, cy - 104)], 10, dark, outline=False)
        cv.poly([(cx - 8, cy - 196), (cx + 8, cy - 196), (cx + 30, cy - 330), (cx + 4, cy - 300)], (214, 40, 52, 255), width=5)   # пір'їна
        cv.shine(cx - 50, cy - 160, 36, 12, 120, -20)
    elif h == "brodie":   # британська/американська каска WWI: плоска «тарілка» з широкими полями
        ink = (*spec.hat_color, 255)
        dark = _sh(spec.hat_color, 0.66)
        cv.shaded_ellipse(cx, cy - 104, 170, 40, ink, dark, width=8, off=(10, 7))
        cv.shaded_ellipse(cx, cy - 118, 90, 38, _sh(spec.hat_color, 1.1), dark, width=7, off=(8, 6))
        cv.line([(cx - 150, cy - 96), (cx - 124, cy + 36)], 7, (60, 44, 30, 255), outline=False)
        cv.line([(cx + 150, cy - 96), (cx + 124, cy + 36)], 7, (60, 44, 30, 255), outline=False)
    elif h == "boonie":   # польовий капелюх із обвислими крисами
        ink = (*spec.hat_color, 255)
        dark = _sh(spec.hat_color, 0.66)
        cv.shaded_ellipse(cx, cy - 96, 176, 34, ink, dark, width=8, off=(10, 7))
        cv.shaded_poly([(cx - 96, cy - 100), (cx + 96, cy - 100), (cx + 84, cy - 176), (cx - 84, cy - 176)], ink, dark, off=(12, 8), width=8)
        cv.ellipse(cx, cy - 176, 84, 16, _sh(spec.hat_color, 1.12), width=7)
        cv.line([(cx - 92, cy - 118), (cx + 92, cy - 118)], 12, dark, outline=False)
    elif h == "m1":   # сталевий шолом М1 (США, 2-га світова)
        ink = (*spec.hat_color, 255)
        dark = _sh(spec.hat_color, 0.66)
        cv.shaded_ellipse(cx, cy - 124, 142, 80, ink, dark, width=8, off=(12, 9))
        cv.shaded_ellipse(cx, cy - 92, 168, 20, ink, dark, width=8, off=(8, 6))
        cv.line([(cx - 120, cy - 82), (cx - 130, cy + 40)], 8, (70, 52, 36, 255), outline=False)     # ремінець
        cv.line([(cx + 120, cy - 82), (cx + 130, cy + 40)], 8, (70, 52, 36, 255), outline=False)
        for k_ in range(5):
            cv.line([(cx - 90 + k_ * 45, cy - 168), (cx - 80 + k_ * 45, cy - 120)], 4, dark, outline=False)   # сітка маскування
    elif h == "peaked":   # офіцерська кашкет-«грибок»
        ink = (*spec.hat_color, 255)
        dark = _sh(spec.hat_color, 0.62)
        cv.shaded_poly([(cx - 118, cy - 100), (cx + 118, cy - 100), (cx + 150, cy - 176), (cx - 150, cy - 176)], ink, dark, off=(12, 8), width=8)
        cv.ellipse(cx, cy - 176, 150, 24, _sh(spec.hat_color, 1.15), width=8)
        cv.line([(cx - 118, cy - 108), (cx + 118, cy - 108)], 16, (30, 26, 22, 255), outline=False)
        cv.shaded_ellipse(cx, cy - 86, 120, 16, (24, 22, 22, 255), (12, 12, 12, 255), width=7, off=(6, 5))   # козирок
        cv.ellipse(cx, cy - 142, 14, 14, (214, 180, 70, 255), width=5)
    elif h == "campaign":
        ink = (*spec.hat_color, 255)
        dark = _sh(spec.hat_color, 0.62)
        cv.shaded_ellipse(cx, cy - 98, 190, 28, ink, dark, width=8, off=(10, 7))
        cv.shaded_poly([(cx - 78, cy - 100), (cx + 78, cy - 100), (cx + 62, cy - 190), (cx - 62, cy - 190)], ink, dark, off=(12, 8), width=8)
        cv.ellipse(cx, cy - 190, 62, 14, _sh(spec.hat_color, 1.2), width=7)
        cv.line([(cx - 76, cy - 120), (cx + 76, cy - 120)], 14, (60, 44, 30, 255), outline=False)
    elif h == "helmet":
        ink = (*spec.hat_color, 255)
        dark = _sh(spec.hat_color, 0.7)
        cv.shaded_ellipse(cx, cy - 128, 138, 86, ink, dark, width=8, off=(12, 9))
        cv.line([(cx, cy - 212), (cx, cy - 112)], 18, (214, 60, 52, 255), outline=False)
        cv.shine(cx - 60, cy - 164, 40, 14, 130, -20)
    elif h == "cap":
        ink = (*spec.hat_color, 255)
        dark = _sh(spec.hat_color, 0.7)
        cv.shaded_ellipse(cx, cy - 128, 126, 74, ink, dark, width=8, off=(12, 9))
        cv.shaded_ellipse(cx + 30, cy - 98, 132, 22, dark, _sh(spec.hat_color, 0.55), width=8, off=(8, 6))        # козирок
        cv.line([(cx, cy - 200), (cx, cy - 112)], 5, dark, outline=False)
        cv.ellipse(cx, cy - 200, 12, 10, dark, outline=False)
    elif h == "top_hat":
        ink = (*spec.hat_color, 255)
        cv.ellipse(cx, cy - 98, 196, 30, ink, width=8)
        cv.shaded_poly([(cx - 110, cy - 100), (cx + 110, cy - 100), (cx + 104, cy - 300), (cx - 104, cy - 300)], ink, _sh(spec.hat_color, 0.6), off=(14, 8))
        cv.ellipse(cx, cy - 300, 104, 26, _sh(spec.hat_color, 1.25), width=8)
        cv.line([(cx - 108, cy - 138), (cx + 108, cy - 138)], 22, (150, 36, 44, 255), outline=False)
        cv.shine(cx - 60, cy - 220, 10, 54, 110, 4)
    elif h == "bowler":
        ink = (*spec.hat_color, 255)
        cv.shaded_ellipse(cx, cy - 132, 116, 86, ink, _sh(spec.hat_color, 0.6), width=8, off=(12, 9))
        cv.ellipse(cx, cy - 94, 168, 24, ink, width=8)
        cv.line([(cx - 112, cy - 110), (cx + 112, cy - 110)], 16, (80, 70, 70, 255), outline=False)
        cv.shine(cx - 50, cy - 170, 36, 12, 120, -18)
    elif h == "bonnet":
        cv.shaded_ellipse(cx - 6, cy - 78, 112, 56, hc, _sh(spec.hat_color, 0.82), width=8, off=(10, 7))
        cv.line([(cx - 112, cy - 56), (cx - 118, cy + 14), (cx - 96, cy + 54)], 12, (*spec.trim, 255), ow=5)
        cv.ellipse(cx + 52, cy - 106, 26, 18, (*spec.trim, 255), width=5)
    elif h == "headband":
        cv.line([(cx - 138, cy - 56), (cx + 138, cy - 62)], 28, (210, 52, 52, 255), ow=8)



def _bell_body(cv: _Canvas, spec: CharacterSpec, top_y: float, hem_y: float, sway: float, walking: bool):
    robe_c = (*spec.robe, 255)
    trim_c = (*spec.trim, 255)
    if spec.style == "robe":
        pts_l, pts_r = [], []
        n = 14
        for i in range(n + 1):
            t = i / n
            half = 104 + 112 * t ** 1.25
            y = top_y + (hem_y - top_y) * t
            dx = sway * t
            pts_l.append((500 - half + dx, y))
            pts_r.append((500 + half + dx, y))
        # трохи хвилястий поділ
        hem = [(500 + 216 + sway - j * 36, hem_y + 4 + (6 if j % 2 else 0)) for j in range(0, 13)]
        body = pts_l + [(500 - 216 + sway + j * 36, hem_y + 4 + (6 if j % 2 else 0)) for j in range(0, 13)] + pts_r[::-1]
        cv.shaded_poly(body, robe_c, _sh(spec.robe, 0.78), off=(22, 10))
        # смуга на подолі
        cv.line([(500 - 214 + sway, hem_y - 14), (500 + 214 + sway, hem_y - 14)], 22, trim_c, outline=False, ow=0)
        # складки
        for fx in (-80, 0, 84):
            cv.line([(500 + fx * 0.5 + sway * 0.3, top_y + 210), (500 + fx * 1.15 + sway, hem_y - 26)], 5, _sh(spec.robe, 0.7), outline=False)
        # пояс-шарф з вузлом
        by = top_y + 215
        cv.line([(500 - 128, by), (500, by + 20), (500 + 128 + sway * 0.25, by)], 24, (*spec.trim, 255), ow=7)
        cv.ellipse(500 + 24, by + 24, 17, 22, (*spec.trim, 255), width=6)
        # комір
        cv.poly([(500 - 56, top_y - 6), (500, top_y + 82), (500 + 56, top_y - 6)], (244, 240, 228, 255), width=6)
    elif spec.style == "frock":
        tun = (*spec.robe, 255)
        hem = 842
        cv.shaded_poly([(500 - 104, top_y + 10), (500 + 104, top_y + 10), (500 + 134 + sway * 0.4, hem), (500 - 134 + sway * 0.4, hem)], tun,
                       _sh(spec.robe, 0.78), off=(20, 8))
        cv.poly([(500 - 52, top_y - 4), (500 + 52, top_y - 4), (500 + 34, hem - 40), (500 - 34, hem - 40)], (236, 230, 216, 255), width=6)     # сорочка
        cv.poly([(500 - 40, top_y + 70), (500 + 40, top_y + 70), (500 + 32, hem - 140), (500 - 32, hem - 140)], (*spec.trim, 255), width=6)     # жилет
        for k_ in range(4):
            cv.ellipse(500, top_y + 100 + k_ * 62, 7, 7, (240, 220, 160, 255), outline=False)
        cv.poly([(500 - 40, top_y + 4), (500 - 12, top_y + 14), (500, top_y + 70), (500 - 70, top_y + 160), (500 - 98, top_y + 40)], tun, width=6)   # лацкани
        cv.poly([(500 + 40, top_y + 4), (500 + 12, top_y + 14), (500, top_y + 70), (500 + 70, top_y + 160), (500 + 98, top_y + 40)], tun, width=6)
        cv.poly([(500 - 18, top_y + 2), (500 + 18, top_y + 2), (500 + 12, top_y + 52), (500 - 12, top_y + 52)], (190, 50, 56, 255), width=5)       # краватка-метелик/хустка
    elif spec.style in ("tunic", "armor"):
        tun = (*spec.robe, 255)
        hem = 700
        pts = [(500 - 104, top_y + 10), (500 + 104, top_y + 10), (500 + 128 + sway * 0.4, hem), (500 - 128 + sway * 0.4, hem)]
        cv.shaded_poly(pts, tun, _sh(spec.robe, 0.78), off=(20, 8))
        cv.line([(500 - 126 + sway * 0.4, hem - 10), (500 + 126 + sway * 0.4, hem - 10)], 20, trim_c, outline=False, ow=0)
        by = top_y + 200
        cv.line([(500 - 110, by), (500 + 110, by)], 22, (70, 48, 34, 255), ow=7)
        cv.poly([(500 - 18, by - 16), (500 + 18, by - 16), (500 + 18, by + 16), (500 - 18, by + 16)], trim_c, width=6)
        for fx in (-60, 0, 60):
            cv.line([(500 + fx, by + 14), (500 + fx * 1.1 + sway * 0.3, hem - 24)], 4, _sh(spec.robe, 0.68), outline=False)
        if spec.gear:   # плитоноска, підсумки, ремені на плечах
            pc = (44, 46, 42, 255)
            cv.shaded_poly([(500 - 88, top_y + 14), (500 + 88, top_y + 14), (500 + 80, by + 6), (500 - 80, by + 6)], pc, (26, 28, 26, 255), off=(14, 8))
            cv.line([(500 - 80, top_y + 6), (500 - 46, top_y - 14)], 18, (30, 32, 30, 255), ow=5)
            cv.line([(500 + 80, top_y + 6), (500 + 46, top_y - 14)], 18, (30, 32, 30, 255), ow=5)
            for fx_ in (-52, 0, 52):
                cv.shaded_poly([(500 + fx_ - 22, by - 84), (500 + fx_ + 22, by - 84), (500 + fx_ + 22, by - 6), (500 + fx_ - 22, by - 6)], (58, 60, 54, 255), (34, 36, 32, 255), off=(5, 4), width=6)
            cv.poly([(500 - 30, top_y + 52), (500 + 30, top_y + 52), (500 + 30, top_y + 72), (500 - 30, top_y + 72)], (186, 180, 160, 255), width=4)
        if spec.style == "armor":
            st = (*spec.steel, 255)
            cv.shaded_poly([(500 - 98, top_y + 4), (500 + 98, top_y + 4), (500 + 88, by + 4), (500 - 88, by + 4)], st, (*STEEL_DARK, 255), off=(18, 8))
            cv.line([(500 - 70, top_y + 70), (500 + 70, top_y + 70)], 6, (*STEEL_DARK, 255), outline=False)
            cv.line([(500, top_y + 20), (500, by)], 6, (*STEEL_DARK, 255), outline=False)
            cv.shine(500 - 44, top_y + 70, 22, 54, 140, 8)
        cv.poly([(500 - 50, top_y - 8), (500, top_y + 56), (500 + 50, top_y - 8)], (232, 224, 208, 255), width=6)
        if spec.fur:
            for i in range(9):
                cv.ellipse(500 - 88 + i * 22, top_y + 2, 20, 17, (238, 232, 220, 255), width=5)
    elif spec.style == "kaftan":
        pts_l, pts_r = [], []
        for i in range(15):
            t = i / 14
            half = 100 + 78 * t ** 1.2
            y = top_y + (hem_y - top_y) * t
            pts_l.append((500 - half + sway * t, y))
            pts_r.append((500 + half + sway * t, y))
        cv.shaded_poly(pts_l + pts_r[::-1], robe_c, _sh(spec.robe, 0.76), off=(22, 10))
        cv.poly([(500 - 40, top_y), (500 + 40, top_y), (500 + 28 + sway, hem_y), (500 - 28 + sway, hem_y)], (*[min(255, int(v * 0.55 + 90)) for v in spec.robe], 255), width=6)
        for i in range(7):
            cv.ellipse(500 + sway * i / 12, top_y + 56 + i * 62, 10, 10, trim_c, width=4)
        by = top_y + 232
        cv.line([(500 - 118, by), (500 + 118 + sway * 0.25, by)], 28, trim_c, ow=7)
        cv.line([(500 - 214 + sway, hem_y - 14), (500 + 214 + sway, hem_y - 14)], 18, trim_c, outline=False, ow=0)
        if spec.fur:
            for i in range(11):
                cv.ellipse(500 - 100 + i * 20, top_y + 4, 22, 20, (236, 230, 216, 255), width=5)
    else:
        skin_c = (*spec.skin, 255)
        torso = [(500 - 102, top_y + 10), (500 + 102, top_y + 10), (500 + 90, 560), (500 - 90, 560)]
        cv.shaded_poly(torso, skin_c, _sh(spec.skin, 0.84), off=(20, 8))
        # широкий комір-«усех»
        cv.arc((500 - 100, top_y - 40, 500 + 100, top_y + 130), 20, 160, 36, trim_c)
        cv.arc((500 - 100, top_y - 40, 500 + 100, top_y + 130), 20, 160, 5, OUT)
        kilt = [(500 - 96, 540), (500 + 96, 540), (500 + 150 + sway, 820), (500 - 150 + sway, 820)]
        cv.shaded_poly(kilt, (244, 240, 228, 255), (214, 208, 196, 255), off=(24, 8))
        cv.line([(500 - 96, 550), (500 + 96, 550)], 20, trim_c, outline=False, ow=0)
        for fx in (-70, 0, 70):
            cv.line([(500 + fx * 0.7, 566), (500 + fx * 1.0 + sway * 0.5, 800)], 4, (200, 194, 180, 255), outline=False)
        cv.poly([(500 - 150 + sway, 800), (500 + 150 + sway, 800), (500 + 154 + sway, 822), (500 - 154 + sway, 822)], trim_c, width=6)


def _held_item(cv: _Canvas, spec: CharacterSpec, hx: float, hy: float):
    """Предмет у правій руці: списа/меч/ятаган/смолоскип/прапор/вила/кубок. Тримається вертикально (хват у центрі)."""
    st, sd = (*spec.steel, 255), (*STEEL_DARK, 255)
    wood = (140, 96, 58, 255)
    it = spec.item
    if it == "spear":
        cv.line([(hx + 4, hy + 330), (hx - 2, hy - 430)], 15, wood)
        cv.poly([(hx - 28, hy - 430), (hx + 24, hy - 430), (hx - 2, hy - 560)], st, width=7)
    elif it == "pitchfork":
        cv.line([(hx + 4, hy + 320), (hx - 2, hy - 360)], 15, wood)
        cv.line([(hx - 42, hy - 470), (hx - 42, hy - 360), (hx + 38, hy - 360), (hx + 38, hy - 470)], 12, sd, ow=6)
        cv.line([(hx - 2, hy - 480), (hx - 2, hy - 360)], 12, sd, ow=6)
    elif it == "torch":
        cv.line([(hx + 2, hy + 150), (hx - 2, hy - 250)], 18, wood)
        cv.poly([(hx - 40, hy - 250), (hx + 36, hy - 250), (hx + 52, hy - 330), (hx + 8, hy - 470), (hx - 12, hy - 360), (hx - 48, hy - 330)], (255, 150, 40, 255), width=7)
        cv.poly([(hx - 18, hy - 262), (hx + 20, hy - 262), (hx + 28, hy - 320), (hx + 4, hy - 400), (hx - 24, hy - 320)], (255, 226, 110, 255), outline=False)
    elif it == "banner":
        cv.line([(hx + 2, hy + 330), (hx - 2, hy - 520)], 15, wood)
        cv.poly([(hx - 4, hy - 510), (hx + 220, hy - 480), (hx + 190, hy - 400), (hx + 224, hy - 320), (hx - 4, hy - 300)], (176, 30, 44, 255), width=7)
        cv.ellipse(hx + 100, hy - 405, 36, 36, (232, 186, 70, 255), width=6)
        cv.ellipse(hx - 2, hy - 524, 14, 14, (232, 186, 70, 255), width=5)
    elif it == "sword":
        cv.poly([(hx - 12, hy - 40), (hx + 12, hy - 40), (hx + 10, hy - 420), (hx, hy - 470), (hx - 10, hy - 420)], st, width=6)
        cv.line([(hx - 56, hy - 40), (hx + 56, hy - 40)], 16, (150, 110, 50, 255))
    elif it == "scimitar":
        pts = []
        for i in range(11):
            t = i / 10
            pts.append((hx + 110 * math.sin(t * 1.3) * t, hy - 40 - 440 * t))
        cv.line(pts, 22, st, ow=6)
        cv.line([(hx - 50, hy - 40), (hx + 50, hy - 40)], 16, (150, 110, 50, 255))
    elif it == "cb_mic":
        cv.line([(hx, hy + 30), (hx + 50, hy + 120), (hx + 20, hy + 190)], 7, (30, 30, 34, 255), outline=False)
        cv.shaded_poly([(hx - 30, hy - 56), (hx + 30, hy - 56), (hx + 36, hy + 40), (hx - 36, hy + 40)], (46, 46, 54, 255), (24, 24, 30, 255), off=(6, 5), width=7)
        for k_ in range(3):
            cv.line([(hx - 18, hy - 34 + k_ * 20), (hx + 18, hy - 34 + k_ * 20)], 5, (170, 170, 180, 255), outline=False)
    elif it == "broom":
        cv.line([(hx, hy + 60), (hx, hy - 330)], 20, (150, 108, 64, 255))
        cv.poly([(hx - 50, hy + 150), (hx + 50, hy + 150), (hx + 22, hy + 40), (hx - 22, hy + 40)], (214, 176, 84, 255), width=7)
        cv.line([(hx - 20, hy + 60), (hx - 28, hy + 140)], 5, (150, 112, 56, 255), outline=False)
        cv.line([(hx + 20, hy + 60), (hx + 28, hy + 140)], 5, (150, 112, 56, 255), outline=False)
    elif it == "cross":
        cv.line([(hx, hy + 20), (hx, hy - 260)], 24, (236, 190, 70, 255))
        cv.line([(hx - 80, hy - 180), (hx + 80, hy - 180)], 24, (236, 190, 70, 255))
        cv.ellipse(hx, hy - 180, 14, 14, (214, 36, 52, 255), width=5)
    elif it == "stake":
        cv.poly([(hx - 18, hy + 60), (hx + 18, hy + 60), (hx + 14, hy - 330), (hx, hy - 420), (hx - 14, hy - 330)], (170, 120, 70, 255), width=7)
        cv.line([(hx - 4, hy + 40), (hx - 2, hy - 300)], 5, (130, 88, 50, 255), outline=False)
    elif it == "garlic":
        for k_, (dx, dy) in enumerate([(-34, -90), (34, -90), (0, -150)]):
            cv.poly([(hx + dx - 36, hy + dy + 40), (hx + dx + 36, hy + dy + 40), (hx + dx + 24, hy + dy - 20), (hx + dx, hy + dy - 56), (hx + dx - 24, hy + dy - 20)],
                    (248, 244, 232, 255), width=6)
        cv.line([(hx, hy - 150), (hx, hy - 220)], 8, (96, 130, 70, 255), outline=False)
    elif it == "lantern":
        cv.line([(hx, hy - 70), (hx, hy - 170)], 8, (60, 50, 44, 255), outline=False)
        cv.poly([(hx - 50, hy + 40), (hx + 50, hy + 40), (hx + 40, hy - 70), (hx - 40, hy - 70)], (255, 214, 110, 255), width=7)
        cv.poly([(hx - 56, hy - 70), (hx + 56, hy - 70), (hx, hy - 120)], (70, 60, 56, 255), width=6)
    elif it == "cup":
        cv.poly([(hx - 50, hy - 150), (hx + 50, hy - 150), (hx + 34, hy - 60), (hx + 8, hy - 40), (hx + 8, hy), (hx + 34, hy + 12), (hx - 34, hy + 12), (hx - 8, hy), (hx - 8, hy - 40),
                 (hx - 34, hy - 60)], (240, 196, 70, 255), width=7)
        cv.shine(hx - 20, hy - 112, 10, 22, 170, 10)


def _staff(cv: _Canvas, hand):
    x, y = hand
    cv.line([(x, y - 470), (x + 4, y + 560)], 16, (150, 100, 60, 255))
    cv.ellipse(x, y - 480, 32, 32, (232, 186, 70, 255))


def _scroll(cv: _Canvas, wl, wr):
    cx, cy = (wl[0] + wr[0]) / 2, (wl[1] + wr[1]) / 2 - 8
    half = max(abs(wr[0] - wl[0]) / 2 + 20, 90)
    cv.poly([(cx - half, cy - 42), (cx + half, cy - 42), (cx + half, cy + 42), (cx - half, cy + 42)], (246, 232, 196, 255), width=7)
    for i in range(3):
        cv.line([(cx - half * .7, cy - 20 + i * 20), (cx + half * .7, cy - 20 + i * 20)], 6, (120, 92, 60, 255), outline=False)
    cv.ellipse(cx - half, cy, 14, 46, (216, 190, 140, 255), width=7)
    cv.ellipse(cx + half, cy, 14, 46, (216, 190, 140, 255), width=7)


def _draw(spec: CharacterSpec, pose: str, expr: str, mouth: int, phase: float, blink: bool, height_px: float) -> Image.Image:
    p = POSES.get(pose, POSES["stand"])
    k = (height_px / 1000.0) * SS
    cv = _Canvas(k)
    walking = p.get("walk", False)
    spd = p.get("speed", 1.0)
    swing = math.sin(phase * spd) if walking else 0.0
    bob = (abs(math.sin(phase * spd)) * -14 * spd) if walking else math.sin(phase * 0.7) * 3
    if p.get("shake"):
        bob = math.sin(phase * 6.0) * 9
    drop = p.get("drop", 0)
    lean = p.get("lean", 0)
    sh_up = p.get("shoulders", 0)
    skin_c = (*spec.skin, 255)
    hand_c = (*spec.glove, 255) if spec.glove else skin_c
    shoe = (150, 100, 60, 255)

    if spec.wings:   # крила за спиною (малюються першими: під усім): віяло з зубчастим зовнішнім краєм
        wing_top = 345 + bob + sh_up * 0.4 + drop
        ox, oy = 0, wing_top + 50
        for side in (-1, 1):
            pts = [(500 + side * 40, oy + 30)]
            n_f = 10
            for i in range(n_f + 1):
                ang = math.radians(112 - i * 8.8)
                ln = 340 + 60 * math.sin(i / n_f * math.pi)
                pts.append((500 + side * 60 + side * ln * math.cos(ang), oy - ln * math.sin(ang)))
                if i < n_f:
                    ang2 = math.radians(112 - (i + 0.5) * 8.8)
                    ln2 = ln * 0.8
                    pts.append((500 + side * 60 + side * ln2 * math.cos(ang2), oy - ln2 * math.sin(ang2)))
            cv.poly(pts, (240, 234, 220, 255), width=7)
            for i in range(1, n_f):
                ang = math.radians(112 - (i - 0.5) * 8.8)
                cv.line([(500 + side * 60, oy), (500 + side * 60 + side * 250 * math.cos(ang), oy - 250 * math.sin(ang))], 4, (196, 184, 160, 255), outline=False)
    # ноги / ступні (під одягом)
    if spec.cape:
        cc = (*spec.cape, 255)
        top_c = 335 + bob + drop
        cv.shaded_poly([(500 - 120, top_c), (500 + 120, top_c), (500 + 250 + swing * 14, 900), (500 + 170, 930), (500 + 90, 905), (500, 935), (500 - 90, 905),
                        (500 - 170, 930), (500 - 250 + swing * 14, 900)], cc, _sh(spec.cape, 0.72), off=(24, 10))
        cv.line([(500 - 120, top_c + 8), (500 + 120, top_c + 8)], 18, (*spec.trim, 255), outline=False, ow=0)
    for s in (-1, 1):
        fx = 500 + s * 76 + (s * swing * 46 if walking else 0)
        lift = max(0.0, s * swing) * 34 if walking else 0
        if spec.style in ("tunic", "armor", "frock"):
            sw = swing if walking else 0.0
            hip = (500 + s * 46, 700 if spec.style != "frock" else 780)
            lift_ = max(0.0, s * sw) * 30
            ank = (500 + s * 72 + s * sw * 30, 920 - lift_)                 # щиколотка: ступні не перехрещуються (крок ≤ ±30)
            knee = ((hip[0] + ank[0]) / 2 + s * 12, (hip[1] + ank[1]) / 2 - lift_ * 0.35)
            cv.noodle(hip, knee, ank, 56, 50, (*spec.legs, 255), shade=_sh(spec.legs, 0.78))
            bt = (*spec.boots, 255)
            ax, ay = ank
            cv.shaded_poly([(ax - 33, ay - 34), (ax + 33, ay - 34), (ax + 33, ay + 30), (ax - 33, ay + 30)], bt, _sh(spec.boots, 0.7), off=(8, 6), width=7)
            cv.shaded_ellipse(ax + s * 24, ay + 22, 48, 20, bt, _sh(spec.boots, 0.7), width=7, off=(6, 4))      # носок
            cv.line([(ax - 36, ay + 36), (ax + s * 70, ay + 36)], 10, (214, 206, 190, 255), outline=False)         # світла підошва: чобіт читається на темному пальті
            cv.line([(ax - 33, ay - 14), (ax + 33, ay - 14)], 6, _sh(spec.boots, 1.5), outline=False)               # манжета халяви
            if spec.straw:
                _straw(cv, ax, ay - 30, 5, 70, 34)
        elif spec.style in ("robe", "kaftan"):
            cv.shaded_ellipse(fx + s * 10, 922 - lift, 56, 28, shoe, _sh(shoe, 0.75), width=7, off=(8, 8))
        else:
            hip = (500 + s * 52, 780)
            foot = (fx, 924 - lift)
            mid = ((hip[0] + foot[0]) / 2 + s * 6, (hip[1] + foot[1]) / 2)
            cv.noodle(hip, mid, foot, 44, 34, skin_c, shade=_sh(spec.skin, 0.84))
            cv.shaded_ellipse(fx + s * 12, 942 - lift, 56, 26, shoe, _sh(shoe, 0.75), width=7, off=(8, 8))

    sway = swing * 18
    top_y = 345 + bob + sh_up * 0.4 + drop
    hem_y = 905
    if drop:
        hem_y = 905  # одяг «збирається»: нижня частина ховається за ступнями/землею
    _bell_body(cv, spec, top_y, hem_y, sway, walking)
    if spec.gloss:
        cv.shine(430, top_y + 150, 34, 120, 70, 8)
    if spec.high_collar:
        cc = (*(spec.cape or (24, 20, 30)), 255)
        base_y = top_y + 30
        r_ = spec.head_r
        for sx in (-1, 1):
            cv.shaded_poly([(500 + sx * 70, base_y), (500 + sx * 188 * r_, base_y - 20), (500 + sx * 230 * r_, 170 + bob - 120 * r_ * 0.2),
                            (500 + sx * 150 * r_, base_y - 150 * r_), (500 + sx * 96, base_y - 40)], cc, _sh(spec.cape or (24, 20, 30), 0.7), off=(12, 8))
            cv.poly([(500 + sx * 96, base_y - 40), (500 + sx * 150 * r_, base_y - 150 * r_), (500 + sx * 200 * r_, 180 + bob - 100 * r_ * 0.2),
                     (500 + sx * 120, base_y - 20)], (160, 28, 44, 255), width=5)

    if spec.straw:
        _straw(cv, 500, top_y + 70, 9, 190, 52)
    S_l, S_r = (404, top_y + 40), (596, top_y + 40)
    arm_l, arm_r = p["l"], p["r"]
    if walking:
        a = 22 * swing
        arm_l, arm_r = (arm_l[0] + a, arm_l[1] + a * .6), (arm_r[0] - a, arm_r[1] - a * .6)
    front = p.get("front", False)

    # шия + плечі
    cv.ellipse(500, top_y - 14, 44, 44, _sh(spec.skin, 0.92), width=7)
    for S in (S_l, S_r):
        cv.ellipse(S[0], S[1], 36 if spec.style != "armor" else 44, 36 if spec.style != "armor" else 44,
                   (*spec.steel, 255) if spec.style == "armor" else ((*spec.robe, 255) if spec.style in ("robe", "tunic", "kaftan", "frock") else skin_c), width=7)

    hands = {}

    def arms():
        if p.get("item") == "staff":
            hand = _limb(S_r, "r", *arm_r)[1]
            _staff(cv, hand)
        hands["l"] = _draw_arm(cv, spec, S_l, "l", *arm_l)
        hands["r"] = _draw_arm(cv, spec, S_r, "r", *arm_r)
        if p.get("item") == "scroll":
            _scroll(cv, hands["l"], hands["r"])
            for h in hands.values():
                cv.shaded_ellipse(h[0], h[1], 30, 28, hand_c, _sh(spec.glove or spec.skin, 0.84), width=7, off=(7, 6))
        elif spec.item and p.get("item") is None:
            hx, hy = hands["r"]
            _held_item(cv, spec, hx, hy)
            cv.shaded_ellipse(hx, hy, 30, 28, hand_c, _sh(spec.glove or spec.skin, 0.84), width=7, off=(7, 6))

    if not front:
        arms()
    _draw_head(cv, spec, expr, mouth, blink, bob + drop, look=0.0)
    _draw_hat(cv, spec, bob + drop)
    if front:
        arms()

    img = cv.img.resize((int(CW * k / SS), int(CH * k / SS)), Image.LANCZOS)
    if lean:
        img = img.rotate(-lean, resample=Image.BICUBIC, center=((500 - X0) * k / SS, (940 - Y0) * k / SS))
    return img


SPRITE_FX = None   # функція RGBA→RGBA для всіх спрайтів відео (стиль «силует»); виставляється стилем


def set_sprite_fx(fn) -> None:
    global SPRITE_FX
    SPRITE_FX = fn
    render.cache_clear()


@lru_cache(maxsize=220)
def render(spec: CharacterSpec, pose: str = "stand", expr: str = "neutral", mouth: int = 0, phase: float = 0.0,
           facing: int = 1, height_px: int = 520, blink: bool = False):
    """(RGBA-спрайт, (anchor_x, anchor_y)) — якір = центр стоп. facing=-1 віддзеркалює."""
    phase_q = round(phase * 4) / 4
    img = _draw(spec, pose, expr, mouth, phase_q, blink, height_px)
    if SPRITE_FX is not None:
        img = SPRITE_FX(img)
    k = height_px / 1000.0
    ax, ay = (500 - X0) * k, (1000 - Y0) * k
    bbox = img.getbbox()
    if bbox:
        img = img.crop(bbox)
        ax, ay = ax - bbox[0], ay - bbox[1]
    if facing < 0:
        img = img.transpose(Image.FLIP_LEFT_RIGHT)
        ax = img.width - ax
    return img, (ax, ay)
