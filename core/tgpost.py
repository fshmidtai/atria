"""TgPost — доставка снимка колонии в Telegram (третий renderer после sitegen).

Философия та же, что у всего роя: никакого state по умолчанию. Нет
TG_BOT_TOKEN / TG_CHANNEL — функция молча возвращается (конституция §1.4:
колония не зависит от внешних сервисов). Появился бот — следующий тик
начинает постить дайджест в канал автоматически.

Одноразовые шаги человека (Zero-Human-Touch):
  1. @BotFather → /newbot → TOKEN
  2. канал → бота админом → @username канала
  3. secrets: TG_BOT_TOKEN (+ TG_CHANNEL, либо site.tg.channel в config)

Деньги (потом): Telegram Stars-инвойсы ( Bot API createInvoiceLink /
sendInvoice, валюта XTR), выплаты — Fragment в TON (подтверждено анализ
docs/STAGE4_NICHES.md). Платный ящик отключён до выбора вертикали.
"""
from __future__ import annotations

import html
import json
import os
import sqlite3
import time
import urllib.error
import urllib.request

API = "https://api.telegram.org/bot"
TIMEOUT = 20


def format_digest(snapshot: dict, top_n: int = 5, lang: str = "ru") -> str:
    """Чистая функция: снимок → готовое HTML-сообщение дайджеста.
    Тестируется офлайн; именно её покрывает selftest."""
    items = snapshot.get("items", [])[:top_n]
    totals = snapshot.get("totals", {})
    n_items = totals.get("items", len(items))
    head = ("📡 Свежий снимок" if lang == "ru" else "Fresh snapshot")
    lines = [f"<b>{head} · {n_items} </b>" + ("записей" if lang == "ru" else "items")]
    for i, it in enumerate(items, 1):
        title = html.escape(str(it.get("title", ""))[:90])
        src = html.escape(str(it.get("source", "")))
        link = html.escape(str(it.get("url", "")))
        buzz = it.get("buzz", 0)
        lines.append(f'{i}. <a href="{link}">{title}</a> '
                     f'<i>({src}, buzz {buzz})</i>')
    when = snapshot.get("generated_at", "")
    tail = "автономно роем Атрия" if lang == "ru" else "autonomously by the Atria swarm"
    lines.append(f"\n<i>{tail}{(f' · {str(when)[:16]}') if when else ''}</i>")
    return "\n".join(lines)


