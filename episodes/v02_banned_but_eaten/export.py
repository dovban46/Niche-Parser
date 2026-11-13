"""v02 пакет Flow: 10 концептів прев'ю (по 2 генерації, ЙДУТЬ ПЕРШИМИ) у стилі «Why Not Eat»: спліт-екран «дозволене | заборонене», їжа з обличчями, кухар по центру, зверху вільна смуга під великий жовтий заголовок.
Запуск з кореня: PYTHONIOENCODING=utf-8 python episodes/v02_banned_but_eaten/export.py"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from app.jp import core, flow, plan  # noqa: E402

SLUG = "v02_banned_but_eaten"
COMP = ("YouTube thumbnail in a popular educational cartoon style, 16:9, vivid saturated colors, rich detail, thick black outlines, soft cel shading; "
        "SPLIT composition: left half bright and sunny with the smug allowed food characters, right half dark and gloomy with the banned scary food characters, "
        "the same worried chef in the middle with sweat drops and wide eyes, food characters have big eyes and faces, plenty of rich background details; "
        "keep the top 22% of the picture calm (sky or wall) for a big title added later")

# (ключ, текст прев'ю пізніше, cast, сцена)
THUMBS = [
    ("T01", "ЖИВИЙ СИР?!", ["chef"],
     "left: a smug pizza and a smug burger on a white plate in a sunny kitchen; right: a gloomy cellar with a big plate of casu marzu cheese covered with tiny white jumping larvae, the cheese has an evil face; chef in the middle, horrified"),
    ("T02", "ЗАБОРОНЕНО?", ["chef"],
     "left: a green apple and bread with proud smug faces on a sunny table; right: a dark table with a scary pufferfish on a plate with a small skull sign and a cheese with larvae, a big red forbidden stamp above the right half; chef in the middle sweating"),
    ("T03", "ЇСТИ ЦЕ?!", ["chef", "jchef"],
     "chef in the middle holding a fork shaking, in front of him a huge scary pufferfish on a big white plate with a glowing green aura, a Japanese chef with a long knife on the right looking calm, dark teal background on the right, bright on the left"),
    ("T04", "НАВІЩО?!", ["chef", "french"],
     "left: a fancy dinner table in bright light; right: a dark candlelit table where a man with a white napkin over his head is eating a tiny roasted bird, the little bird on the plate has a sad face; chef in the middle covering his mouth in shock"),
    ("T05", "ЦЕ ЗАБОРОНЕНО?", ["chef", "scot"],
     "left: an American flag and an empty plate with a red forbidden sign; right: a happy Scottish man in a kilt holding a haggis sack character on a plate, green hills behind; chef in the middle scratching his head with a question mark"),
    ("T06", "СМЕРТЕЛЬНО?!", ["chef"],
     "left: a bright and smiling ackee fruit opened wide on a sunny plate with a green check; right: a dark closed green ackee fruit with a skull sign glowing sickly green; chef in the middle sweating and pointing at the right fruit"),
    ("T07", "СЕМЕРО ЗАБОРОН", ["chef"],
     "chef in the middle with an astonished face, behind him a long table with seven different banned dishes lined up each with a face: a cheese with larvae, a pufferfish, a little bird, a haggis, a green fruit, a green bottle, a bulging tin can; dark moody right and bright left"),
    ("T08", "ЧОМУ ЇДЯТЬ?", ["chef"],
     "left: a huge red forbidden sign over a plate of food with a sad face; right: a crowd of happy people eating the same food around a table; chef in the middle shrugging with sweat drops, split composition dark left bright right"),
    ("T09", "ВОНО ЖИВЕ!", ["chef"],
     "extreme close-up of a cheese character full of tiny white larvae jumping out of it like popcorn, chef on the right terrified shielding his plate with his hand, dark cellar background, left side bright"),
    ("T10", "СМАЧНО ЧИ СТРАШНО?", ["chef"],
     "left: a bright plate with a delicious steaming dish with a smug happy face; right: the very same dish dark and scary with glowing red eyes and a skull sign; chef in the middle holding a fork with a worried face"),
]


def thumb_items(style_head: str) -> list[dict]:
    cast = plan.load_cast(SLUG)
    items, n = [], 900
    for key, _, who, scene in THUMBS:
        looks = (" Character looks (draw exactly): " + "; ".join(f"{k} = {cast[k]}" for k in who) + ".") if who else ""
        prompt = f"{style_head} {COMP}.{looks} Scene: {scene}."
        for k in range(2):
            items.append({"id": n, "file": f"thumb_{key}_{k}.jpg", "prompt": prompt, "edits": []})
            n += 1
    return items


if __name__ == "__main__":
    base = flow.export(SLUG)
    f = base / "agent_A" / "prompts.json"
    pj = core.load_json(f)
    style_head = (core.job_dir(SLUG) / "style.txt").read_text(encoding="utf-8").strip().format(era="")
    style_head = style_head.replace("ONE clear main subject drawn large; ", "").replace("wide-angle 16:9 scene with ", "")
    pj["items"] = thumb_items(style_head) + pj["items"]
    core.save_json(f, pj)
    print(base, len(pj["items"]), "елементів (20 прев'ю + кадри)")
