"""Звукова доріжка: озвучка + фон + акценти. Диктор завжди головний — ефекти лише доповнюють:
1. кожен шар має низьку базову гучність (config.SFX_ACCENT_GAIN_DB / SFX_BED_GAIN_DB);
2. sidechain-компресор (ducking) додатково притискає ВСІ ефекти щоразу, коли говорить диктор;
3. loudnorm вирівнює ТІЛЬКИ голос (-16 LUFS) ще до мікшування; ефекти змішуються відносно нього, а наприкінці стоїть
   лише обмежувач — loudnorm на підсумку працює як автопідсилення і піднімав би ефекти в паузах між реченнями.
"""

import json
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from . import sfx
from .config import CLIP_AUDIO_GAIN_DB, SFX_ACCENT_GAIN_DB, SFX_BED_GAIN_DB, SFX_DUCK_RATIO, USE_SFX_BEDS
from .ffutil import error_tail, run_ffmpeg

_ACCENT_OFFSET_S = 0.4  # перший акцент — трохи після початку репліки, а не впритул до першого слова
_BED_OVERLAP_S = 1.5  # запас на кросфейд між сусідніми фонами


@dataclass
class Layer:
    path: Path
    start_s: float
    gain_db: float
    loop: bool = False
    length_s: float | None = None  # обов'язково для loop
    fade_in_s: float = 0.03
    fade_out_s: float = 0.3
    kind: str = "accent"  # "accent" | "bed" | "clip" — лише для статистики


def plan_layers(
    segments: list[dict],
    starts_s: list[float],
    durations_s: list[float],
    clip_audio: dict[int, Path] | None = None,
) -> tuple[list[Layer], dict]:
    """Перетворює розкадрування (теги в сегментах) на шари. Теги без файлу в бібліотеці пропускає
    (і повертає в info["missing"]) — відео збереться й без них. clip_audio[i] — нормалізований звук
    Veo-кліпу сегмента i (природні шуми сцени): кладеться тихим шаром на весь сегмент."""
    layers: list[Layer] = []
    for i, path in (clip_audio or {}).items():
        layers.append(Layer(path, starts_s[i], CLIP_AUDIO_GAIN_DB, length_s=durations_s[i] + 0.3,
                            fade_in_s=0.3, fade_out_s=0.5, kind="clip"))
    missing: set[str] = set()
    bed_tag, bed_start = "", 0.0
    beds: list[tuple[str, float, float]] = []  # (tag, start, end)

    for seg, start, dur in zip(segments, starts_s, durations_s):
        tags = json.loads(seg.get("sfx_tags") or "[]")
        for i, tag in enumerate(tags[:2]):
            if not sfx.path_for(tag).exists():
                missing.add(tag)
                continue
            offset = _ACCENT_OFFSET_S if i == 0 else max(_ACCENT_OFFSET_S, dur * 0.55)
            layers.append(Layer(sfx.path_for(tag), start + min(offset, max(dur - 0.5, 0)), SFX_ACCENT_GAIN_DB))

        if USE_SFX_BEDS:
            tag = (seg.get("ambience_tag") or "").strip()
            if tag and tag != bed_tag:
                if bed_tag:
                    beds.append((bed_tag, bed_start, start))
                bed_tag, bed_start = tag, start
    end_total = (starts_s[-1] + durations_s[-1]) if starts_s else 0.0
    if USE_SFX_BEDS:
        if bed_tag:
            beds.append((bed_tag, bed_start, end_total))
        elif starts_s:
            # Розкадрування не задало фону — кладемо один загальний, щоб відео не було "голим" між акцентами.
            available = sfx.available_tags("ambience")
            if available:
                beds.append(("amb_wind" if "amb_wind" in available else available[0], 0.0, end_total))

    for tag, b_start, b_end in beds:
        if not sfx.path_for(tag).exists():
            missing.add(tag)
            continue
        start = max(0.0, b_start - _BED_OVERLAP_S / 2)
        layers.append(
            Layer(sfx.path_for(tag), start, SFX_BED_GAIN_DB, loop=True, length_s=(b_end - start) + _BED_OVERLAP_S,
                  fade_in_s=_BED_OVERLAP_S, fade_out_s=_BED_OVERLAP_S, kind="bed")
        )
    return layers, {"accents": sum(1 for l in layers if l.kind == "accent"), "beds": sum(1 for l in layers if l.kind == "bed"),
                    "clip_audio": sum(1 for l in layers if l.kind == "clip"), "missing": sorted(missing)}


