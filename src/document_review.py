"""Additive PDF adapter. Manual transaction facts stay manual; provenance is not approval."""
import copy

from .evidence import unknown_facts
from .extraction import OpenRouterClient
from .pdf_ingestion import locate_quote
from .pdf_worker import read_pdf_isolated as read_pdf
from .pipeline import run_batch
from .schema import INPUT_FIELDS, INSUFFICIENT, OUT


def evidence_items(row, document):
    """Every structured quote has a canonical PDF evidence item, with paths to raw diagnostics."""
    groups = {}

    def add(quote, path):
        if not isinstance(quote.get("quote"), str):
            return
        key = (quote.get("fact"), quote.get("value"), quote["quote"])
        item = groups.setdefault(key, dict(fact=key[0], value=key[1], quote=key[2], origins=[],
                                          text_interpretation_status="UNVALIDATED_EXTRACTION"))
        item["origins"].append(path)
        if "semantic_guard_passed" in quote:
            item["text_interpretation_status"] = "SUPPORTED_FACTUAL_EVIDENCE" if quote["semantic_guard_passed"] else "REJECTED_BY_SAFETY_GUARD"
        if "interpretation_state" in quote:
            item["text_interpretation_status"] = quote["interpretation_state"]
        mapping = locate_quote(document, key[2], quote.get("positions"))
        if item.get("source_mapping", {}).get("status") != "UNRESOLVED":
            item["source_mapping"] = mapping

    def walk(node, path):
        if isinstance(node, dict):
            if "quote" in node:
                add(node, path)
            for name, value in node.items():
                if name == "contradictory_evidence" and isinstance(value, list):
                    for index, quote in enumerate(value):
                        if isinstance(quote, str):
                            add(dict(fact="contradiction", value="conflicting", quote=quote),
                                "{}.{}/{}".format(path, name, index))
                else:
                    walk(value, path + "." + name)
        elif isinstance(node, list):
            for index, value in enumerate(node):
                walk(value, path + "/" + str(index))

    walk(row, "text_analysis")
    # Interpretations from the review layer take precedence over generic lexical failure.
    for quote in (row.get("evidence_review") or {}).get("items", []):
        key = (quote.get("fact"), quote.get("value"), quote["quote"])
        groups[key]["text_interpretation_status"] = quote["interpretation_state"]
    for item in groups.values():
        item["human_review_required"] = True
        item["review_status"] = "NEEDS_REVIEW"
        item["may_support_statutory_proposal"] = False
    return list(groups.values())


def review_pdf_contract(metadata, contract_path, invoice_path=None, mode="baseline", client=None):
    if not isinstance(metadata, dict) or "contract_excerpt" in metadata:
        raise ValueError("Supply manual transaction metadata without contract_excerpt")
    if mode not in ("baseline", "hybrid"):
        raise ValueError("PDF adapter supports baseline or explicit factual extraction client")
    contract = read_pdf(contract_path)
    documents = {"contract": contract}
    if invoice_path is not None:
        documents["invoice"] = read_pdf(invoice_path)
    if client is not None and hasattr(client, 'validate_document'):
        client.validate_document(contract)
    record = {name: metadata.get(name) for name in INPUT_FIELDS if name != "contract_excerpt"}
    record["contract_excerpt"] = contract["text"]
    # No implicit environment credentials. The CLI exposes only offline baseline mode.
    batch = run_batch([record], mode, contract["file_sha256"],
                      client=client if client is not None else OpenRouterClient("", ""))
    row = batch["results"][0]
    items = evidence_items(row, contract)
    issues = []
    for role, doc in documents.items():
        if doc["status"] != "EXTRACTED":
            issues.append(role.upper() + "_TEXT_INCOMPLETE_OR_UNRELIABLE")
    if any(i["source_mapping"]["status"] == "UNRESOLVED" for i in items):
        issues.append("SOURCE_MAPPING_UNRESOLVED")
    if any(o.get("cross_page") for i in items for o in i["source_mapping"]["occurrences"]):
        issues.append("CROSS_PAGE_EVIDENCE_REQUIRES_VISUAL_REVIEW")
    review = {key: copy.deepcopy(row[key]) for key in (
        "case_id", "run_status", "date_selection", "factual_evidence_status", "validated_facts",
        "human_review_reasons", "validation_failures", "legal_sources")}
    review.update(review_status="NEEDS_REVIEW", human_review_required=True, proposed_table_item=None,
                  document_issues=issues)
    # PDF reading order/visibility is never certified by text extraction. Phase 4 has
    # no human-confirmation workflow, so it releases no statutory proposal, even for clean text.
    hold_reason = "Inspect PDF reading order, visibility and completeness before any legal proposal."
    review["human_review_reasons"].append(hold_reason)
    row["proposed_table_item"] = None
    row["human_review_reasons"].append(hold_reason)
    if issues:
        review["validated_facts"] = unknown_facts()
        review["validated_facts"]["missing_facts"].append("Reliable complete document text and source mapping.")
        if review["factual_evidence_status"] != OUT:
            review["factual_evidence_status"] = INSUFFICIENT
        review["validation_failures"].extend(issues)
    for item in items:
        item["interpretation_status"] = "DOCUMENT_REVIEW_REQUIRED" if issues else item["text_interpretation_status"]
    return dict(schema_version="pdf-review-v1", status="NEEDS_DOCUMENT_REVIEW" if issues else "TEXT_REVIEW_COMPLETE",
                documents=documents, review=review, text_analysis=row, evidence_items=items,
                manual_field_sources={k:"MANUALLY_PROVIDED_NOT_INFERRED_FROM_PDF" for k in record if k != "contract_excerpt"},
                api_calls=batch["api_calls"],
                limitations=["Page character offsets address extracted Unicode text, not PDF bytes or glyph coordinates.",
                             "Exact mapping is not semantic verification or proof of visual reading order.",
                             "No OCR, automatic legal determination, or statutory proposal release in this PDF path."])
