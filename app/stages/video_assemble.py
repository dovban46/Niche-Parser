import json
import re
import shutil
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .. import audio_mix, dossier, fx, music, overlays
from ..config import (
    DUST_OPACITY,
    INTRO_SILENCE_SECONDS,
    INTRO_TITLE_SECONDS,
    STORAGE_ROOT,
    TRANSITION_SECONDS,
    USE_CLIP_AUDIO,
    USE_DUST_OVERLAY,
    USE_MUSIC,
    VIDEO_FPS,
    VIDEO_HEIGHT,
    VIDEO_WIDTH,
    VIDEOS_ROOT,
    VISUAL_CONCURRENCY,
)
from ..ffutil import error_tail, have_ffmpeg, probe_duration, run_ffmpeg
from . import _visuals as v
from .base import StageContext, StageResult

_JOIN_BATCH = 12  # скільки шматків склеюється одним викликом ffmpeg (ланцюг xfade)

class VideoAssembleStage:
    """Монтаж: кожен озвучений сегмент → відеошматок (AI-кліп, підігнаний під озвучку, або стоп-кадр із повільним
    Ken Burns) → склейка з розчиненням між сегментами → єдина кольорова обробка стилю, титул на початку, тихий
    підпис під час прохання підписатися, плавний вхід/вихід → звукова доріжка (озвучка + тихі звуки сцени й ефекти
    з ducking). Готовий mp4 лягає в VIDEOS_ROOT; шлях у БД — відносно нього.

    Проміжні шматки кодуються майже без втрат, а обробка й фінальне стиснення робляться один раз наприкінці —
    так відео не проходить кілька поколінь стиснення."""

    name = "video_assemble"

    def run(self, ctx: StageContext) -> StageResult:
        segments = [s for s in ctx.repo.list_segments(ctx.job_id) if s["audio_path"] and s["duration_ms"]]
        if not segments:
            return StageResult(status="failed", error="Немає озвучених сегментів для збірки.")

        manifest = {
            "segment_count": len(segments),
            "total_duration_ms": sum(s["duration_ms"] for s in segments),
            "segments": [
                {
                    "index": s["segment_index"], "audio_path": s["audio_path"], "visual_path": s["visual_path"],
                    "clip_path": s["visual_clip_path"], "visual_type": s["visual_type"], "sfx": s["sfx_tags"],
                    "ambience": s["ambience_tag"], "cta": bool(s["is_cta"]), "duration_ms": s["duration_ms"],
                    "start_ms": s["start_ms"],
                }
                for s in segments
            ],
        }
        path = ctx.storage.video_dir() / "assembly_manifest.json"
        path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        output = {"manifest_path": ctx.storage.relative(path), "total_duration_ms": manifest["total_duration_ms"]}

        not_ready = [s["segment_index"] for s in segments if not v.exists(s["visual_path"])]
        if not_ready:
            output["segments_missing_visual"] = not_ready
            return StageResult(status="needs_review", output=output)

        narration = _find_narration(ctx)
        if narration is None or not have_ffmpeg():
            output["note"] = "mp4 не зібрано: немає зведеної озвучки або ffmpeg/ffprobe не знайдено в PATH."
            return StageResult(status="success", output=output)

        try:
            final_rel, info = _render_video(ctx, segments, narration)
        except (subprocess.CalledProcessError, RuntimeError) as exc:
            detail = error_tail(exc) if isinstance(exc, subprocess.CalledProcessError) else str(exc)
            return StageResult(status="failed", error=f"Збірка відео: {detail}")

        ctx.repo.update_job(ctx.job_id, final_video_path=final_rel)
        output.update(info)
        output["final_video_path"] = final_rel
        return StageResult(status="success", output=output)


def _find_narration(ctx: StageContext) -> Path | None:
    for ext in ("mp3", "wav"):
        candidate = ctx.storage.audio_dir() / f"full_narration.{ext}"
        if candidate.exists():
            return candidate
    return None


