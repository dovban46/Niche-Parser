"""Бібліотека фонів і предметів. За замовчуванням fal.ai FLUX (≈$0.003/кадр): генеруємо 2-3 кандидати, дешевий
візуальний суддя (Haiku) обирає найкращий за стилем/змістом; Nano Banana лишається запасним. Один плоский стиль, що підходить
до процедурного аватара. Предмети — на білому тлі з вирізанням; для фонів додатково аналізується «прохідна» зона підлоги."""

import base64
import hashlib
import io
import json
import os
import re
import threading
from pathlib import Path

import numpy as np
import requests
from PIL import Image, ImageDraw, ImageFilter

from ..config import STORAGE_ROOT

ASSET_ROOT = STORAGE_ROOT / "explainer_assets"
PROVIDER = (os.environ.get("EXPLAINER_ASSET_PROVIDER") or "fal").lower()      # fal | google
CANDIDATES = int(os.environ.get("EXPLAINER_ASSET_CANDIDATES") or 3)

# FLUX читає ~256 токенів: короткий стиль, що повторюється ключовими словами
ART = (os.environ.get("EXPLAINER_ART") or "cartoon").lower()      # cartoon | serious | photo
STYLE_FLUX = ("stylized 2D graphic-novel illustration, thin dark ink outlines, muted desaturated military palette, soft painterly shading, subtle texture, cinematic lighting"
              if ART == "serious" else "flat 2D vector cartoon, thick dark outlines, flat colors, simple clean shapes, explainer video style")
BG_SUFFIX_FLUX = ", wide empty scene background, no people, no characters, no text, no letters, " + STYLE_FLUX
BGV_SUFFIX_FLUX = (", tall vertical 9:16 documentary photograph, black and white, 35mm film grain, high contrast, realistic, sharp focus, no text, no letters, no close-up faces"
                    if ART == "photo" else ", tall vertical 9:16 empty scene background, clear solid ground in the lower middle, no people, no characters, no text, no letters, " + STYLE_FLUX)
_PROP_STYLE = ("flat 2D vector illustration, thin dark outlines, muted desaturated colors, simple clean shapes" if ART == "serious" else STYLE_FLUX)   # чисте ключування потребує пласкої графіки
PROP_SUFFIX_FLUX = ", single isolated object, centered, full object visible, on a solid pure green screen chroma key background (#00FF00), perfectly flat uniform green, no shadow, no text, " + _PROP_STYLE

STYLE = (
    "flat 2D vector cartoon illustration in the style of a modern animated explainer video, thick dark brown-black outlines, "
    "simple clean shapes, flat colors with minimal cel shading, warm saturated palette, no text, no letters, no hieroglyph writing, "
    "no people, no characters"
)
BG_SUFFIX = ", wide 16:9 background scene, large calm empty area in the lower middle for a character to stand, detailed but uncluttered, " + STYLE
PROP_SUFFIX = (
    ", a single object centered, full object visible with margin, on a plain pure white background, thick dark outline, flat colors, "
    "no shadow, no ground, no text, sticker style"
)


def _slug(key: str) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", key.lower()).strip("_")


# ---------- генерація ----------
def _fal_images(prompt: str, w: int, h: int, n: int) -> list[Image.Image]:
    key = os.environ.get("FAL_API_KEY")
    if not key:
        raise RuntimeError("FAL_API_KEY не знайдено")
    r = requests.post("https://fal.run/fal-ai/flux/schnell",
                      headers={"Authorization": f"Key {key}", "Content-Type": "application/json"},
                      json={"prompt": prompt, "image_size": {"width": w, "height": h}, "num_images": n, "num_inference_steps": 4,
                            "enable_safety_checker": False},
                      timeout=180)
    if r.status_code != 200:
        raise RuntimeError(f"fal {r.status_code}: {r.text[:200]}")
    out = []
    for im in r.json().get("images", []):
        data = requests.get(im["url"], timeout=60).content
        out.append(Image.open(io.BytesIO(data)).convert("RGB"))
    if not out:
        raise RuntimeError("fal не повернув зображень")
    return out


