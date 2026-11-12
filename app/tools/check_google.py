"""Перевірка Google AI Studio перед першим запуском.

    python -m app.tools.check_google                 # безкоштовно: ключ + чи бачить він потрібні моделі
    python -m app.tools.check_google --probe-image   # + один тестовий кадр (≈ $0.034)
    python -m app.tools.check_google --probe-video   # + один 4-с кліп із цього кадру (≈ $0.20)
"""

import argparse
import os
import sys

from ..config import STORAGE_ROOT
from ..providers.base import ProviderConfigError
from ..providers.google_client import get_client


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--probe-image", action="store_true")
    parser.add_argument("--probe-video", action="store_true")
    args = parser.parse_args()

    try:
        client = get_client()
    except ProviderConfigError as exc:
        print("FAIL:", exc)
        return 1

    image_model = os.environ.get("GOOGLE_IMAGE_MODEL") or "gemini-3.1-flash-lite-image"
    video_model = os.environ.get("GOOGLE_VIDEO_MODEL") or "veo-3.1-lite-generate-preview"

    try:
        names = [m.name.removeprefix("models/") for m in client.models.list()]
    except Exception as exc:  # noqa: BLE001 — будь-яка помилка тут = проблема з ключем/мережею
        print("FAIL: ключ не пройшов перевірку:", str(exc)[:300])
        return 1
    print(f"OK: ключ приймається, моделей доступно: {len(names)}")

    for label, wanted, hint in (("кадри", image_model, "image"), ("відео", video_model, "veo")):
        if wanted in names:
            print(f"OK: {label}: модель '{wanted}' доступна")
        else:
            similar = [n for n in names if hint in n]
            print(f"УВАГА: {label}: модель '{wanted}' у списку немає. Схожі: {', '.join(similar) or 'жодної'}")
            print("       Задай потрібну в .env: GOOGLE_IMAGE_MODEL / GOOGLE_VIDEO_MODEL")

    probe = STORAGE_ROOT / "style_tests" / "probe.webp"
    try:
        if args.probe_image or args.probe_video:
            from ..providers.images.google_image import GoogleImageProvider

            print("Генерую тестовий кадр (≈ $0.034) ...")
            GoogleImageProvider().generate_image(
                "Cinematic oil-painting style, distant medieval stone castle at dawn, mist, banners in the wind. "
                "No text, no people close-up, 16:9.",
                probe,
            )
            print("OK: кадр збережено:", probe)

        if args.probe_video:
            from ..providers.video.google_video import GoogleVideoProvider

            out = probe.with_suffix(".mp4")
            print("Генерую тестовий 4-с кліп (≈ $0.20, до кількох хвилин) ...")
            GoogleVideoProvider().generate_clip("Slow push-in, mist drifting, banners fluttering in the wind.", probe, out, 4)
            print("OK: кліп збережено:", out)
    except ProviderConfigError as exc:
        print("FAIL:", exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
