from ..providers.registry import get_image_provider, get_tts_provider
from ._visuals import generate_segment_image, load_glossary
from .base import StageContext, StageResult
from .tts_synthesize import job_voice

# Свідомо обмежений список: автоматично лагодимо лише те, що однозначно прив'язане
# до одного сегмента і має очевидний "рецепт" виправлення (перегенерувати саме цей
# шматок). Усе інше (напр. проблеми гучності/кліпінг, коли підключимо реальний звук)
# краще позначити для ручного перегляду, ніж "наосліп" виправляти автоматично.
_AUTO_FIXABLE = {"missing_audio", "missing_visual"}


class QaAutofixStage:
    name = "qa_autofix"

    def run(self, ctx: StageContext) -> StageResult:
        issues = [i for i in ctx.repo.list_qa_issues(ctx.job_id) if i["resolution"] == "unresolved"]
        if not issues:
            return StageResult(status="success", output={"fixed": 0, "flagged": 0})

        segments_by_id = {s["id"]: s for s in ctx.repo.list_segments(ctx.job_id)}
        tts = get_tts_provider()
        image_gen = get_image_provider()
        voice = job_voice(ctx)
        glossary = load_glossary(ctx)

        fixed, flagged = 0, 0

        for issue in issues:
            seg = segments_by_id.get(issue["segment_id"])
            if issue["issue_type"] not in _AUTO_FIXABLE or seg is None:
                self._flag(ctx, issue)
                flagged += 1
                continue

            try:
                if issue["issue_type"] == "missing_audio":
                    out_path = ctx.storage.audio_dir() / f"segment_{seg['segment_index']:04d}.{tts.file_extension}"
                    duration_ms = tts.synthesize(seg["text"], out_path, ctx.job["language"], voice)
                    ctx.repo.update_segment(
                        ctx.job_id,
                        seg["segment_index"],
                        audio_path=ctx.storage.relative(out_path),
                        duration_ms=duration_ms,
                    )
                elif issue["issue_type"] == "missing_visual":
                    out_path, prompt = generate_segment_image(ctx, seg, image_gen, glossary)
                    ctx.repo.update_segment(
                        ctx.job_id,
                        seg["segment_index"],
                        visual_path=ctx.storage.relative(out_path),
                        visual_prompt=prompt,
                        visual_source="generated_image",
                        status="ready",
                    )
                self._resolve(ctx, issue, "auto_fixed")
                fixed += 1
            except Exception:
                self._flag(ctx, issue)
                flagged += 1

        status = "success" if flagged == 0 else "needs_review"
        return StageResult(status=status, output={"fixed": fixed, "flagged": flagged})

    @staticmethod
    def _resolve(ctx: StageContext, issue: dict, resolution: str) -> None:
        # add_qa_issue не має update — найпростіше зробити прямий UPDATE через repo-модуль.
        ctx.repo.resolve_qa_issue(issue["id"], resolution)

    @staticmethod
    def _flag(ctx: StageContext, issue: dict) -> None:
        ctx.repo.resolve_qa_issue(issue["id"], "flagged_for_review")
