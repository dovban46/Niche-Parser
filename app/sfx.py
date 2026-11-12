"""Бібліотека звукових ефектів: акценти (тятива, штурм) і фонові шари (вітер, табір, гул бою).

Ефекти генеруються ОДИН раз через ElevenLabs Sound Effects (~$0.02 за ефект, той самий ключ, що й
озвучка), нормалізуються до -23 LUFS і кладуться в storage/sfx_library/ — далі переиспользуються
всіма відео безкоштовно й переживають видалення job'ів. Запуск:
    python -m app.tools.build_sfx_library
"""

import os
from dataclasses import dataclass
from pathlib import Path

import requests

from .config import SFX_ROOT
from .ffutil import error_tail, have_ffmpeg, probe_duration, run_ffmpeg
from .providers.base import ProviderConfigError

_API_URL = "https://api.elevenlabs.io/v1/sound-generation"
_AMBIENCE_SECONDS = 22.0  # максимум, який дає API; зациклюється безшовно


@dataclass(frozen=True)
class SfxDef:
    tag: str
    kind: str  # "accent" | "ambience"
    prompt: str
    duration: float


_NO_MUSIC = ", no music, no speech"

CATALOG: dict[str, SfxDef] = {d.tag: d for d in [
    SfxDef("bow_draw", "accent", "Wooden longbow being slowly drawn back, creaking wood and taut string tension" + _NO_MUSIC, 3),
    SfxDef("arrow_volley", "accent", "A volley of arrows whooshing through the air and thudding into wood and earth" + _NO_MUSIC, 4),
    SfxDef("siege_ladder", "accent", "Heavy wooden siege ladder thudding against a stone castle wall, wood creaking", 4),
    SfxDef("wall_clash", "accent", "Muffled distant clash of swords and shields at a castle wall, faint far-away shouting", 5),
    SfxDef("battering_ram", "accent", "Heavy battering ram booming against a wooden castle gate, deep thud, wood splintering", 4),
    SfxDef("trebuchet", "accent", "Wooden trebuchet creaking then releasing with a whoosh, followed by a distant stone crash", 5),
    SfxDef("stone_impact", "accent", "Large stone smashing into a castle wall, deep impact and crumbling rubble", 3),
    SfxDef("horse_gallop", "accent", "A group of horses galloping across dirt ground, hooves pounding, harness jingling", 5),
    SfxDef("war_horn", "accent", "Deep medieval war horn blast in the distance, echoing across a valley", 4),
    SfxDef("army_march", "accent", "Armored soldiers marching in step on gravel, metal armor clinking, spears knocking", 5),
    SfxDef("war_drums", "accent", "Slow deep medieval war drum beats, ominous, reverberating" + _NO_MUSIC.replace(", no music", ""), 5),
    SfxDef("battle_cry", "accent", "Distant crowd of soldiers roaring a battle cry across a field, muffled by distance", 4),
    SfxDef("banner_flap", "accent", "Large cloth banner flapping in strong wind", 4),
    SfxDef("fire_burst", "accent", "Torches and flaming arrows igniting, fire whoosh and crackle", 3),
    SfxDef("amb_wind", "ambience", "Steady wind blowing across an open grassy field, clearly audible gusts and rustling grass, distant birds, outdoor ambience" + _NO_MUSIC, _AMBIENCE_SECONDS),
    SfxDef("amb_camp", "ambience", "Medieval army camp at night, quiet crackling campfire, low murmuring of men, distant horse snort" + _NO_MUSIC, _AMBIENCE_SECONDS),
    SfxDef("amb_battle_far", "ambience", "Distant medieval battlefield ambience, faint muffled clashing of metal and far-off shouting, low war drums, wind" + _NO_MUSIC, _AMBIENCE_SECONDS),
    SfxDef("amb_siege", "ambience", "Ambience near a besieged castle, distant crowd roar, occasional dull thuds against stone, wind" + _NO_MUSIC, _AMBIENCE_SECONDS),
    # ancient_mysteries: заборонені книги/апокрифи/давні таємниці (archive, ruins, crypt, monastery)
    SfxDef("page_turn", "accent", "An old heavy book page being turned slowly, dry aged paper rustling" + _NO_MUSIC, 3),
    SfxDef("quill_scratch", "accent", "A quill pen scratching slowly across parchment, close and intimate" + _NO_MUSIC, 4),
    SfxDef("book_thud", "accent", "A large heavy old book being closed or set down on a wooden table, dull thud and paper flutter" + _NO_MUSIC, 3),
    SfxDef("wax_seal", "accent", "A wax seal being pressed onto a letter, soft sizzle and stamp thud" + _NO_MUSIC, 3),
    SfxDef("distant_bell", "accent", "A single deep monastery bell tolling once, echoing into distance" + _NO_MUSIC, 5),
    SfxDef("thunder_rumble", "accent", "Slow distant thunder rumbling across the sky" + _NO_MUSIC, 5),
    SfxDef("stone_door", "accent", "A heavy ancient stone door grinding slowly open, deep scraping rock" + _NO_MUSIC, 4),
    SfxDef("torch_ignite", "accent", "A torch catching fire and starting to burn, whoosh and steady crackle" + _NO_MUSIC, 3),
    # explainer (мультяшний формат): короткі ефекти для монтажу
    SfxDef("x_whoosh", "accent", "A fast clean cartoon whoosh swipe, air movement, short" + _NO_MUSIC, 1),
    SfxDef("x_pop", "accent", "A short bubbly cartoon pop sound, cheerful" + _NO_MUSIC, 1),
    SfxDef("x_ding", "accent", "A bright single bell ding notification chime, clean" + _NO_MUSIC, 1.5),
    SfxDef("x_boing", "accent", "A comedic cartoon spring boing, bouncy" + _NO_MUSIC, 1.5),
    SfxDef("x_record_scratch", "accent", "A vinyl record scratch stop, comedic" + _NO_MUSIC, 1.5),
    SfxDef("x_sting", "accent", "A short dramatic orchestral hit stinger, deep boom with tension rise, no speech", 2.5),
    SfxDef("x_magic", "accent", "A magical sparkle chime glissando, shimmering, uplifting" + _NO_MUSIC, 2.5),
    SfxDef("x_gulp", "accent", "A comedic big gulp swallow sound with a cartoon chomp" + _NO_MUSIC, 1.5),
    SfxDef("x_thud", "accent", "A heavy comedic thud, something big landing on the ground" + _NO_MUSIC, 1.5),
    SfxDef("x_gasp", "accent", "A crowd of people gasping in surprise, short, no music", 2),
    SfxDef("x_tada", "accent", "A short triumphant fanfare ta-da with trumpets, no speech", 2.5),
    SfxDef("x_tick", "accent", "A single sharp tick of a stopwatch clock, dry" + _NO_MUSIC, 1),
    SfxDef("x_swipe_paper", "accent", "A fast paper swipe flick, light rustle" + _NO_MUSIC, 1),
    SfxDef("x_riser", "accent", "A rising cinematic tension riser sweep building up, short, no music, no speech", 3),
    SfxDef("x_boom", "accent", "A deep cinematic bass boom impact with short tail, no music, no speech", 2),
    SfxDef("x_glitch", "accent", "A short digital glitch stutter sound, no music, no speech", 1),
    SfxDef("x_click", "accent", "A crisp short UI click tick sound, no music, no speech", 1),
    SfxDef("x_swish", "accent", "A very fast short air swish, light, no music, no speech", 1),
    SfxDef("x_ping_up", "accent", "A short bright rising ping chime, magical sparkle, no music, no speech", 1.5),
    SfxDef("amb_library", "ambience", "Ancient candlelit archive or scriptorium at night, soft candle flicker, faint paper rustle, deep silence" + _NO_MUSIC, _AMBIENCE_SECONDS),
    SfxDef("amb_ruins", "ambience", "Wind blowing softly through ancient stone ruins, distant faint echo, no birds" + _NO_MUSIC, _AMBIENCE_SECONDS),
    SfxDef("amb_crypt", "ambience", "Damp underground crypt or vault ambience, slow water drips, long stone echo, oppressive silence" + _NO_MUSIC, _AMBIENCE_SECONDS),
    SfxDef("amb_monastery", "ambience", "Distant monastery ambience at dusk, faint low chanting, soft wind, occasional far bell" + _NO_MUSIC, _AMBIENCE_SECONDS),
]}


