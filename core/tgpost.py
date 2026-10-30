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


def format_digest(snapshot: dict, top_n: int = 5, lang: str = "ru",
                  pro_link: str = "") -> str:
    """Чистая функция: снимок → готовое HTML-сообщение дайджеста.
    pro_link подставляется только для бесплатных подписчиков (pitch Pro
    в каждом дайджесте = бесплатная конверсия). Тестируется офлайн."""
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
    if pro_link:
        pitch = ("⭐ <b>Атрия Pro</b> — полный дайджест (top-20, все 10 вертикалей): "
                 if lang == "ru" else
                 "⭐ <b>Atria Pro</b> — full digest (top-20, all 10 verticals): ")
        lines.append(f"\n{pitch}{html.escape(pro_link)}")
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




def process_updates(token: str, state: dict, lang: str = "ru") -> int:
    """Опрос очереди (non-blocking, timeout=0). Тик разбирает накопленное:
    команды и оплаты Stars (платёж обрабатывает сам Telegram по постоянной
    ссылке-инвойсу, нам приходит только подтверждение).
    offset подтверждаем сразу и пишем в state (бот_tick коммитит state в HF,
    если апдейты были)."""
    if not token:
        return 0
    offset = int(state.get("offset", 0) or 0)
    data = _api(token, "getUpdates", {"timeout": 0, "offset": offset})
    if not data or not data.get("ok"):
        return 0
    ups = data.get("result", [])
    chats = state.setdefault("chats", {})
    for u in ups:
        state["offset"] = int(u.get("update_id", offset)) + 1
        msg = (u.get("message") or {})
        chat = msg.get("chat") or {}
        cid = chat.get("id")
        text = (msg.get("text") or "").strip()
        pay = msg.get("successful_payment")
        if pay and cid is not None:
            try:
                days = json.loads(pay.get("payload", "{}")).get("days", PRO_DAYS)
            except Exception:
                days = PRO_DAYS
            chats[str(cid)] = {**(chats.get(str(cid)) or {}), "chat_id": cid,
                               "until": time.time() + days * 86400}
            _api(token, "sendMessage", {
                "chat_id": cid, "parse_mode": "HTML",
                "text": f"⭐ <b>Pro активирован</b> на {days} дн. — полный "
                        "дайджест (top-20) пойдёт следующим тиком. Спасибо!"})
            continue
        if cid is None:
            continue
        if text.startswith("/start"):
            chats[str(cid)] = {**(chats.get(str(cid)) or {}), "chat_id": cid}
            link = state.get("invoice_url")
            hi = WELCOME_RU if lang == "ru" else WELCOME_EN
            if link:
                hi += ("\n\n⭐ <b>Pro</b> (полный дайджест, месяц): "
                       f"<a href=\"{link}\">{PRO_PRICE_STARS} Stars</a>")
            _api(token, "sendMessage", {"chat_id": cid, "parse_mode": "HTML",
                                        "text": hi})
        elif text.startswith("/help"):
            link = state.get("invoice_url")
            _api(token, "sendMessage", {
                "chat_id": cid, "parse_mode": "HTML",
                "text": ("🤖 <b>Атрия</b> — автономный мониторинг 10 вертикалей\n\n"
                         "/start — подписка на дайджест\n"
                         "/pro — подключить Pro (полный top-20)\n"
                         "/stop — отписка\n\n"
                         "Дайджест приходит каждые 4 часа. Бот работает без "
                         "сервера: состояние хранится в открытом репозитории, "
                         "пульс — GitHub Actions."
                         + (f"\n\n⭐ Pro: {link}" if link else ""))})
        elif text.startswith("/pro"):
            link = ensure_invoice(token, state)
            _api(token, "sendMessage", {
                "chat_id": cid, "parse_mode": "HTML",
                "text": f"⭐ <b>Атрия Pro</b> — полный дайджест по всем "
                        f"вертикалям (top-20 вместо 5), {PRO_DAYS} дн.\n"
                        f"Оплата {PRO_PRICE_STARS} Stars внутри Telegram.",
                "reply_markup": ({"inline_keyboard": [[{
                    "text": f"Оплатить {PRO_PRICE_STARS} Stars", "url": link}]]}
                    if link else None)})
        elif text.startswith("/stop"):
            chats.pop(str(cid), None)
            _api(token, "sendMessage", {"chat_id": cid, "text": "Unsubscribed."})
    return len(ups)


