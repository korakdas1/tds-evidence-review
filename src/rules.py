"""Deterministic date selection and deliberately provisional treatment proposals."""
import json
import re
from datetime import date
from pathlib import Path

from .schema import CUSTOMER, VENDOR, CONFLICT, INSUFFICIENT, OUT, residency

BOUNDARY = date(2026, 4, 1)
OLD_ACT = "Income-tax Act, 1961"
NEW_ACT = "Income-tax Act, 2025"
RULES = json.loads(Path(__file__).with_name("rules_v1.json").read_text(encoding="utf-8"))


def select_act(credit_date, payment_date):
    errors, dates = [], []
    for name, value in (("credit_date", credit_date), ("payment_date", payment_date)):
        try:
            if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                raise ValueError()
            dates.append(date.fromisoformat(value))
        except ValueError:
            errors.append(name + " is missing or invalid; use YYYY-MM-DD")
    if errors:
        return {"status": "NEEDS_DATE_REVIEW", "applicable_act": None,
                "trigger_date": None, "validation_failures": errors}
    trigger = min(dates)
    return {"status": "RESOLVED", "applicable_act": OLD_ACT if trigger < BOUNDARY else NEW_ACT,
            "trigger_date": trigger.isoformat(), "validation_failures": []}


def factual_status(facts):
    supervisor = facts["worker_supervisor"]
    if supervisor == "conflicting" or facts["contradictory_evidence"]:
        return CONFLICT
    if supervisor == "customer" and facts["personnel_supplied"] == "yes":
        return CUSTOMER
    if supervisor == "vendor":
        return VENDOR
    return INSUFFICIENT


def report_rules(record, status, date_result, evidence_failures):
    scope = residency(record.get("payee_residency"))
    reasons = ["Qualified human review is required for any legal mapping or tax treatment.",
               "Contract wording may differ from actual working practices."]
    if scope == "nonresident":
        status = OUT
        reasons.append("Nonresident vendor is outside the resident-payment prototype scope.")
    elif scope == "unknown":
        status = INSUFFICIENT
        reasons.append("Vendor residency must be established.")
    proposal = None
    if date_result["status"] != "RESOLVED":
        reasons.append("Both valid credit and payment dates are required.")
    elif date_result["applicable_act"] == OLD_ACT:
        reasons.append("Old Act selected; old-Act treatment mapping is not implemented.")
    elif (status == CUSTOMER and not evidence_failures and scope == "resident"
          and record.get("payer_type", "").strip().lower() == "indian resident private company"):
        proposal = {
            "reference": "Section 393(1), Table 6(i)",
            "basis": "Section 402(47)(f)",
            "status": "PROVISIONAL_REQUIRES_QUALIFIED_HUMAN_REVIEW",
            "mapping_verification": "NOT_PRACTITIONER_VALIDATED",
            "rule_id": "customer_manpower_candidate",
        }
    if status == VENDOR:
        reasons.append("Vendor supervision alone does not establish professional or technical services.")
    if evidence_failures:
        reasons.append("Extraction/evidence validation failed; no table item may be proposed.")
    applicable = [r for r in RULES["rules"] if r["id"] == "act_transition"]
    if date_result["applicable_act"] == NEW_ACT and scope == "resident":
        applicable += [r for r in RULES["rules"] if r["id"] != "act_transition"]
    return {"factual_evidence_status": status, "proposed_table_item": proposal,
            "human_review_required": True, "review_status": "NEEDS_REVIEW",
            "human_review_reasons": reasons, "legal_sources": applicable,
            "rules_version": RULES["version"],
            "limitations": ["Exact quotations establish provenance, not semantic correctness.",
                            "No final legal determination, withholding authorization, or return filing."]}
