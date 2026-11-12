"""[v6: персонаж-кухар згенерований у Google Flow (Nano Banana 2.1), файл _work/flow/chef_flow.jpg; код малює лише компонування й текст.
Стару процедурну версію кухаря лишено функцією chef() як запасну.]
Фірмовий стиль каналу «Хіба це можна їсти?»: аватар, банер, горизонтальний логотип — малюється кодом (Pillow),
без AI-кадрів і витрат. Персонаж: мультяшний кухар із виделкою, на якій підозріла рибка; біле тло, як у конкурента-еталона
за стилем (мультяшний персонаж у колі + простий білий банер), але інший герой і написи.
Змінити назву/кольори — у константах і запустити:  python channel_brand/build_brand.py"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
WORK, LOGO, BANNER = ROOT / "_work", ROOT / "logo", ROOT / "banner"
FONT = "C:/Windows/Fonts/comicbd.ttf"          # рукописний мультяшний, має кирилицю
NAME_LINES = ("Хіба це", "можна їсти?")

INK = (34, 26, 24)
SKIN, BLUSH = (247, 206, 168), (240, 150, 140)
WHITE = (255, 255, 255)
RED = (214, 64, 46)
BROWN = (120, 72, 40)
FISH, FISH_D = (92, 176, 186), (60, 130, 142)
STEEL = (200, 206, 214)
BLUE = (120, 190, 235)
S = 1000        # проєктний розмір полотна персонажа
SS = 3


class Pic:
    def __init__(self, size=S, bg=WHITE):
        self.k = SS * size / S
        self.size = size
        self.im = Image.new("RGB", (int(size * SS), int(size * SS)), bg)
        self.d = ImageDraw.Draw(self.im)

    def _p(self, pts):
        return [(x * self.k, y * self.k) for x, y in pts]

    def poly(self, pts, fill, outline=INK, w=0):
        if outline and w:
            self.d.polygon(self._p(pts), fill=outline, outline=outline, width=int(w * 2 * self.k))
        self.d.polygon(self._p(pts), fill=fill)

    def line(self, pts, width, fill=INK):
        p = self._p(pts)
        self.d.line(p, fill=fill, width=int(width * self.k), joint="curve")
        r = width * self.k / 2
        for x, y in (p[0], p[-1]):
            self.d.ellipse((x - r, y - r, x + r, y + r), fill=fill)

    def blob(self, shapes, fill, w):
        """Об'єднання еліпсів з єдиним зовнішнім контуром: shapes = [(cx, cy, rx, ry)]."""
        for cx, cy, rx, ry in shapes:
            self.d.ellipse(self._p([(cx - rx - w, cy - ry - w), (cx + rx + w, cy + ry + w)]), fill=INK)
        for cx, cy, rx, ry in shapes:
            self.d.ellipse(self._p([(cx - rx, cy - ry), (cx + rx, cy + ry)]), fill=fill)

    def result(self):
        return self.im.resize((self.size, self.size), Image.LANCZOS)


def chef(p: Pic):
    W = 14                                                    # товщина контуру
    # рука з виделкою (за тулубом)
    p.line([(735, 840), (830, 640)], 150, INK)
    p.line([(735, 840), (830, 640)], 150 - 2 * W, WHITE)
    p.line([(850, 600), (850, 290)], 30, INK)                  # ручка виделки
    p.line([(850, 600), (850, 290)], 30 - 2 * 6, STEEL)
    # плечі / кітель
    p.blob([(500, 1010, 330, 290)], WHITE, W)
    p.poly([(405, 742), (595, 742), (500, 835)], RED, INK, 8)  # хустинка
    for y in (905, 985):
        p.blob([(500, y, 22, 22)], RED, 7)
    # вуха й голова
    p.blob([(262, 545, 42, 55), (738, 545, 42, 55)], SKIN, W)
    p.blob([(500, 535, 252, 232)], SKIN, W)
    # капелюх
    p.blob([(335, 215, 105, 95), (500, 160, 125, 120), (665, 215, 105, 95), (500, 255, 190, 60)], WHITE, W)
    p.line([(318, 300), (682, 300)], 16, INK)                  # смужка капелюха
    # очі
    for ex, px in ((405, 424), (595, 614)):
        p.blob([(ex, 525, 66, 82)], WHITE, 11)
        p.blob([(px, 545, 33, 37)], INK, 1)
        p.blob([(px + 12, 530, 11, 11)], WHITE, 0)
    # занепокоєні брови
    p.line([(325, 428), (445, 392)], 22, INK)
    p.line([(555, 392), (675, 428)], 22, INK)
    # щоки, ніс
    p.blob([(335, 615, 34, 24), (665, 615, 34, 24)], BLUSH, 0)
    p.blob([(500, 595, 38, 30)], (244, 170, 140), 9)
    # вуса
    left = [(500, 640), (432, 612), (372, 636), (352, 680), (392, 700), (445, 678), (500, 668)]
    right = [(1000 - x, y) for x, y in left]
    p.poly(left, BROWN, INK, 9)
    p.poly(right, BROWN, INK, 9)
    # рот і крапля поту
    p.blob([(500, 730, 26, 21)], (120, 30, 30), 8)
    tear = [(768, 380), (798, 440), (790, 470), (768, 482), (746, 470), (738, 440)]
    p.poly(tear, BLUE, INK, 8)
    # виделка: зубці + рибка
    p.line([(815, 340), (885, 340)], 24, INK)
    for tx in (815, 850, 885):
        p.line([(tx, 340), (tx, 268)], 18, INK)
    for tx in (815, 850, 885):
        p.line([(tx, 338), (tx, 272)], 8, STEEL)
    p.line([(815, 340), (885, 340)], 10, STEEL)
    p.blob([(838, 225, 70, 38)], FISH, 9)                      # тіло рибки
    p.poly([(895, 225), (968, 180), (968, 270)], FISH_D, INK, 8)  # хвіст
    p.blob([(800, 215, 14, 14)], WHITE, 6)
    p.blob([(796, 217, 6, 6)], INK, 0)
    p.line([(815, 245), (845, 255)], 6, INK)


