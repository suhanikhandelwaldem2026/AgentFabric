"""
tests/test_it_agent.py — IT (Wave 3) acceptance tests.

Runnable directly: `python3 tests/test_it_agent.py`
Runs with USE_LLM=false (default) — zero API calls.
"""
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("USE_LLM", "false")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from agents.finance_agent import run_finance_agent  # noqa: E402
from agents.procurement_agent import run_procurement_agent  # noqa: E402
from agents.corporate_agent import run_corporate_agent  # noqa: E402
from agents.it_agent import run_it_agent  # noqa: E402

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
    "TCK-6001": "auto_approve",  # match + high quality + low severity
    "TCK-6002": "escalate",      # no known-issue match
    "TCK-6003": "escalate",      # match but source quality below 75
    "TCK-6004": "escalate",      # match + high quality but severity guard trips
}

FINANCE_INVOICE_IDS = [
    "INV-2001", "INV-2002", "INV-2003", "INV-2004",
    "INV-2005", "INV-2006", "INV-2007", "INV-2008",
]
PROCUREMENT_RFQ_IDS = ["RFQ-4001", "RFQ-4002", "RFQ-4003"]
CORPORATE_REQUEST_IDS = ["RPT-5001", "RPT-5002", "RPT-5003", "RPT-5004"]


def main():
    reset_audit_files()

    print("== IT agent: decision correctness across all 4 tickets ==")
    results = {}
    for ticket_id, expected_decision in EXPECTED.items():
        result_state = run_it_agent(ticket_id)
        results[ticket_id] = result_state
        check(
            f"{ticket_id} -> expected '{expected_decision}', got '{result_state['decision']}'",
            result_state["decision"] == expected_decision,
        )

    print("\n== IT agent: each escalation reason names the SPECIFIC failing condition ==")
    check(
        "TCK-6002 (no match) reason mentions 'known-issue'",
        "known-issue" in results["TCK-6002"]["decision_reason"].lower(),
    )
    check(
        "TCK-6003 (low quality) reason mentions 'data quality' and the score",
        "data quality" in results["TCK-6003"]["decision_reason"].lower()
        and "61" in results["TCK-6003"]["decision_reason"],
    )
    check(
        "TCK-6004 (severity) reason mentions 'severity guard' and the user count",
        "severity guard" in results["TCK-6004"]["decision_reason"].lower()
        and "450" in results["TCK-6004"]["decision_reason"],
    )

    print("\n== IT agent: auto-resolved ticket used the correct runbook ==")
    outcome = results["TCK-6001"]["outcome"]
    check(
        "TCK-6001 outcome has status='resolved'",
        outcome is not None and outcome.get("status") == "resolved",
    )
    check(
        "TCK-6001 resolved via KI-01's runbook (RB-100)",
        outcome.get("runbook_id") == "RB-100",
    )

    print("\n== IT agent: audit log has exactly 4 new records ==")
    with open(AUDIT_LOG_FILE, "r", encoding="utf-8") as f:
        audit_records = json.load(f)
    it_records = [r for r in audit_records if r["agent_name"] == "it_agent"]
    check("4 it_agent records in audit_log.json", len(it_records) == 4)

    print("\n== Four-agent shared infrastructure regression check ==")
    for invoice_id in FINANCE_INVOICE_IDS:
        run_finance_agent(invoice_id)
    for rfq_id in PROCUREMENT_RFQ_IDS:
        run_procurement_agent(rfq_id)
    for request_id in CORPORATE_REQUEST_IDS:
        run_corporate_agent(request_id)

    with open(AUDIT_LOG_FILE, "r", encoding="utf-8") as f:
        audit_records = json.load(f)
    agent_names_present = {r["agent_name"] for r in audit_records}
    check(
        "audit_log.json contains ALL FOUR agent_name values in the SAME file",
        agent_names_present == {"finance_agent", "procurement_agent", "corporate_agent", "it_agent"},
    )
    check("audit_log.json has exactly 19 records (4 + 8 + 3 + 4)", len(audit_records) == 19)

    print(f"\n{_passed} passed, {_failed} failed")
    if _failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
