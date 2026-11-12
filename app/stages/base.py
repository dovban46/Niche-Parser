"""Контракт стадії пайплайна. Кожна стадія в app/stages/*.py реалізує Stage:
має атрибут `name` (збігається з job_stages.stage_name) і метод run(ctx) -> StageResult.

Стадія НІКОЛИ не звертається до попередньої стадії напряму — лише читає стан із
ctx.repo (БД) і файлів у ctx.storage. Це дає безкоштовний resume: повторний виклик
run() для вже частково виконаної стадії просто продовжує з того, що знайшов на диску/в БД.
"""

from dataclasses import dataclass
from types import ModuleType
from typing import Any, Literal, Protocol

from ..storage import JobStorage

StageStatus = Literal["success", "failed", "needs_review"]


@dataclass
class StageResult:
    status: StageStatus
    output: dict[str, Any] | None = None
    error: str | None = None


class StageContext:
    """Усе, що потрібно стадії: поточний job (dict-рядок із БД), repository-модуль для
    читання/запису стану (app.jobs.repository), storage для шляхів файлів, і config job'а
    (обрані провайдери)."""

    def __init__(self, job: dict, repo: ModuleType, storage: JobStorage, config: dict):
        self.job = job
        self.repo = repo
        self.storage = storage
        self.config = config

    @property
    def job_id(self) -> int:
        return self.job["id"]


class Stage(Protocol):
    name: str

    def run(self, ctx: StageContext) -> StageResult: ...
