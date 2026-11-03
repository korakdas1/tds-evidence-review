"""Offline evaluation of frozen synthetic PDF fixtures; never model/Tax accuracy."""
import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from src.document_review import review_pdf_contract
from src.pdf_ingestion import verify_location

FIXTURES = Path(__file__).resolve().parent / "tests/fixtures/pdf_v1"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True, help="Must not already exist")
    args = parser.parse_args(argv)
    manifest = json.loads((FIXTURES / "manifest.json").read_text())
    for item in manifest["fixtures"]:
        if hashlib.sha256((FIXTURES / item["file"]).read_bytes()).hexdigest() != item["sha256"]:
            raise ValueError("Frozen PDF fixture hash mismatch")
    metadata_path = FIXTURES / "transaction.json"
    if hashlib.sha256(metadata_path.read_bytes()).hexdigest() != manifest["transaction_sha256"]:
        raise ValueError("Frozen manual metadata hash mismatch")
    metadata = json.loads(metadata_path.read_text())
    args.output_dir.mkdir(parents=True, exist_ok=False)
    cases, source_checks, invalid_probes = [], [], []
    for item in manifest["fixtures"]:
        # All fixtures stress the contract adapter here, including invoice text with no
        # supervision facts. Invoice-as-separate-document integration has its own tests/demo.
        result = review_pdf_contract(metadata, FIXTURES / item["file"])
        doc = result["documents"]["contract"]
        fragments = [f for i in result["evidence_items"] for o in i["source_mapping"]["occurrences"] for f in o["fragments"]]
        checks = [verify_location(doc, f) for f in fragments]
        source_checks.extend(checks)
        if item["file"] == "supported.pdf" and fragments:
            source = fragments[0]
            for change in ({"page_number":0}, {"page_number":999}, {"start":-1}, {"end":999999},
                           {"start":True}, {"quote":"fabricated"}, {"document_id":"wrong"},
                           {"file_sha256":"wrong"}, {"document_name":"wrong.pdf"},
                           {"context":{"start":0,"end":1,"text":"bad"}}):
                invalid_probes.append(not verify_location(doc, dict(source, **change)))
        cases.append(dict(file=item["file"], expected_extraction_status=item["expected_status"], observed_extraction_status=doc["status"],
                          status_matches=doc["status"] == item["expected_status"], document_issues=doc["issues"],
                          page_issues=[dict(page=p["page_number"], issues=p["issues"]) for p in doc["pages"] if p["issues"]],
                          text_only_factual_status=result["text_analysis"]["factual_evidence_status"],
                          final_factual_status=result["review"]["factual_evidence_status"],
                          document_gate=result["status"], source_items=len(result["evidence_items"]),
                          mapped_items=sum(i["source_mapping"]["status"] == "MAPPED_TO_EXTRACTED_TEXT" for i in result["evidence_items"]),
                          source_fragments_valid=sum(checks), source_fragments_total=len(checks),
                          statutory_proposal=result["review"]["proposed_table_item"], api_calls=result["api_calls"]))
        (args.output_dir / (Path(item["file"]).stem + ".json")).write_text(json.dumps(result, indent=2) + "\n")
    def count(n, d):return dict(numerator=n, denominator=d)
    summary = dict(suite="pdf-fixtures-v1", fixtures_sha256=hashlib.sha256((FIXTURES/"manifest.json").read_bytes()).hexdigest(),
                   implementation_sha256={name:hashlib.sha256((FIXTURES.parents[2]/name).read_bytes()).hexdigest()
                                          for name in ("src/pdf_ingestion.py", "src/document_review.py", "evaluate_pdfs.py")},
                   interpretation="Source-informed synthetic extraction/provenance tests, not independent model or legally validated accuracy.",
                   cases=cases, extraction_status_counts=dict(Counter(c["observed_extraction_status"] for c in cases)),
                   expected_outcomes=count(sum(c["status_matches"] for c in cases),len(cases)),
                   source_fragments_verified=count(sum(source_checks),len(source_checks)),
                   invalid_location_probes_rejected=count(sum(invalid_probes),len(invalid_probes)),
                   mapped_evidence_items=count(sum(c["mapped_items"] for c in cases),sum(c["source_items"] for c in cases)),
                   statutory_proposals_released=count(sum(c["statutory_proposal"] is not None for c in cases),len(cases)),
                   api_calls=sum(c["api_calls"] for c in cases))
    (args.output_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps({k:v for k,v in summary.items() if k != "cases"}, indent=2))
    return 0 if all(c["status_matches"] for c in cases) and all(source_checks) and all(invalid_probes) else 1


if __name__ == "__main__":
    raise SystemExit(main())
