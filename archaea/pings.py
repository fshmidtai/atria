"""Pings — заявки на индексацию новых страниц (IndexNow: Bing, Yandex, Seznam).

Протокол: кладём на сайт файл key.txt с нашим ключом (доказательство владения),
POST на api.indexnow.org список URL — поисковики сами решают, что краулить.
Бесплатно, без API-ключей и регистрации — идеально для роя (§4.3).

Ошибки → False, тик едет дальше.
"""
from __future__ import annotations

import json
import urllib.request

API = "https://api.indexnow.org/IndexNow"


def submit(base_url: str, key: str, urls: list[str],
           timeout: int = 30) -> tuple[bool, str]:
    """base_url: https://host.pages.dev; key: hex-ключ; urls: страницы сайта.
    Возвращает (ok, заметка) — для отчёта тика."""
    urls = [u for u in (urls or []) if u.startswith(base_url)]
    if not urls or not key or not base_url.startswith("http"):
        return False, "нет данных"
    body = json.dumps({
        "host": base_url.split("//", 1)[1],
        "key": key,
        "keyLocation": f"{base_url}/key.txt",
        "urlList": urls,
    }).encode("utf-8")
    req = urllib.request.Request(
        API, data=body, headers={"Content-Type": "application/json"},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            # 200 = принято, 202 — в обработке, 422 — плохой ключ/рой
            return r.status in (200, 202), f"HTTP {r.status}, {len(urls)} url"
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}"
    except Exception as e:
        return False, f"{type(e).__name__}"


def gen_key(colony: str) -> str:
    """Детерминированный hex-ключ колонии: один доктор на все тики."""
    import hashlib
    return hashlib.sha256(("atria-indexnow-" + colony).encode()).hexdigest()[:32]
