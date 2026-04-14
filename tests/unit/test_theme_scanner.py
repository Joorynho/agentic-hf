import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.data.services.theme_scanner import ThemeScanner


@pytest.fixture
def mock_web_searcher():
    ws = MagicMock()
    ws.search = AsyncMock(return_value=[
        {"title": "AI stocks surge", "snippet": "Tech sector leads...", "url": "https://example.com/ai"}
    ])
    ws.fetch_page = AsyncMock(return_value="AI infrastructure spending hits record highs. NVDA, NBIS lead gains.")
    return ws


@pytest.fixture
def scanner(mock_web_searcher):
    return ThemeScanner(web_searcher=mock_web_searcher)


def test_scanner_init(scanner):
    assert scanner is not None


@pytest.mark.asyncio
async def test_run_web_searches_returns_summaries(scanner, mock_web_searcher):
    results = await scanner._run_web_searches(month="April", year="2026")
    assert isinstance(results, list)
    assert len(results) == 4   # 4 search queries
    mock_web_searcher.search.assert_called()


@pytest.mark.asyncio
async def test_scrape_curated_sites_returns_list(scanner, mock_web_searcher):
    results = await scanner._scrape_curated_sites()
    assert isinstance(results, list)
    assert len(results) >= 0


@pytest.mark.asyncio
async def test_synthesize_themes_returns_themes(scanner):
    web_results = [
        {"query": "top sectors", "content": "AI and semiconductors lead market gains."},
        {"query": "emerging themes", "content": "Data center stocks hit record highs."},
        {"query": "institutional buys", "content": "Funds piling into AI infrastructure."},
        {"query": "breakout stocks", "content": "NBIS, VRT, CEG breaking out."},
    ]
    site_results = [{"url": "https://investing.com", "content": "AI infra boom continues."}]
    headlines = [{"title": "Nebius partners with NVIDIA", "sentiment": 0.8}]
    existing_universe = ["SPY", "QQQ", "NVDA"]

    with patch("src.data.services.theme_scanner.llm_chat", return_value='''
    {"themes": [{"name": "AI Infrastructure", "thesis": "Hyperscaler capex surging.", "confidence": 0.85, "tickers": [{"symbol": "NBIS", "reason": "NVIDIA partnership"}, {"symbol": "VRT", "reason": "Data center power"}]}]}
    '''), patch("src.data.services.theme_scanner.has_llm_key", return_value=True):
        themes = await scanner.synthesize_themes(
            web_results=web_results, site_results=site_results, headlines=headlines,
            poly_signals=[], fred_snapshot={"VIXCLS": 18.0, "DGS10": 4.2},
            existing_universe=existing_universe,
        )
    assert len(themes) == 1
    assert themes[0]["name"] == "AI Infrastructure"
    assert len(themes[0]["tickers"]) == 2
    assert themes[0]["tickers"][0]["symbol"] == "NBIS"


@pytest.mark.asyncio
async def test_synthesize_themes_handles_llm_failure(scanner):
    with patch("src.data.services.theme_scanner.llm_chat", return_value="not valid json"), \
         patch("src.data.services.theme_scanner.has_llm_key", return_value=True):
        themes = await scanner.synthesize_themes(
            web_results=[], site_results=[], headlines=[],
            poly_signals=[], fred_snapshot={}, existing_universe=[],
        )
    assert themes == []


@pytest.mark.asyncio
async def test_validate_tickers_accepts_valid(scanner, mock_web_searcher):
    candidates = [{"symbol": "NBIS", "reason": "NVIDIA partnership", "theme": "AI Infrastructure", "thesis": "Cloud AI infra provider."}]
    mock_web_searcher.search = AsyncMock(return_value=[
        {"title": "Nebius stock analysis 2026", "snippet": "NBIS is a US-listed AI cloud company.", "url": "https://ex.com"}
    ])
    with patch("src.data.services.theme_scanner.llm_chat", return_value='{"valid": true, "reason": "Confirmed US-listed"}'), \
         patch("src.data.services.theme_scanner.has_llm_key", return_value=True):
        validated = await scanner.validate_tickers(candidates, month="April", year="2026")
    assert len(validated) == 1
    assert validated[0]["symbol"] == "NBIS"


