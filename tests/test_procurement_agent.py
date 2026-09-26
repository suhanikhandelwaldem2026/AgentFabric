"""
tests/test_procurement_agent.py — Phase 4 acceptance tests.

Runnable directly: `python3 tests/test_procurement_agent.py`
Runs with USE_LLM=false (default) — zero API calls.

Also re-runs Phase 3's finance batch first so this file can assert the
regression check that matters most: both agent_name values landing in
the SAME audit_log.json, without needing a separate cross-phase script.
"""
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("USE_LLM", "false")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from agents.finance_agent import run_finance_agent  # noqa: E402
from agents.procurement_agent import run_procurement_agent  # noqa: E402

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
AUDIT_LOG_FILE = DATA_DIR / "audit_log.json"
ESCALATION_QUEUE_FILE = DATA_DIR / "escalation_queue.json"
FABRIC_DIR = Path(__file__).resolve().parent.parent / "src" / "fabric"

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


EXPECTED_RFQ = {
    "RFQ-4001": "auto_approve",  # clean — clearly lowest, within 5% of benchmark
    "RFQ-4002": "escalate",      # ambiguous — top two within 1%, tie-break
    "RFQ-4003": "escalate",      # outlier — lowest >15% below benchmark
}

FINANCE_INVOICE_IDS = [
    "INV-2001", "INV-2002", "INV-2003", "INV-2004",
    "INV-2005", "INV-2006", "INV-2007", "INV-2008",
]


def main():
    reset_audit_files()

    print("== Sanity: fabric/ files unchanged since before this phase ==")
    fabric_files = sorted(FABRIC_DIR.glob("*.py"))
    check("fabric/ still has exactly 5 files (init + 4 modules)", len(fabric_files) == 5)
    print("  (byte-for-byte diff check done separately via md5sum in the build log)")

    # Run Phase 3's finance batch first so the audit log has both agents'
    # records in it for the shared-file regression check below.
    for invoice_id in FINANCE_INVOICE_IDS:
        run_finance_agent(invoice_id)

    print("\n== Procurement agent: decision correctness across all 3 RFQs ==")
    results = {}
    for rfq_id, expected_decision in EXPECTED_RFQ.items():
        result_state = run_procurement_agent(rfq_id)
        results[rfq_id] = result_state
        check(
            f"{rfq_id} -> expected '{expected_decision}', got '{result_state['decision']}'",
            result_state["decision"] == expected_decision,
        )

    print("\n== Procurement agent: reason content sanity checks ==")
    check(
        "RFQ-4002 (tie) reason mentions tie-break",
        "tie-break" in results["RFQ-4002"]["decision_reason"].lower(),
    )
    check(
        "RFQ-4003 (outlier) reason mentions verification",
        "verif" in results["RFQ-4003"]["decision_reason"].lower(),
    )

    print("\n== Procurement agent: auto-approved RFQ issued a PO ==")
    auto_outcome = results["RFQ-4001"]["outcome"]
    check(
        "RFQ-4001 outcome has status='issued'",
        auto_outcome is not None and auto_outcome.get("status") == "issued",
    )
    check(
        "RFQ-4001 PO went to the lowest quote's vendor (V-1001)",
        auto_outcome.get("vendor_id") == "V-1001",
    )

    print("\n== Shared infrastructure regression check ==")
    with open(AUDIT_LOG_FILE, "r", encoding="utf-8") as f:
        audit_records = json.load(f)
    agent_names_present = {r["agent_name"] for r in audit_records}
    check(
        "audit_log.json contains BOTH agent_name values in the SAME file",
        agent_names_present == {"finance_agent", "procurement_agent"},
    )
    finance_count = len([r for r in audit_records if r["agent_name"] == "finance_agent"])
    procurement_count = len([r for r in audit_records if r["agent_name"] == "procurement_agent"])
    check("8 finance_agent records present", finance_count == 8)
    check("3 procurement_agent records present", procurement_count == 3)

    with open(ESCALATION_QUEUE_FILE, "r", encoding="utf-8") as f:
        escalations = json.load(f)
    escalation_agents = {e["agent_name"] for e in escalations}
    check(
        "escalation_queue.json contains tickets from both agents",
        escalation_agents == {"finance_agent", "procurement_agent"},
    )

    print(f"\n{_passed} passed, {_failed} failed")
    if _failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
