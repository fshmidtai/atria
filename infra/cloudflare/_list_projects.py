"""Список Pages-проектов нашего аккаунта + проверка свободы имён."""
import json
import os
import urllib.request

t = os.environ["CLOUDFLARE_API_TOKEN"]
aid = os.environ["CLOUDFLARE_ACCOUNT_ID"]
req = urllib.request.Request(
    f"https://api.cloudflare.com/client/v4/accounts/{aid}/pages/projects",
    headers={"Authorization": "Bearer " + t})
d = json.loads(urllib.request.urlopen(req, timeout=60).read().decode("utf-8"))
for p in d.get("result", []):
    print(p["name"], "->", (p.get("subdomain") or ""), "| created",
          (p.get("created_on") or "")[:10])
