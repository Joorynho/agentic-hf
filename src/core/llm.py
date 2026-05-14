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
from collections import deque
from datetime import datetime, timezone

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
    SPECIALIST_BRIEFS = "specialist_briefs"
    PM_FINAL_AFTER_SPECIALISTS = "pm_final_after_specialists"
    COMMITTEE_REVIEW = "committee_review"
    DECISION_EVALUATION = "decision_evaluation"
    SHADOW_REPLAY = "shadow_replay"
    PORTFOLIO_CONSTRUCTION = "portfolio_construction"
    THESIS_MONITOR = "thesis_monitor"
    CALIBRATION = "calibration"


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
    LLMTask.SPECIALIST_BRIEFS: "strong",
    LLMTask.PM_FINAL_AFTER_SPECIALISTS: "strong",
    LLMTask.COMMITTEE_REVIEW: "strong",
    LLMTask.DECISION_EVALUATION: "default",
    LLMTask.SHADOW_REPLAY: "strong",
    LLMTask.PORTFOLIO_CONSTRUCTION: "strong",
    LLMTask.THESIS_MONITOR: "default",
    LLMTask.CALIBRATION: "default",
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
_llm_call_log: deque[dict] = deque(maxlen=250)


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


def _record_llm_call(
    *,
    provider: str,
    model: str,
    task: str,
    status: str,
    latency_ms: float,
    error: str = "",
    fallback_attempt: int = 0,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    total_tokens: int | None = None,
    cost_estimate: float | None = None,
    model_tier: str | None = None,
    model_selection_reason: str | None = None,
    budget_mode: str | None = None,
    fallback_path: str | None = None,
) -> None:
    """Store lightweight model observability for dashboard/debugging."""
    policy = model_policy_for_task(task)
    _llm_call_log.appendleft({
        "ts": datetime.now(timezone.utc).isoformat(),
        "provider": provider,
        "model": model,
        "task": task,
        "status": status,
        "latency_ms": round(float(latency_ms), 1),
        "error": str(error or "")[:500],
        "fallback_attempt": int(fallback_attempt or 0),
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "cost_estimate": cost_estimate,
        "model_tier": model_tier or policy["model_tier"],
        "model_selection_reason": model_selection_reason or policy["model_selection_reason"],
        "budget_mode": budget_mode or ("degraded" if (_openai_exhausted or _openrouter_exhausted) else "normal"),
        "fallback_path": fallback_path or (f"attempt:{fallback_attempt}" if fallback_attempt else ""),
    })


def _usage_payload(resp) -> dict:
    usage = getattr(resp, "usage", None)
    if not usage:
        return {}
    prompt = getattr(usage, "prompt_tokens", None)
    completion = getattr(usage, "completion_tokens", None)
    total = getattr(usage, "total_tokens", None)
    if total is None and (prompt is not None or completion is not None):
        total = int(prompt or 0) + int(completion or 0)
    return {
        "prompt_tokens": int(prompt or 0) if prompt is not None else None,
        "completion_tokens": int(completion or 0) if completion is not None else None,
        "total_tokens": int(total or 0) if total is not None else None,
    }


def _estimate_call_cost(provider: str, model: str, usage: dict) -> float | None:
    prompt = usage.get("prompt_tokens")
    completion = usage.get("completion_tokens")
    if prompt is None and completion is None:
        return None
    # Conservative dashboard estimate, USD per 1M tokens. Override exact
    # accounting later if provider billing export is wired in.
    model_l = str(model or "").lower()
    if provider == "openrouter" and ":free" in model_l:
        return 0.0
    if "gpt-5.2" in model_l or "gpt-5" == model_l:
        in_rate, out_rate = 1.25, 10.0
    elif "gpt-5-mini" in model_l or "mini" in model_l:
        in_rate, out_rate = 0.25, 2.0
    else:
        in_rate, out_rate = 0.50, 2.0
    return round(((float(prompt or 0) * in_rate) + (float(completion or 0) * out_rate)) / 1_000_000, 6)


