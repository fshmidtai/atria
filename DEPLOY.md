# Atria — живая инфраструктура

Развернуто на 100% бесплатном стеке. Всё крутится само (cron каждые 6 часов),
руки нужны только при стратегических решениях.

## Что живёт

| Слой | Где | URL |
|---|---|---|
| Репозиторий-ульй | GitHub | https://github.com/fshmidtai/atria |
| Пульс (цикл роя) | GitHub Actions `Atria hive tick` | cron `17 */6 * * *` + workflow_dispatch |
| Состояние (metrics/history/датасеты) | HuggingFace dataset | https://huggingface.co/datasets/fshmidtai/atria-hive-state |
| Пульт-дашборд | HF Static Space | https://fshmidtai-atria-console.static.hf.space |
| Колония: AI-инструменты | Cloudflare Pages | https://vesper-ai-radar.pages.dev |
| Колония: кибербез | Cloudflare Pages | https://sentinel-post.pages.dev |
| Колония: финансы (EN) | Cloudflare Pages | https://bourse-radar.pages.dev |
| Колония: AI-новости (RU) | Cloudflare Pages | https://signal-frontier.pages.dev |
| Колония: ML/данные (EN) | Cloudflare Pages | https://meridian-radar.pages.dev |

## Цикл одного тика

```
schedule/workflow_dispatch
  → selftest (78 тестов ядра, без сети)
  → soak (12 тиков офлайн)
  → genesis (сбор → очистка → датасеты → сайты; публикация в HF)
  → commit hive state (dist + storage → master)
  → QA gate (публикация вслепую запрещена)
  → deploy_pages.py (бейдж: CF Pages, все колонии)
```

## Cloudflare Pages: direct-upload деплой

`infra/cloudflare/deploy_pages.py` — реализация протокола wrangler (никаких
обёрток): per-project `upload-token` (JWT) → `/pages/assets/check-missing` →
`/pages/assets/upload` (base64) → `/pages/assets/upsert-hashes` →
`/accounts/{id}/pages/projects/{name}/deployments` с multipart-манифестом.

Ключ ассета — **blake3(base64(контент) + расширение_без_точки)[:32 hex]**
(см. `packages/deploy-helpers/src/deploy/helpers/hash.ts` в wrangler).
Не sha256 — на это уткнулась первая попытка (edge отдавал 500 при «success»
от API).

Переменные: `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`
(секреты `CF_API_TOKEN` / `CF_ACCOUNT_ID` в GitHub Actions).

## HF Space: статический пульт

Gradio/Docker Spaces на free-плане теперь требуют PRO (HTTP 402), поэтому
пульт — **Static Space** (`sdk: static`): `index.html` тянет
`metrics.json` из публичного датасета состояния (CORS открыт).
Поднимается/обновляется: `python infra/space/push_space.py` (нужен `HF_TOKEN`).

## Supabase

URL + publishable key лежат в `.env` (ждут стадии монетизации:
realtime-таблицы для API-ключей клиентов).

## Oracle Always Free

Регистрация отклонена (карты не принимаются) — решение зафиксировано:
пульс роя полностью на GitHub Actions (бесплатно, unlimited на public-репо).
Если аккаунт Oracle появится — `infra/oracle/` готов (Docker, selftest).

## Stage 4: первый $1 — статус

✅ **Рельс подключён**: Ko-fi `https://ko-fi.com/miningchia` вшит во все 5 колоний
(`monetization.support_url` в config.json). CTA-блок «Поддержать улей» /
«Support the hive» уже живёт на всех сайтах (RU/EN по локали колонии),
следующий тик и любой будущий апдейты уходят на автомате.

⬜ **Опциональные рельсы** (когда будет желание):
- **Gumroad** — продажа полного датасета колонии (CSV-экспорты уже пекутся
  каждый тик). Даёт `products_url` — кнопка «Купить датасет».
- CF API-токен с **Workers Scripts: Edit** — поднимет `atria-links` Worker
  (роутер `/go/:slug` + `/status` API): CTA-ссылки перенацеливаются без
  перевыпуска сайтов + клики-аналитика.

Казна (`core/treasury.py`) уже имеет `revenue(amount_u, source)` —
приход пойдёт в µ$-книгу с ROI по агентам.
