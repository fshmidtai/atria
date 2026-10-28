# 🚀 Деплой Атрии — пошаговая операционная карта

Когда от KDD получены доступы (см. `.env.example`), разворачивание сводится к
выполнению этой инструкции. Каждый этап независим и проверяем.

**Принцип очерёдности:** GitHub → Cloudflare → HuggingFace → Oracle.
Сначала пульс и видимые руки ( Colony-сайты), потом резидентный улей.

---

## 0. Предусловия (один раз, руками KDD)

| Дано | Где взять |
|---|---|
| `GITHUB_TOKEN` | GitHub → Settings → Developer settings → Personal access tokens → Fine-grained (repo: read/write, workflows: write) |
| `HF_TOKEN` | HF → Settings → Access tokens → role: **Write** |
| `CLOUDFLARE_API_TOKEN` | Cloudflare → My Profile → API Tokens → «Edit Cloudflare Workers»-шаблон + Pages |
| `CLOUDFLARE_ACCOUNT_ID` | Cloudflare → любой сайт/воркер → правый сайдбар |
| `ORACLE_IP`, `ORACLE_SSH_KEY` | Oracle → Instance details (IP) + приватный ключ, скачанный при создании |
| `SUPABASE_URL`, `SUPABASE_KEY` | Supabase → Project Settings → API (v0.3) |

---

## 1. GitHub — пульс роя (15 минут)

```bash
cd atria
git remote add origin git@github.com:<user>/atria.git   # или https
git push -u origin master
```

**Проверка:** вкладка Actions → workflow **Atria — hive tick** → Run workflow.
Если зелёный — рой уже живёт: каждые 6 часов (и по push) гоняет цикл и
коммитит состояние (dist/metrics/exports) обратно в репо.

**Что улучшить:** `GITHUB_TOKEN` добавить в Secrets репо (`Settings → Secrets`),
чтобы rate-limit для GitHub-источника снялся.

---

## 2. Cloudflare Pages — лица колоний (10 минут на колонию)

1. dash.cloudflare.com → **Workers & Pages** → Create → Pages → **Connect to Git**
2. Выбрать репо `atria`, ветка `master`
3. Build settings:
   - Framework preset: **None**
   - Build command: *(пусто)* — сайт уже собран роем
   - **Build output directory:** `colonies/phosphor/dist`
4. Deploy. Повторить для **каждой** колонии (сейчас их 4):
   `colonies/phosphor/dist`, `colonies/vesper/dist`,
   `colonies/sentinel/dist`, `colonies/meridian/dist` — 4 проекта CF Pages.

**Результат:** `https://<project>.pages.dev` — каждая колония в интернете.

**Проверка (поэтому и живём):** в репо коммитятся только сайты, прошедшие
QA — шаг `QA gate` в workflow краснеет, если у колонии `err>0`
(см. `archaea/qa.py`, `archaea/qa_gate.py`). Локально то же самое:
`python archaea/qa_gate.py`.

**Custom domain** (опц.): Pages → Custom domains → добавить. Бесплатный SSL
выпускается автоматически. Домен покупается у любого регистратора (~$10/год)
— это первый расход из казначейства (Конституция §2).

**AMP/SEO-проверка:** sitemap доступен по `<site>/sitemap.xml`, JSON-LD и
Open Graph — в коде страниц (проверено QA и soak).

---

## 3. HuggingFace — датасеты + пульт (20 минут)

### 3.1. Хранилище состояния (приватное or public, бесплатно)

1. HF → **New dataset** → name: `<user>/atria-hive-state`, type: Public
2. Локально: `pip install huggingface_hub`, `huggingface-cli login` (HF_TOKEN)

**Подключение к рою:** в GitHub-репо Secrets добавить:
- `HF_TOKEN` — токен на запись
- `HF_STATE_REPO` = `<user>/atria-hive-state`

После первого тика genesis сам выложит `metrics.json` + exports колоний.

### 3.2. Space-пульт (Gradio)

1. HF → **New Space** → name: `atria-console`, SDK: **Gradio**, public
2. Клонировать и наполнить (см. `infra/space/README.md`):

```bash
git clone https://huggingface.co/spaces/<user>/atria-console
cp atria/infra/space/app.py atria-console/
cp atria/infra/space/requirements.txt atria-console/
cd atria-console && cp ../atria/storage/metrics.json .
git add -A && git commit -m "console" && git push
```

3. В Space Settings → Variables: `HF_STATE_REPO` = `<user>/atria-hive-state`,
   `HF_TOKEN` = read-токен.

**Проверка:** открыть Space — дашборд покажет агентов, бюджет, карточки
колоний (QA-статусы, дата-продукты, страницы), топ снимка и историю тиков.

### 3.3. Датасеты и продукты на продажу (Data Arbitrage)

После каждого тика в `atria-hive-state` лежит по каждой колонии:
`dataset.json`, `DATA_CARD.md` и папка `products/`
(`digest_top.csv`, `trend_index.csv`, `cve_digest.csv` — у Sentinel,
`PRODUCTS.md` — манифест). Датасет можно верифицировать и включить
«Pro»-продажи, либо раздавать как лид-магнит.

---

## 4. Oracle — резидентный улей (30 минут)

```bash
ssh -i <key> ubuntu@<ORACLE_IP>
curl -fsSL https://get.docker.com | sh && sudo usermod -aG docker ubuntu
# перезайти
git clone https://github.com/<user>/atria.git && cd atria
cp .env.example .env && nano .env       # заполнить HF_*, GITHUB_TOKEN
docker compose -f infra/oracle/docker-compose.yml up -d --build
docker compose -f infra/oracle/docker-compose.yml logs -f hive
```

**Проверка:** в логе `[hive] tick start` → отчёт улья → `[hive] sleeping 21600s`.

**Что даёт улей поверх GitHub-пульса:** постоянное состояние (volume),
место под self-hosted LLM (24 ГБ RAM — Qwen 32B поднимается), векторная
память (Qdrant) и устойчивость к перебоям GitHub.

**Защита от idle-reclaim:** циклы идут постоянно, healthcheck (см.
`docker-compose.yml`) держит статус контейнера — `docker ps` покажет
`unhealthy`, если улей перестал плодить `metrics.json`. При необходимости —
бесплатный UptimeRobot-пинг на любой HTTP-эндпоинт по требованию.

---

## 5. Что нельзя делать (Конституция §4)

- не публиковать `.env`, не коммитить `storage/atria.db` (уже в .gitignore)
- публично светить токены (передача — только приватным каналом)
- включать платные ресурсы без решения казначейства

---

## 6. Откат / миграция

Любой компонент умирает — рой выживает:
- упал GitHub Actions → улей на Oracle продолжает тикать
- упал Oracle → `git push` + любой CI, `docker compose` на новом узле
- упала Cloudflare → Vercel/Netlify: те же `colonies/*/dist` → deploy
- упало всё → `git clone` + `python archaea/genesis.py` = рой жив
