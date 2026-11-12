from .. import dossier
from ..providers.registry import get_llm_provider
from .base import StageContext, StageResult


class ScriptGenerateStage:
    name = "script_generate"

    def run(self, ctx: StageContext) -> StageResult:
        llm = get_llm_provider()
        brief = dossier.for_script(dossier.read_dossier(ctx.storage))
        script = llm.generate_script(
            ctx.job["topic"], ctx.job["target_duration_minutes"], ctx.job["language"], brief
        )

        path = ctx.storage.script_dir() / "draft_v1.md"
        path.write_text(script, encoding="utf-8")

        return StageResult(
            status="success",
            output={"script_path": ctx.storage.relative(path), "word_count": len(script.split())},
        )
