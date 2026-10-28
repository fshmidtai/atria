"""Sitegen — генератор статического SEO-сайта колонии Phosphor.

Принципы (для Core Web Vitals и любви поисковиков):
  - чистый HTML + inline CSS, ноль внешних запросов, ноль JS-фреймворков
  - JSON-LD разметка (WebSite + Article)
  - sitemap.xml + robots.txt на каждый тик
  - читаемый человеками (lang, мета-описания, alt-тексты)

Выход: dist/ — папка, которую deplo'им на Cloudflare Pages «как есть».
"""
from __future__ import annotations

import html
import json
import re
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape as xescape

from colonies.phosphor.pipeline import SOURCE_LABELS

CSS = """
:root { color-scheme: dark; }
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  background: #0b0d12; color: #d7dce5;
  font: 16px/1.6 -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
}
.wrap { max-width: 980px; margin: 0 auto; padding: 24px 20px 64px; }
header { display: flex; justify-content: space-between; align-items: baseline;
         border-bottom: 1px solid #232836; padding-bottom: 14px; flex-wrap: wrap; gap: 8px; }
.brand { font-weight: 700; font-size: 20px; color: #f2c14e; text-decoration: none; }
nav { display: flex; gap: 16px; }
nav a { color: #9aa4b8; text-decoration: none; }
nav a:hover { color: #f2c14e; }
.hero { padding: 36px 0 8px; }
.hero h1 { font-size: 30px; line-height: 1.25; color: #f4f6fb; }
.hero p { margin-top: 10px; color: #9aa4b8; max-width: 640px; }
.stats { display: flex; gap: 24px; flex-wrap: wrap; margin: 22px 0 6px; }
.stat { background: #12151d; border: 1px solid #232836; border-radius: 10px;
        padding: 12px 18px; }
.stat b { display: block; font-size: 22px; color: #f2c14e; }
.stat span { font-size: 13px; color: #9aa4b8; }
h2 { margin: 34px 0 12px; font-size: 21px; color: #f4f6fb; }
.chips { display: flex; gap: 8px; flex-wrap: wrap; margin: 8px 0 20px; }
.chip { background: #12151d; border: 1px solid #2a3145; color: #c9d2e6;
        border-radius: 999px; padding: 4px 14px; text-decoration: none; font-size: 14px; }
.chip:hover { border-color: #f2c14e; color: #f2c14e; }
table { width: 100%; border-collapse: collapse; }
th, td { text-align: left; padding: 10px 10px; border-bottom: 1px solid #1d2330;
         vertical-align: top; }
th { color: #9aa4b8; font-size: 13px; text-transform: uppercase; letter-spacing: .04em; }
td a { color: #8fb7ff; text-decoration: none; }
td a:hover { text-decoration: underline; }
.src { display: inline-block; font-size: 12px; padding: 2px 8px; border-radius: 999px;
       background: #1a2030; color: #9aa4b8; white-space: nowrap; }
.buzz { color: #f2c14e; font-weight: 600; white-space: nowrap; }
.tagrow { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 4px; }
.tag { font-size: 12px; color: #7f9bc4; }
footer { margin-top: 48px; color: #5d6578; font-size: 13px;
         border-top: 1px solid #232836; padding-top: 16px; }
.bar { background: #1d2330; border-radius: 6px; height: 14px; overflow: hidden; }
.bar > i { display: block; height: 100%; background: #f2c14e; }
.meta { color: #9aa4b8; font-size: 14px; margin-top: 6px; }
.pager { margin-top: 26px; }
@media (max-width: 640px) { .hero h1 { font-size: 23px; } th, td { padding: 8px 6px; } }
"""


def _esc(s: str) -> str:
    return html.escape(str(s), quote=True)


def _slug(s: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    s = s.strip("-")[:64]
    return s or "item"


def _page(body: str, title: str, description: str, base_url: str, path: str,
          jsonld: str = "", feed_title: str = "") -> str:
    canonical = f"{base_url}/{path}" if path else base_url
    feed = (
        f'<link rel="alternate" type="application/rss+xml" '
        f'title="{_esc(feed_title or "RSS")}" href="/feed.xml">'
    )
    # Постраниц без собственного JSON-LD получаем дефолтный WebSite:
    # структурированные данные должны быть на каждой странице (SEO).
    if not jsonld and feed_title:
        jsonld = json.dumps({
            "@context": "https://schema.org",
            "@type": "WebSite",
            "name": feed_title,
            "url": base_url,
        }, ensure_ascii=False)
    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(title)}</title>
