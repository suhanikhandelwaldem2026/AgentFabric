"""
agents/procurement_agent.py — Wave 2 (Procurement RFQ/quote comparison).

Mirrors finance_agent.py's node structure deliberately. Calls fabric/*
tools unmodified — this file adds zero lines to fabric/. That's the
concrete proof point behind the Fabric strategy's "second agent is a
configuration exercise, not a new integration project" claim.
"""
from __future__ import annotations

import os
from typing import Optional

from fabric import erp_tools, rag, approval_tool
from fabric.state import BaseAgentState

AUTO_SELECT_BAND = 0.10       # ±10%
TIE_BREAK_THRESHOLD = 0.01    # 1%
OUTLIER_THRESHOLD = 0.15      # 15% below benchmark


class ProcurementState(BaseAgentState, total=False):
    rfq_id: str
    rfq: Optional[dict]
    quote_analysis: Optional[dict]


# ---------------------------------------------------------------------
# Graph nodes
# ---------------------------------------------------------------------

def fetch_rfq(state: ProcurementState) -> ProcurementState:
    state["rfq"] = erp_tools.get_rfq(state["rfq_id"])
    return state


def analyze_quotes(state: ProcurementState) -> ProcurementState:
    """
    Pure computation, no policy logic. Given rfq["quotes"] and
    rfq["historical_price_index_eur"], compute lowest quote, ranking,
    tie flag, and outlier flag.
    """
    rfq = state.get("rfq")
    if rfq is None:
        state["quote_analysis"] = None
        return state

    quotes = rfq["quotes"]
    benchmark = rfq["historical_price_index_eur"]

    sorted_quotes = sorted(quotes, key=lambda q: q["total_eur"])
    lowest = sorted_quotes[0]

    lowest_vs_benchmark_pct = (lowest["total_eur"] - benchmark) / benchmark

    is_tie = False
    if len(sorted_quotes) >= 2:
        second = sorted_quotes[1]
        tie_pct = abs(second["total_eur"] - lowest["total_eur"]) / lowest["total_eur"]
        is_tie = tie_pct <= TIE_BREAK_THRESHOLD

    is_outlier = lowest_vs_benchmark_pct < -OUTLIER_THRESHOLD

    state["quote_analysis"] = {
        "lowest_quote": lowest,
        "sorted_quotes": sorted_quotes,
        "lowest_vs_benchmark_pct": lowest_vs_benchmark_pct,
        "is_tie": is_tie,
        "is_outlier": is_outlier,
    }
    return state


def retrieve_procurement_policy(state: ProcurementState) -> ProcurementState:
    state["policy_context"] = rag.retrieve_policy(
        "quote selection tie-break auto-select outlier"
    )
    return state


def _maybe_llm_reason(fallback_reason: str, context: str) -> str:
    """Identical pattern to finance_agent.py's helper — LLM explains,
    never decides, and fails safe back to the template reason."""
    if os.getenv("USE_LLM", "false").lower() != "true":
        return fallback_reason
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return fallback_reason
    try:
        client = anthropic.Anthropic()
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=100,
            messages=[{
                "role": "user",
                "content": (
                    "In one short sentence, explain this procurement "
                    f"decision for an audit log. Context: {context}. "
                    f"Base reason: {fallback_reason}"
                ),
            }],
        )
        text_blocks = [b.text for b in response.content if getattr(b, "type", "") == "text"]
        return text_blocks[0].strip() if text_blocks else fallback_reason
    except Exception:
        return fallback_reason


