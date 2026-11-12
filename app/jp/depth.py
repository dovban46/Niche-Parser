"""Карти глибини кадрів (Depth Anything V2 small, ONNX, CPU) для паралакса 2.5D у рендері.
Карта: float32 0..1 (1 = ближче до камери), зберігається як depth/beat_XXX.npy для кожного якірного кадру."""

from pathlib import Path

import cv2
import numpy as np
import requests

from . import core

MODEL_URL = "https://huggingface.co/onnx-community/depth-anything-v2-small/resolve/main/onnx/model_quantized.onnx"
MODEL_PATH = core.JOBS_ROOT.parent / "models" / "depth_anything_v2_small_q.onnx"
SIZE = 518
_MEAN = np.array([0.485, 0.456, 0.406], np.float32)
_STD = np.array([0.229, 0.224, 0.225], np.float32)
_sess = None


def _session():
    global _sess
    if _sess is None:
        import onnxruntime as ort
        if not MODEL_PATH.exists():
            MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
            r = requests.get(MODEL_URL, timeout=300)
            r.raise_for_status()
            MODEL_PATH.write_bytes(r.content)
        _sess = ort.InferenceSession(str(MODEL_PATH), providers=["CPUExecutionProvider"])
    return _sess


def depth_of(img_bgr: np.ndarray) -> np.ndarray:
    """Відносна глибина 0..1 (ближче = більше) у розмірі зображення."""
    h, w = img_bgr.shape[:2]
    rgb = cv2.cvtColor(cv2.resize(img_bgr, (SIZE, SIZE), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
    x = ((rgb - _MEAN) / _STD).transpose(2, 0, 1)[None]
    sess = _session()
    out = sess.run(None, {sess.get_inputs()[0].name: x})[0][0]
    out = cv2.GaussianBlur(out, (0, 0), 3)               # м'якші краї: менше розривів при зсуві
    lo, hi = np.percentile(out, 2), np.percentile(out, 98)
    out = np.clip((out - lo) / max(hi - lo, 1e-6), 0, 1)
    return cv2.resize(out, (w, h), interpolation=cv2.INTER_LINEAR).astype(np.float32)


def compute_all(slug: str, log=print) -> int:
    d = core.job_dir(slug)
    beats = core.load_json(d / "beats.json")
    out_dir = d / "depth"
    out_dir.mkdir(exist_ok=True)
    n = 0
    for i in range(len(beats)):
        npy = out_dir / f"beat_{i:03d}.npy"
        if npy.exists():
            continue
        paths = core.frame_paths(d, i)
        if not paths:
            continue
        dm = depth_of(cv2.imread(str(paths[0])))
        np.save(npy, cv2.resize(dm, (480, 270), interpolation=cv2.INTER_AREA).astype(np.float16))
        n += 1
        if n % 40 == 0:
            log(f"глибина: {n}")
    log(f"глибина готова: нових {n}")
    return n
