"""Shared instructions for PM entry-thesis quality."""

ASSET_EVIDENCE_CHECKLISTS: dict[str, tuple[str, ...]] = {
    "equities": (
        "current price and recent relative performance",
        "earnings/revenue/margin or estimate-revision evidence",
        "valuation or peer multiple if claiming cheap/expensive",
        "sector breadth, factor exposure, flows, or positioning",
        "rates, dollar, or macro sensitivity when relevant",
    ),
    "fx": (
        "current ETF/pair price and recent relative performance",
        "rate differential, real-yield, or carry evidence",
        "central-bank reaction function and upcoming policy/data dates",
        "inflation/growth divergence between the currencies",
        "USD/DXY, risk sentiment, positioning, or flow evidence",
    ),
    "crypto": (
        "current price and relative performance versus BTC and ETH over more than one window",
        "valuation/network evidence such as market cap/TVL, FDV/TVL, fees, revenue, stablecoin supply, DEX volume, active users, or active addresses",
        "liquidity, rates/real yields, dollar, and risk-appetite context",
        "positioning evidence such as funding rates, open interest, ETF/fund flows, or spot/derivatives volume",
        "confirmed catalyst details; if a catalyst is only a narrative event, label it speculative",
    ),
    "commodities": (
        "current price and recent relative performance",
        "supply/demand or physical-market evidence such as inventories, production, demand, curve/roll, or seasonality",
        "USD, real-yield, inflation, growth, and policy context as relevant",
        "positioning, ETF/producer flow, or futures-market evidence when available",
        "geopolitical/weather/OPEC policy catalysts separated from assumptions about market response",
    ),
}


def asset_evidence_checklist(asset_class: str) -> tuple[str, ...]:
    """Return evidence checks PMs should satisfy before making claims."""
    key = str(asset_class or "").strip().lower()
    if key in ("commodity", "commodities_pod"):
        key = "commodities"
    if key not in ASSET_EVIDENCE_CHECKLISTS:
        return ASSET_EVIDENCE_CHECKLISTS["equities"]
    return ASSET_EVIDENCE_CHECKLISTS[key]


TRADEABLE_ENTRY_THESIS_STANDARD = """
TRADEABLE ENTRY THESIS STANDARD:
For every non-HOLD trade, the reasoning field must be a complete tradeable entry thesis.
Do not stop mid-sentence. Do not summarize away the key evidence.

Use these labels inside reasoning:
- FACTS: verified current facts from the prompt, live data, article reads, or search results.
- ASSUMPTIONS: what must be true but is not yet proven; state uncertainty plainly.
- THESIS: the core long/short argument in one complete paragraph.
- DRIVERS: the specific macro, micro, flow, positioning, and price-action inputs that matter.
- VALUATION/EVIDENCE: the comparison metric that supports any cheap, expensive, undervalued, overvalued, or relative-value claim.
- CATALYST: why this can move now, including relevant news or event timing. Label speculative catalysts as speculative.
- WHY NOW: why the market should reprice during the intended holding window, not merely why the asset is high quality.
- ENTRY: why the proposed entry is acceptable now versus waiting for confirmation or a pullback.
- TIMEFRAME: the intended holding period and why stop-loss/take-profit/max_hold_days fit the asset's volatility and catalyst timing.
- INVALIDATION: the concrete facts that would prove the thesis wrong.
- RISK: what can hurt the trade and how position size/stop/exit_when address it.
- INSTRUMENT FIT: why this symbol is the right vehicle for the thesis.

Data discipline:
- Cite specific data from the prompt when available. If a required input is missing, say it is missing.
- Never invent current market facts. Never assert a rate, yield, flow, or probability that is not in the prompt or fetched context.
- Separate facts from assumptions. Do not present assumptions as facts.
- If you claim something is cheap, expensive, undervalued, overvalued, crowded, or under-owned, support it with a relevant metric or explicitly say the evidence is not available.
- Use article reads or search_queries when a key current fact is not provided, such as current gas fees, TVL, ETF flows, inventory data, central-bank dates, confirmed event announcements, or earnings dates.
- Compare important metrics across more than one timeframe where possible, not only the last few days.
- If evidence is mixed, say so and reduce conviction or HOLD.
- If adding to an existing position, explicitly say why this is an expansion/add now, how the original thesis has been revalidated, and what new evidence justifies more risk.
- If the thesis lifecycle review says watch/challenged/broken/needs rewrite, do not add unless you write a fresh thesis that addresses the listed issues.

Asset-class discipline:
- Equities: discuss the relevant earnings/fundamental driver, valuation or multiple setup, sector/market beta, rates/macro sensitivity, and catalyst/flow evidence.
- FX: discuss rate differentials/carry, central-bank policy, inflation/growth divergence, the USD or cross-currency driver, and risk sentiment.
- Crypto: discuss liquidity, rates/real yields, risk sentiment, regulation/security risk, and flow/network/adoption evidence. Undervalued or relative-value claims need crypto-native metrics such as market cap/TVL, FDV/TVL, fees/revenue, stablecoin supply, DEX volume, active users/addresses, funding rates, open interest, flows, and relative performance versus BTC/ETH across multiple windows.
- Commodities: discuss the relevant supply/demand driver, inventories or physical-market evidence, USD sensitivity, growth/inflation regime, and the specific sub-theme catalyst.
- Energy commodities: explicitly handle oil/gas supply-demand, inventories, OPEC/geopolitics/weather, USD, and growth demand.
- Industrial metals: explicitly handle industrial demand, inventories, China/global growth, USD, and the manufacturing cycle.
- Agriculture/softs: explicitly handle weather/crop conditions, inventories, USD, export demand, and seasonality.
- For GLD, GDX, GDXJ, SLV, miners, and related precious-metals trades, explicitly discuss real-yield direction, breakevens/inflation expectations, Fed reaction function, USD trend, positioning/ETF or central-bank demand if available, and geopolitical risk as a conditional catalyst.
- Never claim negative real rates unless the real-yield data shown in the prompt is actually below zero.
- Treat geopolitics as a catalyst/risk-premium argument, not a standalone reason to buy. Explain the second-order path through oil, inflation expectations, growth, real yields, USD, or safe-haven flows.
- Treat events, summits, conferences, and headlines as tradable catalysts only if there is a confirmed announcement, flow, policy decision, release, or repricing trigger attached. Otherwise call them narrative support, not a catalyst.
"""


def tradeable_entry_thesis_instruction(asset_class: str) -> str:
    """Return a concise user-prompt reminder for the active PM call."""
    evidence = "; ".join(asset_evidence_checklist(asset_class))
    return (
        "\n\nMANDATORY ENTRY THESIS REQUIREMENT:\n"
        f"For {asset_class} trades, each trade.reasoning must follow the tradeable entry thesis standard "
        "from the system prompt. The reasoning should be complete, falsifiable, and data-consistent. "
        "Use FACTS, ASSUMPTIONS, THESIS, DRIVERS, VALUATION/EVIDENCE, CATALYST, WHY NOW, ENTRY, "
        "TIMEFRAME, INVALIDATION, RISK, and INSTRUMENT FIT labels. "
        f"Evidence checklist for this pod: {evidence}. "
        "If a key current fact is missing, request read_articles/search_queries before making the trade or say the evidence is missing. "
        "For adds/expansions, explicitly explain why more exposure is justified now and why the original thesis still holds. "
        "If you cannot write that thesis from the supplied evidence, output no trades and HOLD."
    )
