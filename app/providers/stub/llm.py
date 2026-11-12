"""Stub-реалізація LLMProvider — без жодного API-ключа.

Генерує правдоподібно структурований, але зовсім не "розумний" текст, аби решта
пайплайна (сегментація → TTS → візуал → збірка) мала на чому реально відпрацювати
end-to-end. Замінюється на providers/llm/anthropic_provider.py в наступному кроці.
"""

from ...config import WORDS_PER_MINUTE
from ..base import LLMProvider, MetadataResult, SegmentPlan

_PARAGRAPH_TEMPLATES = [
    "Тема сьогоднішнього випуску — {topic}. Це один із найцікавіших фактів, "
    "які варто розглянути детальніше, адже він змінює наше уявлення про звичні речі.",
    "Мало хто замислюється, наскільки глибоко {topic} повʼязана з іншими явищами. "
    "Науковці роками досліджували це питання, і ось до чого вони дійшли.",
    "Якщо поглянути на {topic} під іншим кутом, стає зрозуміло: масштаб цього явища "
    "вражає навіть досвідчених дослідників.",
    "Історія вивчення {topic} почалась задовго до сучасних технологій, "
    "але саме зараз ми можемо побачити повну картину.",
    "Наступний факт про {topic} здивує навіть тих, хто вважає себе експертом у темі.",
]


_STUB_DOSSIER = """## Перевірка теми
✅ Stub-досьє: тема не перевірялась (реальну перевірку зробить LLM_PROVIDER=anthropic).
## Рамка
Тип теми: історія/битва. Епоха й місце — невідомі (stub).
## Ключові факти
- Факт 1 (?)
- Факт 2 (?)
## Сторони та учасники
- Сторона A: спорядження й тактика (?)
- Сторона B: спорядження й тактика (?)
## Ключові моменти
1. Початок 2. Середина 3. Розв'язка
## Теза і кут подачі
Stub: одна ідея, що відрізняє відео від шаблонного переказу.
## Міфи та що перевірити
Усе в цьому stub-досьє потребує перевірки.
## Visual guide (English)
Generic period setting, muted earthy palette, period-appropriate clothing and architecture.
## Forbidden in visuals (English)
modern objects, gunpowder weapons, text overlays
## Accent colour
#C6953A
"""


class StubLLMProvider(LLMProvider):
    def build_dossier(self, topic: str, niche: str) -> str:
        return f"# Досьє: {topic}\n\n" + _STUB_DOSSIER

    def generate_script(self, topic: str, target_duration_minutes: int, language: str, dossier: str = "") -> str:
        target_words = target_duration_minutes * WORDS_PER_MINUTE
        paragraphs = [
            f"# [{language}] {topic}\n",
            f"## Вступ\n\nЛаскаво просимо! Сьогодні поговоримо про {topic}. "
            "Якщо відео сподобається — підпишись на канал і постав лайк.",
        ]
        word_count = sum(len(p.split()) for p in paragraphs)
        i = 0
        while word_count < target_words:
            template = _PARAGRAPH_TEMPLATES[i % len(_PARAGRAPH_TEMPLATES)]
            para = f"## Факт {i + 1}\n\n{template.format(topic=topic)}"
            paragraphs.append(para)
            word_count += len(para.split())
            i += 1
        paragraphs.append(f"## Висновок\n\nОсь такі цікаві факти про {topic}. Дякуємо за перегляд!")
        return "\n\n".join(paragraphs)

    def review_script(self, script: str, language: str, dossier: str = "") -> str:
        # Реальний провайдер тут пропустить сценарій через LLM-редактора (факти/темп/довжина).
        # Stub лише позначає прохід редактури, не змінюючи змісту.
        return script + "\n\n<!-- reviewed: stub pass, без реальних правок -->"

    def revise_script(self, script: str, feedback: str, language: str, dossier: str = "") -> str:
        return script + f"\n\n<!-- revised per feedback: {feedback} (stub, без реальних правок) -->"

    def build_visual_glossary(self, script: str) -> str:
        return "Stub glossary: generic historical setting, muted earthy palette, period-appropriate clothing."

    def segment_script(
        self,
        script: str,
        glossary: str = "",
        accent_tags: list[str] | None = None,
        ambience_tags: list[str] | None = None,
    ) -> list[SegmentPlan]:
        blocks = [b.strip() for b in script.split("\n\n") if b.strip() and not b.strip().startswith("<!--")]
        accents, beds = accent_tags or [], ambience_tags or []
        segments: list[SegmentPlan] = []
        for block in blocks:
            text = block.lstrip("#").strip()
            if not text:
                continue
            words = text.split()
            # ~18 слів на сегмент — як і в реальному розкадруванні (5-8 с озвучки).
            for start in range(0, len(words), 18):
                piece = " ".join(words[start:start + 18])
                i = len(segments)
                keywords = " ".join(words[start:start + 5])
                segments.append(
                    SegmentPlan(
                        text=piece,
                        visual_keywords=keywords,
                        suggested_source="generated",
                        shot=f"Wide painterly view illustrating: {keywords}",
                        motion="slow camera push-in, gentle wind, drifting smoke",
                        visual_type="animated" if i % 4 == 0 else "still",
                        sfx=[accents[i % len(accents)]] if accents and i % 3 == 0 else [],
                        ambience=beds[0] if beds and i == 0 else "",
                        cta="підпиш" in piece.lower(),
                    )
                )
        return segments

    def expand_shot_beats(self, shot: str, glossary: str, n: int) -> list[str]:
        angles = ["wide establishing view", "medium shot", "close detail", "low angle", "high angle", "from behind"]
        return [f"{shot} ({angles[i % len(angles)]})" for i in range(n)]

    def generate_metadata(self, script: str, language: str) -> MetadataResult:
        first_line = script.strip().splitlines()[0].lstrip("#").strip() or "Відео"
        return MetadataResult(
            title_options=[
                f"{first_line} — Факти, які варто знати",
                f"{first_line}: Повний огляд за {len(script.split()) // 150} хв",
                f"Ти не повіриш: {first_line}",
            ],
            description=f"У цьому відео розглядаємо: {first_line}.\n\n(stub-опис, буде замінено на LLM-генерацію)",
            tags=[t.lower() for t in first_line.split()][:8],
            thumbnail_text="STUB PREVIEW",
            thumbnail_subject=f"A dramatic silhouette related to: {first_line}",
        )
