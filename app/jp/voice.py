"""Озвучка ElevenLabs із таймінгами слів → таймлайн бітів. Довгий текст озвучується частинами (≤ ~4000 символів,
з контекстом сусідніх частин для плавної інтонації) і склеюється; кожна частина кешується, тож повтор не платить удруге."""

import subprocess

from ..explainer import tts
from ..ffutil import error_tail, probe_duration, run_ffmpeg
from . import core, costs

# Brian (premade): глибокий, теплий оповідач; інший за голос Forbidden Folio (George).
DEFAULT_VOICE = "nPczCjzI2devNBz1zQrb"
FALLBACK_VOICE = "JBFqnCBsd6RMkjVDRZzb"
TAIL_S = 0.9          # пауза-фінал після останнього слова (завершений кінець, не обірваний)
PART_CHARS = 4000     # ліміт частини; між частинами додається коротка пауза
PART_GAP_S = 0.25


def _parts(lines: list[str]) -> list[list[str]]:
    parts, cur, n = [], [], 0
    for l in lines:
        if cur and n + len(l) > PART_CHARS:
            parts.append(cur)
            cur, n = [], 0
        cur.append(l)
        n += len(l) + 1
    if cur:
        parts.append(cur)
    return parts


def _tts_part(d, i: int, text: str, prev: str, nxt: str, voice: str | None) -> dict:
    mp3, meta = d / f"voice_part_{i}.mp3", d / f"voice_part_{i}.json"
    if mp3.exists() and meta.exists():
        return core.load_json(meta)
    last_exc = None
    for v in ([voice] if voice else [DEFAULT_VOICE, FALLBACK_VOICE]):
        try:
            al = tts.synthesize_with_timestamps(text, mp3, voice_id=v, stability=0.42, style=0.40, previous_text=prev, next_text=nxt)
            costs.spend_eleven(al["chars_billed"])
            al["voice"] = v
            core.save_json(meta, al)
            return al
        except Exception as exc:
            last_exc = exc
            print(f"голос {v} недоступний ({exc})")
    raise last_exc


def synthesize(slug: str, voice: str | None = None, force: bool = False) -> dict:
    d = core.job_dir(slug)
    mp3, tl = d / "voice.mp3", d / "timeline.json"
    if mp3.exists() and tl.exists() and not force:
        return core.load_json(tl)
    script = (d / "script.txt").read_text(encoding="utf-8").strip()
    lines = [l.strip() for l in script.splitlines() if l.strip()]
    parts = _parts(lines)
    texts = [core.NL.join(p) for p in parts]
    words_all, offset, part_files, chars = [], 0.0, [], 0
    used_voice = None
    for i, text in enumerate(texts):
        prev = texts[i - 1] if i else ""
        nxt = texts[i + 1] if i + 1 < len(texts) else ""
        al = _tts_part(d, i, text, prev, nxt, voice or used_voice)
        used_voice = al.get("voice")
        chars += al["chars_billed"]
        part_mp3 = d / f"voice_part_{i}.mp3"
        dur = probe_duration(part_mp3) or al["ends"][-1]
        for w in tts.words_from_alignment(al):
            words_all.append({"w": w["w"], "s": w["s"] + offset, "e": w["e"] + offset})
        part_files.append(part_mp3)
        offset += dur + PART_GAP_S
    # склейка частин із паузами (anullsrc) одним ffmpeg-викликом
    if len(part_files) == 1:
        run_ffmpeg(["-i", str(part_files[0]), "-c:a", "libmp3lame", "-b:a", "128k", str(mp3)])
    else:
        inputs, filt = [], []
        for k, f in enumerate(part_files):
            inputs += ["-i", str(f)]
            filt.append(f"[{k}:a]aresample=44100,apad=pad_dur={PART_GAP_S}[a{k}]")
        graph = ";".join(filt) + ";" + "".join(f"[a{k}]" for k in range(len(part_files))) + f"concat=n={len(part_files)}:v=0:a=1[out]"
        try:
            run_ffmpeg([*inputs, "-filter_complex", graph, "-map", "[out]", "-c:a", "libmp3lame", "-b:a", "128k", str(mp3)])
        except subprocess.CalledProcessError as exc:
            raise RuntimeError("ffmpeg (склейка озвучки): " + error_tail(exc))
    beats = core.load_json(d / "beats.json")
    out_beats, k = [], 0
    for b in beats:
        n = len(core.words_of(b["t"]))
        out_beats.append({"first": k, "last": k + n - 1})
        k += n
    if k != len(words_all):
        raise RuntimeError(f"слів у бітах {k}, у озвучці {len(words_all)}: розбіжність")
    total = probe_duration(mp3) or words_all[-1]["e"]
    for i, ob in enumerate(out_beats):
        start = 0.0 if i == 0 else words_all[ob["first"]]["s"] - 0.02
        end = (words_all[out_beats[i + 1]["first"]]["s"] - 0.02) if i + 1 < len(out_beats) else words_all[-1]["e"] + TAIL_S
        ob["s"], ob["e"] = round(max(start, 0.0), 3), round(end, 3)
    # початки рядків сценарію (абзаців) у часі: для розділів, музичних акцентів і глав
    starts, k = [], 0
    for l in lines:
        starts.append({"word": k, "t": round(words_all[k]["s"], 3), "text": l[:60]})
        k += len(core.words_of(l))
    data = {"words": [{"w": w["w"], "s": round(w["s"], 3), "e": round(w["e"], 3)} for w in words_all],
            "beats": out_beats, "voice_s": round(total, 3), "total_s": round(words_all[-1]["e"] + TAIL_S, 3),
            "chars_billed": chars, "lines": starts, "voice": used_voice}
    core.save_json(tl, data)
    return data
