"""Деплой колоний на Cloudflare Pages (Direct Upload API).

Протокол (ровно как у wrangler, без обёрток):
  1. sha256 каждого файла dist/
  2. POST /pages/assets/check-missing {hashes} — какие ещё не на сервере
  3. POST /pages/assets/upload [{key: hash, value: base64, metadata, base64}]
     → JWT
  4. POST /pages/assets/upsert-hashes {hashes} (Bearer JWT)
  5. POST /pages/projects/<name>/deployments — multipart: manifest
     ({"/путь": sha256}) + branch=master

Один вызов = все колонии: base_url из config.json задаёт имя проекта
(<name>.pages.dev). Использование: python infra/cloudflare/deploy_pages.py
[--dry-run]. Переменные: CLOUDFLARE_API_TOKEN, CLOUDFLARE_ACCOUNT_ID.
Секреты — только окружение (Конституция §5).
"""
from __future__ import annotations

import base64
import blake3
import hashlib
import json
import mimetypes
import os
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
API = "https://api.cloudflare.com/client/v4"


def _api(method: str, path: str, token: str, data: bytes | None = None,
         ctype: str = "application/json"):
    req = urllib.request.Request(
        API + path, data=data,
        headers={"Authorization": f"Bearer {token}", "Content-Type": ctype},
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw.strip() else {})
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {"_body": raw[:200].decode(errors="replace")}


def _cf_hash(f: Path) -> str:
    """Ключ ассета ровно как у wrangler:
    blake3(base64(контент) + расширение_без_точки).hex()[:32]
    (packages/deploy-helpers/src/deploy/helpers/hash.ts).
    """
    raw = f.read_bytes()
    ext = f.suffix.lstrip(".")
    return blake3.blake3((base64.b64encode(raw).decode() + ext).encode()).hexdigest()[:32]


def _collect(dist: Path) -> dict[str, str]:
    """{путь в dist: hash} — пути с ведущим «/», как ждёт CF."""
    out = {}
    for f in sorted(p for p in dist.rglob("*") if p.is_file()):
        out["/" + f.relative_to(dist).as_posix()] = _cf_hash(f)
    return out


def deploy_project(aid: str, token: str, project: str, dist: Path) -> tuple[bool, str]:
    assets = _collect(dist)
    hashes = list(assets.values())
    files = {v: k for k, v in assets.items()}  # hash → путь (для contentType)

    # 1. per-project upload-token (JWT) — им, а не API-токеном, авторизуем
    #    ассеты (ровно как wrangler). Метод — GET.
    st, d = _api("GET", f"/accounts/{aid}/pages/projects/{project}/upload-token",
                 token, None)
    if st != 200 or not d.get("success"):
        return False, f"upload-token HTTP {st}: {json.dumps(d)[:160]}"
    jwt = (d.get("result") or {}).get("jwt")
    if not jwt:
        return False, "upload-token: нет jwt"

    # 2. каких ассетов ещё нет на стороне CF
    st, d = _api("POST", "/pages/assets/check-missing", jwt,
                 json.dumps({"hashes": hashes}).encode())
    if st != 200:
        return False, f"check-missing HTTP {st}: {json.dumps(d)[:160]}"
    missing = set(d.get("result", []))

    # 3. заливаем только недостающие (base64, как wrangler)
    if missing:
        payload = []
        for h in missing:
            path = files[h]
            raw = (dist / path.lstrip("/")).read_bytes()
            ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
            payload.append({
                "key": h,
                "value": base64.b64encode(raw).decode(),
                "metadata": {"contentType": ctype},
                "base64": True,
            })
        st, d = _api("POST", "/pages/assets/upload", jwt,
                     json.dumps(payload).encode())
        if st != 200:
            return False, f"assets/upload HTTP {st}: {json.dumps(d)[:160]}"
        # 4. регистрируем хэши
        st, d = _api("POST", "/pages/assets/upsert-hashes", jwt,
                     json.dumps({"hashes": list(missing)}).encode())
        if st != 200:
            return False, f"upsert-hashes HTTP {st}: {json.dumps(d)[:160]}"

    # 5. создаём deployment: manifest = {"/путь": sha256}
    manifest = json.dumps(assets)
    body = (
        "--atriaboundary\r\n"
        'Content-Disposition: form-data; name="manifest"\r\n'
        "Content-Type: application/json\r\n\r\n" + manifest + "\r\n"
        "--atriaboundary\r\n"
        'Content-Disposition: form-data; name="branch"\r\n\r\nmaster\r\n'
        "--atriaboundary--\r\n"
    ).encode()
    st, d = _api(
        "POST", f"/accounts/{aid}/pages/projects/{project}/deployments", token,
        body, ctype="multipart/form-data; boundary=atriaboundary",
    )
    if st != 200 or not d.get("success"):
        return False, f"deployments HTTP {st}: {json.dumps(d)[:200]}"
    url = (d.get("result") or {}).get("url", f"{project}.pages.dev")
    return True, url


def main() -> int:
    token = os.environ.get("CLOUDFLARE_API_TOKEN", "").strip()
    aid = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip()
    if not token or not aid:
        print("нужны CLOUDFLARE_API_TOKEN и CLOUDFLARE_ACCOUNT_ID", file=sys.stderr)
        return 2
    dry = "--dry-run" in sys.argv
    ok_all = True
    for cfg_path in sorted((ROOT / "colonies").glob("*/config.json")):
        colony = cfg_path.parent.name
        dist = ROOT / "colonies" / colony / "dist"
        if not dist.exists():
            print(f"  - {colony}: нет dist/, пропуск")
            continue
        base = json.loads(cfg_path.read_text(encoding="utf-8"))["site"]["base_url"]
        project = base.replace("https://", "").split(".")[0]
        assets = _collect(dist)
        n, kb = len(assets), sum(f.stat().st_size for f in dist.rglob("*") if f.is_file()) // 1024
        if dry:
            print(f"  - {colony} -> {project}.pages.dev: {n} файлов, {kb} КБ")
            continue
        ok, info = deploy_project(aid, token, project, dist)
        print(f"  {'OK' if ok else 'FAIL'} {colony} -> {info}"
              f" ({n} файлов, {kb} КБ)")
        ok_all &= ok
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
