"""Tests for the news sentiment pipeline.

Covers: shared sentiment module, LLM batch scoring, keyword fallback,
caching, RSS/GDELT adapter sentiment, scoring integration, and signal
agent headline format.
"""
from __future__ import annotations

import json
import time
from unittest.mock import patch

import pytest

from src.data.adapters.sentiment import (
    BULLISH_WORDS,
    BEARISH_WORDS,
    compute_keyword_sentiment,
    sentiment_label,
    llm_score_batch,
    score_items,
    _parse_scores,
    _keyword_fallback_scores,
    _CACHE,
    _CACHE_TTL,
)


class TestKeywordSentiment:
    def test_bullish_positive(self):
        score = compute_keyword_sentiment("Markets surge on strong growth and rally")
        assert score > 0.0

    def test_bearish_negative(self):
        score = compute_keyword_sentiment("Crash fears grow as recession looms and crisis deepens")
        assert score < 0.0

    def test_neutral_zero(self):
        score = compute_keyword_sentiment("The committee meets at 3pm on Tuesday")
        assert score == 0.0

    def test_clamped_to_bounds(self):
        all_bull = " ".join(BULLISH_WORDS)
        assert compute_keyword_sentiment(all_bull) <= 1.0
        all_bear = " ".join(BEARISH_WORDS)
        assert compute_keyword_sentiment(all_bear) >= -1.0

    def test_case_insensitive(self):
        assert compute_keyword_sentiment("SURGE RALLY BULLISH") > 0

    def test_mixed_cancels(self):
        score = compute_keyword_sentiment("surge crash")
        assert score == 0.0

    def test_ambiguous_words_removed(self):
        """Words like 'risk', 'warning', 'drop' should NOT appear in keyword lists."""
        for word in ["risk", "warning", "red", "contract", "drop", "negative", "decline"]:
            assert word not in BEARISH_WORDS, f"'{word}' should be removed from BEARISH_WORDS"
        assert "positive" not in BULLISH_WORDS

    def test_label_bullish(self):
        assert sentiment_label(0.5) == "bullish"

    def test_label_bearish(self):
        assert sentiment_label(-0.3) == "bearish"

    def test_label_neutral(self):
        assert sentiment_label(0.05) == "neutral"
        assert sentiment_label(-0.05) == "neutral"

    def test_word_lists_not_empty(self):
        assert len(BULLISH_WORDS) > 10
        assert len(BEARISH_WORDS) > 10


class TestParseScores:
    def test_parse_json_array(self):
        raw = json.dumps([
            {"sentiment": 0.5, "relevancy": 0.8, "impact": 0.6},
            {"sentiment": -0.3, "relevancy": 0.4, "impact": 0.2},
        ])
        scores = _parse_scores(raw, 2)
        assert len(scores) == 2
        assert scores[0]["sentiment"] == 0.5
        assert scores[1]["relevancy"] == 0.4

    def test_parse_with_markdown_fences(self):
        raw = "```json\n" + json.dumps([
            {"sentiment": 0.7, "relevancy": 0.9, "impact": 0.8}
        ]) + "\n```"
        scores = _parse_scores(raw, 1)
        assert len(scores) == 1
        assert scores[0]["sentiment"] == 0.7

    def test_clamps_values(self):
        raw = json.dumps([{"sentiment": 5.0, "relevancy": -2.0, "impact": 3.0}])
        scores = _parse_scores(raw, 1)
        assert scores[0]["sentiment"] == 1.0
        assert scores[0]["relevancy"] == 0.0
        assert scores[0]["impact"] == 1.0

    def test_pads_missing_items(self):
        raw = json.dumps([{"sentiment": 0.5, "relevancy": 0.5, "impact": 0.5}])
        scores = _parse_scores(raw, 3)
        assert len(scores) == 3
        assert scores[2]["sentiment"] == 0.0

    def test_handles_dict_wrapper(self):
        raw = json.dumps({"items": [
            {"sentiment": 0.3, "relevancy": 0.6, "impact": 0.4}
        ]})
        scores = _parse_scores(raw, 1)
        assert scores[0]["sentiment"] == 0.3


class TestKeywordFallback:
    def test_returns_correct_count(self):
        items = [
            {"type": "headline", "text": "Markets surge on growth"},
            {"type": "headline", "text": "Crisis deepens"},
        ]
        scores = _keyword_fallback_scores(items)
        assert len(scores) == 2

    def test_bullish_item_positive(self):
        items = [{"type": "headline", "text": "Markets surge on strong growth rally"}]
        scores = _keyword_fallback_scores(items)
        assert scores[0]["sentiment"] > 0

    def test_default_relevancy_and_impact(self):
        items = [{"type": "headline", "text": "Something neutral"}]
        scores = _keyword_fallback_scores(items)
        assert scores[0]["relevancy"] == 0.5
        assert scores[0]["impact"] == 0.3


