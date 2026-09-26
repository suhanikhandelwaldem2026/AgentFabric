"""
agents/it_agent.py — Wave 3 (IT service-management / ticket triage).

Deliberately the "hard wave" per the strategy deck: highest single-
function gap (€140M), worst data quality (68/100 avg), most fragmented
system landscape (9 ERPs vs. 2 benchmark), and the only wave costing
MORE to build than Procurement (€5-6M vs €2-3M, Section 7) because it
needs a genuinely new connector type — this agent correlates a ticket
against TWO related tables (its source system's data-quality score AND
a known-issue/runbook library), not one flat lookup like the other three
agents. That's reflected here in decide() needing three independent
conditions instead of one threshold check.

Still calls fabric/approval_tool.py completely unmodified — the fourth
agent writing to the same shared audit log and escalation queue with
zero changes to that file. See erp_tools.py's "Added for IT" section for
what genuinely was new: 6 small, purely additive lookup functions.
"""
from __future__ import annotations

import os
from typing import Optional

from fabric import erp_tools, rag, approval_tool
from fabric.state import BaseAgentState

DATA_QUALITY_THRESHOLD = 75
SEVERITY_GUARD_USERS = 50


class ITState(BaseAgentState, total=False):
    ticket_id: str
    ticket: Optional[dict]
    system: Optional[dict]
    known_issue: Optional[dict]
    readiness_check: Optional[dict]


# ---------------------------------------------------------------------
# Graph nodes
# ---------------------------------------------------------------------

def fetch_ticket_and_context(state: ITState) -> ITState:
    """
    Unlike the other agents' single fetch, this pulls from three
    sources: the ticket itself, its reporting system's quality score,
    and (if present) the known issue it was matched against. This
    three-way correlation is the concrete shape of "new connector type."
    """
    ticket = erp_tools.get_ticket(state["ticket_id"])
    state["ticket"] = ticket

    if ticket is None:
        state["system"] = None
        state["known_issue"] = None
        return state

    state["system"] = erp_tools.get_system(ticket["reported_system_id"])

    known_issue_id = ticket.get("known_issue_id")
    state["known_issue"] = (
        erp_tools.get_known_issue(known_issue_id) if known_issue_id else None
    )
    return state


def assess_resolution_readiness(state: ITState) -> ITState:
    """
    Pure computation, no policy thresholds hardcoded here beyond what's
    needed to compute the checks — the actual threshold values live in
    decide(), matching the pattern in the other three agents.
    """
    ticket = state.get("ticket")
    system = state.get("system")
    known_issue = state.get("known_issue")

    if ticket is None:
        state["readiness_check"] = None
        return state

    state["readiness_check"] = {
        "has_known_issue_match": known_issue is not None,
        "source_system_quality_score": system["data_quality_score"] if system else None,
        "affected_users": ticket["affected_users"],
    }
    return state


def retrieve_it_policy(state: ITState) -> ITState:
    state["policy_context"] = rag.retrieve_policy(
        "known issue data quality severity auto-resolve ticket triage"
    )
    return state


def _maybe_llm_reason(fallback_reason: str, context: str) -> str:
    """Same fail-safe pattern as the other three agents."""
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
                    "In one short sentence, explain this IT ticket "
                    f"triage decision for an audit log. Context: {context}. "
                    f"Base reason: {fallback_reason}"
                ),
            }],
        )
        text_blocks = [b.text for b in response.content if getattr(b, "type", "") == "text"]
        return text_blocks[0].strip() if text_blocks else fallback_reason
    except Exception:
        return fallback_reason


