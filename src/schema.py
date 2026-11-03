"""Input adapter and benchmark integrity checks. Never rewrites the dataset."""
import hashlib
import json
from collections import Counter
from pathlib import Path

CUSTOMER = "EVIDENCE_SUPPORTS_CUSTOMER_DIRECTED_MANPOWER"
VENDOR = "EVIDENCE_INDICATES_VENDOR_DIRECTED_SERVICE"
INSUFFICIENT = "INSUFFICIENT_TO_ESTABLISH_CONTROL"
CONFLICT = "CONFLICTING_EVIDENCE"
OUT = "OUT_OF_SCOPE"
STATUSES = (CUSTOMER, VENDOR, INSUFFICIENT, CONFLICT, OUT)
ROOT = Path(__file__).resolve().parent.parent
BENCHMARK = ROOT / "tresata_adversarial_cases.json"
MANIFEST = ROOT / "benchmark_manifest.json"
INPUT_FIELDS = ("id", "invoice_description", "contract_excerpt", "payer_type",
                "payee_residency", "payee_legal_form", "credit_date", "payment_date")


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key: " + key)
        result[key] = value
    return result


def _invalid_constant(value):
    raise ValueError("Non-finite JSON value: " + value)


def parse_json(text):
    return json.loads(text, object_pairs_hook=_unique_object,
                      parse_constant=_invalid_constant)


def load_input(path):
    raw = Path(path).read_bytes()
    data = parse_json(raw.decode("utf-8"))
    cases = data.get("cases") if isinstance(data, dict) else data
    if not isinstance(cases, list) or not cases:
        raise ValueError("Input must be a nonempty list or an object with a nonempty cases list")
    return data, cases, hashlib.sha256(raw).hexdigest()


def input_errors(record):
    if not isinstance(record, dict):
        return ["Record must be an object"]
    errors = []
    for name in INPUT_FIELDS:
        # Dates are separately validated by the rules engine, including absent dates.
        if name in ("credit_date", "payment_date"):
            continue
        value = record.get(name)
        if not isinstance(value, str) or not value.strip():
            errors.append(name + " must be a nonempty string")
    return errors


def transaction_input(record):
    """Only these fields may reach an extractor; no IDs encoding labels or annotations."""
    return {key: record.get(key) for key in INPUT_FIELDS if key != "id"}


def residency(value):
    if not isinstance(value, str):
        return "unknown"
    value = value.strip().lower()
    if value in ("india resident", "indian resident", "resident", "resident in india"):
        return "resident"
    if value in ("non-resident", "nonresident", "non resident"):
        return "nonresident"
    return "unknown"


def validate_benchmark(path=BENCHMARK):
    from .rules import select_act
    data, cases, digest = load_input(path)
    manifest = parse_json(MANIFEST.read_text(encoding="utf-8"))
    failures = []
    if digest != manifest["sha256"]:
        return {"status": "INVALID", "sha256": digest, "case_count": len(cases),
                "failures": ["Frozen benchmark SHA-256 mismatch; do not evaluate changed labels"]}
    if not isinstance(data, dict) or set(data.get("expected_statuses", [])) != set(STATUSES):
        failures.append("Missing or invalid expected_statuses")
    if len(cases) != 16:
        failures.append("Expected exactly 16 cases")
    ids, variants, scenarios, anchor_count = [], Counter(), {}, 0
    for index, case in enumerate(cases):
        errors = input_errors(case)
        if errors:
            failures.extend("Record {}: {}".format(index, err) for err in errors)
            continue
        ids.append(case["id"])
        variants[case.get("variant")] += 1
        if case.get("synthetic") is not True:
            failures.append(case["id"] + ": missing synthetic flag")
        if case.get("expected_fact_status") not in STATUSES:
            failures.append(case["id"] + ": invalid expected status")
        act = select_act(case.get("credit_date"), case.get("payment_date"))
        if act["status"] != "RESOLVED" or act["applicable_act"] != case.get("expected_act"):
            failures.append(case["id"] + ": date / expected Act mismatch")
        anchors = case.get("evidence_anchors")
        if not isinstance(anchors, list):
            failures.append(case["id"] + ": anchors must be a list")
        else:
            for quote in anchors:
                anchor_count += 1
                if not isinstance(quote, str) or not quote or quote not in case["contract_excerpt"]:
                    failures.append(case["id"] + ": invalid evidence anchor")
        if case.get("variant") in ("CUSTOMER_CONTROL", "VENDOR_CONTROL", "CONTROL_REMOVED"):
            scenarios.setdefault(case.get("scenario"), {})[case["variant"]] = case
    if len(set(ids)) != len(ids):
        failures.append("Duplicate case IDs")
    if variants != Counter(CUSTOMER_CONTROL=4, VENDOR_CONTROL=4, CONTROL_REMOVED=4,
                           CONFLICT=1, INJECTION=1, CROSSOVER=1, OUT_OF_SCOPE=1):
        failures.append("Unexpected variant counts")
    if len(scenarios) != 4:
        failures.append("Expected four matched scenario groups")
    for scenario, group in scenarios.items():
        if len(group) != 3:
            failures.append(str(scenario) + ": incomplete matched group")
            continue
        if len({c["invoice_description"] for c in group.values()}) != 1:
            failures.append(str(scenario) + ": invoices differ in matched group")
        base = group["CONTROL_REMOVED"]["contract_excerpt"]
        if not all(c["contract_excerpt"].startswith(base) for c in group.values()):
            failures.append(str(scenario) + ": removal excerpt is not common prefix")
    return {"status": "VALID" if not failures else "INVALID", "sha256": digest,
            "case_count": len(cases), "anchor_count": anchor_count,
            "variants": dict(variants), "failures": failures,
            "labels": "Synthetic provisional factual annotations; not practitioner validated"}
