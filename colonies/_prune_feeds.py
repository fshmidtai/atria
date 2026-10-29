"""Раунд 16: вычистить мёртвые из CI фиды (reddit/venturebeat), вписать замены.
Решение принято по live-метрикам тика: reddit_* и venturebeat дали 0 items."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

DROP_LABELS = {"venturebeat_ai", "reddit_ml", "reddit_ai", "reddit_openai",
               "reddit_cyber", "reddit_quant", "reddit_algotrading",
               "reddit_datasets"}

ADD = {
    "phosphor": [
        {"kind": "rss", "label": "vb_full",
         "url": "https://feeds.feedburner.com/venturebeat/SZYF", "limit": 30},
        {"kind": "rss", "label": "zdnet_ai",
         "url": "https://www.zdnet.com/topic/artificial-intelligence/rss.xml", "limit": 25},
    ],
    "vesper": [
        {"kind": "rss", "label": "zdnet_ai",
         "url": "https://www.zdnet.com/topic/artificial-intelligence/rss.xml", "limit": 25},
        {"kind": "rss", "label": "theverge",
         "url": "https://www.theverge.com/rss/index.xml", "limit": 25},
    ],
    "meridian": [
        {"kind": "rss", "label": "kdnuggets",
         "url": "https://www.kdnuggets.com/feed", "limit": 25},
        {"kind": "rss", "label": "theverge",
         "url": "https://www.theverge.com/rss/index.xml", "limit": 25},
    ],
    "sentinel": [
        {"kind": "rss", "label": "arstechnica",
         "url": "https://feeds.arstechnica.com/arstechnica/index", "limit": 25},
    ],
}

for colony, add in ADD.items():
    path = ROOT / "colonies" / colony / "config.json"
    cfg = json.loads(path.read_text(encoding="utf-8"))
    srcs = cfg.setdefault("sources", [])
    kept = [s for s in srcs if s.get("label") not in DROP_LABELS]
    dropped = [s.get("label") for s in srcs if s.get("label") in DROP_LABELS]
    labels = {s.get("label") for s in kept}
    for rec in add:
        if rec["label"] not in labels:
            kept.append(rec)
            print(f"{colony}: +{rec['label']}")
    cfg["sources"] = kept
    if dropped:
        print(f"{colony}: dropped {dropped}")
    path.write_text(
        json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("done")
