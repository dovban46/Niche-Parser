import json
import shutil
from pathlib import Path

from PIL import Image

from .. import chapters, dossier, thumbnails, title_lint
from ..config import IMAGE_PROVIDER, VIDEOS_ROOT
from ..providers._image_utils import trim_paper_border
from ..providers.registry import get_image_provider, get_llm_provider
from ..styles import style_reference_images
from . import _visuals as v
from .base import StageContext, StageResult

# колір останнього слова прев'ю збігається з акцентним світінням об'єкта (його називає концепція в subject)
_GLOW_COLORS = {"cyan": (60, 225, 255), "gold": (255, 200, 61), "red": (255, 72, 56)}
_THUMBNAIL_VARIANTS = 3  # РІЗНІ концепції (об'єкт+текст) для A/B-тесту «Test & compare» у Studio


def _metadata_txt(title_options: list[str], description: str, tags: list[str], pinned: str = "") -> str:
    lines = ["ВАРІАНТИ НАЗВИ", "=" * 14]
    lines += [f"{i}. {t}" for i, t in enumerate(title_options, 1)]
    lines += ["", "ОПИС", "=" * 4, description, "", f"ТЕГИ ({len(chr(44).join(tags))} із 500 символів)", "=" * 4, ", ".join(tags)]
    return "\n".join(lines)


def _package_output(ctx: StageContext, title_options: list[str], description: str, tags: list[str],
                     thumb_paths: list[str], pinned: str = "") -> None:
    """Складає видачу одного відео в ОДНУ папку videos/{id}_{slug}/: сам mp4 (уже лежить там від
    video_assemble), фінальні варіанти прев'ю (без проміжних _bg/_text) і txt із назвами/описом/тегами —
    щоб публікувати відео можна було, відкривши лише цю папку, без storage/jobs/{id}/."""
    final_video_path = ctx.job.get("final_video_path")
    if not final_video_path:
        return
    job_dir = (VIDEOS_ROOT / final_video_path).resolve().parent
    if not job_dir.is_relative_to(VIDEOS_ROOT.resolve()) or job_dir == VIDEOS_ROOT.resolve():
        return  # старий job (плоский файл прямо в VIDEOS_ROOT) — нема куди пакувати
    for i, rel in enumerate(thumb_paths, 1):
        src = ctx.storage.metadata_dir() / "thumbnails" / Path(rel).name
        if src.is_file():
            shutil.copyfile(src, job_dir / f"thumbnail_{i}{src.suffix}")
    (job_dir / "metadata.txt").write_text(_metadata_txt(title_options, description, tags, pinned), encoding="utf-8")


