---
language:
  - ru
  - en
license: apache-2.0
task_categories:
  - text-mining
  - summarization
tags:
  - autonomous-agents
  - news-radar
  - rss
  - trends
  - russia
size_category: 1K<n<10K
---

# Atria Hive State

Автономное состояние роя **Атрия** — мультиагентной системы, которая каждые
6 часов собирает, чистит и публикует дайджесты публичных потоков
(AI/ML, кибербезопасность, рынки/фintech, вступления в IT).

## Что внутри

- `metrics.json` — снимок состояния роя: по каждой колонии — число записей,
  источники (`by_source`), темы (`by_topic`), top-20 элементов, QA-аудит
  сгенерированных сайтов, бюджет и список агентов.
- `history.jsonl` — append-only история тиков (колония, items, by_source).
- `exports/<colony>/` — собранные датасеты по колониям (CSV/JSON), продукт
  data-арбитража.

## Обновление

Автоматически, раз в 6 часов, без ручных шагей (GitHub Actions cron →
HuggingFace Hub API). Zero-Human-Touch: человек делает только стратегические
решения.

## Продукт

- 🤖 Telegram-бот дайджестов: **@dimon_claw_bot**
- 🛰 Сайты-радары колоний: bourse-radar.pages.dev, signal-frontier.pages.dev,
  vesper-ai-radar.pages.dev, sentinel-post.pages.dev, meridian-radar.pages.dev
- 🐝 Пульт: huggingface.co/spaces/fshmidtai/atria-console
- 💛 Поддержка: TON/USDT-адреса в профиле бота и на пульте.

## Лицензия

Данные собраны из публичных источников (RSS/Atom) со ссылкой на оригинал.
 Apache-2.0 для производных материалов роя.
