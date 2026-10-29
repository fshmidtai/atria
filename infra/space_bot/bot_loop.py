"""Atria Bot Loop — всегда-онлайн рантайм Telegram-бота (HF Docker Space).

Зачем: Stars-оплата и /start требуют ответа за секунды, а тик роя ходит раз в
6 часов. Этот контейнер держит long-poll к Telegram, обрабатывает команды и
платежи мгновенно, а состояние подписок коммитит в HF-датасет (общий файл с
GitHub-тиком, который только читает его перед рассылкой).

Секреты Space: TG_BOT_TOKEN, HF_TOKEN. Переменные: HF_SUBS_REPO, SUBS_FILE.
"""
from __future__ import annotations

import json
import os
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

API = "https://api.telegram.org/bot"
HF_SUBS_REPO = os.environ.get("HF_SUBS_REPO", "fshmidtai/atria-hive-state")
SUBS_FILE = os.environ.get("SUBS_FILE", "tg_subs.json")
SUBS_URL = (f"https://huggingface.co/datasets/{HF_SUBS_REPO}/"
            f"resolve/main/{SUBS_FILE}")

PRO_PRICE_STARS = 199
PRO_DAYS = 31

WELCOME_RU = (
    "👋 <b>Атрия</b> — автономный рой: свежие дайджесты по 10 вертикалям "
    "(AI, кибербез, финтех, гранты, тендеры 44-ФЗ, реклама, регуляторика) "
    "каждые 6 часов.\n\n"
    "Команды: /pro — полный дайджест (top-20) на месяц, /stop — отписка.\n"
    "💛 Поддержать улей криптой: TON/USDT на пульте роя:\n"
    "huggingface.co/spaces/fshmidtai/atria-console"
)


def tg(method: str, payload: dict) -> dict:
    req = urllib.request.Request(
        f"{API}{os.environ['TG_BOT_TOKEN']}/{method}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:  # сеть упала — цикл перезапустится
        print("tg", method, "ERR", type(e).__name__, flush=True)
        return {"ok": False, "_err": str(e)[:80]}


def hf_call(method: str, path: str, body=None, ctype="application/json"):
    req = urllib.request.Request(
        f"https://huggingface.co/api/{path}",
        data=(json.dumps(body).encode() if body is not None else None),
        headers={"Authorization": "Bearer " + os.environ.get("HF_TOKEN", ""),
                 "Content-Type": ctype}, method=method)
    with urllib.request.urlopen(req, timeout=60) as r:
        raw = r.read()
        return json.loads(raw) if raw.strip() else {}


def load_state() -> dict:
    try:
        with urllib.request.urlopen(
                urllib.request.Request(SUBS_URL, headers={"User-Agent": "atria-bot"}),
                timeout=60) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:
        return {"chats": {}, "offset": 0}


def save_state(state: dict):
    """Коммит файла состояния в HF-датасет (lfs не нужен — крошечный JSON)."""
    upload = {
        "key": SUBS_FILE,
        "content": json.dumps(state, ensure_ascii=False),
        "commit": {"title": "bot state update"},
    }
    hf_call("POST", f"spaces/{HF_SUBS_REPO}/upload-progress" if False else
            f"datasets/{HF_SUBS_REPO}/commit/main", body=upload)
    print("saved", len(state["chats"]), "chats", flush=True)


_state = {"data": load_state(), "lock": threading.Lock()}


def handle_update(u: dict):
    state = _state["data"]
    uid = u.get("update_id", state.get("offset", 0))
    state["offset"] = uid + 1
    msg = u.get("message") or {}
    chat = msg.get("chat") or {}
    cid = chat.get("id")
    text = (msg.get("text") or "").strip()

    pay = msg.get("successful_payment")
    if pay and cid is not None:
        try:
            days = json.loads(pay.get("payload", "{}")).get("days", PRO_DAYS)
        except Exception:
            days = PRO_DAYS
        chats = state.setdefault("chats", {})
        chats[str(cid)] = {**(chats.get(str(cid)) or {}),
                           "until": time.time() + days * 86400}
        tg("sendMessage", {
            "chat_id": cid, "parse_mode": "HTML",
            "text": f"⭐ <b>Pro активирован</b> на {days} дн. — полный дайджест "
                    "(top-20) уже в следующем рассылке. Спасибо!"})
        return

    pcq = u.get("pre_checkout_query")
    if pcq:
        tg("answerPreCheckoutQuery", {"pre_checkout_query_id": pcq["id"],
                                      "ok": True})
        return

    if cid is None:
        return
    if text.startswith("/start"):
        chats = state.setdefault("chats", {})
        chats[str(cid)] = {**(chats.get(str(cid)) or {}), "chat_id": cid}
        tg("sendMessage", {"chat_id": cid, "parse_mode": "HTML",
                           "text": WELCOME_RU})
    elif text.startswith("/pro"):
        inv = tg("createInvoiceLink", {
            "title": "Атрия Pro — месяц",
            "description": "Полный дайджест (top-20 вместо 5) по всем 10 "
                           "вертикалям роя на 31 день.",
            "payload": json.dumps({"product": "atria_pro_month",
                                    "days": PRO_DAYS}),
            "currency": "XTR",
            "prices": [{"label": "Pro месяц", "amount": PRO_PRICE_STARS}]})
        link = (inv or {}).get("result") if inv else None
        tg("sendMessage", {
            "chat_id": cid, "parse_mode": "HTML",
            "text": f"⭐ <b>Атрия Pro</b> — полный дайджест по всем вертикалям, "
                    f"{PRO_PRICE_STARS} Stars на {PRO_DAYS} дн. Оплата внутри "
                    "Telegram, поддержка роя — через Fragment.",
            "reply_markup": ({"inline_keyboard": [[{
                "text": f"Оплатить {PRO_PRICE_STARS} Stars", "url": link}]]}
                if link else None)})
    elif text.startswith("/stop"):
        state.setdefault("chats", {}).pop(str(cid), None)
        tg("sendMessage", {"chat_id": cid, "text": "Отписались. /start — назад."})


def loop():
    state = _state["data"]
    print("bot loop up,", len(state.get("chats", {})), "chats", flush=True)
    while True:
        try:
            d = tg("getUpdates", {"timeout": 50, "offset": state.get("offset", 0)})
            if not d.get("ok"):
                time.sleep(5)
                continue
            ups = d.get("result") or []
            if not ups:
                continue
            for u in ups:
                handle_update(u)
            with _state["lock"]:
                save_state(state)
        except Exception as e:
            print("loop ERR", type(e).__name__, str(e)[:100], flush=True)
            time.sleep(5)


class Health(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"atria bot alive")

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    threading.Thread(target=loop, daemon=True).start()
    port = int(os.environ.get("PORT", 7860))
    HTTPServer(("0.0.0.0", port), Health).serve_forever()
