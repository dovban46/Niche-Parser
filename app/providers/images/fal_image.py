"""fal.ai (FLUX) — дешевий image-провайдер (~$0.003/кадр на schnell проти $0.0336 у Nano Banana).

Використовується для "менш важливих" кадрів — беатів довгих still-сегментів (app/stages/_visuals.py:
generate_segment_beats), де об'єм заміняє ціну якості. Дифузійні FLUX-моделі гірше за Gemini-моделі
тримають детальні композиційні інструкції (перевірено: без підсилення промпту "no close-up face" не
виконувалось, з'являлась кольорова "фентезі"-картинка замість гравюри) — тому тут промпт з styles.py
підсилюється власним префіксом/негативним промптом під конкретно FLUX, а не змінюється спільний styles.py
(яким і далі користується google_image.py для важливих кадрів)."""

import io
import os
from pathlib import Path

import requests
from PIL import Image

from .._image_utils import save_clean
from ..base import ImageGenProvider, ProviderConfigError
from ...styles import _SAFETY_SUFFIX

_DEFAULT_MODEL = "fal-ai/flux/schnell"
_COST = {"fal-ai/flux/schnell": 0.003, "fal-ai/flux/dev": 0.025}

# Підсилення стилю специфічно під дифузійну модель — Nano Banana (styles.py) розуміє м'якіші
# формулювання, FLUX слухається лише прямих, повторюваних ключових слів.
_NEGATIVE_PROMPT = (
    "color photo, photorealistic, cinematic, digital painting, fantasy art, close-up face, visible face, "
    "portrait, front-facing, eyes, border, frame, vignette, watermark, text, signature"
)
_GLOSSARY_MARKER = "Background reference only, covering the whole story's different stages"


def _strip_glossary_block(prompt: str) -> str:
    """Вирізає блок багатоетапного глосарія (styles.build_image_prompt) з компільованого промпту —
    лишає Scene/стиль/safety-рядки. Межа блоку — до початку _SAFETY_SUFFIX (завжди йде одразу після
    глосарія, останнім part'ом). Якщо маркера нема (glossary="" чи старіший формат) — повертає як є."""
    start = prompt.find(_GLOSSARY_MARKER)
    if start == -1:
        return prompt
    end = prompt.find(_SAFETY_SUFFIX)
    return prompt[:start] + prompt[end:] if end != -1 else prompt[:start]


class FalImageProvider(ImageGenProvider):
    compact_prompts = True  # FLUX читає лише ~256 токенів: _visuals дає йому коротку версію (styles.build_compact_prompt)

    def __init__(self) -> None:
        key = os.environ.get("FAL_API_KEY")
        if not key:
            raise ProviderConfigError(
                "FAL_API_KEY не знайдено. Візьми ключ на https://fal.ai/dashboard/keys "
                "(і поповни баланс — fal.ai вимагає передоплату) і додай у .env."
            )
        self._key = key
        self._model = os.environ.get("FAL_IMAGE_MODEL") or _DEFAULT_MODEL
        self.cost_per_image_usd = _COST.get(self._model, 0.01)

    def generate_image(self, prompt: str, out_path: Path, references: list[Path] | None = None) -> Path:
        # references ігноруємо — FLUX schnell/dev не приймають референс-кадри тим самим multimodal-способом,
        # що Gemini (ImageGenProvider.generate_image це прямо дозволяє провайдерам, які так не вміють).
        # Довгий багатоетапний глосарій (styles.build_image_prompt) обрізаємо: підтверджено на job 12, що
        # FLUX при довгому промпті губить конкретну Scene і малює домінантний "історичний" стиль навіть
        # для сцен з явно іншою епохою (Scene уже містить достатньо деталей — glossary був лише довідкою
        # для LLM, яка писала Scene, повторне читання тут моделі лише заважає).
        prompt = _strip_glossary_block(prompt)
        payload = {"prompt": prompt, "image_size": "landscape_16_9", "num_images": 1}
        if "dev" in self._model or "pro" in self._model:
            payload["negative_prompt"] = _NEGATIVE_PROMPT
            payload["guidance_scale"] = 4

        response = requests.post(
            f"https://fal.run/{self._model}",
            headers={"Authorization": f"Key {self._key}", "Content-Type": "application/json"},
            json=payload,
            timeout=120,
        )
        if response.status_code != 200:
            raise ProviderConfigError(f"fal.ai ({self._model}) помилка {response.status_code}: {response.text[:200]}")
        data = response.json()
        images = data.get("images") or []
        if not images:
            raise ProviderConfigError(f"fal.ai не повернув зображення: {str(data)[:200]}")

        img_resp = requests.get(images[0]["url"], timeout=60)
        img_resp.raise_for_status()
        save_clean(Image.open(io.BytesIO(img_resp.content)), out_path)
        return out_path
