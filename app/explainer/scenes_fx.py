"""«Паперові» сцени для Shorts замість персонажа на фоні: досьє з друкарським текстом і замазаними словами, подвійний кадр (до/після),
маршрут на карті. Малюються поверх кадру (непрозора картка, фон затемнено), під субтитрами. Поле біта: card = {"type": ...}."""
import math
import random
import textwrap

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .render import H, W, _emoji_img, ease_out, ease_out_back, smooth

COURIER_B = "C:/Windows/Fonts/courbd.ttf"
COURIER = "C:/Windows/Fonts/cour.ttf"
INK = "C:/Windows/Fonts/Inkfree.ttf"
_F: dict = {}
_PAPER: dict = {}


def _f(path: str, size: int):
    k = (path, size)
    if k not in _F:
        _F[k] = ImageFont.truetype(path, size)
    return _F[k]


def _paper(w: int, h: int, seed: int = 3, tone=(238, 228, 202)) -> Image.Image:
    key = (w, h, seed, tone)
    im = _PAPER.get(key)
    if im is None:
        rnd = np.random.RandomState(seed)
        base = np.ones((h, w, 3), np.float32) * np.array(tone, np.float32)
        base += rnd.normal(0, 4.5, (h, w, 1))
        blob = cv2.GaussianBlur(rnd.normal(0, 1, (h, w)).astype(np.float32), (0, 0), 38) * 90
        base += blob[..., None] * np.array([1.0, 0.9, 0.7], np.float32)
        yy, xx = np.mgrid[0:h, 0:w]
        edge = np.minimum(np.minimum(xx, w - xx), np.minimum(yy, h - yy)).astype(np.float32)
        base *= (0.82 + 0.18 * np.clip(edge / 90.0, 0, 1))[..., None]
        for fy in (h // 3, 2 * h // 3):   # складки
            base[fy: fy + 3] *= 0.93
            base[fy + 3: fy + 6] *= 1.04
        arr = np.clip(base, 0, 255).astype(np.uint8)
        im = Image.fromarray(arr).convert("RGBA")
        _PAPER[key] = im
    return im.copy()


def _dim_blur(frame: np.ndarray, k: float = 0.34) -> np.ndarray:
    small = cv2.resize(frame, (W // 6, H // 6), interpolation=cv2.INTER_AREA)
    small = cv2.GaussianBlur(small, (0, 0), 3.2)
    return (cv2.resize(small, (W, H), interpolation=cv2.INTER_LINEAR).astype(np.float32) * k).astype(np.uint8)


def _shadow(size, box, blur=22, alpha=170, off=(10, 16)) -> Image.Image:
    sh = Image.new("RGBA", size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).rectangle((box[0] + off[0], box[1] + off[1], box[2] + off[0], box[3] + off[1]), fill=(0, 0, 0, alpha))
    return sh.filter(ImageFilter.GaussianBlur(blur))


def _clip(d, x, y, ang_img=None):
    """Канцелярська скріпка у верхньому лівому куті аркуша."""
    pts = [(x, y + 70), (x, y), (x + 34, y), (x + 34, y + 96), (x + 12, y + 96), (x + 12, y + 22)]
    d.line(pts, fill=(150, 150, 158, 255), width=7, joint="curve")


def _parse(line: str):
    """«текст [[замазане]] далі» → [(слово, замазане?), ...] зі збереженням пробілів."""
    out, red = [], False
    for part in line.replace("[[", "\x01").replace("]]", "\x02").split("\x01"):
        if "\x02" in part:
            a, b = part.split("\x02", 1)
            out.append((a, True))
            if b:
                out.append((b, False))
        elif part:
            out.append((part, False))
    return out


def dossier(frame: np.ndarray, card: dict, age: float, dur: float) -> np.ndarray:
    """Аркуш досьє: шапка, друкарський текст, жовтий маркер на ключовому слові, чорні смуги, що з'їжджають."""
    base = Image.fromarray(_dim_blur(frame)).convert("RGBA")
    pw = 920
    cx, cy = W // 2, int(H * 0.44)
    size = int(card.get("size", 74))
    font = _f(COURIER_B, size)
    cw = font.getlength("M")
    maxch = int((pw - 128) / cw)
    lines = []
    for ln in card.get("lines", []):
        plain = ln.replace("[[", "").replace("]]", "")
        if "[[" not in ln:
            lines += textwrap.wrap(plain, maxch) or [""]
        else:   # з маркером: переносимо по словах, зберігаючи розмітку
            words, cur, curlen = ln.split(" "), [], 0
            for w_ in words:
                wl = len(w_.replace("[[", "").replace("]]", ""))
                if cur and curlen + 1 + wl > maxch:
                    lines.append(" ".join(cur)); cur, curlen = [w_], wl
                else:
                    cur.append(w_); curlen += wl + (1 if len(cur) > 1 else 0)
            if cur:
                lines.append(" ".join(cur))
    lh = int(size * 1.5)
    ph = int(min(max(290 + len(lines) * lh, 560), 1180))
    slide = 1.0 - min(ease_out_back(min(age / 0.34, 1.0), 1.5), 1.0)
    paper = _paper(pw, ph, seed=int(card.get("seed", 3)), tone=tuple(card.get("tone", (238, 228, 202))))
    d = ImageDraw.Draw(paper)
    ink = (36, 34, 30, 255)
    head = card.get("head", "CASE FILE")
    if card.get("kind") == "telegram":   # чорна шапка, пунктирні краї, великі літери
        d.rectangle((0, 0, pw, 96), fill=(20, 20, 20, 255))
        d.text((64, 66), head, font=_f(COURIER_B, 44), fill=(236, 226, 190, 255), anchor="ls")
        for yy_ in range(110, ph - 20, 26):
            d.line((14, yy_, 14, yy_ + 12), fill=(120, 100, 60, 255), width=4)
            d.line((pw - 14, yy_, pw - 14, yy_ + 12), fill=(120, 100, 60, 255), width=4)
        lines = [l.upper() for l in lines]
    else:
        d.text((64, 100), head, font=_f(COURIER_B, 40), fill=(150, 36, 36, 255), anchor="ls")
        d.line((64, 124, pw - 64, 124), fill=ink, width=4)
        d.line((64, 134, pw - 64, 134), fill=ink, width=1)
    sub = card.get("sub", "")
    if sub:
        d.text((pw - 64, 100), sub, font=_f(COURIER, 30), fill=(70, 66, 58, 255), anchor="rs")
    total_chars = sum(len(l.replace("[[", "").replace("]]", "")) for l in lines) or 1
    type_end = max(dur * 0.62, 0.9)
    shown = int(total_chars * min(max(age - 0.25, 0.0) / type_end, 1.0))
    reveal = max(0.0, min((age - dur * 0.66) / 0.35, 1.0))
    hot = card.get("hot")
    y = 230 + size // 2
    left = shown
    for ln in lines:
        segs = _parse(ln)
        x = 64
        for seg, red in segs:
            n = len(seg)
            take = max(0, min(n, left))
            txt = seg[:take]
            if hot and not red and hot in seg and left >= n:   # маркер під ключовим словом
                i0 = seg.index(hot)
                hx0 = x + cw * i0
                d.rectangle((hx0 - 6, y - size + 8, hx0 + cw * len(hot) + 6, y + 14), fill=(255, 224, 60, 255))
            d.text((x, y), txt, font=font, fill=ink, anchor="ls")
            if red:
                bw = cw * n
                vis = bw * (1.0 - smooth(reveal))
                if shown >= total_chars - 0 or left >= n:
                    d.rectangle((x - 4, y - size + 6, x - 4 + max(vis, 0) + 8, y + 12), fill=(14, 14, 14, 255))
            x += cw * n
            left -= n
        y += lh
    # курсор друкарки
    if shown < total_chars and int(age * 4) % 2 == 0:
        d.rectangle((64, 190, 76, 200), fill=ink)
    _clip(d, 70, -10)
    # складання сцени
    pos = (cx - pw // 2, int(cy - ph // 2 + slide * 900))
    ang = -2.2 + slide * 10
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    layer.alpha_composite(_shadow((W, H), (pos[0], pos[1], pos[0] + pw, pos[1] + ph)))
    rot = paper.rotate(ang, resample=Image.BICUBIC, expand=True)
    layer.alpha_composite(rot, (int(cx - rot.width / 2), int(pos[1] + ph / 2 - rot.height / 2)))
    base.alpha_composite(layer)
    return np.asarray(base.convert("RGB"))


def split(frame: np.ndarray, card: dict, age: float, dur: float) -> np.ndarray:
    """Два кадри один над одним (до / після, вигадка / реальність) із підписами-ярликами й бейджем між ними."""
    from . import assets
    base = Image.fromarray(_dim_blur(frame, 0.3)).convert("RGBA")
    pw, ph = 920, 500
    gap = 70
    top_y = int(H * 0.18)
    panels = []
    for i, key in enumerate((card.get("top"), card.get("bottom"))):
        try:
            im = Image.open(assets.ASSET_ROOT / "bgv" / f"{key}.png").convert("RGB")
        except Exception:   # noqa: BLE001
            im = Image.new("RGB", (768, 1344), (60, 60, 60))
        zoom = 1.0 + 0.06 * min(age / max(dur, 0.5), 1.0)
        iw, ih = im.size
        cw_, ch_ = iw / zoom, iw / zoom * ph / pw
        y0 = (ih - ch_) * (0.55 if i == 0 else 0.62)
        im = im.crop((int((iw - cw_) / 2), int(y0), int((iw + cw_) / 2), int(y0 + ch_))).resize((pw, ph), Image.LANCZOS)
        panels.append(im)
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    for i, im in enumerate(panels):
        t_in = smooth(min(max((age - 0.08 * i) / 0.3, 0.0), 1.0))
        x = int((W - pw) / 2 + (1 - t_in) * (-W if i == 0 else W))
        y = top_y + i * (ph + gap)
        layer.alpha_composite(_shadow((W, H), (x, y, x + pw, y + ph), blur=16, alpha=150, off=(8, 12)))
        card_im = Image.new("RGBA", (pw + 16, ph + 16), (240, 238, 230, 255))
        card_im.paste(im, (8, 8))
        layer.alpha_composite(card_im, (x - 8, y - 8))
        lab = card.get("labels", ["", ""])[i]
        if lab:
            dd = ImageDraw.Draw(layer)
            f = _f(COURIER_B, 44)
            tw = dd.textlength(lab, font=f)
            dd.rectangle((x + 18, y + ph - 82, x + 18 + tw + 40, y + ph - 18), fill=(12, 12, 12, 235))
            dd.text((x + 38, y + ph - 34), lab, font=f, fill=(244, 240, 226, 255), anchor="ls")
    badge = card.get("badge", "VS")
    if age > 0.3:
        s = ease_out_back(min((age - 0.3) / 0.25, 1.0), 2.2)
        dd = ImageDraw.Draw(layer)
        cy_ = top_y + ph + gap // 2
        r = int(58 * max(s, 0.05))
        dd.ellipse((W // 2 - r, cy_ - r, W // 2 + r, cy_ + r), fill=(196, 40, 40, 255), outline=(244, 240, 226, 255), width=6)
        dd.text((W // 2, cy_ + 2), badge, font=_f(COURIER_B, int(54 * max(s, 0.05))), fill=(244, 240, 226, 255), anchor="mm")
    base.alpha_composite(layer)
    return np.asarray(base.convert("RGB"))


_MAP: dict = {}


def _auto_map(pw: int, ph: int, seed: int) -> Image.Image:
    """Процедурна карта без тексту: пергамент, сітка широт/довгот, суша по краях (шум + градієнт), рамка."""
    key = (pw, ph, seed)
    im = _MAP.get(key)
    if im is None:
        rnd = np.random.RandomState(seed)
        base = np.asarray(_paper(pw, ph, seed=seed, tone=(226, 208, 168)).convert("RGB")).astype(np.float32)
        low = cv2.GaussianBlur(rnd.normal(0, 1, (ph // 8, pw // 8)).astype(np.float32), (0, 0), 3.0)
        low = cv2.resize(low, (pw, ph), interpolation=cv2.INTER_CUBIC)
        xx = np.linspace(0, 1, pw, dtype=np.float32)[None, :]
        edge = np.maximum(1.0 - xx / 0.34, 0) + np.maximum((xx - 0.66) / 0.34, 0)
        land = (low * 2.6 + edge * 1.5) > 0.9
        land = cv2.GaussianBlur(land.astype(np.float32), (0, 0), 2.2) > 0.5
        base[land] = base[land] * np.array([0.84, 0.88, 0.74], np.float32)
        edge_m = cv2.dilate(land.astype(np.uint8), np.ones((5, 5), np.uint8)) - cv2.erode(land.astype(np.uint8), np.ones((5, 5), np.uint8))
        base[edge_m > 0] = base[edge_m > 0] * 0.55
        arr = np.clip(base, 0, 255).astype(np.uint8)
        im = Image.fromarray(arr)
        d = ImageDraw.Draw(im)
        for gx in range(1, 7):
            d.line((gx * pw / 7, 0, gx * pw / 7, ph), fill=(150, 126, 90), width=2)
        for gy in range(1, 8):
            d.line((0, gy * ph / 8, pw, gy * ph / 8), fill=(150, 126, 90), width=2)
        d.rectangle((6, 6, pw - 7, ph - 7), outline=(90, 66, 40), width=6)
        _MAP[key] = im
    return im.copy()


def route(frame: np.ndarray, card: dict, age: float, dur: float) -> np.ndarray:
    """Маршрут на карті: пунктирна лінія малюється до точок, шпильки з підписами, значок літака на кінці."""
    from . import assets
    base = Image.fromarray(_dim_blur(frame, 0.3)).convert("RGBA")
    pw, ph = 920, 1000
    cx, cy = W // 2, int(H * 0.45)
    mp = _auto_map(pw, ph, int(card.get("seed", 7)))
    d = ImageDraw.Draw(mp)
    pts = [(p[0] * pw, p[1] * ph) for p in card.get("pts", [(0.15, 0.8), (0.85, 0.2)])]
    seg = [math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]
    total = sum(seg) or 1
    prog = smooth(min(max((age - 0.2) / max(dur * 0.7, 0.8), 0.0), 1.0)) * total
    drawn, head = 0.0, pts[0]
    for i, L in enumerate(seg):
        a, b = pts[i], pts[i + 1]
        take = max(0.0, min(prog - drawn, L))
        if take > 0:
            e = (a[0] + (b[0] - a[0]) * take / L, a[1] + (b[1] - a[1]) * take / L)
            n = int(take // 26) + 1
            for k in range(n):
                u0, u1 = k * 26 / take, min((k * 26 + 14) / take, 1.0)
                if u0 >= 1.0:
                    break
                p0 = (a[0] + (e[0] - a[0]) * u0, a[1] + (e[1] - a[1]) * u0)
                p1 = (a[0] + (e[0] - a[0]) * u1, a[1] + (e[1] - a[1]) * u1)
                d.line((p0, p1), fill=(176, 30, 30), width=9)
            head = e
        drawn += L
    labels = card.get("labels", [])
    for i, p in enumerate(pts):
        reached = (sum(seg[:i]) <= prog + 1)
        if not reached:
            continue
        d.ellipse((p[0] - 17, p[1] - 17, p[0] + 17, p[1] + 17), fill=(176, 30, 30), outline=(250, 244, 230), width=5)
        if i < len(labels) and labels[i]:
            f = _f(COURIER_B, 40)
            tw = d.textlength(labels[i], font=f)
            lx = min(max(p[0] - tw / 2, 20), pw - tw - 36)
            ly = p[1] - 70 if p[1] > 150 else p[1] + 30
            d.rectangle((lx - 10, ly - 4, lx + tw + 22, ly + 52), fill=(14, 14, 14))
            d.text((lx + 6, ly + 42), labels[i], font=f, fill=(244, 240, 226), anchor="ls")
    # значок літака (трикутник) на кінці лінії
    ang = math.atan2(pts[-1][1] - pts[0][1], pts[-1][0] - pts[0][0])
    tri = [(head[0] + 34 * math.cos(ang), head[1] + 34 * math.sin(ang)),
           (head[0] + 22 * math.cos(ang + 2.5), head[1] + 22 * math.sin(ang + 2.5)),
           (head[0] + 22 * math.cos(ang - 2.5), head[1] + 22 * math.sin(ang - 2.5))]
    d.polygon(tri, fill=(20, 20, 20), outline=(250, 244, 230))
    frame_im = Image.new("RGBA", (pw + 20, ph + 20), (244, 240, 226, 255))
    frame_im.paste(mp, (10, 10))
    slide = 1.0 - min(ease_out_back(min(age / 0.32, 1.0), 1.4), 1.0)
    pos = (cx - pw // 2 - 10, int(cy - ph // 2 - 10 + slide * 900))
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    layer.alpha_composite(_shadow((W, H), (pos[0], pos[1], pos[0] + pw + 20, pos[1] + ph + 20)))
    rot = frame_im.rotate(1.6 + slide * 8, resample=Image.BICUBIC, expand=True)
    layer.alpha_composite(rot, (int(cx - rot.width / 2), int(pos[1] + (ph + 20) / 2 - rot.height / 2)))
    base.alpha_composite(layer)
    return np.asarray(base.convert("RGB"))


def timeline(frame: np.ndarray, card: dict, age: float, dur: float) -> np.ndarray:
    """Вертикальна часова шкала на пергаменті: віхи (рік + підпис) виринають по черзі."""
    base = Image.fromarray(_dim_blur(frame, 0.3)).convert("RGBA")
    items = card.get("items", [])
    n = max(len(items), 1)
    pw, row = 920, 230
    ph = 200 + row * n
    paper = _paper(pw, ph, seed=int(card.get("seed", 5)), tone=(226, 208, 168))
    d = ImageDraw.Draw(paper)
    d.text((pw // 2, 100), card.get("head", "TIMELINE"), font=_f(COURIER_B, 44), fill=(110, 30, 30, 255), anchor="mm")
    lx = 190
    d.line((lx, 170, lx, ph - 60), fill=(90, 60, 34, 255), width=8)
    span = max(dur * 0.78, 1.0)
    for i, (yr, txt) in enumerate(items):
        t_i = 0.2 + span * i / n
        q = ease_out_back(min(max((age - t_i) / 0.3, 0.0), 1.0), 1.8)
        if q <= 0.02:
            continue
        y = 170 + row * i + 80
        r = int(24 * q)
        d.ellipse((lx - r, y - r, lx + r, y + r), fill=(150, 26, 40, 255), outline=(60, 30, 20, 255), width=5)
        d.text((lx + 56, y - 8), str(yr), font=_f(COURIER_B, int(76 * min(q, 1.0))), fill=(40, 30, 20, 255), anchor="lm")
        d.text((lx + 56, y + 56), txt, font=_f(COURIER_B, 33), fill=(90, 62, 36, 255), anchor="lm")
    slide = 1.0 - min(ease_out_back(min(age / 0.32, 1.0), 1.4), 1.0)
    cx, cy = W // 2, int(H * 0.46)
    pos = (cx - pw // 2, int(cy - ph // 2 + slide * 900))
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    layer.alpha_composite(_shadow((W, H), (pos[0], pos[1], pos[0] + pw, pos[1] + ph)))
    rot = paper.rotate(-1.4 + slide * 8, resample=Image.BICUBIC, expand=True)
    layer.alpha_composite(rot, (int(cx - rot.width / 2), int(pos[1] + ph / 2 - rot.height / 2)))
    base.alpha_composite(layer)
    return np.asarray(base.convert("RGB"))


def stat(frame: np.ndarray, card: dict, age: float, dur: float) -> np.ndarray:
    """Величезне число, що рахується від 0, на темній панелі з променями; підпис під ним."""
    from .render import _font
    base = Image.fromarray(_dim_blur(frame, 0.22)).convert("RGBA")
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    cx, cy = W // 2, int(H * 0.42)
    for k in range(18):   # промені
        a0 = math.radians(k * 20 + age * 8)
        a1 = a0 + math.radians(9)
        d.polygon([(cx, cy), (cx + 1500 * math.cos(a0), cy + 1500 * math.sin(a0)), (cx + 1500 * math.cos(a1), cy + 1500 * math.sin(a1))], fill=(236, 196, 96, 26))
    val = float(card.get("value", 100))
    q = smooth(min(max((age - 0.1) / max(dur * 0.55, 0.7), 0.0), 1.0))
    cur = int(val * q)
    txt = f"{cur:,}" + str(card.get("suffix", ""))
    pop = ease_out_back(min(age / 0.25, 1.0), 1.6)
    f = _font(int(250 * max(pop, 0.05)))
    tw = d.textlength(txt, font=f)
    if tw > W * 0.9:
        f = _font(int(250 * W * 0.9 / tw))
    d.text((cx + 8, cy + 10), txt, font=f, fill=(0, 0, 0, 150), anchor="mm")
    d.text((cx, cy), txt, font=f, fill=(250, 232, 170, 255), anchor="mm", stroke_width=6, stroke_fill=(110, 24, 30, 255))
    lab = card.get("label", "")
    if lab:
        lf = _f(COURIER_B, 70)
        lw = d.textlength(lab, font=lf)
        if lw > W * 0.86:
            lf = _f(COURIER_B, int(70 * W * 0.86 / lw))
            lw = d.textlength(lab, font=lf)
        d.rectangle((cx - lw / 2 - 34, cy + 186, cx + lw / 2 + 34, cy + 292), fill=(14, 14, 14, 235))
        d.text((cx, cy + 240), lab, font=lf, fill=(244, 240, 226, 255), anchor="mm")
    base.alpha_composite(layer)
    return np.asarray(base.convert("RGB"))


def radar(frame: np.ndarray, card: dict, age: float, dur: float) -> np.ndarray:
    """Зелений радарний екран: кільця, розгортка зі шлейфом, точки-кораблі з підписами (можуть пливти), трек торпеди малюється."""
    base = Image.fromarray(_dim_blur(frame, 0.18)).convert("RGBA")
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    R = 440
    cx, cy = W // 2, int(H * 0.42)
    d.ellipse((cx - R - 16, cy - R - 16, cx + R + 16, cy + R + 16), fill=(24, 30, 26, 255), outline=(90, 100, 92, 255), width=8)
    d.ellipse((cx - R, cy - R, cx + R, cy + R), fill=(4, 26, 12, 255), outline=(60, 160, 90, 255), width=4)
    for k in (1, 2, 3):
        rr = R * k / 4
        d.ellipse((cx - rr, cy - rr, cx + rr, cy + rr), outline=(40, 120, 66, 255), width=3)
    d.line((cx - R, cy, cx + R, cy), fill=(40, 120, 66, 255), width=3)
    d.line((cx, cy - R, cx, cy + R), fill=(40, 120, 66, 255), width=3)
    ang = (age * 1.9) % (2 * math.pi)
    for k in range(34):   # шлейф розгортки
        a0 = ang - k * 0.045
        a1 = a0 - 0.045
        d.polygon([(cx, cy), (cx + R * math.cos(a0), cy + R * math.sin(a0)), (cx + R * math.cos(a1), cy + R * math.sin(a1))], fill=(70, 220, 120, max(4, 90 - k * 3)))
    d.line((cx, cy, cx + R * math.cos(ang), cy + R * math.sin(ang)), fill=(150, 255, 180, 255), width=5)
    p_move = smooth(min(max((age - 0.2) / max(dur * 0.75, 0.8), 0.0), 1.0))
    mono = _f(COURIER_B, 36)
    for b in card.get("blips", []):
        p0 = b["p"]
        p1 = b.get("to", p0)
        px = p0[0] + (p1[0] - p0[0]) * p_move
        py = p0[1] + (p1[1] - p0[1]) * p_move
        x, y = cx + px * R * 0.92, cy + py * R * 0.92
        pulse = 1.0 + 0.25 * math.sin(age * 8)
        d.ellipse((x - 14 * pulse, y - 14 * pulse, x + 14 * pulse, y + 14 * pulse), fill=(170, 255, 190, 255), outline=(20, 90, 40, 255), width=3)
        lab = b.get("l", "")
        if lab:
            d.text((x + 22, y - 18), lab, font=mono, fill=(170, 255, 190, 255), anchor="lm")
    tr = card.get("track")
    if tr:
        a, bb = tr["from"], tr["to"]
        q = smooth(min(max((age - 0.35) / max(dur * 0.6, 0.7), 0.0), 1.0))
        x0, y0 = cx + a[0] * R * 0.92, cy + a[1] * R * 0.92
        x1, y1 = cx + bb[0] * R * 0.92, cy + bb[1] * R * 0.92
        ex, ey = x0 + (x1 - x0) * q, y0 + (y1 - y0) * q
        d.line((x0, y0, ex, ey), fill=(255, 90, 70, 255), width=7)
        d.ellipse((ex - 12, ey - 12, ex + 12, ey + 12), fill=(255, 90, 70, 255))
        if tr.get("label"):
            d.text((ex + 20, ey + 26), tr["label"], font=mono, fill=(255, 140, 120, 255), anchor="lm")
    date = card.get("date", "")
    if date:
        d.text((cx, cy + R + 74), date, font=_f(COURIER_B, 46), fill=(170, 255, 190, 255), anchor="mm")
    base.alpha_composite(layer)
    return np.asarray(base.convert("RGB"))


_PH: dict = {}


def photo(frame: np.ndarray, card: dict, age: float, dur: float) -> np.ndarray:
    """Повноекранне «документальне фото» з повільним рухом камери (наїзд + панорама), зерном і підписом-плашкою (місце · рік)."""
    from . import assets
    key = card.get("img", "")
    im = _PH.get(key)
    if im is None:
        try:
            im = Image.open(assets.ASSET_ROOT / "bgv" / f"{key}.png").convert("RGB")
        except Exception:   # noqa: BLE001
            im = Image.new("RGB", (768, 1344), (40, 40, 40))
        _PH[key] = im
    iw, ih = im.size
    q = smooth(min(age / max(dur, 0.6), 1.0))
    mode = card.get("move", "in")
    z = 1.0 + (0.20 * q if mode in ("in", "left", "right") else 0.0) + (0.20 * (1 - q) if mode == "out" else 0.0)
    cw, ch = iw / z, ih / z
    px = {"left": -0.5, "right": 0.5}.get(mode, 0.0)
    cx = iw / 2 + px * (iw - cw) * (q * 2 - 1)
    y0 = (ih - ch) / 2 + (0.0 if mode != "up" else -(ih - ch) * 0.4 * (q * 2 - 1))
    x0 = min(max(cx - cw / 2, 0), iw - cw)
    y0 = min(max(y0, 0), ih - ch)
    crop = im.crop((int(x0), int(y0), int(x0 + cw), int(y0 + ch))).resize((W, H), Image.LANCZOS)
    arr = np.asarray(crop).astype(np.float32)
    rnd = np.random.RandomState(int(age * 24) % 977)
    arr += rnd.normal(0, 6, arr.shape[:2])[..., None]
    out = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).convert("RGBA")
    cap = card.get("caption", "")
    if cap:
        lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(lay)
        f = _f(COURIER_B, 44)
        tw = d.textlength(cap, font=f)
        slide = smooth(min(max((age - 0.2) / 0.3, 0.0), 1.0))
        x = -tw - 120 + (tw + 190) * slide
        y = int(H * 0.60)
        d.rectangle((x, y, x + tw + 70, y + 84), fill=(8, 8, 10, 215))
        d.rectangle((x, y, x + 10, y + 84), fill=(212, 52, 44, 255))
        d.text((x + 36, y + 58), cap, font=f, fill=(246, 240, 226, 255), anchor="ls")
        out.alpha_composite(lay)
    return np.asarray(out.convert("RGB"))


def kinetic(frame: np.ndarray, card: dict, age: float, dur: float) -> np.ndarray:
    """Типографічна сцена: рядки великого тексту по черзі «впадають»; слова між *зірочками* — акцентним кольором. Фон — приглушений кадр."""
    from .render import _font
    base = Image.fromarray(_dim_blur(frame, 0.40)).convert("RGBA")
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    lines = card.get("lines", [])
    n = max(len(lines), 1)
    size = int(card.get("size", 150))
    f0 = _font(size)
    cy0 = int(H * 0.42) - int((n - 1) * size * 0.62)
    accent = tuple(card.get("accent", (232, 66, 52)))
    for i, ln in enumerate(lines):
        t_i = 0.08 + 0.28 * i
        q = ease_out_back(min(max((age - t_i) / 0.24, 0.0), 1.0), 2.0)
        if q <= 0.02:
            continue
        plain = ln.replace("*", "")
        f = f0
        wmax = d.textlength(plain, font=f)
        if wmax > W * 0.9:
            f = _font(int(size * W * 0.9 / wmax))
        sz = int(getattr(f, "size", size) * max(min(q, 1.1), 0.1))
        f = _font(max(sz, 12))
        parts = ln.split("*")
        tw = d.textlength(plain, font=f)
        x = W / 2 - tw / 2
        cy = cy0 + i * size * 1.24 + (1.0 - min(q, 1.0)) * -120
        for k, part in enumerate(parts):
            if not part:
                continue
            col = accent if k % 2 == 1 else (250, 246, 232)
            d.text((x + 7, cy + 9), part, font=f, fill=(0, 0, 0, 180), anchor="lm", stroke_width=12, stroke_fill=(0, 0, 0, 180))
            d.text((x, cy), part, font=f, fill=(*col, 255), anchor="lm", stroke_width=9, stroke_fill=(8, 8, 10, 255))
            x += d.textlength(part, font=f)
    base.alpha_composite(layer)
    return np.asarray(base.convert("RGB"))


def deck_diagram(frame: np.ndarray, card: dict, age: float, dur: float) -> np.ndarray:
    """Вигляд зверху: прямий / кутовий посадковий майданчик. Літак заходить, пропускає трос; на прямій палубі врізається в стоянку,
    на кутовій — іде на друге коло. Параметри: mode straight|angled, built (кутова смуга вже намальована)."""
    pw, ph = 920, 1040
    cx, cy = W // 2, int(H * 0.44)
    sea = Image.new("RGBA", (pw, ph), (10, 30, 52, 255))
    d = ImageDraw.Draw(sea)
    for k in range(0, ph, 46):   # хвилі
        for j in range(0, pw, 120):
            x = j + (k * 3) % 80 + math.sin(age * 2 + k) * 6
            d.line((x, k, x + 44, k), fill=(34, 76, 112, 255), width=3)
    mode = card.get("mode", "straight")
    # корпус (вгорі ніс)
    hx, hw = 400, 150
    hull = [(hx, 70), (hx + hw, 190), (hx + hw, 940), (hx - hw, 940), (hx - hw, 190)]
    d.polygon(hull, fill=(150, 156, 164, 255), outline=(236, 240, 244, 255))
    deck = [(hx, 90), (hx + hw - 14, 200), (hx + hw - 14, 930), (hx - hw + 14, 930), (hx - hw + 14, 200)]
    d.polygon(deck, fill=(206, 210, 216, 255))
    # припарковані літаки на носі
    for (px, py) in [(hx - 70, 220), (hx, 200), (hx + 70, 224), (hx - 40, 290), (hx + 40, 296)]:
        d.polygon([(px, py - 24), (px + 22, py + 18), (px, py + 8), (px - 22, py + 18)], fill=(34, 38, 46, 255))
    ang_len = 600
    built = card.get("built", mode == "straight")
    p_build = 1.0 if built else smooth(min(max((age - 0.1) / 0.8, 0.0), 1.0))
    if mode == "angled":
        # кутова посадкова смуга: паралелограм зліва-знизу вгору-ліворуч
        x0, y0 = hx + 20, 930
        x1, y1 = hx - 120, 330
        ex, ey = x0 + (x1 - x0) * p_build, y0 + (y1 - y0) * p_build
        d.line((x0, y0, ex, ey), fill=(40, 40, 48, 255), width=18)
        d.line((x0 - 60, y0, ex - 60, ey), fill=(40, 40, 48, 255), width=6)
        d.line((x0 + 60, y0, ex + 60, ey), fill=(40, 40, 48, 255), width=6)
    else:
        d.line((hx, 930, hx, 330), fill=(40, 40, 48, 255), width=18)
        d.line((hx - 60, 930, hx - 60, 330), fill=(40, 40, 48, 255), width=6)
        d.line((hx + 60, 930, hx + 60, 330), fill=(40, 40, 48, 255), width=6)
    # тросові лінії
    for yy_ in (700, 650, 600):
        if mode == "angled":
            t_ = (930 - yy_) / 600.0
            xa = hx + 20 + (-140) * t_
            d.line((xa - 70, yy_, xa + 70, yy_), fill=(40, 40, 44, 255), width=6)
        else:
            d.line((hx - 70, yy_, hx + 70, yy_), fill=(40, 40, 44, 255), width=6)
    # літак
    t0 = 0.0 if built else 0.9
    q = smooth(min(max((age - t0 - 0.2) / max(dur - t0 - 0.5, 0.8), 0.0), 1.0))
    if mode == "straight":
        py = 1000 - q * 760            # заходить знизу вгору, пропускає трос і летить на стоянку
        px = hx
        crash = q > 0.86
    else:
        # вздовж кутової смуги, потім у повітря й коло вліво-вгору
        if q < 0.55:
            u = q / 0.55
            px, py = hx + 20 + (-140) * u * 0.6, 1000 - u * 640
        else:
            u = (q - 0.55) / 0.45
            px, py = hx - 52 - u * 150, 360 - u * 280 + math.sin(u * 3) * 20
        crash = False
    sc = 1.0 + (0.5 if (mode == "angled" and q >= 0.55) else 0.0)
    d.polygon([(px, py - 34 * sc), (px + 30 * sc, py + 24 * sc), (px, py + 10 * sc), (px - 30 * sc, py + 24 * sc)], fill=(255, 255, 255, 255), outline=(8, 8, 12, 255))
    if crash:
        r = 40 + 60 * smooth((q - 0.86) / 0.14)
        d.polygon([(px + r * math.cos(a), 250 + r * math.sin(a) * (1 if i % 2 == 0 else 0.55)) for i, a in enumerate([k * 0.4 for k in range(16)])], fill=(255, 150, 50, 255))
        d.text((px, 260), "CRASH", font=_f(COURIER_B, 64), fill=(255, 255, 255, 255), anchor="mm", stroke_width=6, stroke_fill=(120, 20, 10, 255))
    if mode == "angled" and q >= 0.55:
        d.text((hx - 200, 120), "GO AROUND", font=_f(COURIER_B, 56), fill=(255, 255, 255, 255), anchor="mm", stroke_width=5, stroke_fill=(10, 10, 14, 255))
    lab = card.get("label", "")
    if lab:
        f = _f(COURIER_B, 56)
        tw = d.textlength(lab, font=f)
        d.rectangle((pw - tw - 90, 24, pw - 24, 100), fill=(8, 8, 10, 235))
        d.text((pw - 24 - (tw + 66) / 2, 62), lab, font=f, fill=(246, 240, 226, 255), anchor="mm")
    base = Image.fromarray(_dim_blur(frame, 0.3)).convert("RGBA")
    slide = 1.0 - min(ease_out_back(min(age / 0.3, 1.0), 1.4), 1.0)
    framed = Image.new("RGBA", (pw + 16, ph + 16), (240, 238, 230, 255))
    framed.paste(sea, (8, 8))
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    pos = (cx - pw // 2 - 8, int(cy - ph // 2 - 8 + slide * 900))
    layer.alpha_composite(_shadow((W, H), (pos[0], pos[1], pos[0] + pw + 16, pos[1] + ph + 16)))
    layer.alpha_composite(framed, pos)
    base.alpha_composite(layer)
    return np.asarray(base.convert("RGB"))


def repair(frame: np.ndarray, card: dict, age: float, dur: float) -> np.ndarray:
    """Креслення авіаносця збоку: червоні позначки пошкоджень по черзі стають зеленими, угорі зворотний відлік до виходу в море."""
    base = Image.fromarray(_dim_blur(frame, 0.12)).convert("RGBA")
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    cy_ = int(H * 0.12)
    px0, py0, px1, py1 = 50, cy_, W - 50, cy_ + 860
    pop = ease_out_back(min(age / 0.3, 1.0), 1.3)
    d.rectangle((px0, py0 + int((1 - pop) * 700), px1, py1 + int((1 - pop) * 700)), fill=(6, 24, 52, 246), outline=(120, 214, 255, 255), width=5)
    if pop < 0.98:
        base.alpha_composite(layer)
        return np.asarray(base.convert("RGB"))
    cy_ = py0
    for gx in range(px0 + 60, px1, 60):   # сітка креслення
        d.line((gx, py0, gx, py1), fill=(120, 214, 255, 26), width=2)
    for gy in range(py0 + 60, py1, 60):
        d.line((px0, gy, px1, gy), fill=(120, 214, 255, 26), width=2)
    q = smooth(min(max((age - 0.35) / max(dur * 0.78, 1.0), 0.0), 1.0))
    hours = float(card.get("hours", 72))
    tot = hours * 3600 * (1 - q)
    hh, mm, ss = int(tot // 3600), int(tot % 3600 // 60), int(tot % 60)
    ready = q >= 0.999
    col = (120, 232, 160, 255) if ready else (120, 214, 255, 255)
    d.text((W // 2, py0 + 110), f"{hh:02d}:{mm:02d}:{ss:02d}", font=_f(COURIER_B, 190), fill=col, anchor="mm")
    d.text((W // 2, py0 + 232), "READY TO SAIL" if ready else str(card.get("clock", "TIME TO SAIL")), font=_f(COURIER_B, 50), fill=col, anchor="mm")
    # силует авіаносця
    y = py0 + 520
    hull = [(110, y), (W - 110, y), (W - 150, y + 100), (230, y + 100), (150, y + 56)]
    d.polygon(hull, fill=(10, 40, 76, 255), outline=(120, 214, 255, 255))
    d.line((110, y, W - 110, y), fill=(120, 214, 255, 255), width=7)
    d.rectangle((640, y - 82, 740, y), fill=(10, 40, 76, 255), outline=(120, 214, 255, 255), width=4)   # острів
    d.line((690, y - 82, 690, y - 150), fill=(120, 214, 255, 255), width=4)
    d.line((660, y - 130, 720, y - 130), fill=(120, 214, 255, 255), width=3)
    for k in range(5):   # літаки на палубі
        ax = 280 + k * 62
        d.polygon([(ax, y - 4), (ax + 20, y - 24), (ax + 40, y - 4)], fill=(120, 214, 255, 120))
    marks = [(330, y + 8), (520, y + 52), (790, y + 30), (910, y - 2)]
    n = len(marks)
    for i, (mx, my) in enumerate(marks):
        fixed = q > (i + 1) / (n + 0.4)
        r = 24
        if fixed:
            d.ellipse((mx - r, my - r, mx + r, my + r), fill=(60, 170, 110, 255), outline=(220, 255, 230, 255), width=4)
            d.line((mx - 11, my + 1, mx - 3, my + 10, mx + 13, my - 9), fill=(255, 255, 255, 255), width=6)
        else:
            blink = 0.55 + 0.45 * math.sin(age * 9 + i)
            d.ellipse((mx - r, my - r, mx + r, my + r), fill=(210, 56, 48, int(235 * blink)), outline=(255, 210, 200, 255), width=4)
            d.line((mx - 10, my - 10, mx + 10, my + 10), fill=(255, 255, 255, 255), width=5)
            d.line((mx - 10, my + 10, mx + 10, my - 10), fill=(255, 255, 255, 255), width=5)
    lab = str(card.get("label", ""))
    if lab:
        d.text((W // 2, py1 - 60), lab, font=_f(COURIER_B, 54), fill=(214, 236, 250, 255), anchor="mm")
    base.alpha_composite(layer)
    return np.asarray(base.convert("RGB"))


CARDS = {"dossier": dossier, "split": split, "route": route, "timeline": timeline, "stat": stat, "radar": radar, "photo": photo, "kinetic": kinetic, "deck": deck_diagram, "repair": repair}


def apply(frame: np.ndarray, card: dict, age: float, dur: float) -> np.ndarray:
    fn = CARDS.get(card.get("type"))
    return fn(frame, card, age, dur) if fn else frame


# ---------- нові переходи ----------
def shutter_transition(a: np.ndarray, b: np.ndarray, p: float, n: int = 12) -> np.ndarray:
    """Жалюзі: смуги по черзі «перегортаються» з кадру A на кадр B."""
    out = a.copy()
    sh = H // n + 1
    for i in range(n):
        q = min(max(p * 1.6 - 0.6 * i / n, 0.0), 1.0)
        y0 = i * sh
        y1 = min(y0 + sh, H)
        cut = y0 + int((y1 - y0) * q)
        out[y0:cut] = b[y0:cut]
        if 0 < q < 1:
            out[max(cut - 3, y0):cut] = (255, 255, 255)
    return out


def tear_transition(a: np.ndarray, b: np.ndarray, p: float, seed: int = 0) -> np.ndarray:
    """Розрив паперу: рваний діагональний край рухається по екрану, кадр B відкривається під ним."""
    rnd = np.random.RandomState(seed + 5)
    jag = cv2.GaussianBlur(rnd.normal(0, 1, (1, W)).astype(np.float32), (0, 0), 6)[0] * 0.05
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    field = xx / W * 0.55 + (1.0 - yy / H) * 0.45 + jag[None, :]
    thr = p * 1.25 - 0.1
    m = field < thr
    out = np.where(m[..., None], b, a)
    edge = (np.abs(field - thr) < 0.012)[..., None]
    return np.where(edge, np.array([244, 240, 226], np.uint8), out).astype(np.uint8)
