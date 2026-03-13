"""Shared LLM client helper — OpenRouter + OpenAI fallback.

Tries OpenRouter free-tier models first. If rate-limited, falls back to
direct OpenAI API using OPENAI_API_KEY with gpt-4o-mini.
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

OPENAI_FALLBACK_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

_last_success_model: str | None = None


def _get_openrouter_client():
    import openai
    api_key = os.getenv("OPENROUTER_API_KEY", "")
    if not api_key:
        return None
    return openai.OpenAI(
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1",
        max_retries=0,
        timeout=15.0,
    )


def _get_openai_client():
    import openai
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        return None
    return openai.OpenAI(api_key=api_key, max_retries=0, timeout=30.0)


def _get_client():
    """Legacy helper — returns whichever client is available (OpenRouter preferred)."""
    return _get_openrouter_client() or _get_openai_client()


def get_llm_client():
    """Return (openai.OpenAI client, model_name) configured for the best available provider."""
    or_client = _get_openrouter_client()
    if or_client:
        model = os.getenv("OPENROUTER_MODEL", "google/gemma-3-27b-it:free")
        return or_client, model
    oai_client = _get_openai_client()
    if oai_client:
        return oai_client, OPENAI_FALLBACK_MODEL
    import openai
    return openai.OpenAI(api_key="missing", max_retries=0), "gpt-4o-mini"


def has_llm_key() -> bool:
    return bool(os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY"))


_openrouter_exhausted = False
_openrouter_reset: float = 0.0


def llm_chat(messages: list[dict], max_tokens: int = 300) -> str:
    """Make an LLM call. Tries OpenRouter free models first, falls back to OpenAI.

    Returns the raw response text. Raises on total failure.
    """
    global _last_success_model, _openrouter_exhausted, _openrouter_reset
    import openai

    # Reset OpenRouter exhaustion after cooldown
    if _openrouter_exhausted and time.time() >= _openrouter_reset:
        _openrouter_exhausted = False

    or_client = _get_openrouter_client()
    oai_client = _get_openai_client()

    # --- Phase 1: Try OpenRouter free models ---
    if or_client and not _openrouter_exhausted:
        preferred = os.getenv("OPENROUTER_MODEL", "google/gemma-3-27b-it:free")
        models_to_try = [preferred]
        if _last_success_model and _last_success_model not in models_to_try:
            models_to_try.insert(0, _last_success_model)
        for m in FREE_MODELS:
            if m not in models_to_try:
                models_to_try.append(m)

        rate_limit_count = 0
        for model in models_to_try:
            try:
                resp = or_client.chat.completions.create(
                    model=model, max_tokens=max_tokens, messages=messages,
                )
                text = resp.choices[0].message.content
                if text:
                    _last_success_model = model
                    logger.info("[llm] Success via OpenRouter/%s", model)
                    return text
            except (openai.RateLimitError, openai.APIStatusError) as exc:
                err_str = str(getattr(exc, "body", "") or "")
                if "per-day" in err_str:
                    _openrouter_exhausted = True
                    _openrouter_reset = time.time() + 3600
                    logger.warning("[llm] OpenRouter daily limit hit — falling back to OpenAI")
                    break
                rate_limit_count += 1
                if rate_limit_count >= 3:
                    logger.warning("[llm] 3+ OpenRouter models rate-limited, trying OpenAI")
                    break
                time.sleep(0.2)
            except Exception as exc:
                logger.debug("[llm] OpenRouter/%s failed: %s", model, exc)

    # --- Phase 2: Fallback to direct OpenAI ---
    if oai_client:
        try:
            resp = oai_client.chat.completions.create(
                model=OPENAI_FALLBACK_MODEL, max_tokens=max_tokens, messages=messages,
            )
            text = resp.choices[0].message.content
            if text:
                logger.info("[llm] Success via OpenAI/%s", OPENAI_FALLBACK_MODEL)
                return text
        except Exception as exc:
            logger.error("[llm] OpenAI fallback failed: %s", exc)
            raise RuntimeError(f"OpenAI fallback failed: {exc}") from exc

    raise RuntimeError("No LLM provider available — set OPENROUTER_API_KEY or OPENAI_API_KEY")


_JSON_BLOCK = re.compile(r"```(?:json)?\s*\n?(.*?)```", re.DOTALL)


def _ensure_dict(val: object) -> dict:
    """Coerce a parsed JSON value into a dict."""
    if isinstance(val, dict):
        return val
    if isinstance(val, list):
        return {"items": val}
    return {"value": val}


def extract_json(text: str) -> dict:
    """Parse JSON from LLM output, handling markdown fences and truncated output."""
    if text is None:
        raise ValueError("LLM returned empty response")
    text = text.strip()
    m = _JSON_BLOCK.search(text)
    if m:
        text = m.group(1).strip()

    try:
        return _ensure_dict(json.loads(text))
    except json.JSONDecodeError:
        pass

    # Attempt to repair truncated JSON by closing open strings/braces/brackets
    repaired = text
    if repaired.count('"') % 2 == 1:
        repaired += '"'
    stack: list[str] = []
    in_string = False
    escape = False
    for ch in repaired:
        if escape:
            escape = False
            continue
        if ch == '\\' and in_string:
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch in ('{', '['):
            stack.append('}' if ch == '{' else ']')
        elif ch in ('}', ']') and stack and stack[-1] == ch:
            stack.pop()
    repaired += ''.join(reversed(stack))

    try:
        return _ensure_dict(json.loads(repaired))
    except json.JSONDecodeError:
        pass

    # Find the outermost balanced { ... } block (handles nested braces)
    start = text.find("{")
    if start >= 0:
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return _ensure_dict(json.loads(text[start:i + 1]))
                    except json.JSONDecodeError:
                        break

    # Fallback: find innermost { ... } block
    brace_match = re.search(r"\{[^{}]*\}", text, re.DOTALL)
    if brace_match:
        try:
            return _ensure_dict(json.loads(brace_match.group(0)))
        except json.JSONDecodeError:
            pass

    raise json.JSONDecodeError("Could not extract JSON from LLM output", text, 0)
