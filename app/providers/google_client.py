"""Спільна частина Google-провайдерів (картинки Nano Banana + відео Veo): один ключ, один клієнт,
єдиний перекладач помилок SDK у ProviderConfigError і повтор на тимчасових збоях."""

import mimetypes
import os
import time
from pathlib import Path

from .base import ProviderConfigError

_TRANSIENT_CODES = {429, 500, 502, 503, 504}
_RETRY_DELAYS = (5, 15, 40)


def get_client():
    api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ProviderConfigError(
            "GOOGLE_API_KEY не знайдено. Створи ключ у https://aistudio.google.com/apikey, увімкни оплату "
            "(Veo і Nano Banana лише на платному тарифі) і додай у .env (див. .env.example)."
        )
    try:
        from google import genai
    except ImportError as exc:  # pragma: no cover
        raise ProviderConfigError("Пакет google-genai не встановлено: pip install -r requirements.txt") from exc
    return genai.Client(api_key=api_key)


def mime_for(path: Path) -> str:
    return mimetypes.guess_type(str(path))[0] or "image/png"


def _quota_blocked(exc: Exception) -> bool:
    """429 із free_tier / "limit: 0" — проєкт на безкоштовному тарифі без квоти для цієї моделі (оплата не
    ввімкнена). Це не тимчасовий збій: повторювати марно."""
    text = (getattr(exc, "message", None) or str(exc)).lower()
    return getattr(exc, "code", None) == 429 and ("free_tier" in text or "limit: 0" in text)


def call_with_retry(fn, what: str):
    """Виконує fn(); на 429/5xx повторює з паузами, решту помилок API перекладає людською мовою."""
    from google.genai import errors

    last: Exception | None = None
    for attempt in range(len(_RETRY_DELAYS) + 1):
        try:
            return fn()
        except errors.APIError as exc:
            last = exc
            if (getattr(exc, "code", None) in _TRANSIENT_CODES and not _quota_blocked(exc)
                    and attempt < len(_RETRY_DELAYS)):
                time.sleep(_RETRY_DELAYS[attempt])
                continue
            break
    code = getattr(last, "code", "?")
    message = getattr(last, "message", None) or str(last)
    hint = ""
    if last is not None and _quota_blocked(last):
        message = "квота безкоштовного тарифу для цієї моделі = 0"
        hint = (" Проєкт на free tier: у Google AI Studio -> Billing підключи оплату й поповни баланс (paid tier), "
                "після цього повтори.")
    elif code in (401, 403):
        hint = " Перевір ключ і що в Google AI Studio ввімкнено оплату (paid tier)."
    elif code == 404:
        hint = " Модель недоступна для цього ключа — запусти `python -m app.tools.check_google`."
    raise ProviderConfigError(f"Google API ({what}) помилка {code}: {message[:300]}.{hint}") from last
