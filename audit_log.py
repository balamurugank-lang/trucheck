"""
audit_log.py

Lightweight SQLite audit trail. Every /api/chat request gets logged with:
question, answer, which FAQ sources were cited, caller identity, and
timestamp - so a later dispute ("the bot told me X") has a real record.
"""
import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import List

DB_PATH = os.environ.get("AUDIT_LOG_DB_PATH", "../audit_log.db")

_conn = None


def _get_conn():
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                caller_id TEXT,
                question TEXT NOT NULL,
                answer TEXT NOT NULL,
                sources_json TEXT,
                suggested_questions_json TEXT
            )
            """
        )
        _conn.commit()
    return _conn


def log_interaction(
    caller_id: str,
    question: str,
    answer: str,
    sources: List[dict],
    suggested_questions: List[str],
) -> None:
    """Best-effort logging - a logging failure should never break the chat
    response itself, so callers should wrap this in try/except."""
    conn = _get_conn()
    conn.execute(
        """
        INSERT INTO chat_log
            (timestamp, caller_id, question, answer, sources_json, suggested_questions_json)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            datetime.now(timezone.utc).isoformat(),
            caller_id,
            question,
            answer,
            json.dumps(sources),
            json.dumps(suggested_questions),
        ),
    )
    conn.commit()