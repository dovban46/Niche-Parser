"""Локальна історія пошуків (SQLite) — щоб не втрачати і не переоплачувати квотою
вже зроблені пошуки. Файл бази — app/data/history.sqlite3, у git не потрапляє.
"""

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "data" / "history.sqlite3"

_lock = threading.Lock()


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _lock, _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS searches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                params_json TEXT NOT NULL,
                response_json TEXT NOT NULL,
                results_count INTEGER NOT NULL,
                quota_used INTEGER NOT NULL
            )
            """
        )


def save_search(params: dict, response: dict) -> int:
    created_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with _lock, _connect() as conn:
        cur = conn.execute(
            "INSERT INTO searches (created_at, params_json, response_json, results_count, quota_used) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                created_at,
                json.dumps(params, ensure_ascii=False),
                json.dumps(response, ensure_ascii=False),
                len(response.get("results", [])),
                response.get("quota_used_today", 0),
            ),
        )
        return cur.lastrowid


def list_searches(limit: int = 50) -> list[dict]:
    with _lock, _connect() as conn:
        rows = conn.execute(
            "SELECT id, created_at, params_json, results_count, quota_used "
            "FROM searches ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()

    items = []
    for row in rows:
        params = json.loads(row["params_json"])
        items.append(
            {
                "id": row["id"],
                "created_at": row["created_at"],
                "keywords": params.get("keywords", []),
                "region_code": params.get("region_code", ""),
                "published_after_days": params.get("published_after_days"),
                "video_type": params.get("video_type", "all"),
                "results_count": row["results_count"],
                "quota_used": row["quota_used"],
            }
        )
    return items


def get_search(search_id: int) -> dict | None:
    with _lock, _connect() as conn:
        row = conn.execute(
            "SELECT id, created_at, params_json, response_json, results_count, quota_used "
            "FROM searches WHERE id = ?",
            (search_id,),
        ).fetchone()

    if row is None:
        return None

    params = json.loads(row["params_json"])
    return {
        "id": row["id"],
        "created_at": row["created_at"],
        "keywords": params.get("keywords", []),
        "region_code": params.get("region_code", ""),
        "published_after_days": params.get("published_after_days"),
        "video_type": params.get("video_type", "all"),
        "results_count": row["results_count"],
        "quota_used": row["quota_used"],
        "params": params,
        "response": json.loads(row["response_json"]),
    }


def delete_search(search_id: int) -> bool:
    with _lock, _connect() as conn:
        cur = conn.execute("DELETE FROM searches WHERE id = ?", (search_id,))
        return cur.rowcount > 0
