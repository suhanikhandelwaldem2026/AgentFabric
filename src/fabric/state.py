"""
fabric/state.py — shared base state shape.

finance_agent.py and procurement_agent.py both extend BaseAgentState
rather than each inventing an incompatible state shape from scratch.
"""
from __future__ import annotations

from typing import TypedDict


class BaseAgentState(TypedDict, total=False):
    """
    Fields common to any agent built on the Fabric.

    entity_id       — the invoice_id / rfq_id / etc. being processed
    policy_context   — the policy section text retrieved via rag.retrieve_policy
    decision         — "auto_approve" | "escalate"
    decision_reason  — human-readable reason for the decision
    outcome          — result of executing the decision (payment confirmation,
                        PO issuance confirmation, or escalation ticket)
    """
    entity_id: str
    policy_context: str
    decision: str | None
    decision_reason: str | None
    outcome: dict | None