def font(px):
    return ImageFont.truetype(FONT, px)


def chef_img() -> Image.Image:
    """Кухар із Flow без білих полів (обрізано по вмісту)."""
    import numpy as np
    im = Image.open(WORK / "flow" / "chef_flow.jpg").convert("RGB")
    a = np.asarray(im).astype(int)
    mask = (a.min(axis=2) < 235)
    ys, xs = np.where(mask)
    return im.crop((xs.min() - 6, ys.min() - 6, xs.max() + 7, ys.max() + 7))


def avatar(size=800) -> Image.Image:
    ch = chef_img()
    canvas = Image.new("RGB", (size, size), WHITE)
    k = size * 0.80 / max(ch.size)
    ch = ch.resize((int(ch.width * k), int(ch.height * k)), Image.LANCZOS)
    canvas.paste(ch, ((size - ch.width) // 2, int(size * 0.10)))
    return canvas


def draw_line_text(dr, x, y, text, f, fill_main=INK, fill_q=RED):
    """Малює рядок; завершальне «?» червоним."""
    if text.endswith("?"):
        main = text[:-1]
        dr.text((x, y), main, font=f, fill=fill_main)
        dr.text((x + dr.textlength(main, font=f), y), "?", font=f, fill=fill_q)
    else:
        dr.text((x, y), text, font=f, fill=fill_main)


def banner() -> Image.Image:
    W, H = 2560, 1440
    im = Image.new("RGB", (W, H), WHITE)
    ch = chef_img()
    k = 410 / ch.height
    ch = ch.resize((int(ch.width * k), 410), Image.LANCZOS)
    im.paste(ch, (560, 515))                         # безпечна зона x 507-2053, y 508-931
    dr = ImageDraw.Draw(im)
    f = font(168)
    for i, text in enumerate(NAME_LINES):
        w = dr.textlength(text, font=f)
        draw_line_text(dr, 1500 - w / 2, 520 + i * 195, text, f)
    return im


def horizontal(height=300) -> Image.Image:
    av = avatar(height).convert("RGBA")
    mask = Image.new("L", (height, height), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, height - 1, height - 1), fill=255)
    av.putalpha(mask)
    f = font(int(height * 0.34))
    tmp = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    w = int(height * 1.1 + max(tmp.textlength(t, font=f) for t in NAME_LINES) + 40)
    im = Image.new("RGBA", (w, height), (0, 0, 0, 0))
    im.alpha_composite(av, (0, 0))
    dr = ImageDraw.Draw(im)
    x = int(height * 1.1)
    draw_line_text(dr, x, int(height * 0.12), NAME_LINES[0], f, INK + (255,), RED + (255,))
    draw_line_text(dr, x, int(height * 0.50), NAME_LINES[1], f, INK + (255,), RED + (255,))
    return im


if __name__ == "__main__":
    for d in (LOGO, BANNER, WORK):
        d.mkdir(exist_ok=True)
    av = avatar(800)
    av.save(LOGO / "avatar_800.png")
    av.resize((256, 256), Image.LANCZOS).save(LOGO / "favicon_256.png")
    horizontal(300).save(LOGO / "logo_horizontal.png")
    b = banner()
    b.save(BANNER / "banner_2560x1440.png")
    small = av.resize((98, 98), Image.LANCZOS)
    mask = Image.new("L", (98, 98), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, 97, 97), fill=255)
    prev = Image.new("RGB", (98, 98), (220, 220, 220))
    prev.paste(small, (0, 0), mask)
    prev.resize((294, 294), Image.NEAREST).save(WORK / "preview_avatar_98px.png")
    b.crop((507, 508, 2053, 931)).save(WORK / "preview_banner_mobile.png")
    print("готово")
