"""Залить dataset-card README.md в HF-репозиторий состояния роя
(открытие датасета в поиске HF зависит от карточки)."""
import os

from huggingface_hub import HfApi

api = HfApi(token=os.environ["HF_TOKEN"])
api.upload_file(
    path_or_fileobj=os.path.join(os.path.dirname(__file__), "README.md"),
    path_in_repo="README.md",
    repo_id="fshmidtai/atria-hive-state",
    repo_type="dataset",
)
print("card: https://huggingface.co/datasets/fshmidtai/atria-hive-state")
