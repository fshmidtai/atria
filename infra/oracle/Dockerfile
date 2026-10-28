# Dockerfile улья. Базовый образ slim, никаких внешних системных зависимостей.
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Один цикл при старте; цикличность обеспечивает docker-compose (команда sh -c while).
CMD ["python", "archaea/genesis.py"]