def _google_image(prompt: str, out: Path) -> Image.Image:
    from ..providers.images.google_image import GoogleImageProvider
    GoogleImageProvider().generate_image(prompt, out)
    return Image.open(out).convert("RGB")


_VISION_MODEL = "claude-haiku-4-5-20251001"


def _vision_json(images: list[Image.Image], prompt: str, max_tokens: int = 400):
    from ..providers.llm.anthropic_provider import AnthropicLLMProvider, _extract_json
    llm = AnthropicLLMProvider()
    content = []
    for i, im in enumerate(images):
        im = im.copy()
        im.thumbnail((768, 768))
        buf = io.BytesIO()
        im.convert("RGB").save(buf, "JPEG", quality=85)
        content.append({"type": "text", "text": f"Image {i}:"})
        content.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": base64.b64encode(buf.getvalue()).decode()}})
    content.append({"type": "text", "text": prompt})
    resp = llm._client.messages.create(model=_VISION_MODEL, max_tokens=max_tokens, messages=[{"role": "user", "content": content}])
    from ..providers.llm.usage import usage_tracker
    usage_tracker.record(_VISION_MODEL, resp.usage.input_tokens, resp.usage.output_tokens)
    text = "".join(b.text for b in resp.content if b.type == "text")
    return _extract_json(text)


def _pick(cands: list[Image.Image], desc: str, kind: str) -> tuple[int, bool]:
    """Суддя обирає найкращого кандидата; ok=False, якщо жоден не годиться."""
    if kind in ("bg", "bgv") and ART == "photo":
        crit = ("a realistic black-and-white documentary photograph of: " + desc + ". Must look like a real photo (not a cartoon), no text or letters, no melted or distorted shapes, no close-up faces.")
    elif kind == "bg":
        crit = ("an EMPTY background scene of: " + desc + ". Must be " + ("a stylized 2D graphic-novel illustration with thin outlines and muted colors" if ART == "serious" else "a flat 2D vector cartoon illustration with thick outlines and flat colors") + "; "
                "NO people or characters, NO text or letters, no photo-realism, no weird melted shapes.")
    else:
        crit = ("ONE single isolated object/figure: " + desc + ", on a flat solid green screen background, " + ("stylized 2D illustration with thin outlines and muted colors" if ART == "serious" else "flat 2D vector cartoon with thick outlines") + "; "
                "complete (not cropped), no text or letters, no background scenery, background is ONE uniform green colour (also visible through any gaps/holes of the object).")
    prompt = (f"Choose the image that best matches {crit} Answer ONLY JSON: " + '{"best": <index>, "ok": true|false, "why": "<8 words>"}'
              + " ('ok' false if even the best one is unusable).")
    try:
        data = _vision_json(cands, prompt, 200)
        return int(data.get("best", 0)) % len(cands), bool(data.get("ok", True))
    except Exception:  # noqa: BLE001
        return 0, True


def _green_border(im: Image.Image) -> bool:
    """Тло предмета має бути суцільним зеленим: зелений канал помітно домінує на краях, краї однорідні."""
    a = np.asarray(im.convert("RGB").resize((128, 128))).astype(np.float32)
    border = np.concatenate([a[0], a[-1], a[:, 0], a[:, -1]])
    m = border.mean(axis=0)
    return bool(m[1] > m[0] + 50 and m[1] > m[2] + 50 and border.std(axis=0).max() < 45)


def _semi_share(im: Image.Image) -> float:
    """Частка напівпрозорих пікселів після ключування (0 = чисто): для кандидата, на якому ключ спрацює погано, вона висока."""
    a = np.asarray(im.convert("RGB").resize((256, 256))).astype(np.float32)
    border = np.concatenate([a[0], a[-1], a[:, 0], a[:, -1]])
    key = np.median(border, axis=0)
    dist = np.sqrt(((a - key) ** 2).sum(axis=2))
    alpha = np.clip((dist - 40.0) / 50.0, 0.0, 1.0)
    fg = alpha > 0.05
    return float(((alpha > 0.05) & (alpha < 0.9)).sum() / max(fg.sum(), 1))


