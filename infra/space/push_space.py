"""Подъём пульта-дашборда на HF Space (один раз).

HF перевёл Gradio/Docker Spaces на PRO → бесплатный путь: STATIC Space
(index.html + vanilla JS, данные тянутся из публичного датасета состояния).
"""
import os
import shutil
from pathlib import Path

from huggingface_hub import HfApi, create_repo, upload_folder

ROOT = Path(__file__).resolve().parents[2]
SPACE_DIR = ROOT / "infra" / "space"
STAGE = ROOT / ".space-stage"

token = os.environ["HF_TOKEN"]
api = HfApi(token=token)
repo = "fshmidtai/atria-console"

create_repo(repo, repo_type="space", space_sdk="static", exist_ok=True)
STAGE.mkdir(exist_ok=True)
for name in ("README.md", "index.html"):
    shutil.copy(SPACE_DIR / name, STAGE / name)
upload_folder(repo_id=repo, folder_path=str(STAGE), repo_type="space",
              commit_message="atria console v1 (static)")
print("space:", f"https://huggingface.co/spaces/{repo}")

