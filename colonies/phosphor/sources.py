"""Sources — бесплатные источники данных колоний. Никаких API-ключей.

Источник = «рецепт»:
  {"kind": "hn_front",      "limit": 60}
  {"kind": "hn_search",     "query": "Show HN", "limit": 60}
  {"kind": "arxiv",         "limit": 60}
  {"kind": "github_search", "q": "topic:ai stars:>50", "days": 14, "limit": 40}

Все источники публичны и без ключей (Конституция §4.3 — соблюдаем ToS).
Любой источник падает -> возвращаем [] и едем дальше: конвейер не должен
останавливаться из-за сбоя одного канала.
"""
from __future__ import annotations

import email.utils
import hashlib
import json
import os
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

#UA: честный, но «совместимый» — проходит наивные UA-фильтры CDN и не врёт,
# кто мы такие (Конституция §4: вежливый бот — живой бот).
UA = {"User-Agent": "Mozilla/5.0 (compatible; Atria/0.1; +https://github.com/)"}
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


def _rfc822(s: str | None) -> float:
    """RFC 822 (поля pubDate в RSS) и ISO 8601 (Atom) → epoch."""
    if not s:
        return time.time()
    try:
        return email.utils.parsedate_to_datetime(s).timestamp()
    except Exception:
        return _epoch(s)


# ---------------------------------------------------------------- robots.txt
_ROBOTS_CACHE: dict = {}


def _robots_allowed(url: str) -> bool:
    """Соблюдаем robots.txt (Конституция §4.3). Файла нет — ограничений нет."""
    p = urllib.parse.urlparse(url)
    if not p.scheme.startswith("http"):
        return True
    host = f"{p.scheme}://{p.netloc}"
    if host not in _ROBOTS_CACHE:
        rp = urllib.robotparser.RobotFileParser()
        try:
            raw = _get(host + "/robots.txt", timeout=10)
            rp.parse(raw.splitlines())
        except Exception:
            rp = None  # нет/недоступен robots.txt → не ограничиваем
        _ROBOTS_CACHE[host] = rp
    rp = _ROBOTS_CACHE[host]
    if rp is None:
        return True
    return rp.can_fetch(UA["User-Agent"], url)


# ---------------------------------------------------------------- RSS / Atom
def _parse_feed(raw: str, _feed_url: str = "") -> list[dict]:
    out: list[dict] = []
    try:
        root = ET.fromstring(raw)
    except Exception:
        return []

    def _uid(seed: str) -> str:
        return "rss:" + hashlib.md5((seed or "").encode("utf-8")).hexdigest()[:14]

    if root.tag == "rss":
        channel = root.find("channel")
        items = channel.findall("item") if channel is not None else []
        for it in items:
            title = " ".join((it.findtext("title") or "").split())
            link = (it.findtext("link") or "").strip()
            desc = " ".join((it.findtext("description") or "").split())
            creator = it.findtext("{http://purl.org/dc/elements/1.1/}creator") or it.findtext("author") or ""
            out.append(_item(
                _uid(link or title), "rss", title, link,
                _rfc822(it.findtext("pubDate")), 0, 0, creator.strip(), desc[:400],
            ))
    elif root.tag.endswith("}feed") or root.tag == "feed":
        for entry in root.findall(f"{ATOM}entry"):
            title = " ".join((entry.findtext(f"{ATOM}title") or "").split())
            link = ""
            for ln in entry.findall(f"{ATOM}link"):
                if ln.get("rel") in (None, "alternate"):
                    link = ln.get("href") or ""
                    break
            desc = " ".join((
                entry.findtext(f"{ATOM}summary") or entry.findtext(f"{ATOM}content") or ""
            ).split())
            author = (entry.find(f"{ATOM}author") or ET.Element("x")).findtext(f"{ATOM}name") or ""
            out.append(_item(
                _uid(link or title), "rss", title, link,
                _rfc822(entry.findtext(f"{ATOM}updated") or entry.findtext(f"{ATOM}published")),
                0, 0, author.strip(), desc[:400],
            ))
    return out


def fetch_rss(url: str, limit: int = 40) -> list[dict]:
    """RSS 2.0 / Atom-фид — самый машинно-дружелюбный публичный формат."""
    if not url:
        return []
    try:
        if not _robots_allowed(url):
            return []  # хозяин не велел — уходим (§4.3)
        raw = _get(url)
    except Exception:
        return []
    return _parse_feed(raw)[:limit]


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
def _hn_to_items(data: dict) -> list[dict]:
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


def _hn_fetch(params: dict) -> list[dict]:
    url = "https://hn.algolia.com/api/v1/search?" + urllib.parse.urlencode(params)
    try:
        return _hn_to_items(json.loads(_get(url)))
    except Exception:
        return []


def fetch_hn(limit: int = 60) -> list[dict]:
    """Front page Hacker News — что вообще обсуждает tech-комьюнити."""
    return _hn_fetch({"tags": "front_page", "hitsPerPage": limit})


def fetch_hn_search(query: str, limit: int = 60) -> list[dict]:
    """Поиск по HN — 'Show HN' даёт поток свежих продуктовых запусков."""
    if not query:
        return []
    return _hn_fetch({"query": query, "tags": "story", "hitsPerPage": limit})


