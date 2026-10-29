import sys
import time

sys.path.insert(0, ".")
from colonies.phosphor import sources

FIELDS = [
    {"name": "sum", "re": r"VALUE\s*\n+\s*RUB\s*([\d,]+)"},
    {"name": "region", "re": r"LOCATION\s*\n+\s*([^\n]+)"},
]
for u in ["https://freetender.net/tenders/russia?page=2",
          "https://freetender.net/tenders/russia?page=3",
          "https://freetender.net/tenders/russia/manufacturing-supply",
          "https://freetender.net/tenders/russia/it-telecom"]:
    t0 = time.time()
    items = sources.fetch_html_list(u, fields=FIELDS)
    small = [i for i in items if i.get("sum")
             and float(i["sum"].replace(",", "").replace(" ", "")) <= 300000]
    print(f"\n{u}")
    print(f"  items={len(items)} <=300k={len(small)} elapsed={time.time()-t0:.0f}s")
    for i in items[:3]:
        print("   -", i.get("sum"), i.get("region"), "|", i["title"][:45])