def ensure_invoice(token: str, state: dict) -> str | None:
    """Постоянная ссылка-инвойс Stars: создаётся один раз, живёт без нас —
    пока бот не онлайн (бесплатный хостинг), Telegram сам принимает платёж,
    подтверждение придёт в очередь и тик его подберёт."""
    link = state.get("invoice_url")
    if not link:
        d = _api(token, "createInvoiceLink", invoice_payload())
        link = (d or {}).get("result")
        if link:
            state["invoice_url"] = link
    return link


def hf_subs_file() -> str:
    repo = os.environ.get("HF_STATE_REPO", "fshmidtai/atria-hive-state").strip()
    return f"https://huggingface.co/datasets/{repo}/resolve/main/tg_subs.json"


def save_subs(state: dict) -> bool:
    """Коммит состояния подписок в HF-датасет (только если есть HF_TOKEN)."""
    token = os.environ.get("HF_TOKEN", "").strip()
    repo = os.environ.get("HF_STATE_REPO", "fshmidtai/atria-hive-state").strip()
    if not token or not repo or not state:
        return False
    try:
        from huggingface_hub import HfApi
        HfApi(token=token).upload_file(
            path_or_fileobj=json.dumps(state, ensure_ascii=False).encode("utf-8"),
            path_in_repo="tg_subs.json", repo_id=repo, repo_type="dataset",
            commit_message="tg subs state sync")
        return True
    except Exception:
        return False


def parse_subs_json(raw: str) -> dict:
    """Состояние подписок из HF-файла: {"chats": {"<id>": {...}},
    "offset": int, "invoice_url": str?}"""
    try:
        d = json.loads(raw)
    except Exception:
        return {"chats": {}, "offset": 0}
    d.setdefault("chats", {})
    d.setdefault("offset", 0)
    return d


def fetch_subs(url: str | None = None, timeout: int = 20) -> dict:
    """Тянем состояние подписок с HF (public read, без токена)."""
    req = urllib.request.Request(url or hf_subs_file(),
                                 headers={"User-Agent": "atria-tick"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return parse_subs_json(r.read().decode("utf-8"))
    except Exception:
        return {"chats": {}, "offset": 0}


def bot_tick(snapshots: list, lang: str = "ru", subs: dict | None = None) -> dict:
    """Вход из тика: (1) разобрать очередь (подписки/оплаты/команды) и
    закоммитить состояние в HF, (2) раздать дайджесты (Pro = top-20)."""
    token = os.environ.get("TG_BOT_TOKEN", "")
    if not token:
        return {"updates": 0, "sent": 0}
    state = subs if subs is not None else fetch_subs()
    updates = process_updates(token, state, lang=lang)
    if updates:
        state["saved"] = save_subs(state)
    now = time.time()
    sent = 0
    for key, meta in list(state.get("chats", {}).items()):
        cid = meta.get("chat_id") if isinstance(meta, dict) else None
        if cid is None:
            try:
                cid = int(key)
            except Exception:
                continue
        pro = isinstance(meta, dict) and float(meta.get("until", 0) or 0) > now
        # бесплатным — pitch Pro в каждом дайджесте (Pro его не видит)
        pro_link = "" if pro else str(state.get("invoice_url") or "")
        for snap in snapshots:
            if not snap.get("totals", {}).get("items"):
                continue  # тощая колония не спамит пустой рассылкой
            text = format_digest(snap, top_n=20 if pro else 5, lang=lang,
                                 pro_link=pro_link)
            if _api(token, "sendMessage", {"chat_id": cid, "text": text,
                                            "parse_mode": "HTML",
                                            "disable_web_page_preview": True}):
                sent += 1
    return {"updates": updates, "sent": sent,
            "chats": len(state.get("chats", {}))}