def _slug(text: str) -> str:
    slug = re.sub(r"[\W_]+", "-", text.lower(), flags=re.UNICODE).strip("-")
    return slug[:50].strip("-") or "video"


def _job_title(ctx: StageContext) -> str:
    reviewed = ctx.storage.script_dir() / "reviewed_final.md"
    if reviewed.exists():
        for line in reviewed.read_text(encoding="utf-8").splitlines():
            if line.startswith("# "):
                return line[2:].strip()
    return ctx.job["topic"]


# ---------------------------------------------------------------- шматки


_KENBURNS_SCALE = "5760:3240"  # проміжний канвас для zoompan: більший за 3840x2160 (було) — менше помітне
                                # "тремтіння" від округлення пікселів на дрібних штрихах гравюрного стилю
_ZOOM_FLOOR = 1.03  # zoom НІКОЛИ не торкається рівно 1.0 — на цій межі zoompan інколи "оголює" край
                     # проскейленого канвасу (звідси й скарга "деколи з'являється рамка")
_BEAT_TRANSITION_SECONDS = 0.25  # маленьке розчинення між "беатами" (кількома фото одного сегмента)

# "u" (0..1, прогрес плану) підставляється в smoothstep (3u²-2u³) замість голого on/frames — рух
# розганяється й гальмує плавно, а не їде зі сталою швидкістю до різкого стопу в кінці плану (фідбек
# 2026-09-23: "плавно випливає, потім різко вирівнюється"). derivative smoothstep в 0 і 1 = 0.
def _eased(frames: int) -> str:
    return f"(3*pow(on/{frames},2)-2*pow(on/{frames},3))"


def _kenburns_filter(seed: int, frames: int, zoom: float | None = None) -> str:
    """ОДИН, сталий напрямок руху на весь `frames` (кадр/беат рендериться одним викликом, "подвійного
    напрямку" на одному фото не буває). 8 режимів: наїзд і віддалення в центр, наїзд у верхню/нижню "третину"
    кадру, панорами вліво/вправо, нахил угору, діагональний дрейф із віддаленням. Бюджетне рішення 2026-10-03:
    фото тепер ~6с замість ~3с, тож амплітуда руху росте з тривалістю (довший план = помітніший, але плавний
    рух), а сусідні плани за seed завжди різні — це компенсує довший показ кожного фото."""
    seconds = frames / VIDEO_FPS
    if zoom is None:
        zoom = min(0.17, max(0.07, 0.05 + 0.014 * seconds))
    mode = seed % 8
    lo, hi = _ZOOM_FLOOR, _ZOOM_FLOOR + zoom
    e = _eased(frames)
    cx, cy = "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    mid = f"{lo + zoom * 0.6:.4f}"
    if mode == 0:  # наїзд у центр
        z, x, y = f"{lo:.4f}+{zoom:.4f}*{e}", cx, cy
    elif mode == 1:  # віддалення від центру
        z, x, y = f"{hi:.4f}-{zoom:.4f}*{e}", cx, cy
    elif mode == 2:  # панорама вправо
        z, x, y = mid, f"(iw-iw/zoom)*{e}", cy
    elif mode == 3:  # панорама вліво
        z, x, y = mid, f"(iw-iw/zoom)*(1-{e})", cy
    elif mode == 4:  # наїзд у верхню ліву третину
        z, x, y = f"{lo:.4f}+{zoom:.4f}*{e}", "(iw-iw/zoom)*0.33", "(ih-ih/zoom)*0.30"
    elif mode == 5:  # наїзд у нижню праву третину
        z, x, y = f"{lo:.4f}+{zoom:.4f}*{e}", "(iw-iw/zoom)*0.68", "(ih-ih/zoom)*0.70"
    elif mode == 6:  # нахил угору
        z, x, y = mid, cx, f"(ih-ih/zoom)*(1-{e})"
    else:  # діагональний дрейф із віддаленням
        z, x, y = f"{hi:.4f}-{zoom:.4f}*{e}", f"(iw-iw/zoom)*(0.35+0.30*{e})", f"(ih-ih/zoom)*(0.60-0.30*{e})"
    return (
        f"scale={_KENBURNS_SCALE}:force_original_aspect_ratio=increase,crop={_KENBURNS_SCALE},"
        f"zoompan=z='{z}':x='{x}':y='{y}':d={frames}:s={VIDEO_WIDTH}x{VIDEO_HEIGHT}:fps={VIDEO_FPS}"
    )


