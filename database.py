import sqlite3
import os
import json
from datetime import datetime
from typing import Dict, List, Any
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
                decision_signal TEXT  -- New column to store approved/rejected signal
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
        
        # Check if decision_signal column exists (migration for existing db)
        try:
            cursor.execute("ALTER TABLE tasks ADD COLUMN decision_signal TEXT")
        except sqlite3.OperationalError:
            # Column likely already exists
            pass
            
        conn.commit()

def update_task_status(task_id: str, status: str):
    """Updates the status in the DB."""
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE tasks SET status = ? WHERE task_id = ?", (status, task_id))
        conn.commit()

def update_decision_signal(task_id: str, signal: str):
    """Updates the decision signal (APPROVED/REJECTED) in the DB."""
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE tasks SET decision_signal = ? WHERE task_id = ?", (signal, task_id))
        conn.commit()

def get_task_status(task_id: str):
    """Get content of status and decision_signal."""
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT status, decision_signal FROM tasks WHERE task_id = ?", (task_id,))
        row = cursor.fetchone()
        if row:
            return {"status": row[0], "decision_signal": row[1]}
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
