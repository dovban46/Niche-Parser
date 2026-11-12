"""Рендерер explainer-кадрів: фон + аватар + предмети → камера (punch/drift/shake) → перехід → великий текст і
субтитри по словах. Кадри йдуть у ffmpeg через pipe. Рот аватара — за реальною гучністю озвучки."""

import math
import random
import subprocess
import tempfile
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from ..ffutil import error_tail
from . import assets
from .character import SAGE, CharacterSpec, render as render_char

import os

VERTICAL = os.environ.get("EXPLAINER_ORIENT", "").lower() == "vertical"   # Shorts 9:16 (див. shorts.py)
FPS = 24
if VERTICAL:
    W, H = 1080, 1920
    SW, SH = 1620, 2880          # сцена 1.5x від кадру: наїзди до 1.5x лишаються нативно різкими
    GROUND_Y = 0.60            # стопи вище; під ними субтитри; нижні ~25% кадру — «небезпечна» зона інтерфейсу Shorts
    CHAR_H = 0.36
    SAFE_TOP, SAFE_BOTTOM = 0.16, 0.60
    MAX_SHOT_S = 1.5
    BG_DIR = "bgv"
    PROP_SCALE = 0.62          # висоту предметів з розкадрування (частки кадру) зменшуємо: вертикальний кадр вузький
    SUB_BASE, SUB_Y, SUB_WORDS = 92, 0.73, 2
    BIG_BASE = 120
    BIG_SLOTS = [(0.5, 0.23), (0.5, 0.31), (0.5, 0.44)]   # нижче HUD (плашка серії + шкали до y≈0.16)
else:
    W, H = 1280, 720
    SW, SH = 1600, 900            # сцена рендериться з запасом під камеру (zoom до 1.25 без втрати різкості)
    GROUND_Y = assets.FEET_Y      # лінія стоп аватара (частка висоти)
    CHAR_H = 0.58                 # висота аватара (частка висоти)
    SAFE_TOP, SAFE_BOTTOM = 0.20, 0.79   # зона дії: зверху великий текст, знизу субтитри
    MAX_SHOT_S = 2.0
    BG_DIR = "bg"
    PROP_SCALE = 1.0
    SUB_BASE, SUB_Y, SUB_WORDS = 62, 0.915, 3
    BIG_BASE = 92
    BIG_SLOTS = [(0.5, 0.105), (0.27, 0.105), (0.73, 0.105), (0.2, 0.42), (0.8, 0.42)]
HOOK_SHOT_S, HOOK_WINDOW_S = 1.1, 6.0   # перші секунди — частіші склейки (утримання на старті)
# Режим «як у stickman-каналів-референсів»: камера СТАТИЧНА в межах кадру (зміна лише монтажними склейками), без паралакса, пилу, зерна,
# погойдування й «дихання» персонажів; рух лише там, де він має сенс (кроки, жести, поява предметів, удар-тряска).
STATIC = True
BG_PAD = 1.07                 # фон трохи більший за кадр: зсувається повільніше за героїв (паралакс)
FONT_IMPACT = "C:/Windows/Fonts/impact.ttf"
OUTLINE = (24, 18, 16)
YELLOW = (255, 212, 40)
GOLD = (232, 186, 70)


# ---------- допоміжні ----------
def ease_out_back(p: float, s: float = 1.9) -> float:
    p = min(max(p, 0.0), 1.0) - 1
    return 1 + (s + 1) * p ** 3 + s * p ** 2


def ease_out(p: float) -> float:
    p = min(max(p, 0.0), 1.0)
    return 1 - (1 - p) ** 3


def smooth(p: float) -> float:
    p = min(max(p, 0.0), 1.0)
    return p * p * (3 - 2 * p)


STICKER_RGB = (255, 255, 255)      # None = без білої висічки (серйозний режим)
BIG_STYLE = "pop"                  # pop | stencil


def set_style(font_path=None, sticker=None, big=None) -> None:
    """Стиль відео: шрифт напису й колір висічки наклейок (викликається при завантаженні таймлайну)."""
    global FONT_IMPACT, STICKER_RGB, BIG_STYLE
    if big:
        BIG_STYLE = big
    if sticker is False:
        STICKER_RGB = None
        sticker = None
    if font_path and font_path != FONT_IMPACT:
        FONT_IMPACT = font_path
        _font.cache_clear()
    if sticker:
        STICKER_RGB = tuple(sticker)


@lru_cache(maxsize=64)
def _font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FONT_IMPACT, size)


# ---------- рот за гучністю ----------
def mouth_levels(audio: Path, n_frames: int) -> list[int]:
    """0..3 на кожен кадр: RMS озвучки → стани рота (закритий / трохи / відкритий / широко) зі згладжуванням."""
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(audio), "-ac", "1", "-ar", "16000", "-f", "s16le", "-"],
                         check=True, capture_output=True).stdout
    x = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    hop = 16000 // FPS
    n = len(x) // hop
    rms = np.sqrt((x[: n * hop].reshape(n, hop) ** 2).mean(axis=1) + 1e-9)
    ref = np.percentile(rms, 92) or 1.0
    v = rms / ref
    levels = np.where(v < 0.10, 0, np.where(v < 0.32, 1, np.where(v < 0.62, 2, 3))).astype(int)
    out = list(levels) + [0] * max(0, n_frames - len(levels))
    # прибираємо одноразові «смикання»: стан тримається щонайменше 2 кадри
    for i in range(1, len(out) - 1):
        if out[i] != out[i - 1] and out[i] != out[i + 1]:
            out[i] = out[i - 1]
    return out[:n_frames]


