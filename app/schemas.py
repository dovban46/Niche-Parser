import re

from pydantic import BaseModel, Field, field_validator

from .config import DEFAULT_NICHE, DEFAULT_TARGET_DURATION_MINUTES
from .styles import STYLES

VOICE_ID_RE = re.compile(r"[A-Za-z0-9_-]{1,64}")

# Обмежений набір мов на старті — єдине джерело правди для UI (селектор), валідації
# запиту й підказки мови в LLM-промптах (providers/llm/anthropic_provider.py) та вибору
# TTS-голосу (providers/tts/*). Додати нову мову = один новий рядок тут + voice-мапи
# в edge_provider.py/elevenlabs_provider.py.
SUPPORTED_LANGUAGES: dict[str, str] = {
    "uk": "Українська",
    "en": "English",
    "pl": "Polski",
    "de": "Deutsch",
    "es": "Español",
    "it": "Italiano",
    "fr": "Français",
}
DEFAULT_LANGUAGE = "uk"

# Порядок стадій пайплайна — єдине джерело правди для прогресу "X/9" в UI
# (сам список Stage-об'єктів живе в jobs/pipeline.py, тут — тільки імена й підписи).
STAGE_LABELS: dict[str, str] = {
    "research_dossier": "Досьє теми",
    "script_generate": "Сценарій",
    "script_review": "Редактура сценарію",
    "visual_plan": "Сегментація й план візуалу",
    "tts_synthesize": "Озвучка (TTS)",
    "visual_generate": "Генерація візуалу",
    "video_assemble": "Збірка відео",
    "qa_analyze": "QA-аналіз",
    "qa_autofix": "Автовиправлення",
    "metadata_generate": "Метадані й превью",
}
STAGE_ORDER: list[str] = list(STAGE_LABELS.keys())


class JobCreateRequest(BaseModel):
    topic: str = Field(..., min_length=3, description="Тема/бриф для сценарію")
    niche: str = Field(DEFAULT_NICHE, description="Ніша (наразі впливає лише на промпти)")
    target_duration_minutes: int = Field(DEFAULT_TARGET_DURATION_MINUTES, ge=1, le=120)
    language: str = Field(DEFAULT_LANGUAGE, description="Код мови сценарію й озвучки")
    voice_id: str | None = Field(None, description="Голос озвучки; None — дефолтний голос провайдера")
    style_id: str | None = Field(None, description="Візуальний стиль (ключ із styles.STYLES); None — за замовчуванням")
    preview_seconds: int | None = Field(
        None, ge=10, le=600,
        description="Тест-режим: озвучити й анімувати лише перші N секунд (решта й метадані не генеруються)",
    )
    auto_dossier: bool = Field(False, description="Схвалити досьє автоматично (без паузи на перевірку)")

    @field_validator("language")
    @classmethod
    def _validate_language(cls, v: str) -> str:
        if v not in SUPPORTED_LANGUAGES:
            allowed = ", ".join(SUPPORTED_LANGUAGES)
            raise ValueError(f"Непідтримувана мова '{v}'. Доступні: {allowed}.")
        return v

    @field_validator("style_id")
    @classmethod
    def _validate_style(cls, v: str | None) -> str | None:
        if v and v not in STYLES:
            raise ValueError(f"Невідомий стиль '{v}'. Доступні: {', '.join(STYLES)}.")
        return v or None

    @field_validator("voice_id")
    @classmethod
    def _validate_voice_id(cls, v: str | None) -> str | None:
        return _validate_voice_id(v)


def _validate_voice_id(v: str | None) -> str | None:
    # voice_id потрапляє в URL ElevenLabs і в ім'я файлу прев'ю — пускаємо лише безпечні символи.
    v = (v or "").strip()
    if not v:
        return None
    if not VOICE_ID_RE.fullmatch(v):
        raise ValueError("Невалідний ID голосу (дозволені літери, цифри, '-' та '_', до 64 символів).")
    return v


class VoicePreviewRequest(BaseModel):
    language: str = Field(DEFAULT_LANGUAGE)
    voice_id: str | None = None

    @field_validator("language")
    @classmethod
    def _validate_language(cls, v: str) -> str:
        if v not in SUPPORTED_LANGUAGES:
            raise ValueError(f"Непідтримувана мова '{v}'.")
        return v

    @field_validator("voice_id")
    @classmethod
    def _validate_voice_id(cls, v: str | None) -> str | None:
        return _validate_voice_id(v)


class DossierSaveRequest(BaseModel):
    text: str = Field(..., min_length=20, max_length=20000, description="Відредаговане досьє (Markdown)")


class ScriptReviseRequest(BaseModel):
    feedback: str = Field(..., min_length=3, description="Конкретні правки, які хоче автор")


class JobStageView(BaseModel):
    stage_name: str
    stage_label: str
    stage_order: int
    status: str
    attempt: int
    started_at: str | None = None
    finished_at: str | None = None
    output: dict | None = None
    error_message: str | None = None


class SegmentView(BaseModel):
    index: int
    text: str
    visual_keywords: str | None = None
    suggested_source: str | None = None
    start_ms: int | None = None
    duration_ms: int | None = None
    audio_url: str | None = None
    shot: str | None = None
    motion: str | None = None
    visual_type: str = "still"
    clip_url: str | None = None
    sfx: list[str] = []
    ambience: str | None = None
    cta: bool = False
    pause_seconds: float | None = None
    visual_source: str = "pending"
    visual_url: str | None = None
    visual_provider: str | None = None
    visual_license: str | None = None
    status: str = "pending"


class QaIssueView(BaseModel):
    issue_type: str
    start_sec: float | None = None
    end_sec: float | None = None
    severity: str
    resolution: str
    notes: str | None = None


class JobSummary(BaseModel):
    id: int
    created_at: str
    updated_at: str
    topic: str
    niche: str
    language: str
    voice_id: str | None = None
    voice_name: str | None = None
    style_id: str | None = None
    preview_seconds: int | None = None
    target_duration_minutes: int
    status: str
    current_stage: str | None = None
    progress_done: int
    progress_total: int


class JobDetail(JobSummary):
    error_message: str | None = None
    final_video_url: str | None = None
    script_approved: bool = False
    script_text: str | None = None
    visual_glossary: str | None = None
    dossier: str | None = None
    dossier_approved: bool = True
    estimated_cost_usd: float = 0.0
    stages: list[JobStageView]
    segments: list[SegmentView]
    qa_issues: list[QaIssueView]
