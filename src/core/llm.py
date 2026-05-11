"""Shared LLM client helper with task-adaptive model routing.

Direct OpenAI calls default to GPT-5 mini. Higher-stakes reasoning tasks can
route to stronger models from one central policy, while OpenRouter remains a
fallback/provider option.
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

OPENAI_DEFAULT_MODEL = "gpt-5-mini"
OPENAI_STRONG_MODEL = "gpt-5"
OPENAI_FRONTIER_MODEL = "gpt-5.2"


class LLMTask:
    """Stable task labels for model routing."""

    DEFAULT = "default"
    SENTIMENT = "sentiment"
    RESEARCH = "research"
    THEME_SCAN = "theme_scan"
    THEME_VALIDATION = "theme_validation"
    PM_DECISION = "pm_decision"
    PM_REVISION = "pm_revision"
    ARTICLE_DEEP_DIVE = "article_deep_dive"
    THESIS_VERIFICATION = "thesis_verification"
    GOVERNANCE = "governance"
    ALLOCATION = "allocation"
    POSITION_REVIEW = "position_review"
    LOSS_REVIEW = "loss_review"


_OPENAI_TASK_TIERS = {
    LLMTask.SENTIMENT: "default",
    LLMTask.RESEARCH: "default",
    LLMTask.THEME_SCAN: "strong",
    LLMTask.THEME_VALIDATION: "default",
    LLMTask.PM_REVISION: "default",
    LLMTask.PM_DECISION: "strong",
    LLMTask.ARTICLE_DEEP_DIVE: "strong",
    LLMTask.THESIS_VERIFICATION: "strong",
    LLMTask.GOVERNANCE: "strong",
    LLMTask.ALLOCATION: "strong",
    LLMTask.POSITION_REVIEW: "frontier",
    LLMTask.LOSS_REVIEW: "frontier",
}

# Backwards-compatible name for older imports/tests. The value now points at
# the GPT-5 mini default.
OPENAI_FALLBACK_MODEL = os.getenv("OPENAI_MODEL", OPENAI_DEFAULT_MODEL)

_last_success_model: str | None = None
_last_success_openai_model: dict[str, str] = {}
_openrouter_exhausted = False
_openrouter_reset: float = 0.0
_openai_exhausted = False
_openai_reset: float = 0.0


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _cooldown_seconds(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return max(1, int(raw))
    except ValueError:
        return default


def _normalize_task(task: str | None) -> str:
    value = (task or LLMTask.DEFAULT).strip().lower().replace("-", "_").replace(" ", "_")
    return value or LLMTask.DEFAULT


def _env_model_name(prefix: str, task: str) -> str:
    return os.getenv(f"{prefix}_{task.upper()}", "").strip()


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        item = (item or "").strip()
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _openai_default_model() -> str:
    return (
        os.getenv("OPENAI_MODEL_DEFAULT")
        or os.getenv("OPENAI_MODEL")
        or OPENAI_DEFAULT_MODEL
    ).strip()


def _openai_strong_model() -> str:
    return (
        os.getenv("OPENAI_MODEL_STRONG")
        or os.getenv("OPENAI_MODEL_REASONING")
        or OPENAI_STRONG_MODEL
    ).strip()


def _openai_frontier_model() -> str:
    return (
        os.getenv("OPENAI_MODEL_FRONTIER")
        or os.getenv("OPENAI_MODEL_DEEP_REASONING")
        or os.getenv("OPENAI_MODEL_REASONING")
        or OPENAI_FRONTIER_MODEL
    ).strip()


def openai_models_for_task(task: str | None = None) -> list[str]:
    """Return ordered OpenAI model candidates for a task.

    Environment overrides:
    - OPENAI_MODEL_<TASK>, e.g. OPENAI_MODEL_PM_DECISION
    - OPENAI_MODEL_DEFAULT / OPENAI_MODEL for the GPT-5 mini tier
    - OPENAI_MODEL_STRONG / OPENAI_MODEL_REASONING for stronger tasks
    - OPENAI_MODEL_FRONTIER for review/escalation tasks
    """
    task_name = _normalize_task(task)
    explicit = _env_model_name("OPENAI_MODEL", task_name)
    default_model = _openai_default_model()
    strong_model = _openai_strong_model()
    frontier_model = _openai_frontier_model()
    tier = _OPENAI_TASK_TIERS.get(task_name, "default")

    if tier == "frontier":
        models = [explicit, _last_success_openai_model.get(task_name, ""), frontier_model, strong_model, default_model]
    elif tier == "strong":
        models = [explicit, _last_success_openai_model.get(task_name, ""), strong_model, default_model]
    else:
        models = [explicit, _last_success_openai_model.get(task_name, ""), default_model]
    return _dedupe(models)


def openrouter_models_for_task(task: str | None = None) -> list[str]:
    """Return ordered OpenRouter model candidates for a task."""
    task_name = _normalize_task(task)
    explicit = _env_model_name("OPENROUTER_MODEL", task_name)
    preferred = os.getenv("OPENROUTER_MODEL", "google/gemma-3-27b-it:free")
    models_to_try = [explicit, preferred]
    if _last_success_model:
        models_to_try.append(_last_success_model)
    models_to_try.extend(FREE_MODELS)
    return _dedupe(models_to_try)


def _provider_order() -> list[str]:
    raw = os.getenv("LLM_PROVIDER_ORDER", "").strip()
    if raw:
        order = [part.strip().lower() for part in raw.split(",") if part.strip()]
        return [provider for provider in order if provider in {"openai", "openrouter"}] or ["openai", "openrouter"]
    if os.getenv("OPENAI_API_KEY"):
        return ["openai", "openrouter"]
    return ["openrouter", "openai"]


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
    """Legacy helper; returns the first client in the configured provider order."""
    for provider in _provider_order():
        if provider == "openai":
            client = _get_openai_client()
            if client:
                return client
        if provider == "openrouter":
            client = _get_openrouter_client()
            if client:
                return client
    return None


def get_llm_client():
    """Return (openai.OpenAI client, model_name) configured for the best available provider."""
    for provider in _provider_order():
        if provider == "openai":
            oai_client = _get_openai_client()
            if oai_client and not _openai_exhausted:
                return oai_client, openai_models_for_task(LLMTask.DEFAULT)[0]
        if provider == "openrouter":
            or_client = _get_openrouter_client()
            if or_client and not _openrouter_exhausted:
                return or_client, openrouter_models_for_task(LLMTask.DEFAULT)[0]
    import openai
    return openai.OpenAI(api_key="missing", max_retries=0), OPENAI_DEFAULT_MODEL


def has_llm_key() -> bool:
    if not _env_bool("MISSION_CONTROL_USE_LLM", default=True):
        return False
    return bool(os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY"))


def _try_openai(client, messages: list[dict], max_tokens: int, task: str, openai_module) -> str:
    global _openai_exhausted, _openai_reset
    last_error: Exception | None = None
    for model in openai_models_for_task(task):
        try:
            resp = client.chat.completions.create(
                model=model, max_tokens=max_tokens, messages=messages,
            )
            text = resp.choices[0].message.content
            if text:
                _last_success_openai_model[task] = model
                logger.info("[llm] Success via OpenAI/%s task=%s", model, task)
                return text
        except openai_module.RateLimitError as exc:
            _openai_exhausted = True
            _openai_reset = time.time() + _cooldown_seconds("OPENAI_COOLDOWN_SECONDS", 3600)
            logger.error("[llm] OpenAI quota/rate-limit hit; cooling down: %s", exc)
            last_error = exc
            break
        except openai_module.APIStatusError as exc:
            last_error = exc
            status = getattr(exc, "status_code", None)
            if status in {400, 404}:
                logger.warning("[llm] OpenAI/%s unavailable for task=%s: %s", model, task, exc)
                continue
            logger.error("[llm] OpenAI/%s failed for task=%s: %s", model, task, exc)
            continue
        except Exception as exc:
            last_error = exc
            logger.error("[llm] OpenAI/%s failed for task=%s: %s", model, task, exc)
            continue
    if last_error:
        raise RuntimeError(f"OpenAI failed for task={task}: {last_error}") from last_error
    raise RuntimeError(f"No OpenAI model candidates for task={task}")


def _try_openrouter(client, messages: list[dict], max_tokens: int, task: str, openai_module) -> str:
    global _last_success_model, _openrouter_exhausted, _openrouter_reset
    rate_limit_count = 0
    last_error: Exception | None = None
    for model in openrouter_models_for_task(task):
        try:
            resp = client.chat.completions.create(
                model=model, max_tokens=max_tokens, messages=messages,
            )
            text = resp.choices[0].message.content
            if text:
                _last_success_model = model
                logger.info("[llm] Success via OpenRouter/%s task=%s", model, task)
                return text
        except (openai_module.RateLimitError, openai_module.APIStatusError) as exc:
            last_error = exc
            err_str = str(getattr(exc, "body", "") or "")
            status = getattr(exc, "status_code", None)
            if status in {400, 404}:
                logger.debug("[llm] OpenRouter/%s unavailable for task=%s: %s", model, task, exc)
                continue
            if "per-day" in err_str:
                _openrouter_exhausted = True
                _openrouter_reset = time.time() + 3600
                logger.warning("[llm] OpenRouter daily limit hit; trying next provider")
                break
            rate_limit_count += 1
            if rate_limit_count >= 3:
                _openrouter_exhausted = True
                _openrouter_reset = time.time() + _cooldown_seconds("OPENROUTER_COOLDOWN_SECONDS", 900)
                logger.warning("[llm] 3+ OpenRouter models rate-limited; cooling down")
                break
            time.sleep(0.05)
        except Exception as exc:
            last_error = exc
            logger.debug("[llm] OpenRouter/%s failed for task=%s: %s", model, task, exc)
    if last_error:
        raise RuntimeError(f"OpenRouter failed for task={task}: {last_error}") from last_error
    raise RuntimeError(f"No OpenRouter model candidates for task={task}")


def llm_chat(messages: list[dict], max_tokens: int = 300, task: str | None = None) -> str:
    """Make an LLM call through the task router.

    Returns the raw response text. Raises on total failure.
    """
    global _openrouter_exhausted, _openrouter_reset
    global _openai_exhausted, _openai_reset
    import openai

    if not _env_bool("MISSION_CONTROL_USE_LLM", default=True):
        raise RuntimeError("LLM calls are disabled by MISSION_CONTROL_USE_LLM=false")

    task_name = _normalize_task(task)

    # Reset provider cooldowns after their window expires.
    if _openrouter_exhausted and time.time() >= _openrouter_reset:
        _openrouter_exhausted = False
    if _openai_exhausted and time.time() >= _openai_reset:
        _openai_exhausted = False

    or_client = _get_openrouter_client()
    oai_client = _get_openai_client()
    errors: list[str] = []

    for provider in _provider_order():
        if provider == "openai":
            if not oai_client:
                continue
            if _openai_exhausted:
                logger.warning("[llm] OpenAI temporarily disabled after quota/rate-limit failure")
                continue
            try:
                return _try_openai(oai_client, messages, max_tokens, task_name, openai)
            except Exception as exc:
                errors.append(str(exc))
                continue
        if provider == "openrouter":
            if not or_client or _openrouter_exhausted:
                continue
            try:
                return _try_openrouter(or_client, messages, max_tokens, task_name, openai)
            except Exception as exc:
                errors.append(str(exc))
                continue

    detail = "; ".join(errors[-3:]) if errors else "set OPENAI_API_KEY or OPENROUTER_API_KEY"
    raise RuntimeError(f"No LLM provider available for task={task_name} - {detail}")


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

    # Attempt to repair truncated JSON by closing open strings/braces/brackets.
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
        if ch == "\\" and in_string:
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch in ("{", "["):
            stack.append("}" if ch == "{" else "]")
        elif ch in ("}", "]") and stack and stack[-1] == ch:
            stack.pop()
    repaired += "".join(reversed(stack))

    try:
        return _ensure_dict(json.loads(repaired))
    except json.JSONDecodeError:
        pass

    # Find the outermost balanced { ... } block.
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

    # Fallback: find innermost { ... } block.
    brace_match = re.search(r"\{[^{}]*\}", text, re.DOTALL)
    if brace_match:
        try:
            return _ensure_dict(json.loads(brace_match.group(0)))
        except json.JSONDecodeError:
            pass

    raise json.JSONDecodeError("Could not extract JSON from LLM output", text, 0)
