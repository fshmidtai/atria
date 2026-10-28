"""Atria Hive Console — пульт управления роем.

Читает metrics.json:
  1. рядом с собой (локальная проверка / ручная копия)
  2. из HF-датасета (HF_STATE_REPO) — туда его автоматически грузит genesis.py
     после каждого цикла, если заданы HF_TOKEN и HF_STATE_REPO.

Запуск локально:   python infra/space/app.py
Деплой:            см. infra/space/README.md
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import gradio as gr

METRICS_LOCAL = Path(__file__).parent / "metrics.json"


def load_metrics() -> dict:
    if METRICS_LOCAL.exists():
        try:
            return json.loads(METRICS_LOCAL.read_text(encoding="utf-8"))
        except Exception:
            pass
    repo = os.environ.get("HF_STATE_REPO", "").strip()
    if repo:
        try:
            from huggingface_hub import hf_hub_download

            p = hf_hub_download(
                repo_id=repo,
                filename="metrics.json",
                repo_type="dataset",
                token=os.environ.get("HF_TOKEN") or None,
            )
            return json.loads(Path(p).read_text(encoding="utf-8"))
        except Exception as e:
            return {"error": f"состояние недоступно: {e!r}"}
    return {"error": "metrics.json ещё нет — прогони archaea/genesis.py хотя бы раз"}


def _fmt_u(u) -> str:
    return f"${(u or 0) / 1_000_000:.4f}"


def refresh() -> tuple[str, list, str]:
    m = load_metrics()
    if "error" in m:
        return f"⚠️ {m['error']}", [], ""

    totals = m.get("totals") or {}
    budget = m.get("budget") or {}
    agents = m.get("agents") or []
    agents_md = "\n".join(
        f"- `{a['name']}` — {a['role']} / {a['colony']} — **{a['status']}**"
        for a in agents
    )
    stats_md = f"""
### Состояние улья

- **Цикл:** {m.get('tick')} · завершён за {m.get('elapsed_s')}с
- **Задачи:** {m.get('tasks')}
- **Бюджет:** расход {_fmt_u(budget.get('spent_u'))} · выручка {_fmt_u(budget.get('revenue_u'))}
- **Предметов в снимке:** {totals.get('items')} · источники: {totals.get('by_source')}

### Агенты

{agents_md}
"""
    rows = [
        [it.get("title", "")[:90], it.get("source", ""), it.get("buzz", 0),
         ", ".join(it.get("topics", []))]
        for it in m.get("top_items", [])
    ]
    raw = json.dumps(m, ensure_ascii=False, indent=2)
    return stats_md, rows, raw[:8000]


with gr.Blocks(title="Atria — пульт улья", theme=gr.themes.Soft()) as demo:
    gr.Markdown(
        "# 🐝 Atria · Hive Console\n"
        "Пульт автономного роя: метрики цикла, агенты и их бюджеты, топ снимка. "
        "Состояние обновляется автоматически после каждого цикла улья."
    )
    with gr.Row():
        btn = gr.Button("Опросить улей", variant="primary")
    stats = gr.Markdown()
    gr.Markdown("### Топ снимка")
    table = gr.Dataframe(
        headers=["заголовок", "источник", "buzz", "темы"],
        datatype=["str", "str", "number", "str"],
        wrap=True,
    )
    with gr.Accordion("Сырой metrics.json", open=False):
        raw = gr.Code(label="metrics.json", language="json")

    btn.click(refresh, outputs=[stats, table, raw])
    demo.load(refresh, outputs=[stats, table, raw])


if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860)
