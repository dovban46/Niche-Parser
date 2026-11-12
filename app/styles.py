"""Візуальні стилі. Стиль живе в ПЕРШОМУ КАДРІ (Nano Banana малює його з префіксом + референсами),
а Veo лише оживлює цей кадр — тому узгодженість між сценами вирішується тут, а не в анімації.

Додати стиль = новий запис у STYLES. Референс-кадри (2-4 затверджені зразки) кладуться в
storage/style_refs/<style_id>/ — їх автоматично отримує кожен виклик генерації картинки.
"""

from dataclasses import dataclass
from pathlib import Path

from .config import STYLE_REFS_ROOT

_SAFETY_SUFFIX = (
    "Widescreen 16:9 composition. No text, no captions, no watermark. Render ONLY the era and setting "
    "described in the Scene below: if the Scene explicitly places us in a later period or the modern day "
    "(e.g. a 20th-century city, a modern library or lab, people in modern dress), depict THAT period "
    "accurately — modern clothing, electric light, modern furniture and objects as appropriate — instead "
    "of defaulting to antiquity; only avoid modern/anachronistic objects when the Scene itself is clearly "
    "set in antiquity or does not mention a later period. "
    "No blood, no gore, no graphic violence: keep any conflict implied, distant or symbolic; "
    "no close-up faces — people are seen from a distance, from behind, or as silhouettes. "
    "The scene must fill the entire frame edge-to-edge — no decorative border, no ornamental "
    "frame, no vignette drawn as part of the image, nothing meant to look like a page margin: "
    "this is a single continuous shot, not a framed illustration, because it will be panned and "
    "zoomed and a drawn border would warp and break the illusion. Anatomically consistent figures: "
    "correct number of fingers, and if a hand performs an action (writing, holding, pouring), the "
    "SAME hand does it throughout — never switch which hand holds the tool mid-gesture."
)

_MOTION_SUFFIX = (
    "Slow, steady cinematic camera movement. Only gentle natural motion (wind, smoke, fire, fog, "
    "water, cloth, banners, distant marching). No fast cuts, no close combat, no text, no gore. "
    "Keep the frame full-bleed — no border or frame drawn around the scene. If any figure's hand is "
    "performing an action across the shot (writing, holding, pouring, lighting), that same hand must "
    "stay the same hand for the whole motion — do not let it switch sides. "
    "Sound: only natural ambient sound effects of the scene (wind, cloth, fire, footsteps, distant metal), "
    "no speech, no singing, no music."
)


@dataclass(frozen=True)
class Style:
    id: str
    label: str
    description: str
    image_prefix: str
    motion_hint: str
    negative_video: str
    grade: str  # ffmpeg-фільтр єдиної кольорової обробки всіх візуалів відео
    accent: str  # типовий акцентний колір титулу/плашок (досьє теми може його перекрити)
    flux_prefix: str = ""  # КОРОТКИЙ опис стилю (~25 слів) для FLUX: той читає лише ~256 токенів промпта
    image_boost: str = ""  # жорсткий хвіст промпта для слабших дифузійних моделей (FLUX): стиль як ТЕХНІКА, не епоха


