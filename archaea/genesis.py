"""Genesis — кнопка «запустить жизнь».

Что делает один запуск:
  1. инициализирует ядро (ledger / treasury / registry / orchestrator) в storage/atria.db
  2. спавнит первую колонию (Phosphor) — идемпотентно, повторные запуски не дубли
  3. ставит задачу на цикл колонии и прогоняет её через orchestrator.tick()
  4. исполняет апоптоз-правила (Казначейство)
  5. печатает отчёт роя и кладёт storage/metrics.json (для HF Space-пульта)

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
    # (имя, роль, колония, дневной лимит в µ$)
    ("radar", "scout", "phosphor", 2_000_000),      # $2.00/день на сбор
    ("refiner", "refinery", "phosphor", 2_000_000),  # $2.00/день на обработку
    ("scribe", "writer", "phosphor", 2_000_000),     # $2.00/день на упаковку
    ("merchant", "trade", "phosphor", 1_000_000),    # $1.00/день на публикацию
]


def load_config(name: str) -> dict:
    cfg_path = ROOT / "colonies" / name / "config.json"
    return json.loads(cfg_path.read_text(encoding="utf-8"))


def phosphor_cycle_factory(config: dict, treasury: Treasury, ledger: Ledger):
    """Обработчик задачи 'phosphor_cycle' — один цикл колонии Phosphor."""
    from colonies.phosphor import pipeline, sitegen

    workdir = ROOT / "storage" / "phosphor"

    def run(payload: dict) -> dict:
        snapshot = pipeline.cycle(workdir, config, treasury=treasury, ledger=ledger)

        dist = ROOT / "colonies" / "phosphor" / "dist"
        site = sitegen.generate(snapshot, dist, config)

        treasury.spend("merchant", 100, note="publish snapshot")
        ledger.event("phosphor", "merchant", "published", {
            "pages": site["pages"],
            "out": site["outdir"],
            "items": snapshot["totals"]["items"],
        })
        return {
            "items": snapshot["totals"]["items"],
            "by_source": snapshot["totals"]["by_source"],
            "pages": site["pages"],
        }

    return run


def render_report(ledger: Ledger, treasury: Treasury, registry: Registry,
                  orch: Orchestrator, tick_stats: dict, site_out: dict | None,
                  snapshot: dict | None) -> str:
    lines = []
    lines.append("=" * 62)
    lines.append("                    УЛЕЙ · ОТЧЁТ ЦИКЛА")
    lines.append("=" * 62)

    lines.append("\n▸ АГЕНТЫ:")
    for a in registry.all():
        cell = treasury.cells()
        c = next((x for x in cell if x["agent_id"] == a["name"]), None)
        spent = c["spent_u"] / 1_000_000 if c else 0
        limit = c["daily_limit_u"] / 1_000_000 if c else 0
        roi = treasury.roi(a["name"])
        lines.append(
            f"  {a['name']:<10} {a['role']:<9} {a['colony']:<9} {a['status']:<8} "
            f"потрачено ${spent:.4f}/${limit:.2f}  ROI {roi:.2f}"
        )

    lines.append("\n▸ БЮДЖЕТ:")
    s = treasury.summary()
    lines.append(f"  расход ${s['spent_u']/1e6:.4f} · выручка ${s['revenue_u']/1e6:.4f}")

    lines.append("\n▸ ЗАДАЧИ:")
    lines.append(f"  {orch.stats()} · тик: {tick_stats}")

    vics = treasury.victims()
    if vics:
        lines.append("\n▸ АПОПТОЗ:")
        for v in vics:
            lines.append(f"  {v['agent_id']}: {v['status']} → ретирую")
            registry.retire(v["agent_id"], "budget overrun")
    else:
        lines.append("\n▸ АПОПТОЗ: нет кандидатов — все клетки в норме")

    lines.append("\n▸ СОБЫТИЯ (последние 10):")
    for e in ledger.recent(10):
        lines.append(f"  [{e['colony']}/{e['agent']}] {e['type']} {json.dumps(e['payload'], ensure_ascii=False)[:90]}")

    if snapshot:
        t = snapshot["totals"]
        lines.append("\n▸ КОЛОНИЯ PHOSPHOR:")
        lines.append(f"  предметов в снимке: {t['items']}")
        lines.append(f"  по источникам:     {t['by_source']}")
        lines.append(f"  топ-темы:          {list(t['by_topic'])[:6]}")
        top = snapshot["items"][:5]
        for i, it in enumerate(top, 1):
            lines.append(f"  {i}. [{it['source']}] {it['title'][:70]} (buzz {it['buzz']})")

    if site_out:
        lines.append(f"\n▸ САЙТ: {site_out['pages']} страниц → colonies/phosphor/dist/")
        for u in site_out["sitemap"][:5]:
            lines.append(f"    {u}")
        lines.append("    ...")

    return "\n".join(lines)


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
        exports = ROOT / "storage" / "phosphor" / "exports"
        if exports.exists():
            api.upload_folder(
                folder_path=str(exports),
                repo_id=repo,
                repo_type="dataset",
                path_in_repo="phosphor",
            )
        ledger.event("core", "atria", "state_published", {"repo": repo})
    except Exception as e:
        ledger.event("core", "atria", "state_publish_failed", {"error": repr(e)[:200]})


def main():
    started = time.time()
    storage = ROOT / "storage"
    storage.mkdir(exist_ok=True)
    db = storage / "atria.db"

    ledger = Ledger(db)
    treasury = Treasury(db)
    registry = Registry(db, treasury)
    orch = Orchestrator(db)

    ledger.event("core", "atria", "genesis", {
        "db": str(db), "agents": [a[0] for a in SEED_AGENTS],
    })

    # 1. спавн колонии
    for name, role, colony, limit in SEED_AGENTS:
        registry.spawn(name, role, colony, limit)

    # 2. конфиг и обработчики
    config = load_config("phosphor")
    handlers = {
        "phosphor_cycle": phosphor_cycle_factory(config, treasury, ledger),
    }

    # 3. задача на цикл + пульс
    orch.enqueue("phosphor", "data-refine-publish cycle", "phosphor_cycle",
                 {"workdir": str(ROOT / "storage" / "phosphor")})
    tick_stats = orch.tick(handlers)

    # 4. результаты
    done = [t for t in []]
    site_out = None
    snapshot = None
    if tick_stats["ran"]:
        last = ledger.recent(1, colony="phosphor")
        # снимок перечитываем из экспорта
        snap_path = storage / "phosphor" / "exports" / "dataset.json"
        if snap_path.exists():
            snapshot = json.loads(snap_path.read_text(encoding="utf-8"))
        dist = ROOT / "colonies" / "phosphor" / "dist"
        if (dist / "index.html").exists():
            pages = sum(1 for _ in dist.rglob("*.html"))
            site_out = {"pages": pages, "sitemap": [
                config["site"]["base_url"] + u
                for u in ["/", "/data.html", "/about.html", "/sitemap.xml"]
            ]}

    # 5. апоптоз — отдельным актом, чтобы попасть в отчёт
    for v in treasury.victims():
        registry.retire(v["agent_id"], "budget overrun")

    # 6. metrics.json для HF Space-пульта
    metrics = {
        "generated_at": time.time(),
        "elapsed_s": round(time.time() - started, 2),
        "tick": tick_stats,
        "agents": registry.all(),
        "budget": treasury.summary(),
        "tasks": orch.stats(),
        "totals": snapshot["totals"] if snapshot else None,
        "top_items": [
            {"title": i["title"], "source": i["source"], "buzz": i["buzz"],
             "url": i["url"], "topics": i["topics"]}
            for i in (snapshot or {}).get("items", [])[:15]
        ],
    }
    (storage / "metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    publish_state(ledger)
    ledger.event("core", "atria", "tick_done", {"elapsed_s": metrics["elapsed_s"]})

    print(render_report(ledger, treasury, registry, orch, tick_stats, site_out, snapshot))

    ledger.close()
    treasury.close()
    registry.close()
    orch.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