def mix_soundtrack(narration: Path, total_s: float, layers: list[Layer], out_path: Path, lead_s: float = 0.0) -> None:
    """Пише out_path (AAC): озвучка + шари з ducking і вирівнюванням гучності. `lead_s` — тиша перед першим
    словом (glядач встигає побачити перший кадр, перш ніж почує голос); шари вже приходять зсунутими на
    ту саму величину (video_assemble рахує їхні `start_s` від starts_padded), тут зсувається лише голос."""
    fmt = "aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo"
    inputs: list[list[str]] = [["-i", str(narration)]]
    file_index: dict[tuple[Path, bool], int] = {}
    placements: dict[int, list[int]] = {}
    for n, layer in enumerate(layers):
        key = (layer.path, layer.loop)
        if key not in file_index:
            file_index[key] = len(inputs)
            inputs.append((["-stream_loop", "-1"] if layer.loop else []) + ["-i", str(layer.path)])
        placements.setdefault(file_index[key], []).append(n)

    lines: list[str] = []
    # loudnorm віддає 192 кГц — повертаємо 44.1; adelay зсуває вступ на lead_s (0 = без затримки, як і було)
    voice = f"[0:a]{fmt},loudnorm=I=-16:TP=-1.5:LRA=11,aresample=44100,{fmt},adelay={round(lead_s * 1000)}:all=1"
    if layers:
        lines.append(f"{voice},asplit=2[nv][ns]")
    else:
        lines.append(f"{voice}[nv]")

    for idx, layer_ids in placements.items():
        outs = [f"[f{idx}_{j}]" for j in range(len(layer_ids))]
        lines.append(f"[{idx}:a]{fmt}" + (f",asplit={len(outs)}{''.join(outs)}" if len(outs) > 1 else outs[0]))

    layer_labels: list[str] = []
    for idx, layer_ids in placements.items():
        for j, n in enumerate(layer_ids):
            layer = layers[n]
            chain = []
            if layer.length_s is not None:
                chain.append(f"atrim=0:{layer.length_s:.3f},asetpts=PTS-STARTPTS")
            chain.append(f"afade=t=in:d={layer.fade_in_s:.2f}")
            if layer.length_s is not None:
                chain.append(f"afade=t=out:st={max(layer.length_s - layer.fade_out_s, 0):.3f}:d={layer.fade_out_s:.2f}")
            chain.append(f"volume={layer.gain_db:.1f}dB")
            chain.append(f"adelay={int(layer.start_s * 1000)}:all=1")
            lines.append(f"[f{idx}_{j}]{','.join(chain)}[L{n}]")
            layer_labels.append(f"[L{n}]")

    fades = f"afade=t=in:d=0.2,afade=t=out:st={max(total_s - 1.2, 0):.3f}:d=1.2"
    tail = f"alimiter=limit=0.94,{fades},atrim=0:{total_s:.3f}[out]"
    if layers:
        lines.append(f"{''.join(layer_labels)}amix=inputs={len(layer_labels)}:normalize=0:duration=longest[bus]")
        lines.append(f"[bus][ns]sidechaincompress=threshold=0.02:ratio={SFX_DUCK_RATIO:g}:attack=20:release=450:makeup=1[duck]")
        lines.append(f"[nv][duck]amix=inputs=2:normalize=0:duration=first,{tail}")
    else:
        lines.append(f"[nv]{tail}")

    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as script:
        script.write(";\n".join(lines))
        script_path = script.name
    try:
        args = [a for inp in inputs for a in inp]
        run_ffmpeg([*args, "-filter_complex_script", script_path, "-map", "[out]", "-c:a", "aac", "-b:a", "192k", str(out_path)])
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"ffmpeg (мікс звуку): {error_tail(exc)}") from exc
    finally:
        Path(script_path).unlink(missing_ok=True)
