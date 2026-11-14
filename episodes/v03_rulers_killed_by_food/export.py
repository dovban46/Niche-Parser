"""v03 пакет Flow: 10 концептів прев'ю (по 2 генерації, ЙДУТЬ ПЕРШИМИ) у стилі олівцевого скетчу з акварелью, але з яскравішими акцентами та великим вільним верхом під заголовок.
Вибір прев'ю ТІЛЬКИ разом з користувачем після рендеру. Запуск з кореня: PYTHONIOENCODING=utf-8 python episodes/v03_rulers_killed_by_food/export.py"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from app.jp import core, flow, plan  # noqa: E402

SLUG = "v03_rulers_killed_by_food"
COMP = ("YouTube thumbnail, 16:9, hand-drawn pencil and ink sketch with bold watercolor wash on cream paper, stronger and more saturated colors than a plain sketch, "
        "confident ink outlines, clear readable big shapes that work at small size, one dramatic main subject with an exaggerated surprised or worried face, "
        "a few small background details; keep the top 22% of the picture calm and light (empty paper or soft sky) for a big title added later; no text, no letters, no numbers")

THUMBS = [
    ("T01", "ВБИЛА БУЛОЧКА?", ["adolf"],
     "King Adolf Frederick in a powdered wig sitting at a table looking at a huge cream bun on a plate with fear, a pile of fourteen buns on a silver tray behind"),
    ("T02", "ГРИБ ЗМІНИВ ЄВРОПУ", ["charles"],
     "Emperor Charles VI in a long wig staring at a big mushroom on a plate, behind him a faint sketch of cannon smoke and marching armies"),
    ("T03", "ОТРУЇЛИ?!", ["claudius", "agrippina"],
     "Roman emperor Claudius raising a fork with a mushroom, shocked; behind his shoulder Agrippina smiles coldly and a servant hides a small vial"),
    ("T04", "ВБИЛА МІНОГА?", ["henry", "doctor"],
     "King Henry I of England at a feast table with a plate of long snake-like lampreys, a doctor beside him shaking his head and waving a finger"),
    ("T05", "ДВІ ДИНІ Й ПАПА", ["paul"],
     "Pope Paul II in a tall jeweled tiara hugging two enormous melons with a greedy face, Roman columns behind"),
    ("T06", "ВИШНІ ВБИЛИ ПРЕЗИДЕНТА?", ["taylor"],
     "President Zachary Taylor sweating under a hot sun holding a glass of milk with ice and a bowl of cherries, a unfinished white monument behind him"),
    ("T07", "СЕМЕРО ПРАВИТЕЛІВ", ["chef"],
     "a long banquet table with seven rulers from different eras, each in a crown or tiara in front of his own deadly-looking dish, the chef host at the end of the table sweating and wide eyed"),
    ("T08", "МІФ ЧИ ПРАВДА?", ["chef", "scientist"],
     "a big old balance scale: on one pan a king's crown, on the other a plate of food; a chef host and a forensic scientist with a magnifying glass looking at it, question marks floating"),
    ("T09", "ВЕСІЛЬНИЙ БЕНКЕТ", ["attila", "ildico"],
     "Attila the Hun at a smoky wedding feast with a huge goblet, a shy bride beside him, torches and a dark ominous shadow behind him"),
    ("T10", "ЇХ ЗГУБИЛА ЇЖА?", ["chef"],
     "an empty royal crown lying on a white dinner plate between a fork and a knife like a meal, the chef host peeking from behind a napkin with a terrified face, dark dramatic background"),
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
