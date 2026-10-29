import re
import sys

sys.path.insert(0, ".")
from colonies.phosphor import sources

h = sources._get("https://freetender.net/tenders/russia")
hrefs = sorted(set(re.findall(r'href="([^"]+)"', h)))
print("total hrefs:", len(hrefs))
for u in hrefs:
    low = u.lower()
    if ("/tenders" in u or "categor" in low or "page" in low
            or "sector" in low or "region" in low or "fund" in low
            or "insight" in low or "guide" in low):
        print(" ", u[:110])
# также: есть ли на детальной странице ссылка на категорию тендера
d = sources._get("https://freetender.net/tender/tender-0354100010626000313")
for u in sorted(set(re.findall(r'href="([^"]+)"', d))):
    if "/tenders/" in u or "categor" in u.lower():
        print("detail:", u[:110])
