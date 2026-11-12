"""Прев'ю explainer-а за конкурентами: великий експресивний персонаж + один сильний предмет на тематичному тлі,
2-3 слова товстим текстом (останнє — жовте). Збирається з наших ресурсів (безкоштовно), 3 різні концепції для A/B."""
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from ..providers.llm.anthropic_provider import _extract_json
from . import assets
from .character import SAGE, CharacterSpec, EXPRS, POSES, render as render_char
from .render import FONT_IMPACT, OUTLINE, YELLOW
from .storyboard import actor_kwargs

W, H = 1280, 720
NL = chr(10)

_SYSTEM = (
    "You design YouTube thumbnails for an animated explainer channel (flat cartoon, one expressive character + one strong object, "
    "2-3 word text). Competitors that reach recommendations use: a BIG emotional face (shock, fear, smug), one clearly readable "
    "object, high contrast, a curiosity-gap text of 2-3 words in CAPS that does NOT repeat the title. Choose 3 DIFFERENT concepts from "
    "the catalog. Output ONLY a JSON array of 3 objects: "
    '{"text": "2-3 CAPS words", "bg": key, "who": actor key, "expr": expression, "pose": pose, "prop": prop key or null, '
    '"side": "left"|"right" (where the character stands; prop goes opposite), "glow": "gold"|"cyan"|"red"}.'
)


def _outline(img: Image.Image, color=(255, 255, 255), px=7) -> Image.Image:
    a = img.getchannel("A")
    big = a.filter(ImageFilter.MaxFilter(px * 2 + 1))
    base = Image.new("RGBA", img.size, (*color, 0))
    base.putalpha(big)
    base.alpha_composite(img)
    return base


def _cover(im: Image.Image) -> Image.Image:
    s = max(W / im.width, H / im.height)
    im = im.resize((int(im.width * s) + 1, int(im.height * s) + 1), Image.LANCZOS)
    x, y = (im.width - W) // 2, (im.height - H) // 2
    return im.crop((x, y, x + W, y + H))


def _brand_grade(img: Image.Image) -> Image.Image:
    """Єдиний «фірмовий» грейд усіх прев'ю каналу: насичені теплі кольори й контраст (переможці ніші — золоті/насичені,
    а не приглушені), легке золоте світіння в центрі. Один вигляд на всі відео = впізнаваність у стрічці."""
    from PIL import ImageEnhance
    rgb = img.convert("RGB")
    rgb = ImageEnhance.Color(rgb).enhance(1.30)
    rgb = ImageEnhance.Contrast(rgb).enhance(1.10)
    a = np.asarray(rgb).astype(np.float32)
    a[..., 0] *= 1.04
    a[..., 2] *= 0.94
    yy, xx = np.mgrid[0:H, 0:W]
    glow = np.exp(-(((xx - W * 0.5) / (W * 0.55)) ** 2 + ((yy - H * 0.45) / (H * 0.6)) ** 2))[..., None]
    a += glow * np.array([38, 24, 4], np.float32)
    return Image.fromarray(np.clip(a, 0, 255).astype("uint8")).convert("RGBA")


