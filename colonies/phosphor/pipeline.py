"""Pipeline — конвейер колонии Phosphor.

Сбор → дедуп → скоринг «базза» → тегирование тем → снимок (snapshot) →
экспорт датасета (JSON + CSV + data-card для HuggingFace).

Скоринг алгоритмический (LLM не нужен): buzz = points + 3×comments + надбавка
за свежесть. Темы — словарный матч. Так колония живёт на $0 и без ключей.
"""
from __future__ import annotations

import csv
import json
import re
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from colonies.phosphor import sources as sources_mod

TOPIC_KEYWORDS = {
    "ai": ["ai", "ml", "llm", "gpt", "neural", "transformer", "machine learning",
           "deep learning", "agent", "openai", "diffusion", "rag", "fine-tune",
           "training", "model", "anthropic", "qwen", "deepseek", "vllm"],
    "dev": ["dev", "api", "sdk", "framework", "library", "rust", "python", "typescript",
            "compiler", "kubernetes", "docker", "coding", "debugger", "ide", "editor",
            "database", "postgres", "git", "terminal", "bundler"],
    "crypto": ["crypto", "bitcoin", "ethereum", "blockchain", "web3", "defi", "nft",
               "solana", "token", "smart contract", "zktlsnark", "zero-knowledge"],
    "science": ["physics", "biology", "chemistry", "quantum", "space", "gene", "protein",
                "climate", "paper", "fusion", "material", "math"],
    "biz": ["startup", "funding", "saas", "revenue", "b2b", "market", "invest", "ipo",
            "acquisition", "founder", "valuation", "series a", "profit"],
    "security": ["security", "vulnerab", "zero-day", "malware", "ransomware", "encryption",
                 "privacy", "cve", "exploit", "breach", "ransom"],
    "hardware": ["chip", "gpu", "cpu", "datacenter", "server", "robot", "drone", "sensor",
                 "semiconductor", "edge", "rtx", "accelerator"],
}

SOURCE_LABELS = {
    "hn": "Hacker News",
    "arxiv": "arXiv",
    "github": "GitHub",
}


# ---------------------------------------------------------------- обработка
def tag_topics(item: dict) -> list[str]:
    hay = f"{item.get('title', '')} {item.get('summary', '')}".lower()
    return [t for t, kws in TOPIC_KEYWORDS.items() if any(k in hay for k in kws)]


def buzz_score(item: dict, now: float | None = None) -> int:
    now = now or time.time()
    age_h = max(0.0, (now - float(item.get("ts", now))) / 3600.0)
    recency = 80 if age_h < 24 else (30 if age_h < 72 else (10 if age_h < 24 * 7 else 0))
    return int(item.get("points", 0) + 3 * item.get("comments", 0) + recency)


def _title_key(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()


def collect(recipes: list) -> list[dict]:
    """Собрать все рецепты источников, слить в один список."""
    raw = sources_mod.fetch_recipes(recipes)
    items = []
    for bucket in raw.values():
        items.extend(bucket)
    return items


def clean(items: list[dict], now: float | None = None) -> list[dict]:
    """Дедуп (по uid и по нормализованному заголовку), подсчёт buzz, теги.

    Толерантна к неполным item'ам: внешние источники бывают рваными,
    конвейер не должен падать из-за одного кривого поля.
    """
    now = now or time.time()
    by_uid: dict[str, dict] = {}
    by_title: dict[str, dict] = {}
    for it in items:
        if not it.get("title") or not it.get("url"):
            continue
        uid = it.get("uid") or f"{it.get('source', 'x')}:{it['title'][:60]}"
        if uid in by_uid:
            continue
        key = _title_key(it["title"])
        prev = by_title.get(key)
        if prev is not None:
            # крест-источник: оставляем вариант с большим buzz-потенциалом
            if (it.get("points", 0) + 3 * it.get("comments", 0)) <= (
                prev.get("points", 0) + 3 * prev.get("comments", 0)
            ):
                continue
            by_uid.pop(prev["uid"], None)
        it = dict(it)
        it["uid"] = uid
        it["buzz"] = buzz_score(it, now)
        it["topics"] = tag_topics(it)
        it["date"] = datetime.fromtimestamp(
            float(it.get("ts", now)), tz=timezone.utc
        ).strftime("%Y-%m-%d")
        by_uid[uid] = it
        by_title[key] = it
    return sorted(by_uid.values(), key=lambda x: x["buzz"], reverse=True)


# ---------------------------------------------------------------- снимок
def build_snapshot(items: list[dict], recipes: list) -> dict:
    by_source = Counter(i["source"] for i in items)
    by_recipe = Counter(i.get("recipe", "?") for i in items)
    by_topic = Counter(t for i in items for t in i["topics"])
    domains = Counter(urlparse(i["url"]).netloc.replace("www.", "") for i in items if i["url"])
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sources_used": [r.get("kind", r) if isinstance(r, dict) else r for r in (recipes or [])],
        "totals": {
            "items": len(items),
            "by_source": dict(by_source),
            "by_recipe": dict(by_recipe.most_common()),
            "by_topic": dict(by_topic.most_common()),
            "top_domains": domains.most_common(25),
        },
        "items": items,
    }