def _render_still(images: list[Path], index: int, frames: int, out: Path, common: list[str]) -> None:
    """Один чи кілька РІЗНИХ кадрів → відео. Кожне зображення в списку — своє окреме фото (з visual_generate:
    довгий план отримує кілька різних кадрів замість одного, п.9 фідбеку), кожне рендериться ОДНИМ викликом
    _kenburns_filter (один незмінний напрямок на все своє фото) і склеюється різким стиком — зміна кадру
    щонайдовше раз на STILL_MAX_SECONDS, а не трюк з рухом камери на тій самій картинці."""
    n = len(images)
    if n == 1:
        vf = f"{_kenburns_filter(index, frames)},format=yuv420p"
        run_ffmpeg(["-i", str(images[0]), "-vf", vf, "-frames:v", str(frames), *common])
        return

    # Рівний поділ кадрів між фото (не "макс, а решта окремим куцим шматком"). Стик між фото —
    # маленьке розчинення (не різкий concat): різкий стик після плавного руху камери й давав ефект
    # "плавно їхало — потім різко вирівнялось" (фідбек 2026-09-23), хай навіть фото інші.
    base, extra = divmod(frames, n)
    seed = index * 7
    half = round(_BEAT_TRANSITION_SECONDS * VIDEO_FPS / 2)
    # Власна підпапка на цей сегмент — _join_parts пише проміжні join_*.mp4 з іменами, що повторюються
    # між викликами; кілька сегментів рендеряться паралельно (ThreadPoolExecutor), тож без ізоляції
    # вони затирали б файли одне одного.
    work = out.parent / f"{out.stem}_beats"
    work.mkdir(parents=True, exist_ok=True)
    sub_paths, sub_frames = [], []
    try:
        for i, image in enumerate(images):
            n_frames = base + (1 if i < extra else 0)
            pad = (half if i > 0 else 0) + (half if i < n - 1 else 0)
            sub_out = work / f"sub{i}{out.suffix}"
            vf = f"{_kenburns_filter(seed + i, n_frames + pad)},format=yuv420p"
            run_ffmpeg(["-i", str(image), "-vf", vf, "-frames:v", str(n_frames + pad), *common[:-1], str(sub_out)])
            sub_paths.append(sub_out)
            sub_frames.append(n_frames + pad)
        _join_parts(sub_paths, sub_frames, half, work, out)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _render_part(seg: dict, index: int, frames: int, out: Path) -> str:
    """Один сегмент → відео рівно `frames` кадрів. Повертає "clip" або "still"."""
    seconds = frames / VIDEO_FPS
    clip = STORAGE_ROOT / seg["visual_clip_path"] if v.exists(seg["visual_clip_path"]) else None
    common = ["-r", str(VIDEO_FPS), "-c:v", "libx264", "-preset", "veryfast",
              "-crf", "16", "-pix_fmt", "yuv420p", "-an", str(out)]
    if clip is not None:
        clip_len = probe_duration(clip) or seconds
        slow = min(seconds / clip_len, 1.3) if clip_len < seconds else 1.0  # коротший кліп трохи розтягуємо, решту — заморожений кінець
        # stop_duration МАЄ покривати весь залишок сегмента, інакше tpad вичерпується раніше, ніж
        # -frames:v дораховує кадри, і ffmpeg тихо (exit 0!) віддає КОРОТШИЙ файл, ніж треба — далі
        # xfade в _join_parts на цьому "з'їдає" решту відео без жодної помилки (знайдено 2026-09-29,
        # job 10: Veo-кліп 8с розтягнутий на сегмент 17-19с при фіксованому stop_duration=4 обрізав
        # відео на середині). +1с запасу поверх точного залишку.
        stop_duration = max(4.0, seconds - clip_len * slow + 1.0)
        vf = (
            f"setpts={slow:.4f}*PTS,fps={VIDEO_FPS},scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}:force_original_aspect_ratio=increase,"
            f"crop={VIDEO_WIDTH}:{VIDEO_HEIGHT},tpad=stop_mode=clone:stop_duration={stop_duration:.3f},format=yuv420p"
        )
        run_ffmpeg(["-i", str(clip), "-vf", vf, "-frames:v", str(frames), *common])
        return "clip"
    images = _still_images(seg)
    _render_still(images, index, frames, out, common)
    return "still"


