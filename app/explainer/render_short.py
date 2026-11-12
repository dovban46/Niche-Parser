"""Монтаж Shorts (9:16): набагато динамічніший за довге відео. На відміну від довгого формату тут камера «б'є» на кожному біті:
різні розміри кадру (загальний / середній / крупний план обличчя / вставка-предмет), різкий наїзд-«удар» з миттєвим затуханням, легкий
«ривок»-нахил, тряска на акцентах, перехідні ефекти (whip, zoom-through, спалах), кінетичні субтитри (слова вилітають по одному, активне слово
в жовтому прямокутнику), індикатор прогресу. Використовується, коли storyboard.json має "format": "short"."""
import math
import random

import cv2
import numpy as np
from PIL import Image, ImageDraw

from . import short_fx as fx
from . import style_fx as sfx
from . import scenes_fx as scn
from .render import (_emoji_img, FPS, GOLD, H, OUTLINE, W, YELLOW, SW, SH, GROUND_Y, CHAR_H, SUB_BASE, SUB_Y, Timeline, _font, ease_out, ease_out_back, smooth)

SHOT_ZOOM = {"wide": 1.0, "medium": 1.32, "close": 1.85, "insert": 1.6}
FACE_Y = 0.40          # куди в кадрі ставимо обличчя при крупному плані
_ORDER = ["wide", "close", "medium", "insert", "close", "wide", "medium", "close"]


