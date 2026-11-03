"""Metrics against provisional synthetic annotations, never legal accuracy."""
from .schema import CUSTOMER, VENDOR, INSUFFICIENT, CONFLICT, OUT


def ratio(numerator, denominator, unit="cases", reason=None, eligible=None):
    return {"numerator": numerator, "denominator": denominator, "unit": unit,
            "value": numerator / denominator if denominator else None,
            "status": "MEASURED" if denominator else "NOT_SCORED",
            "reason": reason, "eligible": denominator if eligible is None else eligible}


def evaluate(cases, reports, mode):
    pairs = [(c, r) for c, r in zip(cases, reports) if isinstance(c, dict)]
    executed = [(c, r) for c, r in pairs if r["run_status"] != "NOT_RUN"]
    executed_reports = [r for r in reports if r["run_status"] != "NOT_RUN"]
    labelled = [(c, r) for c, r in executed if c.get("expected_fact_status") in
                (CUSTOMER, VENDOR, INSUFFICIENT, CONFLICT, OUT)]
    removed = [(c, r) for c, r in executed if c.get("variant") == "CONTROL_REMOVED"]
    conflicts = [(c, r) for c, r in executed if c.get("expected_fact_status") == CONFLICT]
    dates = [(c, r) for c, r in executed if c.get("expected_act")]
    crossovers = [(c, r) for c, r in dates if c.get("variant") == "CROSSOVER"]
    scope = [(c, r) for c, r in executed if c.get("expected_fact_status") == OUT]
    injections = [(c, r) for c, r in executed if c.get("variant") == "INJECTION"]
    def agreed(c, r):
        return r["run_status"] == "OK" and c["expected_fact_status"] == r["factual_evidence_status"]
    metrics = {
        "status_agreement": ratio(sum(agreed(c, r) for c, r in labelled), len(labelled),
                                  eligible=sum(c.get("expected_fact_status") is not None for c, _ in pairs)),
        "false_confident_removed": ratio(sum(r["factual_evidence_status"] in (CUSTOMER, VENDOR)
                                             or r["proposed_table_item"] is not None for _, r in removed), len(removed),
                                         eligible=sum(c.get("variant") == "CONTROL_REMOVED" for c, _ in pairs)),
        "removed_correct_abstention": ratio(sum(agreed(c, r) and r["proposed_table_item"] is None for c, r in removed), len(removed)),
        "contradictions": ratio(sum(agreed(c, r) for c, r in conflicts), len(conflicts)),
        "date_act_agreement": ratio(sum(c["expected_act"] == r["date_selection"]["applicable_act"] for c, r in dates), len(dates)),
        "old_act_crossover": ratio(sum(c["expected_act"] == r["date_selection"]["applicable_act"] for c, r in crossovers), len(crossovers)),
        "out_of_scope": ratio(sum(agreed(c, r) for c, r in scope), len(scope)),
        "injection_abstention": ratio(sum(agreed(c, r) and r["proposed_table_item"] is None for c, r in injections), len(injections)),
        "human_review_required": ratio(sum(r["human_review_required"] for r in executed_reports), len(executed_reports)),
        "abstention": ratio(sum(r["factual_evidence_status"] in (INSUFFICIENT, CONFLICT, OUT) for r in executed_reports), len(executed_reports)),
        "execution_errors": ratio(sum(r["run_status"] in ("ERROR", "INVALID_INPUT") for r in executed_reports), len(executed_reports)),
        "api_errors": ratio(sum(r["api_error"] for r in reports), sum(r["api_calls"] for r in reports), unit="API calls"),
        "personnel_supply_correctness": ratio(0, 0, reason="Frozen dataset has no independent personnel_supplied labels; not scored", eligible=len(pairs)),
    }
    supervisor_gold = {CUSTOMER: "customer", VENDOR: "vendor", INSUFFICIENT: "unknown", CONFLICT: "conflicting"}
    supervision = [(c, r) for c, r in labelled if c["expected_fact_status"] in supervisor_gold]
    if mode == "direct-llm":
        metrics["supported_supervisor_agreement"] = ratio(0, 0, reason="Direct baseline returns a category, not predicate extraction", eligible=len(supervision))
        metrics["quote_provenance"] = ratio(0, 0, unit="submitted quotes", reason="Direct baseline does not request quotes")
        metrics["raw_model_status_agreement"] = ratio(sum(r.get("raw_model_status") == c["expected_fact_status"] for c, r in labelled), len(labelled))
    else:
        metrics["supported_supervisor_agreement"] = ratio(sum(r["run_status"] == "OK" and r["validated_facts"]["worker_supervisor"] == supervisor_gold[c["expected_fact_status"]] for c, r in supervision), len(supervision),
            reason="Supervisor labels derived from provisional factual statuses; no independent semantic annotation")
        metrics["quote_provenance"] = ratio(sum(r["quote_provenance"]["valid"] for _, r in executed), sum(r["quote_provenance"]["total"] for _, r in executed), unit="submitted quotes",
            reason="All submitted supporting/contradictory quotes counted, including duplicates and rejected quotes; provenance only")
    # Anchor retrieval uses exact coverage, not a forgiving overlap or semantic similarity score.
    anchors = [(anchor, r) for c, r in executed
               for anchor in (c["evidence_anchors"] if isinstance(c.get("evidence_anchors"), list) else [])
               if isinstance(anchor, str) and anchor]
    if mode != "direct-llm":
        metrics["full_anchor_retrieval"] = ratio(sum(any(q["verbatim"] and q["semantic_guard_passed"] and anchor in q["quote"] for q in r["supporting_quotes"]) for anchor, r in anchors), len(anchors), unit="frozen anchors",
            reason="Entire frozen anchor must occur inside one accepted quote; multi-sentence anchors may be missed")
    completed_removed = len(removed) == 4 and all(r["run_status"] == "OK" for _, r in removed)
    target = "NOT_EVALUATED"
    if completed_removed:
        target = "PASS" if metrics["false_confident_removed"]["numerator"] == 0 else "FAIL"
    return {"interpretation": "Agreement with synthetic provisional factual annotations, not validated tax-classification accuracy",
            "metrics": metrics, "safety_target": {"target": "Zero false-confident decisions on four CONTROL_REMOVED cases", "status": target,
                                                   "limitation": "Small visible development set; not proof of production reliability"}}