def _still_images(seg: dict) -> list[Path]:
    """Список фото для "still"-сегмента: кілька з beats_json (visual_generate — довгий план), або
    одне з visual_path (короткий план чи fallback, коли Veo-кліп не вдався)."""
    raw = seg.get("beats_json")
    if raw:
        try:
            beats = json.loads(raw)
        except json.JSONDecodeError:
            beats = []
        paths = [STORAGE_ROOT / b["path"] for b in beats if v.exists(b.get("path"))]
        if paths:
            return paths
    return [STORAGE_ROOT / seg["visual_path"]]


# ---------------------------------------------------------------- склейка


def _write_script(text: str) -> Path:
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as fh:
        fh.write(text)
    return Path(fh.name)


def _xfade_join(parts: list[tuple[Path, int]], d_frames: int, out: Path) -> int:
    """Склеює шматки розчиненням тривалістю d_frames. Кожен шматок (крім країв) має d/2 "запасу" з обох боків, тож
    сумарна тривалість = сума чистих тривалостей сегментів. Повертає кількість кадрів результату."""
    if len(parts) == 1:
        shutil.copy(parts[0][0], out)
        return parts[0][1]
    lines = [f"[{k}:v]settb=AVTB,setpts=PTS-STARTPTS,fps={VIDEO_FPS},format=yuv420p[v{k}]" for k in range(len(parts))]
    prev, acc = "[v0]", parts[0][1]
    for k in range(1, len(parts)):
        label = f"[x{k}]"
        lines.append(
            f"{prev}[v{k}]xfade=transition=fade:duration={d_frames / VIDEO_FPS:.5f}:offset={(acc - d_frames) / VIDEO_FPS:.5f}{label}"
        )
        prev, acc = label, acc + parts[k][1] - d_frames
    script = _write_script(";\n".join(lines))
    try:
        args = [a for p, _ in parts for a in ("-i", str(p))]
        run_ffmpeg([*args, "-filter_complex_script", str(script), "-map", prev, "-c:v", "libx264", "-preset", "veryfast",
                    "-crf", "16", "-pix_fmt", "yuv420p", "-r", str(VIDEO_FPS), str(out)])
    finally:
        script.unlink(missing_ok=True)
    return acc


def _join_parts(parts: list[Path], frame_counts: list[int], half: int, work: Path, out: Path) -> None:
    if half == 0:  # різкі склейки: без перекодування
        script = _write_script("".join(f"file '{p.resolve().as_posix()}'\n" for p in parts))
        try:
            run_ffmpeg(["-f", "concat", "-safe", "0", "-i", str(script), "-c", "copy", str(out)])
        finally:
            script.unlink(missing_ok=True)
        return

    items = list(zip(parts, frame_counts))
    level = 0
    while len(items) > 1:
        next_items = []
        for g in range(0, len(items), _JOIN_BATCH):
            group = items[g:g + _JOIN_BATCH]
            joined = work / f"join_{level}_{g // _JOIN_BATCH:03d}.mp4"
            frames = _xfade_join(group, 2 * half, joined)
            next_items.append((joined, frames))
        items, level = next_items, level + 1
    shutil.move(str(items[0][0]), str(out))


