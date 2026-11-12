"""План ефектів explainer-а з «прорідженням»: у довгому відео ефекти мають бути рідкісним акцентом, а не шумом
на кожному переході. Пріоритет 3 — смисловий удар (sting/tada/gulp…), 2 — ефект із розкадрування, 1 — переходи."""

from .. import audio_mix, sfx
from ..config import SFX_ACCENT_GAIN_DB

_TRANSITION_SFX = {"whip": "x_whoosh", "wipe": "x_whoosh"}   # діафрагма/спалах — без звуку
_HIGH = {"x_sting", "x_tada", "x_gulp", "x_record_scratch", "x_gasp", "x_thud"}
_GAP = {1: 8.0, 2: 4.5, 3: 2.5}      # мінімум секунд між ефектами (береться за нижчим пріоритетом пари)
_SAME_TAG_GAP = {"x_whoosh": 20.0, "page_turn": 40.0, "x_ding": 18.0, "x_pop": 16.0}
_DEFAULT_SAME = 10.0


def plan_sfx(tl, density: float = 1.0) -> tuple[list[audio_mix.Layer], dict]:
    cands = []   # (pri, t, tag, gain)
    for i, b in enumerate(tl.beats):
        for j, tag in enumerate(b.get("sfx", [])):
            if sfx.path_for(tag).exists():
                cands.append((3 if tag in _HIGH else 2, b["s"] + 0.04 + j * 0.35, tag, SFX_ACCENT_GAIN_DB))
        w = _TRANSITION_SFX.get(b.get("tr", "cut"))
        if w and i > 0 and sfx.path_for(w).exists():
            cands.append((1, max(tl.starts[i] - 0.06, 0), w, SFX_ACCENT_GAIN_DB - 3))
    accepted: list[tuple[int, float, str, float]] = []
    dropped = 0
    for c in sorted(cands, key=lambda x: (-x[0], x[1])):
        pri, t, tag, _ = c
        bad = False
        for a in accepted:
            gap = _GAP[min(pri, a[0])] / max(density, 0.1)
            if abs(t - a[1]) < gap and not (a[2] != tag and abs(t - a[1]) < 0.5 and pri >= 2 and a[0] >= 2):
                bad = True
            if tag == a[2] and abs(t - a[1]) < _SAME_TAG_GAP.get(tag, _DEFAULT_SAME) / max(density, 0.1):
                bad = True
            if bad:
                break
        if bad:
            dropped += 1
        else:
            accepted.append(c)
    layers = [audio_mix.Layer(sfx.path_for(tag), t, gain) for _, t, tag, gain in sorted(accepted, key=lambda x: x[1])]
    return layers, {"planned": len(cands), "kept": len(accepted), "dropped": dropped}


def plan_sfx_short(tl) -> tuple[list[audio_mix.Layer], dict]:
    """Щільний, але чистий звуковий дизайн Shorts: whoosh/swish на кожну зміну місця, pop на кожен великий текст, sting на 0-му кадрі,
    riser перед розв'язкою, boom на останньому акценті. Мінімум 0.35 с між ефектами, один і той самий тег не частіше ніж раз на 2 с."""
    ev: list[tuple[float, str, float]] = []   # (час, тег, зсув гучності дБ)
    n = len(tl.beats)
    for i, b in enumerate(tl.beats):
        t0 = max(tl.starts[i], 0.0)
        kind = getattr(tl, "tr_kind", ["cut"] * n)[i]
        if i == 0:
            ev.append((0.02, "x_sting", 0.0))
            continue
        if kind in ("whip", "zoom"):
            ev.append((t0 - 0.05, "x_whoosh" if kind == "whip" else "x_swish", -4.0))
        elif kind == "slash":
            ev.append((t0 - 0.02, "x_swish", -1.0))
            ev.append((t0 + 0.1, "x_thud", -5.0))
        elif kind == "ink":
            ev.append((t0 - 0.05, "x_riser", -7.0))
        elif kind == "glitch":
            ev.append((t0 - 0.02, "x_glitch", -3.0))
        elif kind == "pixel":
            ev.append((t0 - 0.02, "x_click", -4.0))
        elif kind == "push":
            ev.append((t0 - 0.05, "x_whoosh", -4.0))
        elif kind in ("shutter", "tear"):
            ev.append((t0 - 0.03, "x_swish", -2.0))
        if b.get("stamp"):
            ev.append((t0 + 0.14, "x_boom", -1.0))
        if b.get("choice"):
            dur_b = max(tl.ends[i] - tl.starts[i], 0.3)
            ev.append((t0 + 0.12, "x_click", -3.0))
            ev.append((t0 + max(dur_b * 0.55, 0.9), "x_ping_up", -4.0))
        if b.get("cta"):
            ev.append((t0 + 0.85, "x_click", -3.0))
            ev.append((t0 + 1.5, "x_ping_up", -4.0))
        if b.get("decree"):
            ev.append((t0 + 0.25, "quill_scratch", -5.0))
        elif kind == "flash":
            ev.append((t0, "x_boom", -4.0))
        if b.get("big"):
            ev.append((t0 + 0.04, "x_pop", -2.0))
        for tag in b.get("sfx", []):
            ev.append((t0 + 0.05, tag, 0.0))
    last = tl.beats[-1]["s"] if tl.beats else tl.total
    ev.append((max(last - 5.2, 1.0), "x_riser", -3.0))
    ev.sort(key=lambda e: e[0])
    kept, last_t, last_by_tag = [], -9.0, {}
    for t, tag, g in ev:
        if not sfx.path_for(tag).exists():
            continue
        if t - last_t < 0.35 or t - last_by_tag.get(tag, -9.0) < {"x_pop": 0.9, "x_whoosh": 1.2, "x_swish": 1.2}.get(tag, 2.0):
            continue
        kept.append(audio_mix.Layer(sfx.path_for(tag), max(t, 0.0), SFX_ACCENT_GAIN_DB + g))
        last_t, last_by_tag[tag] = t, t
    return kept, {"planned": len(ev), "kept": len(kept)}