def send_message(token: str, channel: str, text: str) -> bool:
    """Один POST в Bot API. False = сети/токена нет, рой едет дальше."""
    try:
        req = urllib.request.Request(
            f"{API}{token}/sendMessage",
            data=json.dumps({
                "chat_id": channel, "text": text,
                "parse_mode": "HTML", "disable_web_page_preview": True,
            }).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST")
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return r.status == 200
    except (urllib.error.URLError, OSError, ValueError):
        return False


def maybe_post(snapshot: dict, config: dict, top_n: int = 5) -> bool:
    """Точка входа из genesis-тика: постит, только если рельсы есть.
    Канал: config['site']['tg']['channel'] или env TG_CHANNEL."""
    token = os.environ.get("TG_BOT_TOKEN", "")
    site = (config or {}).get("site", {})
    channel = (site.get("tg") or {}).get("channel", "") or os.environ.get("TG_CHANNEL", "")
    if not token or not channel:
        return False
    text = format_digest(snapshot, top_n=top_n, lang=site.get("lang", "ru"))
    return send_message(token, channel, text)


# ---------------------------------------------------------------- подписчики
SUBS_SCHEMA = """
CREATE TABLE IF NOT EXISTS subs (
    chat_id  INTEGER PRIMARY KEY,
    lang    TEXT    NOT NULL DEFAULT 'ru',
    created REAL    NOT NULL,
    until   REAL    NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS tg_state (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def _open_subs(db_path):
    conn = sqlite3.connect(str(db_path))
    conn.executescript(SUBS_SCHEMA)
    conn.commit()
    return conn


def _api(token: str, method: str, payload: dict) -> dict | None:
    """Один вызов Bot API. None = сеть упала, рой едет дальше."""
    try:
        req = urllib.request.Request(
            f"{API}{token}/{method}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return json.loads(r.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError):
        return None


WELCOME_RU = (
    "👋 Ты подписан на дайджест роя <b>Атрия</b> — автономный сбор публичных "
    "потоков каждые 6 часов. Здесь будет свежий срез.\n\n"
    "Поддержать улей криптой — адреса в закрепе канала и на сайтах роя."
)
WELCOME_EN = (
    "👋 You are subscribed to the <b>Atria</b> swarm digest — an autonomous "
    "harvest of public streams every 6 hours."
)

# Telegram Stars (XTR) — встроенный платёжный провайдер, без внешних ключей.
# Выплаты — Fragment в TON (проверенный рельс, docs/STAGE4_NICHES.md).
PRO_PRICE_STARS = 199          # ≈ $2, месяц полного дайджеста
PRO_DAYS = 31
PRO_PRODUCT = "atria_pro_month"


def invoice_payload() -> dict:
    """Чистая функция — тело инвойса Stars (тестируется офлайн).
    XTR не требует provider_token: Telegram сам его выставляет."""
    return {
        "title": "Атрия Pro — месяц",
        "description": "Полный дайджест (top-20 вместо 5) по всем 10 вертикалям "
                       "роя на 31 день. Оплата Stars, поддержка Fragment.",
        "payload": json.dumps({"product": PRO_PRODUCT, "days": PRO_DAYS}),
        "currency": "XTR",
        "prices": [{"label": "Pro месяц", "amount": PRO_PRICE_STARS}],
    }


def is_pro(conn, chat_id: int, now: float | None = None) -> bool:
    row = conn.execute(
        "SELECT until FROM subs WHERE chat_id = ?", (chat_id,)).fetchone()
    if not row:
        return False
    return float(row[0] or 0) > (now if now is not None else time.time())



def handle_updates(token: str, db_path, lang: str = "ru") -> int:
    """Опрос long-poll одним заходом. /start = подписка, /stop = отписка.
    offset подтверждает апдейты (иначе Telegram будет присылать их снова 24ч).
    Возвращает число обработанных апдейтов (0 = нет токена/сети/апдейтов)."""
    if not token:
        return 0
    conn = _open_subs(db_path)
    row = conn.execute(
        "SELECT value FROM tg_state WHERE key='offset'").fetchone()
    offset = int(row[0]) if row else 0
    data = _api(token, "getUpdates", {"timeout": 0, "offset": offset})
    if not data or not data.get("ok"):
        conn.close()
        return 0
    updates = data.get("result", [])
    handled = 0
    for u in updates:
        uid = u.get("update_id", offset)
        conn.execute(
            "INSERT OR REPLACE INTO tg_state (key, value) VALUES ('offset', ?)",
            (str(uid + 1),))
        msg = (u.get("message") or {})
        chat = msg.get("chat") or {}
        cid = chat.get("id")
        text = (msg.get("text") or "").strip()
        # успешная оплата Stars (приходит как message.successful_payment)
        pay = msg.get("successful_payment")
        if pay and cid is not None:
            try:
                days = json.loads(pay.get("payload", "{}")).get("days", PRO_DAYS)
            except Exception:
                days = PRO_DAYS
            until = time.time() + days * 86400
            conn.execute(
                "UPDATE subs SET until = ? WHERE chat_id = ?", (until, cid))
            _api(token, "sendMessage", {
                "chat_id": cid,
                "text": f"⭐ Pro активирован на {days} дн. Спасибо за поддержку "
                        f"роя! Теперь дайджесты придут в полном виде (top-20)."})
            handled += 1
            continue
        if cid is None:
            handled += 1
            continue
        if text.startswith("/start"):
            conn.execute(
                "INSERT OR IGNORE INTO subs (chat_id, lang, created) VALUES (?,?,?)",
                (cid, lang, time.time()))
            _api(token, "sendMessage", {
                "chat_id": cid,
                "text": WELCOME_RU if lang == "ru" else WELCOME_EN,
                "parse_mode": "HTML"})
        elif text.startswith("/pro"):
            inv = _api(token, "createInvoiceLink", invoice_payload())
            link = (inv or {}).get("result") if inv else None
            _api(token, "sendMessage", {
                "chat_id": cid,
                "text": ("⭐ <b>Атрия Pro</b> — полный дайджест по всем вертикалям "
                         f"(top-20), {PRO_PRICE_STARS} Stars на {PRO_DAYS} дн.\n"
                         "Оплата внутри Telegram, вывод роя — через Fragment.")[:300],
                "parse_mode": "HTML",
                "reply_markup": ({"inline_keyboard": [[{
                    "text": f"Оплатить {PRO_PRICE_STARS} Stars", "url": link}]]}
                    if link else None)})
        elif text.startswith("/stop"):
            conn.execute("DELETE FROM subs WHERE chat_id = ?", (cid,))
            _api(token, "sendMessage", {"chat_id": cid, "text": "Unsubscribed."})
        handled += 1
    conn.commit()
    conn.close()
    return handled


def broadcast(token: str, db_path, text: str, max_chats: int = 200) -> int:
    """Рассылка дайджеста всем подписчикам. Telegram-сеть падает — шлём кому
    смогли, очередь не копим (дайджест частый — потеря одной волны не критична)."""
    if not token:
        return 0
    conn = _open_subs(db_path)
    rows = conn.execute(
        "SELECT chat_id FROM subs ORDER BY created LIMIT ?", (max_chats,)).fetchall()
    conn.close()
    sent = 0
    for (cid,) in rows:
        if _api(token, "sendMessage",
                {"chat_id": cid, "text": text, "parse_mode": "HTML",
                 "disable_web_page_preview": True}):
            sent += 1
    return sent


def parse_subs_json(raw: str) -> dict:
    """Состояние подписок из HF-файла (Space пишет, тик читает).
    Формат: {"chats": {"<chat_id>": {...}}, "offset": int}"""
    try:
        d = json.loads(raw)
    except Exception:
        return {"chats": {}, "offset": 0}
    d.setdefault("chats", {})
    d.setdefault("offset", 0)
    return d


def fetch_subs(url: str, timeout: int = 20) -> dict:
    """Тянем состояние подписок с HF (public read, без токена)."""
    req = urllib.request.Request(url, headers={"User-Agent": "atria-tick"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return parse_subs_json(r.read().decode("utf-8"))
    except Exception:
        return {"chats": {}, "offset": 0}


def bot_tick(snapshots: list, subs: dict | None = None, lang: str = "ru") -> dict:
    """Вход из тика: раздать дайджесты всем подписчикам из HF-состояния.
    getUpdates НЕ зовём — очередь owns always-on Space (иначе 409 Conflict);
    тик только читает общий файл и рассылает."""
    token = os.environ.get("TG_BOT_TOKEN", "")
    if not token or not subs:
        return {"updates": 0, "sent": 0}
    now = time.time()
    sent = 0
    chats = subs.get("chats", {})
    for key, meta in chats.items():
        cid = meta.get("chat_id") if isinstance(meta, dict) else None
        if cid is None:
            try:  # старый формат — ключ был chat_id
                cid = int(key)
            except Exception:
                continue
        pro = isinstance(meta, dict) and float(meta.get("until", 0) or 0) > now
        for snap in snapshots:
            if not snap.get("totals", {}).get("items"):
                continue  # тощая колония не спамит пустой рассылкой
            text = format_digest(snap, top_n=20 if pro else 5, lang=lang)
            if _api(token, "sendMessage", {"chat_id": cid, "text": text,
                                            "parse_mode": "HTML",
                                            "disable_web_page_preview": True}):
                sent += 1
    return {"updates": 0, "sent": sent}
