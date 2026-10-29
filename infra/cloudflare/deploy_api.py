"""Деплой бэкенд-проекта atria-api (Pages advanced mode) — одной командой.

python infra/cloudflare/deploy_api.py
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from deploy_pages import _api, _collect, deploy_project

ROOT = Path(__file__).resolve().parents[2]
PROJECT = "atria-api"
DIST = ROOT / "infra" / "cloudflare" / "api-dist"


def main():
    aid = os.environ["CLOUDFLARE_ACCOUNT_ID"].strip()
    tok = os.environ["CLOUDFLARE_API_TOKEN"].strip()
    # создаём проект, если ещё нет
    st, d = _api("POST", f"/accounts/{aid}/pages/projects", tok,
                 json.dumps({"name": PROJECT, "production_branch": "master"}).encode())
    if st in (200, 201):
        print(f"проект {PROJECT} создан")
    elif st == 400 and "already" in json.dumps(d).lower():
        pass
    else:
        print(f"project create HTTP {st}: {json.dumps(d)[:200]}")

    # _worker.js — единственный «ассет»; Pages включает advanced mode
    ok, info = deploy_project(aid, tok, PROJECT, DIST)
    print(("OK  " if ok else "FAIL"), PROJECT, "->", info)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
