"""Самопроверка роя — гоняется без сети за ~1 секунду.

CI (см. .github/workflows/hive-tick.yml) запускает selftest перед каждым циклом:
если сломалось ядро — пульс даже не начинается, а ответственный человек получает
красный крестик вместо молчаливой смерти колонии.

Локально: python archaea/selftest.py
"""
from __future__ import annotations

import json
import sys
import tempfile
import time
import urllib.robotparser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from archaea import qa
from colonies.phosphor import pipeline
from core.orchestrator import Orchestrator
from core.registry import Registry
from core.treasury import Treasury

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, cond, note: str = ""):
    RESULTS.append((name, bool(cond), str(note)))


# ---------------------------------------------------------------- pipeline
def test_clean_dedup():
    now = time.time()
    items = [
        {"uid": "a", "title": "Some Big Launch", "url": "https://x.com/1", "ts": now,
         "points": 10, "comments": 0, "source": "hn"},
        {"uid": "b", "title": "some! big  launch", "url": "https://x.com/2", "ts": now,
         "points": 500, "comments": 20, "source": "hn"},
    ]
    out = pipeline.clean(items)
    check("clean: дедуп по нормализованному заголовку (2→1)", len(out) == 1, len(out))
    check("clean: выживает сильнейший", out and out[0]["uid"] == "b",
          out[0]["uid"] if out else "none")


def test_score_and_tags():
    now = time.time()
    it = {"uid": "c", "title": "New open-source LLM beats GPT on RAG benchmark",
          "url": "https://x.com", "ts": now, "points": 100, "comments": 20, "source": "hn"}
    out = pipeline.clean([it])
    check("tag: ai-тег ставится", "ai" in out[0]["topics"], out[0]["topics"])
    check("score: buzz ≥ points + 3×comments", out and out[0]["buzz"] >= 160, out[0]["buzz"])
    check("score: свежесть даёт надбавку",
          out and out[0]["buzz"] >= 160 + 30, out[0]["buzz"])


def test_snapshot():
    now = time.time()
    items = [{"uid": "d", "title": "X", "url": "https://example.com/a", "ts": now,
              "points": 1, "comments": 1, "source": "hn", "recipe": "show_hn",
              "topics": ["ai"], "buzz": 5, "date": "2026-01-01"}]
    snap = pipeline.build_snapshot(items, [{"kind": "hn_search"}])
    check("snapshot: totals считаются", snap["totals"]["items"] == 1)
    check("snapshot: by_recipe считается", snap["totals"]["by_recipe"].get("show_hn") == 1,
          snap["totals"]["by_recipe"])


# ---------------------------------------------------------------- rss + guard
def test_rss_parse():
    from colonies.phosphor import sources as S

    rss = (
        '<?xml version="1.0"?><rss version="2.0"><channel><title>X</title>'
        "<item><title>Alpha launch</title><link>https://a.example/1</link>"
        "<pubDate>Wed, 21 Oct 2026 10:00:00 GMT</pubDate>"
        "<description>Big news about AI agents</description>"
        "<dc:creator xmlns:dc=\"http://purl.org/dc/elements/1.1/\">jane</dc:creator>"
        "</item></channel></rss>"
    )
    items = S._parse_feed(rss)
    check("rss: парсит RSS 2.0", len(items) == 1 and items[0]["title"] == "Alpha launch",
          [i.get("title") for i in items])
    check("rss: uid стабильного формата", items and items[0]["uid"].startswith("rss:"),
          items[0]["uid"] if items else "none")
    check("rss: author+description приехали",
          items and items[0]["author"] == "jane" and "AI agents" in items[0]["summary"])

    atom = (
        '<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><entry>'
        "<title>Beta paper</title><link href='https://b.example/2' rel='alternate'/>"
        "<updated>2026-10-21T10:00:00Z</updated><summary>Quantum thing</summary>"
        "</entry></feed>"
    )
    items = S._parse_feed(atom)
    check("rss: парсит Atom", len(items) == 1 and items[0]["title"] == "Beta paper",
          [i.get("title") for i in items])
    check("rss: битый XML даёт []", S._parse_feed("<not<xml") == [])


def test_robots_guard():
    from colonies.phosphor import sources as S

    rp = urllib.robotparser.RobotFileParser()
    rp.parse(["User-agent: *", "Disallow: /private"])
    S._ROBOTS_CACHE["https://example.com"] = rp
    check("robots: запрещает /private", S._robots_allowed("https://example.com/private/feed") is False)
    check("robots: разрешает публичное", S._robots_allowed("https://example.com/feed") is True)
    S._ROBOTS_CACHE["https://gone.example"] = None
    check("robots: нет файла → разрешаем", S._robots_allowed("https://gone.example/feed") is True)


def test_pii_scrub():
    from colonies.phosphor.pipeline import scrub_pii

    t = "Write to ceo@evilcorp.com or call +1 (415) 555 0132, card 4111111111111111 today"
    s = scrub_pii(t)
    check("pii: email вычищен", "@" not in s and "[email]" in s, s)
    check("pii: телефон вычищен", "555 0132" not in s and "[phone]" in s, s)
    check("pii: карта вычищена", "4111" not in s, s)
    check("pii: чистый текст не калечится", scrub_pii("AI agents everywhere") == "AI agents everywhere")
    check("pii: None не роняет", scrub_pii(None) == "")


