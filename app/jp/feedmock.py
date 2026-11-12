"""Перевірка упаковки «як у стрічці YouTube»: наше прев'ю + назва серед справжніх хітів ніші.

    python -m app.jp.feedmock <thumb.jpg> "<назва>" [<thumb2.jpg> "<назва2>" ...] [--out feed_check.jpg]

Малює темну сітку головної сторінки (3 колонки, 400 px) з нашим варіантом серед 8 хітів конкурентів
(storage/research/packaging_2026_11_09: picked.json + img/), а знизу кожен наш варіант у розмірі «Схожі відео»
(168x94) і «телефон» (360x203). Питання для оцінки: чи око зупиняється на нашому, чи читається текст у 168 px,
чи видно героя й емоцію, чи назва не губиться серед сусідів.
"""
import json
import random
import sys
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
RES = ROOT / "storage" / "research" / "packaging_2026_11_09"
BG, FG, SUB = (15, 15, 15), (241, 241, 241), (170, 170, 170)
FB = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 17)
FS = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 14)


def _k(n: int) -> str:
    return f"{n / 1e6:.1f}M" if n >= 1e6 else f"{n / 1e3:.0f}K"


def _card(canvas, d, img: Image.Image, title: str, meta: str, x: int, y: int, w: int) -> None:
    h = w * 9 // 16
    canvas.paste(img.convert("RGB").resize((w, h), Image.LANCZOS), (x, y))
    lines = textwrap.wrap(title, width=max(20, w // 10))[:2]
    for i, l in enumerate(lines):
        d.text((x, y + h + 8 + i * 21), l, font=FB, fill=FG)
    d.text((x, y + h + 8 + 2 * 21 + 4), meta, font=FS, fill=SUB)


def mock(ours: list[tuple[Path, str]], out: Path, seed: int = 7) -> Path:
    hits = [r for r in json.loads((RES / "picked.json").read_text(encoding="utf-8")) if (RES / "img" / f"{r['id']}.jpg").exists()
            and not any(k in r["title"].lower() for k in ("ambient", "music", "meditation", "soundscape", "episode", "full movie", "multi-sub"))]
    rnd = random.Random(seed)
    w, cols, gap = 400, 3, 16
    card_h = w * 9 // 16 + 80
    rows_per = 3
    blocks = []
    for th, title in ours:                       # одна сітка 3x3 на кожен наш варіант, наш у випадковій клітинці
        pool = rnd.sample(hits, 8)
        cells = [(Image.open(RES / "img" / f"{r['id']}.jpg"), r["title"], f"{r['ch']} · {_k(r['views'])} views") for r in pool]
        cells.insert(rnd.randrange(9), (Image.open(th), title, "Japan Through Time · NEW"))
        blocks.append(cells)
    small_h = 203 + 90
    H = len(blocks) * (rows_per * card_h + 40) + len(ours) * (small_h + 20) + 20
    W = cols * w + (cols + 1) * gap
    canvas = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(canvas)
    y = 20
    for cells in blocks:
        for i, (img, t, m) in enumerate(cells):
            _card(canvas, d, img, t, m, gap + (i % cols) * (w + gap), y + (i // cols) * card_h, w)
        y += rows_per * card_h + 40
    for th, title in ours:                        # телефон і «Схожі відео»
        im = Image.open(th)
        _card(canvas, d, im, title, "Japan Through Time", gap, y, 360)
        x2 = gap + 360 + 30
        canvas.paste(im.convert("RGB").resize((168, 94), Image.LANCZOS), (x2, y))
        for i, l in enumerate(textwrap.wrap(title, width=26)[:3]):
            d.text((x2 + 176, y + i * 19), l, font=FS, fill=FG)
        y += small_h + 20
    canvas.save(out, quality=90)
    return out


if __name__ == "__main__":
    args = sys.argv[1:]
    out = Path("feed_check.jpg")
    if "--out" in args:
        i = args.index("--out")
        out = Path(args[i + 1])
        del args[i:i + 2]
    pairs = [(Path(args[i]), args[i + 1]) for i in range(0, len(args), 2)]
    print(mock(pairs, out))
