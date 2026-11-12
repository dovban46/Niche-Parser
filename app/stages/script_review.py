from .. import dossier
from ..providers.registry import get_llm_provider
from .base import StageContext, StageResult


class ScriptReviewStage:
    name = "script_review"

    def run(self, ctx: StageContext) -> StageResult:
        draft_path = ctx.storage.script_dir() / "draft_v1.md"
        if not draft_path.exists():
            return StageResult(status="failed", error="draft_v1.md не знайдено — script_generate не завершився?")

        draft = draft_path.read_text(encoding="utf-8")
        llm = get_llm_provider()
        reviewed = llm.review_script(draft, ctx.job["language"], dossier.for_script(dossier.read_dossier(ctx.storage)))

        path = ctx.storage.script_dir() / "reviewed_final.md"
        path.write_text(reviewed, encoding="utf-8")

        return StageResult(
            status="success",
            output={"script_path": ctx.storage.relative(path), "word_count": len(reviewed.split())},
        )
