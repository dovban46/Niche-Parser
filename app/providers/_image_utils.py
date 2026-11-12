"""Збереження й підготовка зображень: усі згенеровані кадри пишуться в WebP без метаданих."""

import io
from pathlib import Path

import numpy as np
from PIL import Image

WEBP_QUALITY = 92


_MAX_TRIM = 0.07  # не більше 7% з кожного боку: захист від "полів", що насправді є світлим небом


def _uniform_run(lines: np.ndarray, limit: int) -> int:
    """Скільки ПЕРШИХ рядків (від краю) майже однокольорові й світлі (паперове поле гравюри)."""
    n = 0
    for row in lines[:limit]:
        med = np.median(row, axis=0)
        if med.mean() < 165 or (np.abs(row - med).max(axis=1) < 26).mean() < 0.97:
            break
        n += 1
    return n


def trim_paper_border(img: Image.Image) -> Image.Image:
    """Генератори інколи малюють кремове паперове поле з тонкою чорною рамкою навколо ілюстрації, хоч промпт це
    забороняє; під час наїзду камери (Ken Burns) воно вилазить у кадр як "рамка". Обрізаємо поле (+ тонку лінію
    рамки) з кожного боку не більше _MAX_TRIM і повертаємо початковий розмір; без поля — кадр не змінюється."""
    rgb = img.convert("RGB")
    arr = np.asarray(rgb).astype(np.int16)
    h, w = arr.shape[:2]
    lim_y, lim_x = int(h * _MAX_TRIM), int(w * _MAX_TRIM)
    top = _uniform_run(arr, lim_y)
    bottom = _uniform_run(arr[::-1], lim_y)
    left = _uniform_run(arr.transpose(1, 0, 2), lim_x)
    right = _uniform_run(arr.transpose(1, 0, 2)[::-1], lim_x)
    if min(top, bottom, left, right) < 3:  # поле буває не завжди з усіх чотирьох боків, але мінімум 3 з 4 мають бути
        sides = sorted([top, bottom, left, right])
        if sides[1] < 3:
            return img
    pad = 7  # тонка темна лінія рамки одразу за полем
    t, b, l, r = (top + pad if top else 0), (bottom + pad if bottom else 0), (left + pad if left else 0), (right + pad if right else 0)
    if t + b >= h * 0.3 or l + r >= w * 0.3:
        return img
    return rgb.crop((l, t, w - r, h - b)).resize((w, h), Image.LANCZOS)


def save_clean(img: Image.Image, path: Path) -> None:
    """Пише кадр у `path`: `.webp` — WebP (якість 92) без EXIF/ICC/XMP, інакше PNG. Кадр копіюється в
    новий обʼєкт, щоб жодні метадані вихідного файлу не потрапили до збереженого."""
    if path.suffix.lower() == ".webp":  # кадри відео (не прев'ю): прибираємо паперове поле
        img = trim_paper_border(img)
    clean = Image.new("RGB", img.size)
    clean.paste(img.convert("RGB"))
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() == ".webp":
        clean.save(path, format="WEBP", quality=WEBP_QUALITY, method=6)
    else:
        clean.save(path, format="PNG")


def model_input(path: Path) -> tuple[bytes, str]:
    """Байти й mime для передачі в модель (Veo приймає PNG/JPEG): WebP перекодуємо в PNG у памʼяті."""
    if path.suffix.lower() in (".png", ".jpg", ".jpeg"):
        return path.read_bytes(), "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    buf = io.BytesIO()
    Image.open(path).convert("RGB").save(buf, format="PNG")
    return buf.getvalue(), "image/png"