# ---------------------------------------------------------------- apothecary + feed
def test_apothecary():
    from colonies import apothecary

    tmp = Path(tempfile.mkdtemp())
    (tmp / "history.jsonl").write_text(
        json.dumps({"ts": 1, "colony": "x", "items": 3,
                    "by_topic": {"ai": 5, "dev": 2}}) + "\n",
        encoding="utf-8",
    )
    items = [
        {"uid": "a", "source": "hn", "title": "A", "url": "https://x/1", "buzz": 5,
         "date": "2026-10-24", "topics": ["ai"]},
        {"uid": "c1", "source": "cve", "title": "CVE-2026-1: Boom", "url": "https://g/1",
         "buzz": 900, "date": "2026-10-24", "topics": ["security"], "author": "pkg-x",
         "summary": "Severity: critical. Remote code execution"},
    ]
    snap = {"generated_at": "2026-10-24T00:00:00+00:00",
            "totals": {"by_topic": {"ai": 9, "dev": 2}, "items": 5}, "items": items}

    out = apothecary.bake(snap, "x", tmp)
    check("apothecary: продукты испеклись",
          {"digest_top.csv", "trend_index.csv", "cve_digest.csv"} <= set(out["products"]),
          list(out["products"]))

    trend = (Path(out["outdir"]) / "trend_index.csv").read_text(encoding="utf-8")
    check("trend: дельта к прошлому тику посчитана",
          ",ai,9,5,4" in trend.replace("\r", ""), trend.replace("\n", " | "))

    cve = (Path(out["outdir"]) / "cve_digest.csv").read_text(encoding="utf-8")
    check("apothecary: CVE распарсен (id/severity/package)",
          "CVE-2026-1" in cve and "critical" in cve and "pkg-x" in cve, cve[:120])

    snap2 = dict(snap)
    snap2["items"] = items[:1]
    out2 = apothecary.bake(snap2, "x", tmp)
    check("apothecary: нет CVE → нет cve_digest", "cve_digest.csv" not in out2["products"],
          list(out2["products"]))


def test_feed_roundtrip():
    """Колония излучает RSS — и мы же его парсим собственным парсером (dogfooding)."""
    from colonies.phosphor import sitegen
    from colonies.phosphor import sources as S

    cfg = {"site": {"title": "T", "tagline": "TT", "base_url": "https://t.example"},
           "top_items_home": 5}
    snap = {"items": [
        {"title": "One <b>html</b>", "ts": time.time(), "summary": "Sum & more", "topics": ["ai"]},
        {"title": "Two", "ts": time.time(), "summary": "", "topics": []},
    ]}
    tmp = Path(tempfile.mkdtemp())
    path = sitegen.generate_feed(snap, tmp, cfg)
    raw = Path(path).read_text(encoding="utf-8")
    parsed = S._parse_feed(raw)
    check("feed: парсится нашим же RSS-парсером", len(parsed) == 2, len(parsed))
    check("feed: ссылки ведут на наши страницы",
          parsed[0]["url"].startswith("https://t.example/item/"), parsed[0]["url"])
    check("feed: XML-экранирование", "&lt;b&gt;" in raw and "&amp;" in raw)


