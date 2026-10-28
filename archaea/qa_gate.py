"""QA-гейт CI: вердикт после цикла.

genesis — это *работа*: всегда выходит в 0, состояние коммитится, рой живёт
дальше (один сломанный тик не должен убивать автономию).
qa_gate — это *приговор*: если у какой-то колонии QA-ошибки, выходим в 1 —
джоба краснеет, человек замечает, Die Stimme в темноте. Ничто не публикуется
вслепую, но и не блокирует рой.

Запуск: python archaea/qa_gate.py [путь/до/metrics.json]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def parse_err(qa_str: str) -> int:
    """'QA ok:8 warn:0 err:0' → 0."""
    for part in (qa_str or "").split():
        if part.startswith("err:"):
            try:
                return int(part.split(":", 1)[1])
            except Exception:
                pass
    return 0


def gate(metrics_path: Path) -> int:
    if not metrics_path.exists():
        print(f"qa_gate: metrics.json не найден ({metrics_path}) — сначала genesis")
        return 2
    try:
        m = json.loads(metrics_path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"qa_gate: metrics.json не читается: {exc!r}")
        return 2

    colonies = m.get("colonies") or {}
    bad = [(name, c.get("qa") or "?") for name, c in colonies.items() if parse_err(c.get("qa") or "")]

    if bad:
        print("qa_gate: FAIL — публиковать нельзя:")
        for name, s in bad:
            print(f"  !! {name}: {s}")
        return 1

    print(f"qa_gate: PASS — {len(colonies)} колоний чистые")
    for name, c in colonies.items():
        print(f"  {name}: {c.get('qa')} · {c.get('pages', 0)} страниц")
    return 0


if __name__ == "__main__":
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "storage" / "metrics.json"
    sys.exit(gate(path))
