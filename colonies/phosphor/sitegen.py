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
.cta { margin-top: 40px; background: #12151d; border: 1px solid #2a3145;
       border-radius: 12px; padding: 20px 22px; }
.cta p { margin: 0 0 12px; color: #c9d2e6; }
.cta b { color: #f4f6fb; }
.cta a.btn { display: inline-block; margin: 4px 12px 0 0; padding: 8px 18px;
             border-radius: 8px; background: #f2c14e; color: #141822;
             text-decoration: none; font-weight: 600; font-size: 14px; }
.cta a.btn.ghost { background: transparent; border: 1px solid #3a4358; color: #c9d2e6; }
.bar { background: #1d2330; border-radius: 6px; height: 14px; overflow: hidden; }
.bar > i { display: block; height: 100%; background: #f2c14e; }
.meta { color: #9aa4b8; font-size: 14px; margin-top: 6px; }
.pager { margin-top: 26px; }
@media (max-width: 640px) { .hero h1 { font-size: 23px; } th, td { padding: 8px 6px; } }
"""


def _esc(s: str) -> str:
    return html.escape(str(s), quote=True)


# ------------------------------------------------------------------ i18n
# Копи-таблица: одна кодовая база — любые локали. lang берётся из config
# колонии, EN-колония рождается без единой строчки кода (programmatic SEO:
# та же дата, другой языковой рынок).
COPY = {
    "ru": {
        "nav_feed": "Лента", "nav_topics": "Темы", "nav_data": "Данные",
        "nav_trends": "Тренды", "nav_about": "О проекте",
        "intro": "Автоматический радар: публичные потоки — что набирает резонанс "
                 "прямо сейчас. Обновляется каждые 6 часов без участия человека.",
        "hot": "Что вспыхнуло",
        "st_items": "публикаций в снимке", "st_sources": "источников",
        "st_topics": "тем", "st_shot": "снимок от",
        "th_title": "Заголовок", "th_source": "Источник",
        "topic_meta": "Тема {topic}: свежие публикации и тренды",
        "topic_n": "{n} публикаций в последнем снимке роя.",
        "back_topics": "← ко всем темам",
        "related": "Ещё по теме",
        "pts": "{p} поинтов / {c} комментариев",
        "read_source": "Читать первоисточник →", "back_feed": "← к ленте",
        "data_h": "Данные снимка",
        "data_p": "Анатомия последнего цикла сбора: источники, темы, домены. Полный "
                  "датасет публикуется на HuggingFace и обновляется каждые 6 часов.",
        "topics_h": "Темы", "th_topic": "тема", "th_count": "публикаций",
        "topics_index_p": "Все темы снимка в одном окне. Каждая страница темы — "
                          "свежая подборка по своей области, обновляется каждый тик.",
        "topics_index_meta": "Все темы колонии — каталог свежих подборок",
        "domains_h": "Топ доменов", "th_domain": "домен", "th_mentions": "упоминаний",
        "data_title": "Данные — {title}",
        "data_desc": "Статистика и структура данных снимка",
        "trends_h": "Trend Index — что растёт",
        "trends_p": "Прирост и спад по темам относительно предыдущего тика роя. "
                    "Тот же индекс живьём — в дата-продуктах колонии.",
        "trends_empty": "Динамика появится со второго тика — рой копит историю.",
        "th_today": "сегодня", "th_prev": "прошлый тик", "th_delta": "дельта",
        "trends_title": "Trend Index — {title}",
        "trends_desc": "Прирост и спад тем относительно предыдущего тика",
        "about_h": "О проекте",
        "about_p1": "<b>{title}</b> — полностью автономное издание. Его собирает "
                    "мультиагентная система <b>Атрия</b>: агенты-«разведчики» тянут "
                    "потоки из публичных источников, очищают, считают «базз»-скоринг "
                    "и генерируют эту страницу.",
        "about_p2": "Ни одного ручного действия: код живёт в git, пульс приходит по "
                    "cron, хостинг — Cloudflare, датасеты — HuggingFace.",
        "contact": "Связь:",
        "about_title": "О проекте — {title}",
        "about_desc": "Об автономном издании и рое Атрия",
        "footer": "Собрано и обновлено автономно роем <b>Атрия</b> · данные из "
                  "публичных источников",
        "og_locale": "ru_RU",
        "404_h": "404 — страницы не существует",
        "404_p": "Рой собрал этот снимок заново, и старая страница растворилась. "
                 "Загляните в ленту — там всё свежее.",
        "404_title": "404 — {title}", "404_desc": "Страница не найдена",
        "mon_pitch": "Рой живёт на бесплатной инфраструктуре и собирает данные "
                     "каждые 6 часов. Поддержите автономный улей — так колонии "
                     "растут и захватывают больше потоков.",
        "mon_support": "Поддержать улей",
        "mon_buy": "Купить полный датасет",
        "mon_crypto": "Поддержать криптой — переводы напрямую на кошелёк:",
        "mon_stars": "⭐ Атрия Pro — полный дайджест (199 Stars/мес)",
    },
    "en": {
        "nav_feed": "Feed", "nav_topics": "Topics", "nav_data": "Data",
        "nav_trends": "Trends", "nav_about": "About",
        "intro": "An autonomous radar of public streams — what is gaining resonance "
                 "right now. Updated every 6 hours, no human in the loop.",
        "hot": "Trending now",
        "st_items": "items in snapshot", "st_sources": "sources",
        "st_topics": "topics", "st_shot": "snapshot of",
        "th_title": "Title", "th_source": "Source",
        "topic_meta": "Topic {topic}: fresh posts and trends",
        "topic_n": "{n} posts in the colony's latest snapshot.",
        "back_topics": "← all topics",
        "related": "More on the topic",
        "pts": "{p} points / {c} comments",
        "read_source": "Read the source →", "back_feed": "← back to feed",
        "data_h": "Snapshot data",
        "data_p": "Anatomy of the latest crawl: sources, topics, domains. The full "
                  "dataset is published on HuggingFace and updated every 6 hours.",
        "topics_h": "Topics", "th_topic": "topic", "th_count": "posts",
        "topics_index_p": "Every topic of the snapshot in one window. Each topic "
                          "page is a fresh selection for its field, updated every cycle.",
        "topics_index_meta": "All colony topics — directory of fresh picks",
        "domains_h": "Top domains", "th_domain": "domain", "th_mentions": "mentions",
        "data_title": "Data — {title}",
        "data_desc": "Statistics and structure of the snapshot",
        "trends_h": "Trend Index — what is growing",
        "trends_p": "Growth and decline by topic versus the previous swarm tick. "
                    "The same index, live — in the colony's data products.",
        "trends_empty": "Trends appear after the second tick — the swarm is gathering history.",
        "th_today": "today", "th_prev": "previous tick", "th_delta": "delta",
        "trends_title": "Trend Index — {title}",
        "trends_desc": "Topic growth and decline versus the previous tick",
        "about_h": "About",
        "about_p1": "<b>{title}</b> is a fully autonomous publication. It is built "
                    "by the <b>Atria</b> multi-agent system: scout agents pull "
                    "streams from public sources, clean them, score the buzz and "
                    "render this page.",
        "about_p2": "Zero manual actions: the code lives in git, the pulse comes "
                    "from cron, hosting is Cloudflare, datasets are on HuggingFace.",
        "contact": "Contact:",
        "about_title": "About — {title}",
        "about_desc": "About the autonomous publication and the Atria swarm",
        "footer": "Built and updated autonomously by the <b>Atria</b> swarm · data "
                  "from public sources",
        "og_locale": "en_US",
        "404_h": "404 — page not found",
        "404_p": "The swarm rebuilt this snapshot and the old page dissolved. "
                 "Check the feed — everything there is fresh.",
        "404_title": "404 — {title}", "404_desc": "Page not found",
        "mon_pitch": "The swarm runs on free infrastructure and harvests data "
                     "every 6 hours. Support the autonomous hive — so colonies "
                     "grow and cover more streams.",
        "mon_support": "Support the hive",
        "mon_buy": "Buy the full dataset",
        "mon_crypto": "Support with crypto (no reversal needed — networks and addresses are current):",
        "mon_stars": "⭐ Atria Pro — full digest (199 Stars/mo)",
    },
}


def _lang(site: dict) -> str:
    return site.get("lang", "ru")


def _cta(site: dict) -> str:
    """Монетизационный блок. Управляется config колонии:
    "monetization": {"support_url": "...", "products_url": "...",
                     "crypto": [{"net": "TON", "address": "..."}, ...]}.
    Нет рельсов — пустая строка, сайт не меняется. Крипто-рельс: приём на
    self-custody кошелёк, работает из РФ без международных карт и KYC
    (анализ рельсов: docs/STAGE4_NICHES.md).
    """
    mon = (site or {}).get("monetization") or {}
    support = mon.get("support_url")
    products = mon.get("products_url")
    stars = mon.get("stars")
    crypto = [c for c in (mon.get("crypto") or [])
              if c.get("net") and c.get("address")]
    if not (support or products or crypto or stars):
        return ""
    L = COPY.get(_lang(site), COPY["ru"])
    buttons = ""
    if support:
        buttons += f'<a class="btn" href="{_esc(support)}" rel="nofollow noopener">{L["mon_support"]}</a>'
    if products:
        buttons += f'<a class="btn ghost" href="{_esc(products)}" rel="nofollow noopener">{L["mon_buy"]}</a>'
    stars_html = ""
    if stars:
        stars_html = ('<p style="margin-top:14px"><a class="btn ghost" '
                      f'href="{_esc(stars)}" rel="nofollow noopener">⭐ '
                      + L.get("mon_stars", "Атрия Pro — месяц (Stars)") + '</a></p>')
    crypto_html = ""
    if crypto:
        rows = "".join(
            '<div style="margin-top:8px"><b>' + _esc(c["net"]) + '</b> '
            '<code style="background:#1a2030;padding:2px 8px;border-radius:6px;'
            'font-size:13px;word-break:break-all">' + _esc(c["address"]) + '</code></div>'
            for c in crypto
        )
        crypto_html = ('<p style="margin-top:14px"><b>' + L["mon_crypto"]
                       + '</b></p>' + rows)
    return ('<div class="cta"><p>' + L["mon_pitch"] + '</p>' + buttons
            + stars_html + crypto_html + '</div>')


def _L(site: dict) -> dict:
    return COPY.get(_lang(site), COPY["ru"])


def _slug(s: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    s = s.strip("-")[:64]
    return s or "item"


def _page(body: str, title: str, description: str, base_url: str, path: str,
          jsonld: str = "", feed_title: str = "", lang: str = "ru",
          cta: str = "") -> str:
    L = COPY.get(lang, COPY["ru"])
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
    # Open Graph / Twitter: превью при шеринге = трафик. og:type выводим из
    # JSON-LD (Article → article), og:image добавим с брендингом позже.
    og_type = "article" if '"@type": "Article"' in jsonld else "website"
    og = (
        f'<meta property="og:type" content="{og_type}">'
        f'<meta property="og:site_name" content="{_esc(feed_title or title)}">'
        f'<meta property="og:title" content="{_esc(title)}">'
        f'<meta property="og:description" content="{_esc(description)}">'
        f'<meta property="og:url" content="{_esc(canonical)}">'
        f'<meta property="og:locale" content="{L["og_locale"]}">'
        '<meta name="twitter:card" content="summary">'
        f'<meta name="twitter:title" content="{_esc(title)}">'
        f'<meta name="twitter:description" content="{_esc(description)}">'
    )
    footer_ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return f"""<!DOCTYPE html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(title)}</title>
<meta name="description" content="{_esc(description)}">
<link rel="canonical" href="{_esc(canonical)}">
{feed}
{og}
<script type="application/ld+json">{jsonld}</script>
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
{body}
{cta}
<footer>{L["footer"]} · {footer_ts}</footer>
</div>
</body>
</html>
"""


def _header(site: dict) -> str:
    L = _L(site)
    return f"""<header>
  <a class="brand" href="/">{_esc(site["title"])}</a>
  <nav>
    <a href="/">{L["nav_feed"]}</a>
    <a href="/topics/">{L["nav_topics"]}</a>
    <a href="/trends.html">{L["nav_trends"]}</a>
    <a href="/data.html">{L["nav_data"]}</a>
    <a href="/about.html">{L["nav_about"]}</a>
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
    L = _L(site)
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
  <p>{L["intro"]}</p>
</div>
<div class="stats">
  <div class="stat"><b>{t['items']}</b><span>{L['st_items']}</span></div>
  <div class="stat"><b>{len(t['by_source'])}</b><span>{L['st_sources']}</span></div>
  <div class="stat"><b>{len(t['by_topic'])}</b><span>{L['st_topics']}</span></div>
  <div class="stat"><b>{snapshot['generated_at'][:10]}</b><span>{L['st_shot']}</span></div>
</div>
<div class="chips">{chips}</div>
<h2>{L["hot"]}</h2>
<table>
  <thead><tr><th>#</th><th>{L['th_title']}</th><th>{L['th_source']}</th><th>Buzz</th></tr></thead>
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
                 feed_title=site["title"], lang=_lang(site), cta=_cta(site))


def page_topic(topic: str, pool: list[dict], site: dict, top_n: int) -> str:
    """pool — только то, что отрендерилось как /item/: список не может ссылаться
    на несуществующую страницу (аудитор qa за этим следит)."""
    L = _L(site)
    items = [i for i in pool if topic in i.get("topics", [])][:top_n]
    rows = "".join(_item_row(i + 1, it) for i, it in enumerate(items))
    body = f"""{_header(site)}
<div class="hero">
  <h1>#{_esc(topic)}</h1>
  <p>{L["topic_n"].format(n=len(items))}</p>
</div>
<table>
  <thead><tr><th>#</th><th>{L['th_title']}</th><th>{L['th_source']}</th><th>Buzz</th></tr></thead>
  <tbody>{rows}</tbody>
</table>
<div class="pager"><a href="/" style="color:#8fb7ff">{L['back_topics']}</a></div>
"""
    return _page(body, f"#{topic} — {site['title']}",
                 L["topic_meta"].format(topic=topic), site["base_url"],
                 f"topics/{topic}.html", feed_title=site["title"], lang=_lang(site), cta=_cta(site))


def page_topics_index(site: dict, topics: list[str], counts: dict) -> str:
    """Хаб всех тем колонии: навигация /topics/ раньше вела в пустоту, а это
    и внутренняя перелинковка, и карта тем для индексатора (ItemList)."""
    L = _L(site)
    rows = "".join(
        f'<tr><td><a href="/topics/{_esc(t)}.html">#{_esc(t)}</a></td>'
        f'<td>{counts.get(t, 0)}</td></tr>'
        for t in topics
    )
    body = f"""{_header(site)}
<div class="hero">
  <h1>{L["topics_h"]}</h1>
  <p>{L["topics_index_p"]}</p>
</div>
<table>
  <thead><tr><th>{L['th_topic']}</th><th>{L['th_count']}</th></tr></thead>
  <tbody>{rows}</tbody>
</table>
<div class="pager"><a href="/" style="color:#8fb7ff">{L['back_feed']}</a></div>
"""
    jsonld = json.dumps({
        "@context": "https://schema.org",
        "@type": "ItemList",
        "name": f"{site['title']} — {L['topics_h']}",
        "itemListElement": [
            {"@type": "ListItem", "position": i + 1, "url": f"{site['base_url']}/topics/{t}.html", "name": f"#{t}"}
            for i, t in enumerate(topics)
        ],
    }, ensure_ascii=False)
    return _page(body, f"{L['topics_h']} — {site['title']}",
                 L["topics_index_meta"], site["base_url"], "topics/",
                 jsonld, feed_title=site["title"], lang=_lang(site), cta=_cta(site))


def page_item(item: dict, site: dict, related: list[dict] | None = None) -> str:
    L = _L(site)
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
        related_block = (
            f'<h2>{L["related"]}</h2>'
            f'<div class="chips" style="margin-top:10px">{chips}</div>'
        )
    body = f"""{_header(site)}
<div class="hero">
  <h1>{_esc(item["title"])}</h1>
  <div class="meta">
    <span class="src">{_esc(SOURCE_LABELS.get(item["source"], item["source"]))}</span>
    · {_esc(item["date"])} · buzz <b class="buzz">{item['buzz']}</b>
    {f"· {L['pts'].format(p=item['points'], c=item['comments'])}" if item["comments"] or item["points"] else ""}
  </div>
  {f'<p style="margin-top:14px;color:#c2c9d8">{_esc(item["summary"])}</p>' if item["summary"] else ""}
  <p style="margin-top:18px"><a href="{_esc(item['url'])}" style="color:#8fb7ff">{L['read_source']}</a></p>
  <div class="chips" style="margin-top:18px">{tags}</div>
</div>
{related_block}
<div class="pager"><a href="/" style="color:#8fb7ff">{L['back_feed']}</a></div>
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
                 feed_title=site["title"], lang=_lang(site), cta=_cta(site))


def page_data(snapshot: dict, site: dict) -> str:
    L = _L(site)
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
  <h1>{L["data_h"]}</h1>
  <p>{L["data_p"]}</p>
</div>
<h2>{L["topics_h"]}</h2>
<table><thead><tr><th>{L['th_topic']}</th><th></th><th>{L['th_count']}</th></tr></thead>
<tbody>{topic_rows}</tbody></table>
<h2>{L["domains_h"]}</h2>
<table><thead><tr><th>{L['th_domain']}</th><th>{L['th_mentions']}</th></tr></thead>
<tbody>{dom_rows}</tbody></table>
"""
    return _page(body, L["data_title"].format(title=site["title"]),
                 L["data_desc"], site["base_url"], "data.html",
                 feed_title=site["title"], lang=_lang(site), cta=_cta(site))


def page_trends(site: dict, trends: list, live_topics: set | None = None) -> str:
    """Публичная грань дата-продукта Trend Index: что растёт, что падает.

    Ссылка на /topics/<t>.html — только для тем, живущих в текущем снимке:
    топики текут от тика к тику, и ссылка на «вчерашнюю» тему была бы мёртвой
    (ловится QA-проверкой внутренних ссылок).
    """
    L = _L(site)
    live = live_topics if live_topics is not None else set()
    rows = ""
    if not trends:
        rows = f'<p style="margin-top:14px;color:#9fb4d0">{L["trends_empty"]}</p>'
    else:
        body_rows = []
        for r in trends:
            topic = _esc(str(r.get("topic", "")))
            today = int(r.get("count", 0) or 0)
            prev = int(r.get("count_prev", 0) or 0)
            delta = today - prev
            arrow = "▲" if delta > 0 else ("▼" if delta < 0 else "→")
            color = "#7ee2a8" if delta > 0 else ("#ff9d9d" if delta < 0 else "#9fb4d0")
            bar = min(today, 60)  # ширина полосы — до 60 «квантов»
            name = (f'<a href="/topics/{_slug(topic)}.html">{topic}</a>'
                    if topic in live else topic)
            body_rows.append(
                f'<tr><td>{name}</td>'
                f'<td>{today} <span style="color:#5e7393">{prev}</span></td>'
                f'<td style="color:{color}">{arrow} {delta:+d}</td>'
                f'<td><span style="display:inline-block;height:10px;width:{bar * 5}px;'
                f'background:#2b5aa8;border-radius:3px"></span></td></tr>'
            )
        rows = (
            '<table class="r"><tr><th>' + L["th_topic"] + '</th><th>'
            + L["th_today"] + ' / ' + L["th_prev"] + '</th><th>' + L["th_delta"]
            + '</th><th></th></tr>' + "".join(body_rows) + '</table>'
        )
    body = f"""{_header(site)}
<div class="hero">
  <h1>{L["trends_h"]}</h1>
  <p style="margin-top:14px">{L["trends_p"]}</p>
  {rows}
</div>
"""
    return _page(body, L["trends_title"].format(title=site["title"]),
                 L["trends_desc"], site["base_url"], "trends.html",
                 feed_title=site["title"], lang=_lang(site), cta=_cta(site))


def page_about(site: dict) -> str:
    L = _L(site)
    body = f"""{_header(site)}
<div class="hero">
  <h1>{L["about_h"]}</h1>
  <p style="margin-top:14px">{L["about_p1"].format(title=_esc(site["title"]))}</p>
  <p style="margin-top:12px">{L["about_p2"]}</p>
  <p style="margin-top:12px">{L["contact"]} <a href="{_esc(site.get('contact', site['base_url']))}" style="color:#8fb7ff">{_esc(site.get('contact', site['base_url']))}</a></p>
</div>
"""
    return _page(body, L["about_title"].format(title=site["title"]),
                 L["about_desc"], site["base_url"], "about.html",
                 feed_title=site["title"], lang=_lang(site), cta=_cta(site))


# ---------------------------------------------------------------- RSS колонии
def page_404(site: dict) -> str:
    L = _L(site)
    body = f"""{_header(site)}
<div class="hero">
  <h1>{L["404_h"]}</h1>
  <p style="margin-top:14px">{L["404_p"]}</p>
  <p style="margin-top:18px"><a href="/" style="color:#8fb7ff">{L['back_feed']}</a></p>
</div>
"""
    return _page(body, L["404_title"].format(title=site["title"]),
                 L["404_desc"], site["base_url"], "",
                 feed_title=site["title"], lang=_lang(site), cta=_cta(site))


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
        f"    <language>{_lang(site)}</language>\n"
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
def generate(snapshot: dict, outdir: str | Path, config: dict,
             trends: list | None = None) -> dict:
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

    # Хаб тем: навигация /topics/ обзаводится реальной страницей (и ItemList
    # для поисковиков). Счётчики — из текущего снимка, мёртвых ссылок нет:
    # каждая тема из topics отрендерена выше.
    (outdir / "topics" / "index.html").write_text(
        page_topics_index(site, topics, snapshot["totals"].get("by_topic", {})),
        encoding="utf-8",
    )
    urls.append("topics/")

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
    # Trend Index — публичная грань дата-продукта (данные предыдущего тика:
    # apothecary печёт trend_index.csv после сайтогенерации). Топики текут,
    # поэтому передаём множество живых тем — мёртвых ссылок быть не должно.
    (outdir / "trends.html").write_text(page_trends(site, trends or [],
                                                    live_topics=topics),
                                        encoding="utf-8")
    (outdir / "about.html").write_text(page_about(site), encoding="utf-8")
    # 404 — в sitemap её не кладём (поисковики не любят), CF Pages подхватит
    # файл сам как fallback для несуществующих путей.
    (outdir / "404.html").write_text(page_404(site), encoding="utf-8")
    generate_feed(snapshot, outdir, config)
    urls += ["data.html", "trends.html", "about.html", "feed.xml"]

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
