"""Набір стилів оформлення Shorts: щоб кожне відео мало інше оформлення (HUD, прогрес, лайк/підписка, субтитри, шрифт, ґрейд, наклейки, переходи).
pick(slug) бере комбінацію, якої ще не було в останніх відео (реєстр storage/style_registry.json), і зберігає її."""
import hashlib
import json
import random
from pathlib import Path

REG = Path(__file__).resolve().parents[2] / "storage" / "style_registry.json"
FONT_DIR = "C:/Windows/Fonts/"
FONTS = {"impact": "impact.ttf", "ariblk": "ariblk.ttf", "comicbd": "comicbd.ttf", "bahnschrift": "bahnschrift.ttf", "framd": "framd.ttf", "consolab": "consolab.ttf", "courbd": "courbd.ttf", "georgiab": "georgiab.ttf", "timesbd": "timesbd.ttf"}
SUBS = {   # (заливка активного слова, текст активного, текст решти)
    "yellow": ((255, 214, 54), (22, 18, 20), (255, 255, 255)),
    "white": ((255, 255, 255), (22, 18, 20), (255, 255, 255)),
    "pink": ((255, 92, 160), (255, 255, 255), (255, 255, 255)),
    "cyan": ((96, 220, 255), (22, 18, 20), (255, 255, 255)),
    "lime": ((166, 235, 70), (22, 18, 20), (255, 255, 255)),
    "doc": ((240, 190, 70), (18, 18, 20), (240, 240, 240)),
    "doc_red": ((222, 92, 74), (18, 18, 20), (236, 236, 230)),
    "doc_ice": ((150, 200, 232), (18, 18, 20), (236, 238, 240)),
    "doc_film": ((255, 238, 176), (18, 18, 20), (250, 248, 240)),    # як у кіно: біла серифна, активне слово кремове
    "doc_poster": ((255, 255, 255), (18, 18, 20), (150, 150, 150)),      # плакатний: жирний Arial Black, активне слово яскраве
    "banner": ((246, 214, 130), (60, 12, 18), (246, 242, 230)),       # геральдична стрічка: золоте активне слово на темній смузі
    "typed": ((255, 224, 60), (20, 20, 20), (244, 240, 226)),      # друкарський: темна смуга, жовтий маркер на активному слові     # документальний: без плашки, активне слово бурштинове
}
STICKER = {"white": (255, 255, 255), "yellow": (255, 230, 90), "mint": (170, 240, 210), "none": False}
# «Серйозний» пресет для військових/історичних тем: без наклейкової обводки, емодзі й вибухів, тактичний HUD, документальні субтитри, плівка
SERIOUS = {"look": "serious", "cta": "lower", "hud": "tactical", "title": "plate", "progress": "thin", "subs": "doc", "font": "bahnschrift",
           "grade": "film", "sticker": "none"}
DOSSIER = {"look": "serious", "cta": "postit", "hud": "none", "title": "tab", "progress": "dash", "subs": "typed", "font": "courbd",
           "grade": "cool", "sticker": "none"}   # «Секретне досьє»: паперові сцени, друкарські субтитри, липкий папірець
POSTER = {"look": "serious", "cta": "capsule", "hud": "none", "title": "line", "progress": "player", "subs": "doc_poster", "font": "ariblk",
          "grade": "duo_red", "sticker": "none", "actors": "silhouette"}   # «Постер»: дуотон, фото з рухом камери, кінетична типографіка, діаграми, силуети
NAVAL = {"look": "serious", "cta": "radiogram", "hud": "none", "title": "dogtag", "progress": "wake", "subs": "doc_film", "font": "timesbd",
         "grade": "oldfilm", "sticker": "none"}   # «Флот 1943»: жетон, кільватер, радіограма, чорно-біла плівка, великий хук-текст
HERALDIC = {"look": "serious", "cta": "scroll", "hud": "none", "title": "ribbon", "progress": "sword", "subs": "banner", "font": "georgiab",
            "grade": "warm", "sticker": "none"}   # «Геральдика»: стрічка, сувій із печаткою, меч у прогресі, золоті субтитри
BLUEPRINT = {"look": "serious", "cta": "workorder", "hud": "none", "title": "stencil", "progress": "rivets", "subs": "doc_ice", "font": "impact",
             "grade": "duo_blue", "sticker": "none"}   # «Креслення»: синій дуотон, табличка-стенсиль, заклепки, наряд-замовлення
SERIOUS_C = dict(SERIOUS, font="framd", subs="doc_ice", grade="sepia", cta="lower_r")   # історичний: сепія, правий CTA, блакитний акцент
SERIOUS_B = dict(SERIOUS, font="consolab", subs="doc_red")   # другий серйозний варіант: моноширинний шрифт, червоний акцент
AXES = {
    "cta": ["pills", "bell", "pow", "ticker", "cursor"],
    "hud": ["meters", "hearts", "dots", "thermo", "rings"],
    "title": ["pill", "tape", "plain"],
    "progress": ["line", "fuse", "segments"],
    "subs": [k for k in SUBS if not k.startswith("doc") and k not in ("typed", "banner")],
    "font": list(FONTS),
    "grade": ["", "night", "warm", "cool", "vhs"],
    "sticker": [k for k in STICKER if k != "none"],
}
# відео до введення набору стилів (усі мали однакове оформлення)
BASE = {"cta": "pills", "hud": "meters", "title": "pill", "progress": "line", "subs": "yellow", "font": "impact", "grade": "", "sticker": "white"}


def _load() -> dict:
    try:
        return json.loads(REG.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def pick(slug: str, fixed: dict | None = None, avoid_last: int = 3, preset: dict | None = None) -> dict:
    """Нова комбінація: по кожній осі уникає значень з останніх `avoid_last` відео (якщо є з чого обирати)."""
    reg = _load()
    if slug in reg:
        return reg[slug]
    if preset:
        reg[slug] = dict(preset)
        REG.parent.mkdir(parents=True, exist_ok=True)
        REG.write_text(json.dumps(reg, ensure_ascii=False, indent=1), encoding="utf-8")
        return reg[slug]
    recent = list(reg.values())[-avoid_last:] or [BASE]
    rnd = random.Random(int(hashlib.md5(slug.encode()).hexdigest()[:8], 16))
    out = {}
    for axis, opts in AXES.items():
        if fixed and axis in fixed:
            out[axis] = fixed[axis]
            continue
        used = {r.get(axis, BASE[axis]) for r in recent}
        free = [o for o in opts if o not in used] or opts
        out[axis] = rnd.choice(free)
    reg[slug] = out
    REG.parent.mkdir(parents=True, exist_ok=True)
    REG.write_text(json.dumps(reg, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


def font_path(name: str) -> str:
    return FONT_DIR + FONTS.get(name, FONTS["impact"])