<meta name="description" content="{_esc(description)}">
<link rel="canonical" href="{_esc(canonical)}">
{feed}
<script type="application/ld+json">{jsonld}</script>
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
{body}
<footer>Собрано и обновлено автономно роем <b>Атрия</b> · данные из публичных
источников · {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}</footer>
</div>
</body>
</html>
"""


def _header(site: dict) -> str:
    return f"""<header>
  <a class="brand" href="/">{_esc(site["title"])}</a>
  <nav>
    <a href="/">Лента</a>
    <a href="/topics/">Темы</a>
    <a href="/data.html">Данные</a>
    <a href="/about.html">О проекте</a>
  </nav>
</header>"""


def _item_row(rank: int, item: dict) -> str:
    slug = _slug(item["title"])
    tags = "".join(f'<span class="tag">#{t}</span>' for t in item.get("topics", [])[:4])
    return f"""<tr>
  <td class="buzz">{rank}</td>
  <td>
    <a href="/item/{slug}.html">{_esc(item["title"])}</a>
    <div class="tagrow">{tags}</div>
  </td>
  <td><span class="src">{_esc(SOURCE_LABELS.get(item["source"], item["source"]))}</span></td>
  <td class="buzz">{item['buzz']}</td>
</tr>"""


# ---------------------------------------------------------------- страницы
def page_home(snapshot: dict, site: dict, pool: list[dict], top_n: int) -> str:
    items = pool[:top_n]
    t = snapshot["totals"]
    rows = "".join(_item_row(i + 1, it) for i, it in enumerate(items))
    chips = "".join(
        f'<a class="chip" href="/topics/{topic}.html">#{topic}</a>'
        for topic in t["by_topic"]
    )
    body = f"""{_header(site)}
<div class="hero">
  <h1>{_esc(site["tagline"])}</h1>
  <p>Автоматический радар: Hacker News, arXiv и GitHub — что набирает резонанс
     прямо сейчас. Обновляется каждые 6 часов без участия человека.</p>
</div>
<div class="stats">
  <div class="stat"><b>{t['items']}</b><span>публикаций в снимке</span></div>
  <div class="stat"><b>{len(t['by_source'])}</b><span>источника</span></div>
  <div class="stat"><b>{len(t['by_topic'])}</b><span>тем</span></div>
  <div class="stat"><b>{snapshot['generated_at'][:10]}</b><span>снимок от</span></div>
</div>
<div class="chips">{chips}</div>
<h2>Что вспыхнуло</h2>
<table>
  <thead><tr><th>#</th><th>Заголовок</th><th>Источник</th><th>Buzz</th></tr></thead>
  <tbody>{rows}</tbody>
</table>
"""
    jsonld = json.dumps({
        "@context": "https://schema.org",
        "@type": "WebSite",
        "name": site["title"],
        "url": site["base_url"],
        "description": site["tagline"],
    }, ensure_ascii=False)
    return _page(body, f"{site['title']} — {site['tagline'][:60]}",
                 site["tagline"], site["base_url"], "", jsonld,
                 feed_title=site["title"])


def page_topic(topic: str, pool: list[dict], site: dict, top_n: int) -> str:
    """pool — только то, что отрендерилось как /item/: список не может ссылаться
    на несуществующую страницу (аудитор qa за этим следит)."""
    items = [i for i in pool if topic in i.get("topics", [])][:top_n]
    rows = "".join(_item_row(i + 1, it) for i, it in enumerate(items))
    body = f"""{_header(site)}
<div class="hero">
  <h1>#{_esc(topic)}</h1>
  <p>{len(items)} публикаций в последнем снимке роя.</p>
</div>
<table>
  <thead><tr><th>#</th><th>Заголовок</th><th>Источник</th><th>Buzz</th></tr></thead>
  <tbody>{rows}</tbody>
</table>
<div class="pager"><a href="/" style="color:#8fb7ff">← ко всем темам</a></div>
"""
    return _page(body, f"#{topic} — {site['title']}",
                 f"Тема {topic}: свежие публикации и тренды", site["base_url"],
                 f"topics/{topic}.html", feed_title=site["title"])


def page_item(item: dict, site: dict, related: list[dict] | None = None) -> str:
    slug = _slug(item["title"])
    tags = "".join(
        f'<a class="chip" href="/topics/{t}.html">#{t}</a>' for t in item.get("topics", [])
    )
    related_block = ""
    if related:
        chips = "".join(
            f'<a class="chip" href="/item/{_slug(r["title"])}.html">{_esc(r["title"][:60])}</a>'
            for r in related
        )
        related_block = f'<h2>Ещё по теме</h2><div class="chips" style="margin-top:10px">{chips}</div>'
    body = f"""{_header(site)}
