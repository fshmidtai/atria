"""Ledger — append-only журнал событий роя.

v0.1: SQLite (нулевых зависимостей, работает и локально, и на Oracle-узле).
v0.2: тот же интерфейс поверх Supabase Postgres — общая память для всех колоний.

Удалять события нельзя: история роя — его ДНК (Конституция §5).
"""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ts      REAL    NOT NULL,
    colony  TEXT    NOT NULL,
    agent   TEXT    NOT NULL,
    type    TEXT    NOT NULL,
    payload TEXT    NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_events_ts     ON events(ts);
CREATE INDEX IF NOT EXISTS idx_events_colony ON events(colony);
"""


class Ledger:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    # --- запись ---------------------------------------------------------
    def event(self, colony: str, agent: str, type_: str, payload: dict | None = None) -> int:
        cur = self.conn.execute(
            "INSERT INTO events (ts, colony, agent, type, payload) VALUES (?, ?, ?, ?, ?)",
            (time.time(), colony, agent, type_, json.dumps(payload or {}, ensure_ascii=False)),
        )
        self.conn.commit()
        return cur.lastrowid

    # --- чтение ---------------------------------------------------------
    def recent(self, limit: int = 50, colony: str | None = None) -> list[dict]:
        if colony:
            rows = self.conn.execute(
                "SELECT * FROM events WHERE colony = ? ORDER BY id DESC LIMIT ?", (colony, limit)
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            try:
                d["payload"] = json.loads(d["payload"])
            except Exception:
                d["payload"] = {}
            out.append(d)
        return out

    def count(self, colony: str | None = None) -> int:
        if colony:
            row = self.conn.execute("SELECT COUNT(*) AS n FROM events WHERE colony = ?", (colony,)).fetchone()
        else:
            row = self.conn.execute("SELECT COUNT(*) AS n FROM events").fetchone()
        return int(row["n"])

    def close(self):
        self.conn.close()