def get_recent_llm_calls(limit: int = 100) -> list[dict]:
    """Return recent LLM call attempts, newest first."""
    limit = max(1, min(int(limit or 100), len(_llm_call_log) or 1))
    return list(_llm_call_log)[:limit]


def get_last_llm_call(task: str | None = None, success_only: bool = True) -> dict:
    """Return the latest LLM telemetry row for a task."""
    task_name = _normalize_task(task) if task else ""
    for row in _llm_call_log:
        if task_name and row.get("task") != task_name:
            continue
        if success_only and row.get("status") != "success":
            continue
        return dict(row)
    return {}


def get_llm_health_report(limit: int = 100) -> dict:
    """Aggregate model health for the dashboard."""
    rows = get_recent_llm_calls(limit)
    by_model: dict[str, dict] = {}
    by_task: dict[str, dict] = {}

    def bump(bucket: dict[str, dict], key: str, row: dict) -> None:
        if not key:
            key = "unknown"
        stat = bucket.setdefault(key, {
            "key": key,
            "calls": 0,
            "successes": 0,
            "failures": 0,
            "avg_latency_ms": 0.0,
            "last_status": "",
            "last_error": "",
            "last_seen": "",
        })
        stat["calls"] += 1
        if row.get("status") == "success":
            stat["successes"] += 1
        else:
            stat["failures"] += 1
        n = stat["calls"]
        stat["avg_latency_ms"] = round(
            ((float(stat["avg_latency_ms"]) * (n - 1)) + float(row.get("latency_ms") or 0.0)) / n,
            1,
        )
        stat["last_status"] = row.get("status", "")
        stat["last_error"] = row.get("error", "")
        stat["last_seen"] = row.get("ts", "")

    for row in rows:
        bump(by_model, f"{row.get('provider')}/{row.get('model')}", row)
        bump(by_task, str(row.get("task") or ""), row)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "provider_order": _provider_order(),
        "default_openai_model": _openai_default_model(),
        "strong_openai_model": _openai_strong_model(),
        "frontier_openai_model": _openai_frontier_model(),
        "openai_exhausted": _openai_exhausted,
        "openrouter_exhausted": _openrouter_exhausted,
        "by_model": sorted(by_model.values(), key=lambda x: x["calls"], reverse=True),
        "by_task": sorted(by_task.values(), key=lambda x: x["calls"], reverse=True),
        "recent": rows,
    }


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


def model_policy_for_task(task: str | None = None, risk_context: dict | None = None) -> dict:
    """Return model tier metadata for a task.

    This is intentionally lightweight: exact provider/model candidates remain
    below in provider-specific routing, while this function explains why a task
    deserves cheap/default/strong/frontier treatment.
    """
    task_name = _normalize_task(task)
    risk_context = risk_context or {}
    tier = _OPENAI_TASK_TIERS.get(task_name, "default")
    reason = f"task_policy:{task_name}"
    if risk_context.get("risk_increasing") and float(risk_context.get("notional", 0.0) or 0.0) >= 500:
        tier = "frontier" if tier == "strong" else tier
        reason += "; high_notional_risk_increasing"
    if risk_context.get("degraded_dependencies"):
        tier = "strong" if tier == "default" else tier
        reason += "; degraded_dependencies"
    return {
        "task": task_name,
        "model_tier": tier,
        "model_selection_reason": reason,
        "budget_mode": "degraded" if (_openai_exhausted or _openrouter_exhausted) else "normal",
    }


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
    tier = model_policy_for_task(task_name)["model_tier"]

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


def _positive_int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return max(1, int(raw))
    except ValueError:
        return default


def _is_gpt5_model(model: str) -> bool:
    return str(model or "").strip().lower().startswith("gpt-5")


