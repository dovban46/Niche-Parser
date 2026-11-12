"""Монтаж: кадри fal → камера (push/pull/pan/punch), обведення деталі, стамп-підписи, великий гачок, субтитри по словах,
переходи (cut/whip/flash/zoom), звук (озвучка + SFX + музика). Кадри йдуть у ffmpeg через pipe."""

import math
import subprocess
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .. import audio_mix, sfx
from ..config import SFX_ACCENT_GAIN_DB
from ..ffutil import error_tail, run_ffmpeg
from . import core, music

W, H, FPS = 1280, 720, 30
IMPACT = "C:/Windows/Fonts/impact.ttf"
YELLOW = (255, 212, 40)
VERMILION_BGR = (40, 60, 235)       # cv2 BGR
TR_DUR = {"whip": 0.22, "flash": 0.20, "zoom": 0.22, "ink": 0.55,   # ink: перехід «мазок туші» (v05)
          "dissolve": 0.45, "burn": 0.60, "iris": 0.45}              # 2026-11-10: з survival-каналу, розставляє vary.py
BARS_H = 0.085                      # висота кінорамки (частка кадру) для бітів з "bars": true
MUSIC_GAIN_DB = -17.0
AMB_GAIN_DB, AMB_LEN_S = -14.0, 7.0 # фони amb_* (20 с вітру/табору) — широкосмуговий шум: тихіше й коротше (v08 звучало як шипіння)
PARALLAX_PX = 15                    # зсув ближніх шарів при паралаксі 2.5D (пікселі кінцевого кадру)
HOOK_HOLD = 1.4                     # скільки тримати рядок штампів-гачка після останнього, с
ANIM_DT = 0.45                      # тривалість пози в кадровій анімації, с
BASE_ZOOM = 1.10                    # мінімальний наїзд: ховає краї кадру й підписи/штампи в кутках
# ПРОФІЛЬ МОНТАЖУ відео (2026-11-10): <робота>/montage.json, щоб кожне відео виглядало інакше (пише vary.apply).
# grade: none|warm|cool|dusk|ink (кольорова градація всього відео); subs: yellow|vermilion|cream (колір активного слова);
# particles: dust|petals|snow|ash (що летить у повітрі); chapter: banner|card (банер зліва або картка по центру).
DEFAULT_MONTAGE = {"grade": "none", "subs": "yellow", "particles": "dust", "chapter": "banner"}
GRADES = {"warm": (0.92, 1.0, 1.10), "cool": (1.10, 1.0, 0.92), "dusk": (1.06, 0.95, 1.06), "ink": (1.0, 1.0, 1.0)}   # множники B, G, R
SUB_ACTIVE = {"yellow": (255, 212, 40), "vermilion": (255, 96, 60), "cream": (250, 238, 212)}
PARTICLE_BGR = {"dust": (215, 232, 246), "petals": (196, 178, 248), "snow": (250, 250, 250), "ash": (150, 150, 155)}


def ease(p: float) -> float:
    p = min(max(p, 0.0), 1.0)
    return p * p * (3 - 2 * p)


def ease_out_back(p: float, s: float = 1.7) -> float:
    p = min(max(p, 0.0), 1.0) - 1
    return 1 + (s + 1) * p ** 3 + s * p ** 2


def lerp(a, b, p):
    return a + (b - a) * p


@lru_cache(maxsize=None)
def font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(IMPACT, size)


def ink_wipe(prev: np.ndarray, new: np.ndarray, p: float, seed: int) -> np.ndarray:
    """Перехід «мазок туші»: нова картинка відкривається зліва направо під рваним краєм мазка, на краю темна смуга туші."""
    rng = np.random.default_rng(seed)
    ys = np.arange(H, dtype=np.float32)
    wob = (np.sin(ys / 37 + seed) * 22 + np.sin(ys / 11 + seed * 2) * 9 + rng.normal(0, 4, H)).astype(np.float32)
    edge = (lerp(-0.25, 1.25, ease(p)) * W + wob)[:, None]
    xs = np.arange(W, dtype=np.float32)[None, :]
    d = edge - xs                                   # >0: уже відкрита нова картинка
    m = np.clip(d / 40.0, 0, 1)[..., None]
    out = new.astype(np.float32) * m + prev.astype(np.float32) * (1 - m)
    ink = np.clip(1 - np.abs(d) / 55.0, 0, 1)[..., None] * 0.92
    out = out * (1 - ink) + np.float32([28, 22, 20]) * ink
    return np.clip(out, 0, 255).astype(np.uint8)


# ---------------- спрайти тексту ----------------
@lru_cache(maxsize=None)
def day_sprite(text: str) -> np.ndarray:
    """Лічильник днів (формат «N днів у…», v06): темна лакова плашка, кремовий текст, кіноварна рамка."""
    f = font(58)
    tw = f.getlength(text)
    pad = 22
    wd, ht = int(tw + pad * 2), 58 + pad * 2
    im = Image.new("RGBA", (wd + 20, ht + 20), (0, 0, 0, 0))
    dr = ImageDraw.Draw(im)
    dr.rounded_rectangle((14, 16, 14 + wd, 16 + ht), 10, fill=(0, 0, 0, 110))
    dr.rounded_rectangle((8, 8, 8 + wd, 8 + ht), 10, fill=(28, 22, 20, 235), outline=(200, 40, 30, 255), width=5)
    dr.text((8 + pad, 8 + pad - 6), text, font=f, fill=(250, 238, 212, 255))
    return np.asarray(im)


@lru_cache(maxsize=None)
def stamp_sprite(text: str) -> np.ndarray:
    f = font(54)
    tw = f.getlength(text)
    pad = 26
    wd, ht = int(tw + pad * 2 + 10), 54 + pad * 2 + 6
    im = Image.new("RGBA", (wd + 40, ht + 40), (0, 0, 0, 0))
    dr = ImageDraw.Draw(im)
    x0, y0 = 20, 20
    dr.rounded_rectangle((x0 + 5, y0 + 6, x0 + wd + 5, y0 + ht + 6), 14, fill=(0, 0, 0, 90))
    dr.rounded_rectangle((x0, y0, x0 + wd, y0 + ht), 14, fill=(250, 238, 212, 255), outline=(200, 40, 30, 255), width=7)
    dr.rounded_rectangle((x0 + 11, y0 + 11, x0 + wd - 11, y0 + ht - 11), 8, outline=(200, 40, 30, 255), width=2)
    dr.text((x0 + pad + 4, y0 + pad - 4), text, font=f, fill=(200, 40, 30, 255))
    return np.asarray(im.rotate(4, resample=Image.BICUBIC, expand=True))