# ---------- ресурси ----------
class Library:
    def __init__(self, bg_keys, prop_keys, actors: dict, prop_float=()):
        self.bg = {}
        self.walk = {}
        self.prop_float = set(prop_float)
        for k in bg_keys:
            im = assets.load(assets.ASSET_ROOT / BG_DIR / f"{assets._slug(k)}.png").convert("RGB")
            try:
                self.walk[k] = assets.analyze_bg(k, kind=BG_DIR)["walkable"]
            except Exception:  # noqa: BLE001
                self.walk[k] = [[0.1, 0.9]]
            if VERTICAL and not self.walk.get(k) and any(w in k for w in ("cloud", "heaven", "sky", "star", "void")):
                self.walk[k] = [[0.2, 0.8]]   # «небесні» фони: герой стоїть на хмарах/зависає — це припустимо в Shorts
            self.bg[k] = np.asarray(im.resize((int(SW * BG_PAD), int(SH * BG_PAD)), Image.LANCZOS).convert("RGBA"))   # запас під паралакс
        self.prop = {k: assets.load(assets.ASSET_ROOT / "prop" / f"{assets._slug(k)}.png") for k in prop_keys}
        self.actors = {k: (CharacterSpec(**v) if v else SAGE) for k, v in actors.items()}
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        d = np.sqrt(((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2)
        self.vignette = (1.0 - 0.20 * np.clip(d - 0.55, 0, 1) ** 1.4)[..., None].astype(np.float32)
        self.xx, self.yy = np.mgrid[0:H, 0:W][1].astype(np.float32), np.mgrid[0:H, 0:W][0].astype(np.float32)
        # ледь помітні ефекти: промені світла, плівкове зерно, пилинки в повітрі
        gx, gy = self.xx / W, self.yy / H
        bands = 0.65 + 0.35 * np.sin((self.xx + 0.55 * self.yy) / 85.0)
        rays = (np.clip(1.0 - (gx * 0.85 + gy * 0.55), 0, 1) ** 2 * bands)[..., None].astype(np.float32)
        self.vig_u8 = np.clip(self.vignette * 255, 0, 255).astype(np.uint8).repeat(3, axis=2)
        rng = np.random.default_rng(11)
        grains = [rng.normal(0, 3.0, (H, W, 1)).astype(np.float32) for _ in range(4)]
        tint = np.array([255, 226, 170], np.float32)
        self.pos, self.neg = [], [[np.clip(-g, 0, 255).round().astype(np.uint8).repeat(3, axis=2) for g in grains]][0]
        for amp in (0.04, 0.055, 0.07):
            self.pos.append([np.clip(rays * tint * amp + np.clip(g, 0, 255), 0, 255).round().astype(np.uint8) for g in grains])
        k = np.zeros((13, 13), np.float32)
        cv2.circle(k, (6, 6), 5, 1.0, -1, cv2.LINE_AA)
        self.dust_k = cv2.GaussianBlur(k, (0, 0), 1.6)
        self.dust_k /= self.dust_k.max()
        tintd = np.array([1.0, 0.95, 0.8], np.float32)
        self.dust_u8 = [np.clip(self.dust_k[..., None] * 255 * (0.14 * (i + 1)) * tintd, 0, 255).astype(np.uint8) for i in range(4)]
        r = np.random.default_rng(5)
        self.dust = [(r.uniform(0, W), r.uniform(0, H), r.uniform(6, 18), r.uniform(-4, 4), r.uniform(0.5, 1.0), r.uniform(0, 6.28))
                     for _ in range(34)]   # x, y, швидкість підйому, дрейф, яскравість, фаза


def _in_walk(x: float, walk, margin: float = 0.05) -> bool:
    return any(a + margin <= x <= b - margin for a, b in walk)


def _clamp_walk(x: float, walk, margin: float = 0.07):
    """Найближча «ґрунтова» точка до x (None — ходити ніде)."""
    best, bd = None, 9.0
    for a, b in walk:
        lo, hi = a + margin, b - margin
        if hi < lo:
            lo = hi = (a + b) / 2
        c = min(max(x, lo), hi)
        if abs(c - x) < bd:
            best, bd = c, abs(c - x)
    return best


_WOB: dict = {}


def _wobble(img: Image.Image, t: float, amp: float = 1.1) -> Image.Image:
    """«Кипляча» лінія ручної анімації: легке хвилясте зміщення, що оновлюється ~8 разів на секунду."""
    ph = int(t * 8) % 3
    w, h = img.size
    key = (w, h, ph)
    maps = _WOB.get(key)
    if maps is None:
        if len(_WOB) > 300:
            _WOB.clear()
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        mx = xx + amp * np.sin(yy / 23.0 + ph * 2.1)
        my = yy + amp * np.sin(xx / 29.0 + ph * 1.7)
        maps = _WOB[key] = (mx, my)
    out = cv2.remap(np.asarray(img), maps[0], maps[1], cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0))
    return Image.fromarray(out, "RGBA")


_EMOJI_CACHE: dict = {}


def _emoji_img(ch: str, size: int):
    key = (ch, size)
    base = _EMOJI_CACHE.get(key)
    if base is None:
        font = ImageFont.truetype("C:/Windows/Fonts/seguiemj.ttf", 109)
        tmp = Image.new("RGBA", (160, 160), (0, 0, 0, 0))
        ImageDraw.Draw(tmp).text((20, 8), ch, font=font, embedded_color=True)
        bbox = tmp.getbbox()
        if not bbox:
            return None
        tmp = tmp.crop(bbox)
        k = size / max(tmp.size)
        base = tmp.resize((max(int(tmp.width * k), 2), max(int(tmp.height * k), 2)), Image.LANCZOS)
        a = base.getchannel("A").filter(ImageFilter.MaxFilter(13))
        halo = Image.new("RGBA", base.size, (255, 255, 255, 0))
        halo.putalpha(a)
        pad = Image.new("RGBA", (base.width + 20, base.height + 20), (0, 0, 0, 0))
        pad.alpha_composite(halo, (10, 10))
        pad.alpha_composite(base, (10, 10))
        base = _EMOJI_CACHE[key] = pad
    return base


def _emoji_sticker(img: Image.Image, ch: str, cx: float, cy: float, bt: float) -> None:
    """Кольоровий емодзі-стікер поруч із героєм: вилітає з «пружинкою», далі легко погойдується."""
    size = int(0.17 * SW)
    key = (ch, size)
    base = _EMOJI_CACHE.get(key)
    if base is None:
        font = ImageFont.truetype("C:/Windows/Fonts/seguiemj.ttf", 109)
        tmp = Image.new("RGBA", (160, 160), (0, 0, 0, 0))
        ImageDraw.Draw(tmp).text((20, 8), ch, font=font, embedded_color=True)
        bbox = tmp.getbbox()
        if not bbox:
            return
        tmp = tmp.crop(bbox)
        k = size / max(tmp.size)
        base = tmp.resize((max(int(tmp.width * k), 2), max(int(tmp.height * k), 2)), Image.LANCZOS)
        # біла «наклейка»-обводка
        a = base.getchannel("A").filter(ImageFilter.MaxFilter(13))
        halo = Image.new("RGBA", base.size, (255, 255, 255, 0))
        halo.putalpha(a)
        pad = Image.new("RGBA", (base.width + 20, base.height + 20), (0, 0, 0, 0))
        pad.alpha_composite(halo, (10, 10))
        pad.alpha_composite(base, (10, 10))
        base = _EMOJI_CACHE[key] = pad
    pop = ease_out_back(bt / 0.3, 2.2)
    if pop <= 0.02:
        return
    w, h = max(int(base.width * pop), 2), max(int(base.height * pop), 2)
    im2 = base.resize((w, h), Image.BILINEAR).rotate(math.sin(bt * 5) * 6, resample=Image.BICUBIC, expand=True)
    img.alpha_composite(im2, (int(cx - im2.width / 2), int(cy - im2.height / 2 + math.sin(bt * 4) * 10)))


def _stickerize(img: Image.Image, border_frac: float = 0.010, shadow: bool = True):
    """«Стікер із соцмереж»: товста біла контурна «висічка» навколо форми + м'яка тінь. Повертає (RGBA, pad) — pad = на скільки зсунулись координати."""
    a = np.asarray(img)[..., 3]
    k = max(int(SW * border_frac) * 2 + 1, 5)
    pad = k + (18 if shadow else 2)
    h, w = a.shape
    big = np.zeros((h + 2 * pad, w + 2 * pad), np.uint8)
    big[pad: pad + h, pad: pad + w] = a
    kern = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
    dil = cv2.GaussianBlur(cv2.dilate(big, kern), (0, 0), 1.3)
    out = np.zeros((h + 2 * pad, w + 2 * pad, 4), np.uint8)
    if shadow:
        sh = cv2.GaussianBlur(np.roll(np.roll(dil, 14, axis=0), 6, axis=1), (0, 0), 9)
        out[..., 3] = (sh * 0.45).astype(np.uint8)
    base = Image.fromarray(out, "RGBA")
    white = np.zeros_like(out)
    if STICKER_RGB is not None:
        white[..., :3] = np.array(STICKER_RGB, np.uint8)
        white[..., 3] = dil
        base.alpha_composite(Image.fromarray(white, "RGBA"))
    base.alpha_composite(img, (pad, pad))
    return base, pad


_BURST: dict = {}


def _sunburst(size: int, angle: float, color=(255, 236, 140), alpha=70) -> Image.Image:
    base = _BURST.get(size)
    if base is None:
        base = np.zeros((size, size, 4), np.uint8)
        c = size / 2
        n = 14
        for i in range(n):
            a0, a1 = 2 * math.pi * i / n, 2 * math.pi * (i + 0.5) / n
            pts = np.array([[c, c], [c + size * math.cos(a0), c + size * math.sin(a0)], [c + size * math.cos(a1), c + size * math.sin(a1)]], np.int32)
            cv2.fillPoly(base, [pts], (*color, alpha))
        yy, xx = np.mgrid[0:size, 0:size]
        d = np.sqrt((xx - c) ** 2 + (yy - c) ** 2) / (size / 2)
        base[..., 3] = (base[..., 3] * np.clip(1.15 - d, 0, 1)).astype(np.uint8)
        _BURST[size] = base
    M = cv2.getRotationMatrix2D((size / 2, size / 2), angle, 1.0)
    return Image.fromarray(cv2.warpAffine(base, M, (size, size), flags=cv2.INTER_LINEAR, borderValue=(0, 0, 0, 0)), "RGBA")


def _glow(w: int, h: int, color=(255, 250, 235), alpha=95) -> Image.Image:
    key = ("glow", w, h, color, alpha)
    g = _PROP_CACHE.get(key)
    if g is None:
        yy, xx = np.mgrid[0:h, 0:w]
        d = np.sqrt(((xx - w / 2) / (w / 2)) ** 2 + ((yy - h / 2) / (h / 2)) ** 2)
        a = (np.clip(1.0 - d, 0, 1) ** 1.6 * alpha).astype(np.uint8)
        arr = np.zeros((h, w, 4), np.uint8)
        arr[..., :3] = color
        arr[..., 3] = a
        g = _PROP_CACHE[key] = Image.fromarray(arr, "RGBA")
    return g


_PROP_CACHE: dict = {}


def _scaled_prop(key: str, sp: Image.Image, w: int, h: int) -> Image.Image:
    k = (key, w, h)
    im = _PROP_CACHE.get(k)
    if im is None:
        if len(_PROP_CACHE) > 120:
            _PROP_CACHE.clear()
        im = sp.resize((w, h), Image.LANCZOS)
        if VERTICAL:
            im, _ = _stickerize(im, 0.007, shadow=True)
        _PROP_CACHE[k] = im
    return im


_SWAY_CACHE: dict = {}


def _swayed(sprite: Image.Image, ax: float, ay: float, ang: float):
    """Повернутий на малий кут спрайт (з полем-запасом); кеш по (спрайт, кут) — обертання дороге."""
    k = (id(sprite), ang)
    hit = _SWAY_CACHE.get(k)
    if hit is None:
        if len(_SWAY_CACHE) > 400:
            _SWAY_CACHE.clear()
        pad = 14
        padded = Image.new("RGBA", (sprite.width + 2 * pad, sprite.height + 2 * pad), (0, 0, 0, 0))
        padded.alpha_composite(sprite, (pad, pad))
        hit = _SWAY_CACHE[k] = (padded.rotate(ang, resample=Image.BICUBIC, center=(ax + pad, ay + pad)), ax + pad, ay + pad, sprite)
    return hit[0], hit[1], hit[2]


def _star(d: ImageDraw.ImageDraw, cx, cy, r, color):
    pts = [(cx, cy - r), (cx + r * .28, cy - r * .28), (cx + r, cy), (cx + r * .28, cy + r * .28),
           (cx, cy + r), (cx - r * .28, cy + r * .28), (cx - r, cy), (cx - r * .28, cy - r * .28)]
    d.polygon(pts, fill=color)


# ---------- сцена ----------
class Timeline:
    def __init__(self, beats: list[dict], total: float, lib: Library, mouths: list[int]):
        self.lib, self.mouths = lib, mouths
        self.beats = beats
        # візуальні межі: біт змінюється трохи ДО першого слова (передбачення), ≤2 с на кадр
        starts = [0.0] + [max(b["s"] - 0.06, 0.0) for b in beats[1:]]
        ends = starts[1:] + [total + 0.8]
        self.shots = []   # (beat_idx, t0, t1, sub_idx)
        for i, (a, b) in enumerate(zip(starts, ends)):
            lim = min(MAX_SHOT_S, HOOK_SHOT_S) if a < HOOK_WINDOW_S else MAX_SHOT_S
            n = max(1, math.ceil((b - a) / lim - 1e-6))
            for k in range(n):
                self.shots.append((i, a + (b - a) * k / n, a + (b - a) * (k + 1) / n, k))
        self.starts, self.ends = starts, ends
        self.total = total + 0.8
        # «серії»: поспіль біти з тим самим фоном ділять одну плавну камеру (без стрибків на кожному переході)
        self.run_id, self.run_start = [], []
        rid, rs = 0, 0.0
        for i, b in enumerate(beats):
            if i and b["bg"] != beats[i - 1]["bg"]:
                rid, rs = rid + 1, starts[i]
            self.run_id.append(rid)
            self.run_start.append(rs)
        self.layout_log: list[str] = []
        self._layout()
        self._frame_rects: list = []
        self._rects: list = []

    def _layout(self) -> None:
        """Розкладка без накладень: герої лише на твердому ґрунті, предмети не налазять на героїв/один на одного й не
        залізають у зони тексту (зверху) та субтитрів (знизу); важкі предмети стоять на землі, легкі «висять»."""
        lib = self.lib
        for bi, b in enumerate(self.beats):
            walk = lib.walk.get(b["bg"]) or []
            a_rect = None
            if b.get("who"):
                if not walk:
                    self.layout_log.append(f"біт {bi}: фон {b['bg']} без ґрунту → кадр без актора ({b['who']})")
                    b["who"] = None
                else:
                    x = _clamp_walk(b.get("x", 0.5), walk)
                    if b.get("x2") is not None:
                        x2 = _clamp_walk(b["x2"], walk)
                        # ходьба не має перетинати воду: лишаємо кінець у тому ж відрізку ґрунту
                        seg = next(((a, c) for a, c in walk if a <= x <= c), None)
                        if seg and not (seg[0] <= x2 <= seg[1]):
                            x2 = min(max(x2, seg[0] + 0.07), seg[1] - 0.07)
                        b["x2"] = x2
                    if abs(x - b.get("x", 0.5)) > 0.04:
                        self.layout_log.append(f"біт {bi}: актор зсунуто {b.get('x', 0.5):.2f}→{x:.2f} ({b['bg']})")
                    b["x"] = x
                    xs = [b["x"]] + ([b["x2"]] if b.get("x2") is not None else [])
                    a_rect = (min(xs) - 0.10, max(xs) + 0.10)
            placed: list[tuple[float, float, float, float]] = []
            newp = []
            for key, px, py, ph, anim in b.get("props", []):
                sp = lib.prop[key]
                asp = sp.width / sp.height
                floating = key in lib.prop_float
                ph = ph * PROP_SCALE
                h0 = min(ph, 0.5 if floating else SAFE_BOTTOM - SAFE_TOP)
                if a_rect and not floating:
                    h0 = min(h0, 0.5)
                done = None
                for strict in (True, False):
                    for shrink in (1.0, 0.85, 0.7, 0.55):
                        hh = h0 * shrink
                        ww = hh * asp * (SH / SW)
                        cy = (SAFE_BOTTOM - hh / 2) if not floating else min(max(py, SAFE_TOP + hh / 2), SAFE_BOTTOM - 0.04 - hh / 2)
                        order = [0.0] + [d * s2 for d in (0.04 * i for i in range(1, 13)) for s2 in (1, -1)]
                        for off in order:
                            cx = px + off
                            if not (ww / 2 + 0.03 <= cx <= 1 - ww / 2 - 0.03):
                                continue
                            if strict and not floating and walk and not _in_walk(cx, walk, 0.02):
                                continue
                            x0, x1 = cx - ww / 2, cx + ww / 2
                            if a_rect and not (x1 < a_rect[0] - 0.01 or x0 > a_rect[1] + 0.01):
                                continue
                            if any(not (x1 < q[0] - 0.01 or x0 > q[1] + 0.01) and not (cy + hh / 2 < q[2] or cy - hh / 2 > q[3]) for q in placed):
                                continue
                            done = (cx, cy, hh, x0, x1)
                            break
                        if done:
                            break
                    if done:
                        break
                if done:
                    cx, cy, hh, x0, x1 = done
                    placed.append((x0, x1, cy - hh / 2, cy + hh / 2))
                    newp.append([key, cx, cy, hh, anim])
                else:
                    self.layout_log.append(f"біт {bi}: предмет {key} не вмістився — прибрано")
            b["props"] = newp

    def shot_at(self, t: float):
        for idx, sh in enumerate(self.shots):
            if sh[1] <= t < sh[2]:
                return idx, sh
        return len(self.shots) - 1, self.shots[-1]

    # --- кадр сцени (без накладок) ---
    def scene(self, shot_idx: int, t: float) -> np.ndarray:
        bi, t0, t1, sub = self.shots[shot_idx]
        b = self.beats[bi]
        lib = self.lib
        bt = t - self.starts[bi]            # час від початку біта
        st = t - t0                         # час від початку кадру (під-кадру)
        dur = max(self.ends[bi] - self.starts[bi], 0.1)
        _, _, _, par = self._cam_params(bi, t)
        bgarr = lib.bg[b["bg"]]
        bh, bw = bgarr.shape[:2]
        bx = int(min(max((bw - SW) / 2 + par, 0), bw - SW))
        by = int(min(max((bh - SH) / 2 + par * 0.25, 0), bh - SH))
        img = Image.fromarray(np.ascontiguousarray(bgarr[by: by + SH, bx: bx + SW]), "RGBA")
        d = ImageDraw.Draw(img)
        rects: list[tuple[float, float, float, float]] = []

        # предмети
        for key, px, py, ph, anim in b.get("props", []):
            sp = lib.prop[key]
            hpx = ph * SH
            scale = hpx / sp.height
            rot, sx, sy, ox = 0.0, 1.0, 1.0, 0.0
            yoff = 0.0
            pop = ease_out_back(bt / 0.32) if anim != "none" else 1.0
            if anim == "bob":
                yoff = math.sin(bt * 3.2) * 0.012 * SH
            elif anim == "tilt_heavy":
                rot = 13 * smooth((bt - 0.15) / 0.7)
            elif anim == "balance":
                rot = 9 * math.exp(-bt * 2.2) * math.sin(bt * 9)
            elif anim == "chomp":
                sy = 1 + 0.07 * math.sin(bt * 24)
                ox = math.sin(bt * 40) * 6
            elif anim == "spin_in":
                rot = (1.0 - min(bt / 0.42, 1.0)) ** 2 * 540
                pop = ease_out_back(bt / 0.4, 1.5)
            elif anim == "slam":
                q_ = min(bt / 0.16, 1.0)
                pop = 1.0 + 1.6 * (1 - q_) ** 2
                yoff = -((1 - q_) ** 2) * 0.25 * SH
                ox = math.sin(bt * 60) * 9 * math.exp(-(bt - 0.16) * 12) if bt > 0.16 else 0.0
            wpx, hpx2 = max(int(sp.width * scale * sx * pop) // 2 * 2, 2), max(int(sp.height * scale * sy * pop) // 2 * 2, 2)
            im2 = _scaled_prop(key, sp, wpx, hpx2)
            if rot:
                im2 = im2.rotate(rot, resample=Image.BICUBIC, expand=True)
            if not STATIC:
                im2 = _wobble(im2, t, 0.9)
            cx, cy = px * SW + ox, py * SH + yoff
            if VERTICAL:
                cy += (1.0 - min(pop, 1.0)) * 0.10 * SH
            img.alpha_composite(im2, (int(cx - im2.width / 2), int(cy - im2.height / 2)))
            rects.append((cx - im2.width / 2, cy - im2.height / 2, cx + im2.width / 2, cy + im2.height / 2))

        # аватар
        who = b.get("who")
        fx = None
        if who:
            spec = lib.actors[who]
            x0 = b.get("x", 0.5)
            x1 = b.get("x2")
            p = min(bt / dur, 1.0)
            walking = b.get("pose", "stand") in ("walk", "run", "sneak")
            step_phase = None
            if x1 is not None and STATIC and walking:
                # ходьба кроками: тіло просувається під час кроку й «стоїть» між ними — без ковзання
                n = max(2, round(abs(x1 - x0) / (0.05 if b.get("pose") == "run" else 0.07)))
                u = p * n
                k = min(int(u), n - 1)
                f = u - k
                e = smooth(min(f / 0.65, 1.0))
                x = x0 + (x1 - x0) * (k + e) / n
                step_phase = (k + e) * math.pi
            else:
                x = x0 + (x1 - x0) * p if x1 is not None else x0
            face = b.get("face") or (-1 if (x1 is not None and x1 < x0) else 1)
            pose = b.get("pose", "stand")
            if b.get("pose2") and (sub > 0 or bt > dur * 0.55):
                pose = b["pose2"]   # жест змінюється всередині біта: персонаж «живий»
            frame_i = int(t * FPS)
            mouth = self.mouths[min(frame_i, len(self.mouths) - 1)] if b.get("speak") else 0
            blink = (t % 3.1) < 0.12
            if pose in ("walk", "run", "sneak"):
                phase = step_phase if step_phase is not None else (int(t * 3.5) % 2) * 1.4
            else:
                phase = t * 9.0 if pose == "laugh" else 0.0
            sprite, (ax, ay) = render_char(spec, pose, b.get("expr", "neutral"), mouth, phase, face, int(CHAR_H * SH), blink)
            # поява героя в новій сцені — м'яка «пружинка»; решта бітів без пульсацій
            first = bi == 0 or self.beats[bi - 1].get("who") != who or self.beats[bi - 1].get("bg") != b["bg"]
            sc = (0.88 + 0.12 * ease_out_back(bt / 0.3, 1.1)) if (first and sub == 0 and bt < 0.3) else 1.0
            walking = pose in ("walk", "run", "sneak")
            slide = 0.0
            if VERTICAL and sub == 0 and bt < 0.34 and pose not in ("walk", "run", "sneak"):
                ee = ease_out_back(bt / 0.34, 1.5)
                sc = 0.8 + 0.2 * ee
                slide = 1.0 - ee
            if STATIC and not VERTICAL:
                sc = 1.0
            else:
                sc *= 1.0 if walking else 1.0 + 0.007 * math.sin(t * 2.1)
            if not walking and not STATIC:   # легке похитування корпусу довкола стоп
                ang = round(0.9 * math.sin(t * 1.6 + 0.7) * 3) / 3
                sprite, ax, ay = _swayed(sprite, ax, ay, ang)
            if abs(sc - 1) > 0.004:
                sprite = sprite.resize((max(int(sprite.width * sc), 2), max(int(sprite.height * sc), 2)), Image.BILINEAR)
                ax, ay = ax * sc, ay * sc
            bob = 0.0 if (pose in ("walk", "run") or STATIC) else math.sin(t * 2.4) * 4
            gx, gy = x * SW + (-1 if x < 0.5 else 1) * slide * 0.22 * SW, GROUND_Y * SH
            # тінь
            sh = Image.new("RGBA", (int(sprite.width * 0.75), int(sprite.width * 0.1)), (0, 0, 0, 0))
            ImageDraw.Draw(sh).ellipse((0, 0, sh.width - 1, sh.height - 1), fill=(0, 0, 0, 70))
            img.alpha_composite(sh, (int(gx - sh.width / 2), int(gy - sh.height / 2 + 10)))
            if not STATIC:
                sprite = _wobble(sprite, t, 1.2)
            if VERTICAL:
                # позаду героя: м'яке світіння (відділяє від фону) + обертові «промені» на акцентних бітах
                gw, gh = int(sprite.width * 1.5), int(sprite.height * 0.95)
                img.alpha_composite(_glow(gw, gh), (int(gx - gw / 2), int(gy - sprite.height * 0.5 - gh / 2)))
                if b.get("big") or b.get("burst"):
                    bs = int(SW * 1.05)
                    fadein = min(bt / 0.25, 1.0)
                    bi_ = _sunburst(bs, (t * 14) % 360, alpha=int(78 * fadein))
                    img.alpha_composite(bi_, (int(gx - bs / 2), int(gy - sprite.height * 0.55 - bs / 2)))
                sprite, pad_ = _stickerize(sprite)
                ax, ay = ax + pad_, ay + pad_
            img.alpha_composite(sprite, (int(gx - ax), int(gy - ay + bob)))
            rects.append((gx - ax, gy - ay + bob, gx - ax + sprite.width, gy - ay + bob + sprite.height))
            fx = x
            self._actor_x = x

        # іскри (магія/баланс)
        if "x_magic" in b.get("sfx", []) or b.get("sparkle"):
            rnd = random.Random(7)
            for i in range(14):
                a = rnd.random() * 6.283
                r = (120 + rnd.random() * 380)
                size = 26 * abs(math.sin(bt * 7 + i * 1.7)) * min(bt / 0.15, 1)
                if size > 3:
                    _star(d, SW * 0.5 + math.cos(a) * r * 1.3, SH * 0.45 + math.sin(a) * r * 0.7, size, (255, 236, 150, 255))

        arr = np.ascontiguousarray(np.asarray(img)[..., :3])
        self._prop_c = None
        for key_, px_, py_, ph_, an_ in b.get("props", []):
            self._prop_c = (px_, py_)
            break
        if fx is None:
            self._actor_x = None
        self._rects = rects
        self._focus = fx if fx is not None else (b["props"][0][1] if b.get("props") else 0.5)
        return arr

    # --- камера ---
    def _cam_params(self, bi: int, t: float):
        """(zoom, dx, dy, паралакс фону) — одна повільна безперервна траєкторія на всю серію бітів з тим самим фоном."""
        if STATIC:
            return 1.0, 0.0, 0.0, 0.0
        rid = self.run_id[bi]
        rt = t - self.run_start[bi]
        rnd = random.Random(rid * 7919 + 13)
        period = rnd.uniform(16, 26)
        zdir = rnd.choice([-1, 1])
        pdir = rnd.choice([-1, 1])
        z = 1.03 + 0.02 * zdir * math.sin(2 * math.pi * rt / period)
        dx = pdir * math.sin(2 * math.pi * rt / (period * 1.35) + rid) * 24 + 2.2 * math.sin(t * 1.3) + 1.4 * math.sin(t * 2.9)
        dy = math.sin(2 * math.pi * rt / (period * 1.8)) * 9 + 1.6 * math.sin(t * 1.7)
        par = -pdir * math.sin(2 * math.pi * rt / (period * 1.35) + rid) * 20
        return z, dx, dy, par

    def camera(self, scene: np.ndarray, shot_idx: int, t: float) -> np.ndarray:
        bi, t0, t1, sub = self.shots[shot_idx]
        b = self.beats[bi]
        bt = t - self.starts[bi]
        kind = b.get("cam", "drift")
        z, ox, oy, _ = self._cam_params(bi, t)
        if STATIC and kind != "shake":
            kind = "static"
        if kind == "punch" and sub == 0:      # рідкісний акцент: наїзд, що м'яко відпускає
            z += 0.03 * math.exp(-bt * 2.6)
        elif kind == "shake":                 # удар: коротка тряска
            amp = 10 * math.exp(-bt * 3.2)
            rnd = random.Random(int(t * FPS))
            ox, oy = ox + rnd.uniform(-amp, amp), oy + rnd.uniform(-amp, amp)
            z += 0.015 * math.exp(-bt * 3.0)
        fx = self._focus
        cw, ch = SW / z, SH / z
        if STATIC:
            cx, cy = min(max(SW / 2 + ox, cw / 2), SW - cw / 2), min(max(SH / 2 + oy, ch / 2), SH - ch / 2)
        else:
            cx = min(max(SW * (0.5 + (fx - 0.5) * 0.28) + ox, cw / 2), SW - cw / 2)
            cy = min(max(SH * 0.5 + oy + 0.02 * SH, ch / 2), SH - ch / 2)
        s = W / cw
        M = np.float32([[s, 0, -(cx - cw / 2) * s], [0, s, -(cy - ch / 2) * s]])
        self._frame_rects = [((x0 - (cx - cw / 2)) * s, (y0 - (cy - ch / 2)) * s, (x1 - (cx - cw / 2)) * s, (y1 - (cy - ch / 2)) * s)
                             for x0, y0, x1, y1 in self._rects]
        return cv2.warpAffine(scene, M, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)

    def clean_frame(self, t: float) -> np.ndarray:
        idx, _ = self.shot_at(t)
        return self.camera(self.scene(idx, t), idx, t)

    # --- переходи ---
    def transition(self, t: float) -> np.ndarray | None:
        idx, sh = self.shot_at(t)
        bi, t0, _, sub = sh
        if sub != 0 or bi == 0:
            return None
        kind = self.beats[bi].get("tr", "cut")
        dur = {"whip": 0.20, "flash": 0.20, "iris": 0.38, "wipe": 0.32}.get(kind)
        if not dur or t - t0 >= dur:
            return None
        p = (t - t0) / dur
        a_t = t0 - 1e-3
        a_idx, _ = self.shot_at(a_t)
        a_img = self.camera(self.scene(a_idx, min(a_t + 0.02, t0 - 1e-3)), a_idx, min(a_t + 0.02, t0 - 1e-3))
        b_img = self.camera(self.scene(idx, t), idx, t)
        if kind == "whip":
            e = smooth(p)
            off = int(e * W)
            canvas = np.concatenate([a_img, b_img], axis=1)[:, off: off + W]
            k = int(8 + 90 * math.sin(math.pi * p))
            return cv2.blur(canvas, (k | 1, 1))
        if kind == "flash":
            base = a_img if p < 0.5 else b_img
            w = 1 - abs(2 * p - 1)
            return cv2.addWeighted(base, 1 - w, np.full_like(base, 255), w, 0)
        if kind == "iris":
            fxp = self.beats[bi].get("x", 0.5) if self.beats[bi].get("who") else 0.5
            cx, cy = fxp * W, 0.5 * H
            r = smooth(p) * math.hypot(W, H)
            dist = np.sqrt((self.lib.xx - cx) ** 2 + (self.lib.yy - cy) ** 2)
            out = np.where((dist < r)[..., None], b_img, a_img)
            ring = (np.abs(dist - r) < 9)
            out[ring] = OUTLINE
            return out
        if kind == "wipe":
            band = 300
            sv = self.lib.xx + 0.35 * self.lib.yy
            edge = smooth(p) * (W + 0.35 * H + band * 1.2) - 40
            out = np.where((sv < edge - band)[..., None], b_img, a_img)
            mid = (sv >= edge - band) & (sv < edge)
            out[mid] = GOLD
            line = (np.abs(sv - edge) < 7) | (np.abs(sv - (edge - band)) < 7)
            out[line] = OUTLINE
            return out
        return None

    # --- накладки ---
    def overlays(self, frame: np.ndarray, t: float) -> np.ndarray:
        idx, (bi, t0, t1, sub) = self.shot_at(t)[0], self.shot_at(t)[1]
        b = self.beats[bi]
        im = Image.fromarray(frame).convert("RGBA")
        ov = Image.new("RGBA", im.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(ov)
        bt = t - self.starts[bi]

        big = b.get("big")
        if big and VERTICAL:   # великий текст не дублює озвучку (її вже показують субтитри)
            import re as _re
            _w = lambda x: set(_re.findall(r"[a-z0-9']+", x.lower()))
            if _w(big) <= _w(str(b.get("t", ""))) or b.get("stamp"):   # дубль озвучки або накладання зі штампом
                big = None
        self.qa = {"big": None, "sub": None, "rects": [tuple(r) for r in self._frame_rects]}
        if big:
            pop = ease_out_back(bt / 0.22)
            best = None
            slots = BIG_SLOTS
            if bt < 0.12 and self.beats.index(b) == 0:
                pop = 1.0   # перший кадр відео — текст-гачок одразу на місці (без анімації появи)
            for scale in (1.0, 0.82, 0.66):
                size = int(BIG_BASE * scale * max(pop, 0.05))
                f = _font(max(size, 8))
                lines_b = [big]
                if VERTICAL and d.textlength(big, font=f) > W * 0.86 and " " in big:
                    ws_ = big.split(" ")
                    cut = max(1, len(ws_) // 2)
                    lines_b = [" ".join(ws_[:cut]), " ".join(ws_[cut:])]
                tw = max(d.textlength(l_, font=f) for l_ in lines_b)
                lh = int(size * 1.05)
                layer = Image.new("RGBA", (int(tw) + 60, lh * len(lines_b) + 40), (0, 0, 0, 0))
                ld = ImageDraw.Draw(layer)
                for li_, l_ in enumerate(lines_b):
                    lx = 30 + (tw - d.textlength(l_, font=f)) / 2
                    ld.text((lx + 8, 30 + 8 + li_ * lh), l_, font=f, fill=(0, 0, 0, 130), stroke_width=22 if VERTICAL else 9, stroke_fill=(0, 0, 0, 130))
                    if BIG_STYLE == "stencil":
                        ld.text((lx, 30 + li_ * lh), l_, font=f, fill=(236, 230, 212, 255), stroke_width=7, stroke_fill=(12, 12, 14, 255))
                    else:
                        if VERTICAL:
                            ld.text((lx, 30 + li_ * lh), l_, font=f, fill=(255, 255, 255, 255), stroke_width=22, stroke_fill=(255, 255, 255, 255))
                        ld.text((lx, 30 + li_ * lh), l_, font=f, fill=YELLOW, stroke_width=9, stroke_fill=OUTLINE)
                layer = layer.rotate(-3, resample=Image.BICUBIC, expand=True)
                for sx, sy in slots:
                    x0, y0 = W * sx - layer.width / 2, H * sy - layer.height / 2
                    x1, y1 = x0 + layer.width, y0 + layer.height
                    if x0 < 0.015 * W or x1 > 0.985 * W:
                        continue
                    ov_area = 0.0
                    for rx0, ry0, rx1, ry1 in self._frame_rects:
                        mx, my = (rx1 - rx0) * 0.08, (ry1 - ry0) * 0.06   # у прозорих кутах спрайта текст допустимий
                        iw = min(x1 - 30, rx1 - mx) - max(x0 + 30, rx0 + mx)
                        ih = min(y1 - 30, ry1 - my) - max(y0 + 30, ry0 + my)
                        if iw > 0 and ih > 0:
                            ov_area += iw * ih
                    if best is None or ov_area < best[0] - 1:
                        best = (ov_area, layer, x0, y0)
                    if ov_area == 0:
                        break
                if best is not None and best[0] == 0:
                    break
            if best is not None:
                ov.alpha_composite(best[1], (int(best[2]), int(best[3])))
                self.qa["big"] = (best[2] + 30, best[3] + 30, best[2] + best[1].width - 30, best[3] + best[1].height - 30, best[0])

        # субтитри по словах: ≤3 слів у рядку, поточне слово жовте й «стрибає»
        words = b.get("words", [])
        if words and not getattr(self, "_custom_caps", False):
            n = len(words)
            k = math.ceil(n / SUB_WORDS)
            sizes = [n // k + (1 if i < n % k else 0) for i in range(k)]
            chunks, c = [], 0
            for s_ in sizes:
                chunks.append(words[c: c + s_])
                c += s_
            cur = chunks[0]
            for ch in chunks:
                if t >= ch[0]["s"] - 0.04:
                    cur = ch
            active = max((i for i, w in enumerate(cur) if t >= w["s"] - 0.02), default=0)
            base = SUB_BASE
            rendered = []
            for i, w in enumerate(cur):
                txt = w["w"].upper().strip(",.:;!?\"“”'‘’")
                if w["w"].rstrip("\"”'’").endswith("?"):
                    txt += "?"
                jump = 1.0 + (0.16 * math.sin(min((t - w["s"]) / 0.14, 1.0) * math.pi) if i == active and t >= w["s"] else 0)
                f = _font(int(base * jump))
                rendered.append((txt, f, i == active))
            gap = 18
            total_w = sum(d.textlength(tx, font=f) for tx, f, _ in rendered) + gap * (len(rendered) - 1)
            x = W / 2 - total_w / 2
            yb = SUB_Y * H
            for tx, f, act in rendered:
                tw = d.textlength(tx, font=f)
                d.text((x, yb), tx, font=f, fill=YELLOW if act else (255, 255, 255), stroke_width=8, stroke_fill=OUTLINE, anchor="ls")
                x += tw + gap
            self.qa["sub"] = (W / 2 - total_w / 2, yb - base * 0.8, W / 2 + total_w / 2, yb + 6)
        return np.asarray(Image.alpha_composite(im, ov).convert("RGB"))

    def _ambient(self, out: np.ndarray, t: float, f: int) -> np.ndarray:
        """Ледь помітні «живі» шари (у uint8 через cv2 — швидко): віньєтка, тепле світло зверху-зліва, плівкове зерно, пилинки."""
        lib = self.lib
        out = cv2.multiply(out, lib.vig_u8, scale=1 / 255.0)
        li = int(round(1 + math.sin(t * 0.55)))      # 0..2 — «дихання» світла
        out = cv2.add(out, lib.pos[li][f % 4])
        out = cv2.subtract(out, lib.neg[f % 4])
        k = lib.dust_u8
        kh = k[0].shape[0] // 2
        for x0, y0, vy, vx, a, ph in lib.dust:
            x = (x0 + vx * t + 12 * math.sin(t * 0.4 + ph)) % W
            y = (y0 - vy * t) % H
            xi, yi = int(x), int(y)
            if kh <= xi < W - kh and kh <= yi < H - kh:
                lvl = min(3, int(((0.25 + 0.2 * math.sin(t * 0.9 + ph)) * a) / 0.14))
                roi = out[yi - kh: yi + kh + 1, xi - kh: xi + kh + 1]
                cv2.add(roi, k[lvl], dst=roi)
        return out

    def frame(self, f: int) -> np.ndarray:
        t = f / FPS
        t = min(t, self.total - 1e-3)
        out = self.transition(t)
        if out is None:
            out = self.clean_frame(t)
        if not STATIC or VERTICAL:
            out = self._ambient(out, t, f)
        return self.overlays(out, t)


def render_video(tl: Timeline, out_path: Path, log=print, only: tuple[int, int] | None = None) -> int:
    n = int(tl.total * FPS)
    rng = range(n) if only is None else range(only[0], min(only[1], n))
    proc = subprocess.Popen(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
         "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", "17", "-pix_fmt", "yuv420p",
         "-movflags", "+faststart", str(out_path)],
        stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        for f in rng:
            proc.stdin.write(tl.frame(f).tobytes())
            if f % 240 == 0:
                log(f"кадр {f}/{n}")
        proc.stdin.close()
        err = proc.stderr.read().decode("utf-8", "replace")
        if proc.wait() != 0:
            raise RuntimeError(f"ffmpeg: {err[-500:]}")
    finally:
        if proc.poll() is None:
            proc.kill()
    return n


def _worker(args):
    cv2.setNumThreads(1)
    folder, f0, f1, out = args
    from .storyboard import load_timeline
    tl = load_timeline(Path(folder))
    render_video(tl, Path(out), log=lambda *_: None, only=(f0, f1))
    return out


def render_parallel(folder: Path, out_path: Path, workers: int = 7, chunk: int = 480, log=print) -> int:
    """Кадри незалежні (все рахується з часу), тож рендеримо шматки паралельно й склеюємо без перекодування."""
    from concurrent.futures import ProcessPoolExecutor
    from .storyboard import load_timeline
    tl = load_timeline(folder)
    n = int(tl.total * FPS)
    parts_dir = folder / "parts"
    parts_dir.mkdir(exist_ok=True)
    jobs, parts = [], []
    for i, f0 in enumerate(range(0, n, chunk)):
        part = parts_dir / f"part_{i:03d}.mp4"
        parts.append(part)
        if not part.exists():
            jobs.append((str(folder), f0, min(f0 + chunk, n), str(part) + ".tmp.mp4"))
    log(f"рендер: {n} кадрів, шматків {len(parts)} (до рендеру {len(jobs)}), процесів {workers}")
    done = 0
    with ProcessPoolExecutor(max_workers=workers) as ex:
        for out in ex.map(_worker, jobs):
            Path(out).replace(out[: -len(".tmp.mp4")])
            done += 1
            log(f"  готово шматків {done}/{len(jobs)}")
    lst = parts_dir / "list.txt"
    lst.write_text("\n".join(f"file '{p.resolve().as_posix()}'" for p in parts), encoding="utf-8")
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
                    "-c", "copy", str(out_path)], check=True, capture_output=True)
    return n
