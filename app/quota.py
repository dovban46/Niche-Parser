"""Облік використаних одиниць квоти YouTube Data API.

Google скидає денну квоту опівночі за тихоокеанським часом (America/Los_Angeles),
а не опівночі UTC чи в момент перезапуску цього сервера. Тому лічильник зберігається
у файлі (app/data/quota_state.json) і "переживає" перезапуски `uvicorn` протягом
доби — інакше після кожного рестарту здавалось би, що квота знову повна, хоча
насправді вона вже частково витрачена на рівні Google Cloud проєкту.

Це все одно лише орієнтовний індикатор для UI (Google — джерело правди), корисний
щоб не "влетіти" у quotaExceeded посеред пошуку.
"""

import json
import threading
from datetime import datetime, timezone
from pathlib import Path

try:
    from zoneinfo import ZoneInfo

    _QUOTA_TZ = ZoneInfo("America/Los_Angeles")
except Exception:
    # Немає бази часових поясів (напр. tzdata не встановлено) — рахуємо по UTC.
    # Це означає, що момент скидання лічильника може відрізнятись від реального
    # на кілька годин, але сам лічильник продовжує коректно накопичувати usage.
    _QUOTA_TZ = None

DEFAULT_DAILY_QUOTA = 10_000

_STATE_PATH = Path(__file__).resolve().parent / "data" / "quota_state.json"


def _today_key() -> str:
    now = datetime.now(_QUOTA_TZ) if _QUOTA_TZ else datetime.now(timezone.utc)
    return now.date().isoformat()


class QuotaTracker:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._date, self._used = self._load()

    def _load(self) -> tuple[str, int]:
        today = _today_key()
        try:
            raw = json.loads(_STATE_PATH.read_text(encoding="utf-8"))
            if raw.get("date") == today:
                return today, max(0, int(raw.get("used", 0)))
        except (OSError, ValueError, TypeError):
            pass
        return today, 0

    def _save(self) -> None:
        try:
            _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
            _STATE_PATH.write_text(
                json.dumps({"date": self._date, "used": self._used}), encoding="utf-8"
            )
        except OSError:
            pass

    def _roll_if_new_day_locked(self) -> None:
        today = _today_key()
        if today != self._date:
            self._date = today
            self._used = 0

    def add(self, units: int) -> None:
        with self._lock:
            self._roll_if_new_day_locked()
            self._used += units
            self._save()

    @property
    def used(self) -> int:
        with self._lock:
            self._roll_if_new_day_locked()
            return self._used

    @property
    def remaining(self) -> int:
        return max(0, DEFAULT_DAILY_QUOTA - self.used)

    def reset(self) -> None:
        with self._lock:
            self._used = 0
            self._save()


quota = QuotaTracker()
