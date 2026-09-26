"""
tests/test_corporate_agent.py — Corporate (Wave 5) acceptance tests.

Runnable directly: `python3 tests/test_corporate_agent.py`
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
    "RPT-5001": "auto_approve",  # clean, all sources available and fresh
    "RPT-5002": "escalate",      # missing source (CRM_Sales unavailable)
    "RPT-5003": "escalate",      # stale source (15 days > 7 day threshold)
    "RPT-5004": "auto_approve",  # clean, single source available and fresh
}

FINANCE_INVOICE_IDS = [
    "INV-2001", "INV-2002", "INV-2003", "INV-2004",
    "INV-2005", "INV-2006", "INV-2007", "INV-2008",
]
PROCUREMENT_RFQ_IDS = ["RFQ-4001", "RFQ-4002", "RFQ-4003"]


def main():
    reset_audit_files()

    print("== Corporate agent: decision correctness across all 4 report requests ==")
    results = {}
    for request_id, expected_decision in EXPECTED.items():
        result_state = run_corporate_agent(request_id)
        results[request_id] = result_state
        check(
            f"{request_id} -> expected '{expected_decision}', got '{result_state['decision']}'",
            result_state["decision"] == expected_decision,
        )

    print("\n== Corporate agent: reason content sanity checks ==")
    check(
        "RPT-5002 (missing source) reason mentions unavailable",
        "unavailable" in results["RPT-5002"]["decision_reason"].lower(),
    )
    check(
        "RPT-5003 (stale source) reason mentions stale",
        "stale" in results["RPT-5003"]["decision_reason"].lower(),
    )

    print("\n== Corporate agent: auto-approved requests published a report ==")
    for request_id in ("RPT-5001", "RPT-5004"):
        outcome = results[request_id]["outcome"]
        check(
            f"{request_id} outcome has status='published'",
            outcome is not None and outcome.get("status") == "published",
        )

    print("\n== Corporate agent: audit log has exactly 4 new records ==")
    with open(AUDIT_LOG_FILE, "r", encoding="utf-8") as f:
        audit_records = json.load(f)
    corporate_records = [r for r in audit_records if r["agent_name"] == "corporate_agent"]
    check("4 corporate_agent records in audit_log.json", len(corporate_records) == 4)

    print("\n== Three-agent shared infrastructure regression check ==")
    for invoice_id in FINANCE_INVOICE_IDS:
        run_finance_agent(invoice_id)
    for rfq_id in PROCUREMENT_RFQ_IDS:
        run_procurement_agent(rfq_id)

    with open(AUDIT_LOG_FILE, "r", encoding="utf-8") as f:
        audit_records = json.load(f)
    agent_names_present = {r["agent_name"] for r in audit_records}
    check(
        "audit_log.json contains ALL THREE agent_name values in the SAME file",
        agent_names_present == {"finance_agent", "procurement_agent", "corporate_agent"},
    )
    check("audit_log.json has exactly 15 records (4 + 8 + 3)", len(audit_records) == 15)

    print(f"\n{_passed} passed, {_failed} failed")
    if _failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
