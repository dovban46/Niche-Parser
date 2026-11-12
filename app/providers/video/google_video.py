"""Veo 3.1 Lite (Gemini API) — image-to-video: оживлює стартовий кадр у 4/6/8-секундний кліп.
Звук Veo не використовуємо (входить у ціну, але неконтрольований): мікшер звуку кладе власні шари."""

import os
import time
from pathlib import Path

from .._image_utils import model_input
from ..base import ProviderConfigError, VideoGenProvider
from ..google_client import call_with_retry, get_client

_DEFAULT_MODEL = "veo-3.1-lite-generate-preview"
_POLL_SECONDS = 10
_TIMEOUT_SECONDS = 900


class GoogleVideoProvider(VideoGenProvider):
    supported_durations = (4, 6, 8)
    cost_per_second_usd = 0.05  # Veo 3.1 Lite, 720p; 1080p = $0.08

    def __init__(self) -> None:
        self._client = get_client()
        self._model = os.environ.get("GOOGLE_VIDEO_MODEL") or _DEFAULT_MODEL
        self._resolution = os.environ.get("GOOGLE_VIDEO_RESOLUTION") or "720p"
        if self._resolution == "1080p":
            self.cost_per_second_usd = 0.08
        # Якщо реальні витрати в біллінгу відрізняються від прайс-листа — задай фактичну ціну секунди тут.
        if os.environ.get("GOOGLE_VIDEO_USD_PER_SEC"):
            self.cost_per_second_usd = float(os.environ["GOOGLE_VIDEO_USD_PER_SEC"])

    def generate_clip(self, prompt: str, start_image: Path, out_path: Path, duration_s: int) -> Path:
        from google.genai import types

        config = types.GenerateVideosConfig(
            aspect_ratio="16:9",
            resolution=self._resolution,
            duration_seconds=duration_s,
            person_generation="allow_adult",  # єдине значення, яке приймає image-to-video
            # negative_prompt Veo 3.1 Lite не підтримує (400) — заборони йдуть у сам текст промпту (styles.py).
            number_of_videos=1,
        )
        data, mime = model_input(start_image)  # кадри зберігаємо у WebP, а Veo приймає PNG/JPEG
        image = types.Image(image_bytes=data, mime_type=mime)

        operation = call_with_retry(
            lambda: self._client.models.generate_videos(model=self._model, prompt=prompt, image=image, config=config),
            f"відео {self._model}",
        )
        deadline = time.monotonic() + _TIMEOUT_SECONDS
        while not operation.done:
            if time.monotonic() > deadline:
                raise ProviderConfigError(f"Veo не завершив генерацію за {_TIMEOUT_SECONDS // 60} хв (операція {operation.name}).")
            time.sleep(_POLL_SECONDS)
            operation = call_with_retry(lambda: self._client.operations.get(operation), "статус відео")

        if operation.error:
            raise ProviderConfigError(f"Veo повернув помилку: {str(operation.error)[:300]}")
        response = operation.response
        videos = getattr(response, "generated_videos", None) or []
        if not videos:
            reasons = getattr(response, "rai_media_filtered_reasons", None) or []
            raise ProviderConfigError(
                "Veo не згенерував кліп: " + (f"спрацював фільтр безпеки ({'; '.join(map(str, reasons))})" if reasons
                                              else "порожня відповідь (ймовірно, фільтр безпеки)")
            )

        video = videos[0].video
        out_path.parent.mkdir(parents=True, exist_ok=True)
        call_with_retry(lambda: self._client.files.download(file=video), "завантаження кліпу")
        video.save(str(out_path))
        return out_path
