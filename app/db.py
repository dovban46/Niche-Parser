"""Сира робота з SQLite (без ORM — той самий підхід, що й у сусідньому parser/history.py).

Зберігає лише метадані/статуси job'ів; важкі бінарні артефакти лежать окремо в STORAGE_ROOT
(див. app/storage.py) і в базу не потрапляють.
"""

import sqlite3
import threading

from .config import DB_PATH

_lock = threading.Lock()


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, ddl_type: str) -> None:
    """Легка міграція для баз, створених до появи цієї колонки (CREATE TABLE IF NOT
    EXISTS не чіпає вже існуючу таблицю) — щоб не втрачати тестові job'и при апдейті."""
    existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type}")


def init_db() -> None:
    with _lock, _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                topic TEXT NOT NULL,
                niche TEXT NOT NULL,
                target_duration_minutes INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                current_stage TEXT,
                config_json TEXT NOT NULL,
                error_message TEXT,
                final_video_path TEXT,
                script_approved INTEGER NOT NULL DEFAULT 0,
                language TEXT NOT NULL DEFAULT 'uk'
            )
            """
        )
        _ensure_column(conn, "jobs", "script_approved", "INTEGER NOT NULL DEFAULT 0")
        _ensure_column(conn, "jobs", "language", "TEXT NOT NULL DEFAULT 'uk'")
        _ensure_column(conn, "jobs", "voice_id", "TEXT")
        _ensure_column(conn, "jobs", "style_id", "TEXT")
        _ensure_column(conn, "jobs", "preview_seconds", "INTEGER")
        # DEFAULT 1: job'и, створені до появи досьє, вважаються схваленими — не зависають на новій паузі.
        _ensure_column(conn, "jobs", "dossier_approved", "INTEGER NOT NULL DEFAULT 1")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS job_stages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id INTEGER NOT NULL REFERENCES jobs(id),
                stage_name TEXT NOT NULL,
                stage_order INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                attempt INTEGER NOT NULL DEFAULT 0,
                started_at TEXT,
                finished_at TEXT,
                output_json TEXT,
                error_message TEXT,
                log_path TEXT,
                UNIQUE(job_id, stage_name)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS segments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id INTEGER NOT NULL REFERENCES jobs(id),
                segment_index INTEGER NOT NULL,
                text TEXT NOT NULL,
                visual_keywords TEXT,
                suggested_source TEXT,
                start_ms INTEGER,
                duration_ms INTEGER,
                audio_path TEXT,
                visual_source TEXT NOT NULL DEFAULT 'pending',
                visual_prompt TEXT,
                visual_path TEXT,
                visual_clip_path TEXT,
                visual_provider TEXT,
                visual_license TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                updated_at TEXT NOT NULL,
                UNIQUE(job_id, segment_index)
            )
            """
        )
        for column, ddl in (
            ("shot_prompt", "TEXT"),
            ("motion_prompt", "TEXT"),
            ("visual_type", "TEXT"),
            ("sfx_tags", "TEXT"),
            ("ambience_tag", "TEXT"),
            ("is_cta", "INTEGER NOT NULL DEFAULT 0"),
            # beats_json: для "still"-сегментів довших за STILL_MAX_SECONDS — JSON-список
            # {"shot": ..., "visual_path": ...} по одному на кожні ~3с показу (замість одного
            # фото, крутити яке довше під різними напрямками камери — фідбек: так виглядає погано).
            ("beats_json", "TEXT"),
            # pause_seconds: "німа" пауза-дихання (текст="", лише картинка/анімація + sfx, без голосу) —
            # для довших відео, щоб не було суцільної безперервної доріжки диктора (app/stages/tts_synthesize.py
            # генерує тишу цієї тривалості замість виклику TTS).
            ("pause_seconds", "REAL"),
        ):
            _ensure_column(conn, "segments", column, ddl)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS qa_issues (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id INTEGER NOT NULL REFERENCES jobs(id),
                segment_id INTEGER REFERENCES segments(id),
                issue_type TEXT NOT NULL,
                start_sec REAL,
                end_sec REAL,
                severity TEXT NOT NULL DEFAULT 'warning',
                resolution TEXT NOT NULL DEFAULT 'unresolved',
                notes TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        _migrate_dossier_stage(conn)


def _migrate_dossier_stage(conn: sqlite3.Connection) -> None:
    """Старим job'ам додаємо стадію research_dossier зі статусом skipped (на початок порядку)."""
    ids = [
        r["id"]
        for r in conn.execute(
            "SELECT j.id FROM jobs j WHERE NOT EXISTS "
            "(SELECT 1 FROM job_stages s WHERE s.job_id = j.id AND s.stage_name = 'research_dossier')"
        )
    ]
    for job_id in ids:
        conn.execute("UPDATE job_stages SET stage_order = stage_order + 1 WHERE job_id = ?", (job_id,))
        conn.execute(
            "INSERT INTO job_stages (job_id, stage_name, stage_order, status) VALUES (?, 'research_dossier', 0, 'skipped')",
            (job_id,),
        )


def connect() -> sqlite3.Connection:
    """Публічний доступ до з'єднання для repository.py (з тим самим локом на запис)."""
    return _connect()


def get_lock() -> threading.Lock:
    return _lock
