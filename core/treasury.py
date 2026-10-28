"""Treasury — казначейство роя и его бюджетные клетки (Конституция §2).

Каждому агенту выдаётся дневной лимит. Любой расход внешнего ресурса списывается
с клетки. Лимит исчерпан → статус overrun → оркестратор ретирует агента (апоптоз).

Деньги — только целые микро-доллары (µ$, 1 $ = 1_000_000 µ$), никакого float.
"""
from __future__ import annotations

import sqlite3
import time
from datetime import date
from pathlib import Path

MICRO = 1_000_000  # 1 USD в µ$

SCHEMA = """
CREATE TABLE IF NOT EXISTS budget_cells (
    agent_id      TEXT    PRIMARY KEY,
    daily_limit_u INTEGER NOT NULL,
    spent_u       INTEGER NOT NULL DEFAULT 0,
    revenue_u     INTEGER NOT NULL DEFAULT 0,
    day           TEXT    NOT NULL DEFAULT '',
    status        TEXT    NOT NULL DEFAULT 'active',   -- active | overrun | apoptosed
    note          TEXT    NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS transactions (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    ts       REAL    NOT NULL,
    agent_id TEXT    NOT NULL,
    kind     TEXT    NOT NULL,        -- spend | revenue
    amount_u INTEGER NOT NULL,
    note     TEXT    NOT NULL DEFAULT ''
);
"""


class Treasury:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def _today(self) -> str:
        return date.fromtimestamp(time.time()).isoformat()

    # --- клетки ---------------------------------------------------------
    def open_cell(self, agent_id: str, daily_limit_u: int):
        self.conn.execute(
            """INSERT INTO budget_cells (agent_id, daily_limit_u, day, status)
               VALUES (?, ?, ?, 'active')
               ON CONFLICT(agent_id) DO NOTHING""",
            (agent_id, daily_limit_u, self._today()),
        )
        self.conn.commit()

    def _cell(self, agent_id: str) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM budget_cells WHERE agent_id = ?", (agent_id,)
        ).fetchone()

    def _rollover_day(self, cell: sqlite3.Row):
        """Суточный сброс счётчика ( Burlingame rule: день ушёл — лимит новый)."""
        today = self._today()
        if cell["day"] != today:
            self.conn.execute(
                "UPDATE budget_cells SET spent_u = 0, day = ?, status = 'active' WHERE agent_id = ?",
                (today, cell["agent_id"]),
            )
            self.conn.commit()

    # --- операции -------------------------------------------------------
    def spend(self, agent_id: str, amount_u: int, note: str = "") -> bool:
        """Списать расход. Вернёт False, если лимит исчерпан → агент под апоптоз.

        Клетка не в 'active' (overrun/apoptosed) — блок: деньги не уходят,
        даже если апоптоз по какой-то причине задержался.
        """
        cell = self._cell(agent_id)
        if cell is None:
            return False
        self._rollover_day(cell)
        cell = self._cell(agent_id)
        if cell["status"] != "active":
            return False
        new_spent = cell["spent_u"] + amount_u
        self.conn.execute(
            "INSERT INTO transactions (ts, agent_id, kind, amount_u, note) VALUES (?, ?, 'spend', ?, ?)",
            (time.time(), agent_id, amount_u, note),
        )
        if new_spent > cell["daily_limit_u"] and cell["status"] == "active":
            self.conn.execute(
                "UPDATE budget_cells SET spent_u = ?, status = 'overrun' WHERE agent_id = ?",
                (new_spent, agent_id),
            )
            self.conn.commit()
            return False
        self.conn.execute(
            "UPDATE budget_cells SET spent_u = ? WHERE agent_id = ?", (new_spent, agent_id)
        )
        self.conn.commit()
        return True

    def revenue(self, agent_id: str, amount_u: int, source: str = ""):
        cell = self._cell(agent_id)
        if cell is None:
            return
        self.conn.execute(
            "INSERT INTO transactions (ts, agent_id, kind, amount_u, note) VALUES (?, ?, 'revenue', ?, ?)",
            (time.time(), agent_id, amount_u, source),
        )
        self.conn.execute(
            "UPDATE budget_cells SET revenue_u = revenue_u + ? WHERE agent_id = ?",
            (amount_u, agent_id),
        )
        self.conn.commit()

    # --- аналитика ------------------------------------------------------
    def roi(self, agent_id: str) -> float:
        cell = self._cell(agent_id)
        if cell is None or cell["spent_u"] == 0:
            return 0.0
        return cell["revenue_u"] / cell["spent_u"]

    def victims(self) -> list[dict]:
        """Кандидаты на апоптоз: overrun или ROI < 0.5 при наличии расходов."""
        rows = self.conn.execute("SELECT * FROM budget_cells").fetchall()
        out = []
        for c in rows:
            if c["status"] == "overrun":
                out.append(dict(c))
        return out

    def force_retire(self, agent_id: str, reason: str):
        self.conn.execute(
            "UPDATE budget_cells SET status = 'apoptosed', note = ? WHERE agent_id = ?",
            (reason, agent_id),
        )
        self.conn.commit()

    def cells(self, status: str | None = None) -> list[dict]:
        if status:
            rows = self.conn.execute(
                "SELECT * FROM budget_cells WHERE status = ? ORDER BY agent_id", (status,)
            ).fetchall()
        else:
            rows = self.conn.execute("SELECT * FROM budget_cells ORDER BY agent_id").fetchall()
        return [dict(r) for r in rows]

    def summary(self) -> dict:
        row = self.conn.execute(
            "SELECT COALESCE(SUM(spent_u),0) AS spent, COALESCE(SUM(revenue_u),0) AS revenue "
            "FROM budget_cells"
        ).fetchone()
        return {"spent_u": row["spent"], "revenue_u": row["revenue"]}

    def close(self):
        self.conn.close()
