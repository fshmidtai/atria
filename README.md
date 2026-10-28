# 🐝 Atria — суверенная мультиагентная сеть

Автономная система «цифровых колоний», которая собирает бесплатные публичные данные,
производит датасеты и programmatic-SEO сайты и monetизирует их — без ручного труда и с $0 затрат на инфраструктуру.

> **Статус:** v0.1 «Genesis» — ядро + первая колония (Phosphor), stdlib-only Python.
> Запускается одной командой, готова к разворачиванию на бесплатном стеке.

## Что здесь

```
atria/
├── docs/CONSTITUTION.md         # «геном» роя — правила бюджета, апоптоза, красные линии
├── core/                        # ядро: память, казначейство, реестр агентов, оркестратор, LLM-шлюз
│   ├── ledger.py                #   append-only журнал событий (SQLite → потом Supabase)
│   ├── treasury.py              #   бюджетные клетки (агент = лимит расходов)
│   ├── registry.py              #   реестр агентов (спавн / ретайр)
│   ├── orchestrator.py          #   cron-движок: tick() — один проход по задачам
│   └── llmrouter.py             #   бесплатные LLM (local → groq → openrouter), опционально
├── colonies/
└── phosphor/                    # колония 1: «медиа-датапрокат»
    ├── sources.py               #   бесплатные источники (Hacker News, arXiv, GitHub)
    ├── pipeline.py              #   сбор → дедуп → скоринг «базза» → тегирование тем
    ├── sitegen.py               #   генератор статического SEO-сайта (JSON-LD, sitemap)
    └── config.json              #   конфиг колонии (ниша, домен, источники)
├── archaea/genesis.py           # «кнопка жизни»: разворачивает ядро + прогоняет цикл
├── infra/
│   ├── github-actions/          # cron-пульс роя (2000 бесплатных минут/мес)
│   ├── oracle/docker-compose    # «улей» на Oracle Always Free ARM 4×24 ГБ
│   └── space/                   # пульт-дашборд (HuggingFace Space, Gradio)
└── storage/                     # SQLite + снимки (state роя, не коммитится)
```

##Быстрый старт (локально, за 1 минуту)

```powershell
python archaea/genesis.py
```

или

```bash
./run.sh        # Linux/macOS/Oracle
.\run.ps1       # Windows
```

Что произойдёт: создастся SQLite-ядро, заспавнятся 4 агента колонии Phosphor,
прогонится цикл (сбор → очистка → датасет → сайт), в `colonies/phosphor/dist`
появится готовый к деплою сайт, а в консоль — отчёт роя.

## Где это живёт (бесплатный стек)

| Компонент | Платформа | Цена |
|---|---|---|
| Код + cron-оркестратор | GitHub (Actions: 2000 мин/мес на private) | $0 |
| Сайты колоний | Cloudflare Pages (безлимит статика) | $0 |
| Датасеты + пульт | HuggingFace (Datasets + Spaces) | $0 |
| Общая память | Supabase (Postgres 500 МБ) — v0.2 | $0 |
| Улей: агенты + self-hosted LLM | Oracle Always Free ARM 4×24 ГБ | $0 |

### Завести в облаке (по мере готовности аккаунтов)

1. **GitHub.** Запушь репозиторий — workflow `.github/workflows/hive-tick.yml`
   подхватится сам: пульс каждые 6 часов + ручной запуск во вкладке Actions.
2. **Cloudflare Pages.** New project → Connect to Git → выбор репо →
   Framework preset: `None` → Build output directory: `colonies/phosphor/dist`.
   Сайт колонии уезжает в интернет за один клик.
3. **HuggingFace Space.** См. `infra/space/README.md` — пульт улья на Gradio.
4. **Oracle.** См. `infra/oracle/README.md` — `docker compose up -d --build`,
   и улей становится резидентным.

Принцип переносимости: **всё состояние — в git + SQLite, ни одной проприетарной привязки**.
Смерть любого узла = `git clone` + одна команда.

## Философия

См. [docs/CONSTITUTION.md](docs/CONSTITUTION.md) — геном роя:
бюджетные клетки, апоптоз нерентабельных агентов, правило распределения дохода 70/20/10,
красные линии (никакого спама, никакого PII, никакого нарушения ToS источников).

Человек («биологический слой») делает только то, что алгоритм не может:
разовая регистрация облаков, KYC, стратегические решения. Остальное — рой.
