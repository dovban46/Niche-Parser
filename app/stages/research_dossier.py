from .. import dossier
from ..providers.registry import get_llm_provider
from .base import StageContext, StageResult


class ResearchDossierStage:
    """Поверхнева перевірка теми ПЕРЕД сценарієм (один недорогий LLM-виклик): що це за тема, чи немає хибних
    припущень, ключові факти, сторони й тактика, візуальний гід і заборонені анахронізми. Після стадії конвеєр
    зупиняється: автор правит/схвалює досьє. Ідемпотентна — наявне досьє (у т.ч. з правками) не перезаписується."""

    name = "research_dossier"

    def run(self, ctx: StageContext) -> StageResult:
        path = dossier.dossier_path(ctx.storage)
        text = dossier.read_dossier(ctx.storage)
        if not text:
            text = get_llm_provider().build_dossier(ctx.job["topic"], ctx.job["niche"]).strip()
            path.write_text(text, encoding="utf-8")
            if dossier.topic_needs_attention(text) and ctx.job["dossier_approved"]:
                # Хибна/двозначна тема — зупиняємось, навіть якщо ввімкнено автосхвалення.
                ctx.repo.set_dossier_approved(ctx.job_id, False)

        return StageResult(
            status="success",
            output={
                "dossier_path": ctx.storage.relative(path),
                "word_count": len(text.split()),
                "needs_attention": dossier.topic_needs_attention(text),
                "accent_colour": dossier.accent_color(text),
            },
        )
