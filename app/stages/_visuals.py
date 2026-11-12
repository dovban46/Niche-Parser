"""Спільні хелпери візуальних стадій (visual_generate, qa_autofix): промпти, шляхи, вибір тривалості."""

import json
import math
from pathlib import Path

from ..config import HERO_IMAGE_SECONDS, STILL_MAX_SECONDS, STILL_OVERRUN_TOLERANCE_SECONDS, STORAGE_ROOT
from ..styles import Style, build_compact_prompt, build_image_prompt, get_style, style_reference_images
from .base import StageContext

GLOSSARY_FILE = "visual_glossary.txt"


def load_glossary(ctx: StageContext) -> str:
    path = ctx.storage.script_dir() / GLOSSARY_FILE
    return path.read_text(encoding="utf-8").strip() if path.exists() else ""


def job_style(ctx: StageContext) -> Style:
    return get_style(ctx.job.get("style_id"))


def image_path(ctx: StageContext, seg: dict) -> Path:
    return ctx.storage.visuals_dir() / f"segment_{seg['segment_index']:04d}.webp"


def beat_image_path(ctx: StageContext, seg: dict, i: int) -> Path:
    return ctx.storage.visuals_dir() / f"segment_{seg['segment_index']:04d}_beat{i}.webp"


def clip_path(ctx: StageContext, seg: dict) -> Path:
    return ctx.storage.visuals_dir() / f"segment_{seg['segment_index']:04d}.mp4"


def exists(relative: str | None) -> bool:
    return bool(relative) and (STORAGE_ROOT / relative).exists()


def shot_for(seg: dict) -> str:
    return seg.get("shot_prompt") or seg.get("visual_keywords") or seg["text"][:80]


def generate_segment_image(ctx: StageContext, seg: dict, image_gen, glossary: str) -> tuple[Path, str]:
    style = job_style(ctx)
    prompt = build_image_prompt(style, glossary, shot_for(seg))
    out = image_path(ctx, seg)
    image_gen.generate_image(prompt, out, style_reference_images(style.id))
    return out, prompt


def beats_needed(seg: dict) -> int:
    """Скільки РІЗНИХ фото потрібне цьому "still"-сегменту: жодне фото не показується довше
    STILL_MAX_SECONDS — довше тримати одне й те саме зображення (навіть із рухом камери) виглядає
    погано (фідбек користувача). "animated"-сегменти отримують Veo-кліп і сюди не потрапляють."""
    if seg.get("visual_type") == "animated":
        return 1
    duration_s = (seg.get("duration_ms") or 0) / 1000
    # Допуск: сегмент до STILL_MAX+TOLERANCE лишається одним фото (рух камери + накладки тримають його).
    return max(1, math.ceil((duration_s - STILL_OVERRUN_TOLERANCE_SECONDS) / STILL_MAX_SECONDS))


def generate_segment_beats(ctx: StageContext, seg: dict, image_gen, llm, glossary: str, n: int) -> list[dict]:
    """n>=2 РІЗНИХ кадрів для одного сегмента (LLM придумує композиції, кожна генерується окремим
    викликом image_gen — свідомо дорожче, але це і був запит: більше генерацій замість трюків з
    напрямком камери на одному фото). Повертає [{"shot": ..., "path": "storage-relative"}, ...]."""
    style = job_style(ctx)
    base_shot = shot_for(seg)
    variants = llm.expand_shot_beats(base_shot, glossary, n)
    beats = []
    for i, shot in enumerate(variants):
        prompt = build_image_prompt(style, glossary, shot)
        out = beat_image_path(ctx, seg, i)
        image_gen.generate_image(prompt, out, style_reference_images(style.id))
        beats.append({"shot": shot, "path": ctx.storage.relative(out)})
    return beats


_JUDGE_RETRIES = 2
ART_FILE = "art_direction.json"
BIBLE_FILE = "art_bible.txt"
_ART_BATCH = 8


def segment_starts(segments: list[dict]) -> dict[int, float]:
    """Початок кожного озвученого сегмента (с) за реальними duration_ms (озвучка вже є на цій стадії)."""
    acc, out = 0.0, {}
    for s in segments:
        out[s["segment_index"]] = acc
        acc += (s.get("duration_ms") or 0) / 1000
    return out


def is_hero(seg: dict, starts: dict[int, float]) -> bool:
    """"Важливий" кадр (дорогий провайдер): вступ (гачок), анімовані старт-кадри для Veo."""
    return seg.get("visual_type") == "animated" or starts.get(seg["segment_index"], 1e9) < HERO_IMAGE_SECONDS


def art_entry(entry) -> tuple[str, str]:
    """(повний промпт, коротка версія) з запису арт-директора; старий формат (рядок) — без короткої."""
    if isinstance(entry, dict):
        return str(entry.get("p", "")), str(entry.get("s", ""))
    return str(entry), ""


