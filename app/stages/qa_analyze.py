from .base import StageContext, StageResult


class QaAnalyzeStage:
    """У цій ітерації аналізує маніфест збірки (структурні пропуски: відсутнє аудіо/візуал,
    нульова тривалість), а не реальний відеофайл. Справжній ffmpeg-аналіз (blackdetect/
    freezedetect/silencedetect) підключиться разом із video_assemble на наступному кроці —
    контракт стадії (список issues у БД) лишиться тим самим."""

    name = "qa_analyze"

    def run(self, ctx: StageContext) -> StageResult:
        segments = [s for s in ctx.repo.list_segments(ctx.job_id) if s["status"] != "skipped"]
        issues_found = 0

        for seg in segments:
            if seg["visual_type"] == "animated" and seg["visual_path"] and not seg["visual_clip_path"]:
                ctx.repo.add_qa_issue(
                    ctx.job_id,
                    segment_id=seg["id"],
                    issue_type="missing_clip",
                    severity="warning",
                    notes=f"Сегмент {seg['segment_index']} мав бути анімованим, але кліп не згенеровано "
                    "(фільтр безпеки чи помилка API) — іде як кадр + Ken Burns. Деталі: стадія 'Генерація візуалу'.",
                )
                issues_found += 1
            if not seg["audio_path"]:
                ctx.repo.add_qa_issue(
                    ctx.job_id,
                    segment_id=seg["id"],
                    issue_type="missing_audio",
                    severity="error",
                    notes=f"Сегмент {seg['segment_index']} без озвучки.",
                )
                issues_found += 1
            if not seg["visual_path"]:
                ctx.repo.add_qa_issue(
                    ctx.job_id,
                    segment_id=seg["id"],
                    issue_type="missing_visual",
                    severity="error",
                    notes=f"Сегмент {seg['segment_index']} без візуалу.",
                )
                issues_found += 1
            if not seg["duration_ms"]:
                ctx.repo.add_qa_issue(
                    ctx.job_id,
                    segment_id=seg["id"],
                    issue_type="zero_duration",
                    severity="warning",
                    notes=f"Сегмент {seg['segment_index']} має нульову тривалість.",
                )
                issues_found += 1

        status = "needs_review" if issues_found else "success"
        return StageResult(status=status, output={"issues_found": issues_found})
