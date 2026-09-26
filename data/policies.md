# Maximus Industries AG — Agent Fabric Policy Reference

This document is the single source of policy truth retrieved by
`fabric/rag.py`. Each `##` section below is treated as one retrievable
unit. Keep numeric thresholds explicit — the agents parse decisions off
these numbers, not off narrative text.

## Finance — Invoice Approval Policy

All incoming invoices are checked against their referencing Purchase
Order (PO) using a three-way match: invoice line items and amount must
agree with the PO's line items and amount.

- **Three-way match must pass.** If the invoice's line items (SKU,
  quantity, unit price) or total amount do not match the PO exactly,
  the invoice is escalated for human review. Do not auto-approve on a
  partial or fuzzy match.
- **Unknown vendor.** If the invoice's `vendor_id` is not present in
  `vendor_master.json`, escalate immediately. Never auto-approve payment
  to an unverified vendor, regardless of amount or match status.
- **Approval threshold: €50,000.** If the three-way match passes and the
  vendor is known and approved, invoices of €50,000 or less are
  auto-approved and routed to payment scheduling. Invoices above €50,000
  require human sign-off even if the match is clean — route to escalation
  with reason "over threshold, requires human sign-off".
- **Escalation routing.** All escalated invoices are sent to the GCC
  (Global Capability Centre) exception queue via
  `request_human_review`, not silently dropped or auto-approved by
  default.

## Procurement — Quote Selection Policy

RFQ (Request for Quote) responses are compared against the item's
historical price index — the benchmark unit/total price Maximus has
paid historically for a comparable item.

- **Auto-select threshold: ±10%.** Auto-select the lowest-priced
  compliant quote and auto-approve the resulting purchase order if that
  quote is within ±10% of the historical price index.
- **Tie-break threshold: 1%.** If two or more quotes are within 1% of
  each other (measured against the lowest quote), do not auto-select.
  Escalate for a human tie-break — an arbitrary pick between
  near-identical quotes is not an acceptable automated decision.
- **Outlier threshold: 15% below benchmark.** If the lowest quote is
  more than 15% below the historical price index, do not treat this as
  an automatic win. Escalate for verification — this pattern more often
  indicates a data error, a scope misunderstanding, or a
  non-compliant/unqualified vendor than a genuine cost saving.
- **Outside the ±10% band but not a 15%+ outlier.** If the lowest quote
  falls outside the ±10% auto-select band but is not low enough to
  trigger the 15% outlier rule, escalate with reason "lowest quote
  outside ±10% policy band" — do not default to auto-approval just
  because no other rule explicitly caught it.
- **Escalation routing.** All escalated RFQs are sent to the GCC
  exception queue via `request_human_review`, identical routing to the
  Finance escalation path.

## Corporate — Management Reporting Policy

Management reporting requests (board decks, KPI dashboards, headcount
and SG&A summaries) are checked against the data sources they depend on
before being auto-generated.

- **Freshness threshold: 7 days.** A data source is considered fresh if
  it was last updated 7 days ago or less. Reports may only be
  auto-generated from sources meeting this threshold.
- **All sources must be available.** If any required data source is
  marked unavailable, do not auto-generate — escalate for manual
  compilation. A report built on a missing source is a report with a
  hole in it, not a report a human should have to catch after the fact.
- **All sources must be fresh.** If any required data source's
  `last_updated_days_ago` exceeds the 7-day freshness threshold,
  escalate — a stale source produces a misleading report even if the
  data is technically present.
- **Auto-generate condition.** Only when every listed data source is
  both available and fresh may the report be auto-generated and routed
  for distribution.
- **Escalation routing.** All escalated report requests are sent to the
  GCC exception queue via `request_human_review`, identical routing to
  the Finance and Procurement escalation paths — the same shared
  approval layer, a third time.

## IT — Service Management / Ticket Triage Policy

IT tickets may only be auto-resolved when three independent conditions
all hold. This function has Maximus's worst enterprise data quality
score (68/100 average, Table 5) and the most fragmented system
landscape (9 ERPs vs. 2 benchmark) of any selected function — the policy
is deliberately stricter here than in Finance, Procurement, or Corporate
to reflect that risk rather than paper over it.

- **Known-issue match required.** The ticket must match a documented
  known issue with an existing runbook. If there is no match, escalate
  for human triage — do not attempt resolution against an undocumented
  problem.
- **Source system data-quality threshold: 75/100.** Even with a known-
  issue match, only auto-resolve if the reporting system's data quality
  score is 75 or higher. Below that, escalate — a matched pattern from
  an unreliable source system is not evidence enough to act on
  automatically. Given the enterprise average is 68/100, most systems
  will fail this bar today; this is expected and intentional, not a bug
  in the policy.
- **Severity guard: 50 affected users.** Regardless of match confidence
  or source data quality, if `affected_users` exceeds 50, escalate. A
  large-scale or business-critical incident always gets human judgment,
  even when the pattern looks routine.
- **Auto-resolve condition.** Only when all three conditions above are
  satisfied — known-issue match, source system quality ≥75, and
  affected_users ≤50 — may the ticket be auto-resolved via its
  documented runbook.
- **Escalation routing.** All escalated tickets are sent to the GCC
  exception queue via `request_human_review`, identical routing to
  every other function's escalation path — the same shared approval
  layer, now serving a fourth agent.
