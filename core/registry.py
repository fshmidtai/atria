"""Registry — реестр агентов роя.

Агент = строка в БД + бюджетная клетка в казначействе. Спавн идемпотентен:
повторный запуск genesis не дублирует рой.
"""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS agents (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    name    TEXT    UNIQUE NOT NULL,
    role    TEXT    NOT NULL,
    colony  TEXT    NOT NULL,
    status  TEXT    NOT NULL DEFAULT 'active',   -- active | retired
    spawned REAL   NOT NULL,
    note    TEXT    NOT NULL DEFAULT ''
);
"""


class Registry:
    def __init__(self, db_path: str | Path, treasury):
        self.db_path = Path(db_path)
        self.treasury = treasury
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def spawn(self, name: str, role: str, colony: str, daily_limit_u: int) -> int:
        """Создать агента с бюджетной клеткой. Если существует — вернуть его id."""
        row = self.conn.execute("SELECT id FROM agents WHERE name = ?", (name,)).fetchone()
        if row:
            return int(row["id"])
        cur = self.conn.execute(
            "INSERT INTO agents (name, role, colony, status, spawned) VALUES (?, ?, ?, 'active', ?)",
            (name, role, colony, time.time()),
        )
        self.conn.commit()
        self.treasury.open_cell(name, daily_limit_u)
        return int(cur.lastrowid)

    def retire(self, name: str, reason: str):
        self.conn.execute(
            "UPDATE agents SET status = 'retired', note = ? WHERE name = ?", (reason, name)
        )
        self.conn.commit()
        self.treasury.force_retire(name, reason)

    def get(self, name: str) -> dict | None:
        row = self.conn.execute("SELECT * FROM agents WHERE name = ?", (name,)).fetchone()
        return dict(row) if row else None

    def active(self, colony: str | None = None) -> list[dict]:
        if colony:
            rows = self.conn.execute(
                "SELECT * FROM agents WHERE status = 'active' AND colony = ? ORDER BY id", (colony,)
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM agents WHERE status = 'active' ORDER BY id"
            ).fetchall()
        return [dict(r) for r in rows]

    def all(self) -> list[dict]:
        rows = self.conn.execute("SELECT * FROM agents ORDER BY id").fetchall()
        return [dict(r) for r in rows]

    def close(self):
        self.conn.close()
