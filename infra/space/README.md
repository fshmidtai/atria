# Пульт на HuggingFace Space

Space — это бесплатный контейнер (2 vCPU / 16 ГБ), который держит Gradio-приложение
и просыпается по любому обращению. Для нас это «дашборд роя».

## Подъём (один раз)

1. **Создай Space:** huggingface.co → Spaces → New space
   - name: `atria-console`, SDK: **Gradio**, license: MIT, Space: **Public** (бесплатно)
2. **Клонируй и наполни:**

   ```bash
   git clone https://huggingface.co/spaces/<username>/atria-console
   cp atria/infra/space/app.py atria-console/app.py
   cp atria/infra/space/requirements.txt atria-console/requirements.txt
   cd atria-console
   cp ../atria/storage/metrics.json .        # первый снимок руками
   git add -A && git commit -m "hive console" && git push
   ```

3. **Создай датасет-хранилище состояния** (туда улей сам будет кладать metrics.json):
   huggingface.co → New dataset → name: `atria-hive-state`, type: **Public**.
   В Settings твоего Space добавь переменные окружения:
   - `HF_STATE_REPO` = `<username>/atria-hive-state`
   - `HF_TOKEN` = access token (role: **Read**) — достаточно read; улей пишет под своим токеном.

## Как состояние попадает в Space

```
github actions / oracle hive
        │  (после каждого цикла)
        ▼
   huggingface_hub.upload_file ──► dataset <username>/atria-hive-state
                                        │
  _space (этот файл) ◄── hf_hub_download┘
```

Пока ключи не заведены — Space просто читает metrics.json, положенный рядом
(см. пункт 2), и не падает.
