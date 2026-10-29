"""Раунд 18: зонд источников под 5 новых колоний. Только RSS/Atom (бесплатно,
без ключей). Мёртвые отсюда — не вписываем (CI потом подтвердит)."""
import os
import sys

os.environ.setdefault(
    "https_proxy", "http://miningchia:mining012345@mproxy.site:12655")

sys.path.insert(0, ".")
from colonies.phosphor import sources

FEEDS = [
    # 1. Регуляторный патруль (МСБ/лицензии)
    ("pravo_ru", "https://pravo.ru/rss/news/"),
    ("garant", "https://www.garant.ru/news/rss/"),
    ("pravo_gov", "https://pravo.gov.ru/rss/"),
    ("nalog", "https://www.nalog.ru/rss/news/"),
    ("fns_news", "https://www.nalog.ru/rn77/news/rss/"),
    # 2. Тендерный срез (микро 44-ФЗ)
    ("tender_news", "https://www.tendernews.ru/rss/"),
    ("zakupki_online", "https://www.zakupki-online.com/rss/"),
    ("tender_plan", "https://tenderplan.ru/feed/"),
    ("sber_agro", "https://www.sberbank-ast.ru/News/AllNewsRSS/"),
    # 3. Гранты/поддержка
    ("asi", "https://asi.ru/rss/"),
    ("mybiz", "https://mybiz.ru/feed/"),
    ("pfg", "https://пфг.рф/rss/"),
    ("dubro", "https://www.dobro.ru/feed/"),
    # 4. ИБ/CVE на русском
    ("securitylab", "https://www.securitylab.ru/rss/news.xml"),
    ("anti_malware", "https://www.anti-malware.ru/rss/"),
    ("xakep", "https://xakep.ru/feed/"),
    ("the_hacker_news_ru", "https://feeds.feedburner.com/TheHackersNews"),
    # 5. Реклама/маркетинг compliance (вместо ТЗ-мониторинга)
    ("sostav", "https://www.sostav.ru/rss/"),
    ("adindex", "https://adindex.ru/rss/"),
    ("fas", "https://fas.gov.ru/rss/"),
]

for label, url in FEEDS:
    try:
        items = sources.fetch_rss(url, limit=5)
        print(f"{label}: {len(items)} items")
    except Exception as e:
        print(f"{label}: ERR {type(e).__name__} {str(e)[:60]}")