@lru_cache(maxsize=None)
def sub_sprite(words: tuple, active: int, act=YELLOW) -> np.ndarray:
    f = font(66)
    gap = 18
    widths = [f.getlength(w) for w in words]
    wd = int(sum(widths) + gap * (len(words) - 1) + 40)
    im = Image.new("RGBA", (wd, 110), (0, 0, 0, 0))
    dr = ImageDraw.Draw(im)
    x = 20
    for i, w in enumerate(words):
        fill = act if i == active else (255, 255, 255)
        dr.text((x, 12), w, font=f, fill=fill + (255,), stroke_width=7, stroke_fill=(20, 14, 12, 255))
        x += widths[i] + gap
    return np.asarray(im)


@lru_cache(maxsize=None)
def chapter_sprite(text: str) -> np.ndarray:
    f = font(46)
    tw = f.getlength(text.upper())
    wd, ht = int(tw + 70), 86
    im = Image.new("RGBA", (wd + 30, ht + 20), (0, 0, 0, 0))
    dr = ImageDraw.Draw(im)
    dr.rounded_rectangle((16, 14, wd + 10, ht + 12), 10, fill=(0, 0, 0, 90))
    dr.rounded_rectangle((10, 8, wd + 4, ht + 6), 10, fill=(38, 44, 96, 255), outline=(250, 238, 212, 255), width=4)
    dr.rectangle((10, 8, 30, ht + 6), fill=(214, 60, 40, 255))
    dr.text((46, 16), text.upper(), font=f, fill=(250, 238, 212, 255))
    return np.asarray(im)


# --- стилі тексту-гачка (montage.json "hook", 2026-11-11: у кожному відео був однаковий рядок штампів угорі) ---
@lru_cache(maxsize=None)
def caption_sprite(text: str) -> np.ndarray:
    """Документальний титр: темна смуга з кіноварною рискою зліва, білий текст (рядки накопичуються зверху ліворуч)."""
    f = font(52)
    tw = f.getlength(text)
    wd, ht = int(tw + 60), 78
    im = Image.new("RGBA", (wd + 20, ht + 20), (0, 0, 0, 0))
    dr = ImageDraw.Draw(im)
    dr.rectangle((10, 10, wd + 10, ht + 10), fill=(10, 10, 14, 175))
    dr.rectangle((10, 10, 22, ht + 10), fill=(214, 50, 36, 255))
    dr.text((38, 18), text, font=f, fill=(250, 246, 236, 255))
    return np.asarray(im)


@lru_cache(maxsize=None)
def seal_sprite(text: str) -> np.ndarray:
    """Червона печатка-ханко з білим текстом, трохи нахилена (стовпчиком праворуч)."""
    f = font(50)
    tw = f.getlength(text)
    wd, ht = int(tw + 54), 84
    im = Image.new("RGBA", (wd + 30, ht + 30), (0, 0, 0, 0))
    dr = ImageDraw.Draw(im)
    dr.rounded_rectangle((15, 15, wd + 15, ht + 15), 6, fill=(186, 32, 26, 240))
    dr.rounded_rectangle((23, 23, wd + 7, ht + 7), 4, outline=(250, 236, 220, 255), width=3)
    dr.text((42, 26), text, font=f, fill=(250, 236, 220, 255))
    return np.asarray(im.rotate(-5, resample=Image.BICUBIC, expand=True))