<div class="hero">
  <h1>{_esc(item["title"])}</h1>
  <div class="meta">
    <span class="src">{_esc(SOURCE_LABELS.get(item["source"], item["source"]))}</span>
    · {_esc(item["date"])} · buzz <b class="buzz">{item['buzz']}</b>
    {f"· {item['points']} поинтов / {item['comments']} комментариев" if item["comments"] or item["points"] else ""}
  </div>
  {f'<p style="margin-top:14px;color:#c2c9d8">{_esc(item["summary"])}</p>' if item["summary"] else ""}
  <p style="margin-top:18px"><a href="{_esc(item['url'])}" style="color:#8fb7ff">Читать первоисточник →</a></p>
  <div class="chips" style="margin-top:18px">{tags}</div>
</div>
{related_block}
<div class="pager"><a href="/" style="color:#8fb7ff">← к ленте</a></div>
"""
    jsonld = json.dumps({
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": item["title"],
        "url": item["url"],
        "datePublished": item["date"],
        "publisher": {"@type": "Organization", "name": site["title"]},
        "mainEntityOfPage": f"{site['base_url']}/item/{slug}.html",
    }, ensure_ascii=False)
    return _page(body, f"{item['title']} — {site['title']}",
                 (item["summary"] or item["title"])[:155].strip(),
                 site["base_url"], f"item/{slug}.html", jsonld,
                 feed_title=site["title"])


def page_data(snapshot: dict, site: dict) -> str:
    t = snapshot["totals"]
    dom_rows = "".join(
        f"<tr><td><b>{_esc(d)}</b></td><td>{n}</td></tr>" for d, n in t["top_domains"]
    )
    max_t = max(t["by_topic"].values() or [1])
    topic_rows = "".join(
        f"""<tr><td><a href="/topics/{k}.html" style="color:#8fb7ff">#{k}</a></td>
            <td style="width:55%"><div class="bar"><i style="width:{int(v/max_t*100)}%"></i></div></td>
            <td class="buzz">{v}</td></tr>"""
        for k, v in t["by_topic"].items()
    )
    body = f"""{_header(site)}
<div class="hero">
  <h1>Данные снимка</h1>
  <p>Анатомия последнего цикла сбора: источники, темы, домены. Полный датасет
     публикуется на HuggingFace и обновляется каждые 6 часов.</p>
</div>
<h2>Темы</h2>
<table><thead><tr><th>тема</th><th></th><th>публикаций</th></tr></thead>
<tbody>{topic_rows}</tbody></table>
<h2>Топ доменов</h2>
<table><thead><tr><th>домен</th><th>упоминаний</th></tr></thead>
<tbody>{dom_rows}</tbody></table>
"""
    return _page(body, f"Данные — {site['title']}", "Статистика и структура данных снимка",
                 site["base_url"], "data.html", feed_title=site["title"])


def page_about(site: dict) -> str:
    body = f"""{_header(site)}
<div class="hero">
  <h1>О проекте</h1>
  <p><b>{_esc(site["title"])}</b> — полностью автономное издание. Его собирает
     мультиагентная система <b>Атрия</b>: агенты-«разведчики» тянут потоки из
     публичных источников (Hacker News, arXiv, GitHub), очищают, считают
     «базз»-скоринг и генерируют эту страницу.</p>
  <p style="margin-top:12px">Ни одного ручного действия: код живёт в git,
     пульс приходит по cron, хостинг — Cloudflare, датасеты — HuggingFace.</p>
  <p style="margin-top:12px">Связь: <a href="{_esc(site.get('contact', site['base_url']))}" style="color:#8fb7ff">{_esc(site.get('contact', site['base_url']))}</a></p>