def _has_black_bars(im: Image.Image) -> bool:
    """FLUX іноді дає чорні поля зверху/знизу/з боків — такі фони непридатні."""
    a = np.asarray(im.convert("L").resize((128, 72)))
    return bool(a[:3].mean() < 12 or a[-3:].mean() < 12 or a[:, :3].mean() < 12 or a[:, -3:].mean() < 12)


def _generate(kind: str, key: str, prompt: str, log) -> Image.Image:
    if PROVIDER == "google":
        raw = ASSET_ROOT / kind / f"{_slug(key)}.raw.png"
        raw.parent.mkdir(parents=True, exist_ok=True)
        return _google_image(prompt + (BG_SUFFIX if kind == "bg" else PROP_SUFFIX), raw)
    full = prompt + (BG_SUFFIX_FLUX if kind == "bg" else (BGV_SUFFIX_FLUX if kind == "bgv" else PROP_SUFFIX_FLUX))
    size = (1344, 768) if kind == "bg" else ((768, 1344) if kind == "bgv" else (768, 768))
    best = None
    for attempt in range(5 if kind == "prop" else 3):
        cands = _fal_images(full, size[0], size[1], min(4, CANDIDATES + (1 if kind == "prop" else 0)))
        if kind in ("bg", "bgv"):
            good = [c for c in cands if not _has_black_bars(c)]
            cands = good or cands
        else:
            good = [c for c in cands if _green_border(c) and _semi_share(c) < 0.22]
            if not good:
                log(f"  prop {key}: жоден кандидат без чистого зеленого тла, повтор")
                continue
            cands = good
        idx, ok = _pick(cands, prompt, kind)
        best = cands[idx]
        if ok:
            return best
        log(f"  {kind} {key}: кандидати погані, повтор")
    if best is None:
        raise RuntimeError(f"{kind} {key}: жодного придатного кандидата")
    if kind == "prop" and not (_green_border(best) and _semi_share(best) < 0.22):
        raise RuntimeError(f"предмет {key}: не вдалось отримати чисте тло для ключування")
    return best


INDEX_PATH = ASSET_ROOT / "index.json"


def _load_index() -> dict:
    if INDEX_PATH.exists():
        return json.load(open(INDEX_PATH, encoding="utf-8"))
    return {"bg": {}, "prop": {}}


_INDEX_LOCK = threading.Lock()


