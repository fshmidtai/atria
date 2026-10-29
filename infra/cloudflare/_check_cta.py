"""Проверка CTA и хаба тем на live-сайтах (тело ответа через прокси)."""
import os
import urllib.request

os.environ.setdefault(
    "https_proxy", "http://miningchia:mining012345@mproxy.site:12655")
PROXY = urllib.request.ProxyHandler({
    "http": os.environ["https_proxy"], "https": os.environ["https_proxy"]})
OPENER = urllib.request.build_opener(PROXY)

SITES = {
    "signal-frontier": "https://signal-frontier.pages.dev/",
    "vesper": "https://vesper-ai-radar.pages.dev/",
    "sentinel": "https://sentinel-post.pages.dev/",
    "meridian": "https://meridian-radar.pages.dev/",
    "bourse": "https://bourse-radar.pages.dev/",
}

for name, url in SITES.items():
    try:
        html = OPENER.open(urllib.request.Request(
            url, headers={"User-Agent": "Mozilla/5.0 Chrome/131"}),
            timeout=40).read().decode("utf-8")
    except Exception as e:
        print(f"{name}: ERR {e}")
        continue
    cta = 'class="cta"' in html and "ko-fi.com/miningchia" in html
    lang = "EN" if "Support the hive" in html else (
        "RU" if "Поддержать улей" in html else "?")
    print(f"{name}: CTA={cta} lang={lang} len={len(html)}")
