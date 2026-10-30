# Продукты колонии `tenderslice`

Снимок от 2026-10-30T04:09:12+00:00.
Продукты генерируются автоматически каждый тик улья (6 часов) из
публичных источников без ключей. Лицензия: MIT, упоминание источника приветствуется.

| продукт | что это | строк |
|---|---|---|
| `digest_top.csv` | топ материала дня, плоский BI-формат | 20 |
| `trend_index.csv` | тема → объём сегодня, вчера, дельта (Trend Index) | 1 |

## Схемы

- `digest_top.csv`: uid, source, title, url, buzz, date, topics
- `trend_index.csv`: colony, date, topic, count, count_prev, delta
- `cve_digest.csv`: cve_id severity package title url date (только если в снимке есть CVE)