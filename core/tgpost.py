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


def bot_tick(snapshots: list, db_path, lang: str = "ru") -> dict:
    """Вход из тика: (1) забрать_signupы, (2) раздать дайджесты.
    Каждый снимок — своя колония; подписчик один на всех (MVP)."""
    token = os.environ.get("TG_BOT_TOKEN", "")
    if not token:
        return {"updates": 0, "sent": 0}
    updates = handle_updates(token, db_path, lang=lang)
    sent = 0
    for snap in snapshots:
        if not snap.get("totals", {}).get("items"):
            continue  # тощая колония не спамит пустой рассылкой
        text = format_digest(snap, top_n=5, lang=lang)
        sent += broadcast(token, db_path, text)
    return {"updates": updates, "sent": sent}