def path_for(tag: str) -> Path:
    return SFX_ROOT / f"{tag}.mp3"


def available_tags(kind: str) -> list[str]:
    return [t for t, d in CATALOG.items() if d.kind == kind and path_for(t).exists()]


def missing_tags() -> list[str]:
    return [t for t in CATALOG if not path_for(t).exists()]


def build_library(only: list[str] | None = None, force: bool = False, log=print) -> dict:
    """Генерує відсутні ефекти. Повертає {"generated": [...], "skipped": [...], "failed": {tag: причина}}."""
    api_key = os.environ.get("ELEVENLABS_API_KEY")
    if not api_key:
        raise ProviderConfigError("ELEVENLABS_API_KEY не знайдено в .env — потрібен для генерації ефектів.")
    if not have_ffmpeg():
        raise ProviderConfigError("ffmpeg/ffprobe не знайдено в PATH — потрібні для нормалізації ефектів.")

    SFX_ROOT.mkdir(parents=True, exist_ok=True)
    result = {"generated": [], "skipped": [], "failed": {}}
    for tag in (only or list(CATALOG)):
        definition = CATALOG.get(tag)
        if definition is None:
            result["failed"][tag] = "невідомий тег"
            continue
        if path_for(tag).exists() and not force:
            result["skipped"].append(tag)
            continue
        try:
            log(f"генерую {tag} ({definition.kind}, {definition.duration:g} с) …")
            raw = SFX_ROOT / f"_{tag}.raw.mp3"
            raw.write_bytes(_generate(api_key, definition))
            _finalize(raw, path_for(tag), seamless=definition.kind == "ambience")
            raw.unlink(missing_ok=True)
            result["generated"].append(tag)
        except (ProviderConfigError, OSError, RuntimeError) as exc:
            result["failed"][tag] = str(exc)
            log(f"  ! {tag}: {exc}")
    return result