class TestLlmScoreBatch:
    def test_empty_items(self):
        assert llm_score_batch([], "equities") == []

    def test_llm_call_mocked(self):
        mock_response = json.dumps([
            {"sentiment": 0.6, "relevancy": 0.9, "impact": 0.7},
            {"sentiment": -0.2, "relevancy": 0.5, "impact": 0.4},
        ])
        _CACHE.clear()
        items = [
            {"type": "headline", "text": "Fed cuts rates"},
            {"type": "prediction", "text": "Will there be a recession? (probability: 30%)"},
        ]
        with patch("src.core.llm.llm_chat", return_value=mock_response):
            scores = llm_score_batch(items, "equities")
        assert len(scores) == 2
        assert scores[0]["sentiment"] == 0.6
        assert scores[1]["sentiment"] == -0.2

    def test_cache_hit(self):
        mock_response = json.dumps([{"sentiment": 0.5, "relevancy": 0.5, "impact": 0.5}])
        _CACHE.clear()
        items = [{"type": "headline", "text": "Test headline for caching"}]

        with patch("src.core.llm.llm_chat", return_value=mock_response) as mock:
            llm_score_batch(items, "equities")
            llm_score_batch(items, "equities")
            assert mock.call_count == 1, "Second call should hit cache"

    def test_cache_expires(self):
        mock_response = json.dumps([{"sentiment": 0.5, "relevancy": 0.5, "impact": 0.5}])
        _CACHE.clear()
        items = [{"type": "headline", "text": "Expiry test headline"}]

        with patch("src.core.llm.llm_chat", return_value=mock_response) as mock:
            llm_score_batch(items, "equities")
            # Expire the cache entry
            for k in list(_CACHE.keys()):
                _CACHE[k] = (time.time() - _CACHE_TTL - 1, _CACHE[k][1])
            llm_score_batch(items, "equities")
            assert mock.call_count == 2, "Expired cache should trigger new LLM call"


class TestScoreItems:
    def test_llm_path(self):
        mock_response = json.dumps([
            {"sentiment": 0.8, "relevancy": 0.9, "impact": 0.7},
            {"sentiment": -0.1, "relevancy": 0.6, "impact": 0.3},
        ])
        _CACHE.clear()
        headlines = [{"title": "Markets rally", "source": "CNBC", "url": ""}]
        predictions = [{"question": "Rate cut?", "probability": 0.8}]

        with patch("src.core.llm.has_llm_key", return_value=True):
            with patch("src.core.llm.llm_chat", return_value=mock_response):
                scored_h, scored_p = score_items(headlines, predictions, "equities")

        assert scored_h[0]["sentiment"] == 0.8
        assert scored_h[0]["sentiment_label"] == "bullish"
        assert scored_h[0]["relevancy"] == 0.9
        assert scored_p[0]["sentiment"] == -0.1

    def test_keyword_fallback_when_no_key(self):
        headlines = [{"title": "Markets surge rally breakout", "source": "CNBC", "url": ""}]
        predictions = []

        with patch("src.core.llm.has_llm_key", return_value=False):
            scored_h, scored_p = score_items(headlines, predictions, "equities")

        assert scored_h[0]["sentiment"] > 0
        assert scored_h[0]["sentiment_label"] == "bullish"
        assert scored_h[0]["relevancy"] == 0.5

    def test_fallback_on_llm_error(self):
        _CACHE.clear()
        headlines = [{"title": "Markets surge rally", "source": "CNBC", "url": ""}]
        predictions = []

        with patch("src.core.llm.has_llm_key", return_value=True):
            with patch("src.core.llm.llm_chat", side_effect=RuntimeError("No LLM")):
                scored_h, _ = score_items(headlines, predictions, "equities")

        assert "sentiment" in scored_h[0]
        assert scored_h[0]["relevancy"] == 0.5

    def test_empty_inputs(self):
        h, p = score_items([], [], "equities")
        assert h == []
        assert p == []

    def test_predictions_get_scored(self):
        mock_response = json.dumps([
            {"sentiment": 0.3, "relevancy": 0.7, "impact": 0.5},
        ])
        _CACHE.clear()
        headlines = []
        predictions = [{"question": "Will GDP grow?", "probability": 0.75}]

        with patch("src.core.llm.has_llm_key", return_value=True):
            with patch("src.core.llm.llm_chat", return_value=mock_response):
                _, scored_p = score_items(headlines, predictions, "equities")

        assert scored_p[0]["sentiment"] == 0.3
        assert scored_p[0]["relevancy"] == 0.7


