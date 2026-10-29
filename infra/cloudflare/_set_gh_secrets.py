"""Установка секретов GitHub Actions (pynacl, libsodium sealed box)."""
import base64
import json
import os
import sys
import urllib.request

from nacl import encoding, public

GH = os.environ["GH"]


def gh(path, method="GET", data=None):
    req = urllib.request.Request(
        "https://api.github.com/repos/fshmidtai/atria" + path,
        headers={"Authorization": "Bearer " + GH, "Accept": "application/vnd.github+json"},
        method=method)
    body = json.dumps(data).encode() if data else None
    if body:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, body, timeout=60) as r:
        raw = r.read()
        return json.loads(raw) if raw.strip() else {}


key = gh("/actions/secrets/public-key")
pk = public.PublicKey(key["key"].encode(), encoding.Base64Encoder())
sealed = public.SealedBox(pk)

for name, value in [
    ("CF_API_TOKEN", os.environ["CF_API_TOKEN"]),
    ("CF_ACCOUNT_ID", os.environ["CF_ACCOUNT_ID"]),
]:
    enc = sealed.encrypt(value.encode())
    gh(f"/actions/secrets/{name}", "PUT",
       {"encrypted_value": base64.b64encode(enc).decode(), "key_id": key["key_id"]})
    print("secret set:", name)
print("done")
