import json
from concurrent.futures import ThreadPoolExecutor

from ..config import STORAGE_ROOT, VISUAL_CONCURRENCY
from ..providers.registry import get_beats_image_provider, get_image_provider, get_llm_provider, get_video_provider
from ..styles import build_motion_prompt
from . import _visuals as v
from .base import StageContext, StageResult


class VisualGenerateStage:
    """Для кожного озвученого сегмента: (1) стоп-кадр у стилі відео (Nano Banana + референси стилю);
    (2) якщо сегмент "animated" — 4/6/8-секундний кліп із цього кадру (Veo). У тест-режимі оживляються
    ВСІ озвучені сегменти — щоб побачити якість анімації на короткому шматку.

    Ідемпотентна: вже згенеровані файли (платна робота) не створюються вдруге. Невдалий кліп не валить
    стадію — сегмент іде як кадр + Ken Burns, причина фіксується у виході й у QA."""

    name = "visual_generate"

    def run(self, ctx: StageContext) -> StageResult:
        segments = [s for s in ctx.repo.list_segments(ctx.job_id) if s["audio_path"]]
        if not segments:
            return StageResult(status="failed", error="Немає озвучених сегментів — tts_synthesize не завершився?")

        image_gen = get_image_provider()  # "важливі" кадри: превью (окремим скриптом), Veo-старт-кадри, короткі плани
        video_gen = get_video_provider()
        glossary = v.load_glossary(ctx)
        preview = bool(ctx.job.get("preview_seconds"))

        # ---- 1. кадри ----
        # Рішення 2026-10-03 (бюджет): кадр показується до STILL_MAX_SECONDS (~6с), тож їх удвічі менше, ніж було.
        # "Важливі" кадри (вступ-гачок і старт-кадри Veo) — дорогим провайдером (Nano Banana), решта — дешевшим
        # BEATS_IMAGE_PROVIDER. Кожне фото отримує власний детальний промпт від арт-директорського проходу
        # (_visuals.plan_art_direction) замість спільного загального.
        llm = get_llm_provider()
        beats_image_gen = get_beats_image_provider()
        starts = v.segment_starts(segments)
        art = v.plan_art_direction(ctx, segments, llm, glossary, preview)

        cheap_stats = v.CheapProviderStats()
        image_errors: dict[int, str] = {}
        counts = {"hero": 0, "regular": 0}
        todo = [dict(s, _n=1 if preview else v.beats_needed(s)) for s in segments if not v.exists(s["visual_path"])]
        is_stub = type(image_gen).__name__ == "StubImageGenProvider"
        license_note = "stub placeholder — не для публікації" if is_stub else "AI-generated"

        def make_images(item):
            hero = v.is_hero(item, starts)
            provider = image_gen if hero else beats_image_gen
            images = v.generate_segment_images(ctx, item, provider, llm, glossary, item["_n"],
                                               art.get(item["segment_index"]),
                                               fallback_gen=None if provider is image_gen else image_gen,
                                               stats=cheap_stats)
            return item, hero, provider, images

        for item, hero, provider, images in _parallel(make_images, todo, image_errors):
            fields = dict(
                visual_path=images[0]["path"], visual_prompt=images[0]["shot"],
                visual_source="generated_image", visual_provider=type(provider).__name__,
                visual_license=license_note, status="ready",
            )
            if len(images) > 1:
                fields["beats_json"] = json.dumps(images, ensure_ascii=False)
            ctx.repo.update_segment(ctx.job_id, item["segment_index"], **fields)
            counts["hero" if hero else "regular"] += len(images)
            counts["fallback"] = counts.get("fallback", 0) + sum(1 for im in images if im.get("fallback"))
            counts["retries"] = counts.get("retries", 0) + sum(im.get("retries", 0) for im in images)
        new_images, new_beat_images = counts["hero"], counts["regular"]

        for idx in image_errors:
            ctx.repo.update_segment(ctx.job_id, idx, status="failed")

        # ---- 2. анімовані кліпи ----
        clip_errors: dict[int, str] = {}
        new_clip_seconds = 0
        if video_gen is not None:
            ready = [s for s in ctx.repo.list_segments(ctx.job_id) if s["audio_path"] and v.exists(s["visual_path"])]
            wanted = [
                s for s in ready
                if (preview or s["visual_type"] == "animated") and not v.exists(s["visual_clip_path"])
            ]
            durations = {s["segment_index"]: v.pick_duration(s["duration_ms"] / 1000, video_gen.supported_durations) for s in wanted}
            style = v.job_style(ctx)

            def make_clip(seg):
                out = v.clip_path(ctx, seg)
                prompt = build_motion_prompt(style, v.shot_for(seg), seg.get("motion_prompt") or "slow camera push-in")
                video_gen.generate_clip(prompt, STORAGE_ROOT / seg["visual_path"], out, durations[seg["segment_index"]])
                return seg, out

            for seg, out in _parallel(make_clip, wanted, clip_errors):
                ctx.repo.update_segment(
                    ctx.job_id, seg["segment_index"],
                    visual_clip_path=ctx.storage.relative(out), visual_source="generated_video",
                )
                new_clip_seconds += durations[seg["segment_index"]]

        fallback_n, retry_n = counts.get("fallback", 0), counts.get("retries", 0)
        cost = ((new_images + fallback_n) * image_gen.cost_per_image_usd
                + (new_beat_images + retry_n) * (beats_image_gen.cost_per_image_usd if beats_image_gen else 0.0)
                + new_clip_seconds * (video_gen.cost_per_second_usd if video_gen else 0.0))
        output = {
            "segments": len(segments),
            "images_generated": new_images,
            "beat_images_generated": new_beat_images,
            "cheap_provider_retries": retry_n,
            **cheap_stats.summary(),
            "expensive_fallback_images": fallback_n,
            "beats_provider": type(beats_image_gen).__name__ if beats_image_gen else None,
            "clip_seconds_generated": new_clip_seconds,
            "clip_fallbacks": clip_errors,  # сегмент → чому кліп не вийшов (йде як кадр + Ken Burns)
            "estimated_cost_usd": round(cost, 3),
            "preview_mode": preview,
        }
        if image_errors:
            output["failed_segments"] = sorted(image_errors)
            output["errors"] = image_errors
            return StageResult(status="needs_review", output=output)
        return StageResult(status="success", output=output)


def _parallel(fn, items: list[dict], errors: dict[int, str]) -> list:
    """Виконує fn(item) паралельно; успіхи повертає, помилки складає в errors[segment_index]."""
    if not items:
        return []
    results = []
    with ThreadPoolExecutor(max_workers=max(1, VISUAL_CONCURRENCY)) as pool:
        futures = [(item, pool.submit(fn, item)) for item in items]
        for item, future in futures:
            try:
                results.append(future.result())
            except Exception as exc:  # провайдер може відхилити один кадр/кліп — решта не мусить страждати
                errors[item["segment_index"]] = f"{type(exc).__name__}: {exc}"[:300]
    return results
