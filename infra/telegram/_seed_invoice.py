"""Раунд 22: one-shot — создать постоянный Stars-инвойс для Pro-подписки и
положить ссылку в HF-состояние tg_subs.json. createInvoiceLink не читает
очередь обновлений, поэтому локальный запуск безопасен."""
import json
import os
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from core import tgpost

env = {}
for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
    if "=" in line and not line.strip().startswith("#"):
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"')

token = env["TG_BOT_TOKEN"]
os.environ["HF_TOKEN"] = env["HF_TOKEN"]
os.environ["HF_STATE_REPO"] = env.get("HF_STATE_REPO", "fshmidtai/atria-hive-state")

state = tgpost.fetch_subs()
print("before:", len(state["chats"]), "chats, offset", state["offset"])
link = tgpost.ensure_invoice(token, state)
print("invoice:", link)
ok = tgpost.save_subs(state)
print("saved:", ok)
