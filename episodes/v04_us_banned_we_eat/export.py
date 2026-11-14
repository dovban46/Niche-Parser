"""v04 пакет Flow: 10 концептів прев'ю (по 2 генерації, ЙДУТЬ ПЕРШИМИ) у стилі олівцевого скетчу з акварелью, але з яскравішими акцентами та великим вільним верхом під заголовок.
Вибір прев'ю ТІЛЬКИ разом з користувачем після рендеру. Запуск з кореня: PYTHONIOENCODING=utf-8 python episodes/v04_us_banned_we_eat/export.py"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from app.jp import core, flow, plan  # noqa: E402

SLUG = "v04_us_banned_we_eat"
COMP = ("YouTube thumbnail, 16:9, hand-drawn pencil and ink sketch with bold watercolor wash on cream paper, stronger and more saturated colors than a plain sketch, "
        "confident ink outlines, clear readable big shapes that work at small size, one dramatic main subject with an exaggerated surprised or worried face, "
        "a few small background details; keep the top 22% of the picture calm and light (empty paper or soft sky) for a big title added later; no text, no letters, no numbers")

THUMBS = [
    ("T01", "ЗАБОРОНЕНО В США!", ["officer", "traveler"],
     "a stern American customs officer holding up a chocolate egg with a toy inside, confiscating it, while a young traveler with a suitcase looks shocked"),
    ("T02", "ЯЙЦЕ ВНЕ ЗАКОНУ", ["child"],
     "a big chocolate egg cut open with a small toy figure inside, a police-style red prohibition sign hanging behind it, a child with wide eyes"),
    ("T03", "СИРЕ МОЛОКО: ЗАБОРОНА?", ["granny"],
     "a village grandmother holding a clay jug of fresh milk next to a cow, an American inspector with a clipboard shaking his head at them"),
    ("T04", "СИР, ЯКОГО НЕМАЄ В США", ["inspector"],
     "a soft round camembert cheese with white rind on a wooden board, a food inspector with a thermometer pointing at it with a stop gesture"),
    ("T05", "ІКРА ПОЗА ЗАКОНОМ", ["fisherman"],
     "a sturgeon fish and an open jar of black caviar on ice, a fisherman holding the fish, a customs stamp falling onto the jar"),
    ("T06", "АБСЕНТ: 95 РОКІВ ЗАБОРОНИ", ["bartender"],
     "a bartender pouring a glowing green drink over a sugar cube on a slotted spoon, wormwood plant and a faint ghostly green mist behind"),
    ("T07", "ЛЕГЕНІ? У США НІ!", ["chef"],
     "a chef host holding a plate of meat pies and aspic and staring wide-eyed at a prohibition sign shaped like lungs on the wall"),
    ("T08", "САМОГОН = ЗЛОЧИН?", ["farmer"],
     "a rural farmer proudly standing beside a copper moonshine still with jars, a jail cell bars shadow and a handcuffs sketch in the corner"),
    ("T09", "7 ПРОДУКТІВ ПІД ЗАБОРОНОЮ", ["chef"],
     "a long table with seven foods: chocolate egg, milk jug, cheese, black caviar, green absinthe, plate of lungs, copper still, all behind police tape, a chef host looking guilty"),
    ("T10", "МИ ЇМО ЗАБОРОНЕНЕ?!", ["chef", "officer"],
     "a chef host hiding a basket of food behind his back, an American customs officer with a flashlight leaning in suspiciously, dark dramatic background"),
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
    style_head = style_head.replace("ONE clear main subject drawn large; ", "").replace("wide 16:9 scene with ", "").replace("no red circles or arrows", "")
    pj["items"] = thumb_items(style_head) + pj["items"]
    core.save_json(f, pj)
    print(base, len(pj["items"]), "елементів (20 прев'ю + кадри)")
