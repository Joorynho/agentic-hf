"""Shared LLM client helper for OpenRouter (OpenAI-compatible).

Provides automatic retry with model rotation across free-tier models.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time

logger = logging.getLogger(__name__)

FREE_MODELS = [
    "google/gemma-3-27b-it:free",
    "qwen/qwen3-next-80b-a3b-instruct:free",
    "mistralai/mistral-small-3.1-24b-instruct:free",
    "nvidia/nemotron-3-nano-30b-a3b:free",
    "meta-llama/llama-3.3-70b-instruct:free",
    "nousresearch/hermes-3-llama-3.1-405b:free",
    "qwen/qwen3-coder:free",
    "google/gemma-3-12b-it:free",
]

_last_success_model: str | None = None


def _get_client():
    import openai
    api_key = os.getenv("OPENROUTER_API_KEY", "") or os.getenv("OPENAI_API_KEY", "")
    base_url = "https://openrouter.ai/api/v1" if os.getenv("OPENROUTER_API_KEY") else None
    kwargs = {"api_key": api_key, "max_retries": 0, "timeout": 15.0}
    if base_url:
        kwargs["base_url"] = base_url
    return openai.OpenAI(**kwargs)


def get_llm_client():
    """Return (openai.OpenAI client, model_name) configured for OpenRouter."""
    model = os.getenv("OPENROUTER_MODEL", "google/gemma-3-27b-it:free")
    return _get_client(), model


def has_llm_key() -> bool:
    return bool(os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY"))


_daily_limit_hit = False
_daily_limit_reset: float = 0.0


def llm_chat(messages: list[dict], max_tokens: int = 300) -> str:
    """Make an LLM call with automatic retry + model rotation on rate limits.

    Fails fast if the daily free-tier limit has been hit.
    Returns the raw response text. Raises on total failure.
    """
    global _last_success_model, _daily_limit_hit, _daily_limit_reset
    import openai

    if _daily_limit_hit and time.time() < _daily_limit_reset:
        raise RuntimeError("OpenRouter daily free-tier limit exhausted — skipping LLM call")

    _daily_limit_hit = False

    client = _get_client()
    preferred = os.getenv("OPENROUTER_MODEL", "google/gemma-3-27b-it:free")

    models_to_try = [preferred]
    if _last_success_model and _last_success_model != preferred:
        models_to_try.insert(0, _last_success_model)
    for m in FREE_MODELS:
        if m not in models_to_try:
            models_to_try.append(m)

    last_err = None
    rate_limit_count = 0
    for model in models_to_try:
        try:
            resp = client.chat.completions.create(
                model=model,
                max_tokens=max_tokens,
                messages=messages,
            )
            text = resp.choices[0].message.content
            if text:
                _last_success_model = model
                logger.info("[llm] Success via %s", model)
                return text
        except (openai.RateLimitError, openai.APIStatusError) as exc:
            err_str = str(getattr(exc, "body", "") or "")
            if "per-day" in err_str:
                _daily_limit_hit = True
                _daily_limit_reset = time.time() + 3600
                logger.warning("[llm] Daily free-tier limit hit — skipping all LLM calls for 1 hour")
                raise RuntimeError("OpenRouter daily free-tier limit exhausted") from exc
            rate_limit_count += 1
            last_err = exc
            if rate_limit_count >= 3:
                logger.warning("[llm] 3+ models rate-limited, giving up early")
                break
            time.sleep(0.2)
        except Exception as exc:
            last_err = exc
            logger.debug("[llm] %s failed: %s", model, exc)

    raise RuntimeError(f"All LLM models failed. Last error: {last_err}")


_JSON_BLOCK = re.compile(r"```(?:json)?\s*\n?(.*?)```", re.DOTALL)


def extract_json(text: str) -> dict:
    """Parse JSON from LLM output, handling markdown fences and truncated output."""
    if text is None:
        raise ValueError("LLM returned empty response")
    text = text.strip()
    m = _JSON_BLOCK.search(text)
    if m:
        text = m.group(1).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Attempt to repair truncated JSON by closing open strings/braces
    repaired = text
    if repaired.count('"') % 2 == 1:
        repaired += '"'
    open_braces = repaired.count("{") - repaired.count("}")
    repaired += "}" * max(open_braces, 0)
    open_brackets = repaired.count("[") - repaired.count("]")
    repaired += "]" * max(open_brackets, 0)

    try:
        return json.loads(repaired)
    except json.JSONDecodeError:
        pass

    # Last resort: find first { ... } block
    brace_match = re.search(r"\{[^{}]*\}", text, re.DOTALL)
    if brace_match:
        return json.loads(brace_match.group(0))

    raise json.JSONDecodeError("Could not extract JSON from LLM output", text, 0)