class MetadataGenerateStage:
    name = "metadata_generate"

    def run(self, ctx: StageContext) -> StageResult:
        if ctx.job.get("preview_seconds"):
            return StageResult(status="success", output={"skipped": "тест-режим: метадані не генеруються (економія токенів)"})

        reviewed_path = ctx.storage.script_dir() / "reviewed_final.md"
        if not reviewed_path.exists():
            return StageResult(status="failed", error="reviewed_final.md не знайдено.")

        script = reviewed_path.read_text(encoding="utf-8")
        llm = get_llm_provider()
        metadata = llm.generate_metadata(script, ctx.job["language"])

        # Лінтер (без LLM, без мережі) сортує LLM-варіанти назв за евристичною оцінкою CTR —
        # довжина під desktop/mobile обрізання, капслок, розпливчасті слова, наявність числа/дати.
        # Нічого не переписує й не відкидає, лише виносить найкращий варіант наперед.
        lint_results = title_lint.rank(metadata["title_options"])
        metadata["title_options"] = [r.title for r in lint_results]

        meta_dir = ctx.storage.metadata_dir()
        (meta_dir / "title_options.json").write_text(
            json.dumps(metadata["title_options"], ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (meta_dir / "title_lint.json").write_text(
            json.dumps([title_lint.to_dict(r) for r in lint_results], ensure_ascii=False, indent=2), encoding="utf-8"
        )
        # Розділи з таймкодами (chapters) рахуються з реальних start_ms озвучених сегментів, а не вигадуються LLM.
        metadata["description"] = chapters.add_to_description(
            metadata["description"], chapters.build(script, ctx.repo.list_segments(ctx.job_id))
        )
        (meta_dir / "description.md").write_text(metadata["description"], encoding="utf-8")
        (meta_dir / "tags.json").write_text(
            json.dumps(metadata["tags"], ensure_ascii=False, indent=2), encoding="utf-8"
        )

        # Прев'ю: окрема композиція (не кадр відео!) за конвенцією ніші — один драматичний силует/
        # артефакт на простому тлі + товстий капс-текст із чорним контуром (app/thumbnails.py). Завжди
        # через "важливий" провайдер (get_image_provider — google), навіть якщо BEATS_IMAGE_PROVIDER
        # дешевший: прев'ю бачать усі, це не філлер-кадр.
        thumb_dir = meta_dir / "thumbnails"
        thumb_paths: list[str] = []
        thumb_text = metadata.get("thumbnail_text") or ""
        base_thumb_subject = metadata.get("thumbnail_subject") or ""
        if IMAGE_PROVIDER == "stub" or not base_thumb_subject:
            _package_output(ctx, metadata["title_options"], metadata["description"], metadata["tags"], [], metadata.get("pinned_comment", ""))
            return StageResult(
                status="success",
                output={
                    "title_options": metadata["title_options"],
                    "title_lint": [title_lint.to_dict(r) for r in lint_results],
                    "description": metadata["description"],
                    "tags": metadata["tags"],
                    "thumbnails": [],
                    "note": "Прев'ю не згенеровано (stub-провайдер або LLM не дав thumbnail_subject).",
                },
            )

        style = v.job_style(ctx)
        accent = dossier.accent_color(dossier.read_dossier(ctx.storage)) or style.accent
        if not thumbnails.fonts_available():
            _package_output(ctx, metadata["title_options"], metadata["description"], metadata["tags"], [], metadata.get("pinned_comment", ""))
            return StageResult(
                status="success",
                output={
                    "title_options": metadata["title_options"],
                    "title_lint": [title_lint.to_dict(r) for r in lint_results],
                    "description": metadata["description"],
                    "tags": metadata["tags"],
                    "thumbnails": [],
                    "note": "Прев'ю не згенеровано: не знайдено Impact/Arial Black шрифт для тексту.",
                },
            )

        image_gen = get_image_provider()
        glossary = v.load_glossary(ctx)
        refs = style_reference_images(style.id)
        concepts = (metadata.get("thumbnail_concepts") or [])[:_THUMBNAIL_VARIANTS]
        if not concepts:  # LLM не дав концепцій — один варіант зі старих полів
            concepts = [{"text": thumb_text, "subject": base_thumb_subject}]
        for i, concept in enumerate(concepts, start=1):
            bg_path = thumb_dir / f"thumb_{i}_bg.png"
            prompt = thumbnails.build_thumbnail_prompt(style, glossary, concept["subject"])
            image_gen.generate_image(prompt, bg_path, refs)

            final_path = thumb_dir / f"thumb_{i}.png"
            text = concept.get("text") or thumb_text
            glow = next((rgb for name, rgb in _GLOW_COLORS.items() if name in concept["subject"].lower()), None)
            if text and thumbnails.render_clickbait_text(text, thumb_dir / f"_text_{i}.png", accent, highlight=glow):
                bg = trim_paper_border(Image.open(bg_path).convert("RGB")).convert("RGBA").resize((thumbnails.W, thumbnails.H))
                text_layer = Image.open(thumb_dir / f"_text_{i}.png").convert("RGBA")
                bg.alpha_composite(text_layer)
                bg.convert("RGB").save(final_path, format="PNG")
            else:
                final_path = bg_path
            thumb_paths.append(ctx.storage.relative(final_path))

        _package_output(ctx, metadata["title_options"], metadata["description"], metadata["tags"], thumb_paths, metadata.get("pinned_comment", ""))
        return StageResult(
            status="success",
            output={
                "title_options": metadata["title_options"],
                "title_lint": [title_lint.to_dict(r) for r in lint_results],
                "description": metadata["description"],
                "tags": metadata["tags"],
                "thumbnail_text": thumb_text,
                "thumbnails": thumb_paths,
            },
        )