@lru_cache(maxsize=None)
def flash_sprite(text: str) -> np.ndarray:
    """Одне велике слово по центру вгорі, біле з чорним контуром; кожне наступне замінює попереднє."""
    f = font(92)
    tw = f.getlength(text)
    im = Image.new("RGBA", (int(tw + 60), 140), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((30, 14), text, font=f, fill=(255, 255, 255, 255), stroke_width=9, stroke_fill=(16, 12, 10, 255))
    return np.asarray(im)


def blit(frame: np.ndarray, sprite: np.ndarray, cx: float, cy: float, scale: float = 1.0, alpha: float = 1.0) -> None:
    """Накладає RGBA-спрайт (RGB) на BGR-кадр з центром у (cx, cy)."""
    if scale != 1.0:
        sprite = cv2.resize(sprite, (max(int(sprite.shape[1] * scale), 2), max(int(sprite.shape[0] * scale), 2)), interpolation=cv2.INTER_LINEAR)
    sh, sw = sprite.shape[:2]
    x0, y0 = int(cx - sw / 2), int(cy - sh / 2)
    fx0, fy0, fx1, fy1 = max(x0, 0), max(y0, 0), min(x0 + sw, W), min(y0 + sh, H)
    if fx0 >= fx1 or fy0 >= fy1:
        return
    sp = sprite[fy0 - y0:fy1 - y0, fx0 - x0:fx1 - x0]
    a = (sp[..., 3:4].astype(np.float32) / 255.0) * alpha
    rgb = sp[..., :3][..., ::-1].astype(np.float32)
    roi = frame[fy0:fy1, fx0:fx1].astype(np.float32)
    frame[fy0:fy1, fx0:fx1] = (roi * (1 - a) + rgb * a).astype(np.uint8)


# ---------------- сцена ----------------
def _ring_ok(box) -> bool:
    """Обводимо лише дрібну деталь: велика рамка (півкадру) виглядає криво."""
    w, h = box[2] - box[0], box[3] - box[1]
    return 0.02 <= w * h <= 0.12 and w <= 0.45 and h <= 0.5


class Scene:
    def __init__(self, slug: str):
        d = core.job_dir(slug)
        self.d = d
        self.beats = core.load_json(d / "beats.json")
        for bt in self.beats:
            if isinstance(bt.get("label"), str):
                bt["label"] = {"text": bt["label"], "kind": "stamp"}
            if bt.get("label") and not bt["label"].get("text"):
                bt["label"] = None
        self.tl = core.load_json(d / "timeline.json")
        raw_rings = core.load_json(d / "rings.json", {})
        self.rings = {int(k): v for k, v in raw_rings.items() if self.beats[int(k)].get("ring") and _ring_ok(v)}
        self._cache: dict = {}
        self._depth: dict = {}
        self.frames = []
        for i in range(len(self.beats)):
            ps = core.frame_paths(d, i)
            if not ps:
                raise RuntimeError(f"нема кадру {i}")
            self.frames.append(ps)
        self.gx, self.gy = np.meshgrid(np.arange(W, dtype=np.float32), np.arange(H, dtype=np.float32))
        rng = np.random.default_rng(11)
        self.dust = np.stack([rng.uniform(0, W, 46), rng.uniform(0, H, 46), rng.uniform(6, 16, 46), rng.uniform(-14, -4, 46), rng.uniform(1.0, 2.6, 46)], 1)
        self.embers = np.stack([rng.uniform(0, W, 38), rng.uniform(0, H, 38), rng.uniform(-30, 30, 38), rng.uniform(-120, -55, 38), rng.uniform(1.5, 3.2, 38)], 1)
        self.total = self.tl["total_s"]
        self.n_frames = int(math.ceil(self.total * FPS))
        yy, xx = np.mgrid[0:H, 0:W]
        r = np.sqrt(((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2)
        self.vig = (1 - 0.28 * np.clip(r - 0.55, 0, 1) ** 1.5)[..., None].astype(np.float32)
        band = np.clip((yy / H - 0.70) / 0.30, 0, 1)
        self.band = (1 - 0.42 * band)[..., None].astype(np.float32)
        self.noise = np.random.default_rng(5).normal(0, 3.2, (H, W, 1)).astype(np.float32)
        self.chunks = self._subtitle_chunks()
        self.hook = self.beats[0].get("hook", "")
        self.mont = {**DEFAULT_MONTAGE, **core.load_json(d / "montage.json", {})}
        g = GRADES.get(self.mont["grade"])
        self.grade = np.float32(g).reshape(1, 1, 3) if g and self.mont["grade"] != "ink" else None
        # серії бітів-плиток (поле grid = назва серії, підряд): біт -> список бітів серії (2-4), «інвентар»
        self.grid_runs = {}
        for i, b in enumerate(self.beats):
            gname = b.get("grid")
            if not gname:
                continue
            run = [j for j in range(len(self.beats)) if self.beats[j].get("grid") == gname]
            if 2 <= len(run) <= 4:
                self.grid_runs[i] = run
        # лічильник днів: день, що діє на кожному біті (поле "day" ставиться на біт, де починається новий день)
        self.day_at, cur_day = [], None
        for b in self.beats:
            cur_day = b.get("day", cur_day)
            self.day_at.append(cur_day or None)     # day=0: лічильник ховається (після останнього дня)
        # суцільні серії бітів з кінорамкою -> часові відрізки
        self.bar_runs, cur = [], None
        for b, tb in zip(self.beats, self.tl["beats"]):
            if b.get("bars"):
                cur = [tb["s"], tb["e"]] if cur is None else [cur[0], tb["e"]]
            elif cur is not None:
                self.bar_runs.append(tuple(cur))
                cur = None
        if cur is not None:
            self.bar_runs.append(tuple(cur))

    def img(self, i: int, k: int = 0) -> np.ndarray:
        """Кадр біта (k-та поза анімації) з невеликим кешем (відео на сотні кадрів не вміщується в пам'ять)."""
        im = self._cache.get((i, k))
        if im is None:
            im = cv2.imread(str(self.frames[i][k]))
            if len(self._cache) > 12:
                self._cache.pop(next(iter(self._cache)))
            self._cache[(i, k)] = im
        return im

    def depth(self, i: int, size):
        """Карта глибини якірного кадру в розмірі зображення (або None)."""
        if i not in self._depth:
            f = self.d / "depth" / f"beat_{i:03d}.npy"
            self._depth[i] = cv2.resize(np.load(f).astype(np.float32), size, interpolation=cv2.INTER_LINEAR) if f.exists() else None
        return self._depth[i]

    def anim_index(self, bi: int, lt: float) -> int:
        n = len(self.frames[bi])
        an = self.beats[bi].get("anim")
        if n < 2 or not an:
            return 0
        k = int(lt / ANIM_DT)
        return k % n if an.get("loop") else min(k, n - 1)

    # --- субтитри ---
    def _subtitle_chunks(self):
        words = self.tl["words"]
        chunks, cur = [], []
        for i, w in enumerate(words):
            cur.append(i)
            end_punct = w["w"][-1] in ".?!:;,"
            gap = (words[i + 1]["s"] - w["e"]) if i + 1 < len(words) else 9
            if len(cur) >= 3 or end_punct or gap > 0.45:
                chunks.append(cur)
                cur = []
        if cur:
            chunks.append(cur)
        return chunks

    def subtitle(self, t: float):
        words = self.tl["words"]
        for ci, ch in enumerate(self.chunks):
            start = words[ch[0]]["s"]
            end = words[self.chunks[ci + 1][0]]["s"] if ci + 1 < len(self.chunks) else self.total
            if start - 0.03 <= t < end:
                active = 0
                for k, wi in enumerate(ch):
                    if t >= words[wi]["s"] - 0.03:
                        active = k
                return tuple(re_clean(words[wi]["w"]) for wi in ch), active, t - start
        return None

    # --- камера ---
    def cam(self, bi: int, lt: float, dur: float):
        b = self.beats[bi]
        p = lt / max(dur, 1e-3)
        e = ease(p)
        fx, fy = {"L": 0.36, "C": 0.5, "R": 0.64}.get(b.get("focus", "C"), 0.5), 0.5
        ring = self.rings.get(bi)
        if ring:
            fx, fy = (ring[0] + ring[2]) / 2, (ring[1] + ring[3]) / 2
        kind = b.get("cam", "push")
        if kind == "push":
            z, cx, cy = lerp(BASE_ZOOM, 1.26, e), lerp(0.5, fx, e * 0.8), lerp(0.5, fy, e * 0.6)
        elif kind == "pull":
            z, cx, cy = lerp(1.30, BASE_ZOOM, e), lerp(fx, 0.5, e * 0.8), lerp(fy, 0.5, e * 0.6)
        elif kind == "panl":
            z, cx, cy = 1.17, lerp(0.57, 0.43, e), 0.5
        elif kind == "panr":
            z, cx, cy = 1.17, lerp(0.43, 0.57, e), 0.5
        elif kind == "punch":
            q = ease(lt / 0.32)
            z, cx, cy = lerp(1.42, 1.22, q) - 0.06 * p, lerp(0.5, fx, 0.6), lerp(0.5, fy, 0.5)
        elif kind == "drift_up":
            z, cx, cy = 1.16, 0.5, lerp(0.55, 0.45, e)
        elif kind == "rack":       # повільний наїзд, різкість переводиться між планами (blur за глибиною, див. beat_image)
            z, cx, cy = lerp(1.14, 1.22, e), lerp(0.5, fx, e * 0.5), 0.5
        elif kind == "tilt":       # «голландський кут»: кадр повертається на кілька градусів (rot у cam_extra)
            z, cx, cy = lerp(1.22, 1.30, e), lerp(0.47, 0.53, e), 0.5
        elif kind == "snap":       # стоїть, потім різкий двоступеневий наїзд у другій половині біта
            q1, q2 = ease(min(max((p - 0.45) / 0.12, 0), 1)), ease(min(max((p - 0.70) / 0.10, 0), 1))
            z = BASE_ZOOM + 0.12 * q1 + 0.14 * q2
            cx, cy = lerp(0.5, fx, q1 * 0.7), lerp(0.5, fy, q1 * 0.5)
        elif kind == "hand":       # «з рук»: легке дихання камери без напрямку (тремтіння в cam_extra)
            z, cx, cy = 1.16 + 0.015 * math.sin(lt * 1.3), 0.5, 0.5
        elif kind == "crane":      # «кран»: великий план зверху вниз із відкриттям (від деталі до загального)
            z, cx, cy = lerp(1.38, BASE_ZOOM + 0.02, e), lerp(fx, 0.5, e), lerp(0.36, 0.5, e)
        else:  # drift_down
            z, cx, cy = 1.16, 0.5, lerp(0.45, 0.55, e)
        half = 0.5 / z
        return z, min(max(cx, half), 1 - half), min(max(cy, half), 1 - half)

    def shake(self, bi: int, lt: float):
        fx = self.beats[bi].get("fx")
        if fx in ("slash", "impact") and lt < 0.38:
            a = (18 if fx == "impact" else 11) * (1 - lt / 0.38)
            return a * math.sin(lt * 90), a * math.cos(lt * 71)
        if self.beats[bi].get("sfx") in ("x_thud", "x_boom", "x_sting") and lt < 0.32:
            a = 7 * (1 - lt / 0.32)
            return a * math.sin(lt * 70), a * math.cos(lt * 83)
        return 0.0, 0.0

    def cam_extra(self, bi: int, lt: float, dur: float):
        """Поворот (градуси) і тремтіння «з рук» (пікселі) для камер tilt / hand / snap."""
        kind = self.beats[bi].get("cam")
        rot = jx = jy = 0.0
        if kind == "tilt":
            rot = (1 if bi % 2 else -1) * lerp(1.2, 3.4, ease(lt / max(dur, 1e-3)))
        if kind in ("hand", "snap"):
            k = 4.0 if kind == "hand" else 2.5
            jx = k * (math.sin(lt * 2.1 + bi) + 0.5 * math.sin(lt * 5.3))
            jy = k * (math.cos(lt * 1.7 + bi) + 0.5 * math.sin(lt * 4.1))
        return rot, jx, jy

    def beat_image(self, bi: int, lt: float):
        """Кадр біта без накладок + матриця камери (для обведення)."""
        s, e = self.tl["beats"][bi]["s"], self.tl["beats"][bi]["e"]
        dur = e - s
        lt = min(max(lt, 0.0), dur)
        z, cx, cy = self.cam(bi, lt, dur)
        img = self.img(bi, self.anim_index(bi, lt))
        ih, iw = img.shape[:2]
        sc = W / iw * z
        sx, sy = self.shake(bi, lt)
        rot, jx, jy = self.cam_extra(bi, lt, dur)
        M = np.float32([[sc, 0, W / 2 - sc * cx * iw + sx + jx], [0, sc, H / 2 - sc * cy * ih + sy + jy]])
        if rot:                                     # поворот навколо центру кадру (без паралаксу)
            R = cv2.getRotationMatrix2D((W / 2, H / 2), rot, 1.0)
            M = (R @ np.vstack([M, [0, 0, 1]])).astype(np.float32)
            return cv2.warpAffine(img, M, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE), M, (iw, ih)
        dep = self.depth(bi, (iw, ih)) if PARALLAX_PX else None
        if dep is None:
            return cv2.warpAffine(img, M, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE), M, (iw, ih)
        # паралакс 2.5D: ближні шари зсуваються сильніше за далекі, напрям чергується від біта до біта
        dout = cv2.warpAffine(dep, M, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
        shift = (1 if bi % 2 else -1) * PARALLAX_PX * (2 * ease(lt / max(dur, 1e-3)) - 1) * (dout - 0.45)
        map_x = (self.gx - M[0, 2]) / M[0, 0] - shift / M[0, 0]
        map_y = (self.gy - M[1, 2]) / M[1, 1]
        out = cv2.remap(img, map_x.astype(np.float32), map_y.astype(np.float32), cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
        if self.beats[bi].get("cam") == "rack":     # переведення різкості: фокус їде від далекого плану до ближнього (або навпаки)
            p = ease(lt / max(dur, 1e-3))
            f = lerp(0.25, 0.80, p) if bi % 2 else lerp(0.80, 0.25, p)
            wgt = np.clip(np.abs(dout - f) * 2.4 - 0.15, 0, 1)[..., None]
            blur = cv2.GaussianBlur(out, (0, 0), 6)
            out = (out * (1 - wgt) + blur * wgt).astype(np.uint8)
        return out, M, (iw, ih)

    def grid_image(self, bi: int, lt: float):
        """Сітка-«інвентар» (перелік зброї, обладунку тощо): біти серії grid з'являються плитками одна за одною
        на темному лаковому тлі з кремовою рамкою (2 / 3 в ряд або 2x2); попередні плитки тьмяніють."""
        run = self.grid_runs[bi]
        pos, n = run.index(bi), len(run)
        frame = np.full((H, W, 3), (22, 20, 34), np.uint8)
        g = 14
        if n == 4:
            cols, rows, th = 2, 2, (H - 120 - g) // 2
        else:
            cols, rows, th = n, 1, int(H * (0.60 if n == 3 else 0.68))
        tw = (W - (cols + 1) * g) // cols
        if n == 4:
            tw = min(tw, int(th * 16 / 9))
        x_off = (W - cols * tw - (cols - 1) * g) // 2 - g
        y0 = (H - rows * th - (rows - 1) * g) // 2 - 20
        t_run = self.tl["beats"][bi]["s"] + lt - self.tl["beats"][run[0]]["s"]
        for j, bj in enumerate(run):
            r, c = divmod(j, cols)
            x, y = x_off + g + c * (tw + g), y0 + r * (th + g)
            if j > pos:
                cv2.rectangle(frame, (x, y), (x + tw, y + th), (70, 60, 52), 2, cv2.LINE_AA)
                continue
            src = self.img(bj)
            ih, iw = src.shape[:2]
            zz = 1.0 + 0.04 * min(t_run / 6.0, 1.0)
            ca = tw / th
            cw, ch = (ih * ca, ih) if iw / ih > ca else (iw, iw / ca)
            cw, ch = cw / zz, ch / zz
            sx0, sy0 = int((iw - cw) / 2), int((ih - ch) / 2)
            tile = cv2.resize(src[sy0:sy0 + int(ch), sx0:sx0 + int(cw)], (tw, th), interpolation=cv2.INTER_AREA)
            if j < pos:
                frame[y:y + th, x:x + tw] = (tile * 0.55).astype(np.uint8)
                cv2.rectangle(frame, (x - 2, y - 2), (x + tw + 1, y + th + 1), (120, 140, 160), 2, cv2.LINE_AA)
                continue
            q = min(lt / 0.28, 1.0)
            sc2 = lerp(0.82, 1.0, ease_out_back(q))
            w2, h2 = max(int(tw * sc2), 2), max(int(th * sc2), 2)
            t2 = cv2.resize(tile, (w2, h2))
            xx, yy = x + (tw - w2) // 2, y + (th - h2) // 2
            roi = frame[yy:yy + h2, xx:xx + w2]
            a = min(q * 3, 1.0)
            frame[yy:yy + h2, xx:xx + w2] = (roi * (1 - a) + t2 * a).astype(np.uint8)
            cv2.rectangle(frame, (xx - 3, yy - 3), (xx + w2 + 2, yy + h2 + 2), (212, 238, 250), 4, cv2.LINE_AA)
        return frame

    def apply_look(self, frame, bi, t):
        """Вигляд біта: mono = шок (чорно-білий з червоним, жорсткий контраст), sepia = легенда/спогад (стара гравюра)."""
        look = self.beats[bi].get("look")
        if look == "mono":
            g = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).astype(np.float32)
            g = np.clip((g - 110) * 1.45 + 110, 0, 255)
            frame[:] = np.stack([g * 0.72, g * 0.74, np.minimum(g * 1.12 + 10, 255)], -1).astype(np.uint8)
        elif look == "sepia":
            g = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).astype(np.float32)
            frame[:] = np.clip(np.stack([g * 0.70 + 18, g * 0.88 + 22, g * 1.02 + 30], -1), 0, 255).astype(np.uint8)

    # --- накладки біта ---
    def draw_ring(self, frame, bi, lt, M, size):
        box = self.rings.get(bi)
        if not box:
            return
        t0, tdraw = 0.22, 0.34
        q = (lt - t0) / tdraw
        if q <= 0:
            return
        q = min(q, 1.0)
        iw, ih = size
        x0, y0, x1, y1 = box
        pw, ph = (x1 - x0) * iw, (y1 - y0) * ih
        cxs, cys = (x0 + x1) / 2 * iw, (y0 + y1) / 2 * ih
        a, b = max(pw * 0.62 + 14, 60), max(ph * 0.62 + 12, 50)
        pts = []
        steps = 80
        for k in range(int(steps * q) + 1):
            th = -math.pi * 0.75 + 2 * math.pi * 1.04 * (k / steps)
            wob = 1 + 0.010 * math.sin(2 * th + 0.8) + 0.05 * (k / steps) ** 2   # майже рівний овал, трохи «недомальований» кінець
            px, py = cxs + a * wob * math.cos(th), cys + b * wob * math.sin(th)
            pts.append((M[0, 0] * px + M[0, 2], M[1, 1] * py + M[1, 2]))
        pts = np.array(pts, np.int32).reshape(-1, 1, 2)
        pulse = 1 + 0.12 * math.sin((lt - t0) * 9) if q >= 1 else 1
        cv2.polylines(frame, [pts], False, (255, 255, 255), int(15 * pulse), cv2.LINE_AA)
        cv2.polylines(frame, [pts], False, VERMILION_BGR, int(8 * pulse), cv2.LINE_AA)

    def draw_particles(self, frame, bi, t):
        """Пил у повітрі на всіх кадрах; іскри — на кадрах із вогнем."""
        ov = frame.copy()
        for x0, y0, vx, vy, r in self.dust:
            kind = self.mont["particles"]
            if kind in ("petals", "snow"):          # падають згори, гойдаються
                px = (x0 + 26 * math.sin(t * 0.9 + y0)) % W
                py = (y0 - vy * t * (2.2 if kind == "snow" else 1.6)) % H
            else:
                px, py = (x0 + vx * t) % W, (y0 + vy * t) % H
            rr = int(r * (1.6 if kind == "petals" else 1.0))
            if kind == "petals":
                cv2.ellipse(ov, (int(px), int(py)), (rr, max(rr // 2, 1)), (t * 60 + x0) % 180, 0, 360, PARTICLE_BGR[kind], -1, cv2.LINE_AA)
            else:
                cv2.circle(ov, (int(px), int(py)), rr, PARTICLE_BGR.get(kind, PARTICLE_BGR["dust"]), -1, cv2.LINE_AA)
        cv2.addWeighted(ov, 0.30 if self.mont["particles"] in ("petals", "snow") else 0.20, frame, 0.70 if self.mont["particles"] in ("petals", "snow") else 0.80, 0, dst=frame)
        txt = self.beats[bi].get("img", "").lower()
        if any(w in txt for w in ("burn", "fire", "flame", "torch", "smoke")):
            ov = frame.copy()
            for x0, y0, vx, vy, r in self.embers:
                x = (x0 + vx * t + 18 * math.sin(t * 2 + y0)) % W
                cv2.circle(ov, (int(x), int((y0 + vy * t) % H)), int(r), (40, 150, 255), -1, cv2.LINE_AA)
            cv2.addWeighted(ov, 0.55, frame, 0.45, 0, dst=frame)

    def draw_fx(self, frame, bi, lt):
        """Удар: біла діагональна смуга-розріз (slash) або розріз + спалах і червоне світло (impact)."""
        fx = self.beats[bi].get("fx")
        if fx not in ("slash", "impact") or lt > 0.5:
            return
        if lt < 0.22:
            q = lt / 0.22
            x0, y0 = int(lerp(-0.1, 0.55, ease(q)) * W), int(H * 0.82)
            x1, y1 = int(lerp(0.45, 1.1, ease(q)) * W), int(H * 0.12)
            ov = frame.copy()
            cv2.line(ov, (x0, y0), (x1, y1), (255, 255, 255), 26, cv2.LINE_AA)
            cv2.line(ov, (x0, y0), (x1, y1), (230, 245, 255), 8, cv2.LINE_AA)
            a = 0.85 * (1 - q * 0.4)
            cv2.addWeighted(ov, a, frame, 1 - a, 0, dst=frame)
        if fx == "impact":
            if lt < 0.09:
                frame[:] = (frame.astype(np.float32) * 0.25 + 255 * 0.75).astype(np.uint8)
            elif lt < 0.5:
                a = 0.35 * (1 - (lt - 0.09) / 0.41)
                red = np.empty_like(frame)
                red[:] = (30, 30, 200)
                cv2.addWeighted(red, a, frame, 1 - a, 0, dst=frame)

    def draw_day(self, frame, bi, lt):
        day = self.day_at[bi]
        if day is None:
            return
        sp = day_sprite(f"DAY {day}")
        q = lt / 0.3 if self.beats[bi].get("day") is not None else 1.0
        sc = lerp(1.7, 1.0, ease_out_back(min(q, 1.0))) if q < 1 else 1.0
        y = H * 0.115 + (H * 0.085 if any(s - 0.01 <= self.tl["beats"][bi]["s"] + lt <= e for s, e in self.bar_runs) else 0)
        blit(frame, sp, 36 + sp.shape[1] / 2, y, scale=sc * 0.82, alpha=min(q * 3, 1.0))

    def draw_bars(self, frame, t):
        """Кінорамка: чорні смуги заїжджають на початку серії бітів з "bars" і з'їжджають у кінці."""
        k = 0.0
        for s, e in self.bar_runs:
            if s - 0.01 <= t <= e:
                k = min(1.0, (t - s) / 0.5, (e - t) / 0.5)
                break
        h = int(H * BARS_H * ease(max(0.0, k)))
        if h > 0:
            frame[:h] = 0
            frame[H - h:] = 0

    def draw_chapter(self, frame, bi, lt):
        ch = self.beats[bi].get("chapter")
        if not ch or lt > 2.6 or (bi == 0 and self.hook):
            return
        sp = chapter_sprite(ch)
        if self.mont["chapter"] == "card":          # картка по центру: вискакує, тримається, тане
            q = min(lt / 0.3, 1.0)
            a = 1.0 if lt < 2.0 else max(0.0, 1 - (lt - 2.0) / 0.4)
            blit(frame, sp, W / 2, H * 0.42, scale=1.35 * lerp(1.5, 1.0, ease_out_back(q)), alpha=min(q * 3, 1.0) * a)
            return
        q = lt / 0.35
        x = lerp(-sp.shape[1] / 2, sp.shape[1] / 2 + 36, ease_out_back(min(q, 1.0), 1.2)) if lt < 2.2 else lerp(sp.shape[1] / 2 + 36, -sp.shape[1] / 2, ease((lt - 2.2) / 0.4))
        blit(frame, sp, x, H * 0.11)

    def draw_label(self, frame, bi, lt):
        lab = self.beats[bi].get("label")
        if not lab or (bi == 0 and self.hook):
            return
        q = (lt - 0.12) / 0.26
        if q <= 0:
            return
        sp = stamp_sprite(lab["text"].upper())
        left_side = self.beats[bi].get("focus", "C") == "R"
        cx = W * (0.24 if left_side else 0.76) if self.beats[bi].get("focus", "C") != "C" else W * 0.76
        cy = H * 0.17
        blit(frame, sp, cx, cy, scale=lerp(1.7, 1.0, ease_out_back(q)), alpha=min(q * 3, 1))

    def hook_items(self) -> list[tuple[str, float]]:
        """Гачок = рядок штампів угорі (рішення 2026-10-24: гігантський текст на весь кадр закривав картинку).
        beats[0]["hook"] = "47 MEN|2 YEARS|1 NIGHT", beats[0]["hook_t"] = [секунди появи кожного штампа] (інакше кожні 0.9 с)."""
        parts = [p.strip().upper() for p in str(self.hook).split("|") if p.strip()]
        times = list(self.beats[0].get("hook_t") or [])
        times += [0.08 + 0.9 * k for k in range(len(times), len(parts))]
        return list(zip(parts, times))

    def draw_hook(self, frame, t):
        if not self.hook:
            return
        items = self.hook_items()
        end = max(tt for _, tt in items) + HOOK_HOLD
        if t > end + 0.3:
            return
        sc, gap = 0.8, 16
        sprites = [stamp_sprite(p) for p, _ in items]
        widths = [s.shape[1] * sc for s in sprites]
        x = (W - sum(widths) - gap * (len(widths) - 1)) / 2
        fade = 1.0 if t < end else max(0.0, 1 - (t - end) / 0.3)
        style = self.mont.get("hook", "stamp")
        if style == "caption":                      # титри накопичуються зверху ліворуч, виїжджають зліва
            for k, (p, t0) in enumerate(items):
                q = (t - t0) / 0.30
                if q > 0:
                    sp = caption_sprite(p)
                    x = lerp(-sp.shape[1] / 2, 40 + sp.shape[1] / 2, ease(min(q, 1.0)))
                    blit(frame, sp, x, H * 0.09 + k * 84, alpha=min(q * 2, 1.0) * fade)
            return
        if style == "seal":                         # печатки стовпчиком праворуч, «удар» зменшенням
            for k, (p, t0) in enumerate(items):
                q = (t - t0) / 0.20
                if q > 0:
                    sp = seal_sprite(p)
                    blit(frame, sp, W - 40 - sp.shape[1] / 2, H * 0.11 + k * 96,
                         scale=lerp(1.6, 1.0, ease_out_back(min(q, 1.0))), alpha=min(q * 3, 1.0) * fade)
            return
        if style == "flash":                        # одне слово за раз по центру вгорі
            cur = [(p, t0) for p, t0 in items if t >= t0]
            if cur:
                p, t0 = cur[-1]
                q = (t - t0) / 0.18
                nxt = [t1 for _, t1 in items if t1 > t0]
                a = fade if not nxt else max(0.0, min(1.0, (nxt[0] - t) / 0.12))
                blit(frame, flash_sprite(p), W / 2, H * 0.70, scale=lerp(1.35, 1.0, ease_out_back(min(q, 1.0))), alpha=min(q * 3, 1.0) * a)
            return
        for sp, (_, t0), w in zip(sprites, items, widths):
            q = (t - t0) / 0.22
            if q > 0:
                blit(frame, sp, x + w / 2, H * 0.12, scale=sc * lerp(1.8, 1.0, ease_out_back(min(q, 1.0))), alpha=min(q * 3, 1.0) * fade)
            x += w + gap

    def draw_subs(self, frame, t):
        s = self.subtitle(t)
        if not s:
            return
        words, active, lt = s
        sp = sub_sprite(words, active, SUB_ACTIVE.get(self.mont["subs"], YELLOW))
        pop = 1 + 0.10 * max(0.0, 1 - lt / 0.12) if lt < 0.12 else 1.0
        blit(frame, sp, W / 2, H * 0.885, scale=pop)

    # --- кадр часу t ---
    def frame(self, t: float) -> np.ndarray:
        beats = self.tl["beats"]
        bi = next((i for i, b in enumerate(beats) if b["s"] <= t < b["e"]), len(beats) - 1)
        lt = t - beats[bi]["s"]
        img, M, size = self.beat_image(bi, lt)
        if bi in self.grid_runs:
            img = self.grid_image(bi, lt)
        tr = self.beats[bi].get("tr", "cut") if bi > 0 else "cut"
        if tr in TR_DUR and lt < TR_DUR[tr]:
            p = lt / TR_DUR[tr]
            prev = self.grid_image(bi - 1, 1e9) if bi - 1 in self.grid_runs else self.beat_image(bi - 1, 1e9)[0]
            if tr == "dissolve":
                a = ease(p)
                img = (prev.astype(np.float32) * (1 - a) + img.astype(np.float32) * a).astype(np.uint8)
            elif tr == "burn":                       # теплий «засвіт»: помаранчева пляма пролітає кадр, під нею змішування
                a = ease(p)
                mix = prev.astype(np.float32) * (1 - a) + img.astype(np.float32) * a
                cx = lerp(-0.2, 1.2, p) * W
                leak = np.exp(-(((self.gx - cx) / (W * 0.28)) ** 2))[..., None] * math.sin(math.pi * p)
                img = np.clip(mix + leak * np.float32([60, 150, 255]) * 0.9, 0, 255).astype(np.uint8)
            elif tr == "iris":                       # коло розкривається з центру
                r = ease(p) * math.hypot(W, H) / 2
                mask = (((self.gx - W / 2) ** 2 + (self.gy - H / 2) ** 2) < r * r)[..., None]
                img = np.where(mask, img, (prev * 0.5).astype(np.uint8))
            elif tr == "whip":
                sh = int(W * ease(p))
                both = np.concatenate([prev, img], axis=1)[:, sh:sh + W]
                k = int(2 + 70 * math.sin(math.pi * p))
                img = cv2.blur(both, (k, 1))
            elif tr == "flash":
                a = (1 - p) ** 1.6 * 0.95
                img = (img.astype(np.float32) * (1 - a) + 255 * a).astype(np.uint8)
            elif tr == "ink":
                img = ink_wipe(prev, img, p, bi)
            elif tr == "zoom":
                if p < 0.5:
                    zz = 1 + 0.9 * ease(p / 0.5)
                    src = prev
                else:
                    zz = lerp(1.6, 1.0, ease((p - 0.5) / 0.5))
                    src = img
                Mz = cv2.getRotationMatrix2D((W / 2, H / 2), 0, zz)
                zoomed = cv2.warpAffine(src, Mz, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
                img = cv2.blur(zoomed, (1 + int(12 * math.sin(math.pi * p)) * 2, 1 + int(12 * math.sin(math.pi * p)) * 2)) if 0.1 < p < 0.9 else zoomed
        f = img.astype(np.float32) * self.vig * self.band + self.noise
        if self.grade is not None:
            f = f * self.grade
        frame = np.clip(f, 0, 255).astype(np.uint8)
        if self.mont["grade"] == "ink":              # приглушені кольори, сильніший контраст (суворий тон)
            g = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)[..., None].astype(np.float32)
            frame = np.clip((frame.astype(np.float32) * 0.7 + g * 0.3 - 128) * 1.12 + 128, 0, 255).astype(np.uint8)
        self.apply_look(frame, bi, t)
        self.draw_particles(frame, bi, t)
        self.draw_fx(frame, bi, lt)
        self.draw_bars(frame, t)
        self.draw_ring(frame, bi, lt, M, size)
        self.draw_label(frame, bi, lt)
        self.draw_chapter(frame, bi, lt)
        self.draw_day(frame, bi, lt)
        self.draw_hook(frame, t)
        self.draw_subs(frame, t)
        if t > self.total - 0.45:
            frame = (frame.astype(np.float32) * max(0.0, (self.total - t) / 0.45)).astype(np.uint8)
        return frame

    # --- SFX ---
    def sfx_layers(self):
        beats, out = self.tl["beats"], []
        used_t = []

        def add(tag, t, gain=0.0, gap=0.28):
            if not sfx.path_for(tag).exists():
                return
            if any(abs(t - u) < gap for u in used_t):
                return
            used_t.append(t)
            if tag.startswith("amb_"):
                out.append(audio_mix.Layer(sfx.path_for(tag), max(t, 0.0), SFX_ACCENT_GAIN_DB + gain + AMB_GAIN_DB,
                                           length_s=AMB_LEN_S, fade_in_s=0.8, fade_out_s=2.0))
                return
            out.append(audio_mix.Layer(sfx.path_for(tag), max(t, 0.0), SFX_ACCENT_GAIN_DB + gain, fade_out_s=0.25))

        for i, b in enumerate(self.beats):
            s = beats[i]["s"]
            tr = b.get("tr", "cut") if i else "cut"
            if tr == "whip":
                add("x_whoosh", s - 0.05)
            elif tr == "flash":
                add("x_swish", s - 0.02, 2)
            elif tr in ("zoom", "ink", "iris"):
                add("x_swish", s - 0.05)
            elif tr == "burn":
                add("x_whoosh", s - 0.1, -5)
            if b.get("sfx"):
                add(b["sfx"], s + 0.04, gap=2.6)
            if b.get("day") is not None:
                add("x_thud", s + 0.06, -2, gap=0.2)
            if b.get("label") and not (i == 0 and self.hook):
                add("x_ding", s + 0.14, -3)
            if self.rings.get(i):
                add("x_click", s + 0.22, -4)
        if self.hook:
            for _, t0 in self.hook_items():
                add("x_thud", t0 + 0.04, -3, gap=0.2)
        return out


def re_clean(w: str) -> str:
    return w.strip()


def _render_part(args) -> str:
    """Один відрізок кадрів → окремий mp4 (виконується в окремому процесі)."""
    slug, start, end, path = args
    cv2.setNumThreads(1)
    sc = Scene(slug)
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}", "-r", str(FPS),
           "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "21", "-g", "60", "-pix_fmt", "yuv420p", str(path)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        for n in range(start, end):
            proc.stdin.write(sc.frame(n / FPS).tobytes())
        proc.stdin.close()
        err = proc.stderr.read().decode("utf-8", "replace")
        if proc.wait() != 0:
            raise RuntimeError("ffmpeg: " + err[-600:])
    finally:
        if proc.poll() is None:
            proc.kill()
    return str(path)


def render(slug: str, log=print, workers: int = 6) -> Path:
    from concurrent.futures import ProcessPoolExecutor
    sc = Scene(slug)
    d = sc.d
    silent = d / "video_silent.mp4"
    parts_dir = d / "parts"
    parts_dir.mkdir(exist_ok=True)
    n_parts = max(workers * 2, 2)                       # дрібніші шматки: збій не губить усе, готові шматки кешуються
    step = -(-sc.n_frames // n_parts)
    jobs = []
    for k in range(n_parts):
        start, end = k * step, min((k + 1) * step, sc.n_frames)
        if start < end:
            jobs.append((slug, start, end, parts_dir / f"p_{k:02d}.mp4"))
    todo = [j for j in jobs if not j[3].exists()]
    log(f"рендер: {sc.n_frames} кадрів, шматків {len(jobs)}, до рендеру {len(todo)}, процесів {workers}")
    # шматок пишеться в тимчасовий файл і перейменовується лише після успішного завершення
    tmp_jobs = [(a, b, c, e.with_suffix(".part.mp4")) for a, b, c, e in todo]
    done = 0
    with ProcessPoolExecutor(workers) as ex:
        for res, job in zip(ex.map(_render_part, tmp_jobs), todo):
            Path(res).replace(job[3])
            done += 1
            log(f"шматок {done}/{len(todo)} готовий")
    lst = parts_dir / "list.txt"
    lst.write_text(core.NL.join(f"file '{j[3].as_posix()}'" for j in jobs) + core.NL, encoding="utf-8")
    try:
        run_ffmpeg(["-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(silent)])
    except subprocess.CalledProcessError as exc:
        raise RuntimeError("ffmpeg concat: " + error_tail(exc))
    # звук: музика + SFX + озвучка
    twist = next((w["s"] for w in sc.tl["words"] if w["w"].lower().startswith("twist")), None)
    hits = [0.05, sc.tl["words"][-1]["s"] - 0.1]
    if twist:
        hits.append(twist - 0.6)
    last = 0.0
    for ln in sc.tl.get("lines", []):
        if ln["t"] - last >= 85 and ln["t"] < sc.total - 20:
            hits.append(ln["t"] - 0.05)
            last = ln["t"]
    wav = music.make(d / "music.wav", sc.total, hits_s=hits)
    layers = sc.sfx_layers()
    layers.append(audio_mix.Layer(wav, 0.0, MUSIC_GAIN_DB, length_s=sc.total + 0.5, fade_in_s=0.4, fade_out_s=1.4, kind="bed"))
    audio = d / "audio.m4a"
    audio_mix.mix_soundtrack(d / "voice.mp3", sc.total, layers, audio)
    final = d / "video.mp4"
    try:
        run_ffmpeg(["-i", str(silent), "-i", str(audio), "-c:v", "copy", "-af", "apad", "-c:a", "aac", "-b:a", "192k", "-t", f"{sc.total:.3f}", str(final)])
    except subprocess.CalledProcessError as exc:
        raise RuntimeError("ffmpeg mux: " + error_tail(exc))
    log(f"готово: {final}, SFX-шарів {len(layers) - 1}")
    return final