def compose(spec: dict, sb: dict, out: Path) -> None:
    from PIL import ImageFont
    bgp = Path(spec["bg_file"]) if spec.get("bg_file") else assets.ASSET_ROOT / "bg" / f"{assets._slug(spec['bg'])}.png"
    canvas = _cover(Image.open(bgp).convert("RGB")).convert("RGBA")
    # контраст і темніші краї
    arr = np.asarray(canvas).astype(np.float32)
    yy, xx = np.mgrid[0:H, 0:W]
    d = np.sqrt(((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2)
    arr[..., :3] = np.clip((arr[..., :3] - 128) * 1.12 + 128, 0, 255) * (1 - 0.35 * np.clip(d - 0.5, 0, 1))[..., None]
    canvas = Image.fromarray(arr.astype("uint8")).convert("RGBA")
    canvas = _brand_grade(canvas)

    glow = {"gold": (255, 200, 60), "cyan": (70, 220, 255), "red": (255, 80, 60)}.get(spec.get("glow"), (255, 200, 60))
    left = spec.get("side", "left") == "left"
    # предмет
    prop_key = spec.get("prop")
    prop_cx = W * (0.74 if left else 0.26)
    if prop_key and prop_key in sb["props"]:
        pim = assets.load(assets.ASSET_ROOT / "prop" / f"{assets._slug(prop_key)}.png")
        ph = int(H * 0.5)
        pim = pim.resize((max(int(pim.width * ph / pim.height), 2), ph), Image.LANCZOS)
        halo = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        hd = ImageDraw.Draw(halo)
        hd.ellipse((prop_cx - ph * .62, H * .70 - ph * .55, prop_cx + ph * .62, H * .70 + ph * .55), fill=(*glow, 150))
        canvas.alpha_composite(halo.filter(ImageFilter.GaussianBlur(60)))
        pim = _outline(pim, (255, 255, 255), 6)
        canvas.alpha_composite(pim, (int(prop_cx - pim.width / 2), int(H * 0.72 - pim.height / 2)))
    # персонаж
    raw = sb["actors"].get(spec["who"], {})
    cs = CharacterSpec(**actor_kwargs(raw)) if raw else SAGE
    sprite, (ax, ay) = render_char(cs, spec["pose"], spec["expr"], 3 if spec["expr"] in ("surprised", "scared") else 2, 0.0,
                                   1 if left else -1, int(H * spec.get("char_scale", 0.96)), False)
    sprite = _outline(sprite, (255, 255, 255), 7)
    gx = W * spec.get("char_x", 0.27 if left else 0.73)
    canvas.alpha_composite(sprite, (int(gx - ax), int(H + 8 - ay)))
    # текст
    words = spec["text"].upper().split()
    lines = [" ".join(words[:-1]), words[-1]] if len(words) > 1 else [words[0]]
    d = ImageDraw.Draw(canvas)
    top_layout = spec.get("layout") == "top"
    if top_layout:   # один рядок по центру зверху: нижня частина кадру лишається для головного візуалу
        lines = [" ".join(words)]
    size = 175
    while size > 80:
        f = ImageFont.truetype(FONT_IMPACT, size)
        if max(d.textlength(l, font=f) for l in lines) < (W * 0.92 if top_layout else W * 0.5):
            break
        size -= 8
    tx = W * 0.5 if top_layout else W * (0.73 if left else 0.27)
    y = 18 if top_layout else 40
    for i, line in enumerate(lines):
        last = i == len(lines) - 1
        if top_layout and len(line.split()) > 1:
            head, tail = line.rsplit(" ", 1)
            wh, wt = d.textlength(head + " ", font=f), d.textlength(tail, font=f)
            x0 = tx - (wh + wt) / 2
            sw = max(8, size // 12)
            d.text((x0, y), head + " ", font=f, fill=(255, 255, 255), stroke_width=sw, stroke_fill=OUTLINE, anchor="la")
            d.text((x0 + wh, y), tail, font=f, fill=YELLOW, stroke_width=sw, stroke_fill=OUTLINE, anchor="la")
        else:
            d.text((tx, y), line, font=f, fill=YELLOW if last else (255, 255, 255), stroke_width=max(8, size // 12), stroke_fill=OUTLINE, anchor="ma")
        y += int(size * 1.02)
    canvas.convert("RGB").save(out)


def make_thumbnails(llm, wd: Path, sb: dict, meta: dict, dest: Path, log=print) -> list[Path]:
    catalog = (f"BACKGROUNDS: {', '.join(sb['backgrounds'])}{NL}PROPS: {', '.join(sb['props'])}{NL}ACTORS: {', '.join(sb['actors'])}{NL}"
               f"POSES: {', '.join(POSES)}{NL}EXPRESSIONS: {', '.join(EXPRS)}")
    titles = " | ".join(meta.get("title_options", []))
    concepts = json.dumps(meta.get("thumbnail_concepts", []), ensure_ascii=False)
    raw = llm._complete(_SYSTEM, f"TITLES: {titles}{NL}CONCEPT HINTS: {concepts}{NL}{NL}{catalog}", 1500, effort="low")
    specs = _extract_json(raw)
    out = []
    for i, sp in enumerate(specs[:3], 1):
        for k, default in (("bg", next(iter(sb["backgrounds"]))), ("who", "sage"), ("expr", "surprised"), ("pose", "talk_a")):
            if k == "bg" and sp.get(k) not in sb["backgrounds"]:
                sp[k] = default
            elif k == "who" and sp.get(k) not in sb["actors"]:
                sp[k] = default
            elif k == "expr" and sp.get(k) not in EXPRS:
                sp[k] = default
            elif k == "pose" and sp.get(k) not in POSES:
                sp[k] = default
        if i == 2 and sp["who"] != "sage":   # талісман каналу хоча б в одному варіанті
            sp["who"], sp["pose"] = "sage", "talk_a"
        p = dest / f"thumbnail_{i}.png"
        compose(sp, sb, p)
        out.append(p)
        log(f"прев'ю {i}: {sp['text']} / {sp['bg']} / {sp['who']} / {sp.get('prop')}")
    return out


def make_from_packages(packages: list[dict], sb: dict, dest: Path, log=print) -> list[Path]:
    out = []
    for i, pkg in enumerate(packages[:3], 1):
        v = dict(pkg["visual"])
        v["text"] = pkg["thumb_text"]
        v.setdefault("side", "left")
        v["expr"] = v.get("expr") if v.get("expr") in EXPRS else "surprised"
        v["pose"] = v.get("pose") if v.get("pose") in POSES else "talk_a"
        if v.get("prop") and v["prop"] not in sb["props"]:
            v["prop"] = None
        p = dest / f"thumbnail_{i}.png"
        compose(v, sb, p)
        out.append(p)
        log(f"прев'ю {i}: {pkg['thumb_text']}  |  {pkg['title']}")
    return out
