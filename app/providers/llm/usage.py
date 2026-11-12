"""Облік реального використання Anthropic API (токени + орієнтовна вартість) за час
роботи процесу. На відміну від app/quota.py в сусідньому parser — не персистентний
на диску (тут головне — швидко порахувати вартість конкретного тестового прогону,
а не пильнувати денний ліміт), скидається при рестарті сервера.
"""

import threading

# $ за 1M токенів (див. app/providers/llm/anthropic_provider.py _DEFAULT_MODEL)
_PRICING_PER_MILLION = {
    "claude-sonnet-5": {"input": 2.00, "output": 10.00},
    "claude-opus-5": {"input": 5.00, "output": 25.00},
    "claude-haiku-4-5": {"input": 1.00, "output": 5.00},
}
_DEFAULT_PRICING = _PRICING_PER_MILLION["claude-sonnet-5"]


class _UsageTracker:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._calls = 0
        self._input_tokens = 0
        self._output_tokens = 0
        self._cost_usd = 0.0

    def record(self, model: str, input_tokens: int, output_tokens: int) -> None:
        pricing = _PRICING_PER_MILLION.get(model, _DEFAULT_PRICING)
        cost = (input_tokens * pricing["input"] + output_tokens * pricing["output"]) / 1_000_000
        with self._lock:
            self._calls += 1
            self._input_tokens += input_tokens
            self._output_tokens += output_tokens
            self._cost_usd += cost

    def summary(self) -> dict:
        with self._lock:
            return {
                "calls": self._calls,
                "input_tokens": self._input_tokens,
                "output_tokens": self._output_tokens,
                "estimated_cost_usd": round(self._cost_usd, 4),
            }


usage_tracker = _UsageTracker()
