"""Stub-реалізація ImageGenProvider — без жодного API-ключа.

Малює справжній PNG (16:9, кольоровий фон + підпис із промпту) через Pillow, щоб
video_assemble/qa мали реальний файл для роботи. Колір фону детермінований від
промпту — просто для візуальної різноманітності між сегментами. Замінюється на
providers/images/replicate_provider.py в наступному кроці.
"""

import hashlib
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .._image_utils import save_clean
from ..base import ImageGenProvider

_WIDTH, _HEIGHT = 1280, 720


def _color_from_prompt(prompt: str) -> tuple[int, int, int]:
    digest = hashlib.sha256(prompt.encode("utf-8")).digest()
    # Тримаємо кольори в темнуватому, не кислотному діапазоні.
    return (30 + digest[0] % 100, 30 + digest[1] % 100, 40 + digest[2] % 120)


class StubImageGenProvider(ImageGenProvider):
    def generate_image(self, prompt: str, out_path: Path, references: list[Path] | None = None) -> Path:
        out_path.parent.mkdir(parents=True, exist_ok=True)

        img = Image.new("RGB", (_WIDTH, _HEIGHT), color=_color_from_prompt(prompt))
        draw = ImageDraw.Draw(img)

        if "Scene:" in prompt:  # структурований промпт: підпис — сама сцена, а не стильовий префікс
            prompt = prompt.split("Scene:", 1)[1].strip().splitlines()[0]
        label = (prompt[:80] + "…") if len(prompt) > 80 else prompt
        try:
            font = ImageFont.truetype("arial.ttf", 36)
        except OSError:
            font = ImageFont.load_default()

        # Проста ручна перенесення тексту по словах, щоб влізло в кадр.
        words = label.split()
        lines: list[str] = []
        current = ""
        for word in words:
            trial = f"{current} {word}".strip()
            if draw.textlength(trial, font=font) > _WIDTH - 120:
                lines.append(current)
                current = word
            else:
                current = trial
        if current:
            lines.append(current)

        total_h = len(lines) * 48
        y = (_HEIGHT - total_h) // 2
        for line in lines:
            w = draw.textlength(line, font=font)
            draw.text(((_WIDTH - w) / 2, y), line, fill=(235, 235, 235), font=font)
            y += 48

        draw.text((20, _HEIGHT - 36), "STUB IMAGE — placeholder", fill=(180, 180, 180), font=font)

        save_clean(img, out_path)
        return out_path
