"""CRUD над jobs/job_stages/segments/qa_issues. Модуль функцій (як history.py в parser),
без класів-репозиторіїв — простіше й достатньо для одного локального SQLite-файлу.
"""

import json
import sqlite3
from datetime import datetime, timezone

from ..db import connect, get_lock
from ..schemas import STAGE_ORDER

_lock = get_lock()


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _row_to_dict(row: sqlite3.Row | None) -> dict | None:
    return dict(row) if row is not None else None


# ---------- jobs ----------


def create_job(
    topic: str,
    niche: str,
    target_duration_minutes: int,
    language: str,
    config: dict,
    voice_id: str | None = None,
    style_id: str | None = None,
    preview_seconds: int | None = None,
    dossier_approved: bool = False,
) -> int:
    now = _now()
    with _lock, connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO jobs (created_at, updated_at, topic, niche, target_duration_minutes,
                               language, voice_id, style_id, preview_seconds, dossier_approved,
                               status, config_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)
            """,
            (
                now,
                now,
                topic,
                niche,
                target_duration_minutes,
                language,
                voice_id,
                style_id,
                preview_seconds,
                1 if dossier_approved else 0,
                json.dumps(config, ensure_ascii=False),
            ),
        )
        job_id = cur.lastrowid
        for order, stage_name in enumerate(STAGE_ORDER):
            conn.execute(
                "INSERT INTO job_stages (job_id, stage_name, stage_order, status) VALUES (?, ?, ?, 'pending')",
                (job_id, stage_name, order),
            )
        return job_id


def get_job(job_id: int) -> dict | None:
    with _lock, connect() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return _row_to_dict(row)


def list_jobs() -> list[dict]:
    with _lock, connect() as conn:
        rows = conn.execute("SELECT * FROM jobs ORDER BY id DESC").fetchall()
        return [dict(r) for r in rows]


def update_job(
    job_id: int,
    *,
    status: str | None = None,
    current_stage: str | None = "__unset__",
    error_message: str | None = "__unset__",
    final_video_path: str | None = None,
) -> None:
    fields, values = [], []
    if status is not None:
        fields.append("status = ?")
        values.append(status)
    if current_stage != "__unset__":
        fields.append("current_stage = ?")
        values.append(current_stage)
    if error_message != "__unset__":
        fields.append("error_message = ?")
        values.append(error_message)
    if final_video_path is not None:
        fields.append("final_video_path = ?")
        values.append(final_video_path)
    fields.append("updated_at = ?")
    values.append(_now())
    values.append(job_id)

    with _lock, connect() as conn:
        conn.execute(f"UPDATE jobs SET {', '.join(fields)} WHERE id = ?", values)


def delete_job(job_id: int) -> None:
    """Прибирає всі рядки job'а з БД (файли на диску чистить service.delete_job)."""
    with _lock, connect() as conn:
        conn.execute("DELETE FROM qa_issues WHERE job_id = ?", (job_id,))
        conn.execute("DELETE FROM segments WHERE job_id = ?", (job_id,))
        conn.execute("DELETE FROM job_stages WHERE job_id = ?", (job_id,))
        conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))


def set_dossier_approved(job_id: int, approved: bool) -> None:
    with _lock, connect() as conn:
        conn.execute(
            "UPDATE jobs SET dossier_approved = ?, updated_at = ? WHERE id = ?",
            (1 if approved else 0, _now(), job_id),
        )


def set_script_approved(job_id: int, approved: bool) -> None:
    with _lock, connect() as conn:
        conn.execute(
            "UPDATE jobs SET script_approved = ?, updated_at = ? WHERE id = ?",
            (1 if approved else 0, _now(), job_id),
        )


def mark_running_jobs_failed_on_startup() -> int:
    """Викликається при старті сервера: job'и, що лишились 'running' після краху/рестарту,
    вже не мають живого воркера — позначаємо їх failed, користувач тисне Retry сам."""
    now = _now()
    with _lock, connect() as conn:
        cur = conn.execute(
            "UPDATE jobs SET status = 'failed', error_message = ?, updated_at = ? WHERE status = 'running'",
            ("Перервано перезапуском сервера. Натисни Retry, щоб продовжити.", now),
        )
        conn.execute(
            "UPDATE job_stages SET status = 'failed', error_message = ? "
            "WHERE status = 'running' AND job_id IN (SELECT id FROM jobs WHERE status = 'failed')",
            ("Перервано перезапуском сервера.",),
        )
        return cur.rowcount


