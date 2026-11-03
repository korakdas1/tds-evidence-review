"""Exact provenance plus conservative lexical checks; not a semantic proof system."""
import re

PERSON = re.compile(r"\b(engineers?|operators?|personnel|assistants?|workers?|staff|manpower|engineering resources)\b", re.I)
ACTOR = re.compile(r"\b(customer|client|recipient|conference organiser|organiser|supplier|vendor|agency|provider)\b", re.I)
CONTROL = re.compile(r"\b(supervis(?:e|es|ing)|direct(?:s|ing)?|instruct(?:s|ing)?|allocates?|assigns?|issues?|monitors?)\b", re.I)
SUPPLY = re.compile(r"\b(assigns?|places?|provides?|suppl(?:y|ies)|makes? available|deploys?)\b", re.I)
NEGATION = re.compile(r"\b(no|not|never|neither|without|cannot|can't|doesn't|isn't|aren't|won't)\b", re.I)
INJECTION = re.compile(
    r"ignore.{0,60}instructions|notice to ai|system\s*(?:prompt|message|:)|"
    r"(?:output|return|mark|classify).{0,50}(?:json|compliant|tds|customer_control|evidence_supports)|"
    r"(?:assistant|developer)\s*:|</?(?:system|assistant)>|override.{0,40}(?:prompt|instructions)", re.I)
FIELDS = {"personnel_supplied", "worker_supervisor", "supporting_quotes", "missing_facts", "contradictory_evidence"}


def unknown_facts():
    return {"personnel_supplied": "unknown", "worker_supervisor": "unknown",
            "supporting_quotes": [], "missing_facts": [], "contradictory_evidence": []}


def sentences(text):
    """Keep original offsets. Full sentence context prevents clipping a negation."""
    for match in re.finditer(r"[^.!?\n]+(?:[.!?]|$)", text):
        raw = match.group()
        trimmed = raw.strip()
        if trimmed:
            start = match.start() + len(raw) - len(raw.lstrip())
            yield trimmed, start, start + len(trimmed)


def quote_positions(contract, quote):
    if not isinstance(quote, str) or not quote.strip():
        return []
    positions, offset = [], 0
    while True:
        start = contract.find(quote, offset)
        if start < 0:
            break
        positions.append({"start": start, "end": start + len(quote)})
        offset = start + 1
    return positions


def sentence_predicates(sentence):
    """A small transparent heuristic. Unknown wording is deliberately left unrecognized."""
    if INJECTION.search(sentence):
        return set()
    # Labels before a colon may contain amendment metadata, not operative negation.
    clause = sentence.rsplit(":", 1)[-1]
    facts = set()
    if re.search(r"\bno (?:individual )?(?:personnel|workers|staff|manpower) (?:are |is )?(?:supplied|provided|assigned)", clause, re.I):
        facts.add(("personnel_supplied", "no"))
    if NEGATION.search(clause):
        return facts
    actor = ACTOR.search(clause)
    person = PERSON.search(clause)
    if actor and person:
        supply = SUPPLY.search(clause, actor.end())
        if (actor.group().lower() in ("supplier", "vendor", "agency", "provider")
                and supply and supply.start() < person.start()
                and not re.search(r"\b(tasks?|duties|bins|tickets?|shifts?|rosters?)\b", clause[supply.end():person.start()], re.I)):
            facts.add(("personnel_supplied", "yes"))
    if actor:
        action = CONTROL.search(clause, actor.end())
        # Require a people object following the action, or an explicit possessive work reference.
        people_object = action and (PERSON.search(clause, action.end()) or
                                    re.search(r"\b(?:their|each operator's) (?:work|tasks|shifts)\b", clause[action.end():], re.I))
        quality_only = re.search(r"\b(?:only|solely)\b.{0,40}\b(?:outputs?|outcomes?|quality|results?|deliverables?)\b", clause, re.I)
        if action:
            tail = clause[action.end():]
            # Assigning people to a site is supply, not assigning their daily work.
            if action.group().lower().startswith("assign") and not re.search(r"\b(tasks?|duties|bins|tickets?|shifts?|rosters?|work)\b", tail, re.I):
                people_object = False
            if re.match(r"\s+(?:the\s+)?(?:quality|outputs?|outcomes?|results?|deliverables?|service levels?)\b", tail, re.I):
                quality_only = True
        conditional = re.search(r"\b(?:if|unless|might|could|would)\b", clause, re.I)
        if action and people_object and not quality_only and not conditional:
            supervisor = "customer" if actor.group().lower() in (
                "customer", "client", "recipient", "conference organiser", "organiser") else "vendor"
            facts.add(("worker_supervisor", supervisor))
    return facts


def lexical_extract(contract):
    facts = unknown_facts()
    values = {"personnel_supplied": set(), "worker_supervisor": set()}
    for sentence, _, _ in sentences(contract):
        for field, value in sorted(sentence_predicates(sentence)):
            values[field].add(value)
            facts["supporting_quotes"].append({"fact": field, "value": value, "quote": sentence})
    supplied = values["personnel_supplied"]
    control = values["worker_supervisor"]
    if len(supplied) == 1:
        facts["personnel_supplied"] = next(iter(supplied))
    if len(control) == 1:
        facts["worker_supervisor"] = next(iter(control))
    if len(control) > 1 or len(supplied) > 1:
        facts["worker_supervisor"] = "conflicting"
        facts["contradictory_evidence"] = [q["quote"] for q in facts["supporting_quotes"]]
    if not control:
        facts["missing_facts"].append("Who supervises, controls or directs individual workers?")
    if not supplied:
        facts["missing_facts"].append("Whether personnel are supplied to the recipient.")
    return facts


