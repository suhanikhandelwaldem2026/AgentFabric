"""
agents/corporate_agent.py — Wave 5 (Corporate management reporting).

Cheapest, lowest-risk wave per the strategy deck (Section 7: €1.5-2M,
config-only, self-funds harder waves). Same five-node shape as Finance
and Procurement. Calls fabric/approval_tool.py completely unmodified —
this is the third agent writing to the same shared audit log and
escalation queue with zero changes to that file.

Unlike Procurement, this agent's data (report requests) is a new entity
type not covered by Phase 2's original erp_tools.py, so three small
lookup functions were added there (get_report_request,
list_report_requests, publish_report) — purely additive, verified via
diff, nothing existing modified. See erp_tools.py's "Added for
Corporate" section.
"""
from __future__ import annotations

import os
from typing import Optional

from fabric import erp_tools, rag, approval_tool
from fabric.state import BaseAgentState

FRESHNESS_THRESHOLD_DAYS = 7


class CorporateState(BaseAgentState, total=False):
    request_id: str
    report_request: Optional[dict]
    readiness_check: Optional[dict]


# ---------------------------------------------------------------------
# Graph nodes
# ---------------------------------------------------------------------

def fetch_report_request(state: CorporateState) -> CorporateState:
    state["report_request"] = erp_tools.get_report_request(state["request_id"])
    return state


def check_data_readiness(state: CorporateState) -> CorporateState:
    """
    Pure computation, no policy logic. Checks every listed data source
    for availability and freshness against the 7-day threshold.
    """
    request = state.get("report_request")
    if request is None:
        state["readiness_check"] = None
        return state

    unavailable = []
    stale = []

    for source in request["data_sources"]:
        if not source["available"]:
            unavailable.append(source["source_name"])
        elif source["last_updated_days_ago"] is not None and \
                source["last_updated_days_ago"] > FRESHNESS_THRESHOLD_DAYS:
            stale.append(source["source_name"])

    state["readiness_check"] = {
        "unavailable_sources": unavailable,
        "stale_sources": stale,
        "all_ready": len(unavailable) == 0 and len(stale) == 0,
    }
    return state


def retrieve_corporate_policy(state: CorporateState) -> CorporateState:
    state["policy_context"] = rag.retrieve_policy(
        "management reporting data source freshness auto-generate"
    )
    return state


def _maybe_llm_reason(fallback_reason: str, context: str) -> str:
    """Same fail-safe pattern as finance_agent / procurement_agent."""
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
                    "In one short sentence, explain this management "
                    f"reporting decision for an audit log. Context: {context}. "
                    f"Base reason: {fallback_reason}"
                ),
            }],
        )
        text_blocks = [b.text for b in response.content if getattr(b, "type", "") == "text"]
        return text_blocks[0].strip() if text_blocks else fallback_reason
    except Exception:
        return fallback_reason


def decide(state: CorporateState) -> CorporateState:
    """The only node with business logic. Deterministic."""
    request = state.get("report_request")
    readiness = state.get("readiness_check")

    if request is None or readiness is None:
        state["decision"] = "escalate"
        state["decision_reason"] = "report request not found"
        return state

    if readiness["all_ready"]:
        reason = "all data sources available and fresh (within 7-day threshold)"
        state["decision"] = "auto_approve"
        state["decision_reason"] = _maybe_llm_reason(reason, reason)
        return state

    problems = []
    if readiness["unavailable_sources"]:
        problems.append(f"unavailable: {', '.join(readiness['unavailable_sources'])}")
    if readiness["stale_sources"]:
        problems.append(f"stale (>7 days): {', '.join(readiness['stale_sources'])}")
    reason = "data not ready for auto-generation — " + "; ".join(problems)

    state["decision"] = "escalate"
    state["decision_reason"] = _maybe_llm_reason(reason, reason)
    return state


def execute_outcome(state: CorporateState) -> CorporateState:
    request = state.get("report_request")
    entity_id = state["request_id"]

    if state["decision"] == "auto_approve":
        publication = erp_tools.publish_report(
            request_id=entity_id,
            report_type=request["report_type"],
        )
        approval_tool.log_decision(
            agent_name="corporate_agent",
            entity_type="report_request",
            entity_id=entity_id,
            decision="auto_approve",
            reason=state["decision_reason"],
            amount_eur=None,
        )
        state["outcome"] = publication
    else:
        ticket = approval_tool.request_human_review(
            agent_name="corporate_agent",
            entity_type="report_request",
            entity_id=entity_id,
            reason=state["decision_reason"],
        )
        approval_tool.log_decision(
            agent_name="corporate_agent",
            entity_type="report_request",
            entity_id=entity_id,
            decision="escalate",
            reason=state["decision_reason"],
            amount_eur=None,
        )
        state["outcome"] = ticket

    return state


# ---------------------------------------------------------------------
# Entry point used by tests and by the demo
# ---------------------------------------------------------------------

def run_corporate_agent(request_id: str) -> CorporateState:
    """
    fetch_report_request -> check_data_readiness ->
    retrieve_corporate_policy -> decide -> execute_outcome
    """
    state: CorporateState = {"request_id": request_id}
    state = fetch_report_request(state)
    state = check_data_readiness(state)
    state = retrieve_corporate_policy(state)
    state = decide(state)
    state = execute_outcome(state)
    return state


def build_corporate_graph():
    """LangGraph assembly — same optional pattern as the other two agents."""
    from langgraph.graph import StateGraph, END

    graph = StateGraph(CorporateState)
    graph.add_node("fetch_report_request", fetch_report_request)
    graph.add_node("check_data_readiness", check_data_readiness)
    graph.add_node("retrieve_corporate_policy", retrieve_corporate_policy)
    graph.add_node("decide", decide)
    graph.add_node("execute_outcome", execute_outcome)

    graph.set_entry_point("fetch_report_request")
    graph.add_edge("fetch_report_request", "check_data_readiness")
    graph.add_edge("check_data_readiness", "retrieve_corporate_policy")
    graph.add_edge("retrieve_corporate_policy", "decide")
    graph.add_edge("decide", "execute_outcome")
    graph.add_edge("execute_outcome", END)

    return graph.compile()
