"""Offline PDF contract review with page provenance; optional invoice text stays separate."""
import argparse
import json
import sys
from pathlib import Path

from src.document_review import review_pdf_contract
from src.schema import parse_json

FIXTURES = Path(__file__).resolve().parent / "tests/fixtures/pdf_v1"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path)
    parser.add_argument("--metadata", type=Path, help="One manual transaction JSON object; no contract_excerpt")
    parser.add_argument("--invoice", type=Path, help="Optional invoice PDF for inspection, not field inference")
    parser.add_argument("--output", type=Path, help="New JSON file only; existing files are never overwritten")
    args = parser.parse_args(argv)
    if (args.contract is None) != (args.metadata is None) or args.invoice and args.contract is None:
        parser.error("Custom PDFs require both --contract and --metadata; no transaction facts are inferred.")
    try:
        metadata = parse_json((args.metadata or FIXTURES / "transaction.json").read_text(encoding="utf-8"))
        report = review_pdf_contract(metadata, args.contract or FIXTURES / "supported.pdf", args.invoice)
        if args.output:
            if args.output.suffix.lower() != ".json":
                raise ValueError("Output must be JSON")
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open("x", encoding="utf-8") as stream:
                json.dump(report, stream, indent=2, ensure_ascii=True)
                stream.write("\n")
        print("PDF evidence review - offline; no OCR or model calls")
        print("Transaction fields are manual; source mapping is not legal validation.")
        for role, doc in report["documents"].items():
            print("{}: {} | {} | {} pages".format(role.title(), json.dumps(doc["name"]), doc["status"], len(doc["pages"])))
            print("  Document ID: " + str(doc["document_id"]))
            for issue in doc["issues"]:
                print("  Review reason: " + issue)
            for page in doc["pages"]:
                if page["issues"]:
                    print("  Page {}: {}".format(page["page_number"], ", ".join(page["issues"])))
        print("Factual finding: " + report["review"]["factual_evidence_status"])
        for item in report["evidence_items"]:
            if item["fact"] not in ("personnel_supplied", "worker_supervisor"):
                continue
            print("  {}={} | {} | {}".format(item["fact"], item["value"], item["interpretation_status"], item["source_mapping"]["status"]))
            for occurrence in item["source_mapping"]["occurrences"]:
                for fragment in occurrence["fragments"]:
                    print("    Page {} [{}:{}]: {}".format(fragment["page_number"], fragment["start"], fragment["end"], json.dumps(fragment["quote"])))
        print("Human review: REQUIRED; statutory proposal: WITHHELD pending PDF visual review.")
        if report["review"]["document_issues"]:
            print("Document review: " + ", ".join(report["review"]["document_issues"]))
        return 0 if report["status"] == "TEXT_REVIEW_COMPLETE" and report["review"]["run_status"] == "OK" else 2
    except (OSError, ValueError, TypeError):
        print("PDF demo input/output error: use valid local metadata and a new output path; existing files are not overwritten.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