def extraction_errors(value):
    if not isinstance(value, dict) or set(value) != FIELDS:
        return ["Extraction must contain exactly the five factual schema fields"]
    errors = []
    if value["personnel_supplied"] not in ("yes", "no", "unknown"):
        errors.append("Invalid personnel_supplied")
    if value["worker_supervisor"] not in ("customer", "vendor", "unknown", "conflicting"):
        errors.append("Invalid worker_supervisor")
    for name in ("missing_facts", "contradictory_evidence"):
        if not isinstance(value[name], list) or any(not isinstance(x, str) or not x.strip() for x in value[name]):
            errors.append(name + " must be a list of nonempty strings")
    quotes = value["supporting_quotes"]
    if not isinstance(quotes, list):
        errors.append("supporting_quotes must be a list")
    else:
        for q in quotes:
            if (not isinstance(q, dict) or set(q) != {"fact", "value", "quote"}
                    or not all(isinstance(v, str) and v.strip() for v in q.values())
                    or q.get("fact") not in ("personnel_supplied", "worker_supervisor")
                    or q.get("value") not in ("yes", "no", "customer", "vendor")):
                errors.append("Malformed supporting quote")
    return errors


def validate_evidence(contract, extraction):
    errors = extraction_errors(extraction)
    if errors:
        return {"facts": unknown_facts(), "quotes": [], "validation_failures": errors,
                "provenance_valid": 0, "provenance_total": 0}
    facts = {**extraction, "supporting_quotes": [], "missing_facts": list(extraction["missing_facts"])}
    checked, supported = [], set()
    all_quotes = list(extraction["supporting_quotes"])
    all_quotes += [{"fact": "contradiction", "value": "conflicting", "quote": q}
                   for q in extraction["contradictory_evidence"]]
    for quote in all_quotes:
        positions = quote_positions(contract, quote["quote"])
        # Evaluate all full sentences touched by the quote, never the clipped quote alone.
        predicates = set()
        for position in positions:
            for sentence, start, end in sentences(contract):
                if start < position["end"] and end > position["start"]:
                    # Also require the quote itself to contain the predicate. A lone word
                    # from a true sentence is insufficient evidence for the full fact.
                    predicates |= sentence_predicates(sentence) & sentence_predicates(quote["quote"])
        semantic_ok = ((quote["fact"], quote["value"]) in predicates if quote["fact"] != "contradiction" else bool(predicates))
        item = {**quote, "positions": positions, "verbatim": bool(positions),
                "semantic_guard_passed": semantic_ok}
        checked.append(item)
        if not positions:
            errors.append("Quote not found verbatim in contract")
        elif not semantic_ok:
            errors.append("Quote does not pass conservative factual support check")
        elif quote["fact"] != "contradiction":
            supported.add((quote["fact"], quote["value"]))
            facts["supporting_quotes"].append(quote)
    for field in ("personnel_supplied", "worker_supervisor"):
        value = facts[field]
        if value not in ("unknown", "conflicting") and (field, value) not in supported:
            errors.append("Unsupported asserted fact: " + field)
            facts[field] = "unknown"
    controls = {v for f, v in supported if f == "worker_supervisor"}
    supplies = {v for f, v in supported if f == "personnel_supplied"}
    conflict = len(controls) > 1 or len(supplies) > 1
    if extraction["worker_supervisor"] == "conflicting" or extraction["contradictory_evidence"]:
        if not conflict:
            errors.append("Claimed contradiction lacks opposing supported predicates")
            facts["worker_supervisor"] = "unknown"
            facts["contradictory_evidence"] = []
    if conflict:
        facts["worker_supervisor"] = "conflicting"
        facts["contradictory_evidence"] = [q["quote"] for q in facts["supporting_quotes"]]
    # Catch omitted decisive clauses within the deliberately limited lexical vocabulary.
    observed = lexical_extract(contract)
    context_findings = []
    if observed["worker_supervisor"] == "conflicting":
        if not conflict:
            errors.append("Extraction omitted contradictory control evidence found in full contract")
            context_findings = [dict(q, positions=quote_positions(contract, q["quote"]),
                                     origin="deterministic_full_contract_check")
                                for q in observed["supporting_quotes"]]
        facts["worker_supervisor"] = "conflicting"
        facts["contradictory_evidence"] = observed["contradictory_evidence"]
    if INJECTION.search(contract):
        errors.append("Potential embedded model instruction detected; route for review")
    # Any failure blocks confident factual outputs as well as table-item proposals.
    if errors and facts["worker_supervisor"] != "conflicting":
        facts["worker_supervisor"] = "unknown"
    if facts["worker_supervisor"] == "unknown":
        facts["missing_facts"].append("Reliable evidence of individual-worker supervision/control.")
    if facts["personnel_supplied"] == "unknown":
        facts["missing_facts"].append("Reliable evidence of personnel supply.")
    facts["missing_facts"] = list(dict.fromkeys(facts["missing_facts"]))
    return {"facts": facts, "quotes": checked, "validation_failures": list(dict.fromkeys(errors)),
            "context_findings": context_findings,
            "provenance_valid": sum(q["verbatim"] for q in checked),
            "provenance_total": len(checked)}
