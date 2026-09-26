"""
tests/test_fabric.py — Phase 2 acceptance tests.

Runnable directly: `python3 tests/test_fabric.py`
No pytest dependency — plain asserts, prints PASS/FAIL per check.
Zero API calls made anywhere in this file.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from fabric import erp_tools, rag, approval_tool  # noqa: E402

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

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
    """Clean slate for the parts of this test that assert exact counts."""
    for f in (DATA_DIR / "audit_log.json", DATA_DIR / "escalation_queue.json"):
        if f.exists():
            f.unlink()


def main():
    print("== erp_tools: vendor / PO / invoice / RFQ lookups ==")
    known_vendor = erp_tools.get_vendor("V-1001")
    check("known vendor resolves", known_vendor is not None and known_vendor["vendor_id"] == "V-1001")
    unknown_vendor = erp_tools.get_vendor("V-9999")
    check("unknown vendor returns None", unknown_vendor is None)

    known_po = erp_tools.get_purchase_order("PO-3001")
    check("known PO resolves", known_po is not None and known_po["po_id"] == "PO-3001")
    unknown_po = erp_tools.get_purchase_order("PO-0000")
    check("unknown PO returns None", unknown_po is None)

    known_invoice = erp_tools.get_invoice("INV-2001")
    check("known invoice resolves", known_invoice is not None)
    unknown_invoice = erp_tools.get_invoice("INV-0000")
    check("unknown invoice returns None", unknown_invoice is None)

    all_invoices = erp_tools.list_invoices()
    check("list_invoices returns 8 records", len(all_invoices) == 8)

    known_rfq = erp_tools.get_rfq("RFQ-4001")
    check("known RFQ resolves", known_rfq is not None)
    unknown_rfq = erp_tools.get_rfq("RFQ-0000")
    check("unknown RFQ returns None", unknown_rfq is None)

    all_rfqs = erp_tools.list_rfqs()
    check("list_rfqs returns 3 records", len(all_rfqs) == 3)

    print("\n== erp_tools: three-way match ==")
    clean_invoice = erp_tools.get_invoice("INV-2001")
    clean_po = erp_tools.get_purchase_order(clean_invoice["po_id"])
    clean_result = erp_tools.check_three_way_match(clean_invoice, clean_po)
    check("clean invoice (INV-2001) matches", clean_result["matched"] is True)
    check("clean invoice has zero discrepancies", len(clean_result["discrepancies"]) == 0)

    mismatch_invoice = erp_tools.get_invoice("INV-2006")
    mismatch_po = erp_tools.get_purchase_order(mismatch_invoice["po_id"])
    mismatch_result = erp_tools.check_three_way_match(mismatch_invoice, mismatch_po)
    check("mismatched invoice (INV-2006) fails match", mismatch_result["matched"] is False)
    check("mismatched invoice reports at least one discrepancy", len(mismatch_result["discrepancies"]) > 0)

    print("\n== rag: policy retrieval distinguishes Finance vs Procurement ==")
    finance_section = rag.retrieve_policy("three-way match threshold")
    check(
        "Finance query returns Finance section",
        "Finance" in finance_section and "€50,000" in finance_section,
    )
    check(
        "Finance query does NOT return Procurement section",
        "Tie-break threshold" not in finance_section,
    )

    procurement_section = rag.retrieve_policy("quote selection tie-break")
    check(
        "Procurement query returns Procurement section",
        "Procurement" in procurement_section and "tie-break" in procurement_section.lower(),
    )
    check(
        "Procurement query does NOT return Finance section",
        "Approval threshold: €50,000" not in procurement_section,
    )

    print("\n== approval_tool: shared audit log across two different agent_names ==")
    reset_audit_files()

    rec1 = approval_tool.log_decision(
        agent_name="finance_agent",
        entity_type="invoice",
        entity_id="INV-2001",
        decision="auto_approve",
        reason="clean match, under threshold",
        amount_eur=12500.00,
    )
    check("log_decision (finance) returns the written record", rec1["agent_name"] == "finance_agent")

    rec2 = approval_tool.log_decision(
        agent_name="procurement_agent",
        entity_type="rfq",
        entity_id="RFQ-4001",
        decision="auto_approve",
        reason="lowest quote within 5% of benchmark",
        amount_eur=97000.00,
    )
    check("log_decision (procurement) returns the written record", rec2["agent_name"] == "procurement_agent")

    with open(DATA_DIR / "audit_log.json", "r", encoding="utf-8") as f:
        audit_records = json.load(f)

    agent_names_present = {r["agent_name"] for r in audit_records}
    check(
        "audit_log.json contains BOTH agent_name values in the SAME file",
        agent_names_present == {"finance_agent", "procurement_agent"},
    )
    check("audit_log.json has exactly 2 records after 2 calls", len(audit_records) == 2)

    print("\n== approval_tool: escalation queue ==")
    ticket = approval_tool.request_human_review(
        agent_name="finance_agent",
        entity_type="invoice",
        entity_id="INV-2005",
        reason="over threshold, requires human sign-off",
    )
    check("request_human_review returns pending_review status", ticket["status"] == "pending_review")
    check("request_human_review returns a review_ticket_id", ticket["review_ticket_id"].startswith("GCC-"))

    with open(DATA_DIR / "escalation_queue.json", "r", encoding="utf-8") as f:
        escalations = json.load(f)
    check("escalation_queue.json has exactly 1 record", len(escalations) == 1)
    check(
        "escalation record has correct entity_id",
        escalations[0]["entity_id"] == "INV-2005",
    )

    print(f"\n{_passed} passed, {_failed} failed")
    if _failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
