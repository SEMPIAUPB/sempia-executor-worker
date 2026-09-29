import sqlite3
import json
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

DB_PATH = 'outbox.db'

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS outbox_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            submission_id TEXT NOT NULL,
            payload TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'PENDING',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def save_to_outbox(submission_id: str, payload: dict):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO outbox_events (submission_id, payload, status) VALUES (?, ?, 'PENDING')",
            (submission_id, json.dumps(payload))
        )
        conn.commit()
    except Exception as e:
        logger.error(f"Failed to save event to outbox: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()

def get_pending_events() -> List[Dict[str, Any]]:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, submission_id, payload FROM outbox_events WHERE status = 'PENDING'")
    rows = cursor.fetchall()
    conn.close()
    
    events = []
    for row in rows:
        events.append({
            "id": row[0],
            "submission_id": row[1],
            "payload": json.loads(row[2])
        })
    return events

def mark_event_processed(event_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE outbox_events SET status = 'PROCESSED', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (event_id,)
    )
    conn.commit()
    conn.close()
