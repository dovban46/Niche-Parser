"""Абстрактні інтерфейси зовнішніх сервісів. Кожен конкретний провайдер (stub, anthropic,
google, replicate, nasa...) реалізує один із цих класів в окремому файлі — стадії пайплайна
(app/stages/*.py) працюють ЛИШЕ через ці інтерфейси і ніколи не знають, який провайдер
насправді підключено. Заміна провайдера = новий файл + зміна *_PROVIDER у .env.
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import NotRequired, TypedDict


class ProviderConfigError(Exception):
    """Провайдер обрано, але для нього не вистачає ключа/налаштування — людяне повідомлення."""


class SegmentPlan(TypedDict):
    text: str
    visual_keywords: str
    suggested_source: str  # "stock" | "generated"
    # Розкадрування (англійською — це промпти для генеративних моделей):
    shot: NotRequired[str]  # що намалювати на стоп-кадрі
    motion: NotRequired[str]  # що рухається в кліпі
    visual_type: NotRequired[str]  # "animated" (AI-кліп) | "still" (кадр + Ken Burns)
    sfx: NotRequired[list[str]]  # теги акцентних ефектів з бібліотеки
    ambience: NotRequired[str]  # тег фону; порожньо = лишається попередній
    cta: NotRequired[bool]  # сегмент, де звучить прохання підписатися/поставити лайк (на екрані — тихий підпис)
    pause_seconds: NotRequired[float]  # "німа" пауза-дихання: text="", лише візуал+sfx на цю тривалість, без голосу


class MetadataResult(TypedDict):
    title_options: list[str]
    description: str
    tags: list[str]
    thumbnail_text: NotRequired[str]  # 1-4 слова капсом для прев'ю; НЕ повторює слова заголовка (app/thumbnails.py)
    thumbnail_subject: NotRequired[str]  # англ. опис ГОЛОВНОГО об'єкта прев'ю (одна драматична постать/артефакт)
    pinned_comment: NotRequired[str]  # питання під відео для закріпленого коментаря (мовою відео)
    thumbnail_concepts: NotRequired[list[dict]]  # 3 РІЗНІ концепції прев'ю [{text, subject}] для A/B-тесту в Studio


class LLMProvider(ABC):
    """`language` скрізь — код із schemas.SUPPORTED_LANGUAGES (напр. "uk", "en", "pl").
    Сегментація (segment_script) мови не потребує: вона лише ріже вже написаний текст і
    завжди повертає visual_keywords англійською (для якості пошуку/генерації візуалу),
    незалежно від мови самого відео."""

    @abstractmethod
    def build_dossier(self, topic: str, niche: str) -> str:
        """Поверхневе досьє теми (Markdown, українською для автора; візуальні розділи англійською) — швидка
        перевірка перед сценарієм, не глибоке дослідження. Формат розділів — див. providers/llm/anthropic_provider.py."""

    @abstractmethod
    def generate_script(self, topic: str, target_duration_minutes: int, language: str, dossier: str = "") -> str: ...

    @abstractmethod
    def review_script(self, script: str, language: str, dossier: str = "") -> str: ...

    @abstractmethod
    def revise_script(self, script: str, feedback: str, language: str, dossier: str = "") -> str:
        """Точкові правки за конкретними побажаннями автора (людина-в-циклі), а не
        повторний повний редакторський прохід — має міняти лише те, про що просять.
        Побажання (feedback) може бути написане іншою мовою, ніж сам сценарій — language
        визначає мову РЕЗУЛЬТАТУ, а не мову feedback."""

    @abstractmethod
    def build_visual_glossary(self, script: str) -> str:
        """Стислий англомовний візуальний глосарій (епоха, сторони, обладунки, герби, місцевість) —
        вставляється в кожен промпт кадру, щоб історичні деталі не пливли між сценами."""

    @abstractmethod
    def segment_script(
        self,
        script: str,
        glossary: str = "",
        accent_tags: list[str] | None = None,
        ambience_tags: list[str] | None = None,
    ) -> list[SegmentPlan]:
        """Розкадрування: різ сценарію на сегменти по ~5-8 с озвучки + shot/motion/тип/ефекти.
        accent_tags/ambience_tags — які ефекти реально є в бібліотеці (інших не вигадувати)."""

    @abstractmethod
    def generate_metadata(self, script: str, language: str) -> MetadataResult: ...

    @abstractmethod
    def expand_shot_beats(self, shot: str, glossary: str, n: int) -> list[str]:
        """n (>=2) ВІДМІННИХ композицій для одного "still"-сегмента, який довший за один короткий
        план (STILL_MAX_SECONDS): той самий предмет/сцена/епоха, але різний кут/план/деталь у фокусі —
        а не те саме фото з іншим напрямком руху камери (це і був фідбек: так виглядає погано).
        Перший рядок результату — сумісний із оригінальним `shot` (можна лишити майже як є)."""

    def judge_image(self, image_path: Path, scene: str, style_desc: str) -> dict | None:
        """Дешева автоперевірка кадра моделлю з баченням: {"style_ok": bool, "scene_ok": bool, "why": str}.
        None = провайдер не вміє (stub) — кадр приймається як є."""
        return None

    def build_art_bible(self, script: str, glossary: str) -> str:
        """"Біблія кадрів": фіксований опис повторюваних персонажів/предметів, ключові деталі локацій кожного
        візуального етапу й список банальних повторів, яких слід уникати. Порожній рядок = провайдер не вміє
        (stub) — тоді працює старий шлях (shot + expand_shot_beats)."""
        return ""

    def art_direct_images(self, items: list[dict], glossary: str, bible: str, previous: list[str]) -> dict[int, list[str]]:
        """Арт-директорський прохід: для кожного сегмента (items: index, text, shot, n, hero) — РІВНО n детальних
        самодостатніх промптів для генератора картинок (локація, час, світло, кольори, вбрання, реквізит, камера,
        композиція), що відрізняються від `previous`. {} = провайдер не вміє — старий шлях."""
        return {}


class TTSProvider(ABC):
    # Формат файлу, який реально пише synthesize() — stub пише WAV, реальні мовні API
    # (ElevenLabs, edge-tts) віддають MP3. Стадії будують ім'я файлу за цим атрибутом,
    # а не хардкодять розширення.
    file_extension: str = "wav"

    @abstractmethod
    def resolve_voice(self, language: str, voice: str | None = None) -> str:
        """Конкретний ідентифікатор голосу: обраний користувачем `voice`, а якщо його
        немає — дефолт провайдера для цієї мови."""

    @abstractmethod
    def synthesize(
        self,
        text: str,
        out_path: Path,
        language: str,
        voice: str | None = None,
        previous_text: str | None = None,
        next_text: str | None = None,
    ) -> int:
        """Синтезує озвучку в out_path мовою `language` голосом `voice` (None — дефолтний
        голос провайдера), повертає тривалість у мілісекундах. previous_text/next_text —
        сусідні репліки: провайдери, що вміють, підбирають інтонацію під контекст, щоб
        окремо озвучені сегменти зливались в одне читання."""


class ImageGenProvider(ABC):
    compact_prompts: bool = False  # True — модель з малим вікном тексту, потрібен короткий промпт
    # Орієнтовна ціна одного зображення (USD) — для кошторису в UI; stub — 0.
    cost_per_image_usd: float = 0.0

    @abstractmethod
    def generate_image(self, prompt: str, out_path: Path, references: list[Path] | None = None) -> Path:
        """Генерує/зберігає зображення в out_path (створює батьківські директорії сама).
        references — стильові референс-кадри (провайдери, що не вміють, ігнорують їх)."""


class VideoGenProvider(ABC):
    # Тривалості кліпів, які вміє модель (секунди), і орієнтовна ціна секунди (USD).
    supported_durations: tuple[int, ...] = (4, 6, 8)
    cost_per_second_usd: float = 0.0

    @abstractmethod
    def generate_clip(self, prompt: str, start_image: Path, out_path: Path, duration_s: int) -> Path:
        """Оживлює start_image (image-to-video) в mp4 тривалістю duration_s → out_path.
        Кидає ProviderConfigError із зрозумілою причиною (напр. спрацював фільтр безпеки)."""
