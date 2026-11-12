import json

from .. import dossier, sfx
from ..config import INTRO_ANIMATED_SECONDS, MAX_ANIMATED_SHARE, MAX_EXTRA_ANIMATED, WORDS_PER_MINUTE
from ..providers.registry import get_llm_provider
from ._visuals import GLOSSARY_FILE
from .base import StageContext, StageResult


class VisualPlanStage:
    """Розкадрування: візуальний глосарій + різ сценарію на сегменти по 5-8 с озвучки, кожен із
    shot/motion/типом (анімація чи кадр)/ефектами. У тест-режимі (preview_seconds) розкадровується
    лише початок сценарію — решта відео не потрібна, тож і LLM-виклики на неї не витрачаються."""

    name = "visual_plan"

    def run(self, ctx: StageContext) -> StageResult:
        reviewed_path = ctx.storage.script_dir() / "reviewed_final.md"
        if not reviewed_path.exists():
            return StageResult(status="failed", error="reviewed_final.md не знайдено — script_review не завершився?")

        script = reviewed_path.read_text(encoding="utf-8")
        llm = get_llm_provider()

        glossary_path = ctx.storage.script_dir() / GLOSSARY_FILE
        if glossary_path.exists():
            glossary = glossary_path.read_text(encoding="utf-8").strip()
        else:
            # Структурований візуальний гід із досьє (з правками автора); LLM-глосарій — запасний варіант для job'ів без досьє.
            glossary = dossier.visual_glossary(dossier.read_dossier(ctx.storage)) or llm.build_visual_glossary(script).strip()
            glossary_path.write_text(glossary, encoding="utf-8")

        preview = ctx.job.get("preview_seconds")
        plan_script = _head(script, int(preview / 60 * WORDS_PER_MINUTE * 1.7) + 20) if preview else script

        segments = llm.segment_script(
            plan_script,
            glossary=glossary,
            accent_tags=sfx.available_tags("accent"),
            ambience_tags=sfx.available_tags("ambience"),
        )
        if not segments:
            return StageResult(status="failed", error="Сегментація повернула 0 сегментів.")
        segments = cap_animated(merge_short(segments), MAX_ANIMATED_SHARE)

        plan_path = ctx.storage.script_dir() / "segments_plan.json"
        plan_path.write_text(json.dumps(segments, ensure_ascii=False, indent=2), encoding="utf-8")
        ctx.repo.replace_segments(ctx.job_id, segments)

        return StageResult(
            status="success",
            output={
                "segments_plan_path": ctx.storage.relative(plan_path),
                "segment_count": len(segments),
                "animated_segments": sum(1 for s in segments if s.get("visual_type") == "animated"),
                "sfx_available": {"accents": len(sfx.available_tags("accent")), "beds": len(sfx.available_tags("ambience"))},
                "visual_glossary": glossary,
                "preview_only": bool(preview),
            },
        )


_MIN_WORDS, _MAX_WORDS = 10, 26  # ≈ 4 с і ≈ 10 с озвучки: коротші сегменти не варті окремого кліпу (мінімум 4 с)


def _words(seg: dict) -> int:
    return len(seg["text"].split())


def _is_pause(seg: dict) -> bool:
    """Пауза-дихання (text="", лише візуал+sfx) — ніколи не зливається з сусідами: злиття приписало б їй
    чужий текст або розтягнуло б чуже озвучене речення на її "німу" тривалість."""
    return bool(seg.get("pause_seconds"))


def _merge(a: dict, b: dict) -> dict:
    """Склеює два сусідні сегменти; кадр/рух беремо з довшого (там більше змісту), ефекти й тип — обʼєднуємо."""
    main = a if _words(a) >= _words(b) else b
    merged = dict(main)
    merged["text"] = f"{a['text']} {b['text']}"
    merged["sfx"] = list(dict.fromkeys([*(a.get("sfx") or []), *(b.get("sfx") or [])]))[:2]
    merged["ambience"] = a.get("ambience") or b.get("ambience") or ""
    merged["visual_type"] = "animated" if "animated" in (a.get("visual_type"), b.get("visual_type")) else "still"
    merged["cta"] = bool(a.get("cta") or b.get("cta"))
    return merged