def decide(state: ITState) -> ITState:
    """
    Three independent conditions must ALL hold to auto-resolve — more
    branching than any other agent's decide(), by design. This is what
    "the strategy deliberately makes IT stricter" looks like in code,
    not just in prose.
    """
    ticket = state.get("ticket")
    readiness = state.get("readiness_check")

    if ticket is None or readiness is None:
        state["decision"] = "escalate"
        state["decision_reason"] = "ticket not found"
        return state

    if not readiness["has_known_issue_match"]:
        reason = "no known-issue match — escalate for human triage"
        state["decision"] = "escalate"
        state["decision_reason"] = _maybe_llm_reason(reason, reason)
        return state

    quality_score = readiness["source_system_quality_score"]
    if quality_score is None or quality_score < DATA_QUALITY_THRESHOLD:
        reason = (
            f"source system data quality ({quality_score}/100) is below "
            f"the {DATA_QUALITY_THRESHOLD}/100 threshold — known-issue "
            "match alone is not sufficient given unreliable source data"
        )
        state["decision"] = "escalate"
        state["decision_reason"] = _maybe_llm_reason(reason, reason)
        return state

    affected_users = readiness["affected_users"]
    if affected_users > SEVERITY_GUARD_USERS:
        reason = (
            f"affected_users ({affected_users}) exceeds the "
            f"{SEVERITY_GUARD_USERS}-user severity guard — large-scale "
            "incidents always get human review regardless of match confidence"
        )
        state["decision"] = "escalate"
        state["decision_reason"] = _maybe_llm_reason(reason, reason)
        return state

    reason = (
        "known-issue match, source system quality "
        f"({quality_score}/100) meets threshold, and affected_users "
        f"({affected_users}) is within the severity guard"
    )
    state["decision"] = "auto_approve"
    state["decision_reason"] = _maybe_llm_reason(reason, reason)
    return state


def execute_outcome(state: ITState) -> ITState:
    entity_id = state["ticket_id"]
    known_issue = state.get("known_issue")

    if state["decision"] == "auto_approve":
        resolution = erp_tools.resolve_ticket(
            ticket_id=entity_id,
            runbook_id=known_issue["runbook_id"],
        )
        approval_tool.log_decision(
            agent_name="it_agent",
            entity_type="it_ticket",
            entity_id=entity_id,
            decision="auto_approve",
            reason=state["decision_reason"],
            amount_eur=None,
        )
        state["outcome"] = resolution
    else:
        ticket_out = approval_tool.request_human_review(
            agent_name="it_agent",
            entity_type="it_ticket",
            entity_id=entity_id,
            reason=state["decision_reason"],
        )
        approval_tool.log_decision(
            agent_name="it_agent",
            entity_type="it_ticket",
            entity_id=entity_id,
            decision="escalate",
            reason=state["decision_reason"],
            amount_eur=None,
        )
        state["outcome"] = ticket_out

    return state


# ---------------------------------------------------------------------
# Entry point used by tests and by the demo
# ---------------------------------------------------------------------

def run_it_agent(ticket_id: str) -> ITState:
    """
    fetch_ticket_and_context -> assess_resolution_readiness ->
    retrieve_it_policy -> decide -> execute_outcome
    """
    state: ITState = {"ticket_id": ticket_id}
    state = fetch_ticket_and_context(state)
    state = assess_resolution_readiness(state)
    state = retrieve_it_policy(state)
    state = decide(state)
    state = execute_outcome(state)
    return state


def build_it_graph():
    """LangGraph assembly — same optional pattern as the other agents."""
    from langgraph.graph import StateGraph, END

    graph = StateGraph(ITState)
    graph.add_node("fetch_ticket_and_context", fetch_ticket_and_context)
    graph.add_node("assess_resolution_readiness", assess_resolution_readiness)
    graph.add_node("retrieve_it_policy", retrieve_it_policy)
    graph.add_node("decide", decide)
    graph.add_node("execute_outcome", execute_outcome)

    graph.set_entry_point("fetch_ticket_and_context")
    graph.add_edge("fetch_ticket_and_context", "assess_resolution_readiness")
    graph.add_edge("assess_resolution_readiness", "retrieve_it_policy")
    graph.add_edge("retrieve_it_policy", "decide")
    graph.add_edge("decide", "execute_outcome")
    graph.add_edge("execute_outcome", END)

    return graph.compile()