# ---------------------------------------------------------------- экспорт
def export(snapshot: dict, outdir: str | Path) -> dict:
    """Упаковать датасет: dataset.json + dataset.csv + DATA_CARD.md (для HuggingFace)."""
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    json_path = outdir / "dataset.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)

    csv_path = outdir / "dataset.csv"
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["uid", "source", "title", "url", "buzz", "points", "comments",
                    "author", "date", "topics"])
        for it in snapshot["items"]:
            w.writerow([
                it["uid"], it["source"], it["title"], it["url"], it["buzz"],
                it["points"], it["comments"], it["author"], it["date"],
                "|".join(it["topics"]),
            ])

    gen = snapshot["generated_at"]
    card_path = outdir / "DATA_CARD.md"
    card_path.write_text(
        f"""---
language: en
license: mit
pretty_name: Phosphor Tech Buzz Radar
task_categories: [text-classification, summarization]
---

# Phosphor — Tech Buzz Radar ({gen})

Ежедневный снимок резонансных публикаций tech-экосистемы:

- **Hacker News** — front page (посты, поинты, комментарии)
- **arXiv** — cs.AI / cs.CL / cs.LG (свежие препринты)
- **GitHub** — новые репозитории со звёздами за последние 7 дней

## Поля

| поле | описание |
|---|---|
| `uid` | стабильный идентификатор вида `источник:id` |
| `title` | заголовок |
| `url` | ссылка на исходник |
| `buzz` | скоринг роя: `points + 3×comments + надбавка за свежесть` |
| `points` / `comments` | метрики источника (звёзды/форки для GitHub) |
| `topics` | авто-теги: ai, dev, crypto, science, biz, security, hardware |
| `date` | UTC-дата публикации |

## Условия

Данные собираются только из публичных источников без ключей. Соблюдается
robots.txt и ToS площадок. Датасет обновляется автоматически каждые 6 часов.
""",
        encoding="utf-8",
    )
    return {
        "json": str(json_path),
        "csv": str(csv_path),
        "card": str(card_path),
        "items": snapshot["totals"]["items"],
    }


# ---------------------------------------------------------------- цикл
def cycle(workdir: str | Path, config: dict, treasury=None, ledger=None) -> dict:
    """Полный цикл колонии: сбор → очистка → снимок → экспорт."""
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)

    recipes = config.get("sources", [{"kind": "hn_front"}])
    labels = [r.get("kind", r) if isinstance(r, dict) else r for r in recipes]

    if ledger:
        ledger.event("phosphor", "radar", "collect_start", {"sources": labels})
    if treasury:
        treasury.spend("radar", 100 * len(recipes) + 50, note="fetch run")

    items = collect(recipes)
    items = clean(items)
    snapshot = build_snapshot(items, recipes)

    exports = export(snapshot, workdir / "exports")

    if treasury:
        treasury.spend("refiner", 200, note="dedup+score+tag")
        treasury.spend("scribe", 150, note="dataset card")
    if ledger:
        ledger.event("phosphor", "refiner", "snapshot_ready", {
            "items": snapshot["totals"]["items"],
            "by_source": snapshot["totals"]["by_source"],
        })

    snapshot["exports"] = exports
    return snapshot
