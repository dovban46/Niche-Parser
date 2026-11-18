"""v07 пакет Flow: 10 концептів прев'ю (по 2 генерації, ЙДУТЬ ПЕРШИМИ). Стиль ТОЧНО як кадри відео (олівець+акварель на кремовому папері, без яскравих плоских фонів),
дівчата з природними елегантними пропорціями (НЕ карикатура), дуже гарні, одягнені; одна драматична сцена, сильна емоція. Вибір ТІЛЬКИ разом з користувачем після рендеру.
Запуск з кореня: PYTHONIOENCODING=utf-8 python episodes/v07_eu_to_ukraine/export.py"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from app.jp import core, flow  # noqa: E402

SLUG = "v07_eu_to_ukraine"
HEAD = ("Hand-drawn pencil and ink sketch illustration with soft watercolor wash on cream off-white paper, exactly like a page from an explainer storyboard notebook: visible fine pencil hatching, "
        "loose confident ink linework, muted pastel watercolors (dusty blue, sand, sage, warm ochre, soft pink) with a few bolder accents, subtle paper texture, small ink splatters. "
        "16:9 YouTube thumbnail composition, the top 22 percent calm and light for a title. The young women are drawn with natural elegant proportions, NOT caricature and NOT exaggerated cartoon: "
        "refined delicate faces, realistic slim figures, large soft eyes with long lashes, small nose, full lips, rosy watercolor cheeks, long flowing hair drawn with fine pencil strokes, "
        "very beautiful and glamorous, fully clothed. ONE dramatic moment, big faces and big objects, few small details, strong shock or worry or cheeky emotion, readable at tiny size")

THUMBS = [
    ("T01", "ЄВРО НА КОРДОНІ?!",
     "a stunning young Ukrainian traveller woman in a stylish coat clutching a thick stack of euro banknotes behind her back with a guilty worried look, facing a stunning Ukrainian female customs officer in a blue uniform with a yellow-and-blue patch and cap who raises an eyebrow with a teasing smile, a border booth behind them"),
    ("T02", "ЛІКИ = ПРОБЛЕМА?",
     "a stunning young woman holding a small box of pills and a prescription paper with a scared expression, a stunning Ukrainian customs officer woman in a blue uniform leaning in with a stern but beautiful face and a magnifying glass over the pills, airport customs desk"),
    ("T03", "СКІЛЬКИ МОЖНА АЛКОГОЛЮ?",
     "a stunning young woman at a customs table proudly lifting a bottle of wine and a bottle of spirits, several more bottles in her shopping bags, while a stunning Ukrainian female customs officer in a blue uniform holds up a large measuring beaker with an amused shocked expression"),
    ("T04", "КІШКА НА КОРДОНІ",
     "a stunning young woman hugging a cat carrier with a wide-eyed anxious face, a passport and a vaccine booklet in her hand, a stunning Ukrainian female border officer in a blue uniform scanning the cat with a handheld scanner and smiling kindly, the cat's curious eyes peeking out"),
    ("T05", "ПОСИЛКА З ПОЛЬЩІ: ПОДАТОК?!",
     "a stunning young woman opening a big cardboard parcel full of clothes and shoes with delighted eyes, while a stunning Ukrainian customs officer woman in a blue uniform holds a long receipt that reaches the floor and a calculator with a mischievous smile"),
    ("T06", "ВАЛІЗА ПОНАД ЛІМІТ",
     "a stunning young woman struggling to close an overstuffed suitcase with a shocked grimace while shopping bags with logos-free paper bags spill around her, a stunning Ukrainian female customs officer in a blue uniform behind with arms crossed and a playful smirk"),
    ("T07", "ПАЛЬНЕ В КАНІСТРАХ?!",
     "a stunning young woman standing at the open trunk of a small car full of red jerry cans, hands on cheeks in shock, a stunning Ukrainian female officer in a blue uniform with a flashlight and a clipboard looking at the trunk with raised eyebrows, border lane behind"),
    ("T08", "ХОВАЄ В ВЗУТТІ?",
     "a stunning young woman sitting on a bench taking off her boot with a nervous cheeky smile and a roll of banknotes peeking out of the boot, a stunning Ukrainian female customs officer in a blue uniform crouching and peering at her with a mischievous grin"),
    ("T09", "ЗЕЛЕНИЙ ЧИ ЧЕРВОНИЙ?",
     "a stunning young woman stopped at a fork between a green lane and a red lane with a huge suitcase, biting her lip with a worried look, a stunning Ukrainian female customs officer in a blue uniform watching from behind a counter with a half-smile"),
    ("T10", "ПОДАРУНОК З ПОЛЬЩІ",
     "a stunning young woman handing a gift bag across the border barrier to a stunning Ukrainian female customs officer who lifts out a sausage ring and a bottle and raises both eyebrows, the woman covering her mouth, border barrier and flags in soft sketch"),
]


def thumb_items() -> list[dict]:
    items, n = [], 900
    for key, _, scene in THUMBS:
        prompt = f"{HEAD}. Scene: {scene}. No text, no letters, no numbers, no logos, no border."
        for k in range(2):
            items.append({"id": n, "file": f"thumb_{key}_{k}.jpg", "prompt": prompt, "edits": []})
            n += 1
    return items


if __name__ == "__main__":
    base = flow.export(SLUG)
    f = base / "agent_A" / "prompts.json"
    pj = core.load_json(f)
    pj["items"] = thumb_items() + pj["items"]
    core.save_json(f, pj)
    print(base, len(pj["items"]), "елементів (20 прев'ю + кадри)")