# ---------- job_stages ----------


def list_stages(job_id: int) -> list[dict]:
    with _lock, connect() as conn:
        rows = conn.execute(
            "SELECT * FROM job_stages WHERE job_id = ? ORDER BY stage_order", (job_id,)
        ).fetchall()
        return [dict(r) for r in rows]


def get_stage(job_id: int, stage_name: str) -> dict | None:
    with _lock, connect() as conn:
        row = conn.execute(
            "SELECT * FROM job_stages WHERE job_id = ? AND stage_name = ?", (job_id, stage_name)
        ).fetchone()
        return _row_to_dict(row)


def update_stage(
    job_id: int,
    stage_name: str,
    *,
    status: str | None = None,
    output: dict | None = None,
    error: str | None = "__unset__",
    increment_attempt: bool = False,
    mark_started: bool = False,
    mark_finished: bool = False,
) -> None:
    fields, values = [], []
    if status is not None:
        fields.append("status = ?")
        values.append(status)
    if output is not None:
        fields.append("output_json = ?")
        values.append(json.dumps(output, ensure_ascii=False))
    if error != "__unset__":
        fields.append("error_message = ?")
        values.append(error)
    if increment_attempt:
        fields.append("attempt = attempt + 1")
    if mark_started:
        fields.append("started_at = ?")
        values.append(_now())
    if mark_finished:
        fields.append("finished_at = ?")
        values.append(_now())
    values.extend([job_id, stage_name])

    with _lock, connect() as conn:
        conn.execute(
            f"UPDATE job_stages SET {', '.join(fields)} WHERE job_id = ? AND stage_name = ?", values
        )


# ---------- segments ----------


def replace_segments(job_id: int, segments: list[dict]) -> None:
    """Ідемпотентно перезаписує всі сегменти job'а (для повторного запуску visual_plan)."""
    now = _now()
    with _lock, connect() as conn:
        conn.execute("DELETE FROM segments WHERE job_id = ?", (job_id,))
        for idx, seg in enumerate(segments):
            conn.execute(
                """
                INSERT INTO segments (job_id, segment_index, text, visual_keywords,
                                       suggested_source, shot_prompt, motion_prompt, visual_type,
                                       sfx_tags, ambience_tag, is_cta, pause_seconds, status, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)
                """,
                (
                    job_id,
                    idx,
                    seg["text"],
                    seg.get("visual_keywords"),
                    seg.get("suggested_source"),
                    seg.get("shot"),
                    seg.get("motion"),
                    seg.get("visual_type") or "still",
                    json.dumps(seg.get("sfx") or [], ensure_ascii=False),
                    seg.get("ambience") or "",
                    1 if seg.get("cta") else 0,
                    seg.get("pause_seconds") or None,
                    now,
                ),
            )


def list_segments(job_id: int) -> list[dict]:
    with _lock, connect() as conn:
        rows = conn.execute(
            "SELECT * FROM segments WHERE job_id = ? ORDER BY segment_index", (job_id,)
        ).fetchall()
        return [dict(r) for r in rows]


def update_segment(job_id: int, segment_index: int, **fields) -> None:
    if not fields:
        return
    fields["updated_at"] = _now()
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [job_id, segment_index]
    with _lock, connect() as conn:
        conn.execute(
            f"UPDATE segments SET {set_clause} WHERE job_id = ? AND segment_index = ?", values
        )


# ---------- qa_issues ----------


def add_qa_issue(
    job_id: int,
    *,
    segment_id: int | None,
    issue_type: str,
    start_sec: float | None = None,
    end_sec: float | None = None,
    severity: str = "warning",
    resolution: str = "unresolved",
    notes: str | None = None,
) -> None:
    with _lock, connect() as conn:
        conn.execute(
            """
            INSERT INTO qa_issues (job_id, segment_id, issue_type, start_sec, end_sec,
                                    severity, resolution, notes, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (job_id, segment_id, issue_type, start_sec, end_sec, severity, resolution, notes, _now()),
        )


def list_qa_issues(job_id: int) -> list[dict]:
    with _lock, connect() as conn:
        rows = conn.execute(
            "SELECT * FROM qa_issues WHERE job_id = ? ORDER BY id", (job_id,)
        ).fetchall()
        return [dict(r) for r in rows]


def resolve_qa_issue(issue_id: int, resolution: str) -> None:
    with _lock, connect() as conn:
        conn.execute("UPDATE qa_issues SET resolution = ? WHERE id = ?", (resolution, issue_id))