# ---------------------------------------------------------------- полный рендер
def test_sitegen_render():
    """Весь сайтgen целиком — ловит регрессии, которые точечные тесты пропускают
    (такие, как NameError 'site' в _page, сломавший тик v0.3)."""
    from colonies.phosphor import sitegen

    cfg = {
        "site": {"title": "Test", "tagline": "T-колония", "base_url": "https://t.example"},
        "topics": [],  # намеренно пусто: topic-страницы должны родиться из данных
        "top_items_home": 3,
        "top_item_pages": 5,
    }
    items = [
        {"uid": "a", "source": "hn", "title": "Alpha (topic)", "url": "https://x/1",
         "buzz": 5, "date": "2026-10-24", "ts": time.time(), "points": 1,
         "comments": 0, "topics": ["ai"], "summary": "text"},
        {"uid": "b", "source": "cve", "title": "CVE-9: Beta", "url": "https://g/2",
         "buzz": 9, "date": "2026-10-24", "ts": time.time(), "points": 0,
         "comments": 0, "topics": ["ai"], "summary": "Severity: high. boom"},
    ]
    snap = {
        "generated_at": "2026-10-24T00:00:00+00:00",
        "totals": {"items": 2, "by_source": {"hn": 1, "cve": 1}, "by_topic": {"ai": 2},
                   "top_domains": [("x", 1)], "recipes": {}},
        "items": [
            {"uid": "a", "source": "hn", "title": "Alpha (topic)", "url": "https://x/1",
             "buzz": 5, "date": "2026-10-24", "ts": time.time(), "points": 1,
             "comments": 0, "topics": ["ai"], "summary": "text"},
            {"uid": "b", "source": "cve", "title": "CVE-9: Beta", "url": "https://g/2",
             "buzz": 9, "date": "2026-10-24", "ts": time.time(), "points": 0,
             "comments": 0, "topics": ["ai"], "summary": "Severity: high. boom"},
        ],
    }
    tmp = Path(tempfile.mkdtemp())
    trends = [{"topic": "ai", "count": 7, "count_prev": 3},
              {"topic": "dev", "count": 2, "count_prev": 2}]
    out = sitegen.generate(snap, tmp, cfg, trends=trends)
    root = Path(out["outdir"])

    idx = (root / "index.html").read_text(encoding="utf-8")
    check("sitegen: сайт собрался", out["pages"] > 0 and "Alpha" in idx)
    check("sitegen: feed.xml существует", (root / "feed.xml").exists())
    check("sitegen: rel=alternate в head", 'type="application/rss+xml"' in idx)
    check("sitegen: sitemap включает feed", "feed.xml" in (root / "sitemap.xml").read_text(encoding="utf-8"))
    check("sitegen: topic из данных (union) отрендерен",
          (root / "topics" / "ai.html").exists()
          and "topics/ai.html" in (root / "sitemap.xml").read_text(encoding="utf-8"))
    check("sitegen: og/twitter-теги есть",
          'property="og:title"' in idx and 'name="twitter:card"' in idx)
    check("sitegen: og:type website на морде", 'content="website"' in idx)
    check("sitegen: 404.html есть", (root / "404.html").exists())
    tr_html = (root / "trends.html").read_text(encoding="utf-8")
    check("sitegen: trends.html есть и в sitemap",
          (root / "trends.html").exists()
          and "trends.html" in (root / "sitemap.xml").read_text(encoding="utf-8"))
    check("sitegen: бары и дельты трендов",
          "▲ +4" in tr_html and "→ +0" in tr_html and "/topics/ai.html" in tr_html)
    # «вчерашняя» тема (dev) не из текущего снимка — должна быть без ссылки:
    # мёртвых ссылок на trends-странице не бывает (QA поймал бы)
    check("sitegen: мёртвых ссылок трендов нет",
          ">dev</td>" in tr_html and "topics/dev.html" not in tr_html)

    item = root / "item" / "alpha-topic.html"
    check("sitegen: страница item'а есть", item.exists())
    if item.exists():
        txt = item.read_text(encoding="utf-8")
        check("sitegen: блок 'Ещё по теме'", "Ещё по теме" in txt)
        check("sitegen: Article JSON-LD", '"@type": "Article"' in txt)

    # EN-локаль: та же кодовая база, другой языковой рынок (programmatic SEO)
    import copy
    cfg_en = copy.deepcopy(cfg)
    cfg_en["site"]["lang"] = "en"
    out_en = sitegen.generate(snap, tmp / "dist_en", cfg_en, trends=trends)
    en_root = Path(out_en["outdir"])
    idx_en = (en_root / "index.html").read_text(encoding="utf-8")
    check("sitegen: EN — lang атрибут", '<html lang="en">' in idx_en)
    topic_en = (en_root / "topics" / "ai.html").read_text(encoding="utf-8")
    check("sitegen: EN-копии на месте",
          "Trending now" in idx_en and "Topic ai: fresh posts" in topic_en)
    item_en = (en_root / "item" / "alpha-topic.html").read_text(encoding="utf-8")
    check("sitegen: EN item-страница", "Read the source →" in item_en and "More on the topic" in item_en)
    check("sitegen: og:type article на item-странице", 'content="article"' in item_en)
    check("sitegen: EN и RU не смешиваются", "Что вспыхнуло" not in idx_en and "к ленте" not in item_en)
    feed_en = (en_root / "feed.xml").read_text(encoding="utf-8")
    check("sitegen: EN feed language", "<language>en</language>" in feed_en)
    qa_en = qa.audit_site(en_root, base_url="https://t.example")
    check("sitegen: EN-сайт проходит QA", qa_en["errors"] == 0, qa.summarize(qa_en))
    tr_en = (en_root / "trends.html").read_text(encoding="utf-8")
    check("sitegen: EN trends.html", "Trend Index — what is growing" in tr_en
          and "▲ +4" in tr_en)


