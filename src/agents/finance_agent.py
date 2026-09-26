"""
agents/finance_agent.py — Wave 1 (Finance invoice processing).

Calls fabric/* tools unmodified. Contains all Finance-specific business
logic; the fabric layer stays generic.

Two ways to run this:
  1. run_finance_agent(invoice_id) — the entry point Phase 5's demo uses.
     Runs the five nodes in sequence directly, so it works with zero
     external dependencies (no langgraph required) and is what this
     phase's tests actually exercise.
  2. build_finance_graph() — assembles the same five nodes into a real
     LangGraph StateGraph, for anyone who wants to run/observe this
     through the LangGraph runtime. Only imports langgraph when called,
     so its absence never breaks run_finance_agent().
"""
from __future__ import annotations

import os
from typing import Optional

from fabric import erp_tools, rag, approval_tool
from fabric.state import BaseAgentState

FINANCE_THRESHOLD_EUR = 50_000.00


class FinanceState(BaseAgentState, total=False):
    invoice_id: str
    invoice: Optional[dict]
    po: Optional[dict]
    match_result: Optional[dict]


# ---------------------------------------------------------------------
# Graph nodes
# ---------------------------------------------------------------------

def fetch_invoice_and_po(state: FinanceState) -> FinanceState:
    invoice = erp_tools.get_invoice(state["invoice_id"])
    po = erp_tools.get_purchase_order(invoice["po_id"]) if invoice else None
    state["invoice"] = invoice
    state["po"] = po
    return state


def run_three_way_match(state: FinanceState) -> FinanceState:
    invoice = state.get("invoice")
    po = state.get("po")
    if invoice is None:
        state["match_result"] = {"matched": False, "discrepancies": ["invoice not found"]}
    else:
        state["match_result"] = erp_tools.check_three_way_match(invoice, po)
    return state


def retrieve_finance_policy(state: FinanceState) -> FinanceState:
    state["policy_context"] = rag.retrieve_policy(
        "three-way match threshold invoice approval"
    )
    return state


def _maybe_llm_reason(fallback_reason: str, context: str) -> str:
    """
    If USE_LLM=true and the anthropic package + API key are available,
    ask the model to phrase the reason in natural language. The LLM only
    explains — it never changes the decision computed deterministically
    in decide(). Falls back silently to the template reason otherwise,
    so this never introduces a hard dependency on the API.
    """
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
                    "In one short sentence, explain this finance "
                    f"decision for an audit log. Context: {context}. "
                    f"Base reason: {fallback_reason}"
                ),
            }],
        )
        text_blocks = [b.text for b in response.content if getattr(b, "type", "") == "text"]
        return text_blocks[0].strip() if text_blocks else fallback_reason
    except Exception:
        # Never let an LLM/network failure break a deterministic decision.
        return fallback_reason


def decide(state: FinanceState) -> FinanceState:
    """
    The only node with business logic. Deterministic; USE_LLM only
    affects the phrasing of decision_reason, never the decision itself.
    """
    invoice = state.get("invoice")
    match_result = state.get("match_result") or {"matched": False, "discrepancies": []}

    if invoice is None:
        state["decision"] = "escalate"
        state["decision_reason"] = "invoice not found"
        return state

    vendor = erp_tools.get_vendor(invoice["vendor_id"])
    if vendor is None:
        reason = "unknown vendor"
        state["decision"] = "escalate"
        state["decision_reason"] = _maybe_llm_reason(
            reason, f"vendor_id {invoice['vendor_id']} not found in vendor master"
        )
        return state

    if not match_result["matched"]:
        reason = "three-way match failed: " + "; ".join(match_result["discrepancies"])
        state["decision"] = "escalate"
        state["decision_reason"] = _maybe_llm_reason(reason, reason)
        return state

    amount = invoice["amount_eur"]
    if amount <= FINANCE_THRESHOLD_EUR:
        reason = "three-way match passed, known vendor, within €50,000 threshold"
        state["decision"] = "auto_approve"
        state["decision_reason"] = _maybe_llm_reason(reason, reason)
    else:
        reason = "over threshold, requires human sign-off"
        state["decision"] = "escalate"
        state["decision_reason"] = _maybe_llm_reason(
            reason, f"amount {amount} exceeds €50,000 threshold despite clean match"
        )

    return state


def execute_outcome(state: FinanceState) -> FinanceState:
    invoice = state.get("invoice")
    entity_id = state["invoice_id"]
    amount = invoice["amount_eur"] if invoice else None

    if state["decision"] == "auto_approve":
        payment = erp_tools.schedule_payment(
            invoice_id=entity_id,
            amount_eur=amount,
            terms=erp_tools.get_vendor(invoice["vendor_id"])["payment_terms"],
        )
        approval_tool.log_decision(
            agent_name="finance_agent",
            entity_type="invoice",
            entity_id=entity_id,
            decision="auto_approve",
            reason=state["decision_reason"],
            amount_eur=amount,
        )
        state["outcome"] = payment
    else:
        ticket = approval_tool.request_human_review(
            agent_name="finance_agent",
            entity_type="invoice",
            entity_id=entity_id,
            reason=state["decision_reason"],
        )
        approval_tool.log_decision(
            agent_name="finance_agent",
            entity_type="invoice",
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

def run_finance_agent(invoice_id: str) -> FinanceState:
    """
    Runs the five Finance nodes in sequence:
    fetch_invoice_and_po -> run_three_way_match -> retrieve_finance_policy
    -> decide -> execute_outcome
    """
    state: FinanceState = {"invoice_id": invoice_id}
    state = fetch_invoice_and_po(state)
    state = run_three_way_match(state)
    state = retrieve_finance_policy(state)
    state = decide(state)
    state = execute_outcome(state)
    return state


# ---------------------------------------------------------------------
# Optional: real LangGraph assembly (not required for run_finance_agent)
# ---------------------------------------------------------------------

def build_finance_graph():
    """
    Assembles the same five nodes into a LangGraph StateGraph. Requires
    the `langgraph` package. Not called by run_finance_agent() or by
    the test suite — provided for anyone who wants to run this agent
    through the LangGraph runtime directly.
    """
    from langgraph.graph import StateGraph, END

    graph = StateGraph(FinanceState)
    graph.add_node("fetch_invoice_and_po", fetch_invoice_and_po)
    graph.add_node("run_three_way_match", run_three_way_match)
    graph.add_node("retrieve_finance_policy", retrieve_finance_policy)
    graph.add_node("decide", decide)
    graph.add_node("execute_outcome", execute_outcome)

    graph.set_entry_point("fetch_invoice_and_po")
    graph.add_edge("fetch_invoice_and_po", "run_three_way_match")
    graph.add_edge("run_three_way_match", "retrieve_finance_policy")
    graph.add_edge("retrieve_finance_policy", "decide")
    graph.add_edge("decide", "execute_outcome")
    graph.add_edge("execute_outcome", END)

    return graph.compile()
