"""Daily report generator — standalone HTML report with dark theme."""
from __future__ import annotations

import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class DailyReportGenerator:
    """Generate a standalone HTML daily report with inline CSS (dark theme)."""

    def generate(
        self,
        session_dir: str,
        session_start: datetime | None = None,
        session_end: datetime | None = None,
        pods_data: dict | None = None,
        trades: list | None = None,
        governance: list | None = None,
        firm_nav: float = 0.0,
        initial_capital: float = 0.0,
        review_dialogue: list[dict] | None = None,
    ) -> str:
        """Generate a complete HTML report string.

        Args:
            session_dir: Session log directory path
            session_start: Session start timestamp
            session_end: Session end timestamp
            pods_data: Dict mapping pod_id to pod summary (nav, daily_pnl, etc.)
            trades: List of trade dicts (timestamp, pod_id, symbol, side, qty, etc.)
            governance: List of governance decision dicts (agent, decision, reasoning)
            firm_nav: Total firm NAV (used when pods_data empty)
            initial_capital: Starting capital for P&L calculation

        Returns:
            Complete standalone HTML string
        """
        pods = pods_data or {}
        trade_list = trades or []
        gov_list = governance or []

        now = datetime.now()
        date_str = now.strftime("%B %d, %Y")

        # Extract metrics from PodSummary format (risk_metrics nested) or flat
        def _nav(p: dict) -> float:
            return p.get("nav") if "nav" in p else p.get("risk_metrics", {}).get("nav", 0)

        def _pnl(p: dict) -> float:
            return p.get("daily_pnl") if "daily_pnl" in p else p.get("risk_metrics", {}).get("daily_pnl", 0)

        def _sc(p: dict) -> float:
            return p.get("starting_capital") if "starting_capital" in p else p.get("risk_metrics", {}).get("starting_capital", 0)

        def _status(p: dict) -> str:
            s = p.get("status", "UNKNOWN")
            return str(s).upper() if isinstance(s, str) else "UNKNOWN"

        total_nav = sum(_nav(p) for p in pods.values()) if pods else firm_nav
        total_pnl = total_nav - initial_capital if initial_capital > 0 else 0
        pnl_pct = (total_pnl / initial_capital * 100) if initial_capital > 0 else 0
        active_pods = sum(1 for p in pods.values() if _status(p) == "ACTIVE")

        # Duration
        duration = ""
        if session_start and session_end:
            delta = session_end - session_start
            hours, rem = divmod(int(delta.total_seconds()), 3600)
            mins, secs = divmod(rem, 60)
            duration = f"{hours}h {mins}m {secs}s"

        # Build pod rows
        pod_rows = ""
        for pid, pdata in sorted(pods.items()):
            nav = _nav(pdata)
            pnl = _pnl(pdata)
            sc = _sc(pdata)
            ret = ((nav - sc) / sc * 100) if sc > 0 else 0
            status = _status(pdata)
            pnl_color = "#00d68f" if pnl >= 0 else "#e84040"
            pod_rows += f"""<tr>
            <td style="font-weight:600">{pid.upper()}</td>
            <td style="text-align:right">${nav:,.2f}</td>
            <td style="text-align:right;color:{pnl_color}">{'+' if pnl >= 0 else ''}${pnl:,.2f}</td>
            <td style="text-align:right;color:{pnl_color}">{'+' if ret >= 0 else ''}{ret:.2f}%</td>
            <td style="text-align:right">{status}</td>
        </tr>"""

        # Build trade rows
        trade_rows = ""
        for t in trade_list[:50]:
            if isinstance(t, dict):
                ts = str(t.get("timestamp", ""))[:19]
                pod = str(t.get("pod_id", "")).upper()
                sym = t.get("symbol", "")
                side = str(t.get("side", "")).upper()
                qty = t.get("qty", t.get("filled_qty", 0))
                price = t.get("fill_price", t.get("filled_price", 0)) or 0
                status = t.get("status", "FILLED")
                side_color = "#00d68f" if side == "BUY" else "#e84040"
                trade_rows += f"""<tr>
                <td style="font-size:11px;color:#8aa0b8">{ts}</td>
                <td>{pod}</td>
                <td style="font-weight:600">{sym}</td>
                <td style="color:{side_color}">{side}</td>
                <td style="text-align:right">{qty}</td>
                <td style="text-align:right">${price:,.2f}</td>
                <td>{status}</td>
            </tr>"""

        # Build governance rows
        gov_rows = ""
        for g in gov_list[:20]:
            if isinstance(g, dict):
                agent = g.get("agent", "")
                decision = str(g.get("decision", ""))[:100]
                reasoning = str(g.get("reasoning", ""))[:200]
                gov_rows += f"""<tr>
                <td style="font-weight:600;color:#00cfe8">{agent}</td>
                <td>{decision}</td>
                <td style="font-size:11px;color:#8aa0b8">{reasoning}</td>
            </tr>"""

        pnl_color = "#00d68f" if total_pnl >= 0 else "#e84040"

        # Build position review section
        review_section = ""
        if review_dialogue:
            review_cards = ""
            for rv in review_dialogue:
                if not isinstance(rv, dict):
                    continue
                rpod = str(rv.get("pod_id", "UNKNOWN")).upper()
                positions_reviewed = rv.get("positions_reviewed", 0)
                cio_ch = str(rv.get("cio_challenge", "")).replace("<", "&lt;").replace(">", "&gt;")
                pm_resp = str(rv.get("pm_response", "")).replace("<", "&lt;").replace(">", "&gt;")
                cio_dec = str(rv.get("cio_decisions", "")).replace("<", "&lt;").replace(">", "&gt;")
                actions_taken = rv.get("actions", [])
                action_summary = rv.get("summary", "no actions")

                action_rows = ""
                for act in actions_taken:
                    if isinstance(act, dict):
                        a_sym = act.get("symbol", "")
                        a_action = act.get("action", "")
                        a_side = act.get("side", "")
                        a_qty = act.get("qty", 0)
                        a_reason = str(act.get("reasoning", ""))[:150]
                        a_color = "#00d68f" if a_action in ("ADD", "HOLD") else "#e84040"
                        action_rows += f'<div style="padding:6px 0;border-bottom:1px solid #1a2535;font-size:11px"><span style="color:{a_color};font-weight:600">{a_action}</span> {a_sym} — {a_side} {a_qty} — <span style="color:#8aa0b8">{a_reason}</span></div>'

                if not action_rows:
                    action_rows = '<div style="padding:6px 0;font-size:11px;color:#6a90aa">All positions held — no changes</div>'

                review_cards += f'''<div style="background:#13202f;border:1px solid #2a3a50;border-radius:6px;padding:16px;margin-bottom:16px">
                    <div style="font-size:13px;font-weight:700;color:#00cfe8;margin-bottom:12px">{rpod} — {positions_reviewed} position(s) reviewed</div>
                    <div style="margin-bottom:10px"><div style="font-size:10px;letter-spacing:1px;color:#6a90aa;margin-bottom:4px">CIO CHALLENGE</div><div style="font-size:11px;white-space:pre-wrap;color:#c0d0e0;max-height:200px;overflow-y:auto">{cio_ch}</div></div>
                    <div style="margin-bottom:10px"><div style="font-size:10px;letter-spacing:1px;color:#6a90aa;margin-bottom:4px">PM DEFENSE</div><div style="font-size:11px;white-space:pre-wrap;color:#c0d0e0;max-height:200px;overflow-y:auto">{pm_resp}</div></div>
                    <div style="margin-bottom:10px"><div style="font-size:10px;letter-spacing:1px;color:#6a90aa;margin-bottom:4px">CIO FINAL DECISION</div><div style="font-size:11px;white-space:pre-wrap;color:#c0d0e0;max-height:200px;overflow-y:auto">{cio_dec}</div></div>
                    <div><div style="font-size:10px;letter-spacing:1px;color:#6a90aa;margin-bottom:4px">ACTIONS TAKEN</div>{action_rows}</div>
                </div>'''

            review_section = f'''<div style="margin-bottom:28px"><div style="font-size:11px;letter-spacing:1.5px;color:#6a90aa;margin-bottom:10px;border-bottom:1px solid #2a3a50;padding-bottom:6px">POSITION REVIEW</div>{review_cards}</div>'''

        gov_section = ""
        if gov_rows:
            gov_section = f'''<div style="margin-bottom:28px"><div style="font-size:11px;letter-spacing:1.5px;color:#6a90aa;margin-bottom:10px;border-bottom:1px solid #2a3a50;padding-bottom:6px">GOVERNANCE DECISIONS</div><table style="width:100%;border-collapse:collapse;font-size:12px"><thead><tr style="color:#6a90aa;font-size:10px;letter-spacing:0.5px"><th style="text-align:left;padding:6px 8px;border-bottom:1px solid #2a3a50">Agent</th><th style="text-align:left;padding:6px 8px;border-bottom:1px solid #2a3a50">Decision</th><th style="text-align:left;padding:6px 8px;border-bottom:1px solid #2a3a50">Reasoning</th></tr></thead><tbody>{gov_rows}</tbody></table></div>'''

        return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Agentic HF Daily Report — {date_str}</title></head>
