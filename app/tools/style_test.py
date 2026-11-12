"""Тест стилів: по кілька однакових кадрів у кожному стилі — щоб обрати стиль ДО того, як платити за кліпи.

    python -m app.tools.style_test                       # усі стилі × 3 кадри (≈ 9 зображень ≈ $0.30)
    python -m app.tools.style_test --styles painterly    # лише один стиль
    python -m app.tools.style_test --shots 2

Результат: storage/style_tests/index.html (відкрий у браузері: http://127.0.0.1:8020/storage/style_tests/index.html
при запущеному сервері) і окремі PNG. Сподобалися 2-4 кадри стилю — скопіюй їх у storage/style_refs/<стиль>/:
далі КОЖЕН кадр цього стилю малюватиметься з них як з референсів (узгодженість між сценами).
"""

import argparse
import html
import sys

from ..config import IMAGE_PROVIDER, STORAGE_ROOT
from ..providers.base import ProviderConfigError
from ..providers.registry import get_image_provider
from ..styles import STYLES, build_image_prompt, style_reference_images

_GLOSSARY = (
    "Late medieval Europe, 15th century. Knights in plate armor with cloth surcoats and heraldic banners, archers in "
    "padded gambesons with longbows, a stone castle with wooden hoardings, overcast dawn, damp earth and mist."
)
_SHOTS = [
    "Wide view of a stone castle on a hill at dawn, siege towers and tents in the misty valley below, banners in the wind.",
    "Line of archers seen from behind on a castle wall, drawing longbows against an orange dusk sky, silhouettes.",
    "Distant mounted knights riding across a muddy field toward a fortified town, dust and smoke drifting, dramatic clouds.",
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--styles", nargs="+", choices=list(STYLES), default=list(STYLES))
    parser.add_argument("--shots", type=int, default=3, choices=range(1, len(_SHOTS) + 1))
    args = parser.parse_args()

    if IMAGE_PROVIDER == "stub":
        print("УВАГА: IMAGE_PROVIDER=stub — малюватиму заглушки. Для реальних кадрів постав IMAGE_PROVIDER=google у .env.")
    try:
        image_gen = get_image_provider()
    except ProviderConfigError as exc:
        print("FAIL:", exc)
        return 1

    total = len(args.styles) * args.shots
    print(f"Генерую {total} зображень (≈ ${total * image_gen.cost_per_image_usd:.2f}) ...")
    out_dir = STORAGE_ROOT / "style_tests"
    out_dir.mkdir(parents=True, exist_ok=True)

    sections = []
    for style_id in args.styles:
        style = STYLES[style_id]
        refs = style_reference_images(style_id)
        cells = []
        for i, shot in enumerate(_SHOTS[: args.shots], start=1):
            path = out_dir / f"{style_id}_{i}.png"
            try:
                image_gen.generate_image(build_image_prompt(style, _GLOSSARY, shot), path, refs)
                cells.append(f'<img src="{path.name}" alt="">')
                print(f"  OK {path.name}")
            except ProviderConfigError as exc:
                cells.append(f"<p>помилка: {html.escape(str(exc))}</p>")
                print(f"  ! {path.name}: {exc}")
        sections.append(f"<h2>{html.escape(style.label)}</h2><p>{html.escape(style.description)}</p><div>{''.join(cells)}</div>")

    (out_dir / "index.html").write_text(
        "<!doctype html><meta charset='utf-8'><title>Тест стилів</title>"
        "<style>body{background:#0f1420;color:#e7ecf7;font-family:sans-serif;padding:20px}"
        "img{width:32%;margin:4px;border-radius:8px}</style><h1>Тест стилів</h1>" + "".join(sections),
        encoding="utf-8",
    )
    print("Готово:", out_dir / "index.html")
    return 0


if __name__ == "__main__":
    sys.exit(main())
