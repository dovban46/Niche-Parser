"""Впорядкований список стадій і сам runner одного job'а. Викликається з jobs/runner.py
у фоновому потоці — ніколи напряму з HTTP-хендлера (щоб не блокувати запит)."""

import json
import logging
import time

from ..config import STAGE_RETRY_ATTEMPTS, STAGE_RETRY_BACKOFF_SECONDS
from ..stages.base import StageContext, StageResult
from ..stages.metadata_generate import MetadataGenerateStage
from ..stages.qa_analyze import QaAnalyzeStage
from ..stages.qa_autofix import QaAutofixStage
from ..stages.research_dossier import ResearchDossierStage
from ..stages.script_generate import ScriptGenerateStage
from ..stages.script_review import ScriptReviewStage
from ..stages.tts_synthesize import TtsSynthesizeStage
from ..stages.video_assemble import VideoAssembleStage
from ..stages.visual_generate import VisualGenerateStage
from ..stages.visual_plan import VisualPlanStage
from ..storage import JobStorage
from . import repository as repo

logger = logging.getLogger("video_factory.pipeline")

# Порядок відповідає schemas.STAGE_ORDER — тримати синхронізованим.
STAGES = [
    ResearchDossierStage(),
    ScriptGenerateStage(),
    ScriptReviewStage(),
    VisualPlanStage(),
    TtsSynthesizeStage(),
    VisualGenerateStage(),
    VideoAssembleStage(),
    QaAnalyzeStage(),
    QaAutofixStage(),
    MetadataGenerateStage(),
]

# Стадії, що реально звертаються до мережевих провайдерів — лише вони отримують ретраї
# з backoff. ffmpeg/локальні стадії або миттєво успішні, або детерміновано валяться
# (повторення без змін вхідних даних їх не врятує).
_NETWORK_STAGES = {
    "research_dossier",
    "script_generate",
    "script_review",
    "visual_plan",
    "tts_synthesize",
    "visual_generate",
    "metadata_generate",
}

# Після цих стадій пайплайн зупиняється й чекає на ручне підтвердження автора (прапорець у jobs):
# досьє (перш ніж витрачати токени на сценарій) і сценарій (перш ніж платити за озвучку, кадри, кліпи).
CHECKPOINTS = {"research_dossier": "dossier_approved", "script_review": "script_approved"}


def run_job(job_id: int) -> None:
    job = repo.get_job(job_id)
    if job is None:
        logger.error("run_job: job %s не знайдено", job_id)
        return

    storage = JobStorage(job_id)
    storage.ensure_dirs()
    repo.update_job(job_id, status="running", error_message=None)
    config = json.loads(job["config_json"])

    for stage in STAGES:
        stage_row = repo.get_stage(job_id, stage.name)
        if stage_row and stage_row["status"] == "success":
            continue  # resume: стадія вже виконана раніше

        # Ручна зупинка перед платною генерацією візуалів (кадри й Veo-кліпи — головна стаття витрат): якщо в
        # теці job'а лежить файл HOLD_VISUALS, пайплайн стає на awaiting_review. Зняти: видалити файл і
        # POST /api/jobs/{id}/retry. Дає змогу перевірити зразки кадрів/промптів до того, як платити за всі.
        if stage.name == "visual_generate" and (storage.job_root / "HOLD_VISUALS").exists():
            repo.update_job(job_id, status="awaiting_review", current_stage=stage.name)
            return

        repo.update_stage(job_id, stage.name, status="running", increment_attempt=True, mark_started=True)
        repo.update_job(job_id, current_stage=stage.name)

        current_job = repo.get_job(job_id)
        ctx = StageContext(job=current_job, repo=repo, storage=storage, config=config)

        result = _run_with_retry(stage, ctx)

        repo.update_stage(
            job_id,
            stage.name,
            status=result.status,
            output=result.output,
            error=result.error,
            mark_finished=True,
        )

        if result.status == "failed":
            repo.update_job(job_id, status="failed", error_message=f"{stage.name}: {result.error}")
            return

        if result.status == "needs_review":
            repo.update_job(job_id, status="needs_review")
            # MVP: пайплайн все одно триває до кінця (метадані все одно потрібні для огляду) —
            # фінальний статус нижче не перезатре 'needs_review' на 'completed'.
            if stage.name == "tts_synthesize":
                # Не всі сегменти озвучені (напр. закінчились кредити ElevenLabs): далі йти не можна, бо візуали й
                # монтаж без повного аудіо дадуть биту відео й марні витрати. Після усунення причини: /retry
                # (озвучені сегменти повторно не оплачуються: tts_synthesize їх пропускає).
                return

        checkpoint_flag = CHECKPOINTS.get(stage.name)
        if checkpoint_flag and result.status != "failed":
            current_job = repo.get_job(job_id)
            if not current_job[checkpoint_flag]:
                repo.update_job(job_id, status="awaiting_review", current_stage=stage.name)
                return  # зупинка тут — продовжить схвалення в UI через enqueue_job()

    final_job = repo.get_job(job_id)
    if final_job["status"] != "needs_review":
        repo.update_job(job_id, status="completed", current_stage=None)


def _run_with_retry(stage, ctx: StageContext) -> StageResult:
    if stage.name not in _NETWORK_STAGES:
        return _safe_run(stage, ctx)

    last_result: StageResult | None = None
    for attempt in range(STAGE_RETRY_ATTEMPTS):
        last_result = _safe_run(stage, ctx)
        if last_result.status != "failed":
            return last_result
        if attempt < len(STAGE_RETRY_BACKOFF_SECONDS):
            time.sleep(STAGE_RETRY_BACKOFF_SECONDS[attempt])
    return last_result


def _safe_run(stage, ctx: StageContext) -> StageResult:
    try:
        return stage.run(ctx)
    except Exception as exc:  # стадія не мала кинути виняток, але про всяк — не валимо воркер
        logger.exception("Стадія %s впала з винятком", stage.name)
        return StageResult(status="failed", error=f"{type(exc).__name__}: {exc}")