# ---------------------------------------------------------------- монетизация
def test_monetization_cta():
    """CTA-блок: рендерится только когда в config есть monetization-рельсы.
    Пустая конфигурация (нынешнее состояние всех колоний) — сайт не меняется."""
    import copy
    from colonies.phosphor import sitegen

    cfg = {
        "site": {"title": "T", "tagline": "T", "base_url": "https://t.example"},
        "topics": [], "top_items_home": 2, "top_item_pages": 3,
    }
    snap = {
        "generated_at": "2026-10-24T00:00:00+00:00",
        "totals": {"items": 1, "by_source": {"hn": 1}, "by_topic": {"ai": 1},
                   "top_domains": [("x", 1)], "recipes": {}},
        "items": [{"uid": "a", "source": "hn", "title": "Alpha", "url": "https://x/1",
                   "buzz": 5, "date": "2026-10-24", "ts": time.time(), "points": 1,
                   "comments": 0, "topics": ["ai"], "summary": "text"}],
    }
    tmp = Path(tempfile.mkdtemp())
    out = sitegen.generate(snap, tmp / "dist", cfg)
    html_off = (Path(out["outdir"]) / "index.html").read_text(encoding="utf-8")
    check("mon: без рельсов блока нет", "class=\"cta\"" not in html_off)

    cfg_on = copy.deepcopy(cfg)
    cfg_on["site"]["monetization"] = {
        "support_url": "https://ko-fi.example/atria",
        "products_url": "https://gumroad.example/dataset",
    }
    out_on = sitegen.generate(snap, tmp / "dist_on", cfg_on)
    html_on = (Path(out_on["outdir"]) / "index.html").read_text(encoding="utf-8")
    check("mon: блок есть с рельсами", "class=\"cta\"" in html_on
          and "ko-fi.example/atria" in html_on)
    check("mon: обе кнопки", "Купить полный датасет" in html_on
          and "Поддержать улей" in html_on)
    qa_r = qa.audit_site(Path(out_on["outdir"]), base_url="https://t.example")
    check("mon: QA чистый с CTA", qa_r["errors"] == 0, qa.summarize(qa_r))

    cfg_en = copy.deepcopy(cfg_on)
    cfg_en["site"]["lang"] = "en"
    out_en = sitegen.generate(snap, tmp / "dist_en", cfg_en)
    html_en = (Path(out_en["outdir"]) / "index.html").read_text(encoding="utf-8")
    check("mon: EN-копии кнопок", "Support the hive" in html_en
          and "Buy the full dataset" in html_en)

    # Крипто-рельс: приём на self-custody (TON/USDT), работает из РФ
    cfg_c = copy.deepcopy(cfg)
    cfg_c["site"]["monetization"] = {"crypto": [
        {"net": "TON", "address": "UQBTNAxe01NQlKdF_test"},
        {"net": "USDT (BEP-20)", "address": "0xd4934a0935281c_test"},
    ]}
    out_c = sitegen.generate(snap, tmp / "dist_c", cfg_c)
    html_c = (Path(out_c["outdir"]) / "index.html").read_text(encoding="utf-8")
    check("mon: крипто-блок рендерится", "UQBTNAxe01NQlKdF_test" in html_c
          and "USDT (BEP-20)" in html_c)
    check("mon: мёртвый крипто-рельс не рендерится",
          sitegen._cta({"monetization": {"crypto": [{"net": "", "address": ""}]}}) == "")
    qa_c = qa.audit_site(Path(out_c["outdir"]), base_url="https://t.example")
    check("mon: QA чистый с крипто-CTA", qa_c["errors"] == 0, qa.summarize(qa_c))

    # Stars-рельс: постоянный инвойс Pro, деньги собирает сам Telegram
    cfg_s = copy.deepcopy(cfg)
    cfg_s["site"]["monetization"] = {
        "stars": "https://t.me/$DbtftXcaIUuMFwAAyr9kmgrgww0"}
    out_s = sitegen.generate(snap, tmp / "dist_s", cfg_s)
    html_s = (Path(out_s["outdir"]) / "index.html").read_text(encoding="utf-8")
    check("mon: Stars-CTA рендерится",
          "$DbtftXcaIUuMFwAAyr9kmgrgww0" in html_s and "Pro" in html_s)
    check("mon: мёртвый stars-рельс не рендерится",
          sitegen._cta({"monetization": {"stars": ""}}) == "")

    # Cross-links: 9 соседних колоний, себя не повторяем
    sl = sitegen._sister_links({"base_url": "https://tenderslice.pages.dev",
                                "lang": "ru"})
    n = sl.count("<a href=")
    check("sisters: ~9 соседок в футере", 7 <= n <= 10, f"{n} links")
    check("sisters: себя нет", "tenderslice.pages.dev" not in sl)
    check("sisters: EN-лейбл", "Other verticals" in
          sitegen._sister_links({"base_url": "https://t.example", "lang": "en"}))

    # Бейдж срока тендера: открыт/закрыт/непарсится
    L = sitegen.COPY["ru"]
    b_open = sitegen._closes_badge({"closes": "9 Nov 2099, 05:00 UTC"}, L)
    b_closed = sitegen._closes_badge({"closes": "9 Nov 2020, 05:00 UTC"}, L)
    b_raw = sitegen._closes_badge({"closes": "скоро"}, L)
    b_none = sitegen._closes_badge({}, L)
    check("tender: бейдж открытого", "Приём заявок до" in b_open, b_open)
    check("tender: бейдж закрытого", "закрыт" in b_closed, b_closed)
    check("tender: непарсимый — как есть", "скоро" in b_raw, b_raw)
    check("tender: нет поля — нет бейджа", b_none == "")

    # Pro-лендинг: рендерится только при Stars-рельсе, цена и кнопка — из конфига
    st = {"title": "T", "tagline": "T", "base_url": "https://t.example",
          "lang": "ru",
          "monetization": {"stars": "https://t.me/$INV123",
                           "crypto": [{"net": "TON", "address": "UQ…"}]}}
    pro = sitegen.page_pro(st)
    check("pro: лендинг есть с Stars", "199 ₽" in pro and "$INV123" in pro, pro[:80])
    check("pro: фичи и кнопка оплаты", "top-20" in pro
          and "Telegram Stars" in pro)
    check("pro: бот не торчит, если не задан", "t.me/dimon" not in pro)
    check("pro: без рельсы — пусто", sitegen.page_pro(
        {"title": "T", "base_url": "https://t.example",
         "monetization": {}}) == "")
    # в sitemap pro.html только при рельсе (проверяем через generate)
    out_p = sitegen.generate(snap, tmp / "dist_p",
                             {"site": st, "topics": [], "top_items_home": 2,
                              "top_item_pages": 3})
    html_p = (Path(out_p["outdir"]) / "pro.html").read_text(encoding="utf-8")
    sm = (Path(out_p["outdir"]) / "sitemap.xml").read_text(encoding="utf-8")
    check("pro: страница в sitemap", "/pro.html" in sm)
    check("pro: nav ведёт на /pro.html", 'href="/pro.html"' in html_p)
    qa_p = qa.audit_site(Path(out_p["outdir"]), base_url="https://t.example")
    check("pro: QA чистый", qa_p["errors"] == 0, qa.summarize(qa_p))

    # CF Web Analytics маяк: рендерится iff конфиг несёт cf_beacon
    from colonies.phosphor import sitegen as _sg
    st_b = {"title": "T", "tagline": "T", "base_url": "https://t.example",
            "lang": "ru", "cf_beacon": "BEEFTOKEN123", "monetization": {}}
    out_b = _sg.generate(snap, tmp / "dist_b",
                         {"site": st_b, "topics": [], "top_items_home": 2,
                          "top_item_pages": 3})
    h_b = (Path(out_b["outdir"]) / "index.html").read_text(encoding="utf-8")
    check("beacon: имя маяка в странице", "BEEFTOKEN123" in h_b
          and "beacon.min.js" in h_b)
    out_nb = _sg.generate(snap, tmp / "dist_nb",
                          {"site": {"title": "T", "tagline": "T",
                                    "base_url": "https://t.example",
                                    "lang": "ru", "monetization": {}},
                           "topics": [], "top_items_home": 2, "top_item_pages": 3})
    h_nb = (Path(out_nb["outdir"]) / "index.html").read_text(encoding="utf-8")
    check("beacon: без токена — zero-JS", "beacon.min.js" not in h_nb
          and "<script defer" not in h_nb)


