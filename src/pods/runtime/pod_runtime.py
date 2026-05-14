from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from src.core.bus.collaboration_runner import CollaborationRunner
from src.core.bus.event_bus import EventBus
from src.core.concentration import check_concentration
from src.core.factor_exposure import compute_factor_report, format_factor_report
from src.core.instrument_profile import profiles_for_pod
from src.core.portfolio_construction import review_portfolio_construction
from src.core.thesis_monitor import monitor_positions
from src.core.models.allocation import MandateUpdate
from src.core.models.enums import PodStatus
from src.agents.thesis_verifier import ThesisVerifier
from src.core.models.execution import Order, RiskApprovalToken, PodPosition
from src.core.models.market import Bar
from src.core.models.pod_summary import PodSummary, PodRiskMetrics, PodExposureBucket
from src.core.signal_scorer import SignalScorer
from src.core.thesis_lifecycle import (
    current_regime,
    expansion_thesis_is_fresh,
    format_thesis_reviews_for_prompt,
    review_position_thesis,
)
from src.core.trade_outcomes import TradeOutcomeTracker
from src.agents.investment_committee import InvestmentCommitteeReviewer
from src.agents.specialists import SpecialistRunner
from src.pods.base.agent import BasePodAgent
from src.pods.base.gateway import PodGateway
from src.pods.base.namespace import PodNamespace

logger = logging.getLogger(__name__)