def register(kind: str, key: str, prompt: str, float_flag: bool = False) -> None:
    with _INDEX_LOCK:   # генерація йде в кількох потоках — запис індексу має бути послідовним і атомарним
        idx = _load_index()
        idx[kind][key] = {"p": prompt, "float": bool(float_flag)} if kind == "prop" else {"p": prompt}
        INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = INDEX_PATH.with_suffix(".tmp")
        json.dump(idx, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        tmp.replace(INDEX_PATH)


def library() -> dict:
    """Бібліотека, що вже є на диску: {"bg": {key: {"p": prompt}}, "prop": {key: {"p": prompt, "float": bool}}}. Лише ті, чий PNG існує
    (і для фонів — є аналіз «прохідної» зони). Повторне використання = $0 за генерацію й аналіз."""
    idx = _load_index()
    out = {"bg": {}, "prop": {}}
    for k, v in idx["bg"].items():
        if (ASSET_ROOT / "bg" / f"{_slug(k)}.png").exists():
            out["bg"][k] = v
    for k, v in idx["prop"].items():
        if (ASSET_ROOT / "prop" / f"{_slug(k)}.png").exists():
            out["prop"][k] = v
    return out


def rebuild_index(log=print) -> None:
    """Збирає індекс із design.json/design2.json усіх explainer-job'ів (разова міграція)."""
    idx = {"bg": {}, "prop": {}}
    for f in sorted((STORAGE_ROOT / "explainer_jobs").glob("*/design*.json")):
        d = json.load(open(f, encoding="utf-8"))
        for k, v in (d.get("backgrounds") or {}).items():
            idx["bg"][k] = {"p": v}
        for k, v in (d.get("props") or {}).items():
            idx["prop"][k] = {"p": v["p"], "float": bool(v.get("float"))} if isinstance(v, dict) else {"p": v, "float": False}
    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    json.dump(idx, open(INDEX_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    lib = library()
    log(f"індекс: фонів {len(lib['bg'])}, предметів {len(lib['prop'])}")


def ensure_bg(key: str, prompt: str, log=print) -> Path:
    path = ASSET_ROOT / "bg" / f"{_slug(key)}.png"
    if path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    log(f"фон {key} …")
    im = _generate("bg", key, prompt, log)
    im.save(path)
    register("bg", key, prompt)
    return path


def ensure_bgv(key: str, prompt: str, log=print) -> Path:
    """Вертикальний (9:16) фон для Shorts — окрема тека bgv/, щоб не змішувати з 16:9."""
    path = ASSET_ROOT / "bgv" / f"{_slug(key)}.png"
    if path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    log(f"вертикальний фон {key} …")
    im = _generate("bgv", key, prompt, log)
    im.save(path)
    return path


def ensure_prop(key: str, prompt: str, log=print) -> Path:
    path = ASSET_ROOT / "prop" / f"{_slug(key)}.png"
    if path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    log(f"предмет {key} …")
    im = _generate("prop", key, prompt, log)
    raw = path.with_suffix(".raw.png")
    im.save(raw)
    if PROVIDER == "google":
        cut_out_white(raw, path)
    else:
        chroma_key(raw, path)
        raw.unlink(missing_ok=True)
    register("prop", key, prompt)
    return path


KEY_COLOR = np.array([0.0, 255.0, 0.0], np.float32)


def chroma_key(src: Path, dst: Path, d0: float = 40.0, d1: float = 90.0) -> None:
    """Прозорість за кольором тла (мажента): прозорими стають І проміжки всередині предмета (між дошками, ручки, кільця), де видно те саме тло;
    білі/світлі деталі самого предмета лишаються. Колір ключа береться з медіани країв (FLUX не завжди дає ідеальну маженту);
    «анміксинг» знімає рожевий ореол на краях."""
    import cv2
    im = np.asarray(Image.open(src).convert("RGB")).astype(np.float32)
    h, w = im.shape[:2]
    border = np.concatenate([im[0], im[-1], im[:, 0], im[:, -1]])
    key = np.median(border, axis=0)
    if border.std(axis=0).max() > 40:   # краї не однорідні (об'єкт торкається краю) — беремо канонічний колір ключа
        key = KEY_COLOR
    dist = np.sqrt(((im - key) ** 2).sum(axis=2))
    alpha = np.clip((dist - d0) / (d1 - d0), 0.0, 1.0)
    # відкидаємо дрібні острівці «тла» посеред об'єкта лише якщо вони ВЕЛИКІ світлі/не-мажентові? — ні: тут усе, що за кольором ключа, прозоре
    a = alpha[..., None]
    fg = np.where(a > 0.05, (im - (1 - a) * key) / np.maximum(a, 0.05), im)
    fg = np.clip(fg, 0, 255)
    out = np.dstack([fg, alpha * 255]).astype(np.uint8)
    # чистимо шум: дрібні непрозорі крапки поза основним тілом
    mask = (out[..., 3] > 40).astype(np.uint8)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    if n > 1:
        big = stats[1:, cv2.CC_STAT_AREA].max()
        for i in range(1, n):
            if stats[i, cv2.CC_STAT_AREA] < 0.02 * big:
                out[lab == i, 3] = 0
    img = Image.fromarray(out, "RGBA")
    bbox = img.getchannel("A").point(lambda v: 255 if v > 20 else 0).getbbox()
    if bbox:
        img = img.crop(bbox)
    img.save(dst)


def cut_out_white(src: Path, dst: Path, thresh: int = 38) -> None:
    """Прибирає біле тло заливкою від країв (контур закриває об'єкт, тож білі деталі всередині лишаються)."""
    im = Image.open(src).convert("RGB")
    marker = (255, 0, 255)
    work = im.copy()
    w, h = work.size
    for seed in [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1), (w // 2, 0), (w // 2, h - 1), (0, h // 2), (w - 1, h // 2)]:
        px = work.getpixel(seed)
        if sum(px) > 3 * 225:
            ImageDraw.floodfill(work, seed, marker, thresh=thresh)
    a = np.asarray(work).astype(int)
    bg = (np.abs(a - np.array(marker)).sum(axis=2) < 6)
    alpha = Image.fromarray(np.where(bg, 0, 255).astype("uint8"))
    alpha = alpha.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(0.8))
    rgba = im.convert("RGBA")
    rgba.putalpha(alpha)
    bbox = alpha.point(lambda v: 255 if v > 20 else 0).getbbox()
    if bbox:
        rgba = rgba.crop(bbox)
    rgba.save(dst)
    strip_halo(dst)
    src.unlink(missing_ok=True)


def strip_halo(path: Path, white_min: int = 205, max_iter: int = 60) -> None:
    """Прибирає білий «стікерний» ореол навколо контуру: світлі пікселі, з'єднані з прозорою зоною, стають прозорими."""
    import cv2
    im = np.asarray(Image.open(path).convert("RGBA")).copy()
    alpha = im[..., 3]
    whiteish = im[..., :3].min(axis=2) >= white_min
    region = alpha < 20
    kernel = np.ones((3, 3), np.uint8)
    for _ in range(max_iter):
        grown = cv2.dilate(region.astype(np.uint8), kernel).astype(bool) & whiteish & ~region
        if not grown.any():
            break
        region |= grown
    im[..., 3] = np.where(region, 0, alpha)
    out = Image.fromarray(im)
    a = out.getchannel("A").filter(ImageFilter.GaussianBlur(0.7))
    out.putalpha(a)
    bbox = a.point(lambda v: 255 if v > 20 else 0).getbbox()
    if bbox:
        out = out.crop(bbox)
    out.save(path)


# ---------- «прохідна» зона фону (де можна стояти) ----------
FEET_Y = 0.79


def analyze_bg(key: str, desc: str = "", kind: str = "bg") -> dict:
    """Дешевий візуальний аналіз: на якій частині лінії стоп (79% висоти) твердий ґрунт. Кеш поруч із фоном (.json)."""
    path = ASSET_ROOT / kind / f"{_slug(key)}.png"
    meta = path.with_suffix(".json")
    if meta.exists():
        return json.load(open(meta, encoding="utf-8"))
    im = Image.open(path).convert("RGB")
    d = ImageDraw.Draw(im)
    feet = 0.70 if kind == "bgv" else FEET_Y
    y = int(im.height * feet)
    d.line([(0, y), (im.width, y)], fill=(255, 0, 255), width=3)
    prompt = (
        "This is an empty background for a 2D animated explainer. A full-body cartoon person (about 40-58% of image height) will stand with the "
        "FEET exactly on the magenta horizontal line. List the x-ranges (fractions of image width, 0..1) along that line where a person could "
        "stand and it would look natural: solid walkable ground such as floor, sand, grass, stone, a dock or deck. EXCLUDE water, lava, sky, "
        "clouds, cliff faces, walls, beds, tables, shelves, pits and anything the person would visibly stand IN or ON by mistake. "
        'Answer ONLY JSON: {"walkable": [[x0, x1], ...], "scene": "<5 words>", "ground": "floor|sand|grass|stone|water|void|mixed"} '
        "(empty list if nowhere is suitable)."
    )
    try:
        data = _vision_json([im], prompt, 300)
        walk = [[max(0.0, float(a)), min(1.0, float(b))] for a, b in data.get("walkable", []) if float(b) - float(a) > 0.08]
        res = {"walkable": walk, "scene": str(data.get("scene", "")), "ground": str(data.get("ground", ""))}
    except Exception as exc:  # noqa: BLE001
        res = {"walkable": [[0.1, 0.9]], "scene": "", "ground": "unknown", "error": str(exc)[:100]}
    json.dump(res, open(meta, "w", encoding="utf-8"), ensure_ascii=False)
    return res


def load(path: Path) -> Image.Image:
    return Image.open(path).convert("RGBA")
