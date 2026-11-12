"""Наповнює бібліотеку звукових ефектів (storage/sfx_library/) через ElevenLabs Sound Effects.

    python -m app.tools.build_sfx_library --list        # що є / чого бракує (безкоштовно)
    python -m app.tools.build_sfx_library               # згенерувати все відсутнє (≈ $0.02 за ефект)
    python -m app.tools.build_sfx_library --only bow_draw arrow_volley
    python -m app.tools.build_sfx_library --force       # перегенерувати наявні

Ключ ElevenLabs має бути з правом "Sound Effects" (sound_generation): elevenlabs.io -> Developers ->
API Keys -> редагувати ключ -> увімкнути дозвіл (або створити ключ без обмежень).
"""

import argparse
import sys

from .. import sfx
from ..providers.base import ProviderConfigError


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--only", nargs="+", metavar="TAG")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    if args.list:
        for tag, d in sfx.CATALOG.items():
            print(f"{'є   ' if sfx.path_for(tag).exists() else 'НЕМА'}  {tag:16} {d.kind:9} {d.duration:g} с")
        print(f"\nВідсутніх: {len(sfx.missing_tags())} із {len(sfx.CATALOG)}. Папка: {sfx.SFX_ROOT}")
        return 0

    try:
        result = sfx.build_library(only=args.only, force=args.force)
    except ProviderConfigError as exc:
        print("FAIL:", exc)
        return 1
    print(f"\nЗгенеровано: {len(result['generated'])}, пропущено (вже є): {len(result['skipped'])}, помилок: {len(result['failed'])}")
    for tag, reason in result["failed"].items():
        print(f"  ! {tag}: {reason}")
    return 1 if result["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