STYLES: dict[str, Style] = {
    "painterly": Style(
        id="painterly",
        label="Живописна ілюстрація",
        description="Олійний живопис у дусі романтичних батальних полотен, приглушена палітра.",
        image_prefix=(
            "Cinematic historical illustration in the style of a romantic-era oil painting: rich painterly "
            "brushwork, dramatic chiaroscuro lighting, muted earthy palette (umber, ochre, slate blue, deep "
            "green), subtle canvas texture, epic wide composition, atmospheric depth."
        ),
        motion_hint="Preserve the painterly look. " + _MOTION_SUFFIX,
        negative_video="blood, gore, close-up faces, text, subtitles, watermark, modern objects, photorealistic, cartoon",
        grade="eq=contrast=1.06:saturation=0.88:gamma=0.98,vignette=angle=0.45",
        accent="#C6953A",
    ),
    "graphic_2d": Style(
        id="graphic_2d",
        label="Стилізована 2D-графіка",
        description="Graphic novel: чіткий контур, пласкі кольори, обмежена палітра.",
        image_prefix=(
            "Stylized 2D graphic-novel illustration: bold ink outlines, flat cel-shaded colors in a limited "
            "palette, dramatic lighting, historically epic wide composition, clean shapes."
        ),
        motion_hint="Preserve the flat graphic look. " + _MOTION_SUFFIX,
        negative_video="blood, gore, close-up faces, text, subtitles, watermark, modern objects, photorealistic",
        grade="eq=contrast=1.08:saturation=1.02,vignette=angle=0.35",
        accent="#E4572E",
    ),
    "manuscript": Style(
        id="manuscript",
        label="Ілюмінований рукопис",
        description="Стародавній/середньовічний рукопис: пергамент або папірус, позолота, площинні фігури.",
        image_prefix=(
            "Ancient or medieval illuminated manuscript miniature: flat stylised figures with gilded highlights, "
            "hand-pigmented colors, aged parchment or papyrus texture, naive period-accurate perspective, gold "
            "leaf accent lighting true to the culture and era depicted."
        ),
        motion_hint="Preserve the flat manuscript look. Very subtle motion only: drifting smoke, fluttering banners, "
        "slow camera drift. No text, no gore. Sound: only natural ambient sound effects, no speech, no singing, no music.",
        negative_video="blood, gore, close-up faces, modern text, subtitles, watermark, photorealistic, 3d render",
        grade="eq=contrast=1.04:saturation=0.85:gamma=1.02,vignette=angle=0.4",
        accent="#B8862B",
    ),
    "engraving": Style(
        id="engraving",
        label="Містична гравюра (рекомендовано для ancient_mysteries)",
        description="Старовинна гравюра на міді/дереві: чорнильні штрихи, глибокий контраст, сепія й приглушене золото.",
        image_prefix=(
            "Antique copper/wood engraving illustration in the style of 17th-19th century esoteric and occult "
            "book plates: fine crosshatched ink linework, dramatic chiaroscuro, sepia and aged-paper tones with "
            "restrained gold-leaf highlights, dense atmospheric detail, an air of forbidden and hidden knowledge."
        ),
        motion_hint="Preserve the engraved linework look. " + _MOTION_SUFFIX,
        negative_video="blood, gore, close-up faces, text, subtitles, watermark, modern objects, photorealistic, cartoon, color photo",
        grade="eq=contrast=1.1:saturation=0.55:gamma=0.95,vignette=angle=0.5",
        accent="#8A6D3B",
        flux_prefix="Vintage copper-plate engraving print, dense black crosshatch hatching lines, monochrome sepia ink on aged cream paper",
        image_boost=(
            "RENDER AS: antique copper engraving TECHNIQUE, dense crosshatch ink linework, monochrome sepia on "
            "aged paper. This is a drawing technique only, not a time period: draw the Scene exactly as described."
        ),
    ),
    "woodcut": Style(
        id="woodcut",
        label="Старовинна ксилографія (woodcut)",
        description="Грубий чорно-білий друк з дерев'яної гравюри: товсті штрихи, стійкий контраст, без сепії — інший силует, ніж engraving.",
        image_prefix=(
            "Stark medieval woodcut block-print illustration, in the style of 15th-16th century printed book "
            "woodcuts: bold thick carved ink lines, high-contrast black on aged cream paper, no fine crosshatch "
            "shading, simplified graphic shapes with heavy black silhouettes, rough hand-carved texture, a "
            "grim and primal medieval-gothic mood distinct from delicate copper engraving."
        ),
        motion_hint="Preserve the bold woodcut linework, thick black shapes stay crisp. " + _MOTION_SUFFIX,
        negative_video="blood, gore, close-up faces, text, subtitles, watermark, modern objects, photorealistic, color photo, fine crosshatch, sepia tone",
        grade="eq=contrast=1.25:saturation=0.15:gamma=0.9,vignette=angle=0.35",
        accent="#2B2620",
    ),
    "fresco": Style(
        id="fresco",
        label="Помпейська фреска (античний живопис)",
        description="Автентичний стиль давньоримської фрески з Помпей/Геркуланума: земляні пігменти, "
                     "«помпейський червоний», охра, вицвіла патина — тепла кольорова альтернатива до ч/б стилів.",
        image_prefix=(
            "Ancient Roman fresco painting in the authentic style of Pompeii and Herculaneum wall paintings: "
            "earthy mineral pigments, iconic deep Pompeian red and warm ochre backgrounds, weathered plaster "
            "texture with fine age cracks, flat naturalistic figures with soft sfumato shading and dark "
            "contour outlines, faded muted color palette true to 1st-century Campanian wall art, restrained "
            "gold and terracotta accents."
        ),
        motion_hint="Preserve the fresco look: flat plaster texture, muted earthy palette. " + _MOTION_SUFFIX,
        negative_video="photorealistic, 3d render, modern objects, text, subtitles, watermark, blood, gore, "
                        "close-up faces, cartoon, bright saturated modern colors, black and white, grayscale",
        grade="eq=contrast=1.05:saturation=0.8:gamma=1.03,vignette=angle=0.4",
        accent="#A8481F",
    ),
    "cinematic": Style(
        id="cinematic",
        label="Кінематографічна реконструкція (фотореалізм)",
        description="Фотореалістична документальна реконструкція в дусі великобюджетних історичних "
                     "докудрам (BBC/Netflix) — інший регістр, ніж ілюстрація/гравюра.",
        image_prefix=(
            "Photorealistic cinematic historical reenactment, in the style of a big-budget documentary "
            "drama (BBC/Netflix historical reconstruction): natural but dramatic lighting, volumetric haze "
            "and dust in the air, richly detailed sets, props and costumes accurate to the era, shallow "
            "depth of field, clean modern digital cinema look, warm torchlit or golden-hour color grade."
        ),
        motion_hint="Preserve the photorealistic documentary look, natural lighting. " + _MOTION_SUFFIX,
        negative_video="illustration, painting, cartoon, anime, 3d render, cel shading, drawing, sketch, "
                        "text, subtitles, watermark, blood, gore, close-up faces, modern objects",
        grade="eq=contrast=1.08:saturation=1.02:gamma=1.0,vignette=angle=0.3",
        accent="#C1440E",
    ),
    "engraving_tint": Style(
        id="engraving_tint",
        label="Гравюра з акварельним тонуванням",
        description="Та сама гравюрна лінія, що зайшла глядачам, але з приглушеним акварельним кольором "
                     "(індиго, охра, марена) на старому папері.",
        image_prefix=(
            "Antique copper engraving illustration, 17th-19th century esoteric book plate with fine crosshatched "
            "ink linework, hand-coloured with restrained translucent watercolour washes (muted indigo, ochre, "
            "madder red, verdigris) over aged cream paper, the colour kept soft and limited so the black ink "
            "linework stays dominant, dramatic chiaroscuro, dense atmospheric detail, an air of forbidden and "
            "hidden knowledge."
        ),
        motion_hint="Preserve the hand-coloured engraving look. " + _MOTION_SUFFIX,
        negative_video="blood, gore, close-up faces, text, subtitles, watermark, modern objects, photorealistic, 3d render, cartoon",
        grade="eq=contrast=1.08:saturation=0.85:gamma=0.97,vignette=angle=0.45",
        accent="#9C4A2F",
        flux_prefix="Vintage copper-plate engraving print, black ink crosshatch hatching lines on aged cream paper, hand-tinted with pale watercolour washes of indigo, ochre and madder red",
        image_boost=(
            "RENDER AS: antique copper engraving with dense black crosshatch linework, lightly hand-tinted with "
            "soft watercolour washes in indigo, ochre and madder red on aged paper. Technique only, not a time "
            "period: draw the Scene exactly as described."
        ),
    ),
}
DEFAULT_STYLE_ID = "engraving"  # найкраще пасує ніші ancient_mysteries (заборонені книги/апокрифи)


