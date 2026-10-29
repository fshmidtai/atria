"""Первый выгон бота: проверка токена + описание/команды как у продукта.
Токен только из окружения, нигде не печатается."""
import json
import os
import urllib.error
import urllib.request

TOKEN = os.environ["TG_BOT_TOKEN"]


def call(method, payload=None):
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{TOKEN}/{method}",
        data=json.dumps(payload or {}).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:200]
        # токен не печатаем — только код и тело ответа сервера
        raise SystemExit(f"HTTP {e.code} от api.telegram.org: {body}")


me = call("getMe")
print("getMe ok:", me.get("ok"), "| username:", me.get("result", {}).get("username"))

d = call("setMyDescription", {
    "description": ("Автономный рой Атрия: свежие дайджесты публичных потоков "
                    "каждые 6 часов — AI, кибербез, финансы, данные. "
                    "Поддержать улей: TON/USDT — адреса на сайтах роя.")})
print("setMyDescription:", d.get("ok"))
s = call("setMyShortDescription", {
    "short_description": "Дайджесты роя Атрия — автономно, каждые 6 часов"})
print("setMyShortDescription:", s.get("ok"))
c = call("setMyCommands", {"commands": [
    {"command": "start", "description": "подписаться на дайджест"},
    {"command": "stop", "description": "отписаться"},
]})
print("setMyCommands:", c.get("ok"))
