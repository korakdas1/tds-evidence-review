"""Deterministic date selection and deliberately provisional treatment proposals."""
import json
import re
from datetime import date, timedelta
from pathlib import Path

from .schema import CUSTOMER, VENDOR, CONFLICT, INSUFFICIENT, OUT, residency

RULES = json.loads(Path(__file__).with_name("rules_v1.json").read_text(encoding="utf-8"))
DATE_PATTERN = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")  # ASCII digits only


def load_act_selection(config, rules=RULES):
    """Validate a versioned Act-selection configuration; raise ValueError rather than guess."""
    try:
        if config["id"] != "act_selection" or not re.fullmatch(r"\d+\.\d+\.\d+", config["version"]):
            raise ValueError("Act selection config needs id act_selection and a semantic version")
        if config["trigger"] != "EARLIER_OF_REQUIRED_DATES" or config["required_dates"] != ["credit_date", "payment_date"]:
            raise ValueError("Only the earlier-of-credit-and-payment trigger is implemented")
        periods = config["periods"]
        if len(periods) < 2 or len({p["act"] for p in periods}) != len(periods):
            raise ValueError("Act periods must name at least two distinct Acts")
        if periods[0]["effective_from"] is not None or periods[-1]["effective_to"] is not None:
            raise ValueError("Act periods must cover all dates without open gaps")
        bounds = []
        for earlier, later in zip(periods, periods[1:]):
            end, start = date.fromisoformat(earlier["effective_to"]), date.fromisoformat(later["effective_from"])
            if start != end + timedelta(days=1) or (bounds and start <= bounds[-1]):
                raise ValueError("Act periods must be ordered, contiguous and non-overlapping")
            bounds.append(start)
        source = [r for r in rules["rules"] if r["id"] == config["source_rule_id"]]
        if len(source) != 1 or source[0]["effective_from"] != periods[-1]["effective_from"]:
            raise ValueError("Act selection boundary must match its cited source rule")
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError("Malformed Act selection config: " + type(exc).__name__) from None
    return dict(config, rule_version="{}@{}".format(config["id"], config["version"]),
                boundaries=bounds)


ACT_SELECTION = load_act_selection(json.loads(
    Path(__file__).with_name("act_selection_v1.json").read_text(encoding="utf-8")))
OLD_ACT = ACT_SELECTION["periods"][0]["act"]
NEW_ACT = ACT_SELECTION["periods"][-1]["act"]
BOUNDARY = ACT_SELECTION["boundaries"][-1]


def select_act(credit_date, payment_date, config=ACT_SELECTION):
    errors, dates = [], []
    for name, value in (("credit_date", credit_date), ("payment_date", payment_date)):
        try:
            if not isinstance(value, str) or not DATE_PATTERN.fullmatch(value):
                raise ValueError()
            dates.append(date.fromisoformat(value))
        except ValueError:
            errors.append(name + " is missing or invalid; use YYYY-MM-DD")
    if errors:
        return {"status": "NEEDS_DATE_REVIEW", "applicable_act": None,
                "trigger_date": None, "validation_failures": errors, "rule_version": config["rule_version"]}
    trigger = min(dates)
    index = sum(trigger >= bound for bound in config["boundaries"])
    return {"status": "RESOLVED", "applicable_act": config["periods"][index]["act"],
            "trigger_date": trigger.isoformat(), "validation_failures": [], "rule_version": config["rule_version"]}


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
