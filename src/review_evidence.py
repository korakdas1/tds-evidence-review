"""Separate quote provenance, interpretation confidence, and review-only AI leads.

Suggestions never enter validated facts. The existing conservative validator remains
the sole automatic promotion gate; this module is not a second semantic verifier.
"""
from .evidence import (CONDITIONAL, INJECTION, INOPERATIVE, NEGATION, SERVICE_OBJECT,
                       sentences, validate_evidence)

SUPPORTED = "SUPPORTED_FACTUAL_EVIDENCE"
SUGGESTED = "AI_SUGGESTED_REQUIRING_REVIEW"
CONTRADICTORY = "CONTRADICTORY_EVIDENCE"
INSUFFICIENT = "INSUFFICIENT_EVIDENCE"
REJECTED = "REJECTED_BY_SAFETY_GUARD"


def review_evidence(contract, extraction):
    validated = validate_evidence(contract, extraction)
    items = []
    for quote in validated["quotes"]:
        context = [dict(text=text, start=start, end=end)
                   for text, start, end in sentences(contract)
                   if any(start < p["end"] and end > p["start"] for p in quote["positions"])]
        reasons = []
        if not quote["verbatim"]:
            reasons.append("QUOTE_NOT_FOUND")
        if INJECTION.search(contract):
            reasons.append("EMBEDDED_INSTRUCTION")
        if quote["fact"] != "contradiction":
            asserted = extraction[quote["fact"]]
            if quote["value"] != asserted and not (
                    quote["fact"] == "worker_supervisor" and asserted == "conflicting"):
                reasons.append("ASSERTION_QUOTE_MISMATCH")
        # These are conservative vetoes, not proof that the AI interpretation is false.
        # Inspect full surrounding sentences: clipping must not remove a prohibition.
        for pattern, reason in ((NEGATION, "NEGATED_CONTEXT"),
                                (INOPERATIVE, "INOPERATIVE_CONTEXT"),
                                (CONDITIONAL, "CONDITIONAL_CONTEXT")):
            if any(pattern.search(c["text"]) for c in context):
                reasons.append(reason)
        if (not quote["semantic_guard_passed"] and quote["fact"] != "personnel_supplied"
                and any(SERVICE_OBJECT.search(c["text"]) for c in context)):
            reasons.append("POSSIBLE_SERVICE_OUTCOME_NOT_WORKER_CONTROL")
        if reasons:
            state = REJECTED
        elif quote["semantic_guard_passed"]:
            state = SUPPORTED
        else:
            state = SUGGESTED
            reasons.append("EXACT_SOURCE_BUT_INTERPRETATION_NOT_VERIFIED")
        items.append(dict(quote, interpretation_state=state, review_reasons=reasons,
                          surrounding_context=context,
                          automatic_promotion_allowed=state == SUPPORTED))
    suggested = sum(i["interpretation_state"] == SUGGESTED for i in items)
    facts = validated["facts"]
    if any(i["interpretation_state"] == REJECTED for i in items):
        validated["validation_failures"].append("Review-layer safety veto; no statutory candidate")
        if facts["worker_supervisor"] != "conflicting":
            facts["worker_supervisor"] = "unknown"
        facts["missing_facts"] = list(dict.fromkeys(
            facts["missing_facts"] + ["Resolve rejected evidence before relying on the asserted control."]))
    if facts["worker_supervisor"] == "conflicting":
        state = CONTRADICTORY
    elif suggested:
        state = SUGGESTED
    elif (not validated["validation_failures"] and facts["personnel_supplied"] == "yes"
          and facts["worker_supervisor"] in ("customer", "vendor")):
        state = SUPPORTED
    else:
        state = INSUFFICIENT
    validated["evidence_review"] = {
        "policy_version": "phase3-review-v1", "state": state, "items": items,
        "suggested_quote_count": suggested,
        "unverified_contradiction": bool(extraction.get("contradictory_evidence"))
        and state != CONTRADICTORY if isinstance(extraction, dict) else False,
        "requires_human_review": True,
        "limitation": "Exact-source AI suggestions are leads, not verified facts. Only validated_facts reach legal rules."
    }
    return validated