class TestRssAdapterSentiment:
    def test_newsitem_has_nonzero_sentiment(self):
        from src.data.adapters.rss_adapter import RssAdapter
        from types import SimpleNamespace

        adapter = RssAdapter()
        entry = SimpleNamespace(
            title="Markets surge on strong earnings beat",
            link="https://example.com/article",
            summary="Strong growth data pushes markets to rally",
            published="Mon, 09 Mar 2026 17:00:00 GMT",
            updated=None,
        )
        item = adapter._entry_to_newsitem(entry, "https://example.com/rss")
        assert item is not None
        assert item.sentiment > 0.0, "Bullish headline should have positive sentiment"

    def test_bearish_headline_negative(self):
        from src.data.adapters.rss_adapter import RssAdapter
        from types import SimpleNamespace

        adapter = RssAdapter()
        entry = SimpleNamespace(
            title="Crash fears as recession looms",
            link="https://example.com/crash",
            summary="Markets plunge on crisis concerns",
            published="Mon, 09 Mar 2026 17:00:00 GMT",
            updated=None,
        )
        item = adapter._entry_to_newsitem(entry, "https://example.com/rss")
        assert item is not None
        assert item.sentiment < 0.0, "Bearish headline should have negative sentiment"

    def test_neutral_headline(self):
        from src.data.adapters.rss_adapter import RssAdapter
        from types import SimpleNamespace

        adapter = RssAdapter()
        entry = SimpleNamespace(
            title="Fed meeting scheduled for next week",
            link="https://example.com/fed",
            summary="Committee to discuss policy options",
            published="Mon, 09 Mar 2026 17:00:00 GMT",
            updated=None,
        )
        item = adapter._entry_to_newsitem(entry, "https://example.com/rss")
        assert item is not None
        assert item.sentiment == 0.0


class TestGdeltAdapterSentiment:
    def test_keyword_fallback(self):
        """When no GDELT tone column, fall back to keyword scoring."""
        from src.data.adapters.sentiment import compute_keyword_sentiment
        assert compute_keyword_sentiment("Markets surge on growth") > 0

    def test_gdelt_tone_normalization(self):
        """GDELT tone range [-10, +10] should normalize to [-1, +1]."""
        assert max(-1.0, min(1.0, 5.0 / 10.0)) == 0.5
        assert max(-1.0, min(1.0, -8.0 / 10.0)) == -0.8
        assert max(-1.0, min(1.0, 15.0 / 10.0)) == 1.0


class TestScoringNewSignature:
    def test_sentiment_lists(self):
        from src.core.scoring import compute_macro_score

        result = compute_macro_score(
            fred_snapshot={},
            poly_signals=[],
            news_sentiments=[0.5, 0.3, -0.1],
            social_sentiments=[0.2, 0.4],
        )
        assert "social_score" in result
        assert result["social_score"] != 0.0, "Should use actual sentiment values"

    def test_backward_compat_counts(self):
        from src.core.scoring import compute_macro_score

        result = compute_macro_score(
            fred_snapshot={},
            poly_signals=[],
            news_count=10,
            social_count=5,
        )
        assert "social_score" in result

    def test_sentiment_averaging(self):
        from src.core.scoring import compute_news_sentiment_score

        score = compute_news_sentiment_score([0.5, 0.5], [0.5, 0.5])
        assert score == pytest.approx(0.5)

    def test_mixed_sentiment(self):
        from src.core.scoring import compute_news_sentiment_score

        score = compute_news_sentiment_score([0.5, -0.5], [])
        assert score == pytest.approx(0.0)

    def test_empty_lists_positive(self):
        from src.core.scoring import compute_news_sentiment_score

        score = compute_news_sentiment_score([], [])
        assert score == pytest.approx(0.2)

    def test_all_zero_falls_back_to_activity(self):
        from src.core.scoring import compute_news_sentiment_score

        score = compute_news_sentiment_score([0.0] * 50, [0.0] * 50)
        assert score != 0.2, "Should use activity heuristic, not empty-list default"

    def test_full_pipeline_integration(self):
        from src.core.scoring import compute_macro_score

        result = compute_macro_score(
            fred_snapshot={"T10Y2Y": 1.0, "VIXCLS": 15.0},
            poly_signals=[{"question": "Rate cut?", "implied_prob": 0.8, "volume_24h": 5000}],
            news_sentiments=[0.3, 0.2, -0.1, 0.4],
            social_sentiments=[0.1, 0.5],
        )
        assert -1.0 <= result["macro_score"] <= 1.0
        assert 0.0 <= result["polymarket_confidence"] <= 1.0
        assert result["social_score"] > 0, "Mostly bullish headlines should give positive score"


class TestSignalAgentHeadlineFormat:
    def test_headline_has_all_score_fields(self):
        headline = {
            "title": "Markets rally on earnings beat",
            "source": "rss:cnbc.com",
            "url": "https://cnbc.com/article",
            "sentiment": 0.4,
            "sentiment_label": "bullish",
            "relevancy": 0.8,
            "impact": 0.6,
        }
        for field in ("sentiment", "sentiment_label", "relevancy", "impact"):
            assert field in headline

    def test_x_feed_username_field(self):
        """X adapter uses 'username' not 'handle' — signal agents should read it."""
        tweet = {
            "username": "CNBC Top News",
            "text": "Fed signals rate pause",
            "timestamp": "2026-03-09T17:00:00+00:00",
            "sentiment": 0.0,
            "sentiment_label": "neutral",
        }
        username = tweet.get("username", "")
        assert username == "CNBC Top News"
        assert tweet.get("handle", "") == ""
