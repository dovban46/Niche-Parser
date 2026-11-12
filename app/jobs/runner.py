"""Найпростіша фонова черга: один worker-потік у процесі FastAPI. Без Celery/Redis —
для MVP цього достатньо (один job обробляється кілька секунд у stub-режимі, реальні
провайдери — хвилини). Якщо колись знадобиться паралельна обробка кількох job'ів,
тут же піднімається пул потоків/окрема черга задач без зміни решти пайплайна.
"""

import logging
import queue
import threading

logger = logging.getLogger("video_factory.runner")

_job_queue: "queue.Queue[int]" = queue.Queue()
_worker_thread: threading.Thread | None = None
_worker_lock = threading.Lock()


def enqueue_job(job_id: int) -> None:
    _job_queue.put(job_id)


def _worker_loop() -> None:
    from .pipeline import run_job  # лінивий імпорт: уникаємо циклу runner -> pipeline -> ... -> runner

    while True:
        job_id = _job_queue.get()
        try:
            run_job(job_id)
        except Exception:
            logger.exception("run_job(%s) впав поза межами власної обробки помилок", job_id)
        finally:
            _job_queue.task_done()


def start_worker() -> None:
    global _worker_thread
    with _worker_lock:
        if _worker_thread is not None and _worker_thread.is_alive():
            return
        _worker_thread = threading.Thread(target=_worker_loop, name="video-factory-worker", daemon=True)
        _worker_thread.start()
        logger.info("Фоновий worker запущено.")