@pytest.mark.asyncio
async def test_validate_tickers_rejects_invalid(scanner, mock_web_searcher):
    candidates = [{"symbol": "FAKEXYZ", "reason": "Some reason", "theme": "AI", "thesis": "Fake thesis."}]
    mock_web_searcher.search = AsyncMock(return_value=[])
    with patch("src.data.services.theme_scanner.llm_chat", return_value='{"valid": false, "reason": "Not found"}'), \
         patch("src.data.services.theme_scanner.has_llm_key", return_value=True):
        validated = await scanner.validate_tickers(candidates, month="April", year="2026")
    assert len(validated) == 0


@pytest.mark.asyncio
async def test_review_ticker_still_valid(scanner, mock_web_searcher):
    ticker_data = {"symbol": "NBIS", "theme": "AI Infrastructure", "thesis": "NVIDIA/MSFT cloud partnership.", "discovered_date": "2026-04-07", "next_review_date": "2026-04-14", "status": "active", "invalidation_reason": None, "source_headlines": []}
    mock_web_searcher.search = AsyncMock(return_value=[{"title": "Nebius expands", "snippet": "Continued growth.", "url": "https://ex.com"}])
    with patch("src.data.services.theme_scanner.llm_chat", return_value='{"still_valid": true, "reason": "Thesis intact"}'), \
         patch("src.data.services.theme_scanner.has_llm_key", return_value=True):
        result = await scanner.review_ticker(ticker_data, month="April", year="2026")
    assert result["status"] == "active"
    assert result["next_review_date"] != "2026-04-14"


@pytest.mark.asyncio
async def test_review_ticker_invalidated(scanner, mock_web_searcher):
    ticker_data = {"symbol": "NBIS", "theme": "AI Infrastructure", "thesis": "NVIDIA/MSFT cloud partnership.", "discovered_date": "2026-04-07", "next_review_date": "2026-04-14", "status": "active", "invalidation_reason": None, "source_headlines": []}
    mock_web_searcher.search = AsyncMock(return_value=[{"title": "Nebius loses NVIDIA contract", "snippet": "Partnership terminated.", "url": "https://ex.com"}])
    with patch("src.data.services.theme_scanner.llm_chat", return_value='{"still_valid": false, "reason": "Partnership ended"}'), \
         patch("src.data.services.theme_scanner.has_llm_key", return_value=True):
        result = await scanner.review_ticker(ticker_data, month="April", year="2026")
    assert result["status"] == "inactive"
    assert result["invalidation_reason"] == "Partnership ended"


@pytest.mark.asyncio
async def test_scan_end_to_end(scanner, mock_web_searcher):
    """Full scan returns DiscoveredTicker list."""
    from src.core.models.execution import DiscoveredTicker
    headlines = [{"title": "AI boom continues", "sentiment": 0.8}]
    existing = {"AAPL": {"symbol": "AAPL", "status": "active"}}
    existing_universe = ["SPY", "QQQ", "NVDA", "AAPL"]

    with patch("src.data.services.theme_scanner.llm_chat") as mock_llm, \
         patch("src.data.services.theme_scanner.has_llm_key", return_value=True):
        mock_llm.side_effect = [
            '{"themes": [{"name": "AI Infra", "thesis": "Capex surge.", "confidence": 0.9, "tickers": [{"symbol": "NBIS", "reason": "NVIDIA partner"}]}]}',
            '{"valid": true, "reason": "US-listed AI cloud company"}',
        ]
        result = await scanner.scan(
            headlines=headlines, poly_signals=[], fred_snapshot={"VIXCLS": 18.0, "DGS10": 4.2},
            existing_discovered=existing, existing_universe=existing_universe,
            month="April", year="2026",
        )

    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0].symbol == "NBIS"
    assert result[0].theme == "AI Infra"
    assert result[0].status == "active"
    assert result[0].next_review_date > result[0].discovered_date
