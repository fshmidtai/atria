"""Genesis — кнопка «запустить жизнь».

Что делает один запуск:
  1. инициализирует ядро (ledger / treasury / registry / orchestrator) в storage/atria.db
  2. спавнит агентов роя — идемпотентно, повторные запуски не дублируют
  3. находит все колонии (colonies/*/config.json) и ставит задачу на цикл каждой
  4. прогоняет всё через orchestrator.tick() — один удар пульса
  5. исполняет апоптоз-правила казначейства
  6. печатает отчёт роя и кладёт storage/metrics.json (для HF Space-пульта),
     опционально публикует состояние в HuggingFace-датасет

Запуск: python archaea/genesis.py  (или ./run.sh, ./run.ps1)
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Windows: консоль по умолчанию в cp1251 — принудительно UTF-8, иначе рой не может
# даже рассказать, как прожил свой день.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:
        pass

from core.ledger import Ledger
from core.orchestrator import Orchestrator
from core.registry import Registry
from core.treasury import Treasury

SEED_AGENTS = [
    # (имя, роль, колония, дневной лимит в µ$) — общие агенты роя на все колонии
    ("radar", "scout", "core", 2_000_000),      # $2.00/день на сбор
    ("refiner", "refinery", "core", 2_000_000),  # $2.00/день на обработку
    ("scribe", "writer", "core", 2_000_000),     # $2.00/день на упаковку
    ("merchant", "trade", "core", 1_000_000),    # $1.00/день на публикацию
]


def discovered_colonies() -> list[str]:
    """Колония = любая папка в colonies/ с config.json. Новую колонию добавляем
    просто создав config.json — genesis подхватит её без правок кода."""
    base = ROOT / "colonies"
    if not base.exists():
        return []
    return sorted(
        d.name for d in base.iterdir()
        if d.is_dir() and (d / "config.json").exists()
    )


def load_config(name: str) -> dict:
    return json.loads((ROOT / "colonies" / name / "config.json").read_text(encoding="utf-8"))


def colony_cycle_factory(treasury: Treasury, ledger: Ledger):
    """Обработчик 'colony_cycle' — один цикл любой колонии (параметризуется payload)."""
    from colonies.phosphor import pipeline, sitegen

    def run(payload: dict) -> dict:
        colony = payload["colony"]
        config = load_config(colony)

        snapshot = pipeline.cycle(
            ROOT / "storage" / colony, config, treasury=treasury, ledger=ledger
        )
        site = sitegen.generate(
            snapshot, ROOT / "colonies" / colony / "dist", config
        )

        treasury.spend("merchant", 100, note=f"publish {colony}")
        ledger.event(colony, "merchant", "published", {
            "pages": site["pages"],
            "out": site["outdir"],
            "items": snapshot["totals"]["items"],
        })
        return {
            "colony": colony,
            "items": snapshot["totals"]["items"],
            "by_source": snapshot["totals"]["by_source"],
            "pages": site["pages"],
        }

    return run


def publish_state(ledger: Ledger):
    """Опционально: выложить состояние роя в HF-датасет (для Space-пульта).

    Работает только если заданы HF_TOKEN и HF_STATE_REPO. Без них — тихий пропуск:
    колония не должна зависеть от внешних сервисов (Конституция §1.4).
    """
    import os

    token = os.environ.get("HF_TOKEN", "").strip()
    repo = os.environ.get("HF_STATE_REPO", "").strip()
    if not token or not repo:
        return
    try:
        from huggingface_hub import HfApi

        api = HfApi(token=token)
        metrics_path = ROOT / "storage" / "metrics.json"
        api.upload_file(
            path_or_fileobj=str(metrics_path),
            path_in_repo="metrics.json",
            repo_id=repo,
            repo_type="dataset",
        )
        for colony_dir in (ROOT / "storage").iterdir():
            exports = colony_dir / "exports"
            if exports.exists():
                api.upload_folder(
                    folder_path=str(exports),
                    repo_id=repo,
                    repo_type="dataset",
                    path_in_repo=colony_dir.name,
                )
        ledger.event("core", "atria", "state_published", {"repo": repo})
    except Exception as e:
        ledger.event("core", "atria", "state_publish_failed", {"error": repr(e)[:200]})


def _fmt_u(u) -> str:
    return f"${(u or 0) / 1_000_000:.4f}"


def render_report(registry: Registry, treasury: Treasury, orch: Orchestrator,
                  tick_stats: dict, snapshots: dict, sites: dict) -> str:
    lines = []
    lines.append("=" * 62)
    lines.append("                    УЛЕЙ · ОТЧЁТ ЦИКЛА")
    lines.append("=" * 62)

    lines.append("\n▸ АГЕНТЫ:")
    cells = {c["agent_id"]: c for c in treasury.cells()}
    for a in registry.all():
        c = cells.get(a["name"])
        spent = (c["spent_u"] / 1e6) if c else 0
        limit = (c["daily_limit_u"] / 1e6) if c else 0
        lines.append(
            f"  {a['name']:<10} {a['role']:<9} {a['colony']:<6} {a['status']:<8} "
            f"потрачено ${spent:.4f}/${limit:.2f}  ROI {treasury.roi(a['name']):.2f}"
        )

    s = treasury.summary()
    lines.append("\n▸ БЮДЖЕТ:")
    lines.append(f"  расход {_fmt_u(s['spent_u'])} · выручка {_fmt_u(s['revenue_u'])}")

    lines.append("\n▸ ЗАДАЧИ:")
    lines.append(f"  {orch.stats()} · тик: {tick_stats}")

    vics = treasury.victims()
    if vics:
        lines.append("\n▸ АПОПТОЗ:")
        for v in vics:
            lines.append(f"  {v['agent_id']}: {v['status']} → ретирую")
    else:
        lines.append("\n▸ АПОПТОЗ: нет кандидатов — все клетки в норме")

    for name, snapshot in snapshots.items():
        t = snapshot["totals"]
        cfg = load_config(name)
        site = sites.get(name, {})
        lines.append(f"\n▸ КОЛОНИЯ {name.upper()} ({cfg['site']['title']}):")
        lines.append(f"  предметов в снимке: {t['items']}")
        lines.append(f"  по источникам:     {t['by_source']}")
        lines.append(f"  топ-темы:          {list(t['by_topic'])[:6]}")
        for i, it in enumerate(snapshot["items"][:3], 1):
            lines.append(f"  {i}. [{it['source']}] {it['title'][:70]} (buzz {it['buzz']})")
        if site:
            lines.append(f"  сайт: {site['pages']} страниц → colonies/{name}/dist/")

    return "\n".join(lines)


def main():
    started = time.time()
    storage = ROOT / "storage"
    storage.mkdir(exist_ok=True)
    db = storage / "atria.db"

    ledger = Ledger(db)
    treasury = Treasury(db)
    registry = Registry(db, treasury)
    orch = Orchestrator(db)

    colonies = discovered_colonies()
    ledger.event("core", "atria", "genesis", {
        "db": str(db), "colonies": colonies, "agents": [a[0] for a in SEED_AGENTS],
    })

    # 1. спавн роя (агенты общие — обслуживают все колонии)
    for name, role, colony, limit in SEED_AGENTS:
        registry.spawn(name, role, colony, limit)

    # 2. задачи на циклы + пульс
    handlers = {"colony_cycle": colony_cycle_factory(treasury, ledger)}
    for name in colonies:
        orch.enqueue(name, f"{name} cycle", "colony_cycle", {"colony": name})
    tick_stats = orch.tick(handlers)

    # 3. снимки и сайты
    snapshots: dict[str, dict] = {}
    sites: dict[str, dict] = {}
    for name in colonies:
        snap_path = storage / name / "exports" / "dataset.json"
        if snap_path.exists():
            snapshots[name] = json.loads(snap_path.read_text(encoding="utf-8"))
        dist = ROOT / "colonies" / name / "dist"
        if (dist / "index.html").exists():
            sites[name] = {
                "pages": sum(1 for _ in dist.rglob("*.html")),
                "base_url": load_config(name)["site"]["base_url"],
            }

    # 4. апоптоз
    for v in treasury.victims():
        registry.retire(v["agent_id"], "budget overrun")

    # 4b. таймсерии роя — затравка «индекса трендов» (будущий дата-продукт).
    # append-only JSONL: один факт на колонию за тик, файл — в git.
    now_ts = int(time.time())
    with open(storage / "history.jsonl", "a", encoding="utf-8") as hf:
        for name, s in snapshots.items():
            t = s["totals"]
            hf.write(json.dumps({
                "ts": now_ts,
                "colony": name,
                "items": t["items"],
                "by_source": t["by_source"],
                "by_topic": t["by_topic"],
            }, ensure_ascii=False) + "\n")

    # 5. metrics.json — питание для HF Space-пульта
    metrics = {
        "generated_at": time.time(),
        "elapsed_s": round(time.time() - started, 2),
        "tick": tick_stats,
        "agents": registry.all(),
        "budget": treasury.summary(),
        "tasks": orch.stats(),
        "colonies": {
            name: {
                "site": load_config(name)["site"],
                "totals": s["totals"],
                "pages": sites.get(name, {}).get("pages", 0),
                "top_items": [
                    {"title": i["title"], "source": i["source"], "buzz": i["buzz"],
                     "url": i["url"], "topics": i["topics"]}
                    for i in s.get("items", [])[:15]
                ],
            }
            for name, s in snapshots.items()
        },
    }
    (storage / "metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    publish_state(ledger)
    ledger.event("core", "atria", "tick_done", {"elapsed_s": metrics["elapsed_s"]})

    print(render_report(registry, treasury, orch, tick_stats, snapshots, sites))

    ledger.close()
    treasury.close()
    registry.close()
    orch.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
