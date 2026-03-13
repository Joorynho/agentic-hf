"""Sentiment scoring for financial news — LLM-powered with keyword fallback.

Primary path: batch-scores headlines and predictions via a single LLM call,
returning per-item sentiment (-1 to +1), relevancy (0-1), and impact (0-1).

Fallback path: keyword-based scoring when no LLM key is available.
Used by signal agents (LLM batch), and by RSS/GDELT/X adapters (keyword).
"""
from __future__ import annotations

import hashlib
import json
import logging
import time

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Keyword fallback lists (softened -- ambiguous words removed)
# ---------------------------------------------------------------------------

BULLISH_WORDS: list[str] = [
    "rally", "surge", "breakout", "bullish", "upside", "beat", "strong",
    "growth", "soar", "boom", "gain", "record high", "all-time high",
    "recovery", "optimism", "dovish", "easing", "stimulus", "upgrade",
    "outperform", "accelerat", "expand", "green shoots",
]

BEARISH_WORDS: list[str] = [
    "crash", "plunge", "bearish", "downside", "miss", "weak", "recession",
    "crisis", "collapse", "sell-off", "selloff", "tumble", "slump",
    "fear", "hawkish", "tightening", "downgrade", "default",
    "underperform", "inflation surge", "rate hike", "layoff", "bankruptcy",
]


def compute_keyword_sentiment(text: str) -> float:
    """Keyword-based sentiment scoring, clamped to [-1, +1].

    Counts bullish vs bearish keyword hits in lowercased text.
    Returns (bullish - bearish) / total_hits, or 0.0 if no hits.
    """
    lower = text.lower()
    bullish = sum(1 for w in BULLISH_WORDS if w in lower)
    bearish = sum(1 for w in BEARISH_WORDS if w in lower)
    total = bullish + bearish
    if total == 0:
        return 0.0
    return max(-1.0, min(1.0, (bullish - bearish) / total))


def sentiment_label(score: float) -> str:
    """Map a sentiment score to a human-readable label."""
    if score > 0.1:
        return "bullish"
    elif score < -0.1:
        return "bearish"
    return "neutral"


# ---------------------------------------------------------------------------
# LLM batch scorer
# ---------------------------------------------------------------------------

_SCORE_SYSTEM = """You are a financial market sentiment analyst. Score each item for:
1. sentiment: float from -1.0 (very bearish) to +1.0 (very bullish). 0.0 = neutral.
   IMPORTANT: Read context carefully. "risk easing" is bullish. "rate cut" is bullish.
   "inflation falls" is bullish. Don't just flag negative-sounding words as bearish.
2. relevancy: float 0.0 to 1.0 — how relevant to {pod_name} trading specifically.
3. impact: float 0.0 to 1.0 — how likely to move markets. Major policy/earnings = high. Routine = low.

Return ONLY a JSON array with one object per input item, in the same order.
Each object: {{"sentiment": float, "relevancy": float, "impact": float}}
No explanations, no markdown fences, just the JSON array."""

_CACHE: dict[str, tuple[float, list[dict]]] = {}
_CACHE_TTL = 600  # 10 minutes


def _build_scoring_prompt(items: list[dict], pod_name: str) -> list[dict]:
    """Build the LLM messages for batch sentiment scoring."""
    system = _SCORE_SYSTEM.replace("{pod_name}", pod_name)

    lines = []
    for i, item in enumerate(items):
        item_type = item.get("type", "headline")
        text = item.get("text", "")
        lines.append(f"{i+1}. [{item_type}] {text}")

    user_content = "\n".join(lines)
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user_content},
    ]


import re as _re

_JSON_BLOCK_RE = _re.compile(r"```(?:json)?\s*\n?(.*?)```", _re.DOTALL)


def _parse_scores(raw: str, count: int) -> list[dict]:
    """Parse LLM response into a list of score dicts.

    Handles: plain JSON arrays, markdown-fenced JSON, JSON with surrounding
    text, truncated arrays, and dict wrappers.
    """
    raw = raw.strip()

    # Strip markdown fences
    m = _JSON_BLOCK_RE.search(raw)
    if m:
        raw = m.group(1).strip()

    # Try direct parse first
    parsed = None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Try to find the outermost [ ... ] array
    if parsed is None:
        start = raw.find("[")
        if start >= 0:
            depth = 0
            for i in range(start, len(raw)):
                if raw[i] == "[":
                    depth += 1
                elif raw[i] == "]":
                    depth -= 1
                    if depth == 0:
                        try:
                            parsed = json.loads(raw[start:i + 1])
                        except json.JSONDecodeError:
                            pass
                        break

    # Try to repair truncated JSON by closing open brackets
    if parsed is None:
        attempt = raw
        if attempt.count('"') % 2 == 1:
            attempt += '"'
        open_b = attempt.count("[") - attempt.count("]")
        open_c = attempt.count("{") - attempt.count("}")
        attempt += "}" * max(0, open_c) + "]" * max(0, open_b)
        try:
            parsed = json.loads(attempt)
        except json.JSONDecodeError:
            pass

    if parsed is None:
        raise json.JSONDecodeError("Could not parse LLM sentiment scores", raw, 0)

    if isinstance(parsed, dict):
        parsed = parsed.get("items", parsed.get("scores", [parsed]))
    if not isinstance(parsed, list):
        parsed = [parsed]

    results = []
    for item in parsed[:count]:
        if not isinstance(item, dict):
            results.append({"sentiment": 0.0, "relevancy": 0.5, "impact": 0.3})
            continue
        results.append({
            "sentiment": max(-1.0, min(1.0, float(item.get("sentiment", 0.0)))),
            "relevancy": max(0.0, min(1.0, float(item.get("relevancy", 0.5)))),
            "impact": max(0.0, min(1.0, float(item.get("impact", 0.3)))),
        })

    while len(results) < count:
        results.append({"sentiment": 0.0, "relevancy": 0.5, "impact": 0.3})

    return results