def merge_short(segments: list[dict]) -> list[dict]:
    out: list[dict] = []
    for seg in segments:
        if (out and not _is_pause(out[-1]) and not _is_pause(seg)
                and _words(out[-1]) < _MIN_WORDS and _words(out[-1]) + _words(seg) <= _MAX_WORDS):
            out[-1] = _merge(out[-1], seg)
        else:
            out.append(dict(seg))
    if (len(out) > 1 and not _is_pause(out[-1]) and not _is_pause(out[-2])
            and _words(out[-1]) < _MIN_WORDS and _words(out[-2]) + _words(out[-1]) <= _MAX_WORDS + 6):
        out[-2:] = [_merge(out[-2], out[-1])]
    return out


_MAX_ANIMATED_WORDS = 32  # ≈13с при 150 сл/хв: довше — Veo-кліп (макс. 8с) доведеться заморожувати на
                          # хвіст довше за саму анімацію, сенс "animated" губиться. Такі сегменти — завжди still
                          # (крім вступу: там кліп свідомо розтягується/замінюється першим кадром).
_MAX_ANIMATED_PAUSES = 2


def _estimated_starts(segments: list[dict]) -> list[float]:
    """Орієнтовний початок кожного сегмента (с) за кількістю слів — точні тривалості з'являються лише після
    озвучки, а вибір animated робиться ДО неї."""
    starts, acc = [], 0.0
    for s in segments:
        starts.append(acc)
        acc += (s.get("pause_seconds") or 3.0) if _is_pause(s) else _words(s) / WORDS_PER_MINUTE * 60
    return starts


def cap_animated(segments: list[dict], share: float) -> list[dict]:
    """Veo — головна платна стаття (Google AI Studio), тому анімація лише там, де вона працює на утримання:
    1) ВСТУП — усі сегменти, що починаються в перших INTRO_ANIMATED_SECONDS озвучки (гачок), без винятку;
    2) далі не більше MAX_EXTRA_ANIMATED ключових моментів (спершу паузи-дихання, де картинка — єдиний носій
       уваги, потім сегменти з ефектами й більшою кількістю тексту), але не понад частку `share`.
    Дуже довгі сегменти (> _MAX_ANIMATED_WORDS) поза вступом знімаються з animated ще до відбору."""
    starts = _estimated_starts(segments)
    intro = {i for i in range(len(segments)) if starts[i] < INTRO_ANIMATED_SECONDS or i < 3}
    out = [{**s, "visual_type": "animated" if i in intro else "still"} if i in intro
           else ({**s, "visual_type": "still"} if _words(s) > _MAX_ANIMATED_WORDS and not _is_pause(s) else s)
           for i, s in enumerate(segments)]

    candidates = [i for i, s in enumerate(out) if i not in intro and (s.get("visual_type") == "animated" or _is_pause(s))]
    pauses = [i for i in candidates if _is_pause(out[i])][:_MAX_ANIMATED_PAUSES]
    others = sorted(
        (i for i in candidates if i not in pauses and not _is_pause(out[i])),
        key=lambda i: (len(out[i].get("sfx") or []), _words(out[i])), reverse=True,
    )
    budget = max(0, min(MAX_EXTRA_ANIMATED, round(len(segments) * share) - len(intro)))
    keep = set(pauses[:budget]) | set(others[: max(0, budget - len(pauses[:budget]))])
    return [
        {**s, "visual_type": "animated" if (i in intro or i in keep) else "still"}
        for i, s in enumerate(out)
    ]


def _head(script: str, words: int) -> str:
    """Початок сценарію (по абзацах) приблизно на `words` слів."""
    kept, count = [], 0
    for para in (p for p in script.split("\n\n") if p.strip()):
        kept.append(para)
        count += len(para.split())
        if count >= words:
            break
    return "\n\n".join(kept)
