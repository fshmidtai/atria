"""LLM Router — бесплатный мозг роя.

Приоритет провайдеров (все — free-tier, платных ключей нет по Конституции §2):
  1. local       — self-hosted Qwen на Oracle-узле (LOCAL_LLM_URL)
  2. groq        — GROQ_API_KEY
  3. openrouter  — OPENROUTER_API_KEY (есть free-модели)

Если ни один провайдер не настроен — chat() вернёт None, и колония откатывается
на детерминированную эвристику (v0.1 так и работает: скоринг и тегирование
тем — алгоритмические, LLM понадобится позже для рерайтов и редактуры).
"""
from __future__ import annotations

import json
import os
import urllib.request

TIMEOUT = 30


def _env(name: str) -> str:
    return os.environ.get(name, "").strip()


def available_providers() -> list[str]:
    out = []
    if _env("LOCAL_LLM_URL"):
        out.append("local")
    if _env("GROQ_API_KEY"):
        out.append("groq")
    if _env("OPENROUTER_API_KEY"):
        out.append("openrouter")
    return out


def chat(prompt: str, system: str | None = None, max_tokens: int = 512) -> str | None:
    """Спросить у первого доступного бесплатного провайдера. None — никто не ответил."""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    if _env("LOCAL_LLM_URL"):
        r = _openai_compat(_env("LOCAL_LLM_URL") + "/v1/chat/completions", "", messages, max_tokens)
        if r is not None:
            return r
    if _env("GROQ_API_KEY"):
        r = _openai_compat(
            "https://api.groq.com/openai/v1/chat/completions",
            _env("GROQ_API_KEY"),
            messages,
            max_tokens,
            model="llama-3.3-70b-versatile",
        )
        if r is not None:
            return r
    if _env("OPENROUTER_API_KEY"):
        r = _openai_compat(
            "https://openrouter.ai/api/v1/chat/completions",
            _env("OPENROUTER_API_KEY"),
            messages,
            max_tokens,
            model="meta-llama/llama-3.3-70b-instruct:free",
        )
        if r is not None:
            return r
    return None


def _openai_compat(
    url: str, api_key: str, messages: list[dict], max_tokens: int, model: str | None = None
) -> str | None:
    body: dict = {"messages": messages, "max_tokens": max_tokens}
    if model:
        body["model"] = model
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"]
    except Exception:
        return None