# ---------------------------------------------------------------- звук кліпів і накладки


def _clip_audio(clip: Path, out: Path) -> bool:
    """Звук Veo-кліпу → нормалізований wav. Порожній/майже тихий звук пропускаємо (loudnorm роздув би шум)."""
    probe = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(clip), "-vn", "-af", "volumedetect", "-f", "null", "-"],
        capture_output=True, text=True,
    )
    match = re.search(r"mean_volume:\s*(-?[\d.]+) dB", probe.stderr)
    if not match or float(match.group(1)) < -50:
        return False
    run_ffmpeg(["-i", str(clip), "-vn", "-af", "loudnorm=I=-23:TP=-2:LRA=7,aresample=44100", "-ac", "2", str(out)])
    return True


_INTRO_STYLES = ["classic", "lower_third", "cold_open"]


def _intro_style(ctx: StageContext) -> str:
    """Стиль початку відео: classic (титул-картка одразу), lower_third (скромний підпис унизу ліворуч),
    cold_open (спершу лише сцена, титул після гачка). Щоб відео не мали однаковий початок: явно через
    config job'а ("intro_style"), інакше обертається за id job'а."""
    chosen = (ctx.config or {}).get("intro_style")
    return chosen if chosen in _INTRO_STYLES else _INTRO_STYLES[ctx.job_id % len(_INTRO_STYLES)]


