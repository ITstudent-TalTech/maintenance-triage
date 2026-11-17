"""LLM classification through Anthropic, OpenAI or a local LM Studio server.

Provider is chosen with the TRIAGE_PROVIDER environment variable:
  anthropic  -> needs ANTHROPIC_API_KEY  (model: TRIAGE_MODEL, default claude-haiku-4-5)
  openai     -> needs OPENAI_API_KEY     (model: TRIAGE_MODEL, default gpt-4o-mini)
  lmstudio   -> local server at LMSTUDIO_URL (default http://localhost:1234/v1)
  rules      -> no LLM, keyword fallback only
Only the standard library is used, so there is nothing extra to install.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
import urllib.error
import urllib.request

from .schema import CATEGORIES, PRIORITIES

log = logging.getLogger(__name__)

SYSTEM_PROMPT = f"""You triage maintenance requests for commercial buildings (offices, retail, logistics).
Requests can be in Estonian, English or Russian. Personal data is already masked.

Return ONLY a JSON object with these keys:
  category   one of {list(CATEGORIES)}
  priority   one of {list(PRIORITIES)}
  summary    one short line in English for the technician's work order
  location   floor/room/unit if mentioned, else ""
  language   et | en | ru
  confidence number 0..1, how sure you are
  reason     one short sentence

Priority rules:
{chr(10).join(f"  {k}: {v}" for k, v in PRIORITIES.items())}
Treat as P1: people trapped, fire/smoke/burning smell, fire system faults, blocked emergency exits,
water near electrical equipment, server rooms overheating, or a tenant's business fully stopped.
A message that only reports that something is fixed is GENERAL / P4.
"""


class LLMError(RuntimeError):
    pass


def _post(url: str, headers: dict, body: dict, timeout: int = 60) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def _extract_json(text: str) -> dict:
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        raise LLMError(f"no JSON in model output: {text[:120]!r}")
    return json.loads(match.group(0))


def _call(provider: str, user_text: str) -> str:
    model = os.getenv("TRIAGE_MODEL")
    if provider == "anthropic":
        data = _post(
            "https://api.anthropic.com/v1/messages",
            {"x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01",
             "content-type": "application/json"},
            {"model": model or "claude-haiku-4-5", "max_tokens": 400, "temperature": 0,
             "system": SYSTEM_PROMPT, "messages": [{"role": "user", "content": user_text}]},
        )
        return data["content"][0]["text"]

    if provider in ("openai", "lmstudio"):
        if provider == "openai":
            url = "https://api.openai.com/v1/chat/completions"
            headers = {"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"}
            model = model or "gpt-4o-mini"
        else:
            url = os.getenv("LMSTUDIO_URL", "http://localhost:1234/v1") + "/chat/completions"
            headers = {}
            model = model or "local-model"
        headers["Content-Type"] = "application/json"
        data = _post(url, headers, {
            "model": model, "temperature": 0,
            "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user_text}],
        })
        return data["choices"][0]["message"]["content"]

    raise LLMError(f"unknown provider {provider!r}")


def classify(provider: str, building: str, text: str, retries: int = 2) -> dict:
    """Return the model's raw JSON answer. Retries on network errors and bad JSON."""
    user_text = f"Building: {building}\nRequest: {text}"
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            return _extract_json(_call(provider, user_text))
        except (urllib.error.URLError, TimeoutError, LLMError, json.JSONDecodeError, KeyError) as exc:
            last_error = exc
            log.warning("LLM attempt %d failed: %s", attempt + 1, exc)
            time.sleep(1.5 * (attempt + 1))
    raise LLMError(f"LLM failed after {retries + 1} attempts: {last_error}")
