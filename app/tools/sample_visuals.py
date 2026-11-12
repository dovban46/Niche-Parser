"""Зразковий прогін кадрів ДО повної генерації (платної): арт-директорські промпти для всього сценарію
(дешево, Claude), потім кілька кадрів: hero (вступ) по кілька кандидатів дорогим провайдером і кілька звичайних
дешевшим. Збирає контактний лист — його можна подивитись і лише тоді знімати HOLD_VISUALS.

    python -m app.tools.sample_visuals <job_id> [hero_n=4] [regular_n=6] [candidates=2]

Кандидат hero-кадру лежить у storage/jobs/<id>/samples/. Звичайні зразки пишуться одразу на своє місце (стадія
visual_generate їх уже не генерує вдруге); для hero копіюється кандидат №1 (інший — вручну, `pick_candidate`)."""

import json
import shutil
import sys

from PIL import Image, ImageDraw

from ..db import init_db
from ..jobs import repository as repo
from ..providers.registry import get_beats_image_provider, get_image_provider, get_llm_provider
from ..stages import _visuals as v
from ..stages.base import StageContext
from ..storage import JobStorage
from ..styles import build_image_prompt, style_reference_images


def _ctx(job_id: int) -> StageContext:
    init_db()
    job = repo.get_job(job_id)
    return StageContext(job=job, repo=repo, storage=JobStorage(job_id), config=json.loads(job["config_json"]))


def _set_image(ctx: StageContext, seg: dict, path, shot: str, provider) -> None:
    repo.update_segment(
        ctx.job_id, seg["segment_index"], visual_path=ctx.storage.relative(path), visual_prompt=shot,
        visual_source="generated_image", visual_provider=type(provider).__name__, visual_license="AI-generated", status="ready",
    )


def pick_candidate(job_id: int, segment_index: int, k: int) -> None:
    """Робить кандидата k (1-based) офіційним кадром сегмента."""
    ctx = _ctx(job_id)
    seg = next(s for s in repo.list_segments(job_id) if s["segment_index"] == segment_index)
    src = ctx.storage.job_root / "samples" / f"hero_{segment_index:04d}_c{k}.webp"
    dst = v.image_path(ctx, seg)
    shutil.copyfile(src, dst)
    art = json.loads((ctx.storage.script_dir() / v.ART_FILE).read_text(encoding="utf-8"))
    _set_image(ctx, seg, dst, v.art_entry((art.get(str(segment_index)) or [""])[0])[0], get_image_provider())


def main(job_id: int, hero_n: int = 4, regular_n: int = 6, candidates: int = 2) -> None:
    ctx = _ctx(job_id)
    style = v.job_style(ctx)
    segments = [s for s in repo.list_segments(job_id) if s["audio_path"]]
    glossary, llm = v.load_glossary(ctx), get_llm_provider()
    art = v.plan_art_direction(ctx, segments, llm, glossary, False)
    starts = v.segment_starts(segments)
    out_dir = ctx.storage.job_root / "samples"
    out_dir.mkdir(exist_ok=True)

    hero_gen, regular_gen = get_image_provider(), get_beats_image_provider()
    tiles: list[tuple[str, str]] = []

    heroes = [s for s in segments if v.is_hero(s, starts) and v.beats_needed(s) == 1][:hero_n]
    for seg in heroes:
        idx = seg["segment_index"]
        prompt = v.art_entry((art.get(idx) or [v.shot_for(seg)])[0])[0]
        for k in range(1, candidates + 1):
            path = out_dir / f"hero_{idx:04d}_c{k}.webp"
            hero_gen.generate_image(build_image_prompt(style, "" if idx in art else glossary, prompt), path,
                                    style_reference_images(style.id))
            tiles.append((f"hero {idx} c{k}", str(path)))
        pick_candidate(job_id, idx, 1)

    regular = [s for s in segments if not v.is_hero(s, starts)]
    step = max(1, len(regular) // max(regular_n, 1))
    for seg in regular[::step][:regular_n]:
        idx = seg["segment_index"]
        n = v.beats_needed(seg)
        images = v.generate_segment_images(ctx, seg, regular_gen, llm, glossary, n, art.get(idx))
        repo.update_segment(
            ctx.job_id, idx, visual_path=images[0]["path"], visual_prompt=images[0]["shot"],
            visual_source="generated_image", visual_provider=type(regular_gen).__name__, visual_license="AI-generated",
            status="ready", **({"beats_json": json.dumps(images, ensure_ascii=False)} if len(images) > 1 else {}),
        )
        tiles.append((f"seg {idx} ({n} img)", str(ctx.storage.job_root.parent.parent / images[0]["path"])))

    cols, tw, th = 3, 480, 270
    rows = (len(tiles) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * tw, rows * (th + 22)), (20, 20, 20))
    draw = ImageDraw.Draw(sheet)
    for i, (label, path) in enumerate(tiles):
        x, y = (i % cols) * tw, (i // cols) * (th + 22)
        sheet.paste(Image.open(path).convert("RGB").resize((tw, th)), (x, y + 22))
        draw.text((x + 6, y + 4), label, fill=(235, 235, 235))
    sheet_path = out_dir / "sheet.png"
    sheet.save(sheet_path)
    print(sheet_path)


if __name__ == "__main__":
    args = [int(a) for a in sys.argv[1:]]
    main(*args)
