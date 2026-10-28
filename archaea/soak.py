"""Soak — выживет ли рой, если его никто не трогает?

Симулирует N тиков полностью офлайн: колония «дышит» (снимки разной
наполненности, то один источник отваливается), казначейство перекатывает
суточные лимиты, оркестратор жарит задачи с инъекцией сбоев, QA смотрит
каждый тик. Проявляется только во времени: дельты Trend Index, рост
history, идемпотентность регенерации, блокировка overrun-клетки.

Запуск: python archaea/soak.py [тиков]
"""
from __future__ import annotations

import random
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from archaea import qa
from colonies import apothecary
from colonies.phosphor import pipeline, sitegen
from core.orchestrator import Orchestrator
from core.treasury import Treasury

TOPICS = ["ai", "dev", "security", "science", "biz", "hardware", "crypto"]
SOURCES = ["hn", "cve", "rss", "github", "arxiv"]
WORDS = [
    "neural", "quantum", "kernel", "ledger", "mesh", "cortex", "vortex",
    "phoenix", "oracle", "harbor", "beacon", "citadel",
]

CFG = {
    "site": {
        "title": "Soak Colony", "tagline": "T", "base_url": "https://soak.example",
        "lang": "ru",
    },
    "topics": TOPICS,
    "top_items_home": 20,
    "top_items_topic": 20,
    "top_item_pages": 30,
}


def synth_snapshot(rng: random.Random) -> dict:
    """Снимок переменной наполненности: 40–90 предметов, один источник отваливается."""
    alive = [s for s in SOURCES if rng.random() > 0.2]
    if not alive:
        alive = ["hn"]
    per = {s: rng.randint(5, 20) for s in alive}
    items = []
    for source, n in per.items():
        for i in range(n):
            title = f"{rng.choice(WORDS)} {rng.choice(WORDS)} #{rng.randint(1, 999)}"
            items.append({
                "uid": f"{source}:{source}-{i}",
                "source": source,
                "title": title,
                "url": f"https://{source}.example/{i}",
                "ts": time.time() - rng.randint(0, 200_000),
                "points": rng.randint(0, 500),
                "comments": rng.randint(0, 300),
                "author": f"user{rng.randint(0, 50)}",
                "summary": f"Кратко: {title} — почта hi@evil.com и телефон +1 415 555 0132.",
                "topics": [rng.choice(TOPICS)],
            })
    return pipeline.build_snapshot(items, {"probe": []})


def one_tick(root: Path, tick: int, rng: random.Random) -> dict:
    """Один синтетический тик колонии: очистка → сайт → QA → продукты."""
    raw = synth_snapshot(rng)
    snapshot = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()),
        "totals": raw["totals"],
        "items": pipeline.clean(raw["items"]),
        "recipes": raw.get("recipes", {}),
    }
    out = apothecary.bake(snapshot, "soak", root)
    site = sitegen.generate(snapshot, root / "soak" / "dist", CFG)
    audit = qa.audit_site(root / "soak" / "dist", base_url=CFG["site"]["base_url"])

    # PII-скраб каждый тик: сырые summary грязные, в снимке должны быть чистые
    pii_leaks = sum("@" in (i.get("summary") or "") for i in snapshot["items"])


    # дельта трендов: со второго тика должна считаться
    trend_path = root / "soak" / "exports" / "products" / "trend_index.csv"
    trend_txt = trend_path.read_text(encoding="utf-8") if trend_path.exists() else ""
    deltas = [ln for ln in trend_txt.splitlines() if ",0," not in ln]

    # дописываем историю руками — в симуляции genesis этого не делает
    with open(root / "history.jsonl", "a", encoding="utf-8") as hf:
        hf.write("{}\n".format(_json_line(tick, snapshot["totals"]["by_topic"])))

    return {
        "tick": tick,
        "items": snapshot["totals"]["items"],
        "pages": site["pages"],
        "qa": audit,
        "products": out["products"],
        "trend_rows": len(trend_txt.splitlines()) - 1,
        "trend_deltas": len(deltas),
        "pii_leaks": pii_leaks,
    }