def _gpt5_min_completion_tokens(task: str | None = None) -> int:
    task_name = _normalize_task(task)
    if task_name in {LLMTask.POSITION_REVIEW, LLMTask.LOSS_REVIEW}:
        return _positive_int_env("OPENAI_GPT5_FRONTIER_MIN_COMPLETION_TOKENS", 900)
    if task_name in {
        LLMTask.PM_DECISION,
        LLMTask.ARTICLE_DEEP_DIVE,
        LLMTask.THESIS_VERIFICATION,
        LLMTask.GOVERNANCE,
        LLMTask.ALLOCATION,
        LLMTask.THEME_SCAN,
    }:
        return _positive_int_env("OPENAI_GPT5_STRONG_MIN_COMPLETION_TOKENS", 700)
    return _positive_int_env("OPENAI_GPT5_DEFAULT_MIN_COMPLETION_TOKENS", 400)


def _openai_completion_budget(model: str, max_tokens: int, task: str | None = None) -> int:
    requested = max(1, int(max_tokens or 1))
    if _is_gpt5_model(model):
        return max(requested, _gpt5_min_completion_tokens(task))
    return requested


def _openai_token_limit_kwargs(model: str, max_tokens: int, task: str | None = None) -> dict[str, int]:
    """Return the correct token-limit parameter for the OpenAI chat API.

    GPT-5 chat-completions models reject `max_tokens` and require
    `max_completion_tokens`; older chat-completions models still use
    `max_tokens`. OpenRouter stays on `max_tokens` in its own call path.
    """
    budget = _openai_completion_budget(model, max_tokens, task)
    if _is_gpt5_model(model):
        return {"max_completion_tokens": budget}
    return {"max_tokens": budget}


def _text_from_content_part(part: object) -> str:
    if isinstance(part, str):
        return part
    if isinstance(part, dict):
        text = part.get("text")
        if isinstance(text, str):
            return text
        if isinstance(text, dict) and isinstance(text.get("value"), str):
            return text["value"]
        value = part.get("value")
        return value if isinstance(value, str) else ""
    text = getattr(part, "text", None)
    if isinstance(text, str):
        return text
    if isinstance(text, dict) and isinstance(text.get("value"), str):
        return text["value"]
    value = getattr(part, "value", None)
    return value if isinstance(value, str) else ""


def _extract_chat_completion_text(resp: object) -> str:
    """Extract text from OpenAI-compatible chat completion responses.

    Most responses expose `choices[0].message.content` as a string, but some
    SDK/provider combinations can return a list of text parts. Treat a 200 OK
    with no usable text as an empty response so the router can try the next
    model and record why it moved on.
    """
    choices = getattr(resp, "choices", None) or []
    if not choices:
        return ""
    message = getattr(choices[0], "message", None)
    if message is None:
        return ""
    content = getattr(message, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(_text_from_content_part(part) for part in content)
    if content is not None:
        return str(content)
    refusal = getattr(message, "refusal", None)
    return refusal if isinstance(refusal, str) else ""


def _try_openai(client, messages: list[dict], max_tokens: int, task: str, openai_module) -> str:
    global _openai_exhausted, _openai_reset
    last_error: Exception | None = None
    for attempt_idx, model in enumerate(openai_models_for_task(task)):
        started = time.perf_counter()
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=messages,
                **_openai_token_limit_kwargs(model, max_tokens, task),
            )
            text = _extract_chat_completion_text(resp).strip()
            usage = _usage_payload(resp)
            if text:
                _last_success_openai_model[task] = model
                _record_llm_call(
                    provider="openai",
                    model=model,
                    task=task,
                    status="success",
                    latency_ms=(time.perf_counter() - started) * 1000,
                    fallback_attempt=attempt_idx,
                    **usage,
                    cost_estimate=_estimate_call_cost("openai", model, usage),
                )
                logger.info("[llm] Success via OpenAI/%s task=%s", model, task)
                return text
            last_error = RuntimeError("OpenAI returned 200 OK but no message content text")
            _record_llm_call(
                provider="openai",
                model=model,
                task=task,
                status="empty_response",
                latency_ms=(time.perf_counter() - started) * 1000,
                error=str(last_error),
                fallback_attempt=attempt_idx,
            )
            logger.warning("[llm] OpenAI/%s returned empty response for task=%s", model, task)
            continue
        except openai_module.RateLimitError as exc:
            _openai_exhausted = True
            _openai_reset = time.time() + _cooldown_seconds("OPENAI_COOLDOWN_SECONDS", 3600)
            _record_llm_call(
                provider="openai",
                model=model,
                task=task,
                status="rate_limited",
                latency_ms=(time.perf_counter() - started) * 1000,
                error=str(exc),
                fallback_attempt=attempt_idx,
            )
            logger.error("[llm] OpenAI quota/rate-limit hit; cooling down: %s", exc)
            last_error = exc
            break
        except openai_module.APIStatusError as exc:
            last_error = exc
            status = getattr(exc, "status_code", None)
            record_status = "unavailable" if status in {400, 404} else "failed"
            _record_llm_call(
                provider="openai",
                model=model,
                task=task,
                status=record_status,
                latency_ms=(time.perf_counter() - started) * 1000,
                error=str(exc),
                fallback_attempt=attempt_idx,
            )
            if status in {400, 404}:
                logger.warning("[llm] OpenAI/%s unavailable for task=%s: %s", model, task, exc)
                continue
            logger.error("[llm] OpenAI/%s failed for task=%s: %s", model, task, exc)
            continue
        except Exception as exc:
            last_error = exc
            _record_llm_call(
                provider="openai",
                model=model,
                task=task,
                status="failed",
                latency_ms=(time.perf_counter() - started) * 1000,
                error=str(exc),
                fallback_attempt=attempt_idx,
            )
            logger.error("[llm] OpenAI/%s failed for task=%s: %s", model, task, exc)
            continue
    if last_error:
        raise RuntimeError(f"OpenAI failed for task={task}: {last_error}") from last_error
    raise RuntimeError(f"No OpenAI model candidates for task={task}")