# ---------------------------------------------------------------- arXiv
def fetch_arxiv(limit: int = 60, cats: str = "") -> list[dict]:
    """Свежие препринты. cats — категории по умолчанию AI/CL/LG; для финансов
    колония передаёт q-fin.* (см. config колонии)."""
    if not cats:
        cats = "cs.AI+OR+cat:cs.CL+OR+cat:cs.LG"
    url = (
        f"https://export.arxiv.org/api/query?search_query=cat:{cats}"
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
def fetch_github(limit: int = 40, q: str = "", days: int = 7) -> list[dict]:
    """Поиск свежих резонансных репозиториев. q — дополнительный фильтр ('topic:ai')."""
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    parts = []
    if q:
        parts.append(q)
    if "created:" not in q:
        parts.append(f"created:>{since}")
    query = " ".join(parts)
    url = (
        "https://api.github.com/search/repositories?"
        + urllib.parse.urlencode({"q": query, "sort": "stars", "order": "desc", "per_page": limit})
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
        created = repo.get("created_at")
        out.append(
            _item(
                uid=f"gh:{repo.get('full_name', '')}",
                source="github",
                title=repo.get("full_name", ""),
                url=repo.get("html_url", ""),
                ts_epoch=_epoch(created) if created else time.time(),
                points=repo.get("stargazers_count", 0),
                comments=repo.get("forks_count", 0),
                author=(repo.get("owner") or {}).get("login", ""),
                summary=(repo.get("description") or "")[:400],
            )
        )
    return out


# ---------------------------------------------------------------- GitHub Security Advisories
# Severity = «важность» для security-аудитории: критическая CVE по сигналу
# сопоставима с топом HN, а не тонет в шумном потоке.
_SEVERITY_WEIGHTS = {
    "critical": 6000, "high": 3500, "moderate": 1800, "medium": 1800, "low": 700,
}


def fetch_github_advisories(limit: int = 30) -> list[dict]:
    """Публичный поток GitHub Security Advisories — живые CVE без API-ключа.

    Severity даёт «очки важности» — критический баг всплывёт выше потока.
    """
    headers = {"Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        data = json.loads(
            _get(f"https://api.github.com/advisories?per_page={limit}", headers=headers)
        )
    except Exception:
        return []
    out = []
    for a in data:
        cve = a.get("cve_id") or ""
        ghsa = a.get("ghsa_id") or ""
        sev = (a.get("severity") or "").lower()
        pkg = (((a.get("vulnerabilities") or [{}])[0]).get("package") or {}).get("name", "")
        title = f"{cve or ghsa}: {a.get('summary', '')}".strip()
        url = a.get("html_url") or f"https://github.com/advisories/{ghsa}"
        out.append(
            _item(
                uid=f"cve:{ghsa or cve}",
                source="cve",
                title=title,
                url=url,
                ts_epoch=_epoch(a.get("published_at") or a.get("updated_at") or ""),
                points=_SEVERITY_WEIGHTS.get(sev, 50),
                comments=0,
                author=pkg,
                summary=f"Severity: {sev or 'n/a'}. {(a.get('description') or '')[:300]}",
            )
        )
    return out


# ---------------------------------------------------------------- движок рецептов
def fetch_html_list(url: str, pattern: str = r"/tender/", limit: int = 40) -> list[dict]:
    """HTML-страница-каталог как источник: якоря, href которых содержат
    pattern (например '/tender/'). Для публичных агрегаторов без RSS —
    рынок, который deliberately не отдаёт фиды (44-ФЗ).
    Уважаем robots.txt (§4.3), ошибки → [] (рой едет дальше)."""
    import html as _html
    import re as _re

    if not url:
        return []
    try:
        if not _robots_allowed(url):
            return []
        raw = _get(url)
    except Exception:
        return []
    rx = _re.compile(r'<a\s[^>]*href="([^"]+)"[^>]*>(.*?)</a>', _re.S | _re.I)
    seen, out = set(), []
    for href, inner in rx.findall(raw):
        if pattern not in href:
            continue
        link = href if href.startswith("http") else url.rstrip("/") + "/" + href.lstrip("/")
        if link in seen:
            continue
        seen.add(link)
        title = _re.sub(r"<[^>]+>", "", inner)
        title = _html.unescape(_re.sub(r"\s+", " ", title)).strip()
        if len(title) < 8:
            continue
        out.append(_item(
            uid=link, source="html", title=title, url=link,
            ts_epoch=time.time(), points=0, comments=0, author=""))
        if len(out) >= limit:
            break
    return out


def fetch_recipes(recipes: list) -> dict[str, list[dict]]:
    """Прогнать рецепты. Возвращает {label: [items]} — даже пустые, чтобы конвейер не дёргался.

    Каждый item дополнительно помечается рецептом (поле 'recipe') — для аналитики.
    """
    out: dict[str, list[dict]] = {}
    for recipe in recipes or []:
        if not isinstance(recipe, dict):
            continue
        kind = recipe.get("kind", "")
        label = recipe.get("label") or kind
        try:
            if kind == "hn_front":
                items = fetch_hn(limit=int(recipe.get("limit", 40)))
            elif kind == "hn_search":
                items = fetch_hn_search(recipe.get("query", ""), limit=int(recipe.get("limit", 40)))
            elif kind == "arxiv":
                items = fetch_arxiv(limit=int(recipe.get("limit", 40)),
                                    cats=recipe.get("cats", ""))
            elif kind == "github_search":
                items = fetch_github(
                    limit=int(recipe.get("limit", 40)),
                    q=recipe.get("q", ""),
                    days=int(recipe.get("days", 7)),
                )
            elif kind == "rss":
                items = fetch_rss(recipe.get("url", ""), limit=int(recipe.get("limit", 40)))
            elif kind == "html_list":
                items = fetch_html_list(
                    recipe.get("url", ""),
                    pattern=recipe.get("pattern", r"/tender/"),
                    limit=int(recipe.get("limit", 40)))
            elif kind == "github_advisories":
                items = fetch_github_advisories(limit=int(recipe.get("limit", 30)))
            else:
                continue
        except Exception:
            items = []
        for it in items:
            it["recipe"] = label
        out[label] = items
    return out
