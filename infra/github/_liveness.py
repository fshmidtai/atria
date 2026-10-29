"""Раунд 20: liveness-ревизия — таблица by_recipe по всем колониям из HF-метрик."""
import json
import os
import urllib.request

os.environ.setdefault(
    "https_proxy", "http://miningchia:mining012345@mproxy.site:12655")
URL = ("https://huggingface.co/datasets/fshmidtai/atria-hive-state/"
       "resolve/main/metrics.json")
p = urllib.request.ProxyHandler(
    {"http": os.environ["https_proxy"], "https": os.environ["https_proxy"]})
raw = urllib.request.build_opener(p).open(
    urllib.request.Request(URL, headers={"User-Agent": "atria/1.0"}),
    timeout=120).read()
m = json.loads(raw)
print("tick:", m["tick"], "| elapsed", m["elapsed_s"], "s")
for name, c in sorted(m["colonies"].items()):
    t = c["totals"]
    print(f"{name:12s} items={t['items']:4d} by_recipe={t.get('by_recipe', {})}")