def _try_openrouter(client, messages: list[dict], max_tokens: int, task: str, openai_module) -> str:
    global _last_success_model, _openrouter_exhausted, _openrouter_reset
    rate_limit_count = 0
    last_error: Exception | None = None
    for attempt_idx, model in enumerate(openrouter_models_for_task(task)):
        started = time.perf_counter()
        try:
            resp = client.chat.completions.create(
                model=model, max_tokens=max_tokens, messages=messages,
            )
            text = _extract_chat_completion_text(resp).strip()
            usage = _usage_payload(resp)
            if text:
                _last_success_model = model
                _record_llm_call(
                    provider="openrouter",
                    model=model,
                    task=task,
                    status="success",
                    latency_ms=(time.perf_counter() - started) * 1000,
                    fallback_attempt=attempt_idx,
                    **usage,
                    cost_estimate=_estimate_call_cost("openrouter", model, usage),
                )
                logger.info("[llm] Success via OpenRouter/%s task=%s", model, task)
                return text
            last_error = RuntimeError("OpenRouter returned 200 OK but no message content text")
            _record_llm_call(
                provider="openrouter",
                model=model,
                task=task,
                status="empty_response",
                latency_ms=(time.perf_counter() - started) * 1000,
                error=str(last_error),
                fallback_attempt=attempt_idx,
            )
            logger.debug("[llm] OpenRouter/%s returned empty response for task=%s", model, task)
            continue
        except (openai_module.RateLimitError, openai_module.APIStatusError) as exc:
            last_error = exc
            err_str = str(getattr(exc, "body", "") or "")
            status = getattr(exc, "status_code", None)
            record_status = "unavailable" if status in {400, 404} else "rate_limited"
            _record_llm_call(
                provider="openrouter",
                model=model,
                task=task,
                status=record_status,
                latency_ms=(time.perf_counter() - started) * 1000,
                error=str(exc),
                fallback_attempt=attempt_idx,
            )
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
            _record_llm_call(
                provider="openrouter",
                model=model,
                task=task,
                status="failed",
                latency_ms=(time.perf_counter() - started) * 1000,
                error=str(exc),
                fallback_attempt=attempt_idx,
            )
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
