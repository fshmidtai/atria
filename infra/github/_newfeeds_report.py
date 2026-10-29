"""Сводка по новым источникам из live-метрик (HF dataset)."""
import json
import os
import urllib.request

os.environ.setdefault(
    "https_proxy", "http://miningchia:mining012345@mproxy.site:12655")
p = urllib.request.ProxyHandler({
    "http": os.environ["https_proxy"], "https": os.environ["https_proxy"]})
op = urllib.request.build_opener(p)

m = json.loads(op.open(urllib.request.Request(
    "https://huggingface.co/datasets/fshmidtai/atria-hive-state/resolve/main/metrics.json",
    headers={"User-Agent": "Mozilla/5.0"}), timeout=60).read().decode("utf-8"))

NEW = ["venturebeat_ai", "reddit_ml", "reddit_ai", "reddit_openai",
       "hackersnews", "reddit_cyber", "cnbc_top", "reddit_quant",
       "reddit_algotrading", "reddit_datasets", "schneier"]
for col, data in m["colonies"].items():
    br = data["totals"].get("by_recipe", {})
    hits = {k: br[k] for k in NEW if k in br}
    print(f"{col}: items={data['totals']['items']} | new_feeds={hits}")