# ------------------------------------------------------- Накопитель предметов
def test_archive():
    """archive_items: каталог растёт, дедуп по uid, FIFO-срез, порядок по ts."""
    from archaea import genesis

    tmp = Path(tempfile.mkdtemp())
    p = tmp / "storage" / "x" / "archive.jsonl"
    snap = {"items": [
        {"uid": "a1", "title": "A1", "ts": 100, "url": "https://x/1"},
        {"uid": "a2", "title": "A2", "ts": 200, "url": "https://x/2"},
    ]}
    m1 = genesis.archive_items(snap, p)
    check("arch: первый тик — 2 предмета", len(m1) == 2 and p.exists(), len(m1))
    # второй тик: один старый + один новый
    snap2 = {"items": [
        {"uid": "a2", "title": "A2 new", "ts": 300, "url": "https://x/2"},
        {"uid": "a3", "title": "A3", "ts": 250, "url": "https://x/3"},
    ]}
    m2 = genesis.archive_items(snap2, p)
    check("arch: дедип и мерж — 3 уникальных", [i["uid"] for i in m2] == ["a2", "a3", "a1"],
          [i["uid"] for i in m2])
    check("arch: свежая версия перетирает", m2[0]["title"] == "A2 new")
    # cap: архив обрезается по FIFO
    big = {"items": [{"uid": f"b{i}", "title": f"B{i}", "ts": 1000 + i,
                      "url": f"https://x/{i}"} for i in range(10)]}
    p2 = tmp / "storage" / "y" / "archive.jsonl"
    genesis.archive_items(big, p2, cap=5)
    m3 = genesis.archive_items({"items": []}, p2, cap=5)
    check("arch: cap 5 режет до 5", len(m3) == 5, len(m3))
    # нет файла — не падает, возвращает свежие и создаёт архив
    p3 = tmp / "nope" / "archive.jsonl"
    m4 = genesis.archive_items(snap, p3)
    check("arch: нет файла — отдаёт свежие", len(m4) == 2 and p3.exists(), len(m4))


# ---------------------------------------------------------------- IndexNow
def test_pings():
    """Заявки на индексацию (Bing/Yandex/Seznam) — открытый протокол, ключ-файл."""
    from archaea import pings

    class R:
        def __init__(self, s):
            self.status = s

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    orig = pings.urllib.request.urlopen
    seen = {}

    def fake(req, timeout=30):
        import json as _j
        seen["body"] = _j.loads(req.data.decode())
        return R(202)

    pings.urllib.request.urlopen = fake
    ok, note = pings.submit("https://t.example", "abc123",
                            ["https://t.example/", "https://t.example/x.html"])
    # чужой url отбрасывается
    _, _ = pings.submit("https://t.example", "abc123",
                        ["https://other.example/x.html"])
    pings.urllib.request.urlopen = orig
    check("ping: 202 = принято", ok and "202" in note, note)
    check("ping: host+keyLocation в теле",
          seen["body"]["host"] == "t.example"
          and seen["body"]["keyLocation"] == "https://t.example/key.txt"
          and seen["body"]["key"] == "abc123", seen.get("body"))
    check("ping: ключ детерминирован",
          pings.gen_key("x") == pings.gen_key("x")
          and len(pings.gen_key("x")) == 32)


