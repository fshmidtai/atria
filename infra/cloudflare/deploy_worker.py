"""Деплой CF Worker (atria-links) через API: module-worker формат.

Worker = module syntax (export default), content-type application/javascript+module.
Имя воркера: atria-links → URL https://atria-links.<account-subdomain>.workers.dev
"""
import json
import os
import sys
import urllib.request

AID = os.environ["CLOUDFLARE_ACCOUNT_ID"]
TOK = os.environ["CLOUDFLARE_API_TOKEN"]
HERE = os.path.dirname(os.path.abspath(__file__))
NAME = "atria-links"


def put_worker():
    src = open(os.path.join(HERE, "worker", NAME + ".js"), encoding="utf-8").read()
    meta = {"main_module": NAME + ".js", "compatibility_date": "2024-11-01"}
    # multi-part: metadata + module
    body = (
        '----atriaworker\r\n'
        'Content-Disposition: form-data; name="metadata"; filename="metadata.json"\r\n'
        'Content-Type: application/json\r\n\r\n' + json.dumps(meta) + '\r\n'
        f'----atriaworker\r\n'
        f'Content-Disposition: form-data; name="{NAME}.js"; filename="{NAME}.js"\r\n'
        'Content-Type: application/javascript+module\r\n\r\n' + src + '\r\n'
        '----atriaworker--\r\n'
    ).encode()
    req = urllib.request.Request(
        f"https://api.cloudflare.com/client/v4/accounts/{AID}/workers/scripts/{NAME}",
        data=body, method="PUT",
        headers={"Authorization": "Bearer " + TOK,
                 "Content-Type": "multipart/form-data; boundary=----atriaworker"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.status, json.loads(r.read() or b"{}")


if __name__ == "__main__":
    st, d = put_worker()
    print("worker PUT ->", st, json.dumps(d.get("errors", []), ensure_ascii=False)[:200])
