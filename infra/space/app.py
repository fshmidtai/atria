"""Atria Hive Console — пульт управления роем. v0.2

Читает:
  1. metrics.json / history.jsonl рядом с собой (локальная проверка)
  2. из HF-датасета (HF_STATE_REPO) — туда их автоматически грузит genesis.py
     после каждого цикла, если заданы HF_TOKEN и HF_STATE_REPO.

Показывает: состояние роя, карточки колоний (QA!, дата-продукты, страницы),
топ снимка, историю тиков, сырой metrics.json.

Запуск локально:   python infra/space/app.py
Деплой:            см. infra/space/README.md
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

try:
    import gradio as gr
except ImportError:
    # gradio стоит только в Space — чистые функции пульта должны быть
    # импортируемы и тестируемы на любой машине (selftest этим пользуется).
    gr = None

SPACE_DIR = Path(__file__).parent
METRICS_LOCAL = SPACE_DIR / "metrics.json"
HISTORY_LOCAL = SPACE_DIR / "history.jsonl"


def _hf_download(filename: str) -> Path | None:
    repo = os.environ.get("HF_STATE_REPO", "").strip()
    if not repo:
        return None
    try:
        from huggingface_hub import hf_hub_download

        return Path(hf_hub_download(
            repo_id=repo, filename=filename, repo_type="dataset",
            token=os.environ.get("HF_TOKEN") or None,
        ))
    except Exception:
        return None


def load_metrics() -> dict:
    if METRICS_LOCAL.exists():
        try:
            return json.loads(METRICS_LOCAL.read_text(encoding="utf-8"))
        except Exception:
            pass
    p = _hf_download("metrics.json")
    if p:
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:
            return {"error": f"состояние недоступно: {e!r}"}
    return {"error": "metrics.json ещё нет — прогони archaea/genesis.py хотя бы раз"}


def _qa_mark(qa: str) -> str:
    err = 0
    for part in (qa or "").split():
        if part.startswith("err:"):
            try:
                err = int(part.split(":", 1)[1])
            except Exception:
                pass
    if err:
        return f"❌ `{qa}`"
    return f"✅ `{qa or 'нет данных'}`"


def _fmt_u(u) -> str:
    return f"${(u or 0) / 1_000_000:.4f}"


def _load_history() -> list[list]:
    """history.jsonl → [[дата, колония, предметов]] — для таблицы истории."""
    path = HISTORY_LOCAL if HISTORY_LOCAL.exists() else _hf_download("history.jsonl")
    if not path or not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except Exception:
            continue
        rows.append([
            datetime.fromtimestamp(int(r.get("ts", 0))).strftime("%m-%d %H:%M"),
            r.get("colony", "?"),
            r.get("items", 0),
        ])
    return rows[-60:]


def refresh():
    m = load_metrics()
    if "error" in m:
        return f"## ⚠️ {m['error']}", [], [], ""

    budget = m.get("budget") or {}
    tasks = m.get("tasks") or {}
    agents = m.get("agents") or []
    colonies = m.get("colonies") or {}

    agents_md = "\n".join(
        f"- `{a['name']}` — {a['role']} / {a['colony']} — **{a['status']}**"
        for a in agents
    )
    cards = []
    for name, c in colonies.items():
        site = c.get("site") or {}
        totals = c.get("totals") or {}
        products = c.get("products") or {}
        prod_md = "\n".join(
            f"  - `{k}` — {v.get('rows', 0)} строк"
            for k, v in products.items()
        ) or "  — нет"
        base = site.get("base_url") or ""
        link = f" — **[сайт]({base})**" if base else ""
        cards.append(
            f"### {site.get('title', name)} (`{name}`){link}\n"
            f"- QA: {_qa_mark(c.get('qa'))}"
            f"- Страниц: {c.get('pages', 0)} · предметов: {totals.get('items', 0)}"
            f"- Источники: {totals.get('by_source')}"
            f"- Дата-продукты:\n{prod_md}"
        )

    cards_md = "\n\n".join(cards)
    stats_md = f"""## 🐝 Состояние улья

- **Цикл:** {m.get('tick')} · завершён за {m.get('elapsed_s')}с
- **Задачи:** {tasks} · **Бюджет:** расход {_fmt_u(budget.get('spent_u'))} · выручка {_fmt_u(budget.get('revenue_u'))}
- **Снимок от:** {m.get('generated_at', '')}

### Агенты

{agents_md}

---

{cards_md}
"""
    rows = [
        [it.get("title", "")[:90], it.get("source", ""), it.get("buzz", 0),
         ", ".join(it.get("topics", []))]
        for name, c in colonies.items()
        for it in c.get("top_items", [])
    ]
    history = _load_history()
    raw = json.dumps(m, ensure_ascii=False, indent=2)
    return stats_md, rows, history, raw[:8000]


if gr is not None:
    with gr.Blocks(title="Atria — пульт улья", theme=gr.themes.Soft()) as demo:
        gr.Markdown(
            "# 🐝 Atria · Hive Console\n"
            "Пульт автономного роя: метрики цикла, агенты и бюджеты, карточки колоний "
            "(QA-аудит, дата-продукты), топ снимка и история тиков. "
            "Состояние обновляется автоматически после каждого цикла улья."
        )
        with gr.Row():
            btn = gr.Button("Опросить улей", variant="primary")
        stats = gr.Markdown()
        gr.Markdown("### Топ снимка (все колонии)")
        table = gr.Dataframe(
            headers=["заголовок", "источник", "buzz", "темы"],
            datatype=["str", "str", "number", "str"],
            wrap=True,
        )
        gr.Markdown("### История тиков (ближайшие 60)")
        history = gr.Dataframe(
            headers=["тик", "колония", "предметов"],
            datatype=["str", "str", "number"],
        )
        with gr.Accordion("Сырой metrics.json", open=False):
            raw = gr.Code(label="metrics.json", language="json")

        btn.click(refresh, outputs=[stats, table, history, raw])
        demo.load(refresh, outputs=[stats, table, history, raw])

    if __name__ == "__main__":
        demo.launch(server_name="0.0.0.0", server_port=7860)
