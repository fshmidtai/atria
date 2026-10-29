"""Раунд 19: финальная сборка бота-продукта — имя, описание, команды.
Токен только из окружения, не печатается."""
import json
import os
import urllib.request

TOKEN = os.environ["TG_BOT_TOKEN"]


def call(method, payload=None):
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{TOKEN}/{method}",
        data=json.dumps(payload or {}).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


n = call("setMyName", {"name": "Атрия · дайджесты роя"})
print("setMyName:", n.get("ok"))
d = call("setMyDescription", {
    "description": (
        "🌅 Рой Атрия — автономные дайджесты по 10 вертикалям (AI, кибербез, "
        "финтех, гранты, тендеры, реклама, регуляторика):\n"
        "• свежие потоки каждые 6 часов — без цензуры и ручной подборки;\n"
        "• /start — подписка, /stop — отписка.\n\n"
        "💛 Поддержать улей: TON/USDT-адреса на пульте роя:\n"
        "huggingface.co/spaces/fshmidtai/atria-console")})
print("setMyDescription:", d.get("ok"))
s = call("setMyShortDescription", {
    "short_description": "Автономные дайджесты роя Атрия — 10 вертикалей, тик 6ч"})
print("setMyShortDescription:", s.get("ok"))
