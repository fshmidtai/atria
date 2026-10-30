"""Универсальный delivery-генератор: архив колонии → клиентский Excel/CSV.

Любой кворк из offers/kwork (CVE, гранты, реклама, тендеры) закрывается
одной командой:
    python infra/deliver/colony_report.py <colony> [out.xlsx|.csv] [limit]

Колонки: № · Запись · Источник · Дата · Ссылка + поля предмета
(sum/region/closes/buyer…), которые есть в архиве колонии.
Дедуп и качество уже обеспечены архивом (storage/<colony>/archive.jsonl).
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE_COLS = ["№", "Запись", "Источник", "Дата", "Ссылка"]
# поля предмета, которые подставляются отдельными колонками, если есть
EXTRA = ["buyer", "region", "sum", "closes", "points"]


def _dt(ts) -> str:
    try:
        return datetime.fromtimestamp(float(ts), tz=timezone.utc).strftime(
            "%Y-%m-%d %H:%M UTC")
    except Exception:
        return ""


def load(colony: str) -> list[dict]:
    p = ROOT / "storage" / colony / "archive.jsonl"
    if not p.exists():
        raise SystemExit(f"archive not found: {p}")
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines()
            if l.strip()]


def rows(archive: list[dict], limit: int = 200) -> list[list]:
    extra = [k for k in EXTRA
             if any(it.get(k) for it in archive[:60])]
    out = []
    for i, it in enumerate(archive[:limit], 1):
        row = [i, str(it.get("title", ""))[:200],
               str(it.get("source", "")),
               _dt(it.get("ts")), str(it.get("url", ""))]
        row += [str(it.get(k, "") or "") for k in extra]
        out.append(row)
    return out, extra


def to_xlsx(data: list[list], extra: list[str], out: Path, title: str):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    cols = BASE_COLS + [e.capitalize() for e in extra]
    wb = Workbook()
    ws = wb.active
    ws.title = "Записи"[:31]
    ws.append(cols)
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="1F3864")
        c.alignment = Alignment(vertical="center")
    for r in data:
        ws.append(r)
    widths = [5, 62, 12, 18, 60] + [18] * len(extra)
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(cols))}{len(data) + 1}"
    ws.append([])
    ws.append([f"{title} · собрано автономным роем Атрия из открытых источников"])
    wb.save(out)


def to_csv(data: list[list], extra: list[str]) -> str:
    import csv
    import io
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(BASE_COLS + [e.capitalize() for e in extra])
    w.writerows(data)
    return buf.getvalue()


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: colony_report.py <colony> [out.xlsx|out.csv] [limit]")
        return 1
    colony = sys.argv[1]
    limit = int(sys.argv[3]) if len(sys.argv) > 3 else 200
    archive = load(colony)
    data, extra = rows(archive, limit)
    dst = Path(sys.argv[2]) if len(sys.argv) > 2 else (
        ROOT / "storage" / colony / f"{colony}_report.xlsx")
    print(f"{colony}: archive={len(archive)} → отчёт={len(data)} строк, "
          f"доп.колонки={extra or 'нет'}")
    if str(dst).endswith(".csv"):
        dst.write_text(to_csv(data, extra), encoding="utf-8")
    else:
        to_xlsx(data, extra, dst, colony)
    print("saved:", dst)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
