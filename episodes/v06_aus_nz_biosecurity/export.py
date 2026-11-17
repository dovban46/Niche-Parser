"""v06 пакет Flow: 10 концептів прев'ю (по 2 генерації, ЙДУТЬ ПЕРШИМИ), нова схема після CTR 2,8% у v05: ОДИН драматичний момент, сильна емоція (шок/тривога), яскравий насичений фон,
великі обличчя, дуже гарні дівчата (грайливі, одягнені), мінімум деталей. Стиль: олівцевий скетч+акварель, мультяшні гарні персонажі, але фон НЕ кремовий.
Вибір прев'ю ТІЛЬКИ разом з користувачем після рендеру. Запуск з кореня: PYTHONIOENCODING=utf-8 python episodes/v06_aus_nz_biosecurity/export.py"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from app.jp import core, flow  # noqa: E402

SLUG = "v06_aus_nz_biosecurity"
HEAD = ("YouTube thumbnail, 16:9, hand-drawn pencil and ink sketch illustration with bold saturated watercolor wash, confident ink outlines, visible pencil hatching, a few ink splatters, "
        "BUT with a vivid saturated flat-color background (sunny yellow, hot orange or sky blue, NOT cream paper) so it stands out in a feed. "
        "Characters drawn as polished simple storyboard sketch-cartoon: huge expressive eyes with long lashes, glossy lips, rosy cheeks, long flowing hair, "
        "strikingly beautiful and glamorous young women with slim elegant figures, playful confident poses, stylish fitted clothes, fully clothed. "
        "ONE dramatic moment, big faces and big objects, very few small details, strong shock or fear or cheeky emotion, readable at tiny size; "
        "keep the top 22 percent calm (plain colored background) for a big title added later; no text, no letters, no numbers, no logos, no border")

THUMBS = [
    ("T01", "ЯБЛУКО = ШТРАФ?!",
     "a gorgeous Ukrainian young woman with a flower wreath and vyshyvanka blouse in close-up with mouth open in horror, holding a shiny red apple; a huge beagle detector dog sniffing her bag; a big red prohibition sign over the apple"),
    ("T02", "ШТРАФ ЗА ЯБЛУКО?!",
     "a close-up of a gorgeous female Australian biosecurity officer in a snug khaki uniform and cap with a mischievous smile holding a huge fine ticket in one hand and pointing at a shocked Ukrainian girl with a flower wreath who is clutching an apple to her chest"),
    ("T03", "ПЕС ЗНАЙШОВ БУТЕРБРОД",
     "a gorgeous Ukrainian girl in a vyshyvanka at an airport, hugging her bag with wide terrified eyes while a happy beagle detector dog in a vest jumps up and points its nose at a sandwich peeking from the bag, the officer girl in the background raising an eyebrow"),
    ("T04", "АВСТРАЛІЯ: ЗАБОРОНЕНО ВСЕ?",
     "a kangaroo in a customs officer cap stamping a giant red STOP stamp on a suitcase while a gorgeous shocked Ukrainian girl with flower wreath holds up both hands, a map outline of Australia in the corner, a koala sitting on the scanner"),
    ("T05", "ЦЕЙ МЕД КОШТУЄ $2600",
     "a gorgeous Ukrainian girl with a wink holding up a jar of honey like a trophy, a gorgeous Australian officer girl beside her with a fine ticket and huge shocked eyes, bees flying around, bright yellow background"),
    ("T06", "ЧОТИРИ ГОДИНИ ЗАТРИМКИ",
     "a gorgeous Ukrainian girl sitting on her suitcase with a dirty hiking boot in her hand and a sad cute pout, a female officer in rubber gloves holding a tiny bottle of soil and a magnifying glass over the boot, orange background"),
    ("T07", "ВОНА ВЕЗЛА ШИНКУ",
     "a gorgeous Australian girl in a bush hat and a gorgeous Ukrainian girl in a vyshyvanka both holding opposite ends of a ham sandwich and pulling, with a giant red prohibition sign between them, comic fight, sky blue background"),
    ("T08", "ГОЛОВНИЙ ВОРОГ: ЯБЛУКО",
     "a giant glossy red apple in the center with angry cartoon eyes towering over a tiny scared gorgeous Ukrainian girl with a flower wreath and a gorgeous officer girl with a net trying to catch it, dramatic low angle"),
    ("T09", "ЇЇ ОШТРАФУВАЛИ НА $2664",
     "a gorgeous Ukrainian girl in tears of laughter-and-fear holding a stack of fine tickets that reach the floor, the airport hall behind her, a beagle in a vest sitting proudly next to her, bright orange background"),
    ("T10", "СКІЛЬКИ НА ЦЕ ВИТРАТИШ?!",
     "a gorgeous Ukrainian girl holding an empty wallet turned inside out with wide shocked eyes, a pile of confiscated food (apple, honey jar, cheese, sausage) in a clear bin beside her, a gorgeous officer girl smiling and holding a card machine"),
]


def thumb_items() -> list[dict]:
    items, n = [], 900
    for key, _, scene in THUMBS:
        prompt = f"{HEAD}. Scene: {scene}."
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