def _cache_key(items: list[dict], pod_name: str) -> str:
    """Deterministic cache key from items + pod."""
    payload = pod_name + "|" + "|".join(i.get("text", "")[:100] for i in items)
    return hashlib.sha256(payload.encode()).hexdigest()[:24]


def llm_score_batch(items: list[dict], pod_name: str) -> list[dict]:
    """Score a batch of items via LLM. Returns list of score dicts.

    Each input item: {"type": "headline"|"prediction", "text": str}
    Each output: {"sentiment": float, "relevancy": float, "impact": float}

    Raises RuntimeError if no LLM is available.
    """
    if not items:
        return []

    # Check cache
    key = _cache_key(items, pod_name)
    now = time.time()
    if key in _CACHE:
        cached_time, cached_scores = _CACHE[key]
        if now - cached_time < _CACHE_TTL:
            logger.debug("[sentiment] Cache hit for %s (%d items)", pod_name, len(items))
            return cached_scores

    from src.core.llm import llm_chat
    messages = _build_scoring_prompt(items, pod_name)
    raw = llm_chat(messages, max_tokens=2000)
    scores = _parse_scores(raw, len(items))

    _CACHE[key] = (now, scores)

    # Evict stale entries
    stale = [k for k, (t, _) in _CACHE.items() if now - t > _CACHE_TTL * 2]
    for k in stale:
        del _CACHE[k]

    return scores


def _keyword_fallback_scores(items: list[dict]) -> list[dict]:
    """Score items using keyword fallback only."""
    results = []
    for item in items:
        text = item.get("text", "")
        sent = compute_keyword_sentiment(text)
        results.append({
            "sentiment": sent,
            "relevancy": 0.5,
            "impact": 0.3,
        })
    return results


def score_items(
    headlines: list[dict],
    predictions: list[dict],
    pod_name: str,
) -> tuple[list[dict], list[dict]]:
    """Score headlines and predictions. LLM first, keyword fallback.

    Args:
        headlines: list of {"title": str, "source": str, ...}
        predictions: list of {"question": str, "probability": float, ...}
        pod_name: asset class name (equities, fx, crypto, commodities)

    Returns:
        (scored_headlines, scored_predictions) — same dicts with
        sentiment, relevancy, impact, sentiment_label added.
    """
    batch_items = []
    for h in headlines:
        batch_items.append({"type": "headline", "text": h.get("title", "")})
    for p in predictions:
        prob = p.get("probability", 0.5)
        batch_items.append({
            "type": "prediction",
            "text": f"{p.get('question', '?')} (probability: {prob:.0%})",
        })

    if not batch_items:
        return headlines, predictions

    from src.core.llm import has_llm_key

    try:
        if has_llm_key():
            scores = llm_score_batch(batch_items, pod_name)
            logger.info("[sentiment] LLM scored %d items for %s", len(batch_items), pod_name)
        else:
            scores = _keyword_fallback_scores(batch_items)
            logger.info("[sentiment] Keyword fallback for %d items (%s)", len(batch_items), pod_name)
    except Exception as exc:
        logger.warning("[sentiment] LLM scoring failed, using keyword fallback: %s", exc)
        scores = _keyword_fallback_scores(batch_items)

    # Apply scores back to headline dicts
    for i, h in enumerate(headlines):
        if i < len(scores):
            s = scores[i]
            h["sentiment"] = s["sentiment"]
            h["relevancy"] = s["relevancy"]
            h["impact"] = s["impact"]
            h["sentiment_label"] = sentiment_label(s["sentiment"])

    # Apply scores to prediction dicts
    offset = len(headlines)
    for j, p in enumerate(predictions):
        idx = offset + j
        if idx < len(scores):
            s = scores[idx]
            p["sentiment"] = s["sentiment"]
            p["relevancy"] = s["relevancy"]
            p["impact"] = s["impact"]
            p["sentiment_label"] = sentiment_label(s["sentiment"])

    return headlines, predictions
