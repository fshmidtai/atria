# Улей на Oracle Always Free

Цель: постоянный резидент роя — циклический агент с локальной памятью.
Машина: **VM.Standard.A1.Flex, 4 OCPU ARM + 24 ГБ RAM, Ubuntu 24.04** (Always Free).

## Один раз (при создании VM в Oracle Console)

- shape: `VM.Standard.A1.Flex` (4 OCPU, 24 ГБ)
- image: `Canonical Ubuntu 24.04`
- SSH keys: сгенерировать и **скачать приватный ключ**
- после создания: в Instance Details → **Public IP** (скопировать в `.env` → `ORACLE_IP`)

## Подъём улья

```bash
# 1. заход
ssh -i <твой-приватный-ключ>.key ubuntu@<PUBLIC_IP>

# 2. docker (официальный скрипт —Oracle-образ его допускает)
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker ubuntu
# (после этого нужно перезайти по ssh, чтобы группа применилась)

# 3. код роя
git clone <your-repo-url> atria && cd atria
cp .env.example .env
nano .env        # заполнить HF_TOKEN, GITHUB_TOKEN и т.д.

# 4. запуск
docker compose -f infra/oracle/docker-compose.yml up -d --build

# 5. проверить
docker compose -f infra/oracle/docker-compose.yml logs -f hive
```

## Что внутри

- `hive` — бесконечный цикл `genesis.py` каждые 6 часов (см. `docker-compose.yml`),
  состояние — в volume `atria-data` (переживает рестарт контейнера и апдейт кода).
- `qdrant` — векторное хранилище, пока на 127.0.0.1 (подготовка под v0.2).

## Почему именно так

- **Никаких открытых портов наружу** — только исходящий трафик. Минимум атакной поверхности.
- **Idle-reclaim**: Oracle может reclaim'ить простаивающие Always Free-инстансы.
  Наш циклический hive сам по себе не даёт машине простаивать; для надёжности
  (v0.2) добавится бесплатный uptime-пинг (UptimeRobot) на 80-й порт healthcheck'а.

## Обновление кода

```bash
cd atria
git pull
docker compose -f infra/oracle/docker-compose.yml up -d --build
```