class ShortTimeline(Timeline):
    is_short = True

    def __init__(self, beats, *a, **kw):
        # у Shorts немає «порожніх» кадрів: кожен біт без героя й предметів отримує героя (у хмарах/небі герой «стоїть» на хмарах)
        poses = ["stand", "talk_a", "point_right", "idea", "shrug", "present", "talk_b", "think"]
        for i, b in enumerate(beats):
            if not b.get("who") and not b.get("props"):
                b["who"] = "sage" if b["bg"] == "study" else "you"
                b["speak"] = b["who"] == "sage"
                b["pose"], b["expr"] = poses[i % len(poses)], "surprised" if i % 3 == 0 else "neutral"
                b["x"] = 0.35 if i % 2 else 0.65
        super().__init__(beats, *a, **kw)
        self._custom_caps = True
        self._assign_shots()

    # ---- розкадрування розмірів кадру й переходів ----
    def _assign_shots(self) -> None:
        prev = None
        self.shot_kind: list[str] = []
        self.tr_kind: list[str] = []
        k = 0
        for i, b in enumerate(self.beats):
            want = b.get("shot")
            if want not in SHOT_ZOOM:
                if b.get("props") and not b.get("who"):
                    want = "insert"
                elif not b.get("who"):
                    want = "wide"
                else:
                    want = _ORDER[k % len(_ORDER)]
                    k += 1
                    if want == "insert" and not b.get("props"):
                        want = "medium"
            if want == prev:   # два однакових поспіль не дозволяємо
                want = {"wide": "medium", "medium": "close", "close": "medium", "insert": "wide"}[want]
            if i == 0:
                want = "close" if b.get("who") else "wide"   # перший кадр: крупний план + текст-гачок
            self.shot_kind.append(want)
            prev = want
            tr = b.get("tr", "cut")
            if b.get("tr") in ("slash", "ink", "glitch", "pixel", "push", "shutter", "tear", "sweep"):
                pass                                         # режисерські переходи лишаємо
            elif i > 0 and self.beats[i - 1]["bg"] != b["bg"]:
                tr = "whip" if i % 2 else "zoom"          # зміна місця = помітний перехід
            elif i > 0 and b.get("big") and not self.beats[i - 1].get("big") and i % 3 == 0:
                tr = "flash"
            self.tr_kind.append(tr if i > 0 else "cut")

    # ---- камера ----
    def _focus_for(self, kind: str, bi: int, zoom: float) -> tuple[float, float, float]:
        """(cx, cy, z) у координатах сцени (SW×SH)."""
        ax = self._actor_x
        pc = self._prop_c
        if kind == "insert" and pc:
            fx, fy = pc[0], pc[1]
        elif kind in ("close", "medium") and ax is not None:
            head = GROUND_Y - CHAR_H * (0.80 if kind == "close" else 0.58)
            fx, fy = ax, head
        elif pc and ax is None:
            fx, fy = pc
        else:
            fx, fy = 0.5, 0.5
        cw, ch = SW / zoom, SH / zoom
        cx = fx * SW
        cy = fy * SH + (0.5 - FACE_Y) * ch if kind == "close" else fy * SH
        cx = min(max(cx, cw / 2), SW - cw / 2)
        cy = min(max(cy, ch / 2), SH - ch / 2)
        return cx, cy, zoom

    def camera(self, scene: np.ndarray, shot_idx: int, t: float) -> np.ndarray:
        bi, t0, t1, sub = self.shots[shot_idx]
        b = self.beats[bi]
        st = t - t0
        kind = self.shot_kind[bi]
        if sub > 0:   # довгий біт розбито: наступний під-кадр — інший розмір кадру
            kind = {"wide": "medium", "medium": "close", "close": "medium", "insert": "close"}[kind]
        z0 = SHOT_ZOOM[kind]
        z0 *= 1.0 + 0.06 * min(st / max(t1 - t0, 0.3), 1.0)              # повільне «дихання»-наїзд всередині кадру
        z0 *= 1.0 + 0.16 * math.exp(-st / 0.11)                          # різкий «удар» на початку кадру
        cx, cy, z = self._focus_for(kind, bi, z0)
        cw, ch = SW / z, SH / z
        ox = oy = 0.0
        if b.get("big") or b.get("sfx"):
            amp = 15 * math.exp(-st * 8)
            rnd = random.Random(int(t * FPS) * 31 + bi)
            ox, oy = rnd.uniform(-amp, amp), rnd.uniform(-amp, amp)
        cx = min(max(cx + ox, cw / 2), SW - cw / 2)
        cy = min(max(cy + oy, ch / 2), SH - ch / 2)
        s = W / cw
        M1 = np.array([[s, 0, -(cx - cw / 2) * s], [0, s, -(cy - ch / 2) * s], [0, 0, 1]], np.float64)
        ang = (1 if (shot_idx % 2) else -1) * 3.2 * math.exp(-st / 0.22) if kind in ("close", "insert") else 0.0
        if b.get("tilt"):   # «голландський кут»: нахил тримається весь біт (напруга)
            ang += float(b["tilt"]) * smooth(st / 0.18)
        if ang:
            R = np.vstack([cv2.getRotationMatrix2D((W / 2, H / 2), ang, 1.0), [0, 0, 1]])
            M = (R @ M1)[:2]
        else:
            M = M1[:2]
        self._frame_rects = [((x0 - (cx - cw / 2)) * s, (y0 - (cy - ch / 2)) * s, (x1 - (cx - cw / 2)) * s, (y1 - (cy - ch / 2)) * s)
                             for x0, y0, x1, y1 in self._rects]
        return cv2.warpAffine(scene, M.astype(np.float32), (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)

    # ---- переходи ----
    def transition(self, t: float):
        idx, sh = self.shot_at(t)
        bi, t0, _, sub = sh
        if sub != 0 or bi == 0:
            return None
        kind = self.tr_kind[bi]
        dur = {"whip": 0.16, "zoom": 0.20, "flash": 0.12, "slash": 0.30, "ink": 0.46, "glitch": 0.28, "pixel": 0.30, "push": 0.22, "shutter": 0.36, "tear": 0.34, "sweep": 0.5}.get(kind)
        if not dur or t - t0 >= dur:
            return None
        p = (t - t0) / dur
        a_t = t0 - 1e-3
        a_idx, _ = self.shot_at(a_t)
        a_img = self.camera(self.scene(a_idx, a_t), a_idx, a_t)
        b_img = self.camera(self.scene(idx, t), idx, t)
        if kind == "whip":
            e = smooth(p)
            off = int(e * W)
            canvas = np.concatenate([a_img, b_img], axis=1)[:, off: off + W]
            k = int(10 + 120 * math.sin(math.pi * p))
            return cv2.blur(canvas, (k | 1, 1))
        if kind == "zoom":
            za = 1.0 + 0.9 * smooth(p)
            zb = 1.5 - 0.5 * smooth(p)
            Ma = cv2.getRotationMatrix2D((W / 2, H / 2), 0, za)
            Mb = cv2.getRotationMatrix2D((W / 2, H / 2), 0, zb)
            wa = cv2.GaussianBlur(cv2.warpAffine(a_img, Ma, (W, H), borderMode=cv2.BORDER_REPLICATE), (0, 0), 6 * p + 0.1)
            wb = cv2.GaussianBlur(cv2.warpAffine(b_img, Mb, (W, H), borderMode=cv2.BORDER_REPLICATE), (0, 0), 6 * (1 - p) + 0.1)
            return cv2.addWeighted(wa, 1 - smooth(p), wb, smooth(p), 0)
        if kind == "sweep":
            return sfx.sweep_transition(a_img, b_img, p)
        if kind == "shutter":
            return scn.shutter_transition(a_img, b_img, p)
        if kind == "tear":
            return scn.tear_transition(a_img, b_img, p, seed=bi)
        if kind == "glitch":
            return sfx.glitch_transition(a_img, b_img, p, seed=bi)
        if kind == "pixel":
            return sfx.pixel_transition(a_img, b_img, p)
        if kind == "push":
            return sfx.push_transition(a_img, b_img, p)
        if kind == "slash":
            return fx.slash_transition(a_img, b_img, p)
        if kind == "ink":
            return fx.ink_transition(a_img, b_img, p, seed=bi)
        # flash
        w = 1 - abs(2 * p - 1)
        base = a_img if p < 0.5 else b_img
        return cv2.addWeighted(base, 1 - 0.85 * w, np.full_like(base, 255), 0.85 * w, 0)

    def _meter_vals(self, bi: int) -> tuple[dict, dict]:
        cur, prev = {}, {}
        for j in range(bi + 1):
            m = self.beats[j].get("meters")
            if m:
                prev = dict(cur)
                cur = {**cur, **{k: float(v) for k, v in m.items()}}
        return cur, prev

    def _draw_meters_hud(self, ov, d, bi: int, t: float) -> None:
        st = getattr(self, "style", None) or {}
        sfx.draw_title(ov, d, getattr(self, "series_title", ""), st.get("title", "pill"))
        cur, prev = self._meter_vals(bi)
        if cur:
            kind = st.get("hud", "meters")
            if kind == "meters":
                fx.draw_meters(d, cur, prev, t - self.starts[bi], getattr(self, "meter_names", None))
            else:
                sfx.draw_hud_values(kind, d, cur, prev, t - self.starts[bi], getattr(self, "meter_names", None))

    def apply_style(self, style: dict) -> None:
        """Оформлення відео з design.style: шрифт, колір наклейок; решта читається в overlays()."""
        from . import render as _r
        from . import style_kit as _k
        self.style = dict(style or {})
        if self.style.get("actors") == "silhouette":   # персонажі як силуети з підсвіткою
            from . import character as _ch
            _ch.set_sprite_fx(sfx.sprite_silhouette)
        serious = self.style.get("look") == "serious"
        _r.set_style(_k.font_path(self.style["font"]) if self.style.get("font") else None, _k.STICKER.get(self.style.get("sticker", "")),
                     "stencil" if serious else "pop")
        fx.SERIOUS = serious
        if serious:   # без дитячих елементів: емодзі-стікери, сонячні вибухи
            for b in self.beats:
                b.pop("emoji", None)
                b.pop("burst", None)

    # ---- RPG-HUD формату «Life as …»: назва серії, день, інвентар із предметами, що вилітають у слот ----
    def _hud_state(self, bi: int):
        day, items = None, []
        for j in range(bi + 1):
            b = self.beats[j]
            if b.get("day"):
                day = (b["day"], j)
            if b.get("gain"):
                items.append((b["gain"], j))
        return day, items

    def _draw_hud(self, ov: Image.Image, d: ImageDraw.ImageDraw, bi: int, t: float) -> None:
        title = getattr(self, "series_title", "")
        day, items = self._hud_state(bi)
        if not title and not day and not items:
            return
        # назва серії (біла «наклейка»)
        if title:
            f = _font(44)
            tw = d.textlength(title, font=f)
            x0, y0 = 54, 108
            d.rounded_rectangle((x0 - 6, y0 - 4, x0 + tw + 44, y0 + 70), radius=30, fill=(0, 0, 0, 70))
            d.rounded_rectangle((x0, y0, x0 + tw + 38, y0 + 64), radius=30, fill=(255, 255, 255, 255), outline=(*OUTLINE, 255), width=5)
            d.text((x0 + 19, y0 + 54), title, font=f, fill=(*OUTLINE, 255), anchor="ls")
        # день
        if day:
            txt, j = day
            age = t - self.starts[j]
            pop = 1.0 + 0.35 * max(0.0, 1 - age / 0.35) ** 2
            f = _font(int(60 * pop))
            tw = d.textlength(txt, font=f)
            x1, y0 = W - 54, 108
            d.rounded_rectangle((x1 - tw - 52, y0 - 4, x1 + 6, y0 + 84), radius=34, fill=(0, 0, 0, 70))
            d.rounded_rectangle((x1 - tw - 58, y0, x1, y0 + 78), radius=34, fill=(*YELLOW, 255), outline=(*OUTLINE, 255), width=6)
            d.text((x1 - tw - 29, y0 + 62), txt, font=f, fill=(*OUTLINE, 255), anchor="ls")
        # інвентар: іконки в круглих «наклейках»; новий предмет спершу вистрибує в центрі кадру, потім летить у слот
        size = int(0.105 * W)
        for n, (emo, j) in enumerate(items):
            slot = (54 + size / 2 + n * (size + 14), 270 + size / 2)
            age = t - self.starts[j]
            if age < 0.55:   # політ
                p = smooth(max(age - 0.28, 0) / 0.27)
                cx = (W / 2) * (1 - p) + slot[0] * p
                cy = (H * 0.34) * (1 - p) + slot[1] * p
                sc = (1.9 - 0.9 * p) * (ease_out_back(age / 0.28, 2.0) if age < 0.28 else 1.0)
            else:
                cx, cy, sc = slot[0], slot[1], 1.0
            r = size / 2 * sc
            d.ellipse((cx - r - 4, cy - r + 6, cx + r + 4, cy + r + 14), fill=(0, 0, 0, 70))
            d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(255, 255, 255, 255), outline=(*OUTLINE, 255), width=5)
            em = _emoji_img(emo, int(size * 0.62 * sc))
            if em is not None:
                ov.alpha_composite(em, (int(cx - em.width / 2), int(cy - em.height / 2)))

    # ---- накладки: кінетичні субтитри, прогрес ----
    def overlays(self, frame: np.ndarray, t: float):
        out = super().overlays(frame, t)
        _lk = self.beats[self.shot_at(t)[1][0]].get("look")
        if _lk == "nvg":
            out = sfx.look_nvg(out, t)
        elif _lk == "thermal":
            out = sfx.look_thermal(out, t)
        elif _lk == "oldfilm":
            out = sfx.look_oldfilm(out, t)
        idx, (bi, t0, t1, sub) = self.shot_at(t)[0], self.shot_at(t)[1]
        b = self.beats[bi]
        if isinstance(b.get("card"), dict):   # паперова сцена замість героя (досьє / до-після / маршрут)
            out = scn.apply(out, b["card"], t - self.starts[bi], max(self.ends[bi] - self.starts[bi], 0.4))
        im = Image.fromarray(out).convert("RGBA")
        ov = Image.new("RGBA", im.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(ov)
        age = t - self.starts[bi]
        dur_b = max(self.ends[bi] - self.starts[bi], 0.3)
        if getattr(self, "hud_mode", "inventory") == "meters":
            self._draw_meters_hud(ov, d, bi, t)
        else:
            self._draw_hud(ov, d, bi, t)
        if b.get("circle") and self._frame_rects:
            fx.draw_circle(d, self._frame_rects[0], age)
        if b.get("counter"):
            fx.draw_counter(d, b["counter"], age, dur_b)
        if b.get("decree"):
            fx.draw_decree(ov, d, b["decree"], age, dur_b)
        if b.get("choice"):
            fx.draw_choice(ov, d, b["choice"], int(b.get("pick", 0)), age, dur_b)
        if b.get("stamp"):
            fx.draw_stamp(ov, d, b["stamp"], age)
        cta_i = next((j for j, bb in enumerate(self.beats) if bb.get("cta")), None)
        if cta_i is not None:
            ck = (getattr(self, "style", None) or {}).get("cta", "pills")
            if not (0.0 <= t - self.starts[cta_i] <= 3.0):
                pass   # CTA показується лише у своєму вікні (раніше деякі варіанти «підглядали» до початку)
            elif ck in sfx.CTAS:
                sfx.CTAS[ck](ov, d, t - self.starts[cta_i])
            else:
                fx.draw_cta(ov, d, t - self.starts[cta_i])
        if bi == 0 and b.get("hook"):   # величезний хук-текст на нульовому кадрі
            sfx.draw_hook(ov, d, str(b["hook"]), age)
        if b.get("feed"):
            sfx.draw_feed(d, t, str(b.get("feed")) if isinstance(b.get("feed"), str) else "UAV-2")
        # прогрес-бар
        frac = min(max(t / self.total, 0.0), 1.0)
        _pk = (getattr(self, "style", None) or {}).get("progress", "line")
        if _pk == "player":
            sfx.draw_progress_player(d, frac, t, self.total)
        else:
            sfx.draw_progress(d, _pk, frac, t)
        # субтитри: слова з'являються по одному
        words = b.get("words", [])
        if words:
            n = len(words)
            k = math.ceil(n / 2)
            sizes = [n // k + (1 if i < n % k else 0) for i in range(k)]
            chunks, c = [], 0
            for s_ in sizes:
                chunks.append(words[c: c + s_])
                c += s_
            cur = chunks[0]
            for ch in chunks:
                if t >= ch[0]["s"] - 0.04:
                    cur = ch
            shown = [w for w in cur if t >= w["s"] - 0.03]
            if shown:
                base = SUB_BASE + 18
                if (getattr(self, "style", None) or {}).get("subs", "").startswith("doc"):
                    base = int(base * 0.84)
                items = []
                for i, w in enumerate(shown):
                    txt = w["w"].upper().strip(",.:;!?\"“”'‘’")
                    if w["w"].rstrip("\"”'’").endswith("?"):
                        txt += "?"
                    age = max(t - w["s"], 0.0)
                    pop = 1.0 + 0.32 * max(0.0, 1.0 - age / 0.2) ** 2 + (0.0 if age > 0.2 else 0.08 * math.sin(age * 40))
                    if (getattr(self, "style", None) or {}).get("subs", "").startswith("doc"):
                        pop = 1.0 + 0.06 * max(0.0, 1.0 - age / 0.15)
                    active = (i == len(shown) - 1) and age < 0.55
                    items.append((txt, int(base * pop), active))
                gap = 26
                fonts = [_font(sz) for _, sz, _ in items]
                widths = [d.textlength(tx, font=f) for (tx, _, _), f in zip(items, fonts)]
                total_w = sum(widths) + gap * (len(items) - 1)
                scale = min(1.0, (W * 0.9) / max(total_w, 1))
                if scale < 1.0:
                    fonts = [_font(int(sz * scale)) for _, sz, _ in items]
                    widths = [d.textlength(tx, font=f) for (tx, _, _), f in zip(items, fonts)]
                    total_w = sum(widths) + gap * (len(items) - 1)
                x = W / 2 - total_w / 2
                yb = SUB_Y * H
                from .style_kit import SUBS as _SUBS
                box_c, act_c, idle_c = _SUBS.get((getattr(self, "style", None) or {}).get("subs", "yellow"), _SUBS["yellow"])
                doc = (getattr(self, "style", None) or {}).get("subs", "").startswith("doc")
                typed = (getattr(self, "style", None) or {}).get("subs") == "typed"
                banner = (getattr(self, "style", None) or {}).get("subs") == "banner"
                if (getattr(self, "style", None) or {}).get("subs") == "doc_poster":   # темна смуга під рядком: контраст у дуотоні
                    hh = max(sz for _, sz, _ in items)
                    d.rectangle((x - 30, yb - hh * 0.98, x + total_w + 30, yb + hh * 0.3), fill=(8, 8, 10, 205))
                if banner:   # темна стрічка із золотими лініями, шрифт із засічками
                    hh = max(sz for _, sz, _ in items)
                    d.rectangle((x - 36, yb - hh * 1.0, x + total_w + 36, yb + hh * 0.3), fill=(26, 14, 12, 225))
                    d.line((x - 36, yb - hh * 1.0, x + total_w + 36, yb - hh * 1.0), fill=(236, 196, 96, 255), width=4)
                    d.line((x - 36, yb + hh * 0.3, x + total_w + 36, yb + hh * 0.3), fill=(236, 196, 96, 255), width=4)
                if typed:   # друкарська смуга під рядком; активне слово — на жовтому маркері
                    hh = max(sz for _, sz, _ in items)
                    d.rectangle((x - 30, yb - hh * 0.98, x + total_w + 30, yb + hh * 0.3), fill=(12, 12, 12, 215))
                for (tx, sz, active), f, wd in zip(items, fonts, widths):
                    if banner:
                        if active:
                            d.rectangle((x - 8, yb - sz * 0.88, x + wd + 8, yb + sz * 0.2), fill=(150, 26, 40, 255))
                        d.text((x, yb), tx, font=f, fill=(*(box_c if active else idle_c), 255), anchor="ls")
                        x += wd + gap
                        continue
                    if typed:
                        if active:
                            d.rectangle((x - 8, yb - sz * 0.86, x + wd + 8, yb + sz * 0.18), fill=(*box_c, 255))
                        d.text((x, yb), tx, font=f, fill=(*(act_c if active else idle_c), 255), anchor="ls")
                        x += wd + gap
                        continue
                    if doc:
                        d.text((x + 3, yb + 4), tx, font=f, fill=(0, 0, 0, 170), anchor="ls")
                        d.text((x, yb), tx, font=f, fill=(*(box_c if active else idle_c), 255), stroke_width=5, stroke_fill=(10, 10, 12, 255), anchor="ls")
                        x += wd + gap
                        continue
                    if active:
                        d.rounded_rectangle((x - 22, yb - sz * 0.92, x + wd + 22, yb + sz * 0.22), radius=26, fill=(*box_c, 255), outline=(*OUTLINE, 255), width=7)
                        d.text((x, yb), tx, font=f, fill=(*act_c, 255), anchor="ls")
                    else:
                        d.text((x, yb), tx, font=f, fill=(255, 255, 255, 255), stroke_width=10, stroke_fill=(*OUTLINE, 255), anchor="ls")
                    x += wd + gap
        # емодзі-стікер: у кадрі (екранні координати), вилітає з «пружинкою»
        if b.get("emoji"):
            from .render import _emoji_img
            sticker = _emoji_img(b["emoji"], int(0.24 * W))
            bt = t - self.starts[bi]
            pop = ease_out_back(bt / 0.3, 2.2)
            if sticker is not None and pop > 0.02:
                w2, h2 = max(int(sticker.width * pop), 2), max(int(sticker.height * pop), 2)
                st_im = sticker.resize((w2, h2), Image.BILINEAR).rotate(math.sin(bt * 5) * 7, resample=Image.BICUBIC, expand=True)
                side = 0.80 if bi % 2 == 0 else 0.20
                ov.alpha_composite(st_im, (int(W * side - st_im.width / 2), int(H * 0.30 - st_im.height / 2 + math.sin(bt * 4) * 12)))
        # спалах на «ударі» початку біта
        if bi > 0 and self.tr_kind[bi] == "cut" and (b.get("big") or b.get("sfx")):
            fl = 0.30 * math.exp(-(t - self.starts[bi]) / 0.045)
            if fl > 0.02:
                d.rectangle((0, 0, W, H), fill=(255, 255, 255, int(255 * fl)))
        res = np.asarray(Image.alpha_composite(im, ov).convert("RGB"))
        impact = bool(b.get("stamp") or b.get("burst") or (b.get("sfx") and "x_sting" in b.get("sfx", [])))
        if impact:
            res = fx.chroma_ab(res, 12 * math.exp(-max(t - self.starts[bi], 0) / 0.09))
        gk = getattr(self, "grade", "")
        if gk == "warm":
            res = sfx.grade_warm(res)
        elif gk == "cool":
            res = sfx.grade_cool(res)
        elif gk == "vhs":
            res = sfx.grade_vhs(res, t)
        elif gk == "film":
            res = sfx.grade_film(res, t)
        elif gk == "sepia":
            res = sfx.grade_sepia(res, t)
        elif gk == "oldfilm":
            res = sfx.look_oldfilm(res, t)
        elif gk.startswith("duo_"):
            res = sfx.grade_duotone(res, gk)
        if gk == "night":
            res = fx.vignette(res, 0.62)
            res = np.clip(res.astype(np.float32) * np.array([1.0, 0.94, 0.96], np.float32), 0, 255).astype(np.uint8)
        return res
