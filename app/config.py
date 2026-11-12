"""Централізована конфігурація: читає .env, дає константи шляхів/провайдерів
усьому іншому коду. Один файл — одне джерело правди про налаштування середовища.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent  # корінь video-factory

STORAGE_ROOT = Path(os.environ.get("STORAGE_ROOT") or str(BASE_DIR / "storage")).resolve()
DB_PATH = Path(os.environ.get("DB_PATH") or str(BASE_DIR / "app" / "data" / "video_factory.sqlite3")).resolve()
# Спільні (не прив'язані до job'а) ресурси в STORAGE_ROOT: бібліотека звукових ефектів
# (платна в генерації — переживає видалення job'ів) і референс-кадри стилів.
SFX_ROOT = Path(os.environ.get("SFX_ROOT") or str(STORAGE_ROOT / "sfx_library")).resolve()
STYLE_REFS_ROOT = Path(os.environ.get("STYLE_REFS_ROOT") or str(STORAGE_ROOT / "style_refs")).resolve()
# Готові (зібрані) відео — окрема тека, куди зручно зайти напряму; проміжні артефакти
# job'ів (сценарій, аудіо-сегменти, візуали) лишаються в STORAGE_ROOT/jobs/{id}/.
VIDEOS_ROOT = Path(os.environ.get("VIDEOS_ROOT") or str(BASE_DIR / "videos")).resolve()

# NOTE: `or default`, не `.get(key, default)` — порожнє значення в .env (напр. після
# копіювання шаблону) має так само падати на дефолт, а не пропускати "" далі.
LLM_PROVIDER = os.environ.get("LLM_PROVIDER") or "stub"
TTS_PROVIDER = os.environ.get("TTS_PROVIDER") or "stub"
IMAGE_PROVIDER = os.environ.get("IMAGE_PROVIDER") or "stub"  # stub | google | fal
VIDEO_PROVIDER = os.environ.get("VIDEO_PROVIDER") or "stub"  # stub | google | none
# Провайдер для "беатів" довгих still-сегментів (app/stages/_visuals.py:generate_segment_beats) — де
# об'єм замінює ідеальне слідування стилю. Дефолт = IMAGE_PROVIDER (без гібриду); задай "fal" у .env,
# щоб дорогий IMAGE_PROVIDER=google лишався тільки на превью/анімованих кадрах/коротких планах, а
# основний обсяг кадрів ішов через дешевший fal.ai (FLUX) — див. providers/images/fal_image.py.
BEATS_IMAGE_PROVIDER = os.environ.get("BEATS_IMAGE_PROVIDER") or IMAGE_PROVIDER

DEFAULT_NICHE = "ancient_mysteries"
# 12-16 хв — солодка зона в ніші forbidden books/ancient mysteries (медіана лідера ніші,
# каналу Trending Tales, ~13.6 хв; конкуренти в діапазоні 10-22 хв). Див. app/niche_scan.py
# в E:/YouTube/parser та пам'ять проєкту project_niche_research.md.
DEFAULT_TARGET_DURATION_MINUTES = 14

# Скільки разів повторювати мережеву стадію перед failed, і паузи між спробами (сек).
STAGE_RETRY_ATTEMPTS = 3
STAGE_RETRY_BACKOFF_SECONDS = [2, 4, 8]

# Скільки кліпів/картинок генерувати паралельно (платні мережеві виклики, кожен — десятки секунд).
VISUAL_CONCURRENCY = int(os.environ.get("VISUAL_CONCURRENCY") or 3)

# М'яка межа частки анімованих сегментів (0..1): модель інколи позначає "animated" майже все, а кожна
# анімована секунда платна (Veo). 1 = без обмеження. Тест-режим цю межу ігнорує (там оживляється все).
# 0.18 (було 0.5 — вийшло $7-20 на Veo-кліпи за одне 16-хв відео, забагато). Знижено, бо "застиглість"
# тепер вирішує STILL_MAX_SECONDS (кожні ≤3с — нове фото, не той самий кадр) — анімація більше не єдиний
# інструмент проти статики, це вже "бонус" на ключових/перших моментах, а не основний засіб. Перші 3
# сегменти й так гарантовано анімовані незалежно від цієї частки (segment_script/cap_animated).
MAX_ANIMATED_SHARE = float(os.environ.get("MAX_ANIMATED_SHARE") or 0.18)
# Рішення 2026-10-03 (бюджет Google AI Studio — критична стаття витрат): Veo-анімація лише на ВСТУП
# (перші INTRO_ANIMATED_SECONDS озвучки, це і є гачок) плюс не більше MAX_EXTRA_ANIMATED ключових моментів
# далі. Решта відео — фото з багатим рухом камери й накладками (video_assemble). Частка MAX_ANIMATED_SHARE
# лишається верхньою межею, але практично вирішує саме ця пара.
INTRO_ANIMATED_SECONDS = float(os.environ.get("INTRO_ANIMATED_SECONDS") or 24)
MAX_EXTRA_ANIMATED = int(os.environ.get("MAX_EXTRA_ANIMATED") or 3)
# Перші HERO_IMAGE_SECONDS озвучки й усі анімовані старт-кадри генеруються дорогим "важливим" провайдером
# (Nano Banana); решта кадрів — дешевшим BEATS_IMAGE_PROVIDER (за замовч. fal/FLUX).
HERO_IMAGE_SECONDS = float(os.environ.get("HERO_IMAGE_SECONDS") or 40)

# Жодне фото не показується довше цього: "still"-сегмент, озвучений довше за STILL_MAX_SECONDS, отримує
# КІЛЬКА РІЗНИХ згенерованих кадрів (app/stages/visual_generate.py) замість одного фото з трюками навколо
# напрямку камери — за фідбеком показ однієї картинки довше кількох секунд виглядає погано, навіть із
# рухом. Дорожче (більше викликів генератора картинок), але саме так і просили: більше генерацій, краща
# картинка. Ken Burns (video_assemble.py) лишається — по одному незмінному напрямку на кожне фото.
STILL_MAX_SECONDS = float(os.environ.get("STILL_MAX_SECONDS") or 8.0)  # було 6.0; 8.0 з 2026-10-04 (все-Google кадри дешевші, ніж гібрид з FLUX)
# Допуск перед тим, як ділити довгий план на 2 фото: 7.5с лишається ОДНИМ фото (з рухом камери), а не
# двома по 3.7с — кожне зайве фото це гроші. Див. _visuals.beats_needed().
STILL_OVERRUN_TOLERANCE_SECONDS = float(os.environ.get("STILL_OVERRUN_TOLERANCE_SECONDS") or 1.5)

# Пауза тиші перед першим словом озвучки — глядач встигає побачити перший кадр/прев'ю-подібну картинку,
# перш ніж почує голос (з фідбеку: озвучка "з нуля" відчувається різко). 0 = без паузи.
INTRO_SILENCE_SECONDS = float(os.environ.get("INTRO_SILENCE_SECONDS") or 1.0)

# Фонові SFX-петлі (app/sfx.py, kind="ambience") вимкнено за дефолтом: перевірка спектрограмою показала, що
# ElevenLabs Sound Generation для тривалих (22с) фонових текстур майже завжди повертає суцільний широкосмуговий
# шум без пауз (не окрема хиба одного тегу — це системно на всій бібліотеці, включно з тегами, які не мають нічого
# спільного з Veo/кліпами). loudnorm лише піднімає цей шум до чутного рівня. Короткі акцентні ефекти (0-4с,
# прив'язані до конкретної події в тексті) лишаються — вони рідкісні й проходять під голосом, а не лунають
# безперервно. Перш ніж вмикати фони знову — потрібен або інший підхід до генерації (afftdn зменшує, але не
# прибирає), або їхня заміна на бібліотеку з реальних (ліцензійно чистих) ambience-семплів.
USE_SFX_BEDS = (os.environ.get("USE_SFX_BEDS") or "0") != "0"

# SFX_PRESENCE: наскільки чутні ефекти — "subtle" (≈ -23 дБ відносно голосу: майже нечутні), "balanced" (≈ -19 дБ),
# "present" (≈ -13 дБ, за замовчуванням: чутні, але підпорядковані голосу). Виміряно на реальному відео.
# Кортеж: (акценти, фон, звук кліпів, ratio ducking-компресора; менше ratio = слабше глушіння під голосом).
_SFX_PRESETS = {"subtle": (-6, -13, -8, 9), "balanced": (-3, -9, -5, 5), "present": (0, -6, -3, 3)}
_accent, _bed, _clip, _ratio = _SFX_PRESETS.get(os.environ.get("SFX_PRESENCE") or "present", _SFX_PRESETS["present"])
SFX_ACCENT_GAIN_DB = float(os.environ.get("SFX_ACCENT_GAIN_DB") or _accent)
SFX_BED_GAIN_DB = float(os.environ.get("SFX_BED_GAIN_DB") or _bed)
SFX_DUCK_RATIO = float(os.environ.get("SFX_DUCK_RATIO") or _ratio)

# Монтаж: звук із самих Veo-кліпів (природні шуми сцени; входить у ціну кліпу) тихим шаром під озвучкою,
# перехід-розчинення між сегментами (0 = різкі склейки), титул на початку відео (0 = без титулу).
# Дефолт вимкнено (було 1): на тестовому відео звук із Veo-кліпів звучав як неприємний білий шум —
# відомий недолік AI-генерованого звуку відео, особливо на "тихих" ambient-сценах без діалогу. Своя
# бібліотека SFX (app/sfx.py) підібрана й перевірена вручну, тому нею й обходимось.
USE_CLIP_AUDIO = (os.environ.get("USE_CLIP_AUDIO") or "0") != "0"
CLIP_AUDIO_GAIN_DB = float(os.environ.get("CLIP_AUDIO_GAIN_DB") or _clip)
TRANSITION_SECONDS = float(os.environ.get("TRANSITION_SECONDS") or 0.5)
INTRO_TITLE_SECONDS = float(os.environ.get("INTRO_TITLE_SECONDS") or 4.5)
OVERLAY_FONT = os.environ.get("OVERLAY_FONT") or ""  # шлях до .ttf для титулу/підписів; порожньо = шукати системний

# Пил у променях світла поверх усього відео (app/fx.py) — безкоштовна "жива" накладка для статичних планів.
USE_DUST_OVERLAY = (os.environ.get("USE_DUST_OVERLAY") or "1") != "0"
DUST_OPACITY = float(os.environ.get("DUST_OPACITY") or 0.30)

# Фонова музика (app/music.py): користувацькі треки з storage/music_library/ або власний процедурний ембієнт
# (без правовласників). MUSIC_LUFS — гучність відносно голосу (голос -16 LUFS; -29 ≈ 13 дБ тихіше, і ще
# притискається ducking'ом під диктором).
USE_MUSIC = (os.environ.get("USE_MUSIC") or "1") != "0"
MUSIC_LUFS = float(os.environ.get("MUSIC_LUFS") or -29)

# Параметри відео на виході (Veo 3.1 Lite віддає 720p/24fps — не роздуваємо штучно).
VIDEO_WIDTH, VIDEO_HEIGHT, VIDEO_FPS = 1280, 720, 24

# Скільки "слів на хвилину" закладаємо для оцінки тривалості озвучки (орієнтир TTS-стабів
# і планування довжини сценарію).
WORDS_PER_MINUTE = 150