def plan_art_direction(ctx: StageContext, segments: list[dict], llm, glossary: str, preview: bool) -> dict[int, list[str]]:
    """Арт-директорський прохід (Claude): для кожного сегмента, якому ще бракує картинок, окремі детальні
    промпти на КОЖНЕ фото. Кешується в script/art_direction.json (повторний запуск стадії не платить вдруге).
    Порожній результат (stub-провайдер чи збій) = старий шлях: shot + expand_shot_beats."""
    script_dir = ctx.storage.script_dir()
    cache_path = script_dir / ART_FILE
    cache: dict[int, list[str]] = {}
    if cache_path.exists():
        cache = {int(k): v for k, v in json.loads(cache_path.read_text(encoding="utf-8")).items()}
    need = [s for s in segments if not exists(s["visual_path"]) and s["segment_index"] not in cache]
    if not need:
        return cache

    bible_path = script_dir / BIBLE_FILE
    if bible_path.exists():
        bible = bible_path.read_text(encoding="utf-8")
    else:
        reviewed = script_dir / "reviewed_final.md"
        bible = llm.build_art_bible(reviewed.read_text(encoding="utf-8") if reviewed.exists() else "", glossary)
        if bible:
            bible_path.write_text(bible, encoding="utf-8")

    starts = segment_starts(segments)
    for i in range(0, len(need), _ART_BATCH):
        batch = need[i:i + _ART_BATCH]
        items = [
            {"index": s["segment_index"], "text": s["text"], "shot": shot_for(s),
             "n": 1 if preview else beats_needed(s), "hero": is_hero(s, starts)}
            for s in batch
        ]
        earlier = [art_entry(e)[0] for k in sorted(cache) if k < batch[0]["segment_index"] for e in cache[k][-1:]]
        try:
            result = llm.art_direct_images(items, glossary, bible, earlier)
        except Exception:  # збій одного батчу не валить стадію: ці сегменти підуть старим шляхом
            result = {}
        cache.update(result)
        cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
    return cache


class CheapProviderStats:
    """Запобіжник вартості для дешевого провайдера (FLUX): рахує, скільки кадрів контролер прийняв без звернення
    до дорогого. Якщо після MIN_SAMPLE кадрів частка прийнятих < MIN_RATE, дешевий провайдер більше не
    викликається (кожна спроба FLUX+контролер коштує ~$0.0045 і окупається лише при помітній частці успіхів) —
    решта кадрів одразу йде дорогим провайдером."""

    MIN_SAMPLE = 16
    MIN_RATE = 0.30

    def __init__(self) -> None:
        import threading
        self._lock = threading.Lock()
        self.tried = 0
        self.accepted = 0

    def record(self, accepted: bool) -> None:
        with self._lock:
            self.tried += 1
            self.accepted += 1 if accepted else 0

    def poor(self) -> bool:
        with self._lock:
            return self.tried >= self.MIN_SAMPLE and self.accepted / self.tried < self.MIN_RATE

    def summary(self) -> dict:
        with self._lock:
            return {"cheap_tried": self.tried, "cheap_accepted": self.accepted}


def generate_segment_images(ctx: StageContext, seg: dict, image_gen, llm, glossary: str, n: int,
                            prompts: list | None, fallback_gen=None, stats: CheapProviderStats | None = None) -> list[dict]:
    """n фото одного сегмента провайдером image_gen. З арт-директорськими промптами — кожне фото має власний
    детальний промпт (глосарій тоді НЕ додаємо). Модель із малим вікном тексту (FLUX: image_gen.compact_prompts)
    отримує КОРОТКУ версію сцени + короткий стиль (styles.build_compact_prompt), решта — повний промпт.
    Без арт-промптів — старий шлях (shot + expand_shot_beats). Повертає [{"shot", "path"}]."""
    style = job_style(ctx)
    entries = [art_entry(e) for e in (prompts or []) if art_entry(e)[0]]
    use_art = bool(entries)
    if not use_art:
        base = shot_for(seg)
        entries = [(shot, "") for shot in (llm.expand_shot_beats(base, glossary, n) if n > 1 else [base])]
    while len(entries) < n:
        entries.append(entries[-1])
    compact = bool(getattr(image_gen, "compact_prompts", False))
    out = []
    for i in range(n):
        path = image_path(ctx, seg) if n == 1 else beat_image_path(ctx, seg, i)
        long_p, short_p = entries[i]
        full_long = build_image_prompt(style, "" if use_art else glossary, long_p)
        if compact and fallback_gen is not None and stats is not None and stats.poor():
            # запобіжник: дешевий провайдер не виправдовує себе на цьому відео — одразу дорогий
            fallback_gen.generate_image(full_long, path, style_reference_images(style.id))
            out.append({"shot": long_p, "path": ctx.storage.relative(path), "retries": 0, "fallback": True})
            continue
        if compact:
            full = build_compact_prompt(style, short_p or " ".join(long_p.split()[:55]))
        else:
            full = full_long
        image_gen.generate_image(full, path, style_reference_images(style.id))
        retries, fell_back = 0, False
        if compact:
            # Дешевий провайдер (FLUX) нестабільно тримає стиль і сцену: автоперевірка Claude (Haiku, ~$0.0015) і до
            # _JUDGE_RETRIES перегенерацій ($0.003); якщо всі невдалі — один раз дорожчий провайдер.
            accepted = False
            for attempt in range(_JUDGE_RETRIES + 1):
                verdict = llm.judge_image(path, short_p or long_p, style.flux_prefix or style.image_prefix)
                if verdict is None or (verdict["style_ok"] and verdict["scene_ok"]):
                    accepted = True
                    break
                if attempt == _JUDGE_RETRIES:
                    break
                retries += 1
                image_gen.generate_image(full, path, style_reference_images(style.id))
            if stats is not None:
                stats.record(accepted)
            if not accepted and fallback_gen is not None:
                fallback_gen.generate_image(full_long, path, style_reference_images(style.id))
                fell_back = True
        out.append({"shot": long_p, "path": ctx.storage.relative(path), "retries": retries, "fallback": fell_back})
    return out


MAX_SLOWDOWN = 1.25  # монтаж дозволяє трохи розтягнути кліп під озвучку (video_assemble вміє до 1.3)


def pick_duration(segment_seconds: float, supported: tuple[int, ...]) -> int:
    """Найкоротша підтримувана тривалість кліпу, яку з невеликим уповільненням можна розтягнути на весь
    сегмент — не платимо за секунди, яких монтаж і так не використає."""
    ordered = sorted(supported)
    for d in ordered:
        if d * MAX_SLOWDOWN >= segment_seconds:
            return d
    return ordered[-1]
