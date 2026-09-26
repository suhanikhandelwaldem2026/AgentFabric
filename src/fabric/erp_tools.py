"""
fabric/erp_tools.py — shared, mocked data-access functions.

Both finance_agent.py and procurement_agent.py call these directly.
Neither agent duplicates this logic or reads data/*.json itself.
"""
from __future__ import annotations

import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"

_invoices_cache: list[dict] | None = None
_pos_cache: list[dict] | None = None
_vendors_cache: list[dict] | None = None
_rfqs_cache: list[dict] | None = None

_payment_counter = 0
_po_counter = 0


def _load(filename: str) -> list[dict]:
    with open(DATA_DIR / filename, "r", encoding="utf-8") as f:
        return json.load(f)


def _invoices() -> list[dict]:
    global _invoices_cache
    if _invoices_cache is None:
        _invoices_cache = _load("invoices.json")
    return _invoices_cache


def _purchase_orders() -> list[dict]:
    global _pos_cache
    if _pos_cache is None:
        _pos_cache = _load("purchase_orders.json")
    return _pos_cache


def _vendors() -> list[dict]:
    global _vendors_cache
    if _vendors_cache is None:
        _vendors_cache = _load("vendor_master.json")
    return _vendors_cache


def _rfqs() -> list[dict]:
    global _rfqs_cache
    if _rfqs_cache is None:
        _rfqs_cache = _load("quotes.json")
    return _rfqs_cache


def get_purchase_order(po_id: str) -> dict | None:
    for po in _purchase_orders():
        if po["po_id"] == po_id:
            return po
    return None


def get_vendor(vendor_id: str) -> dict | None:
    for v in _vendors():
        if v["vendor_id"] == vendor_id:
            return v
    return None


def get_invoice(invoice_id: str) -> dict | None:
    for inv in _invoices():
        if inv["invoice_id"] == invoice_id:
            return inv
    return None


def list_invoices() -> list[dict]:
    return list(_invoices())


def get_rfq(rfq_id: str) -> dict | None:
    for rfq in _rfqs():
        if rfq["rfq_id"] == rfq_id:
            return rfq
    return None


def list_rfqs() -> list[dict]:
    return list(_rfqs())


def check_three_way_match(invoice: dict, po: dict | None) -> dict:
    """
    Compares an invoice against its referencing PO.
    Returns {"matched": bool, "discrepancies": [str, ...]}.
    """
    discrepancies: list[str] = []

    if po is None:
        return {"matched": False, "discrepancies": ["referenced PO not found"]}

    if invoice.get("vendor_id") != po.get("vendor_id"):
        discrepancies.append(
            f"vendor mismatch: invoice={invoice.get('vendor_id')} "
            f"po={po.get('vendor_id')}"
        )

    inv_amount = invoice.get("amount_eur")
    po_amount = po.get("amount_eur")
    if inv_amount != po_amount:
        discrepancies.append(
            f"amount mismatch: invoice={inv_amount} po={po_amount}"
        )

    inv_items = invoice.get("line_items", [])
    po_items = po.get("line_items", [])

    if len(inv_items) != len(po_items):
        discrepancies.append(
            f"line item count mismatch: invoice has {len(inv_items)}, "
            f"po has {len(po_items)}"
        )
    else:
        for i, (inv_item, po_item) in enumerate(zip(inv_items, po_items)):
            for field in ("sku", "qty", "unit_price"):
                if inv_item.get(field) != po_item.get(field):
                    discrepancies.append(
                        f"line item {i} field '{field}' mismatch: "
                        f"invoice={inv_item.get(field)} po={po_item.get(field)}"
                    )

    return {"matched": len(discrepancies) == 0, "discrepancies": discrepancies}


def schedule_payment(invoice_id: str, amount_eur: float, terms: str) -> dict:
    """Mock payment scheduling confirmation."""
    global _payment_counter
    _payment_counter += 1
    return {
        "payment_id": f"PAY-{5000 + _payment_counter}",
        "invoice_id": invoice_id,
        "amount_eur": amount_eur,
        "terms": terms,
        "scheduled_date": "2026-08-14",  # mock fixed date, deterministic for tests
        "status": "scheduled",
    }


def issue_purchase_order(rfq_id: str, vendor_id: str, amount_eur: float) -> dict:
    """Mock PO issuance confirmation for a selected RFQ winner."""
    global _po_counter
    _po_counter += 1
    return {
        "po_id": f"PO-{9000 + _po_counter}",
        "rfq_id": rfq_id,
        "vendor_id": vendor_id,
        "amount_eur": amount_eur,
        "status": "issued",
    }


# ---------------------------------------------------------------------
# Added for Corporate (Wave 5, management reporting) — new entity type,
# purely additive. Nothing above this line was modified to add these.
# ---------------------------------------------------------------------

_report_requests_cache: list[dict] | None = None
_report_counter = 0


def _report_requests() -> list[dict]:
    global _report_requests_cache
    if _report_requests_cache is None:
        _report_requests_cache = _load("report_requests.json")
    return _report_requests_cache


def get_report_request(request_id: str) -> dict | None:
    for req in _report_requests():
        if req["request_id"] == request_id:
            return req
    return None


def list_report_requests() -> list[dict]:
    return list(_report_requests())


def publish_report(request_id: str, report_type: str) -> dict:
    """Mock report publication confirmation."""
    global _report_counter
    _report_counter += 1
    return {
        "report_id": f"RPT-OUT-{6000 + _report_counter}",
        "request_id": request_id,
        "report_type": report_type,
        "status": "published",
    }


# ---------------------------------------------------------------------
# Added for IT (Wave 3, service-management ticket triage) — the
# "new connector type" per the strategy deck's Section 7 build-cost
# table. This is the first agent that needs to correlate data across
# TWO related tables (a ticket's source system AND a known-issue
# library) rather than one flat lookup, which is the concrete reason
# this wave costs more to build than Procurement or Corporate. Purely
# additive — nothing above this line was modified.
# ---------------------------------------------------------------------

_tickets_cache: list[dict] | None = None
_systems_cache: list[dict] | None = None
_known_issues_cache: list[dict] | None = None
_resolution_counter = 0


def _tickets() -> list[dict]:
    global _tickets_cache
    if _tickets_cache is None:
        _tickets_cache = _load("it_tickets.json")
    return _tickets_cache


def _systems() -> list[dict]:
    global _systems_cache
    if _systems_cache is None:
        _systems_cache = _load("systems_registry.json")
    return _systems_cache


def _known_issues() -> list[dict]:
    global _known_issues_cache
    if _known_issues_cache is None:
        _known_issues_cache = _load("known_issues.json")
    return _known_issues_cache


def get_ticket(ticket_id: str) -> dict | None:
    for t in _tickets():
        if t["ticket_id"] == ticket_id:
            return t
    return None


def list_tickets() -> list[dict]:
    return list(_tickets())


def get_system(system_id: str) -> dict | None:
    for s in _systems():
        if s["system_id"] == system_id:
            return s
    return None


def list_systems() -> list[dict]:
    return list(_systems())


def get_known_issue(issue_id: str) -> dict | None:
    for issue in _known_issues():
        if issue["issue_id"] == issue_id:
            return issue
    return None


def resolve_ticket(ticket_id: str, runbook_id: str) -> dict:
    """Mock ticket resolution confirmation via an existing runbook."""
    global _resolution_counter
    _resolution_counter += 1
    return {
        "resolution_id": f"RES-{8000 + _resolution_counter}",
        "ticket_id": ticket_id,
        "runbook_id": runbook_id,
        "status": "resolved",
    }
