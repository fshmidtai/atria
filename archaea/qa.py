"""QA-ген: улей сам аудирует свои сайты перед публикацией.

Ноль-контакт означает, что человек не откроет 240 страниц руками — 4 раза в
день, годами. Этот модуль — глаза роя: он ловит битый JSON-LD, мёртвые
внутренние ссылки и фантомы sitemap'а ДО того, как страницы увидит индексатор.

Ошибки = публиковать нельзя. Предупреждения = можно, но присмотреться.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from xml.etree import ElementTree as ET

_JSONLD = re.compile(
    r'<script type="application/ld\+json">(.*?)</script>', re.S
)
_HREF = re.compile(r'<a[^>]+href="([^"]+)"')


def _is_external(href: str) -> bool:
    return (
        href.startswith(("http://", "https://", "mailto:", "#", "tel:"))
        or href.startswith("data:")
    )


def _resolve(dist: Path, href: str) -> Path:
    """'/topics/ai.html' → dist/topics/ai.html; 'index.html' → dist/index.html."""
    clean = href.split("#", 1)[0].split("?", 1)[0].strip()
    if not clean:
        return dist
    if clean.startswith("/"):
        return dist / clean.lstrip("/")
    return dist / clean


def audit_site(dist: str | Path, base_url: str = "") -> dict:
    """Полный аудит одной колонии. Возвращает {checks, errors, warnings}."""
    dist = Path(dist)
    checks: list[dict] = []
    errors = warnings = 0

    def add(name: str, ok: bool, detail: str = "", warn: bool = False):
        nonlocal errors, warnings
        if ok:
            checks.append({"check": name, "status": "ok", "detail": ""})
        else:
            status = "warn" if warn else "error"
            if warn:
                warnings += 1
            else:
                errors += 1
            checks.append({"check": name, "status": status, "detail": detail})

    htmls = sorted(dist.rglob("*.html"))
    if not htmls:
        return {"checks": [{"check": "есть страницы", "status": "error",
                            "detail": "0 html в dist"}],
                "errors": 1, "warnings": 0}

    # 1. JSON-LD: валидный JSON в каждой странице. Нет блока — warn,
    #    битый — error (поисковик получит сломанную семантику страницы).
    bad, missing = [], []
    for h in htmls:
        m = _JSONLD.search(h.read_text(encoding="utf-8"))
        if not m:
            missing.append(h.name)
        elif _bad_json(m.group(1)):
            bad.append(h.name)
    add("json-ld валиден", not bad, f"битых: {len(bad)}/{len(htmls)}")
    add("json-ld есть на каждой странице", not missing,
        f"без блока: {len(missing)}/{len(htmls)}", warn=True)

    # 2. canonical, rel=alternate и Open Graph (превью при шеринге) в каждой странице
    no_canon = [h.name for h in htmls
                if not re.search(r'<link rel="canonical"', h.read_text(encoding="utf-8"))]
    add("canonical есть", not no_canon, f"{len(no_canon)}/{len(htmls)}")
    no_og = [h.name for h in htmls
             if not (re.search(r'property="og:title"', h.read_text(encoding="utf-8"))
                     and re.search(r'name="twitter:card"', h.read_text(encoding="utf-8")))]
    add("og/twitter-теги есть", not no_og, f"{len(no_og)}/{len(htmls)}")
    feed_link_bad = [h.name for h in htmls
                     if 'type="application/rss+xml"' not in h.read_text(encoding="utf-8")]
    add("rel=alternate (RSS)", not feed_link_bad, f"{len(feed_link_bad)}/{len(htmls)}",
        warn=True)

    # 2b. фирменная 404: CF Pages подхватит её как fallback
    add("404.html есть", (dist / "404.html").exists(), "нет файла")

    # 3. Внутренние ссылки разрешаются в файлы
    dead: dict[str, list[str]] = {}
    for h in htmls:
        text = h.read_text(encoding="utf-8")
        seen = set()
        for href in _HREF.findall(text):
            if _is_external(href) or href in seen:
                continue
            seen.add(href)
            if not _resolve(dist, href).exists():
                dead.setdefault(str(h.relative_to(dist)), []).append(href)
    n_dead = sum(len(v) for v in dead.values())
    sample = "; ".join(f"{k}→{v[0]}" for k, v in list(dead.items())[:3])
    add("внутренние ссылки живы", n_dead == 0, f"мёртвых: {n_dead} ({sample})")

    # 4. sitemap: каждая заявленная страница существует (и наоборот)
    sm = dist / "sitemap.xml"
    if sm.exists():
        locs = []
        try:
            root = ET.fromstring(sm.read_text(encoding="utf-8"))
            for el in root.iter():
                tag = el.tag.split("}")[-1]
                if tag == "loc" and el.text:
                    locs.append(el.text.strip())
        except Exception:
            add("sitemap парсится", False, "битый XML")
            locs = []
        if locs:
            ghosts = [l for l in locs
                      if base_url and l.startswith(base_url)
                      and not _resolve(dist, l[len(base_url):]).exists()]
            add("sitemap без фантомов", not ghosts, f"{len(ghosts)}/{len(locs)}")
    else:
        add("sitemap.xml есть", False, "нет файла")

    # 5. feed.xml: RSS парсится и не пуст
    feed = dist / "feed.xml"
    if feed.exists():
        try:
            root = ET.fromstring(feed.read_text(encoding="utf-8"))
            n = len(root.findall("channel/item"))
            add("feed.xml не пуст", n > 0, f"item'ов: {n}")
        except Exception as exc:
            add("feed.xml парсится", False, repr(exc)[:60])
    else:
        add("feed.xml есть", False, "нет файла", warn=True)

    # 6. robots.txt: пушистый, указывает на sitemap
    rb = dist / "robots.txt"
    if rb.exists():
        txt = rb.read_text(encoding="utf-8")
        add("robots.txt: Allow + Sitemap",
            "Allow: /" in txt and "Sitemap:" in txt, txt.replace("\n", " ")[:60])
    else:
        add("robots.txt есть", False, "нет файла")

    return {"checks": checks, "errors": errors, "warnings": warnings}


def _bad_json(blob: str) -> bool:
    try:
        json.loads(blob)
        return False
    except Exception:
        return True


def summarize(result: dict) -> str:
    """Одна строка для отчёта улья (ASCII-only!)."""
    n = len(result["checks"])
    return (f"QA ok:{n - result['errors'] - result['warnings']} "
            f"warn:{result['warnings']} err:{result['errors']}")
