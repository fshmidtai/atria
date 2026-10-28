"""Apothecary — дата-алхимия: снимки и история превращаются в продукты.

Вторая половина нулевого денежного цикла: добытые данные не просто лежат,
а упаковываются в готовые к продаже/раздаче продукты (Data Arbitrage).

Продукты (v0.3):
  digest_top.csv    — топ материала дня, плоский BI-формат
  trend_index.csv   — тема → объём сегодня + дельта к прошлому тику (Trend Index)
  cve_digest.csv    — только CVE: cve_id, severity, package, title, url, date
  PRODUCTS.md       — манифест продуктов (заготовка копии для маркетплейсов)

История читается из storage/history.jsonl — и именно прошлые тики,
поэтому bake() зовём ДО_APPEND'а текущей строки.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

DIGEST_COLS = ["uid", "source", "title", "url", "buzz", "date", "topics"]
CVE_COLS = ["cve_id", "severity", "package", "title", "url", "date"]
TREND_COLS = ["colony", "date", "topic", "count", "count_prev", "delta"]


def _read_history(storage_root: Path, colony: str | None = None) -> list[dict]:
    path = Path(storage_root) / "history.jsonl"
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    if colony is not None:
        rows = [r for r in rows if r.get("colony") == colony]
    return rows


def _top_digest(snapshot: dict, outdir: Path, limit: int = 50) -> dict:
    path = outdir / "digest_top.csv"
    items = snapshot["items"][:limit]
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(DIGEST_COLS)
        for it in items:
            w.writerow([
                it.get("uid", ""), it.get("source", ""), it.get("title", ""),
                it.get("url", ""), it.get("buzz", 0), it.get("date", ""),
                "|".join(it.get("topics", [])),
            ])
    return {"rows": len(items)}


def _trend_index(snapshot: dict, colony: str, storage_root: Path, outdir: Path) -> dict:
    """Тема → объём сегодня, объём вчера, дельта. Затравка Trend Index."""
    current = snapshot["totals"].get("by_topic", {})
    date = (snapshot.get("generated_at") or "")[:10]
    prev: dict = {}
    rows = _read_history(storage_root, colony)
    if rows:
        prev = rows[-1].get("by_topic", {})
    path = outdir / "trend_index.csv"
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(TREND_COLS)
        for topic, cnt in current.items():
            p = prev.get(topic, 0)
            w.writerow([colony, date, topic, cnt, p, cnt - p])
    return {"rows": len(current), "has_prev": bool(rows)}


def _cve_digest(snapshot: dict, outdir: Path) -> dict:
    """Только security-сигнал: нормализованный CVE-поток."""
    rows = []
    for it in snapshot["items"]:
        if it.get("source") != "cve":
            continue
        title = it.get("title", "")
        cve_id = title.split(":", 1)[0].strip() if ":" in title else it.get("uid", "").split(":", 1)[-1]
        severity = ""
        summ = it.get("summary", "")
        if summ.lower().startswith("severity:"):
            severity = summ.split(":", 1)[1].split(".")[0].strip()
        rows.append([cve_id, severity, it.get("author", ""), title, it.get("url", ""), it.get("date", "")])
    path = outdir / "cve_digest.csv"
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(CVE_COLS)
        w.writerows(rows)
    return {"rows": len(rows)}


def _manifest(snapshot: dict, colony: str, produced: dict, outdir: Path):
    lines = [
        f"# Продукты колонии `{colony}`",
        "",
        f"Снимок от {snapshot.get('generated_at', 'n/a')}.",
        "Продукты генерируются автоматически каждый тик улья (6 часов) из",
        "публичных источников без ключей. Лицензия: MIT, упоминание источника приветствуется.",
        "",
        "| продукт | что это | строк |",
        "|---|---|---|",
    ]
    for name, meta in produced.items():
        lines.append(f"| `{name}` | {_DESC.get(name, 'авто-продукт')} | {meta.get('rows', 0)} |")
    lines += [
        "",
        "## Схемы",
        "",
        "- `digest_top.csv`: " + ", ".join(DIGEST_COLS),
        "- `trend_index.csv`: " + ", ".join(TREND_COLS),
        "- `cve_digest.csv`: " + " ".join(CVE_COLS) + " (только если в снимке есть CVE)",
    ]
    (outdir / "PRODUCTS.md").write_text("\n".join(lines), encoding="utf-8")


_DESC = {
    "digest_top.csv": "топ материала дня, плоский BI-формат",
    "trend_index.csv": "тема → объём сегодня, вчера, дельта (Trend Index)",
    "cve_digest.csv": "нормализованный CVE-поток: id, severity, package",
}


def trend_for(colony: str, storage_root: str | Path) -> list[dict]:
    """Trend Index последнего тика как словари — публичная страница трендов."""
    path = Path(storage_root) / colony / "exports" / "products" / "trend_index.csv"
    if not path.exists():
        return []
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def bake(snapshot: dict, colony: str, storage_root: str | Path) -> dict:
    outdir = Path(storage_root) / colony / "exports" / "products"
    outdir.mkdir(parents=True, exist_ok=True)

    produced: dict[str, dict] = {}
    produced["digest_top.csv"] = _top_digest(snapshot, outdir)
    produced["trend_index.csv"] = _trend_index(snapshot, colony, storage_root, outdir)
    if any(i.get("source") == "cve" for i in snapshot["items"]):
        produced["cve_digest.csv"] = _cve_digest(snapshot, outdir)
    _manifest(snapshot, colony, produced, outdir)

    return {
        "outdir": str(outdir),
        "products": produced,
        "rows": sum(m.get("rows", 0) for m in produced.values()),
    }
