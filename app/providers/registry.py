"""Обирає конкретного провайдера за LLM_PROVIDER/TTS_PROVIDER/IMAGE_PROVIDER з .env.

Стадії пайплайна викликають лише ці три функції — ніколи не імпортують конкретний
провайдер напряму. Додати новий провайдер = новий файл у llm/, tts/ чи images/ +
один новий `elif` тут (жодних правок у stages/*).
"""

from ..config import BEATS_IMAGE_PROVIDER, IMAGE_PROVIDER, LLM_PROVIDER, TTS_PROVIDER, VIDEO_PROVIDER
from .base import ImageGenProvider, LLMProvider, ProviderConfigError, TTSProvider, VideoGenProvider


def get_llm_provider() -> LLMProvider:
    if LLM_PROVIDER == "stub":
        from .stub.llm import StubLLMProvider

        return StubLLMProvider()
    if LLM_PROVIDER == "anthropic":
        from .llm.anthropic_provider import AnthropicLLMProvider

        return AnthropicLLMProvider()
    raise ProviderConfigError(
        f"LLM_PROVIDER='{LLM_PROVIDER}' невідомий. Доступні значення: 'stub', 'anthropic'."
    )


def get_tts_provider() -> TTSProvider:
    if TTS_PROVIDER == "stub":
        from .stub.tts import StubTTSProvider

        return StubTTSProvider()
    if TTS_PROVIDER == "elevenlabs":
        from .tts.elevenlabs_provider import ElevenLabsTTSProvider

        return ElevenLabsTTSProvider()
    if TTS_PROVIDER == "edge":
        from .tts.edge_provider import EdgeTTSProvider

        return EdgeTTSProvider()
    raise ProviderConfigError(
        f"TTS_PROVIDER='{TTS_PROVIDER}' невідомий. Доступні значення: 'stub', 'elevenlabs', 'edge'."
    )


def _make_image_provider(name: str) -> ImageGenProvider:
    if name == "stub":
        from .stub.images import StubImageGenProvider

        return StubImageGenProvider()
    if name == "google":
        from .images.google_image import GoogleImageProvider

        return GoogleImageProvider()
    if name == "fal":
        from .images.fal_image import FalImageProvider

        return FalImageProvider()
    raise ProviderConfigError(f"IMAGE_PROVIDER='{name}' невідомий. Доступні значення: 'stub', 'google', 'fal'.")


def get_image_provider() -> ImageGenProvider:
    """"Важливий" провайдер: превью, весь анімований (Veo-стартові кадри), короткі still-сегменти
    (1 кадр). За дефолтом — google (Nano Banana), найкраще тримає стиль/композиційні заборони."""
    return _make_image_provider(IMAGE_PROVIDER)


def get_beats_image_provider() -> ImageGenProvider:
    """Дешевший провайдер для "беатів" — кількох кадрів одного довгого still-сегмента (app/stages/
    visual_generate.py): тут об'єм важливіший за ідеальне слідування стилю. За дефолтом той самий, що
    й get_image_provider() — BEATS_IMAGE_PROVIDER=fal у .env вмикає дешевший FLUX (fal.ai) саме тут."""
    return _make_image_provider(BEATS_IMAGE_PROVIDER)


def get_video_provider() -> VideoGenProvider | None:
    """None (VIDEO_PROVIDER=none) — анімованих кліпів немає, усі сцени йдуть як кадр + Ken Burns."""
    if VIDEO_PROVIDER == "none":
        return None
    if VIDEO_PROVIDER == "stub":
        from .stub.video import StubVideoGenProvider

        return StubVideoGenProvider()
    if VIDEO_PROVIDER == "google":
        from .video.google_video import GoogleVideoProvider

        return GoogleVideoProvider()
    raise ProviderConfigError(
        f"VIDEO_PROVIDER='{VIDEO_PROVIDER}' невідомий. Доступні значення: 'stub', 'google', 'none'."
    )
