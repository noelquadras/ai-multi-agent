import sqlite3
import os
import json
from datetime import datetime
from typing import Dict, List, Any, Optional
import asyncio

# =========================
# SQLITE DATABASE LAYER
# =========================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "crew_tasks.db")

# =========================
# REAL-TIME STATE (RAM ONLY)
# =========================
# Subscribers are live browser connections. They cannot be saved to a DB.
subscribers: Dict[str, List[asyncio.Queue]] = {}

def get_db_conn():
    """Returns a connection to the SQLite database."""
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def init_db():
    """Creates tables if they don't exist."""
    with get_db_conn() as conn:
        cursor = conn.cursor()
        # Primary table for overall task status
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tasks (
                task_id TEXT PRIMARY KEY,
                status TEXT,
                model TEXT,
                user_id TEXT,
                project_id TEXT,
                created_at TEXT,
                decision_signal TEXT,
                rejection_feedback TEXT,
                prompt TEXT
            )
        ''')
        # Table for every log/event produced by the agents
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT,
                type TEXT,
                data TEXT,
                timestamp TEXT,
                FOREIGN KEY (task_id) REFERENCES tasks (task_id)
            )
        ''')
        
        # Migration: Add columns if they don't exist
        for column in ["decision_signal", "rejection_feedback", "prompt"]:
            try:
                cursor.execute(f"ALTER TABLE tasks ADD COLUMN {column} TEXT")
            except sqlite3.OperationalError:
                pass  # Column already exists
            
        conn.commit()

def update_task_status(task_id: str, status: str):
    """Updates the status in the DB."""
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE tasks SET status = ? WHERE task_id = ?", (status, task_id))
        conn.commit()

def update_decision_signal(task_id: str, signal: Optional[str]):
    """Updates the decision signal (APPROVED/REJECTED/None) in the DB."""
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE tasks SET decision_signal = ? WHERE task_id = ?", (signal, task_id))
        conn.commit()

def clear_decision_signal(task_id: str):
    """Clears the decision signal after it has been consumed."""
    update_decision_signal(task_id, None)

def update_rejection_feedback(task_id: str, feedback: Optional[str]):
    """Stores rejection feedback from the user."""
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE tasks SET rejection_feedback = ? WHERE task_id = ?", (feedback, task_id))
        conn.commit()

def get_rejection_feedback(task_id: str) -> Optional[str]:
    """Gets rejection feedback if any."""
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT rejection_feedback FROM tasks WHERE task_id = ?", (task_id,))
        row = cursor.fetchone()
        return row[0] if row else None

def get_task_status(task_id: str) -> Optional[Dict[str, Any]]:
    """Get task status, decision_signal, and rejection_feedback."""
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT status, decision_signal, rejection_feedback FROM tasks WHERE task_id = ?", (task_id,))
        row = cursor.fetchone()
        if row:
            return {"status": row[0], "decision_signal": row[1], "rejection_feedback": row[2]}
        return None

def emit_event(task_id: str, event: Dict[str, Any]):
    """Saves event to DB and broadcasts to any live UI listeners."""
    timestamp = datetime.now().isoformat()
    event["timestamp"] = timestamp
    
    # 1. Save to SQLite
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO events (task_id, type, data, timestamp) VALUES (?, ?, ?, ?)",
            (task_id, event.get("type"), json.dumps(event), timestamp)
        )
        conn.commit()

    # 2. Push to active website users (Real-time)
    if task_id in subscribers:
        for q in subscribers[task_id]:
            q.put_nowait(event)

def get_task_prompt(task_id: str) -> Optional[str]:
    """Gets the original prompt for a task."""
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT prompt FROM tasks WHERE task_id = ?", (task_id,))
        row = cursor.fetchone()
        return row[0] if row else None