# ---------------------------------------------------------------- TG-доставка
def test_tgpost():
    """Бот: формат дайджеста + подписчики (всё офлайн, сеть подменена)."""
    from core import tgpost

    snap = {
        "generated_at": "2026-10-30T12:00:00+00:00",
        "totals": {"items": 42},
        "items": [
            {"title": "Alpha <b>тег</b>", "url": "https://x/1",
             "source": "hn", "buzz": 7},
            {"title": "Beta", "url": "https://x/2", "source": "rss", "buzz": 3},
        ],
    }
    txt = tgpost.format_digest(snap, top_n=2)
    check("tg: дайджест рендерится", "42" in txt and "записей" in txt
          and "Alpha" in txt)
    check("tg: HTML-экранирование", "&lt;b&gt;тег&lt;/b&gt;" in txt)
    txt_en = tgpost.format_digest(snap, top_n=1, lang="en")
    check("tg: EN-копии", "Fresh snapshot" in txt_en and "items" in txt_en)
    check("tg: обрезка top_n", "Beta" not in txt_en)

    # pitch Pro: только бесплатным, экранируется, EN-вариант
    inv = "https://t.me/$DbtftXcaIUuMFwAAyr9kmgrgww0"
    txt_pitch = tgpost.format_digest(snap, top_n=2, pro_link=inv)
    check("tg: pitch Pro в дайджесте", "Атрия Pro" in txt_pitch and inv in txt_pitch)
    check("tg: pitch EN", "Atria Pro" in tgpost.format_digest(
        snap, top_n=1, lang="en", pro_link=inv))
    check("tg: нет pitch без ссылки",
          "Pro" not in tgpost.format_digest(snap, top_n=2))

    # подписчики: сеть подмена (_api), токен есть — JSON-state модель
    calls = []

    def fake_api(token, method, payload):
        calls.append((method, payload))
        if method == "getUpdates":
            return {"ok": True, "result": [
                {"update_id": 100,
                 "message": {"chat": {"id": 123}, "text": "/start"}},
                {"update_id": 101,
                 "message": {"chat": {"id": 456}, "text": "hello"}},
                {"update_id": 102,
                 "message": {"chat": {"id": 123}, "text": "/stop"}},
                {"update_id": 103,
                 "message": {"chat": {"id": 456},
                             "successful_payment": {
                                 "payload": '{"product":"atria_pro_month","days":31}'}}},
                {"update_id": 104,
                 "message": {"chat": {"id": 123}, "text": "/help"}},
            ]}
        if method == "createInvoiceLink":
            return {"ok": True, "result": "https://t.me/invoice/fake"}
        return {"ok": True, "result": {"message_id": 1}}

    import os as _os
    orig_api = tgpost._api
    orig_save = tgpost.save_subs
    tgpost._api = fake_api
    tgpost.save_subs = lambda state: True
    _os.environ["TG_BOT_TOKEN"] = "fake:test"
    state = {"chats": {}, "offset": 0}
    n = tgpost.process_updates("fake:test", state)
    check("tg: 5 апдейтов обработаны", n == 5, n)
    # 123 подписался и отписался, 456 оплатил Pro
    chats = state["chats"]
    check("tg: 123 отпал, 456 остался Pro",
          "123" not in chats and "456" in chats, sorted(chats))
    check("tg: Pro-подписка до > now",
          float(chats.get("456", {}).get("until", 0)) > time.time())
    check("tg: offset подтверждён", state["offset"] == 105, state["offset"])
    help_texts = [p.get("text", "") for m, p in calls
                  if m == "sendMessage" and "автономный мониторинг" in p.get("text", "")]
    check("tg: /help отвечает командами",
          any("/start" in t and "/pro" in t for t in help_texts))
    check("tg: /pro создаёт постоянный инвойс",
          (tgpost.ensure_invoice("fake:test", state)
           == "https://t.me/invoice/fake"
           and state["invoice_url"] == "https://t.me/invoice/fake"),
          state.get("invoice_url"))

    # бот_тик: рассылка с Pro (top-20) и без (top-5)
    def api2(token, method, payload):
        if method == "getUpdates":
            return {"ok": True, "result": []}
        if method == "sendMessage":
            sent2.append((payload["chat_id"], payload["text"]))
            return {"ok": True}
        return {"ok": True}

    sent2 = []
    tgpost._api = api2
    big = {"totals": {"items": 42},
           "items": [{"title": f"item{i}", "url": f"https://x/{i}",
                      "source": "s", "buzz": 1} for i in range(30)]}
    stats = tgpost.bot_tick([big], subs={"chats": chats, "offset": 104})
    pro_txt = [t for c, t in sent2 if c == 456][0]
    free_txt = [t for c, t in sent2 if c == 123]
    check("tg: бот_тик Pro = top-20", pro_txt.count("\n") >= 10, stats)
    check("tg: бот_тик свежие неподписанные не летят", free_txt == [], sent2)
    tgpost._api = orig_api
    tgpost.save_subs = orig_save
    _os.environ.pop("TG_BOT_TOKEN", None)


# ---------------------------------------------------------------- html_list
def test_html_list():
    """Парсер HTML-каталога (агрегаторы без RSS — например FreeTender 44-ФЗ)."""
    from colonies.phosphor import sources

    html_page = (
        '<html><body>'
        '<a href="/tender/tender-0354100010626000313">Поставка лекарственного '
        'препарата ЭСЦИТАЛОПРАМ</a>'
        '<a href="https://freetender.net/tender/xyz">Ремонт авто</a>'
        '<a href="/about">О сервисе</a>'
        '<a href="/tender/short">коротко</a>'
        '<a href="/tender/dupe">Дубль</a>'
        '<a href="/tender/dupe">Дубль</a>'
        '</body></html>')
    orig_get = sources._get
    sources._get = lambda url, headers=None, timeout=40: html_page
    orig_robots = sources._robots_allowed
    sources._robots_allowed = lambda url: True
    items = sources.fetch_html_list("https://freetender.net/tenders/russia")
    sources._get = orig_get
    sources._robots_allowed = orig_robots
    check("html: 2 записи (фильтр паттерна+длина)", len(items) == 2, len(items))
    check("html: абсолютный url", items and items[0]["url"].startswith("http"),
          items[0]["url"] if items else "-")
    check("html: относительный url достроен",
          items and "/tender/short" not in [i["url"] for i in items])


    # ---- обогащение деталей + микро-срез (43-ФЗ ниша: до 300к)
    detail = (
        '<html><body>'
        '<div><dt class="eyebrow">Value</dt><dd>RUB 806,120</dd></div>'
        '<div><dt class="eyebrow">Location</dt><dd>Орловская область</dd></div>'
        '</body></html>')
    calls = {"list": False, "detail": 0}

    def fake_get(url, headers=None, timeout=40):
        if "/tender/" in url and "russia" not in url:
            calls["detail"] += 1
            return detail
        calls["list"] = True
        return html_page

    sources._get = fake_get
    sources._robots_allowed = lambda url: True
    fields = [
        {"name": "sum", "re": r"VALUE\s*\n?\s*RUB\s*([\d,]+)"},
        {"name": "region", "re": r"Location\s*\n+\s*([^\n]+)"},
    ]
    rich = sources.fetch_html_list(
        "https://freetender.net/tenders/russia", fields=fields,
        filters={"sum_max": 300000})
    allf = sources.fetch_html_list(
        "https://freetender.net/tenders/russia", fields=fields)
    small = sources.fetch_html_list(
        "https://freetender.net/tenders/russia", fields=fields,
        filters={"sum_max": 1000000})
    sources._get = orig_get
    sources._robots_allowed = orig_robots
    check("html: поля детали извлечены",
          allf and allf[0].get("sum") == "806,120", allf[0] if allf else "-")
    check("html: summit-фильтр 806к > 300к → 0",
          len(rich) == 0, len(rich))
    check("html: фильтр 806к <= 1м → проходит", len(small) == 2, len(small))
    check("html: детали запросились (3 прохода)",
          calls["detail"] == 6, calls["detail"])


