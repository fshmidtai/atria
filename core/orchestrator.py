"""Orchestrator — однозадачный cron-движок роя.

tick() делает один проход: берёт все готовые задачи, исполняет их, закрывает.
Идемпотентен и безопасен для перезапуска — именно поэтому его можно дёргать
хоть каждую минуту из GitHub Actions, systemd-таймера или Docker-цикла.

Никаких висящих демонов: cron-пульс приходит снаружи, ядро только реагирует.
"""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Callable

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    colony   TEXT    NOT NULL,
    title    TEXT    NOT NULL,
    handler  TEXT    NOT NULL,
    payload  TEXT    NOT NULL DEFAULT '{}',
    status   TEXT    NOT NULL DEFAULT 'pending',  -- pending | running | done | failed
    attempt  INTEGER NOT NULL DEFAULT 0,
    enqueued REAL    NOT NULL,
    claim_ts REAL,
    done_ts  REAL,
    result   TEXT
);
CREATE INDEX IF NOT EXISTS idx_tasks_handler_status ON tasks(handler, status);
"""

HandlerFn = Callable[[dict], object]


class Orchestrator:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.isolation_level = None  # ручные транзакции
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    # --- очередь --------------------------------------------------------
    def enqueue(self, colony: str, title: str, handler: str, payload: dict | None = None):
        cur = self.conn.execute(
            "INSERT INTO tasks (colony, title, handler, payload, status, enqueued) "
            "VALUES (?, ?, ?, ?, 'pending', ?)",
            (colony, title, handler, json.dumps(payload or {}, ensure_ascii=False), time.time()),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def claim_next(self, handler: str) -> dict | None:
        """Атомарно забрать следующую задачу для обработчика."""
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            row = self.conn.execute(
                "SELECT * FROM tasks WHERE handler = ? AND status = 'pending' ORDER BY id LIMIT 1",
                (handler,),
            ).fetchone()
            if row is None:
                self.conn.execute("ROLLBACK")
                return None
            self.conn.execute(
                "UPDATE tasks SET status = 'running', claim_ts = ?, attempt = attempt + 1 WHERE id = ?",
                (time.time(), row["id"]),
            )
            self.conn.execute("COMMIT")
            return dict(row)
        except Exception:
            self.conn.execute("ROLLBACK")
            raise

    def complete(self, task_id: int, status: str, result: object):
        self.conn.execute(
            "UPDATE tasks SET status = ?, done_ts = ?, result = ? WHERE id = ?",
            (status, time.time(), json.dumps(result, ensure_ascii=False, default=str)[:4000], task_id),
        )
        self.conn.commit()

    # --- сердце роя ------------------------------------------------------
    def tick(self, handlers: dict[str, HandlerFn]) -> dict:
        """Один удар пульса: исполнить все готовые задачи для известных обработчиков."""
        stats = {"ran": 0, "failed": 0, "idle": True}
        for handler, fn in handlers.items():
            while True:
                task = self.claim_next(handler)
                if task is None:
                    break
                stats["idle"] = False
                try:
                    payload = json.loads(task["payload"]) if task["payload"] else {}
                    out = fn(payload)
                    self.complete(task["id"], "done", out)
                    stats["ran"] += 1
                except Exception as e:
                    self.complete(task["id"], "failed", {"error": f"{e!r}"})
                    stats["failed"] += 1
        return stats

    def stats(self) -> dict:
        rows = self.conn.execute(
            "SELECT status, COUNT(*) AS n FROM tasks GROUP BY status"
        ).fetchall()
        return {r["status"]: r["n"] for r in rows}

    def close(self):
        self.conn.close()
