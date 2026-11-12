"""Збирає pydantic-моделі (schemas.py) з сирих рядків repository.py + рахує прогрес,
формує URL до артефактів у /storage. HTTP-роути (main.py) працюють тільки через цей модуль."""

import json
import shutil

from .. import dossier as dossier_mod
from ..config import IMAGE_PROVIDER, LLM_PROVIDER, STORAGE_ROOT, TTS_PROVIDER, VIDEO_PROVIDER, VIDEOS_ROOT
from ..providers.base import ProviderConfigError
from ..providers.registry import get_llm_provider, get_tts_provider
from ..providers.tts.voices import PREVIEW_TEXT, voice_name, voices_for
from ..schemas import (
    STAGE_LABELS,
    STAGE_ORDER,
    JobDetail,
    JobStageView,
    JobSummary,
    QaIssueView,
    SegmentView,
)
from ..storage import JobStorage
from . import repository as repo
from .runner import enqueue_job


def _read_script_text(job_id: int) -> str | None:
    """Повний (не розбитий на сегменти) поточний текст сценарію — після редактури,
    якщо вона вже пройшла, інакше чернетка, якщо є хоч вона."""
    storage = JobStorage(job_id)
    reviewed = storage.script_dir() / "reviewed_final.md"
    if reviewed.exists():
        return reviewed.read_text(encoding="utf-8")
    draft = storage.script_dir() / "draft_v1.md"
    if draft.exists():
        return draft.read_text(encoding="utf-8")
    return None


def _read_glossary(job_id: int) -> str | None:
    path = JobStorage(job_id).script_dir() / "visual_glossary.txt"
    return path.read_text(encoding="utf-8").strip() if path.exists() else None


def _storage_url(relative_path: str | None) -> str | None:
    if not relative_path:
        return None
    return f"/storage/{relative_path}"


def _progress(stages: list[dict]) -> tuple[int, int]:
    done = sum(1 for s in stages if s["status"] in ("success", "skipped"))
    return done, len(STAGE_ORDER)


def _video_url(relative_path: str | None) -> str | None:
    """final_video_path — відносно VIDEOS_ROOT (готові відео лежать окремо від storage/)."""
    if not relative_path:
        return None
    return f"/videos/{relative_path}"


def _voice_name_for(job: dict) -> str | None:
    provider = json.loads(job["config_json"]).get("tts_provider", TTS_PROVIDER)
    return voice_name(provider, job["language"], job["voice_id"])


def create_job(
    topic: str,
    niche: str,
    target_duration_minutes: int,
    language: str,
    voice_id: str | None = None,
    style_id: str | None = None,
    preview_seconds: int | None = None,
    auto_dossier: bool = False,
) -> int:
    config = {
        "llm_provider": LLM_PROVIDER,
        "tts_provider": TTS_PROVIDER,
        "image_provider": IMAGE_PROVIDER,
        "video_provider": VIDEO_PROVIDER,
    }
    job_id = repo.create_job(
        topic=topic,
        niche=niche,
        target_duration_minutes=target_duration_minutes,
        language=language,
        config=config,
        voice_id=voice_id,
        style_id=style_id,
        preview_seconds=preview_seconds,
        dossier_approved=auto_dossier,
    )
    enqueue_job(job_id)
    return job_id


def list_voices(language: str) -> dict:
    return {"provider": TTS_PROVIDER, "voices": voices_for(TTS_PROVIDER, language)}


def preview_voice(language: str, voice_id: str | None) -> str:
    """Коротка проба голосу для вибору в UI. Кешується на диску за (провайдер, мова, голос) —
    платний провайдер синтезує кожну пару лише один раз, повторні прослуховування безкоштовні."""
    if TTS_PROVIDER == "stub":
        raise ProviderConfigError("TTS_PROVIDER=stub не має голосів — обери elevenlabs або edge у .env.")
    tts = get_tts_provider()
    resolved = tts.resolve_voice(language, voice_id)
    out_path = STORAGE_ROOT / "voice_previews" / f"{TTS_PROVIDER}_{language}_{resolved}.{tts.file_extension}"
    if not out_path.exists():
        tts.synthesize(PREVIEW_TEXT[language], out_path, language, resolved)
    return f"/storage/voice_previews/{out_path.name}"


class JobBusyError(Exception):
    """Job зараз обробляється воркером — видаляти файли з-під нього не можна."""


