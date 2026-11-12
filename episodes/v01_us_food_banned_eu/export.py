"""v01 пакет Flow для агента Antigravity: 10 концептів прев'ю (по 2 генерації, ЙДУТЬ ПЕРШИМИ) + усі кадри відео.
Текст на прев'ю накладається потім (thumbs.overlay); у промптах «no text» і вільне місце під текст.
Запуск з кореня:  python episodes/v01_us_food_banned_eu/export.py"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from app.jp import core, flow, plan  # noqa: E402

SLUG = "v01_us_food_banned_eu"
COMP = ("bold YouTube thumbnail composition: ONE hero or object HUGE in the foreground, very strong readable emotion, "
        "saturated single-color background (red, yellow or teal, NOT white), thick red hand-drawn marker circle or arrow around the key detail, "
        "very high contrast, simple uncluttered shapes, empty space {space} for big text later")

# (ключ, текст прев'ю пізніше, місце під текст, cast, сцена)
THUMBS = [
    ("T01", "ХЛОР?!", "in the top left", ["chef"],
     "chef HUGE on the right, horrified, hands on cheeks, staring at a whole raw chicken relaxing in a bubble bath in a bathtub with a big chlorine bottle beside it, "
     "red marker circle around the bottle, background saturated teal"),
    ("T02", "ЗАБОРОНЕНО", "in the top left", ["chef", "officer"],
     "a giant chocolate surprise egg HUGE in the center with a red forbidden slash sign over it, a stern customs officer stamping a crate behind it, "
     "chef in the corner biting his fingers, background saturated yellow"),
    ("T03", "ТИ ЇВ?", "in the top left", ["chef"],
     "a huge burger with an American-flag toothpick on the right, a red STOP hand stamp pressing on it, chef on the left pointing at the viewer with a shocked face, red marker arrow to the burger, background saturated red"),
    ("T04", "ХТО ПРАВИЙ?", "in the top left", ["chef"],
     "a whole chicken in the center being pulled by two big cartoon hands, one from the left holding an American flag and one from the right holding a European flag, "
     "chef small in the corner scratching his head with question marks, background saturated yellow"),
    ("T05", "ЗА ЩО?!", "in the top left", ["shepherd"],
     "a determined French sheep farmer with a big mustache and flat cap HUGE on the left holding a crowbar, behind him a half-demolished fast-food restaurant with a yellow arch lying on the ground, "
     "a sheep beside him looking shocked, red marker circle around the arch, background saturated teal"),
    ("T06", "У ХЛІБІ?!", "in the top left", ["chef"],
     "chef HUGE on the right, mouth wide open in shock, holding a sandwich in which a rolled yoga mat peeks out of the bread, red marker arrow pointing at the yoga mat, background saturated red"),
    ("T07", "СТОП", "in the top left", [],
     "a delivery truck full of whole chickens stopped in front of a big red-white border barrier with a European star flag, the truck driver chicken face looking sad out of the window, "
     "red marker circle around the barrier, background saturated yellow"),
    ("T08", "Е-ШКИ?", "in the top left", ["chef", "child"],
     "a huge bag of neon-colored candy in the center with a small warning triangle sticker on it, chef holding a magnifying glass up to it, a child behind reaching for it, "
     "red marker circle around the sticker, background saturated teal"),
    ("T09", "×2", "in the top left", ["shepherd"],
     "a giant wedge of blue cheese HUGE in the center with a gigantic price tag doubling in size shown by two stacked tags, a shocked French shepherd with mustache beside it grabbing his hair, "
     "red marker arrow pointing at the price tag, background saturated red"),
    ("T10", "ТИ Б З'ЇВ?", "in the top left", ["chef"],
     "chef HUGE on the left holding a fork with a piece of chicken that is dripping with bubbly foam, looking at it with a disgusted and curious face, "
     "red marker circle around the foam, background saturated yellow"),
]


def thumb_items(style_head: str) -> list[dict]:
    cast = plan.load_cast(SLUG)
    items, n = [], 900
    for key, _, space, who, scene in THUMBS:
        looks = (" Character looks (draw exactly): " + "; ".join(f"{k} = {cast[k]}" for k in who) + ".") if who else ""
        prompt = f"{style_head}; {COMP.format(space=space)}.{looks} Scene: {scene}."
        for k in range(2):
            items.append({"id": n, "file": f"thumb_{key}_{k}.jpg", "prompt": prompt, "edits": []})
            n += 1
    return items


if __name__ == "__main__":
    base = flow.export(SLUG)
    f = base / "agent_A" / "prompts.json"
    pj = core.load_json(f)
    first = pj["items"][0]["prompt"]
    style_head = first.split(" Character looks")[0].split(" Scene:")[0].rstrip(". ")
    style_head = style_head.replace("ONE clear main subject (a food item, an object or one character) drawn large in the center or on one third of the frame, plenty of empty space around it, "
                                    "medium shot, at most three main elements, ", "")
    pj["items"] = thumb_items(style_head) + pj["items"]
    core.save_json(f, pj)
    print(base, len(pj["items"]), "елементів (20 прев'ю + кадри)")
