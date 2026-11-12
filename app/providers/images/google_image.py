"""Nano Banana (Gemini image) — генерація стоп-кадрів у єдиному стилі, з референс-кадрами стилю."""

import io
import os
from pathlib import Path

from PIL import Image

from .._image_utils import save_clean
from ..base import ImageGenProvider, ProviderConfigError
from ..google_client import call_with_retry, get_client, mime_for

_DEFAULT_MODEL = "gemini-3.1-flash-lite-image"  # Nano Banana 2 Lite, ≈$0.034 за 1K-кадр
_DEFAULT_SIZE = "1K"


class GoogleImageProvider(ImageGenProvider):
    cost_per_image_usd = 0.0336

    def __init__(self) -> None:
        self._client = get_client()
        self._model = os.environ.get("GOOGLE_IMAGE_MODEL") or _DEFAULT_MODEL
        self._size = os.environ.get("GOOGLE_IMAGE_SIZE") or _DEFAULT_SIZE

    def generate_image(self, prompt: str, out_path: Path, references: list[Path] | None = None) -> Path:
        from google.genai import types

        contents: list = [prompt]
        for ref in references or []:
            contents.append(types.Part.from_bytes(data=ref.read_bytes(), mime_type=mime_for(ref)))

        def request(modalities: list[str]):
            return self._client.models.generate_content(
                model=self._model,
                contents=contents,
                config=types.GenerateContentConfig(
                    automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
                    response_modalities=modalities,
                    image_config=types.ImageConfig(aspect_ratio="16:9", image_size=self._size),
                ),
            )

        response = call_with_retry(lambda: request(["IMAGE"]), f"зображення {self._model}")
        data = _first_image_bytes(response)
        if data is None:
            # Деякі моделі вимагають явно ["TEXT", "IMAGE"]; спробуємо ще раз, перш ніж здаватись.
            response = call_with_retry(lambda: request(["TEXT", "IMAGE"]), f"зображення {self._model}")
            data = _first_image_bytes(response)
        if data is None:
            raise ProviderConfigError(f"Google не повернув зображення: {_refusal_reason(response)}")

        save_clean(Image.open(io.BytesIO(data)), out_path)
        return out_path


def _first_image_bytes(response) -> bytes | None:
    for part in getattr(response, "parts", None) or []:
        inline = getattr(part, "inline_data", None)
        if inline is not None and getattr(inline, "data", None):
            return inline.data
    return None


def _refusal_reason(response) -> str:
    feedback = getattr(response, "prompt_feedback", None)
    reason = getattr(feedback, "block_reason", None)
    if reason:
        return f"запит заблоковано фільтром ({reason})"
    text = (getattr(response, "text", None) or "").strip()
    return text[:200] or "порожня відповідь (ймовірно, спрацював фільтр безпеки)"
