"""Спільні утиліти каналу про Японію: шляхи job'ів, виклики fal (кадри й прев'ю), Claude (текст і зір)."""

import base64
import io
import json
import os
import re
import time
from pathlib import Path

import requests
from PIL import Image

from .. import config
from ..config import STORAGE_ROOT, VIDEOS_ROOT
from ..providers.base import ProviderConfigError
from . import costs

JOBS_ROOT = STORAGE_ROOT / "jp_jobs"
NL = chr(10)

# Єдиний стиль каналу для fal FLUX: «сучасний мультфільм у стилі гравюри укійо-е». Кадри читаються з першої секунди.
STYLE = (
    "flat 2D cartoon in a simple woodblock-print comic style: thick dark brown outlines, flat color fills, "
    "limited palette of indigo, vermilion, cream and mustard yellow; very simple characters with plain round faces "
    "(two dot eyes, tiny mouth), simple tube-like limbs and rounded mitten hands without individual fingers; "
    "calm clear composition with large simple shapes, medium or wide shot, at most three characters, characters facing forward or seen from behind; "
    "set in 16th century Japan, the background fits the scene (castle walls, forest, mountain, river, rice fields, temple, room interior, night sky); clean hand-drawn illustration without writing"
)


def job_dir(slug: str) -> Path:
    d = JOBS_ROOT / slug
    d.mkdir(parents=True, exist_ok=True)
    return d


def load_json(path: Path, default=None):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def save_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


# ---------------- fal ----------------
def _fal_key() -> str:
    key = os.environ.get("FAL_API_KEY")
    if not key:
        raise ProviderConfigError("FAL_API_KEY не знайдено в .env")
    return key


def _download(url: str) -> Image.Image:
    r = requests.get(url, timeout=90)
    r.raise_for_status()
    return Image.open(io.BytesIO(r.content)).convert("RGB")


def fal_image(prompt: str, out: Path, model: str = "fal-ai/flux/schnell", size=(1536, 864), seed: int | None = None,
              retries: int = 3) -> Path:
    payload = {"prompt": prompt, "image_size": {"width": size[0], "height": size[1]}, "num_images": 1,
               "enable_safety_checker": True}
    if "schnell" in model:
        payload["num_inference_steps"] = 4
    if seed is not None:
        payload["seed"] = seed
    last = ""
    for attempt in range(retries):
        try:
            r = requests.post(f"https://fal.run/{model}", headers={"Authorization": f"Key {_fal_key()}"}, json=payload, timeout=180)
            if r.status_code == 200 and r.json().get("images"):
                _download(r.json()["images"][0]["url"]).save(out)
                costs.spend_fal(model, size)
                return out
            last = f"{r.status_code}: {r.text[:200]}"
            if r.status_code in (401, 402, 403):
                break
        except requests.RequestException as exc:
            last = str(exc)
        time.sleep(2 + attempt * 3)
    raise ProviderConfigError(f"fal {model}: {last}")


def fal_edit(prompt: str, refs: list[Path], out: Path, model: str = "fal-ai/nano-banana/edit", retries: int = 2, aspect: str = "16:9") -> Path:
    """Nano Banana через fal (ключ fal, НЕ Google): картинка за промптом і референсами стилю."""
    urls = []
    for p in refs:
        im = Image.open(p).convert("RGB")
        im.thumbnail((1280, 1280))
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=88)
        urls.append("data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode())
    payload = {"prompt": prompt, "image_urls": urls, "num_images": 1, "aspect_ratio": aspect}
    last = ""
    for attempt in range(retries):
        r = requests.post(f"https://fal.run/{model}", headers={"Authorization": f"Key {_fal_key()}"}, json=payload, timeout=240)
        if r.status_code == 200 and r.json().get("images"):
            _download(r.json()["images"][0]["url"]).save(out)
            costs.spend_fal(model)
            return out
        last = f"{r.status_code}: {r.text[:300]}"
        if r.status_code in (401, 402, 403, 404, 422):
            break
        time.sleep(3)
    raise ProviderConfigError(f"fal {model}: {last}")


def fal_nb(prompt: str, out: Path, model: str = "fal-ai/nano-banana", aspect: str = "16:9", retries: int = 3) -> Path:
    """Nano Banana text-to-image через fal (без референсів)."""
    payload = {"prompt": prompt, "num_images": 1, "aspect_ratio": aspect, "output_format": "jpeg"}
    last = ""
    for attempt in range(retries):
        try:
            r = requests.post(f"https://fal.run/{model}", headers={"Authorization": f"Key {_fal_key()}"}, json=payload, timeout=240)
            if r.status_code == 200 and r.json().get("images"):
                _download(r.json()["images"][0]["url"]).save(out)
                costs.spend_fal(model)
                return out
            last = f"{r.status_code}: {r.text[:300]}"
            if r.status_code in (401, 402, 403, 404, 422):
                break
        except requests.RequestException as exc:
            last = str(exc)
        time.sleep(3 + attempt * 4)
    raise ProviderConfigError(f"fal {model}: {last}")


# ---------------- Claude ----------------
_llm = None


def llm():
    global _llm
    if _llm is None:
        from ..providers.llm.anthropic_provider import AnthropicLLMProvider
        _llm = AnthropicLLMProvider()
    return _llm


def ask_json(system: str, user: str, max_tokens: int = 12000, effort: str = "medium"):
    from ..providers.llm.anthropic_provider import _extract_json
    return _extract_json(llm()._complete(system, user, max_tokens, effort=effort))


def ask_vision_json(image_path: Path, question: str, max_tokens: int = 400, model: str | None = None):
    from ..providers.llm.anthropic_provider import _extract_json
    prov = llm()
    im = Image.open(image_path).convert("RGB")
    im.thumbnail((1024, 576))
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=85)
    data = base64.b64encode(buf.getvalue()).decode()
    resp = prov._client.messages.create(
        model=model or prov._model, max_tokens=max_tokens,
        messages=[{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": data}},
            {"type": "text", "text": question}]}])
    costs.spend_llm(model or prov._model, resp.usage.input_tokens, resp.usage.output_tokens)
    text = "".join(b.text for b in resp.content if b.type == "text")
    return _extract_json(text)


def words_of(text: str) -> list[str]:
    return re.findall(r"\S+", text)


def frame_paths(d: Path, i: int) -> list:
    """Кадри біта: [якір, поза 2, поза 3, ...]; підтримує jpg/png (Flow) і стару назву beat_NN.png."""
    fr = d / "frames"
    for ext in ("jpg", "png"):
        first = fr / f"beat_{i:03d}.{ext}"
        if first.exists():
            out, k = [first], 2
            while (fr / f"beat_{i:03d}_{k}.{ext}").exists():
                out.append(fr / f"beat_{i:03d}_{k}.{ext}")
                k += 1
            return out
    old = fr / f"beat_{i:02d}.png"
    return [old] if old.exists() else []