<body style="margin:0;padding:0;background:#0d1520;color:#e0e8f0;font-family:'Segoe UI',system-ui,sans-serif">
<div style="max-width:800px;margin:0 auto;padding:32px 24px">

<div style="text-align:center;margin-bottom:32px">
  <div style="font-size:10px;letter-spacing:3px;color:#6a90aa;margin-bottom:8px">AGENTIC HF</div>
  <div style="font-size:22px;font-weight:700;letter-spacing:1px">DAILY REPORT</div>
  <div style="font-size:13px;color:#8aa0b8;margin-top:4px">{date_str}{(' — ' + duration) if duration else ''}</div>
</div>

<div style="display:flex;gap:12px;margin-bottom:28px;flex-wrap:wrap">
  <div style="flex:1;min-width:150px;background:#1a2535;border:1px solid #2a3a50;border-radius:6px;padding:14px;text-align:center">
    <div style="font-size:10px;letter-spacing:1px;color:#6a90aa">FIRM NAV</div>
    <div style="font-size:20px;font-weight:700;margin-top:4px">${total_nav:,.2f}</div>
  </div>
  <div style="flex:1;min-width:150px;background:#1a2535;border:1px solid #2a3a50;border-radius:6px;padding:14px;text-align:center">
    <div style="font-size:10px;letter-spacing:1px;color:#6a90aa">CUMULATIVE P&amp;L</div>
    <div style="font-size:20px;font-weight:700;color:{pnl_color};margin-top:4px">{'+' if total_pnl >= 0 else ''}${total_pnl:,.2f}</div>
    <div style="font-size:11px;color:{pnl_color}">{'+' if pnl_pct >= 0 else ''}{pnl_pct:.2f}%</div>
  </div>
  <div style="flex:1;min-width:150px;background:#1a2535;border:1px solid #2a3a50;border-radius:6px;padding:14px;text-align:center">
    <div style="font-size:10px;letter-spacing:1px;color:#6a90aa">TRADES</div>
    <div style="font-size:20px;font-weight:700;margin-top:4px">{len(trade_list)}</div>
  </div>
  <div style="flex:1;min-width:150px;background:#1a2535;border:1px solid #2a3a50;border-radius:6px;padding:14px;text-align:center">
    <div style="font-size:10px;letter-spacing:1px;color:#6a90aa">ACTIVE PODS</div>
    <div style="font-size:20px;font-weight:700;margin-top:4px">{active_pods} / {len(pods)}</div>
  </div>
