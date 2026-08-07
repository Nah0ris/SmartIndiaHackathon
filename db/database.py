"""SQLite database layer for test templates, submissions, and athletes.

All writes go through helper functions.  Submissions are immutable once created.
The athletes table is seeded on first init with 5 demo athletes.
"""

import contextlib
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DB_PATH = Path(__file__).resolve().parent.parent / "kirti.db"

# ---------- seed data -------------------------------------------------
_SEED_ATHLETES = [
    ("LeBron James", "Basketball"),
    ("Lionel Messi", "Football"),
    ("Sidharth Sivasankar", "Athletics"),
    ("Cristiano Ronaldo", "Football"),
    ("Lewis Hamilton", "Motorsport"),
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


@contextlib.contextmanager
def _db_connection():
    conn = _connect()
    try:
        yield conn
    finally:
        conn.close()


# ======================================================================
# Initialisation
# ======================================================================

def init_db() -> None:
    """Create tables if they don't exist and seed athlete data."""
    with _db_connection() as conn:
        cur = conn.cursor()

        cur.execute("""
            CREATE TABLE IF NOT EXISTS test_templates (
                id          TEXT PRIMARY KEY,
                sport       TEXT NOT NULL,
                test_type   TEXT NOT NULL,
                pass_criteria TEXT NOT NULL,   -- JSON string
                created_at  TEXT NOT NULL,
                locked      INTEGER NOT NULL DEFAULT 1
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS athletes (
                id          TEXT PRIMARY KEY,
                name        TEXT NOT NULL,
                sport       TEXT NOT NULL,
                created_at  TEXT NOT NULL
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS submissions (
                id            TEXT PRIMARY KEY,
                test_id       TEXT NOT NULL REFERENCES test_templates(id),
                athlete_id    TEXT NOT NULL REFERENCES athletes(id),
                athlete_name  TEXT NOT NULL,
                result_value  REAL NOT NULL,
                passed        INTEGER NOT NULL,
                submitted_at  TEXT NOT NULL
            )
        """)

        # Seed athletes idempotently with deterministic UUIDs
        for name, sport in _SEED_ATHLETES:
            seed_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, name))
            cur.execute(
                "INSERT OR IGNORE INTO athletes (id, name, sport, created_at) VALUES (?, ?, ?, ?)",
                (seed_id, name, sport, _now_iso()),
            )

        conn.commit()


# ======================================================================
# Templates
# ======================================================================

def create_template(sport: str, test_type: str, pass_criteria: dict) -> dict:
    """Create a locked test template.  Returns the created row as a dict."""
    tid = str(uuid.uuid4())
    now = _now_iso()
    with _db_connection() as conn:
        conn.execute(
            "INSERT INTO test_templates (id, sport, test_type, pass_criteria, created_at, locked) "
            "VALUES (?, ?, ?, ?, ?, 1)",
            (tid, sport, test_type, json.dumps(pass_criteria), now),
        )
        conn.commit()
    return {"id": tid, "sport": sport, "test_type": test_type,
            "pass_criteria": pass_criteria, "created_at": now, "locked": True}


def get_template(template_id: str) -> dict | None:
    with _db_connection() as conn:
        row = conn.execute("SELECT * FROM test_templates WHERE id = ?", (template_id,)).fetchone()
    if row is None:
        return None
    d = dict(row)
    d["pass_criteria"] = json.loads(d["pass_criteria"])
    d["locked"] = bool(d["locked"])
    return d


def get_all_templates() -> list[dict]:
    with _db_connection() as conn:
        rows = conn.execute("SELECT * FROM test_templates ORDER BY created_at DESC").fetchall()
    result = []
    for row in rows:
        d = dict(row)
        d["pass_criteria"] = json.loads(d["pass_criteria"])
        d["locked"] = bool(d["locked"])
        result.append(d)
    return result


# ======================================================================
# Athletes
# ======================================================================

def get_all_athletes() -> list[dict]:
    with _db_connection() as conn:
        rows = conn.execute("SELECT * FROM athletes ORDER BY name").fetchall()
    return [dict(r) for r in rows]


def get_athlete(athlete_id: str) -> dict | None:
    with _db_connection() as conn:
        row = conn.execute("SELECT * FROM athletes WHERE id = ?", (athlete_id,)).fetchone()
    return dict(row) if row else None


# ======================================================================
# Submissions (immutable)
# ======================================================================

def create_submission(
    test_id: str,
    athlete_id: str,
    athlete_name: str,
    result_value: float,
    passed: bool,
) -> dict:
    """Record an immutable submission.  Returns the created row."""
    sid = str(uuid.uuid4())
    now = _now_iso()
    with _db_connection() as conn:
        conn.execute(
            "INSERT INTO submissions "
            "(id, test_id, athlete_id, athlete_name, result_value, passed, submitted_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (sid, test_id, athlete_id, athlete_name, result_value, int(passed), now),
        )
        conn.commit()
    return {
        "id": sid, "test_id": test_id, "athlete_id": athlete_id,
        "athlete_name": athlete_name, "result_value": result_value,
        "passed": passed, "submitted_at": now,
    }


def get_submissions_for_test(test_id: str) -> list[dict]:
    with _db_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM submissions WHERE test_id = ? ORDER BY submitted_at DESC",
            (test_id,),
        ).fetchall()
    result = []
    for row in rows:
        d = dict(row)
        d["passed"] = bool(d["passed"])
        result.append(d)
    return result
