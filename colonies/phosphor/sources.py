"""Sources — бесплатные источники данных колонии Phosphor. Никаких API-ключей.

Все источники публичны и без ключей (см. Конституцию §4.3 — соблюдаем ToS):
  - Hacker News (Algolia API)      — что обсуждают в tech-комьюнити
  - arXiv (cs.AI / cs.CL / cs.LG)  — научный поток AI/ML
  - GitHub search API              — новые резонансные репозитории

Любой источник падает -> возвращаем [] и едем дальше: конвейер не должен
останавливаться из-за сбоя одного канала.
"""
from __future__ import annotations

import json
import os
import ssl
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

UA = {"User-Agent": "Atria/0.1 (+https://github.com/)"}
TIMEOUT = 20

ATOM = "{http://www.w3.org/2005/Atom}"

# SSL-контекст: prefer certifi (полный набор CA), иначе системный.
# На некоторых машинах встроенный набор Python не доверяет цепочкам части хостов
# (например, arXiv) — certifi лечит это.
try:
    import certifi

    SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:  # pragma: no cover - системный fallback
    SSL_CTX = ssl.create_default_context()


def _get(url: str, headers: dict | None = None, timeout: int = TIMEOUT):
    h = dict(UA)
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=timeout, context=SSL_CTX) as resp:
        return resp.read().decode("utf-8")


def _epoch(iso: str) -> float:
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()
    except Exception:
        return time.time()


def _item(uid, source, title, url, ts_epoch, points, comments, author, summary=""):
    return {
        "uid": uid,
        "source": source,
        "title": (title or "").strip(),
        "url": url,
        "ts": ts_epoch,
        "points": int(points or 0),
        "comments": int(comments or 0),
        "author": (author or "").strip(),
        "summary": (summary or "").strip(),
    }


# ---------------------------------------------------------------- Hacker News
def fetch_hn(limit: int = 60) -> list[dict]:
    try:
        data = json.loads(
            _get(f"https://hn.algolia.com/api/v1/search?tags=front_page&hitsPerPage={limit}")
        )
    except Exception:
        return []
    out = []
    for h in data.get("hits", []):
        obj_id = h.get("objectID", "")
        link = h.get("url") or f"https://news.ycombinator.com/item?id={obj_id}"
        out.append(
            _item(
                uid=f"hn:{obj_id}",
                source="hn",
                title=h.get("title", ""),
                url=link,
                ts_epoch=_epoch(h.get("created_at", "")),
                points=h.get("points", 0),
                comments=h.get("num_comments", 0),
                author=h.get("author", ""),
                summary=(h.get("story_text") or "")[:400],
            )
        )
    return out


# ---------------------------------------------------------------- arXiv
def fetch_arxiv(limit: int = 60) -> list[dict]:
    url = (
        "https://export.arxiv.org/api/query?search_query=cat:cs.AI+OR+cat:cs.CL+OR+cat:cs.LG"
        f"&sortBy=submittedDate&sortOrder=descending&max_results={limit}"
    )
    try:
        raw = _get(url)
    except Exception:
        return []
    out = []
    try:
        root = ET.fromstring(raw)
        for entry in root.findall(f"{ATOM}entry"):
            eid = (entry.findtext(f"{ATOM}id") or "").strip()
            title = " ".join((entry.findtext(f"{ATOM}title") or "").split())
            link = ""
            for ln in entry.findall(f"{ATOM}link"):
                if ln.get("rel") in (None, "alternate"):
                    link = ln.get("href") or ""
                    break
            summary = " ".join((entry.findtext(f"{ATOM}summary") or "").split())
            author = (entry.find(f"{ATOM}author") or ET.Element("x")).findtext(f"{ATOM}name") or ""
            ts = entry.findtext(f"{ATOM}updated") or ""
            out.append(
                _item(
                    uid=f"arxiv:{eid.rsplit('/abs/', 1)[-1]}",
                    source="arxiv",
                    title=title,
                    url=link,
                    ts_epoch=_epoch(ts),
                    points=0,
                    comments=0,
                    author=author.strip(),
                    summary=summary[:400],
                )
            )
    except Exception:
        return []
    return out


# ---------------------------------------------------------------- GitHub
def fetch_github(limit: int = 40) -> list[dict]:
    since = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
    url = (
        "https://api.github.com/search/repositories"
        f"?q=created:>{since}+stars:>30&sort=stars&order=desc&per_page={limit}"
    )
    headers = {"Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        data = json.loads(_get(url, headers=headers))
    except Exception:
        return []
    out = []
    for repo in data.get("items", []):
        out.append(
            _item(
                uid=f"gh:{repo.get('full_name', '')}",
                source="github",
                title=repo.get("full_name", ""),
                url=repo.get("html_url", ""),
                ts_epoch=repo.get("created_at") and _epoch(repo["created_at"]) or time.time(),
                points=repo.get("stargazers_count", 0),
                comments=repo.get("forks_count", 0),
                author=(repo.get("owner") or {}).get("login", ""),
                summary=(repo.get("description") or "")[:400],
            )
        )
    return out


SOURCES = {"hn": fetch_hn, "arxiv": fetch_arxiv, "github": fetch_github}


def fetch_all(enabled: list[str], limits: dict | None = None) -> dict[str, list[dict]]:
    """Собрать всё, что смогло. Возвращаем {source: [items]} — даже если пусто."""
    limits = limits or {}
    result: dict[str, list[dict]] = {}
    for name in enabled:
        fn = SOURCES.get(name)
        if fn is None:
            continue
        try:
            result[name] = fn(limit=int(limits.get(name, 40)))
        except Exception:
            result[name] = []
    return result