# ---------------------------------------------------------------- QA-ген
def test_qa_clean():
    """Чистый сайт: 0 ошибок (используем рендер sitegen из test_sitegen_render)."""
    from colonies.phosphor import sitegen

    cfg = {
        "site": {"title": "T", "tagline": "T", "base_url": "https://t.example",
                 "contact": "https://t.example"},
        "topics": ["ai"], "top_items_home": 2, "top_item_pages": 3,
    }
    snap = {
        "generated_at": "2026-10-24T00:00:00+00:00",
        "totals": {"items": 2, "by_source": {"hn": 2}, "by_topic": {"ai": 2},
                   "top_domains": [("x", 1)], "recipes": {}},
        "items": [
            {"uid": "a", "source": "hn", "title": "Alpha one", "url": "https://x/1",
             "buzz": 5, "date": "2026-10-24", "ts": time.time(), "points": 1,
             "comments": 0, "topics": ["ai"], "summary": "s"},
            {"uid": "b", "source": "hn", "title": "Beta two", "url": "https://x/2",
             "buzz": 3, "date": "2026-10-24", "ts": time.time(), "points": 0,
             "comments": 1, "topics": ["ai"], "summary": "s"},
        ],
    }
    tmp = Path(tempfile.mkdtemp())
    out = sitegen.generate(snap, tmp / "dist", cfg)
    r = qa.audit_site(out["outdir"], base_url="https://t.example")
    check("qa: чистый сайт → 0 ошибок", r["errors"] == 0, qa.summarize(r))

    # отравляем: мёртвая внутренняя ссылка
    idx = tmp / "dist" / "index.html"
    idx.write_text(
        idx.read_text(encoding="utf-8").replace("</body>",
                                                '<a href="/item/ghost.html">x</a></body>'),
        encoding="utf-8",
    )
    r2 = qa.audit_site(tmp / "dist", base_url="https://t.example")
    check("qa: ловит мёртвую ссылку", r2["errors"] >= 1, qa.summarize(r2))

    # отравляем: битый JSON-LD
    idx.write_text(
        idx.read_text(encoding="utf-8").replace('"@type": "WebSite"', '"@type" "WebSite"'),
        encoding="utf-8",
    )
    r3 = qa.audit_site(tmp / "dist", base_url="https://t.example")
    check("qa: ловит битый JSON-LD", r3["errors"] >= 1, qa.summarize(r3))

    # фантом sitemap
    sm = tmp / "dist" / "sitemap.xml"
    sm.write_text(
        sm.read_text(encoding="utf-8").replace("</urlset>",
        "<url><loc>https://t.example/item/nope.html</loc></url></urlset>"),
        encoding="utf-8",
    )
    r4 = qa.audit_site(tmp / "dist", base_url="https://t.example")
    check("qa: ловит фантом sitemap", r4["errors"] >= 1, qa.summarize(r4))


# ---------------------------------------------------------------- QA-гейт CI
def test_qa_gate():
    from archaea import qa_gate

    tmp = Path(tempfile.mkdtemp())
    good = tmp / "good.json"
    good.write_text(
        json.dumps({"colonies": {"a": {"qa": "QA ok:8 warn:0 err:0"}}}),
        encoding="utf-8",
    )
    check("gate: чистый улей → 0", qa_gate.gate(good) == 0)

    bad = tmp / "bad.json"
    bad.write_text(
        json.dumps({"colonies": {
            "a": {"qa": "QA ok:7 warn:0 err:1"},
            "b": {"qa": "QA ok:8 warn:0 err:0"},
        }}),
        encoding="utf-8",
    )
    check("gate: QA-ошибка у колонии → 1", qa_gate.gate(bad) == 1)
    check("gate: metrics.txt отсутствует → 2", qa_gate.gate(tmp / "nope.json") == 2)


