"""
tests/test_demo.py — Phase 5 acceptance tests.

Runnable directly: `python3 tests/test_demo.py`
Runs with USE_LLM=false — zero API calls.
"""
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("USE_LLM", "false")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from demo import (  # noqa: E402
    run_finance_batch,
    run_procurement_batch,
    run_corporate_batch,
    run_it_batch,
    reset_audit_files,
)

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


def main():
    reset_audit_files()

    finance_results = run_finance_batch()
    procurement_results = run_procurement_batch()
    corporate_results = run_corporate_batch()
    it_results = run_it_batch()

    print("== Demo: batch sizes ==")
    check("finance batch has 8 results", len(finance_results) == 8)
    check("procurement batch has 3 results", len(procurement_results) == 3)
    check("corporate batch has 4 results", len(corporate_results) == 4)
    check("IT batch has 4 results", len(it_results) == 4)

    print("\n== Demo: decision split matches expected splits ==")
    finance_auto = len([r for r in finance_results if r["decision"] == "auto_approve"])
    finance_escalate = len([r for r in finance_results if r["decision"] == "escalate"])
    check("finance: 5 auto_approve", finance_auto == 5)
    check("finance: 3 escalate", finance_escalate == 3)

    proc_auto = len([r for r in procurement_results if r["decision"] == "auto_approve"])
    proc_escalate = len([r for r in procurement_results if r["decision"] == "escalate"])
    check("procurement: 1 auto_approve", proc_auto == 1)
    check("procurement: 2 escalate", proc_escalate == 2)

    corp_auto = len([r for r in corporate_results if r["decision"] == "auto_approve"])
    corp_escalate = len([r for r in corporate_results if r["decision"] == "escalate"])
    check("corporate: 2 auto_approve", corp_auto == 2)
    check("corporate: 2 escalate", corp_escalate == 2)

    it_auto = len([r for r in it_results if r["decision"] == "auto_approve"])
    it_escalate = len([r for r in it_results if r["decision"] == "escalate"])
    check("IT: 1 auto_approve", it_auto == 1)
    check("IT: 3 escalate", it_escalate == 3)

    print("\n== Demo: audit log has exactly 19 records after a clean run ==")
    with open(AUDIT_LOG_FILE, "r", encoding="utf-8") as f:
        audit_records = json.load(f)
    check("19 total audit records", len(audit_records) == 19)

    finance_count = len([r for r in audit_records if r["agent_name"] == "finance_agent"])
    procurement_count = len([r for r in audit_records if r["agent_name"] == "procurement_agent"])
    corporate_count = len([r for r in audit_records if r["agent_name"] == "corporate_agent"])
    it_count = len([r for r in audit_records if r["agent_name"] == "it_agent"])
    check(
        "split 8/3/4/4 by agent_name",
        finance_count == 8 and procurement_count == 3
        and corporate_count == 4 and it_count == 4,
    )

    print("\n== Demo: escalation queue has 10 tickets (3+2+2+3) ==")
    with open(ESCALATION_QUEUE_FILE, "r", encoding="utf-8") as f:
        escalations = json.load(f)
    check("10 total escalation tickets", len(escalations) == 10)

    print(f"\n{_passed} passed, {_failed} failed")
    if _failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
