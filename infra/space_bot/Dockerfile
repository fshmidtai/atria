# Рантайм бота: всегда онлайн (getUpdates long-poll), оплата Stars в реальном
# времени. Подписки хранятся в HF-датасете (один файл на всех: Space пишет,
# тик-цикл в GitHub читает — одного источника правды нет, конфликты исключены
# тем, что тик только читает).
FROM python:3.12-slim
WORKDIR /app
COPY bot_loop.py .
ENV PYTHONUNBUFFERED=1
CMD ["python", "bot_loop.py"]