</div>
"""
    return _page(body, f"О проекте — {site['title']}", "Об автономном издании и рое Атрия",
                 site["base_url"], "about.html", feed_title=site["title"])


# ---------------------------------------------------------------- RSS колонии
def generate_feed(snapshot: dict, outdir: str | Path, config: dict) -> str:
    """RSS 2.0 колонии. Item'ы ссылаются на наши страницы, а не на источники:
    подписка агрегаторов и читалок приводит трафик в колонию, а не уводит его.
    """
    site = config["site"]
    items = snapshot["items"][: int(config.get("top_items_home", 30))]
    xml_items = []
    for it in items:
        slug = _slug(it["title"])
        link = f"{site['base_url']}/item/{slug}.html"
        pub = datetime.fromtimestamp(
            float(it.get("ts", time.time())), tz=timezone.utc
        ).strftime("%a, %d %b %Y %H:%M:%S GMT")
        xml_items.append(
            "    <item>\n"
            f"      <title>{xescape(it['title'])}</title>\n"
            f"      <link>{xescape(link)}</link>\n"
            f'      <guid isPermaLink="true">{xescape(link)}</guid>\n'
            f"      <pubDate>{pub}</pubDate>\n"
            f"      <description>{xescape((it.get('summary') or '')[:300])}</description>\n"
            "    </item>"
        )
    built = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<rss version=\"2.0\">\n"
        "  <channel>\n"
        f"    <title>{xescape(site['title'])}</title>\n"
        f"    <link>{site['base_url']}</link>\n"
        f"    <description>{xescape(site['tagline'])}</description>\n"
        "    <language>ru</language>\n"
        f"    <lastBuildDate>{built}</lastBuildDate>\n"
        + "\n".join(xml_items)
        + "\n  </channel>\n</rss>\n"
    )
    path = Path(outdir) / "feed.xml"
    path.write_text(xml, encoding="utf-8")
    return str(path)


def _related(item: dict, pool: list[dict], limit: int = 5) -> list[dict]:
    """Перекрёстные ссылки по общим темам — внутренний линкинг для SEO."""
    out = []
    for other in pool:
        if other.get("uid") == item.get("uid"):
            continue
        if set(other.get("topics", [])) & set(item.get("topics", [])):
            out.append(other)
            if len(out) >= limit:
                break
    return out


# ---------------------------------------------------------------- главный
def generate(snapshot: dict, outdir: str | Path, config: dict) -> dict:
    site = config["site"]
    outdir = Path(outdir)

    # Сначала фиксируем пул рендера, потом только из него строим списки —
    # так ни одна страница не сошлётся на /item/, которого нет.
    # Предыдущие рендеры (устаревшие item-страницы) вычищаем: dist = снимок.
    n_items = int(config.get("top_item_pages", 60))
    pool = snapshot["items"][:n_items]
    for sub in ("item", "topics"):
        d = outdir / sub
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)
        d.mkdir(parents=True, exist_ok=True)

    # Топики рендерим объединением: прописанные в config + реально пришедшие в
    # снимке. Иначе чип «#dev» на странице сошлётся на несуществующую страницу.
    t_topics = set(snapshot["totals"].get("by_topic", {}))
    topics = sorted(set(config.get("topics", [])) | t_topics)

    urls = []
    home = page_home(snapshot, site, pool, int(config.get("top_items_home", 30)))
    (outdir / "index.html").write_text(home, encoding="utf-8")

    for topic in topics:
        p = page_topic(topic, pool, site, int(config.get("top_items_topic", 30)))
        (outdir / "topics" / f"{topic}.html").write_text(p, encoding="utf-8")
        urls.append(f"topics/{topic}.html")

    slugs = set()
    for item in pool:
        slug = _slug(item["title"])
        if slug in slugs:
            continue
        slugs.add(slug)
        p = page_item(item, site, _related(item, pool))
        (outdir / "item" / f"{slug}.html").write_text(p, encoding="utf-8")
        urls.append(f"item/{slug}.html")

    (outdir / "data.html").write_text(page_data(snapshot, site), encoding="utf-8")
    (outdir / "about.html").write_text(page_about(site), encoding="utf-8")
    generate_feed(snapshot, outdir, config)
    urls += ["data.html", "about.html", "feed.xml"]

    sitemap = "\n".join(
        f'<url><loc>{site["base_url"]}/{u}</loc><lastmod>'
        f'{snapshot["generated_at"][:10]}</lastmod></url>'
        for u in urls
    )
    (outdir / "sitemap.xml").write_text(
        f'<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f'{sitemap}\n</urlset>\n',
        encoding="utf-8",
    )
    (outdir / "robots.txt").write_text(
        f'User-agent: *\nAllow: /\nSitemap: {site["base_url"]}/sitemap.xml\n',
        encoding="utf-8",
    )

    return {
        "pages": len(urls) + 1,
        "outdir": str(outdir),
        "sitemap": [f"{site['base_url']}/{u}" for u in urls][:10],
    }