def _overlay_graph(ctx: StageContext, work: Path, segments: list[dict], starts: list[float], durations: list[float],
                   total_s: float, grade: str) -> tuple[list[str], str, dict]:
    """Фінальний фільтр-граф: кольорова обробка → титул на початку → підпис-CTA → вхід із чорного/вихід у чорне.
    Накладки — PNG з app/overlays.py; ffmpeg лише плавно вмикає їх (fade + невеликий зсув). Файли лежать у work,
    а ffmpeg запускається з cwd=work — у графі лише відносні імена. Повертає (додаткові вхідні аргументи, граф, інфо)."""
    inputs = ["-i", "joined.mp4", "-i", "soundtrack.m4a"]
    dust = None
    if USE_DUST_OVERLAY:
        try:
            dust = fx.ensure_dust_loop(STORAGE_ROOT / "fx" / "dust_loop.mp4")
        except Exception:  # накладка — прикраса, не причина валити збірку відео
            dust = None
    if dust is not None:
        # ВАЖЛИВО: змішуємо в RGB (gbrp) — screen у YUV зсуває хроматичні канали й фарбує ВСЕ відео в пурпур
        # (знайдено на job 13). Пил у променях світла (screen поверх усього відео) + дуже повільне "дихання" яскравості: довші
        # статичні плани лишаються живими без жодної платної генерації.
        inputs += ["-stream_loop", "-1", "-i", str(dust)]
        lines = [
            f"[0:v]{grade},eq=brightness='0.012*sin(2*PI*t*0.37)':eval=frame,format=gbrp[g0]",
            f"[2:v]fps={VIDEO_FPS},format=gbrp[d0]",
            f"[g0][d0]blend=all_mode=screen:all_opacity={DUST_OPACITY}:shortest=1,format=yuv420p[b0]",
        ]
        state = {"prev": "b0", "n": 3}
    else:
        lines = [f"[0:v]{grade}[b0]"]
        state = {"prev": "b0", "n": 2}
    info: dict = {}

    def add(png: str, start: float, end: float, fade: float, position: str) -> None:
        dur = end - start
        i = state["n"]
        inputs.extend(["-loop", "1", "-framerate", str(VIDEO_FPS), "-t", f"{dur + 0.1:.2f}", "-i", png])
        lines.append(
            f"[{i}:v]format=rgba,fade=t=in:st=0:d={fade}:alpha=1,fade=t=out:st={max(dur - fade, 0):.2f}:d={fade}:alpha=1,"
            f"setpts=PTS+{start:.3f}/TB[o{i}]"
        )
        lines.append(f"[{state['prev']}][o{i}]overlay={position}:eof_action=pass[b{i}]")
        state["prev"], state["n"] = f"b{i}", i + 1

    if overlays.fonts_available():
        accent = dossier.accent_color(dossier.read_dossier(ctx.storage)) or v.job_style(ctx).accent
        info["accent"] = accent
        if INTRO_TITLE_SECONDS > 0:
            title = _job_title(ctx)
            intro_style = _intro_style(ctx)
            variant = "lower_third" if intro_style == "lower_third" else "centered"
            if overlays.render_title_card(title, work / "overlay_title.png", accent, variant=variant):
                if intro_style == "cold_open" and len(starts) > 2:
                    # Холодне відкриття: перші секунди — лише сцена, титул з'являється, коли гачок "відіграв".
                    start = min(max(starts[2] + 0.4, 9.0), 22.0)
                elif intro_style == "lower_third":
                    start = 3.0
                else:
                    start = 0.4
                end = min(start + INTRO_TITLE_SECONDS, total_s)
                if variant == "lower_third":
                    pos = f"x='-90*pow(1-min(1,(t-{start:.2f})/1.0),2)':y=0"
                else:
                    pos = f"x=0:y='22*pow(1-min(1,(t-{start:.2f})/1.0),2)'"
                add("overlay_title.png", start, end, 0.8, pos)
                info["title"] = title
                info["intro_style"] = intro_style
        cta_windows = []
        for i, seg in enumerate(segments):
            if seg["is_cta"] and overlays.render_subscribe_button(ctx.job["language"], work / f"overlay_cta_{i}.png", accent):
                start, end = starts[i] + 0.4, min(starts[i] + durations[i] - 0.2, starts[i] + 6.0)
                if end - start > 1.2:
                    # Кнопка "вистрибує" знизу (0.45с, ease-out), далі — легке дихання (±3px) замість
                    # статичного висіння: читається як активна кнопка, а не інформаційна плашка.
                    pop = f"{VIDEO_HEIGHT}*pow(1-min(1,(t-{start:.2f})/0.45),2)"
                    bob = f"3*sin(2*PI*(t-{start:.2f}-0.45)*1.1)"
                    y_expr = f"if(lt(t,{start:.2f}+0.45),{pop},{bob})"
                    add(f"overlay_cta_{i}.png", start, end, 0.35, f"x=0:y='{y_expr}'")
                    cta_windows.append([round(start, 1), round(end, 1)])
        info["cta_overlays"] = cta_windows
    else:
        info["overlays"] = "пропущено: не знайдено шрифти (задай OVERLAY_FONT у .env)"

    lines.append(
        f"[{state['prev']}]fade=t=in:st=0:d=0.6,fade=t=out:st={max(total_s - 1.0, 0):.3f}:d=1.0,format=yuv420p[vout]"
    )
    return inputs, ";\n".join(lines), info


# ---------------------------------------------------------------- головна збірка