class JobDeleteError(Exception):
    """Не вдалося прибрати файли job'а з диска (напр. файл відкритий програвачем)."""


def delete_job(job_id: int) -> bool:
    """Повне видалення: файли job'а (storage/jobs/{id}), готове відео у videos/ і рядки БД.
    Спершу диск, потім БД — якщо файли не вдалося прибрати, job лишається в списку й
    видалення можна повторити, а не зависає "привидом" на диску без запису в БД."""
    job = repo.get_job(job_id)
    if job is None:
        return False
    if job["status"] == "running":
        raise JobBusyError("Job зараз виконується — дочекайся завершення чи паузи й спробуй ще раз.")

    targets = [JobStorage(job_id).job_root]
    if job["final_video_path"]:
        video = (VIDEOS_ROOT / job["final_video_path"]).resolve()
        videos_root = VIDEOS_ROOT.resolve()
        # Повні відео тепер лежать у власній підпапці "{id}_{slug}/" разом із превью й metadata.txt
        # (video_assemble.py) — видаляємо всю папку. Старі job'и (плоский файл прямо в VIDEOS_ROOT)
        # лишаються сумісними: тоді video.parent == videos_root, і видаляється лише сам файл.
        target = video.parent if video.parent != videos_root else video
        if target.is_relative_to(videos_root):
            targets.append(target)

    try:
        for path in targets:
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink(missing_ok=True)
    except OSError as exc:
        raise JobDeleteError(f"Не вдалося видалити файли з диска ({exc}). Закрий програвачі й спробуй ще раз.") from exc

    repo.delete_job(job_id)
    return True


def _to_summary(job: dict) -> JobSummary:
    stages = repo.list_stages(job["id"])
    done, total = _progress(stages)
    return JobSummary(
        id=job["id"],
        created_at=job["created_at"],
        updated_at=job["updated_at"],
        topic=job["topic"],
        niche=job["niche"],
        language=job["language"],
        voice_id=job["voice_id"],
        voice_name=_voice_name_for(job),
        style_id=job.get("style_id"),
        preview_seconds=job.get("preview_seconds"),
        target_duration_minutes=job["target_duration_minutes"],
        status=job["status"],
        current_stage=job["current_stage"],
        progress_done=done,
        progress_total=total,
    )


def list_jobs() -> list[JobSummary]:
    return [_to_summary(j) for j in repo.list_jobs()]


def get_job_detail(job_id: int) -> JobDetail | None:
    job = repo.get_job(job_id)
    if job is None:
        return None

    stage_rows = repo.list_stages(job_id)
    stages = [
        JobStageView(
            stage_name=s["stage_name"],
            stage_label=STAGE_LABELS.get(s["stage_name"], s["stage_name"]),
            stage_order=s["stage_order"],
            status=s["status"],
            attempt=s["attempt"],
            started_at=s["started_at"],
            finished_at=s["finished_at"],
            output=json.loads(s["output_json"]) if s["output_json"] else None,
            error_message=s["error_message"],
        )
        for s in stage_rows
    ]

    segment_rows = repo.list_segments(job_id)
    segments = [
        SegmentView(
            index=s["segment_index"],
            text=s["text"],
            visual_keywords=s["visual_keywords"],
            suggested_source=s["suggested_source"],
            start_ms=s["start_ms"],
            duration_ms=s["duration_ms"],
            audio_url=_storage_url(s["audio_path"]),
            shot=s["shot_prompt"],
            motion=s["motion_prompt"],
            visual_type=s["visual_type"] or "still",
            clip_url=_storage_url(s["visual_clip_path"]),
            sfx=json.loads(s["sfx_tags"] or "[]"),
            ambience=s["ambience_tag"] or None,
            cta=bool(s["is_cta"]),
            pause_seconds=s["pause_seconds"],
            visual_source=s["visual_source"],
            visual_url=_storage_url(s["visual_path"]),
            visual_provider=s["visual_provider"],
            visual_license=s["visual_license"],
            status=s["status"],
        )
        for s in segment_rows
    ]

    issue_rows = repo.list_qa_issues(job_id)
    qa_issues = [
        QaIssueView(
            issue_type=i["issue_type"],
            start_sec=i["start_sec"],
            end_sec=i["end_sec"],
            severity=i["severity"],
            resolution=i["resolution"],
            notes=i["notes"],
        )
        for i in issue_rows
    ]

    done, total = _progress(stage_rows)
    return JobDetail(
        id=job["id"],
        created_at=job["created_at"],
        updated_at=job["updated_at"],
        topic=job["topic"],
        niche=job["niche"],
        language=job["language"],
        voice_id=job["voice_id"],
        voice_name=_voice_name_for(job),
        style_id=job.get("style_id"),
        preview_seconds=job.get("preview_seconds"),
        target_duration_minutes=job["target_duration_minutes"],
        status=job["status"],
        current_stage=job["current_stage"],
        progress_done=done,
        progress_total=total,
        error_message=job["error_message"],
        visual_glossary=_read_glossary(job_id),
        dossier=dossier_mod.read_dossier(JobStorage(job_id)) or None,
        dossier_approved=bool(job["dossier_approved"]),
        estimated_cost_usd=round(sum((s.output or {}).get("estimated_cost_usd", 0) for s in stages), 3),
        final_video_url=_video_url(job["final_video_path"]),
        script_approved=bool(job["script_approved"]),
        script_text=_read_script_text(job_id),
        stages=stages,
        segments=segments,
        qa_issues=qa_issues,
    )