</div>

<div style="margin-bottom:28px">
  <div style="font-size:11px;letter-spacing:1.5px;color:#6a90aa;margin-bottom:10px;border-bottom:1px solid #2a3a50;padding-bottom:6px">POD PERFORMANCE</div>
  <table style="width:100%;border-collapse:collapse;font-size:12px">
    <thead><tr style="color:#6a90aa;font-size:10px;letter-spacing:0.5px">
      <th style="text-align:left;padding:6px 8px;border-bottom:1px solid #2a3a50">Pod</th>
      <th style="text-align:right;padding:6px 8px;border-bottom:1px solid #2a3a50">NAV</th>
      <th style="text-align:right;padding:6px 8px;border-bottom:1px solid #2a3a50">P&amp;L</th>
      <th style="text-align:right;padding:6px 8px;border-bottom:1px solid #2a3a50">Return</th>
      <th style="text-align:right;padding:6px 8px;border-bottom:1px solid #2a3a50">Status</th>
    </tr></thead>
    <tbody>{pod_rows if pod_rows else '<tr><td colspan="5" style="text-align:center;color:#6a90aa;padding:12px">No pod data</td></tr>'}</tbody>
  </table>
</div>

{review_section}

<div style="margin-bottom:28px">
  <div style="font-size:11px;letter-spacing:1.5px;color:#6a90aa;margin-bottom:10px;border-bottom:1px solid #2a3a50;padding-bottom:6px">TRADE LOG</div>
  <table style="width:100%;border-collapse:collapse;font-size:12px">
    <thead><tr style="color:#6a90aa;font-size:10px;letter-spacing:0.5px">
      <th style="text-align:left;padding:6px 8px;border-bottom:1px solid #2a3a50">Time</th>
      <th style="text-align:left;padding:6px 8px;border-bottom:1px solid #2a3a50">Pod</th>
      <th style="text-align:left;padding:6px 8px;border-bottom:1px solid #2a3a50">Symbol</th>
      <th style="text-align:left;padding:6px 8px;border-bottom:1px solid #2a3a50">Side</th>
      <th style="text-align:right;padding:6px 8px;border-bottom:1px solid #2a3a50">Qty</th>
      <th style="text-align:right;padding:6px 8px;border-bottom:1px solid #2a3a50">Price</th>
      <th style="text-align:left;padding:6px 8px;border-bottom:1px solid #2a3a50">Status</th>
    </tr></thead>
    <tbody>{trade_rows if trade_rows else '<tr><td colspan="7" style="text-align:center;color:#6a90aa;padding:12px">No trades executed</td></tr>'}</tbody>
  </table>
</div>

{gov_section}

<div style="text-align:center;padding:20px 0;border-top:1px solid #2a3a50;margin-top:32px">
  <div style="font-size:9px;letter-spacing:2px;color:#4a6080">GENERATED BY AGENTIC HF</div>
  <div style="font-size:10px;color:#4a6080;margin-top:4px">{now.strftime("%Y-%m-%d %H:%M:%S UTC")}</div>
</div>

</div>
</body></html>"""
