---
language: en
license: mit
pretty_name: Phosphor Tech Buzz Radar
task_categories: [text-classification, summarization]
---

# Phosphor — Tech Buzz Radar (2026-10-30T01:47:48+00:00)

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
robots.txt и ToS площадок. Персональные данные (e-mail, телефоны, номера карт)
автоматически вычищаются перед упаковкой. Датасет обновляется автоматически каждые 6 часов.