def retry_job(job_id: int) -> bool:
    """Скидає failed-стадію(ї) на pending і повертає job у чергу. Успішні стадії лишаються
    success — resume-логіка pipeline.run_job просто продовжить з місця зупинки."""
    job = repo.get_job(job_id)
    if job is None:
        return False

    for stage in repo.list_stages(job_id):
        if stage["status"] in ("failed", "running"):
            repo.update_stage(job_id, stage["stage_name"], status="pending", error=None)

    repo.update_job(job_id, status="pending", error_message=None)
    enqueue_job(job_id)
    return True


def save_dossier(job_id: int, text: str) -> bool:
    """Зберігає правки автора в досьє (лише поки job чекає на його перевірку)."""
    job = repo.get_job(job_id)
    if job is None or job["status"] != "awaiting_review" or job["current_stage"] != "research_dossier":
        return False
    dossier_mod.dossier_path(JobStorage(job_id)).write_text(text.strip(), encoding="utf-8")
    repo.update_job(job_id, status="awaiting_review")  # оновлює updated_at
    return True


def approve_dossier(job_id: int) -> bool:
    """Автор схвалив досьє — знімає паузу; конвеєр продовжить зі сценарію."""
    job = repo.get_job(job_id)
    if job is None or job["status"] != "awaiting_review" or job["current_stage"] != "research_dossier":
        return False
    repo.set_dossier_approved(job_id, True)
    repo.update_job(job_id, status="pending")
    enqueue_job(job_id)
    return True


def approve_script(job_id: int) -> bool:
    """Користувач задоволений сценарієм — знімає чек-поінт і повертає job у чергу
    (pipeline.run_job продовжить із сегментації, script_generate/review вже 'success')."""
    job = repo.get_job(job_id)
    if job is None or job["status"] != "awaiting_review" or job["current_stage"] != "script_review":
        return False
    repo.set_script_approved(job_id, True)
    repo.update_job(job_id, status="pending")
    enqueue_job(job_id)
    return True


def revise_script(job_id: int, feedback: str) -> str:
    """Точкова правка сценарію за фідбеком користувача — синхронний виклик (не через
    чергу): один LLM-виклик, результат потрібен одразу для показу в UI. Job лишається
    в 'awaiting_review' — це та сама зупинка, просто з оновленим текстом."""
    job = repo.get_job(job_id)
    if job is None or job["status"] != "awaiting_review" or job["current_stage"] != "script_review":
        raise ValueError("Job не в стані очікування перевірки сценарію.")

    current_text = _read_script_text(job_id)
    if current_text is None:
        raise ValueError("Немає збереженого сценарію для правки.")

    llm = get_llm_provider()
    brief = dossier_mod.for_script(dossier_mod.read_dossier(JobStorage(job_id)))
    revised = llm.revise_script(current_text, feedback, job["language"], brief)

    storage = JobStorage(job_id)
    (storage.script_dir() / "reviewed_final.md").write_text(revised, encoding="utf-8")
    repo.update_job(job_id, status="awaiting_review")  # оновлює updated_at
    return revised
