"""python -m app.explainer.make_test <папка> [--frames 10 55 100] [--no-audio]
Збирає тестове відео з <папка>/timing.json + voice.mp3 (див. make_voice). --frames — лише PNG-кадри для перегляду."""
import json
import subprocess
import sys
from pathlib import Path

from PIL import Image

from .. import audio_mix, music, sfx
from ..config import SFX_ACCENT_GAIN_DB
from ..ffutil import error_tail, run_ffmpeg
from . import samples
from .render import FPS, Library, Timeline, mouth_levels, render_video

_TRANSITION_SFX = {"whip": "x_whoosh", "wipe": "x_whoosh", "iris": "x_swipe_paper"}


def build_timeline(folder: Path) -> Timeline:
    data = json.load(open(folder / "timing.json", encoding="utf-8"))
    beats, total = data["beats"], data["total"]
    lib = Library(samples.BACKGROUNDS.keys(), samples.PROPS.keys(), samples.ACTORS)
    mouths = mouth_levels(folder / "voice.mp3", int((total + 1) * FPS))
    return Timeline(beats, total, lib, mouths)


def sfx_layers(tl: Timeline) -> list[audio_mix.Layer]:
    layers = []
    for i, b in enumerate(tl.beats):
        for j, tag in enumerate(b.get("sfx", [])):
            p = sfx.path_for(tag)
            if p.exists():
                layers.append(audio_mix.Layer(p, max(b["s"] + 0.04 + j * 0.35, 0), SFX_ACCENT_GAIN_DB))
        w = _TRANSITION_SFX.get(b.get("tr", "cut"))
        if w and i > 0 and sfx.path_for(w).exists():
            layers.append(audio_mix.Layer(sfx.path_for(w), max(tl.starts[i] - 0.06, 0), SFX_ACCENT_GAIN_DB - 3))
    return layers


def main() -> None:
    folder = Path(sys.argv[1])
    tl = build_timeline(folder)
    if "--frames" in sys.argv:
        ts = [float(x) for x in sys.argv[sys.argv.index("--frames") + 1:]]
        for t in ts:
            Image.fromarray(tl.frame(int(t * FPS))).save(folder / f"frame_{t:05.2f}.png")
        print("кадри:", ts)
        return
    silent = folder / "silent.mp4"
    n = render_video(tl, silent)
    print("відрендерено кадрів:", n, "шотів:", len(tl.shots))
    layers = sfx_layers(tl)
    bed = music.build_bed(1, tl.total, folder / "music_bed.m4a")
    if bed:
        layers.append(audio_mix.Layer(bed, 0.0, 0.0, length_s=tl.total, fade_in_s=1.0, fade_out_s=2.0, kind="music"))
    audio_mix.mix_soundtrack(folder / "voice.mp3", tl.total, layers, folder / "mix.m4a")
    out = folder / "explainer_test.mp4"
    try:
        run_ffmpeg(["-i", str(silent), "-i", str(folder / "mix.m4a"), "-c:v", "copy", "-c:a", "copy", "-shortest", str(out)])
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(error_tail(exc)) from exc
    print("готово:", out, f"{tl.total:.1f} с, ефектів: {len(layers)}")


if __name__ == "__main__":
    main()