def decide(state: ProcurementState) -> ProcurementState:
    """
    The only node with business logic — mirrors finance_agent.decide()'s
    role in its graph. Deterministic; USE_LLM only affects phrasing.
    """
    rfq = state.get("rfq")
    analysis = state.get("quote_analysis")

    if rfq is None or analysis is None:
        state["decision"] = "escalate"
        state["decision_reason"] = "RFQ not found"
        return state

    if analysis["is_outlier"]:
        reason = (
            "lowest quote >15% below historical price index — possible "
            "data error or non-compliant vendor, needs verification"
        )
        state["decision"] = "escalate"
        state["decision_reason"] = _maybe_llm_reason(
            reason,
            f"lowest quote is {analysis['lowest_vs_benchmark_pct']:.1%} vs benchmark",
        )
        return state

    if analysis["is_tie"]:
        reason = "two or more quotes within 1% — human tie-break required"
        state["decision"] = "escalate"
        state["decision_reason"] = _maybe_llm_reason(reason, reason)
        return state

    if abs(analysis["lowest_vs_benchmark_pct"]) <= AUTO_SELECT_BAND:
        reason = "lowest compliant quote within ±10% of historical price index"
        state["decision"] = "auto_approve"
        state["decision_reason"] = _maybe_llm_reason(reason, reason)
        return state

    # Falls outside ±10% band but wasn't caught by the 15%-below outlier
    # rule (e.g. priced above benchmark, or between 10-15% below) —
    # policy says don't default to auto-approval here.
    reason = "lowest quote outside ±10% policy band"
    state["decision"] = "escalate"
    state["decision_reason"] = _maybe_llm_reason(
        reason,
        f"lowest quote is {analysis['lowest_vs_benchmark_pct']:.1%} vs benchmark, "
        "outside the auto-select band but not a 15%+ outlier",
    )
    return state


def execute_outcome(state: ProcurementState) -> ProcurementState:
    rfq = state.get("rfq")
    entity_id = state["rfq_id"]
    analysis = state.get("quote_analysis")
    amount = analysis["lowest_quote"]["total_eur"] if analysis else None

    if state["decision"] == "auto_approve":
        winning_vendor_id = analysis["lowest_quote"]["vendor_id"]
        po_confirmation = erp_tools.issue_purchase_order(
            rfq_id=entity_id,
            vendor_id=winning_vendor_id,
            amount_eur=amount,
        )
        approval_tool.log_decision(
            agent_name="procurement_agent",
            entity_type="rfq",
            entity_id=entity_id,
            decision="auto_approve",
            reason=state["decision_reason"],
            amount_eur=amount,
        )
        state["outcome"] = po_confirmation
    else:
        ticket = approval_tool.request_human_review(
            agent_name="procurement_agent",
            entity_type="rfq",
            entity_id=entity_id,
            reason=state["decision_reason"],
        )
        approval_tool.log_decision(
            agent_name="procurement_agent",
            entity_type="rfq",
            entity_id=entity_id,
            decision="escalate",
            reason=state["decision_reason"],
            amount_eur=amount,
        )
        state["outcome"] = ticket

    return state


# ---------------------------------------------------------------------
# Entry point used by tests and by Phase 5's demo
# ---------------------------------------------------------------------

def run_procurement_agent(rfq_id: str) -> ProcurementState:
    """
    Runs the five Procurement nodes in sequence:
    fetch_rfq -> analyze_quotes -> retrieve_procurement_policy -> decide
    -> execute_outcome

    Same "call nodes directly" pattern as run_finance_agent — works with
    zero external dependencies. See build_procurement_graph() below for
    the LangGraph-runtime version.
    """
    state: ProcurementState = {"rfq_id": rfq_id}
    state = fetch_rfq(state)
    state = analyze_quotes(state)
    state = retrieve_procurement_policy(state)
    state = decide(state)
    state = execute_outcome(state)
    return state


# ---------------------------------------------------------------------
# Optional: real LangGraph assembly (not required for run_procurement_agent)
# ---------------------------------------------------------------------

def build_procurement_graph():
    """
    Assembles the same five nodes into a LangGraph StateGraph. Requires
    the `langgraph` package. Mirrors finance_agent.build_finance_graph()
    exactly in shape.
    """
    from langgraph.graph import StateGraph, END

    graph = StateGraph(ProcurementState)
    graph.add_node("fetch_rfq", fetch_rfq)
    graph.add_node("analyze_quotes", analyze_quotes)
    graph.add_node("retrieve_procurement_policy", retrieve_procurement_policy)
    graph.add_node("decide", decide)
    graph.add_node("execute_outcome", execute_outcome)

    graph.set_entry_point("fetch_rfq")
    graph.add_edge("fetch_rfq", "analyze_quotes")
    graph.add_edge("analyze_quotes", "retrieve_procurement_policy")
    graph.add_edge("retrieve_procurement_policy", "decide")
    graph.add_edge("decide", "execute_outcome")
    graph.add_edge("execute_outcome", END)

    return graph.compile()
