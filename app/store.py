"""SQLite-backed webhook dedupe, short-term conversation memory, and the
transaction leads table.

Known tradeoff: on Render's default disk this file does not survive a
redeploy or restart, which resets conversation memory, dedupe state, and the
leads table. Acceptable for v1 given short, transactional WhatsApp chats —
but note that leads ARE the system of record here (there's no Sheets backup
in this build), so an ephemeral disk means real transaction history could be
lost on redeploy. Use a persistent disk (Render's paid persistent disk add-on,
or an external DB) before relying on this for real transaction volume.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

import config

_SCHEMA = """
CREATE TABLE IF NOT EXISTS seen_messages (
    wamid TEXT PRIMARY KEY,
    received_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS conversations (
    phone TEXT PRIMARY KEY,
    history_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_phone TEXT NOT NULL,
    direction TEXT NOT NULL,
    asset TEXT NOT NULL,
    amount TEXT,
    payment_method TEXT,
    customer_payout_details TEXT,
    notes TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

_OPEN_STATUSES = ("pending", "confirmed")


def _db_path() -> Path:
    path = Path(config.AGENT_DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(_SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


def is_duplicate(wamid: str) -> bool:
    with _connect() as conn:
        row = conn.execute("SELECT 1 FROM seen_messages WHERE wamid = ?", (wamid,)).fetchone()
        return row is not None


def mark_seen(wamid: str) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO seen_messages (wamid, received_at) VALUES (?, ?)",
            (wamid, datetime.now(timezone.utc).isoformat()),
        )


def get_history(phone: str) -> list[dict]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT history_json FROM conversations WHERE phone = ?", (phone,)
        ).fetchone()
        return json.loads(row[0]) if row else []


def save_history(phone: str, history: list[dict]) -> None:
    trimmed = history[-config.MAX_HISTORY_TURNS :]
    # A tool-calling round trip is [assistant(tool_use), user(tool_result), ...]
    # chained onto one user turn — slicing by raw message count can start the
    # window mid-sequence, leaving a tool_result with no preceding tool_use
    # (or an assistant message first), which the API rejects outright. Only a
    # plain-string user message is a safe place to resume.
    while trimmed and not (trimmed[0]["role"] == "user" and isinstance(trimmed[0]["content"], str)):
        trimmed = trimmed[1:]
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO conversations (phone, history_json, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(phone) DO UPDATE SET
                history_json = excluded.history_json,
                updated_at = excluded.updated_at
            """,
            (phone, json.dumps(trimmed, default=str), datetime.now(timezone.utc).isoformat()),
        )


def _row_to_lead(row: sqlite3.Row) -> dict:
    lead = dict(row)
    lead["lead_id"] = f"LD{lead['id']}"
    return lead


def create_lead(
    *,
    customer_phone: str,
    direction: str,
    asset: str,
    amount: str | None,
    payment_method: str | None,
    customer_payout_details: str | None,
    notes: str | None,
) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO leads (
                customer_phone, direction, asset, amount, payment_method,
                customer_payout_details, notes, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
            """,
            (customer_phone, direction, asset, amount, payment_method, customer_payout_details, notes, now, now),
        )
        lead_id = cursor.lastrowid
        row = conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
        return _row_to_lead(row)


def _parse_lead_id(lead_id: str) -> int | None:
    digits = lead_id.strip().upper().removeprefix("LD").strip()
    return int(digits) if digits.isdigit() else None


def get_lead(lead_id: str) -> dict | None:
    numeric_id = _parse_lead_id(lead_id)
    if numeric_id is None:
        return None
    with _connect() as conn:
        row = conn.execute("SELECT * FROM leads WHERE id = ?", (numeric_id,)).fetchone()
        return _row_to_lead(row) if row else None


def update_lead_status(lead_id: str, status: str, notes: str | None = None) -> dict | None:
    numeric_id = _parse_lead_id(lead_id)
    if numeric_id is None:
        return None
    with _connect() as conn:
        existing = conn.execute("SELECT * FROM leads WHERE id = ?", (numeric_id,)).fetchone()
        if not existing:
            return None
        merged_notes = notes if notes else existing["notes"]
        conn.execute(
            "UPDATE leads SET status = ?, notes = ?, updated_at = ? WHERE id = ?",
            (status, merged_notes, datetime.now(timezone.utc).isoformat(), numeric_id),
        )
        row = conn.execute("SELECT * FROM leads WHERE id = ?", (numeric_id,)).fetchone()
        return _row_to_lead(row)


def get_leads_for_phone(phone: str) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM leads WHERE customer_phone = ? ORDER BY id DESC", (phone,)
        ).fetchall()
        return [_row_to_lead(r) for r in rows]


def get_most_recent_open_lead(phone: str) -> dict | None:
    with _connect() as conn:
        placeholders = ",".join("?" * len(_OPEN_STATUSES))
        row = conn.execute(
            f"""
            SELECT * FROM leads
            WHERE customer_phone = ? AND status IN ({placeholders})
            ORDER BY id DESC LIMIT 1
            """,
            (phone, *_OPEN_STATUSES),
        ).fetchone()
        return _row_to_lead(row) if row else None


def get_pending_leads() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM leads WHERE status = 'pending' ORDER BY id ASC"
        ).fetchall()
        return [_row_to_lead(r) for r in rows]


def list_open_leads() -> list[dict]:
    """Pending + confirmed leads, oldest first — the working set the owner
    agent searches over to resolve a natural-language reference like "that
    USDT order" to a real lead ID."""
    with _connect() as conn:
        placeholders = ",".join("?" * len(_OPEN_STATUSES))
        rows = conn.execute(
            f"SELECT * FROM leads WHERE status IN ({placeholders}) ORDER BY id ASC",
            _OPEN_STATUSES,
        ).fetchall()
        return [_row_to_lead(r) for r in rows]
