"""FinanceExecutor — wraps the existing hedge-fund run loop behind the
generic WorkflowExecutor contract so the platform core stays agnostic
of finance specifics.

This module deliberately keeps reaching into the legacy `src/` packages
(`src.utils.progress`) and the existing `app.backend.services.*` helpers
rather than relocating them. Physical moves come in a later phase; today
we only prove the abstraction is shaped right.
"""
from __future__ import annotations

from typing import Any

from app.backend.core.executors import ExecutorContext, ProgressEvent, WorkflowExecutor
from app.backend.models.schemas import HedgeFundRequest
from app.backend.services.graph import (
    create_graph,
    parse_hedge_fund_response,
    run_graph_async,
)
from app.backend.services.portfolio import create_portfolio
from src.utils.progress import progress


class FinanceExecutor(WorkflowExecutor):
    domain = "finance"

    async def run(self, request: dict[str, Any], context: ExecutorContext) -> dict[str, Any]:
        # Re-parse into the typed schema so downstream helpers keep their
        # current signatures. API keys live on the context, not in the
        # incoming payload from the platform route.
        merged = {**request, "api_keys": context.api_keys}
        req = HedgeFundRequest.model_validate(merged)

        model_provider = req.model_provider
        if hasattr(model_provider, "value"):
            model_provider = model_provider.value

        portfolio = create_portfolio(
            req.initial_cash,
            req.margin_requirement,
            req.tickers,
            req.portfolio_positions,
        )

        graph = create_graph(
            graph_nodes=req.graph_nodes,
            graph_edges=req.graph_edges,
        ).compile()

        # Bridge the legacy progress singleton into the executor context so
        # the platform route never has to know about src.utils.progress.
        def _on_progress(agent_name, ticker, status, analysis, timestamp):
            context.emit(
                ProgressEvent(
                    node_id=agent_name,
                    status=status,
                    payload={
                        "ticker": ticker,
                        "analysis": analysis,
                        "timestamp": timestamp,
                    },
                )
            )

        progress.register_handler(_on_progress)
        try:
            result = await run_graph_async(
                graph=graph,
                portfolio=portfolio,
                tickers=req.tickers,
                start_date=req.start_date,
                end_date=req.end_date,
                model_name=req.model_name,
                model_provider=model_provider,
                request=req,
            )
        finally:
            progress.unregister_handler(_on_progress)

        if not result or not result.get("messages"):
            raise RuntimeError("Failed to generate hedge fund decisions")

        return {
            "decisions": parse_hedge_fund_response(result["messages"][-1].content),
            "analyst_signals": result.get("data", {}).get("analyst_signals", {}),
            "current_prices": result.get("data", {}).get("current_prices", {}),
        }
