"""Простий облік використаних одиниць квоти YouTube Data API за час роботи сервера.

Ліміт квоти видається на добу (типово 10 000 unit) на рівні Google Cloud проєкту,
а не на рівні цього процесу, тому цей лічильник — орієнтовний індикатор для UI,
а не джерело правди про залишок квоти.
"""

import threading

DEFAULT_DAILY_QUOTA = 10_000


class QuotaTracker:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._used = 0

    def add(self, units: int) -> None:
        with self._lock:
            self._used += units

    @property
    def used(self) -> int:
        return self._used

    def reset(self) -> None:
        with self._lock:
            self._used = 0


quota = QuotaTracker()