# ---------------------------------------------------------------- пульт (Space)
def test_space_console():
    """Чистые функции пульта — без gradio (он стоит только в Space)."""
    from infra.space import app

    check("пульт: QA-зелёная отметка", app._qa_mark("QA ok:8 warn:0 err:0").startswith("✅"))
    check("пульт: QA-красная отметка", app._qa_mark("QA ok:7 warn:0 err:1").startswith("❌"))

    md, rows, hist, raw = app.refresh()
    check("пульт: refresh без metrics — понятная ошибка",
          "metrics.json" in md and "⚠️" in md, md[:70])

    # фикстура вместо живого metrics.json: тест не должен зависеть от того,
    # прошёл последний цикл улья успешно или нет
    fixture = {
        "tick": 7, "elapsed_s": 3.0,
        "agents": [{"name": "radar", "role": "scout", "colony": "core", "status": "active"}],
        "budget": {"spent_u": 6200, "revenue_u": 0},
        "tasks": {"done": 10, "failed": 0},
        "colonies": {
            "alpha": {
                "site": {"title": "Alpha Radar", "base_url": "https://a.example"},
                "qa": "QA ok:8 warn:0 err:0", "pages": 70,
                "totals": {"items": 5, "by_source": {"hn": 5}},
                "products": {"cve_digest.csv": {"rows": 7}, "trend_index.csv": {"rows": 3}},
                "top_items": [{"title": "Hello", "source": "hn", "buzz": 10, "topics": ["ai"]}],
            },
            "beta": {
                "site": {"title": "Beta Post", "base_url": "https://b.example"},
                "qa": "QA ok:6 warn:0 err:2", "pages": 40,
                "totals": {"items": 3, "by_source": {"cve": 3}},
                "products": {},
                "top_items": [],
            },
        },
    }
    tmp = Path(tempfile.mkdtemp())
    (tmp / "metrics.json").write_text(json.dumps(fixture, ensure_ascii=False),
                                      encoding="utf-8")
    app.METRICS_LOCAL = tmp / "metrics.json"
    md, rows, hist, raw = app.refresh()
    check("пульт: карточки колоний собрались", "alpha" in md and "beta" in md)
    check("пульт: QA-отметки в карточках", "✅" in md and "❌" in md)
    check("пульт: дата-продукты в карточках", "cve_digest.csv" in md)
    check("пульт: топ-предметы собрались", len(rows) == 1, str(len(rows)))


# ---------------------------------------------------------------- core
def test_treasury():
    tmp = Path(tempfile.mkdtemp())
    t = Treasury(tmp / "t.db")
    t.open_cell("probe", 1000)
    check("treasury: лимит позволяет", t.spend("probe", 500, "half") is True)
    over = t.spend("probe", 600, "rest")
    check("treasury: перерасход ловится", over is False)
    check("treasury: жертва апоптоза обнаружена",
          any(v["agent_id"] == "probe" for v in t.victims()))
    t.revenue("probe", 250, "first dollar")
    check("treasury: выручка считается", t.summary()["revenue_u"] == 250)
    # клетка под апоптозом блокируется: деньги не уходят, даже если
    # ретайр задержался (поведение, найденное soak-тестом)
    over_blocked = t.spend("probe", 1) is False
    check("treasury: overrun-клетка не тратит", over_blocked)
    t.close()


def test_orchestrator():
    tmp = Path(tempfile.mkdtemp())
    o = Orchestrator(tmp / "o.db")

    seen = []

    def handler_a(payload):
        seen.append(payload["v"])
        return {"ok": payload["v"]}

    def handler_boom(_payload):
        raise RuntimeError("boom")

    o.enqueue("c", "t1", "ha", {"v": 1})
    o.enqueue("c", "t2", "ha", {"v": 2})
    o.enqueue("c", "bad", "hb", {})
    stats = o.tick({"ha": handler_a, "hb": handler_boom})

    check("orch: выполнил обе задачи", stats["ran"] == 2 and seen == [1, 2], seen)
    check("orch: сбой изолирован", stats["failed"] == 1, stats)
    st = o.stats()
    check("orch: статусы учтены", st.get("done") == 2 and st.get("failed") == 1, st)
    o.close()


def test_registry():
    tmp = Path(tempfile.mkdtemp())
    t = Treasury(tmp / "r.db")
    r = Registry(tmp / "r.db", t)
    a = r.spawn("x", "scout", "core", 1000)
    b = r.spawn("x", "scout", "core", 1000)
    check("registry: спавн идемпотентен", a == b and a is not None, f"{a}/{b}")
    r.retire("x", "test")
    check("registry: ретайр работает", r.get("x")["status"] == "retired")
    r.close()
    t.close()


def main() -> int:
    for fn in (test_clean_dedup, test_score_and_tags, test_snapshot,
               test_rss_parse, test_robots_guard, test_pii_scrub,
               test_apothecary, test_feed_roundtrip, test_sitegen_render,
               test_qa_clean, test_qa_gate, test_space_console,
               test_treasury, test_orchestrator, test_registry,
               test_monetization_cta, test_tgpost, test_html_list, test_pings,
               test_archive):
        try:
            fn()
        except Exception as e:  # тест не должен вешать рой — но должен орать
            check(fn.__name__, False, f"EXCEPTION {e!r}")

    width = max(len(n) for n, _, _ in RESULTS) + 2
    failed = 0
    for name, ok, note in RESULTS:
        print(f"  {'✓' if ok else '✗'} {name.ljust(width)} {note if not ok or note != '' and not ok else ''}")
        if not ok:
            failed += 1
    print(f"\nselftest: {len(RESULTS) - failed}/{len(RESULTS)} пройдено")
    if failed:
        for name, ok, note in RESULTS:
            if not ok:
                print(f"  FAIL {name}: {note}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
