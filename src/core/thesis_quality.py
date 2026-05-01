"""Shared instructions for PM entry-thesis quality."""

TRADEABLE_ENTRY_THESIS_STANDARD = """
TRADEABLE ENTRY THESIS STANDARD:
For every non-HOLD trade, the reasoning field must be a complete tradeable entry thesis.
Do not stop mid-sentence. Do not summarize away the key evidence.

Use these labels inside reasoning:
- THESIS: the core long/short argument in one complete paragraph.
- DRIVERS: the specific macro, micro, flow, positioning, and price-action inputs that matter.
- CATALYST: why this can move now, including relevant news or event timing.
- ENTRY: why the proposed entry is acceptable now versus waiting for confirmation or a pullback.
- INVALIDATION: the concrete facts that would prove the thesis wrong.
- RISK: what can hurt the trade and how position size/stop/exit_when address it.
- INSTRUMENT FIT: why this symbol is the right vehicle for the thesis.

Data discipline:
- Cite specific data from the prompt when available. If a required input is missing, say it is missing.
- Never invent current market facts. Never assert a rate, yield, flow, or probability that is not in the prompt or fetched context.
- If evidence is mixed, say so and reduce conviction or HOLD.

Precious metals and gold-specific discipline:
- For GLD, GDX, GDXJ, SLV, miners, and related precious-metals trades, explicitly discuss real-yield direction, breakevens/inflation expectations, Fed reaction function, USD trend, positioning/ETF or central-bank demand if available, and geopolitical risk as a conditional catalyst.
- Never claim negative real rates unless the real-yield data shown in the prompt is actually below zero.
- Treat geopolitics as a catalyst/risk-premium argument, not a standalone reason to buy. Explain the second-order path through oil, inflation expectations, growth, real yields, USD, or safe-haven flows.
"""


def tradeable_entry_thesis_instruction(asset_class: str) -> str:
    """Return a concise user-prompt reminder for the active PM call."""
    return (
        "\n\nMANDATORY ENTRY THESIS REQUIREMENT:\n"
        f"For {asset_class} trades, each trade.reasoning must follow the tradeable entry thesis standard "
        "from the system prompt. The reasoning should be complete, falsifiable, and data-consistent. "
        "Use THESIS, DRIVERS, CATALYST, ENTRY, INVALIDATION, RISK, and INSTRUMENT FIT labels. "
        "If you cannot write that thesis from the supplied evidence, output no trades and HOLD."
    )