class PodRuntime:
    """Orchestrates the 6 intra-pod agents for one pod.

    Execution order per bar tick:
      1. Researcher  — fetches/refreshes pod-specific data signals
      2. Signal      — generates feature vector from bar + research data
      3. PM          — proposes trade decision (Signal↔PM challenge loop, max 5 iter)
      4. Risk        — validates and signs off on order (PM↔Risk loop, max 10 iter)
      5. Exec Trader — submits approved order through PodGateway
      6. Ops         — heartbeat + reconciliation

    Intra-pod loops are synchronous within this call stack. No bus messages cross
    pod boundaries — only PodGateway.emit_summary() exits the isolation boundary.
    """

    def __init__(
        self,
        pod_id: str,
        namespace: PodNamespace,
        gateway: PodGateway,
        bus: EventBus,
        collaboration_runner: CollaborationRunner | None = None,
    ) -> None:
        self._pod_id = pod_id
        self._ns = namespace
        self._gateway = gateway
        self._bus = bus
        self._collab = collaboration_runner or CollaborationRunner()

        self._outcome_tracker = TradeOutcomeTracker(pod_id)
        self._signal_scorer = SignalScorer(pod_id)
        self._specialist_runner = SpecialistRunner()
        self._committee = InvestmentCommitteeReviewer()

        # Agents are injected after construction via set_agents()
        self._researcher: BasePodAgent | None = None
        self._signal: BasePodAgent | None = None
        self._pm: BasePodAgent | None = None
        self._risk: BasePodAgent | None = None
        self._exec_trader: BasePodAgent | None = None
        self._ops: BasePodAgent | None = None

    def set_agents(
        self,
        researcher: BasePodAgent,
        signal: BasePodAgent,
        pm: BasePodAgent,
        risk: BasePodAgent,
        exec_trader: BasePodAgent,
        ops: BasePodAgent,
    ) -> None:
        self._researcher = researcher
        self._signal = signal
        self._pm = pm
        self._risk = risk
        self._exec_trader = exec_trader
        self._ops = ops

    def set_governance_state(
        self,
        mandate: Optional[MandateUpdate] = None,
        risk_halt: bool = False,
        risk_halt_reason: Optional[str] = None,
    ) -> None:
        """Set governance state (mandate, risk halt) for execution enforcement."""
        self._ns.set("governance_mandate", mandate)
        self._ns.set("governance_risk_halt", risk_halt)
        self._ns.set("governance_risk_halt_reason", risk_halt_reason)

    def _managed_runtime(self):
        try:
            return self._ns.get("managed_runtime")
        except Exception:
            return None

    def _managed_start_run(
        self,
        *,
        agent_id: str,
        agent_type: str,
        task: str,
        trigger: str = "",
        parent_run_id: str | None = None,
        input_payload=None,
    ) -> str:
        managed = self._managed_runtime()
        if not managed:
            return ""
        try:
            try:
                from src.core.llm import model_policy_for_task

                model_policy = model_policy_for_task(task)
            except Exception:
                model_policy = {}
            return managed.agent_runs.start_run(
                agent_id=agent_id,
                agent_type=agent_type,
                pod_id=self._pod_id,
                task=task,
                trigger=trigger,
                parent_run_id=parent_run_id,
                input_payload=input_payload,
                model_tier=model_policy.get("model_tier", ""),
                model_selection_reason=model_policy.get("model_selection_reason", ""),
                budget_mode=model_policy.get("budget_mode", ""),
            )
        except Exception as exc:
            logger.debug("[%s] managed start_run failed for %s: %s", self._pod_id, agent_id, exc)
            return ""

    def _managed_complete_run(self, run_id: str, output_summary=None, *, status: str = "success", artifact_refs: list[str] | None = None) -> None:
        if not run_id:
            return
        managed = self._managed_runtime()
        if not managed:
            return
        try:
            managed.agent_runs.complete_run(run_id, output_summary=output_summary, status=status, artifact_refs=artifact_refs)
        except Exception as exc:
            logger.debug("[%s] managed complete_run failed for %s: %s", self._pod_id, run_id, exc)

    def _managed_fail_run(self, run_id: str, error, *, status: str = "failed") -> None:
        if not run_id:
            return
        managed = self._managed_runtime()
        if not managed:
            return
        try:
            managed.agent_runs.fail_run(run_id, error, status=status)
        except Exception as exc:
            logger.debug("[%s] managed fail_run failed for %s: %s", self._pod_id, run_id, exc)

    async def _run_agent_stage(self, agent, ctx: dict, *, agent_id: str, agent_type: str, task: str, parent_run_id: str | None = None) -> dict:
        run_id = self._managed_start_run(
            agent_id=agent_id,
            agent_type=agent_type,
            task=task,
            trigger="pod_cycle",
            parent_run_id=parent_run_id,
            input_payload={"ctx_keys": sorted(ctx.keys())},
        )
        try:
            result = await agent.run_cycle(ctx)
            self._managed_complete_run(run_id, result)
            return result or {}
        except Exception as exc:
            self._managed_fail_run(run_id, exc)
            raise

    def _record_managed_artifact(self, kind: str, *, status: str = "fresh", freshness_seconds: float | None = None, source_run_id: str = "", payload_ref: str = "") -> str:
        managed = self._managed_runtime()
        if not managed:
            return ""
        try:
            return managed.artifacts.record(
                kind=kind,
                owner=self._pod_id,
                status=status,
                freshness_seconds=freshness_seconds,
                source_run_id=source_run_id,
                payload_ref=payload_ref,
            )
        except Exception as exc:
            logger.debug("[%s] managed artifact failed for %s: %s", self._pod_id, kind, exc)
            return ""

    def _record_managed_report(
        self,
        *,
        report_type: str,
        title: str,
        summary: str,
        body_markdown: str = "",
        symbol: str = "",
        related_run_ids: list[str] | None = None,
        related_catalyst_ids: list[str] | None = None,
        tags: list[str] | None = None,
        quality_flags: list[str] | None = None,
    ) -> str:
        managed = self._managed_runtime()
        if not managed:
            return ""
        try:
            return managed.reports.add_report(
                report_type=report_type,
                pod_id=self._pod_id,
                symbol=symbol,
                related_run_ids=related_run_ids or [],
                related_catalyst_ids=related_catalyst_ids or [],
                title=title,
                summary=summary,
                body_markdown=body_markdown,
                tags=tags or [],
                quality_flags=quality_flags or [],
            )
        except Exception as exc:
            logger.debug("[%s] managed report failed for %s: %s", self._pod_id, report_type, exc)
            return ""

    def _update_catalyst_lifecycle(
        self,
        catalyst_ids: list[str],
        *,
        status: str | None = None,
        linked_run_ids: list[str] | None = None,
        linked_report_ids: list[str] | None = None,
        linked_trade_ids: list[str] | None = None,
    ) -> None:
        if not catalyst_ids:
            return
        try:
            store = self._ns.get("catalyst_lifecycle_store")
        except Exception:
            store = None
        if not store or not hasattr(store, "update_catalyst_lifecycle"):
            return
        for event_id in catalyst_ids:
            try:
                store.update_catalyst_lifecycle(
                    str(event_id),
                    status=status,
                    linked_run_ids=linked_run_ids or [],
                    linked_report_ids=linked_report_ids or [],
                    linked_trade_ids=linked_trade_ids or [],
                )
            except Exception as exc:
                logger.debug("[%s] catalyst lifecycle update failed for %s: %s", self._pod_id, event_id, exc)

    def _managed_dependency_snapshot(self) -> dict:
        managed = self._managed_runtime()
        if not managed:
            return {"status": "unavailable", "checks": []}
        checks = [
            managed.artifacts.check_dependency("research_feed", owner=self._pod_id, hard=False, max_age_seconds=900),
            managed.artifacts.check_dependency("catalyst_ledger", owner="research", hard=False, max_age_seconds=1800),
            managed.artifacts.check_dependency("fresh_prices", owner=self._pod_id, hard=False, max_age_seconds=600),
            managed.artifacts.check_dependency("broker_snapshot", owner="firm", hard=False, max_age_seconds=600),
            managed.artifacts.check_dependency("specialist_briefs", owner=self._pod_id, hard=False, max_age_seconds=1800),
        ]
        degraded = [c for c in checks if not c.get("ok")]
        return {
            "status": "degraded" if degraded else "ok",
            "checks": checks,
            "degraded_reasons": [c.get("reason") for c in degraded if c.get("reason")],
        }

    def _hard_dependency_allows_order(self, order: Order) -> tuple[bool, str]:
        if not self._managed_runtime():
            return True, ""
        if getattr(order, "side", None) is None or order.side.value.upper() != "BUY":
            return True, ""
        managed = self._managed_runtime()
        price_max_age = 180 if "/" in order.symbol else 600
        checks = [
            managed.artifacts.check_dependency("fresh_prices", owner=self._pod_id, hard=True, max_age_seconds=price_max_age),
            managed.artifacts.check_dependency("broker_snapshot", owner="firm", hard=True, max_age_seconds=600),
        ]
        blockers = [c for c in checks if c.get("action") == "block"]
        if blockers:
            return False, "; ".join(c.get("reason") or c.get("kind") or "dependency failed" for c in blockers)
        return True, ""

    def _run_thesis_monitor(self, ctx: dict, accountant) -> dict[str, dict]:
        """Run advisory live thesis checks for open positions."""
        if not accountant:
            return {}
        events = ctx.get("foresight_events") or self._ns.get("foresight_events") or []
        latest_regime = current_regime(ctx.get("features"))
        try:
            results = monitor_positions(
                pod_id=self._pod_id,
                positions=accountant.current_positions,
                catalyst_events=events if isinstance(events, list) else [],
                latest_regime=latest_regime,
            )
        except Exception as exc:
            logger.debug("[%s] thesis monitor skipped: %s", self._pod_id, exc)
            return {}
        managed = self._managed_runtime()
        by_symbol: dict[str, dict] = {}
        add_blocked: dict[str, dict] = {}
        for result in results:
            symbol = str(result.get("symbol") or "").upper()
            if not symbol:
                continue
            if managed:
                try:
                    managed.thesis_monitor.add_result(result)
                except Exception as exc:
                    logger.debug("[%s] thesis monitor persistence failed for %s: %s", self._pod_id, symbol, exc)
            by_symbol[symbol] = result
            if result.get("status") == "ADD_BLOCKED":
                add_blocked[symbol] = result
        self._ns.set("thesis_monitor_results", by_symbol)
        self._ns.set("thesis_add_blocked", add_blocked)
        ctx["thesis_monitor_results"] = by_symbol
        if add_blocked:
            ctx.setdefault("sizing_context", {})["thesis_add_blocked"] = add_blocked
        return by_symbol

    def _portfolio_construction_review(self, order: Order, accountant, data_quality: dict) -> dict:
        """Run and persist the advisory portfolio-construction gate."""
        if not accountant:
            return {}
        try:
            review = review_portfolio_construction(
                pod_id=self._pod_id,
                order=order,
                positions=accountant.current_positions,
                nav=float(getattr(accountant, "nav", 0.0) or 0.0),
                cash=float(getattr(accountant, "cash", getattr(accountant, "_cash", 0.0)) or 0.0),
                dynamic_profiles=self._ns.get("factor_profiles"),
                fallback_price=float(data_quality.get("price") or 0.0),
            )
            row = review.model_dump(mode="json")
        except Exception as exc:
            logger.debug("[%s] portfolio construction review skipped for %s: %s", self._pod_id, order.symbol, exc)
            return {}

        managed = self._managed_runtime()
        if managed:
            try:
                managed.portfolio_construction.add_review(row)
            except Exception as exc:
                logger.debug("[%s] portfolio construction persistence failed for %s: %s", self._pod_id, order.symbol, exc)
        self._ns.set("last_portfolio_construction_review", row)
        by_symbol = dict(self._ns.get("portfolio_construction_reviews_by_symbol") or {})
        by_symbol[order.symbol.upper()] = row
        self._ns.set("portfolio_construction_reviews_by_symbol", by_symbol)
        history = list(self._ns.get("portfolio_construction_history") or [])
        history.insert(0, row)
        self._ns.set("portfolio_construction_history", history[:100])
        return row

    def _apply_portfolio_construction_review(self, order: Order, accountant, data_quality: dict) -> tuple[Order | None, dict]:
        review = self._portfolio_construction_review(order, accountant, data_quality)
        if not review:
            return order, {}

        action = str(review.get("action") or "APPROVE_SIZE").upper()
        if action in {"SKIP_DUPLICATIVE", "REQUEST_PM_REVISION"}:
            return None, review

        if action in {"DOWNSIZE", "TRIM_TO_FUND"}:
            price = float(data_quality.get("price") or order.limit_price or 0.0)
            recommended = float(review.get("recommended_notional") or 0.0)
            if recommended <= 0 or price <= 0:
                return None, review
            adjusted_qty = min(float(order.quantity), recommended / price)
            if adjusted_qty <= 0:
                return None, review
            if adjusted_qty < float(order.quantity):
                original_qty = float(order.quantity)
                adjusted_qty = round(adjusted_qty, 8)
                review["adjusted_quantity"] = adjusted_qty
                order = order.model_copy(update={"quantity": adjusted_qty})
                logger.info(
                    "[%s] Portfolio construction %s %s resized %.6f -> %.6f",
                    self._pod_id,
                    order.side.value.upper(),
                    order.symbol,
                    original_qty,
                    adjusted_qty,
                )
        return order, review

    def _record_decision_snapshots(self, ctx: dict, accountant, pm_run_id: str, thesis_gate_result: dict) -> list[str]:
        """Persist sanitized final PM decision snapshots after revisions finalize."""
        managed = self._managed_runtime()
        if not managed:
            return []
        pm_decision = self._ns.get("last_pm_decision") or {}
        features = ctx.get("features") if isinstance(ctx.get("features"), dict) else {}
        trades = [
            t for t in (pm_decision.get("trades") or [])
            if isinstance(t, dict) and str(t.get("action", "HOLD")).upper() != "HOLD"
        ]
        if not trades:
            trades = [{"action": "HOLD", "symbol": "", "thesis_fields": pm_decision.get("thesis_fields", {})}]
        snapshots: list[str] = []
        events = ctx.get("foresight_events") or pm_decision.get("foresight_events") or []
        specialist_briefs = ctx.get("specialist_briefs") or self._ns.get("specialist_briefs") or []
        artifact_status = ctx.get("managed_dependencies") or self._managed_dependency_snapshot()
        committee_history = self._ns.get("committee_reviews_by_symbol") or {}
        position_state_all = {}
        if accountant:
            for sym, pos in accountant.current_positions.items():
                position_state_all[str(sym).upper()] = {
                    "qty": getattr(pos, "qty", 0.0),
                    "current_price": getattr(pos, "current_price", 0.0),
                    "avg_entry": getattr(pos, "avg_entry", getattr(pos, "avg_cost", 0.0)),
                    "unrealized_pnl": getattr(pos, "unrealized_pnl", 0.0),
                }
        report_ids: list[str] = []
        report_id = self._record_managed_report(
            report_type="pm_decision",
            title=f"{self._pod_id.upper()} final PM decision",
            summary=str(pm_decision.get("action_summary") or pm_decision.get("reasoning") or "Final PM decision")[:1000],
            body_markdown=json.dumps(pm_decision, default=str, indent=2)[:8000],
            related_run_ids=[pm_run_id] if pm_run_id else [],
            related_catalyst_ids=list(pm_decision.get("catalyst_ids") or []),
            tags=["pm_decision", "final"],
            quality_flags=[] if thesis_gate_result.get("passed", True) else ["thesis_gate_failed"],
        )
        if report_id:
            report_ids.append(report_id)
        for trade in trades:
            symbol = str(trade.get("symbol") or "").upper()
            catalyst_ids = list(dict.fromkeys(str(x) for x in (
                trade.get("catalyst_ids") or pm_decision.get("catalyst_ids") or []
            ) if x))
            catalyst_state = []
            for event in events if isinstance(events, list) else []:
                if not isinstance(event, dict):
                    continue
                if catalyst_ids and event.get("event_id") not in catalyst_ids:
                    continue
                catalyst_state.append({
                    "event_id": event.get("event_id"),
                    "thread_id": event.get("thread_id"),
                    "status": event.get("status"),
                    "title": event.get("title"),
                    "factors": event.get("factors", []),
                    "materiality_score": event.get("materiality_score"),
                })
            price = None
            if symbol and accountant and symbol in accountant.current_positions:
                price = float(getattr(accountant.current_positions[symbol], "current_price", 0.0) or 0.0)
            elif ctx.get("bar") is not None:
                price = float(getattr(ctx["bar"], "close", 0.0) or 0.0)
            snapshot_id = managed.decisions.add_snapshot({
                "pod_id": self._pod_id,
                "decision_id": str(pm_decision.get("decision_id") or pm_run_id or ""),
                "symbol": symbol,
                "side": str(trade.get("action") or "HOLD").upper(),
                "status": "active",
                "decision_horizon": str(trade.get("timeframe") or trade.get("horizon") or "days"),
                "price_at_decision": price,
                "position_state": position_state_all.get(symbol, {}) if symbol else position_state_all,
                "catalyst_ids": catalyst_ids,
                "catalyst_state": catalyst_state,
                "signal_features": {
                    "macro_outlook": features.get("macro_outlook"),
                    "regime": features.get("regime"),
                    "top_scores": features.get("scores") or features.get("signal_scores"),
                },
                "specialist_briefs": specialist_briefs if isinstance(specialist_briefs, list) else [],
                "committee_review": committee_history.get(symbol, {}) if isinstance(committee_history, dict) else {},
                "thesis_fields": trade.get("thesis_fields") or pm_decision.get("thesis_fields") or {},
                "risk_state": {
                    "thesis_gate": thesis_gate_result,
                    "loss_review": self._ns.get("loss_review_restriction") or {},
                    "broker_guard": self._ns.get("broker_trade_guard") or {},
                },
                "artifact_status": artifact_status,
                "model_trace_refs": [str((pm_decision.get("llm") or {}).get("model") or "")],
                "report_refs": report_ids,
            })
            snapshots.append(snapshot_id)
        self._ns.set("last_decision_snapshot_ids", snapshots)
        return snapshots

    async def run_cycle(self, bar: Bar, skip_researcher: bool = False) -> None:
        """Run one full agent cycle for a single bar.

        Args:
            bar: Market bar to process.
            skip_researcher: If True, skip the researcher step (caller already ran it).
        """
        assert all(
            a is not None for a in [
                self._researcher, self._signal, self._pm,
                self._risk, self._exec_trader, self._ops,
            ]
        ), "All 6 agents must be set before calling run_cycle()"

        ctx: dict = {"bar": bar}

        if not skip_researcher:
            research_out = await self._run_agent_stage(
                self._researcher,
                ctx,
                agent_id=f"{self._pod_id}.researcher",
                agent_type="researcher",
                task="research_cycle",
            )  # type: ignore[arg-type]
            ctx.update(research_out)

        # 2. Signal
        signal_out = await self._run_agent_stage(
            self._signal,
            ctx,
            agent_id=f"{self._pod_id}.signal",
            agent_type="signal",
            task="signal_generation",
        )  # type: ignore[arg-type]
        ctx.update(signal_out)
        self._inject_foresight_context(ctx)
        ctx["managed_dependencies"] = self._managed_dependency_snapshot()
        try:
            ctx["instrument_profiles"] = profiles_for_pod(self._pod_id, self._ns.get("factor_profiles"))
        except Exception as exc:
            logger.debug("[%s] instrument profile injection skipped: %s", self._pod_id, exc)
            ctx["instrument_profiles"] = []

        # Inject sizing context for PM (LLM-informed position sizing)
        accountant = self._ns.get("accountant")
        if accountant:
            pos_summary = []
            for sym, snap in accountant.current_positions.items():
                pos_summary.append({
                    "symbol": sym, "qty": snap.qty,
                    "notional": abs(snap.qty * snap.current_price),
                    "unrealized_pnl": snap.unrealized_pnl,
                })
            total_notional = sum(p["notional"] for p in pos_summary)
            gross_lev = total_notional / accountant.nav if accountant.nav > 0 else 0
            max_leverage = 1.0 if self._pod_id == "commodities" else 2.0
            ctx["sizing_context"] = {
                "pod_nav": round(accountant.nav, 2),
                "available_cash": round(accountant._cash, 2),
                "current_leverage": round(gross_lev, 2),
                "max_position_pct": 0.20,
                "max_leverage": max_leverage,
                "position_limit_notional": round(accountant.nav * 0.20, 2),
                "positions_summary": pos_summary,
            }

            loss_review = self._ns.get("loss_review") or {}
            loss_restriction = self._ns.get("loss_review_restriction") or {}
            loss_review_text = self._ns.get("loss_review_text") or ""
            if loss_review:
                ctx["loss_review"] = loss_review
            if loss_restriction:
                ctx["loss_review_restriction"] = loss_restriction
                ctx["sizing_context"]["loss_review_restriction"] = loss_restriction
                if loss_restriction.get("block_new_risk"):
                    ctx["sizing_context"]["risk_mode"] = "reduce_only"
            if loss_review_text:
                ctx["sizing_context"]["loss_review_text"] = loss_review_text
            if self._pod_id == "commodities":
                factor_report = compute_factor_report(
                    accountant.current_positions,
                    accountant.nav,
                    dynamic_profiles=self._ns.get("factor_profiles"),
                    cash=accountant.cash,
                )
                factor_text = format_factor_report(factor_report)
                self._ns.set("factor_exposure_report", factor_report)
                self._ns.set("factor_exposure_text", factor_text)
                ctx["sizing_context"]["risk_mode"] = factor_report.get("risk_mode", "normal")
                ctx["sizing_context"]["factor_exposure_report"] = factor_report
                ctx["sizing_context"]["factor_exposure_text"] = factor_text
            if ctx["sizing_context"].get("loss_review_restriction", {}).get("block_new_risk"):
                ctx["sizing_context"]["risk_mode"] = "reduce_only"

        # Store performance metrics in namespace for PM/CIO access
        if accountant and hasattr(accountant, "performance_summary"):
            perf = accountant.performance_summary()
            self._ns.set("performance_summary", perf)
            ctx["performance_summary"] = perf

        # Feed closed trades to outcome tracker + signal scorer, inject into PM context
        if accountant:
            closed = accountant.closed_trades
            self._outcome_tracker.ingest(closed)
            self._signal_scorer.ingest_closed_trades(closed)

            track_record = self._outcome_tracker.format_for_prompt()
            signal_quality = self._signal_scorer.format_for_prompt()
            ctx["trade_track_record"] = track_record
            ctx["signal_quality"] = signal_quality
            self._ns.set("trade_track_record", track_record)
            self._ns.set("signal_quality", signal_quality)

        # Inject firm intelligence memo (cross-pod views) if available
        firm_memo = self._ns.get("firm_memo")
        if firm_memo:
            ctx["firm_memo"] = firm_memo

        managed = self._managed_runtime()
        if managed:
            try:
                prior_reports = managed.reports.list_reports(
                    limit=12,
                    pod_id=self._pod_id,
                )
                ctx["prior_reports"] = prior_reports
                self._ns.set("prior_reports", prior_reports)
            except Exception:
                ctx["prior_reports"] = []

        evidence_review_text = self._ns.get("evidence_review_text")
        evidence_trade_guard = self._ns.get("evidence_trade_guard") or {}
        if evidence_review_text:
            ctx["evidence_review_text"] = evidence_review_text
            if "sizing_context" in ctx:
                ctx["sizing_context"]["evidence_review_text"] = evidence_review_text
                ctx["sizing_context"]["evidence_trade_guard"] = evidence_trade_guard

        thesis_reviews = self._review_open_position_theses(ctx, accountant)
        if thesis_reviews:
            thesis_text = format_thesis_reviews_for_prompt(thesis_reviews)
            ctx["thesis_lifecycle_reviews"] = thesis_reviews
            ctx["thesis_lifecycle_text"] = thesis_text
            if "sizing_context" in ctx:
                ctx["sizing_context"]["thesis_lifecycle_reviews"] = thesis_reviews
                ctx["sizing_context"]["thesis_lifecycle_text"] = thesis_text

        thesis_monitor_results = self._run_thesis_monitor(ctx, accountant)
        if thesis_monitor_results and "sizing_context" in ctx:
            ctx["sizing_context"]["thesis_monitor_results"] = thesis_monitor_results

        # 3. PM (with Signal↔PM challenge, max 5 iter — handled inside pm.run_cycle)
        pm_run_id = self._managed_start_run(
            agent_id=f"{self._pod_id}.pm",
            agent_type="pm",
            task="pm_decision",
            trigger="pod_cycle",
            input_payload={"ctx_keys": sorted(ctx.keys())},
        )
        try:
            pm_out = await self._pm.run_cycle(ctx)  # type: ignore[union-attr]
            self._managed_complete_run(pm_run_id, pm_out)
        except Exception as exc:
            self._managed_fail_run(pm_run_id, exc)
            raise
        ctx["pm_run_id"] = pm_run_id
        ctx.update(pm_out)
        pm_out = await self._maybe_run_specialist_round(ctx, pm_out, parent_run_id=pm_run_id)
        if pm_out:
            ctx.update(pm_out)
        _pm_report = self._ns.get("last_pm_decision") or {}
        if _pm_report:
            _catalyst_ids = list(_pm_report.get("catalyst_ids") or [])
            for _trade in _pm_report.get("trades", []) or []:
                if isinstance(_trade, dict):
                    _catalyst_ids.extend(str(x) for x in (_trade.get("catalyst_ids") or []) if x)
            _pm_report_id = self._record_managed_report(
                report_type="pm_decision",
                title=f"{self._pod_id.upper()} PM decision",
                summary=str(_pm_report.get("action_summary") or _pm_report.get("reasoning") or "PM decision")[:1000],
                body_markdown=json.dumps(_pm_report, default=str, indent=2)[:8000],
                related_run_ids=[pm_run_id] if pm_run_id else [],
                related_catalyst_ids=list(dict.fromkeys(_catalyst_ids)),
                tags=["pm_decision"],
                quality_flags=[],
            )
            _unique_catalysts = list(dict.fromkeys(str(x) for x in _catalyst_ids if x))
            if _unique_catalysts:
                self._update_catalyst_lifecycle(
                    _unique_catalysts,
                    status="acted_on" if _pm_report.get("trades") else "active",
                    linked_run_ids=[pm_run_id] if pm_run_id else [],
                    linked_report_ids=[_pm_report_id] if _pm_report_id else [],
                )
            _ignored = [
                str(item.get("event_id"))
                for item in (_pm_report.get("ignored_catalysts") or [])
                if isinstance(item, dict) and item.get("event_id")
            ]
            if _ignored:
                self._update_catalyst_lifecycle(
                    _ignored,
                    status="ignored",
                    linked_run_ids=[pm_run_id] if pm_run_id else [],
                    linked_report_ids=[_pm_report_id] if _pm_report_id else [],
                )

        # 3.1 Thesis verification: evaluate PM reasoning quality, request revision if weak
        thesis_gate_result = {"passed": True, "quality_score": 1.0, "feedback": ""}
        try:
            from src.core.models.messages import AgentMessage as _AgentMessage
            from datetime import timezone as _tz
            _pm_decision = self._ns.get("last_pm_decision") or {}
            _active = [t for t in _pm_decision.get("trades", []) if str(t.get("action", "HOLD")).upper() != "HOLD"]
            if _active:
                _verifier = ThesisVerifier()
                _revision_occurred = False
                _last_result = None
                for _round in range(2):
                    thesis_run_id = self._managed_start_run(
                        agent_id=f"{self._pod_id}.thesis_verifier",
                        agent_type="thesis_verifier",
                        task="thesis_verification",
                        trigger=f"round:{_round + 1}",
                        parent_run_id=pm_run_id,
                        input_payload={"pod_id": self._pod_id, "active_trade_count": len(_active)},
                    )
                    try:
                        _result = await _verifier.verify_with_llm(_pm_decision, self._pod_id)
                        self._managed_complete_run(
                            thesis_run_id,
                            {
                                "passed": _result.passed,
                                "quality_score": _result.quality_score,
                                "feedback": _result.feedback[:500],
                            },
                        )
                        self._record_managed_report(
                            report_type="thesis_review",
                            title=f"{self._pod_id.upper()} thesis verification",
                            summary=f"passed={_result.passed}, score={_result.quality_score:.2f}",
                            body_markdown=str(_result.feedback or ""),
                            related_run_ids=[thesis_run_id] if thesis_run_id else [],
                            related_catalyst_ids=list(_pm_decision.get("catalyst_ids") or []),
                            tags=["thesis_verification"],
                            quality_flags=[] if _result.passed else ["thesis_gate_failed"],
                        )
                    except Exception as exc:
                        self._managed_fail_run(thesis_run_id, exc)
                        raise
                    _last_result = _result
                    if _result.passed:
                        if _revision_occurred:
                            # Publish "thesis revised and verified" event
                            await self._bus.publish("agent.activity", _AgentMessage(
                                timestamp=datetime.now(_tz.utc),
                                sender=f"{self._pod_id}.pm",
                                recipient="dashboard",
                                topic="agent.activity",
                                payload={
                                    "agent_id": f"{self._pod_id}_pm",
                                    "agent_role": "PM",
                                    "pod_id": self._pod_id,
                                    "action": "thesis_revised",
                                    "summary": f"{self._pod_id.upper()} PM: thesis strengthened after revision (score={_result.quality_score:.2f})",
                                    "detail": _pm_decision.get("reasoning", "")[:300],
                                },
                            ), publisher_id=f"{self._pod_id}.pm")
                        logger.debug("[%s] Thesis verified: score=%.2f", self._pod_id, _result.quality_score)
                        break
                    logger.info(
                        "[%s] Thesis revision round %d: score=%.2f — requesting stronger reasoning",
                        self._pod_id, _round + 1, _result.quality_score,
                    )
                    # Publish "thesis challenged" event
                    await self._bus.publish("agent.activity", _AgentMessage(
                        timestamp=datetime.now(_tz.utc),
                        sender=f"{self._pod_id}.pm",
                        recipient="dashboard",
                        topic="agent.activity",
                        payload={
                            "agent_id": f"{self._pod_id}_pm",
                            "agent_role": "PM",
                            "pod_id": self._pod_id,
                            "action": "thesis_challenged",
                            "summary": f"{self._pod_id.upper()} PM: reasoning challenged (round {_round+1}, score={_result.quality_score:.2f})",
                            "detail": _result.feedback[:300],
                        },
                    ), publisher_id=f"{self._pod_id}.pm")
                    _revision_occurred = True
                    self._ns.set("thesis_revision_feedback", {
                        "feedback": _result.feedback,
                        "round": _round + 1,
                    })
                    try:
                        _revised = await self._pm.run_cycle(ctx)  # type: ignore[union-attr]
                        if _revised:
                            ctx.update(_revised)
                        _pm_decision = self._ns.get("last_pm_decision") or _pm_decision
                    finally:
                        self._ns.set("thesis_revision_feedback", None)
                if _last_result is not None:
                    thesis_gate_result = {
                        "passed": bool(_last_result.passed),
                        "quality_score": float(_last_result.quality_score),
                        "feedback": _last_result.feedback,
                    }
                    if not _last_result.passed:
                        await self._bus.publish("agent.activity", _AgentMessage(
                            timestamp=datetime.now(_tz.utc),
                            sender=f"{self._pod_id}.pm",
                            recipient="dashboard",
                            topic="agent.activity",
                            payload={
                                "agent_id": f"{self._pod_id}_pm",
                                "agent_role": "PM",
                                "pod_id": self._pod_id,
                                "action": "thesis_gate_failed",
                                "summary": (
                                    f"{self._pod_id.upper()} PM: BUY thesis gate failed "
                                    f"(score={_last_result.quality_score:.2f}); new buys blocked"
                                ),
                                "detail": _last_result.feedback[:500],
                            },
                        ), publisher_id=f"{self._pod_id}.pm")
        except Exception as _e:
            logger.debug("[%s] Thesis verification skipped: %s", self._pod_id, _e)
        self._ns.set("thesis_gate_result", thesis_gate_result)
        self._record_decision_snapshots(ctx, accountant, pm_run_id, thesis_gate_result)

        # Emit pod macro view for cross-pod intelligence
        features = ctx.get("features", {})
        regime = features.get("regime", {})
        last_pm = self._ns.get("last_pm_decision") or {}
        self._ns.set("macro_view", {
            "pod_id": self._pod_id,
            "regime": regime.get("label", "Unknown"),
            "outlook": features.get("macro_outlook", "neutral"),
            "action": last_pm.get("action_summary", "holding")[:100],
        })

        # Log PM reasoning for all held positions (diary per position)
        self._log_pm_reasoning(last_pm)

        # --- Collect ALL orders from PM (primary + additional) ---
        all_orders: list[Order] = self._orders_from_pm_context(ctx)

        # Universe boundary enforcement: reject trades for symbols that belong
        # exclusively to another pod's seed universe (prevents cross-pod contamination).
        from src.core.config.universes import POD_UNIVERSES
        my_symbols = POD_UNIVERSES.get(self._pod_id, [])
        valid_orders: list[Order] = []
        for ord_ in all_orders:
            blocked = False
            for other_pod, other_symbols in POD_UNIVERSES.items():
                if other_pod != self._pod_id and ord_.symbol in other_symbols:
                    if ord_.symbol not in my_symbols:
                        logger.warning(
                            "[%s] Rejected trade for %s — symbol belongs to %s universe, not %s",
                            self._pod_id, ord_.symbol, other_pod, self._pod_id,
                        )
                        self._record_trade_block(
                            "universe",
                            ord_,
                            f"Symbol belongs to {other_pod} universe, not {self._pod_id}",
                        )
                        blocked = True
                    break
            if not blocked:
                valid_orders.append(ord_)

        if not valid_orders:
            # No trade proposed — still run Ops
            await self._run_agent_stage(
                self._ops,
                ctx,
                agent_id=f"{self._pod_id}.ops",
                agent_type="ops",
                task="ops_heartbeat",
            )  # type: ignore[arg-type]
            return

        # --- Process each order through risk review + execution ---
        last_pm = self._ns.get("last_pm_decision") or {}
        pm_trades = last_pm.get("trades", [])
        executed_count = 0
        rejected_count = 0
        committee_revision_used = False

        for order in valid_orders:
            # Find matching PM trade metadata for this specific order
            matching_trade = next(
                (t for t in pm_trades if isinstance(t, dict) and t.get("symbol") == order.symbol),
                {},
            )

            trade_reasoning = self._entry_thesis_for_order(order, matching_trade, last_pm)
            dependency_ok, dependency_reason = self._hard_dependency_allows_order(order)
            if not dependency_ok:
                logger.warning(
                    "[%s] Managed dependency gate blocked %s %s: %s",
                    self._pod_id,
                    order.side.value.upper(),
                    order.symbol,
                    dependency_reason,
                )
                self._record_trade_block("dependency", order, dependency_reason)
                rejected_count += 1
                continue

            allowed_by_execution_cooldown, execution_cooldown_reason = self._execution_cooldown_allows_order(order, accountant)
            if not allowed_by_execution_cooldown:
                logger.warning(
                    "[%s] Execution cooldown blocked %s %s: %s",
                    self._pod_id,
                    order.side.value.upper(),
                    order.symbol,
                    execution_cooldown_reason,
                )
                self._record_trade_block("execution_cooldown", order, execution_cooldown_reason)
                rejected_count += 1
                continue

            allowed_by_broker_guard, broker_guard_reason = self._broker_guard_allows_order(order, accountant)
            if not allowed_by_broker_guard:
                logger.warning(
                    "[%s] Broker guard blocked %s %s: %s",
                    self._pod_id,
                    order.side.value.upper(),
                    order.symbol,
                    broker_guard_reason,
                )
                self._record_trade_block("broker_guard", order, broker_guard_reason)
                try:
                    from src.core.models.messages import AgentMessage

                    await self._bus.publish("agent.activity", AgentMessage(
                        timestamp=datetime.now(timezone.utc),
                        sender=f"{self._pod_id}.runtime",
                        recipient="dashboard",
                        topic="agent.activity",
                        payload={
                            "agent_id": f"{self._pod_id}_runtime",
                            "agent_role": "Runtime",
                            "pod_id": self._pod_id,
                            "action": "broker_guard_blocked",
                            "summary": (
                                f"{self._pod_id.upper()} broker guard blocked "
                                f"{order.side.value.upper()} {order.symbol}"
                            ),
                            "detail": broker_guard_reason[:500],
                        },
                    ), publisher_id=f"{self._pod_id}.runtime")
                except Exception as exc:
                    logger.debug("[%s] Failed to publish broker guard event: %s", self._pod_id, exc)
                rejected_count += 1
                continue

            allowed_by_loss_review, loss_review_reason = self._loss_review_allows_order(order, accountant)
            if not allowed_by_loss_review:
                logger.warning(
                    "[%s] Loss review blocked %s %s: %s",
                    self._pod_id,
                    order.side.value.upper(),
                    order.symbol,
                    loss_review_reason,
                )
                self._record_trade_block("loss_review", order, loss_review_reason)
                try:
                    from src.core.models.messages import AgentMessage as _AgentMessage

                    await self._bus.publish("agent.activity", _AgentMessage(
                        timestamp=datetime.now(timezone.utc),
                        sender=f"{self._pod_id}.runtime",
                        recipient="dashboard",
                        topic="agent.activity",
                        payload={
                            "agent_id": f"{self._pod_id}_runtime",
                            "agent_role": "Runtime",
                            "pod_id": self._pod_id,
                            "action": "loss_review_gate_failed",
                            "summary": (
                                f"{self._pod_id.upper()} loss review blocked "
                                f"{order.side.value.upper()} {order.symbol}"
                            ),
                            "detail": loss_review_reason[:500],
                        },
                    ), publisher_id=f"{self._pod_id}.runtime")
                except Exception as exc:
                    logger.debug("[%s] Failed to publish loss review gate event: %s", self._pod_id, exc)
                rejected_count += 1
                continue

            existing_review = thesis_reviews.get(order.symbol.upper()) if thesis_reviews else None
            existing_position = accountant.current_positions.get(order.symbol) if accountant else None
            is_expansion = (
                existing_position is not None
                and (
                    (order.side.value.upper() == "BUY" and existing_position.qty > 0)
                    or (order.side.value.upper() == "SELL" and existing_position.qty < 0)
                )
            )
            allowed_by_evidence_guard, evidence_guard_reason = self._evidence_guard_allows_order(
                order=order,
                accountant=accountant,
                trade_reasoning=trade_reasoning,
                thesis_review=existing_review,
            )
            if not allowed_by_evidence_guard:
                logger.warning(
                    "[%s] Evidence review guard blocked %s %s: %s",
                    self._pod_id,
                    order.side.value.upper(),
                    order.symbol,
                    evidence_guard_reason,
                )
                self._record_trade_block("evidence_review", order, evidence_guard_reason)
                try:
                    from src.core.models.messages import AgentMessage

                    await self._bus.publish("agent.activity", AgentMessage(
                        timestamp=datetime.now(timezone.utc),
                        sender=f"{self._pod_id}.runtime",
                        recipient="dashboard",
                        topic="agent.activity",
                        payload={
                            "agent_id": f"{self._pod_id}_runtime",
                            "agent_role": "Runtime",
                            "pod_id": self._pod_id,
                            "symbol": order.symbol,
                            "action": "evidence_review_blocked",
                            "status": "BLOCKED",
                            "summary": (
                                f"{self._pod_id.upper()} evidence guard blocked "
                                f"{order.side.value.upper()} {order.symbol}"
                            ),
                            "detail": evidence_guard_reason[:700],
                            "reason": evidence_guard_reason,
                        },
                    ), publisher_id=f"{self._pod_id}.runtime")
                except Exception as exc:
                    logger.debug("[%s] Failed to publish evidence guard block: %s", self._pod_id, exc)
                rejected_count += 1
                continue

            quality_gate = self._pre_trade_quality_gate(
                order=order,
                matching_trade=matching_trade,
                pm_decision=last_pm,
                thesis_gate_result=thesis_gate_result,
                trade_reasoning=trade_reasoning,
            )
            self._record_quality_gate_result(quality_gate)
            if quality_gate.get("action") == "block":
                logger.warning(
                    "[%s] Pre-trade quality gate blocked %s %s: %s",
                    self._pod_id,
                    order.side.value.upper(),
                    order.symbol,
                    quality_gate.get("reason", ""),
                )
                self._record_trade_block(
                    "quality_gate",
                    order,
                    quality_gate.get("reason", "") or "Pre-trade quality gate blocked the order",
                )
                rejected_count += 1
                continue
            if quality_gate.get("action") == "warn":
                logger.info(
                    "[%s] Pre-trade quality gate warning for %s %s: %s",
                    self._pod_id,
                    order.side.value.upper(),
                    order.symbol,
                    quality_gate.get("reason", ""),
                )
                try:
                    from src.core.models.messages import AgentMessage

                    await self._bus.publish("agent.activity", AgentMessage(
                        timestamp=datetime.now(timezone.utc),
                        sender=f"{self._pod_id}.runtime",
                        recipient="dashboard",
                        topic="agent.activity",
                        payload={
                            "agent_id": f"{self._pod_id}_runtime",
                            "agent_role": "Runtime",
                            "pod_id": self._pod_id,
                            "symbol": order.symbol,
                            "action": "quality_gate_warning",
                            "summary": (
                                f"{self._pod_id.upper()} quality gate warned on "
                                f"{order.side.value.upper()} {order.symbol}"
                            ),
                            "detail": quality_gate.get("reason", "")[:500],
                            "status": "WARN",
                        },
                    ), publisher_id=f"{self._pod_id}.runtime")
                except Exception as exc:
                    logger.debug("[%s] Failed to publish quality gate warning: %s", self._pod_id, exc)

            if (
                is_expansion
            ):
                fresh_ok, fresh_reason = expansion_thesis_is_fresh(trade_reasoning, existing_review)
                if not fresh_ok:
                    logger.warning(
                        "[%s] Thesis lifecycle gate blocked add to %s: %s",
                        self._pod_id, order.symbol, fresh_reason,
                    )
                    self._record_trade_block("thesis_lifecycle", order, fresh_reason)
                    rejected_count += 1
                    continue

            data_quality = self._pre_trade_data_quality(order, accountant, ctx)
            self._ns.set("last_data_quality_check", data_quality)
            if not data_quality.get("passed", False):
                logger.warning(
                    "[%s] Data quality gate blocked %s %s: %s",
                    self._pod_id,
                    order.side.value.upper(),
                    order.symbol,
                    "; ".join(data_quality.get("issues", [])),
                )
                self._record_data_quality_failure(data_quality)
                self._record_trade_block(
                    "data_quality",
                    order,
                    "; ".join(data_quality.get("issues", [])) or "Market data quality gate failed",
                )
                try:
                    from src.core.models.messages import AgentMessage

                    await self._bus.publish("agent.activity", AgentMessage(
                        timestamp=datetime.now(timezone.utc),
                        sender=f"{self._pod_id}.runtime",
                        recipient="dashboard",
                        topic="agent.activity",
                        payload={
                            "agent_id": f"{self._pod_id}_runtime",
                            "agent_role": "Runtime",
                            "pod_id": self._pod_id,
                            "action": "data_quality_gate_failed",
                            "summary": (
                                f"{self._pod_id.upper()} data gate blocked "
                                f"{order.side.value.upper()} {order.symbol}"
                            ),
                            "detail": "; ".join(data_quality.get("issues", []))[:500],
                        },
                    ), publisher_id=f"{self._pod_id}.runtime")
                except Exception as exc:
                    logger.debug("[%s] Failed to publish data quality gate event: %s", self._pod_id, exc)
                rejected_count += 1
                continue

            monitor_block = (self._ns.get("thesis_add_blocked") or {}).get(order.symbol.upper())
            if is_expansion and monitor_block:
                reason = (
                    monitor_block.get("reason")
                    or "; ".join(monitor_block.get("triggers") or [])
                    or "Live thesis monitor blocks expansion until the thesis is refreshed"
                )
                logger.warning("[%s] Thesis monitor blocked add to %s: %s", self._pod_id, order.symbol, reason)
                self._record_trade_block("thesis_monitor", order, reason)
                rejected_count += 1
                continue

            original_order = order
            order, portfolio_construction_review = self._apply_portfolio_construction_review(order, accountant, data_quality)
            if order is None:
                reason = (
                    portfolio_construction_review.get("reason")
                    or f"Portfolio construction {portfolio_construction_review.get('action', 'review')} blocked the trade"
                )
                self._record_trade_block("portfolio_construction", original_order, reason)
                rejected_count += 1
                continue

            committee_review = await self._committee_review_order(
                order=order,
                accountant=accountant,
                matching_trade=matching_trade,
                pm_decision=last_pm,
                trade_reasoning=trade_reasoning,
                thesis_gate_result=thesis_gate_result,
                quality_gate=quality_gate,
                ctx=ctx,
            )
            if committee_review and committee_review.get("decision") == "REVISE" and not committee_revision_used:
                committee_revision_used = True
                revised_orders = await self._run_committee_revision_round(ctx, committee_review)
                replacement = self._find_revised_order(order, revised_orders)
                if replacement is None:
                    reason = (
                        committee_review.get("reason")
                        or "Investment committee requested a PM revision, but no revised order was submitted."
                    )
                    self._record_trade_block("committee_review", order, reason)
                    rejected_count += 1
                    continue

                order = replacement
                last_pm = self._ns.get("last_pm_decision") or last_pm
                pm_trades = last_pm.get("trades", [])
                matching_trade = next(
                    (t for t in pm_trades if isinstance(t, dict) and t.get("symbol") == order.symbol),
                    {},
                )
                trade_reasoning = self._entry_thesis_for_order(order, matching_trade, last_pm)
                existing_position = accountant.current_positions.get(order.symbol) if accountant else None
                is_expansion = (
                    existing_position is not None
                    and (
                        (order.side.value.upper() == "BUY" and existing_position.qty > 0)
                        or (order.side.value.upper() == "SELL" and existing_position.qty < 0)
                    )
                )
                existing_review = thesis_reviews.get(order.symbol.upper()) if thesis_reviews else None
                quality_gate = self._pre_trade_quality_gate(
                    order=order,
                    matching_trade=matching_trade,
                    pm_decision=last_pm,
                    thesis_gate_result=thesis_gate_result,
                    trade_reasoning=trade_reasoning,
                )
                self._record_quality_gate_result(quality_gate)
                if quality_gate.get("action") == "block":
                    self._record_trade_block(
                        "quality_gate",
                        order,
                        quality_gate.get("reason", "") or "Pre-trade quality gate blocked revised order",
                    )
                    rejected_count += 1
                    continue
                data_quality = self._pre_trade_data_quality(order, accountant, ctx)
                self._ns.set("last_data_quality_check", data_quality)
                if not data_quality.get("passed", False):
                    self._record_data_quality_failure(data_quality)
                    self._record_trade_block(
                        "data_quality",
                        order,
                        "; ".join(data_quality.get("issues", [])) or "Market data quality gate failed",
                    )
                    rejected_count += 1
                    continue
                monitor_block = (self._ns.get("thesis_add_blocked") or {}).get(order.symbol.upper())
                if is_expansion and monitor_block:
                    reason = (
                        monitor_block.get("reason")
                        or "; ".join(monitor_block.get("triggers") or [])
                        or "Live thesis monitor blocks expansion until the thesis is refreshed"
                    )
                    self._record_trade_block("thesis_monitor", order, reason)
                    rejected_count += 1
                    continue
                order, portfolio_construction_review = self._apply_portfolio_construction_review(order, accountant, data_quality)
                if order is None:
                    reason = (
                        portfolio_construction_review.get("reason")
                        or f"Portfolio construction {portfolio_construction_review.get('action', 'review')} blocked revised trade"
                    )
                    self._record_trade_block("portfolio_construction", replacement, reason)
                    rejected_count += 1
                    continue
                committee_review = await self._committee_review_order(
                    order=order,
                    accountant=accountant,
                    matching_trade=matching_trade,
                    pm_decision=last_pm,
                    trade_reasoning=trade_reasoning,
                    thesis_gate_result=thesis_gate_result,
                    quality_gate=quality_gate,
                    ctx=ctx,
                )

            if committee_review and committee_review.get("decision") in {"REVISE", "REJECT"}:
                reason = committee_review.get("reason") or f"IC {committee_review.get('decision')} blocked the trade"
                logger.warning(
                    "[%s] Investment committee blocked %s %s: %s",
                    self._pod_id,
                    order.side.value.upper(),
                    order.symbol,
                    reason,
                )
                self._record_trade_block("committee_review", order, reason)
                rejected_count += 1
                continue

            entry_macro_regime = current_regime(ctx.get("features"))
            thesis_review = existing_review or {
                "symbol": order.symbol.upper(),
                "status": "valid",
                "score": thesis_gate_result.get("quality_score", 1.0),
                "issues": [],
                "reviewed_at": datetime.utcnow().isoformat(),
            }
            evidence_packet = self._build_trade_evidence_packet(
                order=order,
                matching_trade=matching_trade,
                pm_decision=last_pm,
                ctx=ctx,
                accountant=accountant,
                trade_reasoning=trade_reasoning,
                thesis_gate_result=thesis_gate_result,
                quality_gate=quality_gate,
                data_quality=data_quality,
                thesis_review=thesis_review,
                entry_macro_regime=entry_macro_regime,
            )

            # Set per-order metadata so exec trader can attach it to fills
            self._ns.set("pm_trade_metadata", {
                "entry_thesis": trade_reasoning,
                "reasoning": trade_reasoning,
                "conviction": order.conviction,
                "strategy_tag": order.strategy_tag,
                "signal_snapshot": last_pm.get("signal_snapshot", {}),
                "stop_loss_pct": matching_trade.get("stop_loss_pct"),
                "take_profit_pct": matching_trade.get("take_profit_pct"),
                "take_profit_levels": matching_trade.get("take_profit_levels", []),
                "exit_when": matching_trade.get("exit_when", ""),
                "max_hold_days": matching_trade.get("max_hold_days", 0),
                "entry_macro_regime": entry_macro_regime,
                "thesis_review": thesis_review,
                "evidence_packet": evidence_packet,
            })

            # Concentration guard: block firm-level sector overconcentration on BUY orders
            if getattr(order, "side", None) is not None and order.side.value.upper() == "BUY":
                firm_exposure = self._ns.get("firm_exposure") or {}
                POD_SECTOR_MAP = {
                    "equities": "equity",
                    "fx": "fx",
                    "crypto": "crypto",
                    "commodities": "commodity",
                }
                sector = POD_SECTOR_MAP.get(self._pod_id, self._pod_id)
                allowed, reason = check_concentration(sector, firm_exposure)
                if not allowed:
                    logger.warning("[%s] Concentration limit blocked %s buy: %s", self._pod_id, order.symbol, reason)
                    self._record_trade_block("concentration", order, reason)
                    rejected_count += 1
                    continue

            # 4. Risk sign-off loop (PM↔Risk deliberation per order)
            self._ns.set("last_risk_rejection_reason", None)
            risk_run_id = self._managed_start_run(
                agent_id=f"{self._pod_id}.risk",
                agent_type="risk",
                task="risk_signoff",
                trigger="pm_order",
                input_payload={"symbol": order.symbol, "side": order.side.value, "qty": order.quantity},
            )
            try:
                approved_order, exit_orders = await self._run_risk_loop_with_exits(order)
                self._managed_complete_run(
                    risk_run_id,
                    {
                        "approved": approved_order is not None,
                        "exit_orders": len(exit_orders or []),
                        "reason": self._ns.get("last_risk_rejection_reason") or "",
                    },
                )
            except Exception as exc:
                self._managed_fail_run(risk_run_id, exc)
                raise

            # Execute exit orders first (stop-loss / take-profit)
            if exit_orders:
                for eo in exit_orders:
                    exit_ctx = {
                        "approved_order": eo,
                        "mandate": self._ns.get("governance_mandate"),
                        "risk_halt": False,
                        "auto_exit": True,
                    }
                    try:
                        await self._exec_trader.run_cycle(exit_ctx)  # type: ignore[union-attr]
                        logger.info("[%s] Auto-exit executed: %s %s %.4f", self._pod_id, eo.side.value, eo.symbol, eo.quantity)
                    except Exception as e:
                        logger.warning("[%s] Auto-exit failed for %s: %s", self._pod_id, eo.symbol, e)

            if approved_order is None:
                rejected_count += 1
                self._record_trade_block(
                    "risk",
                    order,
                    self._ns.get("last_risk_rejection_reason") or "Risk did not approve the order",
                )
                logger.info("[%s] Order %d/%d rejected by Risk: %s %s",
                            self._pod_id, executed_count + rejected_count,
                            len(valid_orders), order.side.value, order.symbol)
                continue

            # 5. Execution Trader (with governance constraints)
            last_block = self._ns.get("last_trade_block") or {}
            if str(last_block.get("symbol", "")).upper() == approved_order.symbol.upper():
                self._ns.set("last_trade_block", None)
            exec_ctx = dict(ctx)
            exec_ctx["approved_order"] = approved_order
            exec_ctx["mandate"] = self._ns.get("governance_mandate")
            exec_ctx["risk_halt"] = self._ns.get("governance_risk_halt", False)
            exec_ctx["risk_halt_reason"] = self._ns.get("governance_risk_halt_reason")
            exec_ctx["drawdown_halt"] = self._ns.get("drawdown_halt", False)
            exec_ctx["drawdown_sizing_mult"] = float(self._ns.get("drawdown_sizing_mult", 1.0))
            exec_run_id = self._managed_start_run(
                agent_id=f"{self._pod_id}.exec_trader",
                agent_type="execution",
                task="execution_submit",
                trigger="risk_approved",
                input_payload={"symbol": approved_order.symbol, "side": approved_order.side.value, "qty": approved_order.quantity},
            )
            try:
                await self._exec_trader.run_cycle(exec_ctx)  # type: ignore[union-attr]
                last_order_update = self._ns.get("last_order") or {"symbol": approved_order.symbol}
                self._managed_complete_run(exec_run_id, last_order_update)
                trade_ids = []
                if isinstance(last_order_update, dict):
                    for key in ("order_id", "broker_order_id", "local_order_id"):
                        if last_order_update.get(key):
                            trade_ids.append(str(last_order_update.get(key)))
                self._update_decision_snapshot_order_status(approved_order, last_order_update)
                self._update_catalyst_lifecycle(
                    list(matching_trade.get("catalyst_ids") or last_pm.get("catalyst_ids") or []),
                    linked_run_ids=[exec_run_id] if exec_run_id else [],
                    linked_trade_ids=trade_ids,
                )
            except Exception as exc:
                self._managed_fail_run(exec_run_id, exc)
                raise
            executed_count += 1

        if executed_count + rejected_count > 1:
            logger.info("[%s] Multi-order cycle: %d executed, %d rejected (of %d proposed)",
                        self._pod_id, executed_count, rejected_count, len(valid_orders))

        # 6. Ops
        await self._run_agent_stage(
            self._ops,
            ctx,
            agent_id=f"{self._pod_id}.ops",
            agent_type="ops",
            task="ops_heartbeat",
        )  # type: ignore[arg-type]

    def _inject_foresight_context(self, ctx: dict) -> None:
        """Attach advisory catalyst events to signal features and PM context."""
        events = self._ns.get("foresight_events") or self._ns.get("catalyst_events") or []
        if not isinstance(events, list):
            events = []
        if not events:
            return
        features = ctx.setdefault("features", {})
        if isinstance(features, dict):
            features["foresight_events"] = events[:10]
            features["catalyst_events"] = events[:10]
        ctx["foresight_events"] = events[:10]
        text = self._ns.get("foresight_text")
        if text:
            ctx["foresight_text"] = text
            if "sizing_context" in ctx and isinstance(ctx["sizing_context"], dict):
                ctx["sizing_context"]["foresight_text"] = text

    def _orders_from_pm_context(self, ctx: dict) -> list[Order]:
        """Collect primary and additional PM orders, then clear transient extras."""
        orders: list[Order] = []
        primary_order: Order | None = ctx.get("order")
        if primary_order is not None:
            orders.append(primary_order)

        additional_raw = self._ns.get("pm_additional_orders") or []
        for raw in additional_raw:
            try:
                orders.append(Order(**raw))
            except Exception as e:
                logger.warning("[%s] Skipping malformed additional order: %s", self._pod_id, e)
        self._ns.set("pm_additional_orders", [])
        return orders

    async def _maybe_run_specialist_round(self, ctx: dict, pm_out: dict, parent_run_id: str | None = None) -> dict:
        """Run at most one PM-requested specialist round, then ask PM for final decision."""
        last_pm = self._ns.get("last_pm_decision") or {}
        requests = last_pm.get("analyst_requests") or []
        if not isinstance(requests, list) or not requests:
            return pm_out
        managed = self._managed_runtime()
        if managed:
            try:
                budget = managed.budgets.summary(limit=500).get("today", {})
                if budget.get("degraded") and len(requests) > 1:
                    await self._publish_activity(
                        action="budget_degraded_specialists",
                        summary=f"{self._pod_id.upper()} specialist requests reduced by budget policy",
                        detail=budget.get("degraded_reason", "")[:500],
                        status="DEGRADED",
                    )
                    requests = requests[:1]
            except Exception:
                pass

        run_id = self._managed_start_run(
            agent_id=f"{self._pod_id}.specialists",
            agent_type="specialist",
            task="specialist_briefs",
            trigger="pm_request",
            parent_run_id=parent_run_id,
            input_payload={"request_count": len(requests), "types": [r.get("type") for r in requests if isinstance(r, dict)]},
        )
        try:
            briefs = await self._specialist_runner.run_requests(
                pod_id=self._pod_id,
                requests=requests,
                context=ctx,
            )
            artifact_id = self._record_managed_artifact(
                "specialist_briefs",
                status="fresh" if briefs else "degraded",
                freshness_seconds=1800,
                source_run_id=run_id,
                payload_ref="/api/specialist-briefs",
            )
            self._managed_complete_run(run_id, {"brief_count": len(briefs or [])}, artifact_refs=[artifact_id] if artifact_id else [])
        except Exception as exc:
            self._record_managed_artifact(
                "specialist_briefs",
                status="failed",
                freshness_seconds=300,
                source_run_id=run_id,
                payload_ref="/api/specialist-briefs",
            )
            self._managed_fail_run(run_id, exc)
            raise
        self._record_specialist_round(requests, briefs)
        for brief in briefs or []:
            if isinstance(brief, dict):
                _brief_catalysts = [str(x) for x in brief.get("related_catalyst_ids", [])] if isinstance(brief.get("related_catalyst_ids"), list) else []
                _brief_report_id = self._record_managed_report(
                    report_type="specialist_brief",
                    title=f"{self._pod_id.upper()} {brief.get('type', 'specialist')} brief",
                    summary=str(brief.get("conclusion") or brief.get("summary") or "")[:1000],
                    body_markdown=json.dumps(brief, default=str, indent=2)[:8000],
                    symbol=str(brief.get("symbol") or ""),
                    related_run_ids=[run_id] if run_id else [],
                    related_catalyst_ids=_brief_catalysts,
                    tags=["specialist", str(brief.get("type") or "")],
                )
                self._update_catalyst_lifecycle(
                    _brief_catalysts,
                    linked_run_ids=[run_id] if run_id else [],
                    linked_report_ids=[_brief_report_id] if _brief_report_id else [],
                )
        await self._publish_activity(
            action="specialist_request",
            summary=f"{self._pod_id.upper()} PM requested {min(len(requests), 3)} specialist brief(s)",
            detail=json.dumps(requests[:3], default=str)[:900],
            status="REQUESTED",
        )
        if not briefs:
            return pm_out

        features = ctx.setdefault("features", {})
        if isinstance(features, dict):
            features["specialist_briefs"] = briefs
        ctx["specialist_briefs"] = briefs
        self._ns.set("specialist_briefs", briefs)
        await self._publish_activity(
            action="specialist_brief",
            summary=f"{self._pod_id.upper()} received {len(briefs)} specialist brief(s)",
            detail=json.dumps(briefs[:3], default=str)[:1200],
            status="INFO",
        )

        try:
            final_pm_run_id = self._managed_start_run(
                agent_id=f"{self._pod_id}.pm",
                agent_type="pm",
                task="pm_final_after_specialists",
                trigger="specialist_briefs",
                parent_run_id=run_id,
                input_payload={"brief_count": len(briefs)},
            )
            revised = await self._pm.run_cycle(ctx)  # type: ignore[union-attr]
            self._managed_complete_run(final_pm_run_id, revised)
            if revised:
                ctx.update(revised)
                await self._publish_activity(
                    action="specialist_final_decision",
                    summary=f"{self._pod_id.upper()} PM revised after {len(briefs)} specialist brief(s)",
                    detail=(self._ns.get("last_pm_decision") or {}).get("reasoning", "")[:700],
                    status="INFO",
                )
                return revised
        except Exception as exc:
            self._managed_fail_run(locals().get("final_pm_run_id", ""), exc)
            logger.warning("[%s] PM specialist final decision failed: %s", self._pod_id, exc)
        return pm_out

    def _record_specialist_round(self, requests: list, briefs: list[dict]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        request_rows = []
        for req in requests[:6]:
            if isinstance(req, dict):
                request_rows.append({**req, "pod_id": self._pod_id, "created_at": now})
        history = list(self._ns.get("specialist_request_history") or [])
        history = request_rows + history
        self._ns.set("specialist_request_history", history[:100])

        brief_history = list(self._ns.get("specialist_brief_history") or [])
        brief_history = list(briefs or []) + brief_history
        self._ns.set("specialist_brief_history", brief_history[:100])
        for req in request_rows:
            try:
                req["action"] = "specialist_request"
                req["status"] = "REQUESTED"
            except Exception:
                pass
        if briefs:
            for brief in briefs:
                try:
                    brief["pod_id"] = brief.get("pod_id") or self._pod_id
                except Exception:
                    pass

    async def _committee_review_order(
        self,
        *,
        order: Order,
        accountant,
        matching_trade: dict,
        pm_decision: dict,
        trade_reasoning: str,
        thesis_gate_result: dict,
        quality_gate: dict,
        ctx: dict,
    ) -> dict | None:
        should_review, triggers = self._committee.should_review(
            order=order,
            accountant=accountant,
            matching_trade=matching_trade,
            pm_decision=pm_decision,
            thesis_gate_result=thesis_gate_result,
            quality_gate=quality_gate,
        )
        if not should_review:
            return None

        dependency_snapshot = self._managed_dependency_snapshot()
        ctx["ic_dependency_snapshot"] = dependency_snapshot
        run_id = self._managed_start_run(
            agent_id=f"{self._pod_id}.investment_committee",
            agent_type="investment_committee",
            task="committee_review",
            trigger="risk_increasing_trade",
            parent_run_id=ctx.get("pm_run_id") or None,
            input_payload={"symbol": order.symbol, "side": order.side.value, "triggers": triggers},
        )
        try:
            review = await self._committee.review(
                pod_id=self._pod_id,
                order=order,
                accountant=accountant,
                matching_trade=matching_trade,
                pm_decision=pm_decision,
                trade_reasoning=trade_reasoning,
                thesis_gate_result=thesis_gate_result,
                quality_gate=quality_gate,
                ctx=ctx,
                triggers=triggers,
            )
            self._managed_complete_run(run_id, review.model_dump(mode="json"))
        except Exception as exc:
            self._managed_fail_run(run_id, exc)
            raise
        row = review.model_dump(mode="json")
        row["triggers"] = triggers
        row["dependencies"] = dependency_snapshot
        self._record_committee_review(row)
        artifact_id = self._record_managed_artifact(
            "committee_review",
            status="fresh",
            freshness_seconds=1800,
            source_run_id=run_id,
            payload_ref="/api/committee-reviews",
        )
        _ic_catalysts = list(pm_decision.get("catalyst_ids") or [])
        _ic_report_id = self._record_managed_report(
            report_type="committee_review",
            title=f"{self._pod_id.upper()} IC {row.get('decision')} {order.symbol}",
            summary=str(row.get("reason") or "")[:1000],
            body_markdown=json.dumps(row, default=str, indent=2)[:8000],
            symbol=order.symbol,
            related_run_ids=[run_id] if run_id else [],
            related_catalyst_ids=_ic_catalysts,
            tags=["committee_review", row.get("decision", "")],
            quality_flags=["degraded_dependencies"] if dependency_snapshot.get("status") == "degraded" else [],
        )
        self._update_catalyst_lifecycle(
            [str(x) for x in _ic_catalysts if x],
            linked_run_ids=[run_id] if run_id else [],
            linked_report_ids=[_ic_report_id] if _ic_report_id else [],
        )
        if artifact_id:
            self._managed_complete_run(run_id, row, artifact_refs=[artifact_id])
        await self._publish_activity(
            action="committee_review",
            summary=(
                f"{self._pod_id.upper()} IC {row['decision']} "
                f"{order.side.value.upper()} {order.symbol}"
            ),
            detail=row.get("reason", "")[:900],
            status=row.get("decision", "INFO"),
            symbol=order.symbol,
            reason=row.get("reason", ""),
        )
        return row

    def _record_committee_review(self, review: dict) -> None:
        self._ns.set("last_committee_review", review)
        by_symbol = dict(self._ns.get("committee_reviews_by_symbol") or {})
        by_symbol[str(review.get("symbol") or "").upper()] = review
        self._ns.set("committee_reviews_by_symbol", by_symbol)
        history = list(self._ns.get("committee_review_history") or [])
        history.insert(0, review)
        self._ns.set("committee_review_history", history[:100])

    async def _run_committee_revision_round(self, ctx: dict, review: dict) -> list[Order]:
        feedback = review.get("reason") or "Investment committee requested a stronger trade thesis."
        self._ns.set("thesis_revision_feedback", {
            "feedback": (
                "Investment Committee requested revision before risk/execution: "
                + str(feedback)
            ),
            "round": "IC",
        })
        try:
            await self._publish_activity(
                action="committee_revision_requested",
                summary=f"{self._pod_id.upper()} IC requested PM revision",
                detail=str(feedback)[:900],
                status="REVISE",
                symbol=review.get("symbol", ""),
                reason=str(feedback),
            )
            revised = await self._pm.run_cycle(ctx)  # type: ignore[union-attr]
            if revised:
                ctx.update(revised)
            return self._orders_from_pm_context(ctx)
        except Exception as exc:
            logger.warning("[%s] IC revision round failed: %s", self._pod_id, exc)
            return []
        finally:
            self._ns.set("thesis_revision_feedback", None)

    @staticmethod
    def _find_revised_order(original: Order, revised_orders: list[Order]) -> Order | None:
        for order in revised_orders:
            if order.symbol.upper() == original.symbol.upper() and order.side == original.side:
                return order
        return None

    async def _publish_activity(
        self,
        *,
        action: str,
        summary: str,
        detail: str = "",
        status: str = "INFO",
        symbol: str = "",
        reason: str = "",
    ) -> None:
        try:
            from src.core.models.messages import AgentMessage

            await self._bus.publish("agent.activity", AgentMessage(
                timestamp=datetime.now(timezone.utc),
                sender=f"{self._pod_id}.runtime",
                recipient="dashboard",
                topic="agent.activity",
                payload={
                    "agent_id": f"{self._pod_id}_runtime",
                    "agent_role": "Runtime",
                    "pod_id": self._pod_id,
                    "symbol": symbol,
                    "action": action,
                    "summary": summary[:500],
                    "detail": detail[:1200],
                    "status": status,
                    "reason": reason,
                },
            ), publisher_id=f"{self._pod_id}.runtime")
        except Exception as exc:
            logger.debug("[%s] Failed to publish %s activity: %s", self._pod_id, action, exc)

    @staticmethod
    def _parse_timestamp(value) -> datetime | None:
        if value is None:
            return None
        try:
            if isinstance(value, datetime):
                ts = value
            else:
                ts = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            return ts.astimezone(timezone.utc)
        except Exception:
            return None

    @staticmethod
    def _freshness_limit_seconds(symbol: str) -> int:
        return 180 if "/" in str(symbol) else 900

    def _namespace_price_quality(self, symbol: str) -> dict:
        prices = self._ns.get("last_prices") or {}
        updated = self._ns.get("last_price_updated_at") or {}
        sources = self._ns.get("last_price_sources") or {}
        raw_price = prices.get(symbol)
        try:
            price = float(raw_price)
        except (TypeError, ValueError):
            price = 0.0
        ts = self._parse_timestamp(updated.get(symbol))
        age_s = (datetime.now(timezone.utc) - ts).total_seconds() if ts else None
        limit_s = self._freshness_limit_seconds(symbol)
        return {
            "price": price,
            "source": sources.get(symbol) or "last_prices",
            "updated_at": ts.isoformat() if ts else "",
            "age_seconds": round(age_s, 1) if age_s is not None else None,
            "stale": ts is None or age_s is None or age_s > limit_s,
            "limit_seconds": limit_s,
        }

    def _bar_price_quality(self, order: Order, ctx: dict) -> dict:
        bar = ctx.get("bar")
        if not bar or getattr(bar, "symbol", "").upper() != order.symbol.upper():
            return {"price": 0.0}
        try:
            price = float(getattr(bar, "close", 0.0) or 0.0)
        except (TypeError, ValueError):
            price = 0.0
        return {
            "price": price,
            "source": f"bar:{getattr(bar, 'source', 'market')}",
            "updated_at": getattr(bar, "timestamp", datetime.now(timezone.utc)).isoformat(),
            "age_seconds": 0,
            "stale": False,
            "limit_seconds": self._freshness_limit_seconds(order.symbol),
        }

    @staticmethod
    def _order_increases_risk(order: Order, accountant) -> bool:
        """Return True when the order adds exposure instead of reducing it."""
        existing_qty = 0.0
        if accountant:
            try:
                pos = accountant.current_positions.get(order.symbol)
                if pos is not None:
                    existing_qty = float(getattr(pos, "qty", 0.0) or 0.0)
            except Exception:
                existing_qty = 0.0

        side = order.side.value.upper()
        qty = abs(float(order.quantity or 0.0))

        if existing_qty > 0:
            if side == "BUY":
                return True
            if side == "SELL":
                return qty > abs(existing_qty)
        if existing_qty < 0:
            if side == "SELL":
                return True
            if side == "BUY":
                return qty > abs(existing_qty)
        return True

    def _execution_cooldown_allows_order(self, order: Order, accountant) -> tuple[bool, str]:
        """Block new risk after repeated recent execution failures."""
        feedback = self._ns.get("execution_feedback") or []
        if not isinstance(feedback, list):
            feedback = []

        now = datetime.now(timezone.utc)
        window_start = now - timedelta(minutes=30)
        recent: list[dict] = []
        symbol_recent: list[dict] = []
        order_aliases = self._order_symbol_aliases(order.symbol)

        for item in feedback:
            if not isinstance(item, dict):
                continue
            ts = self._parse_timestamp(item.get("timestamp"))
            if ts is not None and ts < window_start:
                continue
            recent.append(item)
            item_aliases = self._order_symbol_aliases(str(item.get("symbol") or ""))
            if order_aliases & item_aliases:
                symbol_recent.append(item)

        active = len(recent) >= 3 or len(symbol_recent) >= 2
        reason = ""
        if len(symbol_recent) >= 2:
            reason = (
                f"{order.symbol} has {len(symbol_recent)} broker/execution rejection(s) "
                "in the last 30 minutes"
            )
        elif len(recent) >= 3:
            reason = (
                f"{self._pod_id} has {len(recent)} broker/execution rejection(s) "
                "in the last 30 minutes"
            )

        self._ns.set("execution_cooldown", {
            "active": active,
            "mode": "reduce_only" if active else "normal",
            "symbol": order.symbol,
            "pod_rejections_30m": len(recent),
            "symbol_rejections_30m": len(symbol_recent),
            "reason": reason,
            "updated_at": now.isoformat(),
        })

        if active and self._order_increases_risk(order, accountant):
            return False, reason + ". New risk is paused until the broker issue is fixed or the cooldown clears."
        return True, ""

    @staticmethod
    def _order_symbol_aliases(symbol: str) -> set[str]:
        raw = str(symbol or "").upper()
        return {
            raw,
            raw.replace("/", ""),
            raw.replace("/", "-"),
        }

    def _broker_guard_allows_order(self, order: Order, accountant) -> tuple[bool, str]:
        """Block trades when reconciliation says local/broker state is unsafe."""
        guard = self._ns.get("broker_trade_guard") or {}
        if not isinstance(guard, dict):
            return True, ""

        if guard.get("status") == "OK":
            return True, ""

        aliases = self._order_symbol_aliases(order.symbol)
        symbol_blocks = guard.get("blocked_symbols") or {}
        matching_block = None
        if isinstance(symbol_blocks, dict):
            for symbol, block in symbol_blocks.items():
                block_aliases = self._order_symbol_aliases(symbol)
                if aliases & block_aliases:
                    matching_block = block if isinstance(block, dict) else {"reason": str(block)}
                    break

        if matching_block:
            reason = str(matching_block.get("reason") or "Broker reconciliation has not cleared this symbol")
            if matching_block.get("block_all_orders"):
                return False, reason
            if self._order_increases_risk(order, accountant):
                return False, reason + ". New risk is blocked until broker/local state reconciles."
            return True, ""

        if guard.get("global_block_new_risk") and self._order_increases_risk(order, accountant):
            reason = str(
                guard.get("global_reason")
                or "Broker reconciliation is unavailable or incomplete"
            )
            return False, reason + ". New risk is blocked; reductions remain allowed."

        return True, ""

    def _loss_review_allows_order(self, order: Order, accountant) -> tuple[bool, str]:
        restriction = self._ns.get("loss_review_restriction") or {}
        if not restriction:
            return True, ""
        blocks_new_risk = bool(restriction.get("block_new_risk")) or restriction.get("mode") == "reduce_only"
        if not blocks_new_risk:
            return True, ""
        if not self._order_increases_risk(order, accountant):
            return True, ""
        reason = restriction.get("reason") or "Pod is in reduce-only loss-review mode"
        return False, f"{reason}. New risk-increasing orders are blocked; reductions remain allowed."

    def _evidence_guard_allows_order(
        self,
        *,
        order: Order,
        accountant,
        trade_reasoning: str,
        thesis_review: dict | None,
    ) -> tuple[bool, str]:
        """Enforce evidence/thesis review controls on risk-increasing orders."""
        guard = self._ns.get("evidence_trade_guard") or {}
        if not isinstance(guard, dict):
            return True, ""

        blocked_symbols = guard.get("blocked_symbols") or {}
        if not isinstance(blocked_symbols, dict) or not blocked_symbols:
            return True, ""

        aliases = self._order_symbol_aliases(order.symbol)
        matching_block = None
        for symbol, block in blocked_symbols.items():
            if aliases & self._order_symbol_aliases(symbol):
                matching_block = block if isinstance(block, dict) else {"reason": str(block)}
                break
        if not matching_block:
            return True, ""

        if matching_block.get("block_all_orders"):
            return False, str(matching_block.get("reason") or "Evidence review guard blocked this symbol")

        if not self._order_increases_risk(order, accountant):
            return True, ""

        status = str(matching_block.get("status") or "REVIEW").upper()
        reason = str(matching_block.get("reason") or "Evidence/thesis review is required")

        if status == "URGENT" or matching_block.get("mode") == "reduce_only":
            return (
                False,
                reason + ". Symbol is reduce-only until evidence/thesis review clears; reductions remain allowed.",
            )

        if status == "REVIEW" or matching_block.get("requires_thesis_refresh"):
            fresh_ok, fresh_reason = expansion_thesis_is_fresh(trade_reasoning, thesis_review)
            if fresh_ok and matching_block.get("allow_add_after_refresh"):
                refresh = {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "pod_id": self._pod_id,
                    "symbol": order.symbol,
                    "status": "REFRESHED",
                    "reason": "PM supplied a fresh expansion thesis against the evidence review guard.",
                    "guard_reason": reason,
                }
                history = list(self._ns.get("evidence_refresh_history") or [])
                history.insert(0, refresh)
                self._ns.set("evidence_refresh_history", history[:50])
                self._ns.set("last_evidence_refresh", refresh)
                return True, ""
            return (
                False,
                reason
                + ". Add/scale-up is blocked until the PM supplies a fresh expansion thesis "
                + "that revalidates the idea against current regime/news/evidence."
                + (f" {fresh_reason}" if fresh_reason else ""),
            )

        return True, ""

    @staticmethod
    def _reasoning_has_tradeable_sections(reasoning: str) -> tuple[int, list[str]]:
        text = str(reasoning or "").lower()
        labels = {
            "thesis": ("thesis:", "thesis -", "long thesis", "short thesis"),
            "entry": ("entry:", "entry condition", "entry trigger", "buy on", "sell on"),
            "invalidation": ("invalidation:", "invalidated", "invalidates", "exit if", "wrong if"),
            "risk": ("risk:", "risk is", "risk:", "downside", "stop"),
        }
        missing = []
        hits = 0
        for name, needles in labels.items():
            if any(n in text for n in needles):
                hits += 1
            else:
                missing.append(name)
        return hits, missing

    @staticmethod
    def _reasoning_evidence_warnings(reasoning: str) -> list[str]:
        """Return non-blocking evidence-quality warnings for a proposed entry thesis."""
        text = str(reasoning or "").lower()
        warnings: list[str] = []

        evidence_groups = {
            "facts": ("facts:", "verified facts:", "data facts:"),
            "assumptions": ("assumptions:", "unproven assumptions:"),
            "valuation/evidence": ("valuation/evidence:", "valuation:", "evidence:", "relative value:"),
            "why now": ("why now:", "why-now:", "timing:", "catalyst window:"),
            "timeframe": ("timeframe:", "holding period:", "hold period:", "max_hold_days"),
        }
        evidence_hits = sum(1 for needles in evidence_groups.values() if any(n in text for n in needles))
        if evidence_hits < 2:
            warnings.append(
                "Entry thesis should separate facts from assumptions and include why-now/timeframe evidence."
            )

        valuation_terms = (
            "undervalued",
            "overvalued",
            "cheap",
            "expensive",
            "discount",
            "mispriced",
            "underpriced",
            "relative value",
        )
        valuation_evidence = (
            "valuation",
            "multiple",
            "p/e",
            "earnings",
            "revenue",
            "rate differential",
            "carry",
            "real yield",
            "tvl",
            "fdv",
            "market cap",
            "protocol fees",
            "fee revenue",
            "stablecoin",
            "dex volume",
            "active address",
            "funding",
            "open interest",
            "inventory",
            "supply",
            "demand",
        )
        if any(t in text for t in valuation_terms) and not any(t in text for t in valuation_evidence):
            warnings.append(
                "Valuation or relative-value claim needs a supporting metric or should be framed as an assumption."
            )

        eth_fee_claim = (
            ("ethereum" in text or " eth" in text or "eth/" in text)
            and ("gas fee" in text or "gas fees" in text or "ethereum fee" in text)
            and any(t in text for t in ("high", "elevated", "expensive", "push", "leaving", "migrat"))
        )
        if eth_fee_claim and not any(t in text for t in ("gwei", "base fee", "fee data", "gas data")):
            warnings.append(
                "Ethereum gas-fee migration claim needs current gas-fee evidence or should be framed as an assumption."
            )

        return warnings

    def _pre_trade_quality_gate(
        self,
        *,
        order: Order,
        matching_trade: dict,
        pm_decision: dict,
        thesis_gate_result: dict,
        trade_reasoning: str,
    ) -> dict:
        """Graduated trade-quality gate.

        This is intentionally not a binary "perfect thesis or no trade" rule.
        It blocks only missing/critical cases and records warnings for decisions
        that should be improved but are still tradeable.
        """
        side = order.side.value.upper()
        score = float(thesis_gate_result.get("quality_score", 1.0) or 0.0)
        passed = bool(thesis_gate_result.get("passed", True))
        issues: list[str] = []
        warnings: list[str] = []
        reasoning = str(trade_reasoning or matching_trade.get("reasoning") or pm_decision.get("reasoning") or "").strip()
        thesis_fields = (
            matching_trade.get("thesis_fields")
            if isinstance(matching_trade.get("thesis_fields"), dict)
            else pm_decision.get("thesis_fields")
            if isinstance(pm_decision.get("thesis_fields"), dict)
            else {}
        )

        if side != "BUY":
            action = "pass"
            reason = "Risk-reducing or exit trade; quality gate records context but does not block sells."
        else:
            if not reasoning:
                issues.append("No entry thesis or PM reasoning was captured for the proposed BUY.")
            elif len(reasoning) < 80:
                warnings.append("Entry reasoning is brief; trade allowed but PM should provide more detail next cycle.")

            section_hits, missing_sections = self._reasoning_has_tradeable_sections(reasoning)
            if section_hits < 2:
                warnings.append(
                    "Reasoning lacks several tradeable sections: "
                    + ", ".join(missing_sections)
                    + "."
                )
            warnings.extend(self._reasoning_evidence_warnings(reasoning))
            required_thesis_fields = [
                "current_price",
                "facts_checked",
                "assumptions",
                "why_now",
                "timeframe",
                "invalidation",
                "stop_take_profit_logic",
            ]
            missing_structured = [
                field for field in required_thesis_fields
                if not thesis_fields.get(field)
            ]
            if missing_structured:
                warnings.append(
                    "Structured thesis fields missing: "
                    + ", ".join(missing_structured)
                    + "."
                )
            catalyst_ids = matching_trade.get("catalyst_ids") or pm_decision.get("catalyst_ids") or []
            catalyst_reasoning = matching_trade.get("catalyst_reasoning") or pm_decision.get("catalyst_reasoning") or ""
            if not catalyst_ids and not catalyst_reasoning:
                warnings.append("BUY thesis should link to a catalyst or explicitly say why it is not catalyst-driven.")

            conviction = float(getattr(order, "conviction", 0.5) or 0.0)
            if conviction == 0.5:
                warnings.append("Conviction is still the neutral default 0.50.")
            elif conviction < 0.15:
                issues.append(f"Conviction is too low for a new BUY ({conviction:.2f}).")

            if not passed:
                feedback = str(thesis_gate_result.get("feedback") or "").strip()
                if score < 0.35:
                    issues.append(
                        "Thesis verifier score is critically low "
                        f"({score:.2f}). {feedback}".strip()
                    )
                else:
                    warnings.append(
                        "Thesis verifier requested improvement "
                        f"(score={score:.2f}). {feedback}".strip()
                    )

            if issues:
                action = "block"
                reason = " ".join(issues)
            elif warnings:
                action = "warn"
                reason = " ".join(warnings)
            else:
                action = "pass"
                reason = "Pre-trade quality checks passed."

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "pod_id": self._pod_id,
            "symbol": order.symbol,
            "side": side,
            "action": action,
            "status": action.upper(),
            "quality_score": round(score, 3),
            "thesis_passed": passed,
            "reason": reason,
            "issues": issues,
            "warnings": warnings,
            "thesis_fields": thesis_fields,
            "llm": (pm_decision or {}).get("llm", {}),
        }

    def _record_quality_gate_result(self, gate: dict) -> None:
        self._ns.set("last_quality_gate", gate)
        results = list(self._ns.get("quality_gate_history") or [])
        results.insert(0, dict(gate))
        self._ns.set("quality_gate_history", results[:50])

    def _pre_trade_data_quality(self, order: Order, accountant, ctx: dict) -> dict:
        """Block new risk-increasing trades when market data is missing or stale."""
        result = {
            "passed": True,
            "pod_id": self._pod_id,
            "symbol": order.symbol,
            "side": order.side.value.upper(),
            "order_type": order.order_type.value,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "price": None,
            "price_source": "",
            "price_updated_at": "",
            "price_age_seconds": None,
            "issues": [],
        }

        if order.side.value.upper() != "BUY":
            return result

        issues: list[str] = []
        existing_position = accountant.current_positions.get(order.symbol) if accountant else None
        if existing_position is not None:
            price = float(getattr(existing_position, "current_price", 0.0) or 0.0)
            result["price"] = price
            result["price_source"] = getattr(existing_position, "price_source", "") or ""
            result["price_updated_at"] = getattr(existing_position, "price_updated_at", "") or ""
            ts = self._parse_timestamp(result["price_updated_at"])
            if ts:
                result["price_age_seconds"] = round((datetime.now(timezone.utc) - ts).total_seconds(), 1)
            if price <= 0:
                issues.append("Existing position has no positive current price")
            if not result["price_source"]:
                issues.append("Existing position has no price source")
            if not result["price_updated_at"]:
                issues.append("Existing position has no price timestamp")
            if bool(getattr(existing_position, "price_stale", False)):
                issues.append("Existing position price is stale")
        else:
            price_info = self._namespace_price_quality(order.symbol)
            if price_info.get("price", 0.0) <= 0:
                price_info = self._bar_price_quality(order, ctx)

            price = float(price_info.get("price") or 0.0)
            result["price"] = price
            result["price_source"] = price_info.get("source", "")
            result["price_updated_at"] = price_info.get("updated_at", "")
            result["price_age_seconds"] = price_info.get("age_seconds")
            if price <= 0:
                issues.append("No positive live price available for proposed BUY")
            if not result["price_updated_at"]:
                issues.append("No price freshness timestamp for proposed BUY")
            if bool(price_info.get("stale", False)):
                issues.append(
                    f"Proposed BUY price is stale or unverified "
                    f"(limit {price_info.get('limit_seconds', self._freshness_limit_seconds(order.symbol))}s)"
                )

        result["issues"] = issues
        result["passed"] = not issues
        return result

    def _build_trade_evidence_packet(
        self,
        *,
        order: Order,
        matching_trade: dict,
        pm_decision: dict,
        ctx: dict,
        accountant,
        trade_reasoning: str,
        thesis_gate_result: dict,
        quality_gate: dict,
        data_quality: dict,
        thesis_review: dict,
        entry_macro_regime: str,
    ) -> dict:
        """Build a compact audit packet for the decision that led to a fill."""
        features = ctx.get("features") or {}
        regime = features.get("regime") if isinstance(features.get("regime"), dict) else {}
        current_pos = None
        try:
            current_pos = accountant.current_positions.get(order.symbol) if accountant else None
        except Exception:
            current_pos = None

        sizing_context = ctx.get("sizing_context") or self._ns.get("sizing_context") or {}
        broker_guard = self._ns.get("broker_trade_guard") or {}
        loss_review = self._ns.get("loss_review_restriction") or {}
        execution_cooldown = self._ns.get("execution_cooldown") or {}
        evidence_guard = self._ns.get("evidence_trade_guard") or {}
        committee_reviews = self._ns.get("committee_reviews_by_symbol") or {}
        committee_review = {}
        if isinstance(committee_reviews, dict):
            committee_review = committee_reviews.get(order.symbol.upper()) or {}
        portfolio_reviews = self._ns.get("portfolio_construction_reviews_by_symbol") or {}
        portfolio_construction_review = {}
        if isinstance(portfolio_reviews, dict):
            portfolio_construction_review = portfolio_reviews.get(order.symbol.upper()) or {}
        catalyst_ids = (
            matching_trade.get("catalyst_ids")
            or pm_decision.get("catalyst_ids")
            or []
        )
        catalyst_ids = [str(x) for x in catalyst_ids] if isinstance(catalyst_ids, list) else []
        available_catalysts = (
            ctx.get("foresight_events")
            or (features.get("foresight_events") if isinstance(features, dict) else [])
            or pm_decision.get("foresight_events")
            or []
        )
        catalyst_refs = []
        for event in (available_catalysts if isinstance(available_catalysts, list) else []):
            if not isinstance(event, dict):
                continue
            if catalyst_ids and event.get("event_id") not in catalyst_ids:
                continue
            catalyst_refs.append({
                "event_id": event.get("event_id"),
                "title": event.get("title"),
                "summary": event.get("summary"),
                "direction": event.get("direction"),
                "impact_score": event.get("impact_score"),
                "confidence": event.get("confidence"),
                "source_refs": event.get("source_refs", []),
            })
            if len(catalyst_refs) >= 6:
                break
        evidence_blocks = evidence_guard.get("blocked_symbols", {}) if isinstance(evidence_guard, dict) else {}
        evidence_block = None
        for _symbol, _block in (evidence_blocks.items() if isinstance(evidence_blocks, dict) else []):
            if self._order_symbol_aliases(order.symbol) & self._order_symbol_aliases(_symbol):
                evidence_block = _block if isinstance(_block, dict) else {"reason": str(_block)}
                break

        checks = [
            {
                "name": "thesis_verifier",
                "status": "PASS" if thesis_gate_result.get("passed", True) else "WARN",
                "score": thesis_gate_result.get("quality_score"),
                "detail": thesis_gate_result.get("feedback", ""),
            },
            {
                "name": "pre_trade_quality",
                "status": str(quality_gate.get("status") or quality_gate.get("action") or "PASS").upper(),
                "score": quality_gate.get("quality_score"),
                "detail": quality_gate.get("reason", ""),
                "warnings": list(quality_gate.get("warnings") or []),
                "issues": list(quality_gate.get("issues") or []),
            },
            {
                "name": "market_data",
                "status": "PASS" if data_quality.get("passed", False) else "BLOCK",
                "detail": "; ".join(data_quality.get("issues") or []) or "Market data freshness check passed.",
                "price": data_quality.get("price"),
                "source": data_quality.get("price_source", ""),
                "price_age_seconds": data_quality.get("price_age_seconds"),
            },
            {
                "name": "thesis_lifecycle",
                "status": str(thesis_review.get("status") or "valid").upper(),
                "score": thesis_review.get("score"),
                "detail": "; ".join(thesis_review.get("issues") or []) or "Open thesis lifecycle check recorded.",
                "block_adds": bool(thesis_review.get("block_adds", False)),
            },
            {
                "name": "broker_reconciliation",
                "status": str(broker_guard.get("status") or "NOT_CHECKED").upper(),
                "detail": broker_guard.get("global_reason") or broker_guard.get("reason", ""),
            },
            {
                "name": "loss_review",
                "status": "REDUCE_ONLY" if loss_review.get("block_new_risk") or loss_review.get("mode") == "reduce_only" else "PASS",
                "detail": loss_review.get("reason", ""),
            },
            {
                "name": "execution_cooldown",
                "status": "ACTIVE" if execution_cooldown.get("active") else "PASS",
                "detail": execution_cooldown.get("reason", ""),
            },
            {
                "name": "evidence_review",
                "status": str((evidence_block or {}).get("status") or evidence_guard.get("status") or "OK").upper(),
                "detail": (evidence_block or {}).get("reason", ""),
                "requires_thesis_refresh": bool((evidence_block or {}).get("requires_thesis_refresh", False)),
            },
            {
                "name": "committee_review",
                "status": str(committee_review.get("decision") or "NOT_REQUIRED").upper(),
                "detail": committee_review.get("reason", ""),
                "confidence": committee_review.get("confidence"),
            },
            {
                "name": "portfolio_construction",
                "status": str(portfolio_construction_review.get("action") or "NOT_RUN").upper(),
                "detail": portfolio_construction_review.get("reason", ""),
                "confidence": portfolio_construction_review.get("confidence"),
            },
        ]

        missing_evidence: list[str] = []
        missing_evidence.extend(str(x) for x in quality_gate.get("warnings") or [])
        missing_evidence.extend(str(x) for x in quality_gate.get("issues") or [])
        missing_evidence.extend(str(x) for x in data_quality.get("issues") or [])
        if not thesis_gate_result.get("passed", True) and thesis_gate_result.get("feedback"):
            missing_evidence.append(str(thesis_gate_result.get("feedback")))
        missing_evidence.extend(str(x) for x in thesis_review.get("issues") or [])

        packet = {
            "version": 1,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "pod_id": self._pod_id,
            "symbol": order.symbol,
            "trade": {
                "side": order.side.value.upper(),
                "qty": order.quantity,
                "conviction": order.conviction,
                "strategy_tag": order.strategy_tag,
                "entry_thesis": trade_reasoning,
                "stop_loss_pct": matching_trade.get("stop_loss_pct"),
                "take_profit_pct": matching_trade.get("take_profit_pct"),
                "take_profit_levels": matching_trade.get("take_profit_levels", []),
                "exit_when": matching_trade.get("exit_when", ""),
                "max_hold_days": matching_trade.get("max_hold_days", 0),
            },
            "market_context": {
                "price": data_quality.get("price"),
                "price_source": data_quality.get("price_source", ""),
                "price_updated_at": data_quality.get("price_updated_at", ""),
                "price_age_seconds": data_quality.get("price_age_seconds"),
                "macro_regime": entry_macro_regime or regime.get("label") or regime.get("regime", ""),
                "macro_outlook": (
                    features.get("macro_outlook")
                    or features.get("liquidity_outlook")
                    or features.get("outlook")
                    or ""
                ),
                "macro_score": features.get("macro_score") or regime.get("macro_score"),
                "fred": self._compact_metric_dict(features.get("fred_indicators") or {}, 12),
            },
            "position_context": {
                "existing_qty": getattr(current_pos, "qty", 0.0) if current_pos is not None else 0.0,
                "existing_notional": getattr(current_pos, "notional", 0.0) if current_pos is not None else 0.0,
                "nav": sizing_context.get("nav"),
                "cash": sizing_context.get("cash"),
                "invested": sizing_context.get("invested"),
            },
            "evidence": {
                "pm_action_summary": pm_decision.get("action_summary", ""),
                "pm_llm": pm_decision.get("llm", {}),
                "signal_snapshot": pm_decision.get("signal_snapshot", {}),
                "top_news": self._compact_evidence_items(features.get("news_headlines") or [], 5),
                "top_prediction_markets": self._compact_evidence_items(features.get("polymarket_predictions") or [], 5),
                "catalyst_ids": catalyst_ids,
                "catalyst_reasoning": matching_trade.get("catalyst_reasoning") or pm_decision.get("catalyst_reasoning", ""),
                "catalysts": catalyst_refs,
                "specialist_briefs": ctx.get("specialist_briefs") or features.get("specialist_briefs") or self._ns.get("specialist_briefs") or [],
                "committee_review": committee_review,
                "portfolio_construction_review": portfolio_construction_review,
                "thesis_fields": matching_trade.get("thesis_fields") or pm_decision.get("thesis_fields") or {},
            },
            "checks": checks,
            "missing_evidence": missing_evidence[:12],
            "review_triggers": list(thesis_review.get("monitors") or []),
            "invalidation": matching_trade.get("exit_when", "") or "; ".join(thesis_review.get("issues") or []),
        }
        return self._json_safe(packet)

    @staticmethod
    def _compact_metric_dict(values: dict, limit: int = 10) -> dict:
        if not isinstance(values, dict):
            return {}
        out = {}
        for key, value in list(values.items())[:limit]:
            if isinstance(value, (int, float, str, bool)) or value is None:
                out[str(key)] = value
            elif isinstance(value, dict):
                out[str(key)] = {
                    str(k): v for k, v in list(value.items())[:4]
                    if isinstance(v, (int, float, str, bool)) or v is None
                }
        return out

    @staticmethod
    def _compact_evidence_items(items, limit: int = 5) -> list:
        if not isinstance(items, list):
            return []
        out = []
        for item in items[:limit]:
            if isinstance(item, str):
                out.append({"text": item[:280]})
            elif isinstance(item, dict):
                out.append({
                    "title": str(item.get("title") or item.get("headline") or item.get("question") or item.get("market") or "")[:220],
                    "source": str(item.get("source") or item.get("url") or "")[:160],
                    "sentiment": item.get("sentiment"),
                    "relevancy": item.get("relevancy"),
                    "impact": item.get("impact"),
                    "probability": item.get("probability") or item.get("implied_prob"),
                })
        return out

    @staticmethod
    def _json_safe(value):
        try:
            return json.loads(json.dumps(value, default=str))
        except Exception:
            return {}

    def _record_data_quality_failure(self, failure: dict) -> None:
        failures = list(self._ns.get("data_quality_failures") or [])
        failures.insert(0, dict(failure))
        self._ns.set("data_quality_failures", failures[:50])

    def _record_trade_block(self, stage: str, order: Order, reason: str) -> None:
        """Record the latest runtime gate that stopped a proposed trade."""
        block = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "pod_id": self._pod_id,
            "symbol": order.symbol,
            "side": order.side.value.upper(),
            "qty": order.quantity,
            "stage": stage,
            "status": "BLOCKED",
            "reason": str(reason or "Trade blocked"),
            "local_order_id": str(order.id),
        }
        self._ns.set("last_trade_block", block)
        blocks = list(self._ns.get("trade_blocks") or [])
        blocks.insert(0, block)
        self._ns.set("trade_blocks", blocks[:50])
        managed = self._managed_runtime()
        if managed:
            try:
                for snapshot_id in self._ns.get("last_decision_snapshot_ids") or []:
                    snap = managed.decisions.get_snapshot(str(snapshot_id))
                    if not snap:
                        continue
                    if str(snap.get("symbol") or "").upper() != order.symbol.upper():
                        continue
                    if str(snap.get("side") or "").upper() != order.side.value.upper():
                        continue
                    managed.decisions.update_snapshot_status(
                        str(snapshot_id),
                        f"blocked:{stage}",
                        {"stage": stage, "reason": str(reason or "")[:1000]},
                    )
            except Exception as exc:
                logger.debug("[%s] decision snapshot block update failed: %s", self._pod_id, exc)

    def _update_decision_snapshot_order_status(self, order: Order, order_update: dict) -> None:
        managed = self._managed_runtime()
        if not managed or not isinstance(order_update, dict):
            return
        raw_status = str(order_update.get("status") or order_update.get("order_status") or "").upper()
        if not raw_status:
            raw_status = "SUBMITTED"
        status = raw_status.lower()
        if "REJECT" in raw_status:
            status = "rejected"
        elif "FILL" in raw_status:
            status = "filled"
        elif "PEND" in raw_status:
            status = "pending"
        try:
            for snapshot_id in self._ns.get("last_decision_snapshot_ids") or []:
                snap = managed.decisions.get_snapshot(str(snapshot_id))
                if not snap:
                    continue
                if str(snap.get("symbol") or "").upper() != order.symbol.upper():
                    continue
                if str(snap.get("side") or "").upper() != order.side.value.upper():
                    continue
                managed.decisions.update_snapshot_status(
                    str(snapshot_id),
                    status,
                    {
                        "order_update": {
                            k: v for k, v in order_update.items()
                            if k not in {"raw_request", "raw_response", "prompt", "api_key"}
                        }
                    },
                )
        except Exception as exc:
            logger.debug("[%s] decision snapshot execution update failed: %s", self._pod_id, exc)

    def _log_pm_reasoning(self, pm_decision: dict) -> None:
        """Log PM reasoning for all held positions after each PM decision cycle."""
        accountant = self._ns.get("accountant")
        if not accountant:
            return

        held_symbols = {
            sym for sym, pos in accountant._positions.items()
            if pos.get("quantity", 0) != 0
        }
        if not held_symbols:
            return

        now_str = datetime.now().isoformat()
        pm_trades = pm_decision.get("trades", [])
        traded_symbols: dict[str, dict] = {}
        for t in pm_trades:
            if isinstance(t, dict) and t.get("symbol"):
                traded_symbols[t["symbol"]] = t

        for sym in held_symbols:
            if sym in traded_symbols:
                t = traded_symbols[sym]
                action = (t.get("action") or "TRADE").upper()
                reasoning = t.get("reasoning", "")[:300]
                conviction = t.get("conviction", 0.0)
            else:
                action = "HOLD"
                summary = pm_decision.get("action_summary", "")
                reasoning = f"No action taken. PM summary: {summary[:200]}" if summary else "Position maintained — no action from PM this iteration"
                conviction = 0.0
            accountant.append_reasoning(sym, now_str, action, reasoning, conviction)

    async def _run_risk_loop_with_exits(self, order: Order) -> tuple[Order | None, list[Order]]:
        """Run the risk loop and collect any exit orders. Returns (approved_order, exit_orders)."""
        current_order = order
        all_exit_orders: list[Order] = []
        original_qty = order.quantity
        for i in range(5):
            risk_out = await self._risk.run_cycle({"order": current_order})  # type: ignore[union-attr]
            exit_orders = risk_out.get("exit_orders", [])
            if exit_orders and i == 0:
                all_exit_orders.extend(exit_orders)
            token: RiskApprovalToken | None = risk_out.get("token")
            if token is not None and token.is_valid():
                self._ns.set("last_risk_token", token)
                return current_order, all_exit_orders

            revised: Order | None = risk_out.get("revised_order")
            reason: str = risk_out.get("reason", "")
            if revised is None:
                self._ns.set("last_risk_rejection_reason", reason or "Risk rejected order")
                logger.info("[%s] Risk rejected %s %s: %s", self._pod_id, order.side.value, order.symbol, reason)
                return None, all_exit_orders

            if revised.quantity >= current_order.quantity:
                logger.info("[%s] Risk revision converged for %s (qty unchanged at %.4f) — approving",
                            self._pod_id, order.symbol, revised.quantity)
                token = RiskApprovalToken(order_id=revised.id, pod_id=self._pod_id, expires_ms=500)
                self._ns.set("last_risk_token", token)
                return revised, all_exit_orders

            pm_accept = await self._pm.run_cycle(  # type: ignore[union-attr]
                {
                    "order": revised,
                    "risk_revision": True,
                    "risk_reason": reason,
                    "original_qty": original_qty,
                }
            )
            accepted_order = pm_accept.get("order")
            if accepted_order is None:
                self._ns.set("last_risk_rejection_reason", reason or "PM declined risk revision")
                logger.info("[%s] PM declined Risk revision for %s", self._pod_id, order.symbol)
                return None, all_exit_orders
            current_order = accepted_order

        return None, all_exit_orders

    async def _run_risk_loop(self, order: Order) -> Order | None:
        """PM proposes, Risk validates. Up to 5 iterations to reach agreement."""
        current_order = order
        original_qty = order.quantity
        for i in range(5):
            risk_out = await self._risk.run_cycle({"order": current_order})  # type: ignore[union-attr]
            token: RiskApprovalToken | None = risk_out.get("token")
            if token is not None and token.is_valid():
                self._ns.set("last_risk_token", token)
                return current_order

            revised: Order | None = risk_out.get("revised_order")
            reason: str = risk_out.get("reason", "")
            if revised is None:
                self._ns.set("last_risk_rejection_reason", reason or "Risk rejected order")
                logger.info("[%s] Risk rejected %s %s: %s", self._pod_id, order.side.value, order.symbol, reason)
                return None

            # If Risk "revised" to the same or larger qty, it already meets limits — approve it
            if revised.quantity >= current_order.quantity:
                logger.info("[%s] Risk revision converged for %s (qty unchanged at %.4f) — approving",
                            self._pod_id, order.symbol, revised.quantity)
                token = RiskApprovalToken(order_id=revised.id, pod_id=self._pod_id, expires_ms=500)
                self._ns.set("last_risk_token", token)
                return revised

            pm_accept = await self._pm.run_cycle(  # type: ignore[union-attr]
                {
                    "order": revised,
                    "risk_revision": True,
                    "risk_reason": reason,
                    "original_qty": original_qty,
                }
            )
            accepted_order = pm_accept.get("order")
            if accepted_order is None:
                self._ns.set("last_risk_rejection_reason", reason or "PM declined risk revision")
                logger.info("[%s] PM declined Risk revision for %s", self._pod_id, order.symbol)
                return None
            current_order = accepted_order

        return None

    async def execute_review_orders(self, orders: list[Order]) -> list[dict]:
        """Execute orders from the daily position review through the standard risk loop.

        Each order goes through Risk validation and, if approved, the Execution Trader.
        Returns a list of result dicts with status per order.
        """
        results = []
        for order in orders:
            approved = await self._run_risk_loop(order)
            if approved is None:
                results.append({"symbol": order.symbol, "side": order.side.value,
                                "qty": order.quantity, "status": "REJECTED_BY_RISK"})
                continue

            review_thesis = (
                f"Position review order: {approved.side.value.upper()} {approved.symbol} "
                f"from daily CIO/PM review."
            )
            self._ns.set("pm_trade_metadata", {
                "entry_thesis": review_thesis,
                "reasoning": review_thesis,
                "conviction": approved.conviction,
                "strategy_tag": approved.strategy_tag,
                "signal_snapshot": {},
                "stop_loss_pct": None,
                "take_profit_pct": None,
                "exit_when": "",
                "max_hold_days": 0,
            })

            ctx = {
                "approved_order": approved,
                "mandate": self._ns.get("governance_mandate"),
                "risk_halt": self._ns.get("governance_risk_halt", False),
                "risk_halt_reason": self._ns.get("governance_risk_halt_reason"),
                "drawdown_halt": self._ns.get("drawdown_halt", False),
                "drawdown_sizing_mult": float(self._ns.get("drawdown_sizing_mult", 1.0)),
            }
            try:
                await self._exec_trader.run_cycle(ctx)
                results.append({"symbol": order.symbol, "side": order.side.value,
                                "qty": order.quantity, "status": "EXECUTED"})
            except Exception as e:
                logger.warning("[%s] Review order execution failed for %s: %s",
                               self._pod_id, order.symbol, e)
                results.append({"symbol": order.symbol, "side": order.side.value,
                                "qty": order.quantity, "status": f"EXEC_ERROR: {e}"})
        return results

    def _entry_thesis_for_order(self, order: Order, matching_trade: dict, last_pm: dict) -> str:
        """Extract a non-empty per-order PM thesis for position metadata."""
        candidates = [
            matching_trade.get("entry_thesis") if isinstance(matching_trade, dict) else "",
            matching_trade.get("thesis") if isinstance(matching_trade, dict) else "",
            matching_trade.get("reasoning") if isinstance(matching_trade, dict) else "",
        ]

        last_reasoning = last_pm.get("reasoning", "") if isinstance(last_pm, dict) else ""
        parsed_reasoning = self._reasoning_from_pm_payload(order.symbol, last_reasoning)
        if parsed_reasoning:
            candidates.append(parsed_reasoning)
        else:
            raw_text = str(last_reasoning or "").strip()
            if raw_text and not (
                raw_text.startswith("{")
                or raw_text.startswith("[")
                or raw_text.startswith("```")
            ):
                candidates.append(raw_text)

        for candidate in candidates:
            text = str(candidate or "").strip()
            if text:
                return text

        action_summary = str(last_pm.get("action_summary", "") if isinstance(last_pm, dict) else "").strip()
        if action_summary:
            return f"{order.side.value.upper()} {order.symbol}: {action_summary}"
        return (
            f"{order.side.value.upper()} {order.symbol}: PM decision metadata did not include "
            "a specific thesis; review the PM prompt/response logs for this cycle."
        )

    @staticmethod
    def _reasoning_from_pm_payload(symbol: str, payload: object) -> str:
        """Unwrap a raw PM JSON payload and return the reasoning for symbol, if present."""
        if isinstance(payload, dict):
            trades = payload.get("trades", [])
        elif isinstance(payload, str):
            text = payload.strip()
            if text.startswith("```"):
                text = text.strip("`")
                if text.lower().startswith("json"):
                    text = text[4:].strip()
            if not (text.startswith("{") or text.startswith("[")):
                return ""
            try:
                parsed = json.loads(text)
            except Exception:
                return ""
            trades = parsed.get("trades", []) if isinstance(parsed, dict) else parsed
        else:
            return ""

        if isinstance(trades, dict):
            trades = [trades]
        if not isinstance(trades, list):
            return ""

        for trade in trades:
            if not isinstance(trade, dict):
                continue
            if str(trade.get("symbol", "")).upper() == symbol.upper():
                return str(
                    trade.get("entry_thesis")
                    or trade.get("thesis")
                    or trade.get("reasoning")
                    or ""
                ).strip()
        return ""

    def _review_open_position_theses(self, ctx: dict, accountant) -> dict[str, dict]:
        """Run a lightweight lifecycle review for every open position."""
        if accountant is None:
            self._ns.set("thesis_lifecycle_reviews", {})
            self._ns.set("thesis_lifecycle_text", "")
            return {}

        features = ctx.get("features") or self._ns.get("features") or {}
        reviews: dict[str, dict] = {}
        for symbol, snap in accountant.current_positions.items():
            meta = accountant._entry_metadata.get(symbol, {})
            thesis = snap.entry_thesis or meta.get("entry_thesis") or meta.get("reasoning", "")
            review = review_position_thesis(
                symbol=symbol,
                entry_thesis=thesis,
                entry_metadata=meta,
                position=snap,
                features=features,
                pod_id=self._pod_id,
            )
            reviews[symbol.upper()] = review
            meta["thesis_status"] = review.get("status", "unknown")
            meta["thesis_issues"] = list(review.get("issues", []))
            meta["thesis_review"] = review
            if not meta.get("entry_macro_regime"):
                meta["entry_macro_regime"] = review.get("entry_macro_regime") or current_regime(features)
            accountant._entry_metadata[symbol] = meta

        text = format_thesis_reviews_for_prompt(reviews)
        self._ns.set("thesis_lifecycle_reviews", reviews)
        self._ns.set("thesis_lifecycle_text", text)
        return reviews

    async def get_summary(self) -> PodSummary:
        """Generate PodSummary with real trading data from PortfolioAccountant.

        Returns:
            PodSummary with current NAV, positions, risk metrics, and exposure buckets.
        """
        # Retrieve PortfolioAccountant from pod namespace
        accountant = self._ns.get("accountant")
        if accountant is None:
            # Fallback: return empty summary (pod not fully initialized)
            logger.warning("[%s] PortfolioAccountant not found in namespace", self._pod_id)
            return PodSummary(
                pod_id=self._pod_id,
                timestamp=datetime.now(),
                status=PodStatus.INITIALIZING,
                risk_metrics=PodRiskMetrics(
                    pod_id=self._pod_id,
                    timestamp=datetime.now(),
                    nav=0.0,
                    daily_pnl=0.0,
                    drawdown_from_hwm=0.0,
                    current_vol_ann=0.0,
                    gross_leverage=0.0,
                    net_leverage=0.0,
                    var_95_1d=0.0,
                    es_95_1d=0.0,
                ),
                exposure_buckets=[],
                expected_return_estimate=0.0,
                turnover_daily_pct=0.0,
                heartbeat_ok=True,
                positions=[],
                error_message="PortfolioAccountant not initialized",
            )

        # Build positions list from accountant
        positions: list[PodPosition] = []
        for symbol, snapshot in accountant.current_positions.items():
            positions.append(
                PodPosition(
                    symbol=symbol,
                    qty=snapshot.qty,
                    current_price=snapshot.current_price,
                    unrealized_pnl=snapshot.unrealized_pnl,
                    notional=snapshot.notional,
                    cost_basis=snapshot.cost_basis,
                    entry_date=snapshot.entry_date,
                    entry_thesis=snapshot.entry_thesis,
                    stop_loss_pct=snapshot.stop_loss_pct,
                    take_profit_pct=snapshot.take_profit_pct,
                    max_hold_days=snapshot.max_hold_days,
                    conviction=snapshot.conviction,
                    thesis_status=snapshot.thesis_status,
                    thesis_issues=snapshot.thesis_issues,
                    thesis_review=snapshot.thesis_review,
                    evidence_packet=snapshot.evidence_packet,
                    price_source=snapshot.price_source,
                    price_updated_at=snapshot.price_updated_at,
                    price_stale=snapshot.price_stale,
                )
            )

        # Calculate leverage
        total_notional = sum(abs(p.notional) for p in positions)
        gross_leverage = total_notional / accountant.nav if accountant.nav > 0 else 0.0

        # Calculate net leverage (long notional - short notional) / NAV
        long_notional = sum(p.notional for p in positions if p.notional > 0)
        short_notional = sum(abs(p.notional) for p in positions if p.notional < 0)
        net_leverage = (long_notional - short_notional) / accountant.nav if accountant.nav > 0 else 0.0

        # Calculate volatility and VaR from price history (simplified)
        # For MVP4, use placeholder values; will enhance in future phases
        vol_ann = self._calculate_volatility()
        var_95 = self._calculate_var(accountant.nav)

        # Calculate drawdown from HWM
        drawdown = accountant.drawdown_from_hwm()

        factor_report = {}
        if self._pod_id == "commodities":
            try:
                factor_report = compute_factor_report(
                    accountant.current_positions,
                    accountant.nav,
                    dynamic_profiles=self._ns.get("factor_profiles"),
                    cash=accountant.cash,
                )
                self._ns.set("factor_exposure_report", factor_report)
                self._ns.set("factor_exposure_text", format_factor_report(factor_report))
            except Exception:
                factor_report = self._ns.get("factor_exposure_report") or {}

        # Build exposure buckets
        exposure_buckets = []
        if total_notional > 0 and accountant.nav > 0:
            if self._pod_id == "commodities" and factor_report.get("factors"):
                for factor, row in (factor_report.get("factors") or {}).items():
                    exposure_buckets.append(
                        PodExposureBucket(
                            asset_class=factor,
                            direction="long",
                            notional_pct_nav=float(row.get("pct_nav", 0.0) or 0.0),
                        )
                    )
            else:
                exposure_pct = total_notional / accountant.nav
                exposure_buckets.append(
                    PodExposureBucket(
                        asset_class="US_EQUITIES",
                        direction="long" if long_notional >= 0 else "short",
                        notional_pct_nav=exposure_pct,
                    )
                )

        # Cash and invested breakdown
        invested = total_notional
        cash_value = accountant.nav - invested

        risk_mode = factor_report.get("risk_mode", "normal") if factor_report else "normal"
        evidence_guard = self._ns.get("evidence_trade_guard") or {}
        if isinstance(evidence_guard, dict) and evidence_guard.get("blocked_symbols"):
            risk_mode = "evidence_review"

        # Build risk metrics
        risk_metrics = PodRiskMetrics(
            pod_id=self._pod_id,
            timestamp=datetime.now(),
            nav=accountant.nav,
            daily_pnl=accountant.daily_pnl,
            realized_pnl=accountant.realized_pnl,
            starting_capital=accountant.starting_capital,
            invested=round(invested, 2),
            cash=round(cash_value, 2),
            drawdown_from_hwm=drawdown,
            current_vol_ann=vol_ann,
            gross_leverage=gross_leverage,
            net_leverage=net_leverage,
            var_95_1d=var_95,
            es_95_1d=var_95 * 1.25,  # Expected shortfall approximation
            risk_mode=risk_mode,
            factor_exposures=factor_report,
            factor_breaches=list(factor_report.get("breaches", [])) if factor_report else [],
        )

        # Determine pod status
        status = PodStatus.ACTIVE

        # Regime label from macro_view (set during run_cycle)
        macro_view = self._ns.get("macro_view") or {}
        macro_regime = macro_view.get("regime")  # e.g. "Risk-On", "Neutral", "Risk-Off", "Crisis"

        # Real performance metrics from accountant's daily NAV history
        try:
            performance_metrics = accountant.performance_summary()
        except Exception:
            performance_metrics = {}

        # Trade outcome stats (only populated once trades have closed)
        try:
            trade_outcome_stats = self._outcome_tracker.to_dict() if self._outcome_tracker.total_trades > 0 else {}
        except Exception:
            trade_outcome_stats = {}

        # Create and return summary
        summary = PodSummary(
            pod_id=self._pod_id,
            timestamp=datetime.now(),
            status=status,
            risk_metrics=risk_metrics,
            exposure_buckets=exposure_buckets,
            expected_return_estimate=0.0,  # Placeholder; calculated by PM agent
            turnover_daily_pct=0.0,  # Placeholder; calculated from order history
            heartbeat_ok=True,
            positions=positions,
            error_message=None,
            macro_regime=macro_regime,
            performance_metrics=performance_metrics,
            trade_outcome_stats=trade_outcome_stats,
        )

        logger.debug(
            "[%s] Generated summary: NAV=$%.2f, positions=%d, leverage=%.2fx",
            self._pod_id, accountant.nav, len(positions), gross_leverage
        )

        return summary

    def _calculate_volatility(self) -> float:
        """Calculate annualized volatility from recent NAV history."""
        accountant = self._ns.get("accountant")
        if accountant and hasattr(accountant, "annualized_volatility"):
            return accountant.annualized_volatility()
        return 0.0

    def _calculate_var(self, nav: float) -> float:
        """Calculate 95% Value at Risk estimate.

        For MVP4, returns placeholder based on standard assumptions.
        Enhanced in future phases with actual distribution analysis.
        """
        # Placeholder: assume 2% daily risk at 95% confidence
        return -nav * 0.02
