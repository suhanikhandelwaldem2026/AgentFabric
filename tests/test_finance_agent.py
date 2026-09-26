"""
tests/test_finance_agent.py — Phase 3 acceptance tests.

Runnable directly: `python3 tests/test_finance_agent.py`
Runs with USE_LLM=false (default) — zero API calls.
"""
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("USE_LLM", "false")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from agents.finance_agent import run_finance_agent  # noqa: E402

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
AUDIT_LOG_FILE = DATA_DIR / "audit_log.json"
ESCALATION_QUEUE_FILE = DATA_DIR / "escalation_queue.json"

_passed = 0
_failed = 0


def check(label: str, condition: bool):
    global _passed, _failed
    if condition:
        _passed += 1
        print(f"  PASS  {label}")
    else:
        _failed += 1
        print(f"  FAIL  {label}")


def reset_audit_files():
    for f in (AUDIT_LOG_FILE, ESCALATION_QUEUE_FILE):
        if f.exists():
            f.unlink()


EXPECTED = {
    "INV-2001": "auto_approve",  # clean, under threshold
    "INV-2002": "auto_approve",  # clean, under threshold
    "INV-2003": "auto_approve",  # clean, under threshold
    "INV-2004": "auto_approve",  # clean, under threshold
    "INV-2005": "escalate",      # clean, OVER threshold
    "INV-2006": "escalate",      # line-item mismatch
    "INV-2007": "escalate",      # unknown vendor
    "INV-2008": "auto_approve",  # clean, under threshold
}


def main():
    reset_audit_files()

    results = {}
    for invoice_id in EXPECTED:
        result_state = run_finance_agent(invoice_id)
        results[invoice_id] = result_state

    print("== Finance agent: decision correctness across all 8 invoices ==")
    for invoice_id, expected_decision in EXPECTED.items():
        actual = results[invoice_id]["decision"]
        check(
            f"{invoice_id} -> expected '{expected_decision}', got '{actual}'",
            actual == expected_decision,
        )

    print("\n== Finance agent: reason content sanity checks ==")
    check(
        "INV-2005 (over threshold) reason mentions threshold",
        "threshold" in results["INV-2005"]["decision_reason"].lower(),
    )
    check(
        "INV-2006 (mismatch) reason mentions match/discrepancy",
        any(
            kw in results["INV-2006"]["decision_reason"].lower()
            for kw in ("match", "discrepanc", "mismatch")
        ),
    )
    check(
        "INV-2007 (unknown vendor) reason mentions vendor",
        "vendor" in results["INV-2007"]["decision_reason"].lower(),
    )

    print("\n== Finance agent: audit log has exactly 8 new records ==")
    with open(AUDIT_LOG_FILE, "r", encoding="utf-8") as f:
        audit_records = json.load(f)
    finance_records = [r for r in audit_records if r["agent_name"] == "finance_agent"]
    check("8 finance_agent records in audit_log.json", len(finance_records) == 8)

    print("\n== Finance agent: escalated invoices produced escalation tickets ==")
    with open(ESCALATION_QUEUE_FILE, "r", encoding="utf-8") as f:
        escalations = json.load(f)
    escalated_ids = {e["entity_id"] for e in escalations}
    expected_escalated_ids = {
        inv_id for inv_id, dec in EXPECTED.items() if dec == "escalate"
    }
    check(
        "escalation_queue.json contains exactly the 3 expected escalated invoices",
        escalated_ids == expected_escalated_ids,
    )

    print("\n== Finance agent: auto-approved invoices scheduled payment ==")
    auto_approved_ids = {
        inv_id for inv_id, dec in EXPECTED.items() if dec == "auto_approve"
    }
    for inv_id in auto_approved_ids:
        outcome = results[inv_id]["outcome"]
        check(
            f"{inv_id} outcome has status='scheduled'",
            outcome is not None and outcome.get("status") == "scheduled",
        )

    print(f"\n{_passed} passed, {_failed} failed")
    if _failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