def _render_video(ctx: StageContext, segments: list[dict], narration: Path) -> tuple[str, dict]:
    """Повертає (ім'я готового файлу відносно VIDEOS_ROOT, інфо для виходу стадії)."""
    style = v.job_style(ctx)
    video_dir = ctx.storage.video_dir()
    work = video_dir / "work"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True, exist_ok=True)

    # Кількість кадрів на сегмент рахуємо через накопичену суму — похибка округлення не накопичується,
    # і за 20 хв відео не "їде" відносно озвучки.
    durations = [s["duration_ms"] / 1000 for s in segments]
    starts = [sum(durations[:i]) for i in range(len(durations))]
    total_s = sum(durations)
    bounds = [round(t * VIDEO_FPS) for t in [*starts, total_s]]
    frames = [max(bounds[i + 1] - bounds[i], 1) for i in range(len(segments))]

    # Розчинення центроване на межі сегментів: шматок отримує d/2 запасу з кожного боку (крім країв відео).
    n = len(segments)
    half = round(TRANSITION_SECONDS * VIDEO_FPS / 2) if n > 1 else 0
    part_frames = [frames[i] + (half if i > 0 else 0) + (half if i < n - 1 else 0) for i in range(n)]
    parts = [work / f"part_{i:04d}.mp4" for i in range(n)]

    with ThreadPoolExecutor(max_workers=max(1, min(VISUAL_CONCURRENCY, 4))) as pool:
        kinds = list(pool.map(lambda i: _render_part(segments[i], i, part_frames[i], parts[i]), range(n)))

    joined_segments = work / "joined_segments.mp4"
    _join_parts(parts, part_frames, half, work, joined_segments)
    # Перевірка цілісності: xfade інколи "успішно" (exit 0) обриває вихід коротшим за очікуване, якщо
    # десь у ланцюжку вхідний шматок хоч на кадр коротший за свій part_frames — тиша, без винятку, і
    # готове відео виходить обрізаним по картинці, хоч звук іде повністю (виявлено 2026-09-29, job 10).
    # Тому рахуємо результат явно й падаємо з чіткою помилкою, а не віддаємо биту склейку далі.
    joined_frames = probe_duration(joined_segments)
    expected_frames_s = sum(frames) / VIDEO_FPS
    if joined_frames is None or abs(joined_frames - expected_frames_s) > 1.0:
        raise RuntimeError(
            f"Склейка сегментів коротша за очікуване: {joined_frames}с проти {expected_frames_s:.2f}с "
            f"очікуваних ({sum(frames)} кадрів) — xfade десь у ланцюжку обрізав результат. "
            "Спробуй ще раз (рендер частин заново) або пиши #дебаг-truncated-join."
        )

    # Пауза тиші перед першим словом: спокійний нерухомий кадр (перший кадр відкриваючого плану) ще
    # lead_frames кадрів ПЕРЕД тим, що вже зібрано — глядач встигає "прогрузитися", перш ніж почне
    # звучати голос і (якщо перший план анімований) рухатись картинка. Свідомо БЕЗ повторного виклику
    # _render_part на кліпі: той перезапускав би Veo-кліп із початку своєї стрічки вдруге з іншим
    # коефіцієнтом уповільнення — на швидкому кліпі це виглядало б як смикання назад у момент стику. Аудіо
    # зсувається на ту саму величину нижче (mix_soundtrack), тож картинка й звук лишаються синхронними.
    lead_frames = round(INTRO_SILENCE_SECONDS * VIDEO_FPS) if n > 0 else 0
    lead_s = lead_frames / VIDEO_FPS
    if lead_frames > 0:
        poster = work / "lead_poster.png"
        first_clip = STORAGE_ROOT / segments[0]["visual_clip_path"] if v.exists(segments[0]["visual_clip_path"]) else None
        if first_clip is not None:
            run_ffmpeg(["-i", str(first_clip), "-frames:v", "1", str(poster)])
        else:
            poster = STORAGE_ROOT / segments[0]["visual_path"]
        lead_part = work / "part_lead.mp4"
        common = ["-r", str(VIDEO_FPS), "-c:v", "libx264", "-preset", "veryfast",
                  "-crf", "16", "-pix_fmt", "yuv420p", "-an", str(lead_part)]
        run_ffmpeg(["-loop", "1", "-i", str(poster), "-vf", "format=yuv420p", "-frames:v", str(lead_frames), *common])
        joined = work / "joined.mp4"
        _join_parts([lead_part, joined_segments], [lead_frames, sum(frames)], 0, work, joined)
    else:
        joined = joined_segments

    starts_padded = [s + lead_s for s in starts]
    total_s_padded = total_s + lead_s

    clip_audio: dict[int, Path] = {}
    if USE_CLIP_AUDIO:
        for i, seg in enumerate(segments):
            if v.exists(seg["visual_clip_path"]):
                target = work / f"clipaudio_{i:04d}.wav"
                if _clip_audio(STORAGE_ROOT / seg["visual_clip_path"], target):
                    clip_audio[i] = target
    layers, sfx_info = audio_mix.plan_layers(segments, starts_padded, durations, clip_audio)
    if USE_MUSIC:
        # Дуже тиха фонова музика (оригінальний ембієнт чи треки користувача) на ВСЮ довжину; проходить через той
        # самий sidechain-ducking, що й ефекти, тож під диктором ще тихіша й слів не перебиває.
        try:
            bed = music.build_bed(ctx.job_id, total_s_padded, work / "music_bed.m4a")
        except Exception as exc:  # музика — прикраса: без неї відео все одно збирається
            bed, sfx_info["music_error"] = None, str(exc)[:200]
        if bed is not None:
            layers.append(audio_mix.Layer(bed, 0.0, 0.0, length_s=total_s_padded, fade_in_s=3.0, fade_out_s=4.0, kind="music"))
            sfx_info["music"] = True
    soundtrack = work / "soundtrack.m4a"
    audio_mix.mix_soundtrack(narration, total_s_padded, layers, soundtrack, lead_s=lead_s)

    in_args, graph, overlay_info = _overlay_graph(
        ctx, work, segments, starts_padded, durations, total_s_padded, style.grade
    )
    (work / "final_graph.txt").write_text(graph, encoding="utf-8")

    tmp_out = work / "render.mp4"  # ASCII-ім'я: ffmpeg на Windows не завжди дружить з юнікодом у шляху
    run_ffmpeg([
        *in_args, "-filter_complex_script", "final_graph.txt", "-map", "[vout]", "-map", "1:a",
        "-c:v", "libx264", "-preset", "medium", "-crf", "21", "-c:a", "copy",
        "-map_metadata", "-1", "-fflags", "+bitexact", "-flags:v", "+bitexact",  # без тегів кодера й метаданих
        "-t", f"{total_s_padded:.3f}", "-movflags", "+faststart", "render.mp4",
    ], cwd=work)

    preview = ctx.job.get("preview_seconds")
    if preview:
        # Тест-режим: не фінальна видача, лишається плоским файлом у VIDEOS_ROOT (не варте окремої папки).
        final_name = f"{ctx.job_id:03d}_{_slug(ctx.job['topic'])}_test{preview}s.mp4"
        final_path = VIDEOS_ROOT / final_name
    else:
        # Повне відео: власна папка "{id}_{slug}/" — метадані (metadata_generate) докладають туди ж
        # фінальні прев'ю й metadata.txt, щоб видача одного відео була однією самодостатньою папкою.
        job_dir = VIDEOS_ROOT / f"{ctx.job_id:03d}_{_slug(ctx.job['topic'])}"
        job_dir.mkdir(parents=True, exist_ok=True)
        final_name = f"{job_dir.name}/video.mp4"
        final_path = VIDEOS_ROOT / final_name
    VIDEOS_ROOT.mkdir(parents=True, exist_ok=True)
    final_path.unlink(missing_ok=True)
    shutil.move(str(tmp_out), str(final_path))
    shutil.rmtree(work, ignore_errors=True)

    return final_name, {
        "video_seconds": round(total_s_padded, 2),
        "intro_silence_seconds": round(lead_s, 2),
        "animated_parts": kinds.count("clip"),
        "still_parts": kinds.count("still"),
        "transition_seconds": round(2 * half / VIDEO_FPS, 2),
        "sfx": sfx_info,
        "style": style.id,
        **overlay_info,
    }
