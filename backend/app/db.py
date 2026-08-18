"""SQLite boundary. Rows in, dicts out; no ORM and no SQL anywhere else."""

import json
import sqlite3
import uuid
from datetime import UTC, datetime

from app.config import DB_PATH

_SCHEMA = """
CREATE TABLE IF NOT EXISTS manuals (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    filename    TEXT NOT NULL,
    page_count  INTEGER NOT NULL,
    page_offset INTEGER,
    ingested_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    id         TEXT PRIMARY KEY,
    manual_id  TEXT NOT NULL REFERENCES manuals(id),
    title      TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id             TEXT PRIMARY KEY,
    session_id     TEXT NOT NULL REFERENCES sessions(id),
    role           TEXT NOT NULL,
    content        TEXT NOT NULL,
    source         TEXT,
    format         TEXT,
    citations_json TEXT,
    created_at     TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS messages_session ON messages(session_id, created_at);

-- The handoff package (D12). The transcript is not copied here; it is the session's messages.
CREATE TABLE IF NOT EXISTS escalations (
    id         TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    manual_id  TEXT NOT NULL,
    question   TEXT NOT NULL,
    reason     TEXT NOT NULL,
    pages_json TEXT NOT NULL,
    status     TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS escalations_status ON escalations(status, created_at);
"""

# Added after messages existed, so it cannot live in _SCHEMA's CREATE IF NOT EXISTS.
_MIGRATIONS = (
    "ALTER TABLE messages ADD COLUMN escalation_id TEXT",
    "ALTER TABLE sessions ADD COLUMN unresolved_streak INTEGER NOT NULL DEFAULT 0",
)


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(_SCHEMA)
    for statement in _MIGRATIONS:
        try:
            connection.execute(statement)
        except sqlite3.OperationalError:
            pass  # already applied
    return connection


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


# --- manuals -------------------------------------------------------------------

def upsert_manual(id: str, title: str, filename: str, page_count: int, offset: int | None) -> None:
    with connect() as db:
        db.execute(
            "INSERT INTO manuals VALUES (?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET"
            " title=excluded.title, filename=excluded.filename,"
            " page_count=excluded.page_count, page_offset=excluded.page_offset,"
            " ingested_at=excluded.ingested_at",
            (id, title, filename, page_count, offset, _now()),
        )


def list_manuals() -> list[dict]:
    with connect() as db:
        return [dict(r) for r in db.execute("SELECT * FROM manuals ORDER BY title")]


def get_manual(id: str) -> dict | None:
    with connect() as db:
        row = db.execute("SELECT * FROM manuals WHERE id = ?", (id,)).fetchone()
    return dict(row) if row else None


# --- sessions ------------------------------------------------------------------

def create_session(manual_id: str, title: str) -> dict:
    session = {
        "id": uuid.uuid4().hex[:12],
        "manual_id": manual_id,
        "title": title[:80],
        "created_at": _now(),
        "updated_at": _now(),
    }
    with connect() as db:
        db.execute(
            "INSERT INTO sessions (id,manual_id,title,created_at,updated_at)"
            " VALUES (:id,:manual_id,:title,:created_at,:updated_at)",
            session,
        )
    return session


def list_sessions() -> list[dict]:
    with connect() as db:
        return [
            dict(r)
            for r in db.execute(
                "SELECT s.*, (SELECT COUNT(*) FROM messages m WHERE m.session_id = s.id)"
                " AS messages FROM sessions s ORDER BY s.updated_at DESC"
            )
        ]


def rename_session(id: str, title: str) -> None:
    with connect() as db:
        db.execute("UPDATE sessions SET title = ? WHERE id = ?", (title[:80], id))


def set_unresolved_streak(id: str, streak: int) -> None:
    """How many turns in a row have failed to resolve the user's problem (D14)."""
    with connect() as db:
        db.execute("UPDATE sessions SET unresolved_streak = ? WHERE id = ?", (streak, id))


def get_session(id: str) -> dict | None:
    with connect() as db:
        row = db.execute("SELECT * FROM sessions WHERE id = ?", (id,)).fetchone()
    return dict(row) if row else None


# --- messages ------------------------------------------------------------------

def add_message(
    session_id: str,
    role: str,
    content: str,
    source: str | None = None,
    format: str | None = None,
    citations: list | None = None,
    escalation_id: str | None = None,
) -> dict:
    message = {
        "id": uuid.uuid4().hex[:12],
        "session_id": session_id,
        "role": role,
        "content": content,
        "source": source,
        "format": format,
        "citations_json": json.dumps(citations) if citations is not None else None,
        "created_at": _now(),
        "escalation_id": escalation_id,
    }
    with connect() as db:
        db.execute(
            "INSERT INTO messages (id,session_id,role,content,source,format,citations_json,"
            "created_at,escalation_id) VALUES (:id,:session_id,:role,:content,:source,:format,"
            ":citations_json,:created_at,:escalation_id)",
            message,
        )
        db.execute("UPDATE sessions SET updated_at = ? WHERE id = ?", (_now(), session_id))
    return message


def list_messages(session_id: str) -> list[dict]:
    """Escalation reason joined in, so a reopened conversation renders the handoff in full."""
    with connect() as db:
        rows = db.execute(
            "SELECT m.*, e.reason AS escalation_reason FROM messages m"
            " LEFT JOIN escalations e ON e.id = m.escalation_id"
            " WHERE m.session_id = ? ORDER BY m.created_at, m.rowid",
            (session_id,),
        )
        return [
            {**dict(r), "citations": json.loads(r["citations_json"] or "[]")} for r in rows
        ]


# --- escalations ---------------------------------------------------------------

def create_escalation(
    session_id: str, manual_id: str, question: str, reason: str, pages: list[int]
) -> dict:
    """The reference is what the user is shown, so it is short and readable (D12)."""
    row = {
        "id": f"ESC-{uuid.uuid4().hex[:6].upper()}",
        "session_id": session_id,
        "manual_id": manual_id,
        "question": question,
        "reason": reason,
        "pages_json": json.dumps(pages),
        "status": "open",
        "created_at": _now(),
        "updated_at": _now(),
    }
    with connect() as db:
        db.execute(
            "INSERT INTO escalations VALUES (:id,:session_id,:manual_id,:question,:reason,"
            ":pages_json,:status,:created_at,:updated_at)",
            row,
        )
    return {**row, "pages": pages}


def list_escalations(status: str | None = None) -> list[dict]:
    query = "SELECT * FROM escalations"
    parameters: tuple = ()
    if status:
        query += " WHERE status = ?"
        parameters = (status,)
    with connect() as db:
        rows = db.execute(query + " ORDER BY created_at DESC", parameters)
        return [{**dict(r), "pages": json.loads(r["pages_json"])} for r in rows]


def get_escalation(id: str) -> dict | None:
    """The full handoff package: the record, its session, and the whole transcript (D14)."""
    with connect() as db:
        row = db.execute("SELECT * FROM escalations WHERE id = ?", (id,)).fetchone()
    if row is None:
        return None
    return {
        **dict(row),
        "pages": json.loads(row["pages_json"]),
        "session": get_session(row["session_id"]),
        "transcript": list_messages(row["session_id"]),
    }


def set_escalation_status(id: str, status: str) -> None:
    with connect() as db:
        db.execute(
            "UPDATE escalations SET status = ?, updated_at = ? WHERE id = ?", (status, _now(), id)
        )