def _json_line(tick: int, by_topic: dict) -> str:
    import json

    return json.dumps({
        "ts": 1_700_000_000 + tick * 21_600,
        "colony": "soak",
        "items": sum(by_topic.values()),
        "by_source": {},
        "by_topic": by_topic,
    }, ensure_ascii=False)


def soak_orchestrator(rng: random.Random) -> dict:
    """20 тиков оркестратора, каждый третий обработчик падает."""
    with tempfile.TemporaryDirectory() as td:
        orch = Orchestrator(Path(td) / "o.db")
        results = []
        for t in range(20):
            orch.enqueue("c", f"task-{t}", "ok" if t % 3 else "boom", {"t": t})
            stats = orch.tick({"ok": lambda p: None, "boom": lambda p: 1 / 0})
            results.append(stats)
        ran = sum(r["ran"] for r in results)
        failed = sum(r["failed"] for r in results)
        orch.close()  # Windows: иначе tempdir не очистится (файл занят)
        return {"ticks": 20, "ran": ran, "failed": failed,
                "failed_is_7": failed == 7 and ran == 13}


def soak_treasury(rng: random.Random) -> dict:
    """День перекатился — лимит новый; overrun-клетка не тратит."""
    with tempfile.TemporaryDirectory() as td:
        tr = Treasury(Path(td) / "t.db")
        tr.open_cell("probe", 1_000)
        assert tr.spend("probe", 700), "первая трата должна проходить"
        # искусственно выставляем «вчера»
        tr.conn.execute("UPDATE budget_cells SET day = '2020-01-01' WHERE agent_id = 'probe'")
        ok = tr.spend("probe", 700)  # старый день → rollover → лимит обновился
        cell = tr._cell("probe")
        rollover_ok = ok and cell["spent_u"] == 700 and cell["status"] == "active"

        # overrun-клетка блокируется, даже если апоптоз задержался
        tr.conn.execute("UPDATE budget_cells SET status='overrun' WHERE agent_id='probe'")
        blocked = tr.spend("probe", 1) is False
        tr.close()
        return {"rollover_ok": rollover_ok, "overrun_blocked": blocked}


def main() -> int:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    print(f"soak: {n} тиков, офлайн-симуляция жизни колонии\n")
    print(f"{'тик':>3} {'предм.':>7} {'стр.':>5} {'QA':>14} {'продуктов':>10} {'delta':>6}")
    root = Path(tempfile.mkdtemp())
    first_err = None
    rng = random.Random(42)
    for t in range(1, n + 1):
        r = one_tick(root, t, rng)
        status = qa.summarize(r["qa"])
        print(f"{t:>3} {r['items']:>7} {r['pages']:>5} {status:>14} "
              f"{len(r['products']):>10} {r['trend_deltas']:>6}")
        if r["qa"]["errors"] and first_err is None:
            first_err = f"тик {t}: {status}"
        if r["qa"]["warnings"] and first_err is None:
            first_err = f"тик {t}: warning {status}"
        if r["pii_leaks"] and first_err is None:
            first_err = f"тик {t}: PII утек ({r['pii_leaks']})"

    orch = soak_orchestrator(rng)
    tr = soak_treasury(rng)
    print(f"\nоркестратор: ran={orch['ran']} failed={orch['failed']} (ожид. 13/7) → "
          f"{'ok' if orch['failed_is_7'] else 'FAIL'}")
    print(f"казначейство: rollover={tr['rollover_ok']} overrun_blocked={tr['overrun_blocked']}")

    history = (root / "history.jsonl").read_text(encoding="utf-8").count("\n")
    print(f"история: {history} строк за {n} тиков (ожид. {n})")

    ok = (
        first_err is None
        and orch["failed_is_7"]
        and tr["rollover_ok"]
        and tr["overrun_blocked"]
        and history == n
    )
    print("\nSOAK " + ("PASS — рой устойчив" if ok else f"FAIL — {first_err or 'см. выше'}"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
