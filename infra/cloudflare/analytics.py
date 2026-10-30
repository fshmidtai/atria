"""Cloudflare Web Analytics — бесплатная аналитика роя без сторонних аккаунтов.

Маяк (beacon.min.js) — privacy-first: без cookies, 1.6 кб, async/defer.
Цена: одна HTML-строка на странице (чистый zero-JS роя нарушаем сознательно —
измерение источников трафика окупает это; отчёты — тоже бесплатно).

Разовый человечесий шаг:
  1. dash.cloudflare.com → My Profile → API Tokens → Create Token →
     Custom: Account · Cloudflare Web Analytics · Edit.
  2. Положить токен в .env как CF_ANALYTICS_TOKEN (локально; CI не нужен —
     beacon-токены публичны по дизайну, как IndexNow-ключи).
  3. python infra/cloudflare/analytics.py create
     → создаёт 10 RUM-сайтов, вписывает site.cf_beacon в каждый config.json.

Дальше — без человека:
  python infra/cloudflare/analytics.py metrics [дней]
  → посетители/просмотры по колониям (питает консоль и стратегию).
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
API = "https://api.cloudflare.com/client/v4"


def load_env() -> dict:
    p = ROOT / ".env"
    env = {}
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.strip().split("=", 1)
                env[k] = v
    return env


def _api(token: str, method: str, path: str, data=None):
    req = urllib.request.Request(
        API + path, data=json.dumps(data).encode() if data else None,
        headers={"Authorization": "Bearer " + token,
                 "Content-Type": "application/json"},
        method=method)
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "{}")
    except Exception as e:  #.co сеть кишлачит — рой едет дальше
        return 0, {"_err": str(e)}


def colonies() -> list[tuple[str, dict]]:
    out = []
    for cfg in sorted((ROOT / "colonies").glob("*/config.json")):
        out.append((cfg.parent.name, cfg))
    return out


def cmd_create(env: dict) -> int:
    tok = env.get("CF_ANALYTICS_TOKEN", "")
    aid = env.get("CLOUDFLARE_ACCOUNT_ID", "")
    if not tok or not aid:
        print("нужны CF_ANALYTICS_TOKEN (Web Analytics: Edit) и "
              "CLOUDFLARE_ACCOUNT_ID в .env")
        return 2
    for colony, cfg_path in colonies():
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        host = cfg["site"]["base_url"].replace("https://", "")
        if cfg["site"].get("cf_beacon"):
            print(f"  - {colony}: уже есть beacon, пропуск")
            continue
        st, d = _api(tok, "POST", f"/accounts/{aid}/rum/site_info",
                     {"name": colony, "domain": host})
        tag = ((d.get("result") or {}).get("site_tag")
               if d.get("success") else None)
        if not tag:
            print(f"  ✗ {colony}: HTTP {st} {json.dumps(d.get('errors'))[:120]}")
            continue
        cfg["site"]["cf_beacon"] = tag
        cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2)
                            + "\n", encoding="utf-8")
        print(f"  ✓ {colony}: beacon {tag} → config.json")
    return 0


def cmd_metrics(env: dict, days: int) -> int:
    tok = env.get("CF_ANALYTICS_TOKEN", "")
    aid = env.get("CLOUDFLARE_ACCOUNT_ID", "")
    if not tok or not aid:
        print("нужны CF_ANALYTICS_TOKEN и CLOUDFLARE_ACCOUNT_ID в .env")
        return 2
    since = (datetime.now(timezone.utc)
             - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    total_pv = total_v = 0
    for colony, cfg_path in colonies():
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        tag = cfg["site"].get("cf_beacon")
        if not tag:
            continue
        st, d = _api(tok, "GET",
                     f"/accounts/{aid}/rum/site_info/{tag}/metrics"
                     f"?since={since}&until={datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z')}")
        if st != 200 or not d.get("success"):
            print(f"  {colony}: no data ({st})")
            continue
        r = d.get("result") or {}
        pv = r.get("pageviews", 0) or 0
        v = r.get("visitors", 0) or 0
        total_pv += pv
        total_v += v
        print(f"  {colony:12s} visitors={v} pageviews={pv}")
    print(f"  TOTAL: visitors={total_v} pageviews={total_pv} (last {days}d)")
    return 0


def main() -> int:
    env = load_env()
    # прокси из окружения (локальный запуск)
    if os.environ.get("https_proxy"):
        proxy = urllib.request.ProxyHandler({
            "http": os.environ["https_proxy"],
            "https": os.environ["https_proxy"]})
        urllib.request.install_opener(urllib.request.build_opener(proxy))
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "create":
        return cmd_create(env)
    if cmd == "metrics":
        days = int(sys.argv[2]) if len(sys.argv) > 2 else 7
        return cmd_metrics(env, days)
    print(__doc__)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