def get_style(style_id: str | None) -> Style:
    return STYLES.get(style_id or "", STYLES[DEFAULT_STYLE_ID])


def build_image_prompt(style: Style, glossary: str, shot: str) -> str:
    # Scene ПЕРШИЙ рядок, не останній: перевірено на job 12 (fal.ai/FLUX) — коли конкретна сцена йшла
    # ПІСЛЯ довгого стильового префікса й багатоетапного глосарія, слабший image-провайдер її просто
    # губив і малював домінантний "історичний" стиль (ченці/античність) навіть для сегментів, де shot
    # прямо писав "Zurich institute library interior, modern dress" — підтверджено звіркою beats_json
    # (запланований текст) із фактично згенерованим зображенням. Diffusion-моделі найсильніше тримають
    # зміст з початку промпту, тому головна дія йде першою, стиль і довідковий глосарій — підпорядковано.
    parts = [f"Scene (render exactly this, including its era/time period if stated): {shot}", style.image_prefix]
    if glossary:
        # Глосарій — КІЛЬКА різних візуальних етапів усієї історії (див. anthropic_provider.py), лише
        # для довідки/точності деталей, не список того, що має бути в КОЖНОМУ кадрі. Без цього застереження
        # генератор картинок намагався втиснути елементи всіх етапів в одне зображення.
        parts.append(
            "Background reference only, covering the whole story's different stages — the Scene above "
            "already tells you which one applies; ignore the rest, never blend multiple stages or "
            "locations into one image:\n" + glossary
        )
    parts.append(_SAFETY_SUFFIX)
    if style.image_boost:
        parts.append(style.image_boost)
    return "\n".join(parts)


def build_compact_prompt(style: Style, scene: str) -> str:
    """Короткий промпт для моделей із малим вікном тексту (FLUX schnell читає ~256 токенів): стиль першим
    рядком, далі сцена (вже коротка версія від арт-директора), мінімальні заборони. Довгий промпт
    build_image_prompt для FLUX відрізається — стиль і/або сцена губляться (знайдено на job 13)."""
    prefix = style.flux_prefix or " ".join(style.image_prefix.split()[:28])
    return (
        f"{prefix}. Scene: {scene.strip()} Drawn as an engraved illustration with visible hatching lines, "
        "not a photograph, not a digital painting. No text, no border, faces hidden or in shadow, wide 16:9."
    )


def build_motion_prompt(style: Style, shot: str, motion: str) -> str:
    return f"{shot}\nMotion: {motion}\n{style.motion_hint}"


def style_reference_images(style_id: str, limit: int = 4) -> list[Path]:
    folder = STYLE_REFS_ROOT / style_id
    if not folder.is_dir():
        return []
    files = sorted(p for p in folder.iterdir() if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"))
    return files[:limit]