def _generate(api_key: str, definition: SfxDef) -> bytes:
    response = requests.post(
        _API_URL,
        headers={"xi-api-key": api_key, "Content-Type": "application/json", "Accept": "audio/mpeg"},
        json={"text": definition.prompt, "duration_seconds": definition.duration, "prompt_influence": 0.4},
        timeout=180,
    )
    if response.status_code != 200:
        raise ProviderConfigError(f"ElevenLabs Sound Effects помилка {response.status_code}: {response.text[:200]}")
    return response.content


def _finalize(raw: Path, final: Path, seamless: bool) -> None:
    """Нормалізація до -23 LUFS; для фонів — безшовна петля (друга половина + перша з кросфейдом)."""
    import subprocess

    try:
        if seamless:
            duration = probe_duration(raw) or _AMBIENCE_SECONDS
            half = duration / 2
            fade = min(2.0, half / 2)
            graph = (
                f"[0:a]asplit=2[a][b];[a]atrim=0:{half:.3f},asetpts=PTS-STARTPTS[h1];"
                f"[b]atrim={half:.3f}:{duration:.3f},asetpts=PTS-STARTPTS[h2];"
                f"[h2][h1]acrossfade=d={fade:.2f}:c1=tri:c2=tri,loudnorm=I=-23:TP=-2:LRA=7,aresample=44100[out]"
            )
            run_ffmpeg(["-i", str(raw), "-filter_complex", graph, "-map", "[out]", "-c:a", "libmp3lame", "-q:a", "3", str(final)])
        else:
            run_ffmpeg([
                "-i", str(raw), "-af", "afade=t=in:d=0.02,loudnorm=I=-23:TP=-2:LRA=7,aresample=44100",
                "-c:a", "libmp3lame", "-q:a", "3", str(final),
            ])
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"ffmpeg: {error_tail(exc)}") from exc
