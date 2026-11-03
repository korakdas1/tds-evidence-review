"""Versioned factual evaluation accounting; never infer legal accuracy or missing measurements."""
from collections import Counter
import hashlib
import math
from pathlib import Path

from .evaluation import ratio
from .schema import CUSTOMER, VENDOR, INSUFFICIENT, CONFLICT, OUT, STATUSES, input_errors, load_input, parse_json

ROOT = Path(__file__).resolve().parent.parent
CONFIDENT = (CUSTOMER, VENDOR)
METHODS = ('baseline', 'direct-llm', 'hybrid')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def known_datasets():
    original = parse_json((ROOT / 'benchmark_manifest.json').read_text())
    v2 = parse_json((ROOT / 'challenge_v2_manifest.json').read_text())
    v3 = parse_json((ROOT / 'phase3_manifest.json').read_text())
    return {original['filename']: original['sha256'], v2['filename']: v2['sha256'],
            'tresata_challenge_v3.json': v3['files']['tresata_challenge_v3.json']}


def validate_dataset(path, expected_sha=None):
    data, cases, digest = load_input(path)
    expected = known_datasets().get(Path(path).name, expected_sha)
    if not expected or digest != expected:
        raise ValueError('Dataset hash does not match a frozen manifest or explicit --input-sha256')
    ids = set()
    for case in cases:
        if input_errors(case):
            raise ValueError('Invalid transaction input')
        if case['id'] in ids or case.get('expected_fact_status') not in STATUSES:
            raise ValueError('Duplicate case ID or invalid expected factual status')
        ids.add(case['id'])
        anchors = case.get('evidence_anchors')
        if not isinstance(anchors, list) or any(not isinstance(q, str) or not q or q not in case['contract_excerpt'] for q in anchors):
            raise ValueError('Evidence anchor is not an exact nonempty contract passage')
    if isinstance(data, dict) and data.get('schema') == 'tds-practitioner-cases-v1':
        validate_practitioner(data)
        origin = 'DECLARED_PRACTITIONER_LABELS_NOT_INDEPENDENTLY_AUTHENTICATED'
    else:
        if not all(c.get('synthetic') is True for c in cases):
            raise ValueError('Other input must be explicitly synthetic or follow practitioner schema')
        origin = 'SYNTHETIC_DEVELOPMENT_NOT_INDEPENDENT_HOLDOUT'
    return cases, digest, origin


def validate_practitioner(data):
    process = data.get('annotation_process')
    if not isinstance(process, dict):
        raise ValueError('Practitioner annotation process is required')
    for key in ('reviewer_reference', 'qualification_assertion', 'labelled_at', 'source_permission', 'conflict_resolution'):
        if not isinstance(process.get(key), str) or not process[key].strip():
            raise ValueError('Missing practitioner provenance field: ' + key)
    if process.get('model_outputs_hidden_during_labelling') is not True:
        raise ValueError('Independent label collection requires hiding model outputs')
    for case in data['cases']:
        facts = case.get('expected_facts')
        if not isinstance(facts, dict) or set(facts) != {'personnel_supplied', 'worker_supervisor'}:
            raise ValueError('Practitioner cases require separate factual predicate labels')
        if facts['personnel_supplied'] not in ('yes','no','unknown') or facts['worker_supervisor'] not in ('customer','vendor','unknown','conflicting'):
            raise ValueError('Invalid predicate label')
        annotations = case.get('evidence_annotations')
        if not isinstance(annotations, list):
            raise ValueError('Evidence annotations must be a list')
        covered = set()
        for a in annotations:
            if not isinstance(a, dict) or a.get('fact') not in facts or a.get('value') != facts[a['fact']]:
                raise ValueError('Annotation does not match predicate label')
            start, end, quote = a.get('start'), a.get('end'), a.get('quote')
            if (type(start) is not int or type(end) is not int or not 0 <= start < end <= len(case['contract_excerpt'])
                    or not isinstance(quote, str) or case['contract_excerpt'][start:end] != quote):
                raise ValueError('Annotation offsets/quote do not match original contract')
            covered.add(a['fact'])
        for fact, value in facts.items():
            if value != 'unknown' and fact not in covered:
                raise ValueError('Every asserted predicate needs an exact labelled anchor')
        if not isinstance(case.get('annotation_rationale'), str) or not case['annotation_rationale'].strip():
            raise ValueError('Annotation rationale is required, including justified abstentions')


def _number(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def metrics(cases, rows, method, kind):
    by_id = {c['id']: c for c in cases}
    if len(rows) != len(cases) or len({r['case_id'] for r in rows}) != len(rows) or set(r['case_id'] for r in rows) != set(by_id):
        raise ValueError('Reports must align exactly by case ID, never by list position')
    for r in rows:
        if r.get('method') != method or r.get('run_status') not in ('OK','ERROR','INVALID_INPUT','NOT_RUN'):
            raise ValueError('Invalid method or run status in report')
        if not isinstance(r.get('supporting_quotes', []), list) or any(not isinstance(q,dict) for q in r.get('supporting_quotes', [])):
            raise ValueError('Malformed submitted quote collection')
        if r.get('run_status') == 'OK' and r.get('factual_evidence_status') not in STATUSES:
            raise ValueError('Successful report has no valid factual status')
    successful = [r for r in rows if r['run_status']=='OK']
    attempted = [r for r in rows if r.get('api_calls',0)>0 or r.get('simulated_client_calls',0)>0]
    executed = [r for r in rows if r['run_status']!='NOT_RUN' or r in attempted]
    correct = [r for r in successful if r['factual_evidence_status']==by_id[r['case_id']]['expected_fact_status']]
    removed_all = [c for c in cases if c.get('variant')=='CONTROL_REMOVED']
    removed = [r for r in successful if by_id[r['case_id']].get('variant')=='CONTROL_REMOVED']
    positives = [r for r in successful if by_id[r['case_id']]['expected_fact_status'] in CONFIDENT]
    fp = [r for r in successful if r['factual_evidence_status'] in CONFIDENT and r not in correct]
    fn = [r for r in positives if r not in correct]
    quotes = [(r,q) for r in rows for q in r.get('supporting_quotes',[]) if isinstance(q,dict)]
    exact = [(r,q) for r,q in quotes if isinstance(q.get('quote'),str) and q['quote'] and q['quote'] in by_id[r['case_id']]['contract_excerpt']]
    unsupported = [(r,q) for r,q in exact if q.get('semantic_guard_passed') is False]
    applicable = method != 'direct-llm'
    latency = [r['runtime_seconds'] for r in executed if _number(r.get('runtime_seconds'))]
    usage = {}
    for field in ('prompt_tokens','completion_tokens','total_tokens'):
        values = [(r.get('usage') or {}).get(field) for r in attempted]
        values = [v for v in values if type(v) is int and v >= 0]
        usage[field] = dict(sum=sum(values) if values else None, reported=len(values), attempted=len(attempted))
    costs = [(r.get('response_metadata') or {}).get('provider_cost_usd') for r in attempted]
    costs = [v for v in costs if _number(v)]
    predicates = {}
    for name in ('personnel_supplied','worker_supervisor'):
        gold = [r for r in successful if name in by_id[r['case_id']].get('expected_facts',{})] if applicable else []
        predicates[name] = ratio(sum((r.get('validated_facts') or {}).get(name)==by_id[r['case_id']]['expected_facts'][name] for r in gold),len(gold), reason='Only explicit predicate annotations are scored; status-derived guesses are excluded')
    result = dict(execution_kind=kind, planned=len(cases), successful=ratio(len(successful),len(cases)),
        agreement_successful=ratio(len(correct),len(successful)), completed_and_matched_planned=ratio(len(correct),len(cases)),
        false_positive_directional=ratio(len(fp),len(successful)), false_negative_directional=ratio(len(fn),len(positives)),
        false_confident_removed=ratio(sum(r['factual_evidence_status'] in CONFIDENT or r.get('proposed_table_item') is not None for r in removed),len(removed),eligible=len(removed_all)),
        abstentions=ratio(sum(r['factual_evidence_status'] in (INSUFFICIENT,CONFLICT) for r in successful),len(successful)),
        out_of_scope=ratio(sum(r['factual_evidence_status']==OUT for r in successful),len(successful)),
        errors=ratio(sum(r['run_status'] in ('ERROR','INVALID_INPUT') for r in rows),len(cases)),
        api_errors=ratio(sum(bool(r.get('api_error')) for r in attempted),len(attempted),unit='provider/client attempts'),
        missing_control_evidence=ratio(sum((r.get('validated_facts') or {}).get('worker_supervisor')=='unknown' for r in successful) if applicable else 0,len(successful) if applicable else 0,reason=None if applicable else 'Direct baseline does not extract predicates'),
        human_review_required=ratio(sum(r.get('human_review_required') is True for r in successful),len(successful)),
        date_act_agreement=ratio(sum((r.get('date_selection') or {}).get('applicable_act')==by_id[r['case_id']]['expected_act'] for r in successful if by_id[r['case_id']].get('expected_act')),sum(bool(by_id[r['case_id']].get('expected_act')) for r in successful)),
        not_run=ratio(sum(r['run_status']=='NOT_RUN' for r in rows),len(cases)),
        refusals=ratio(sum(bool((r.get('response_metadata') or {}).get('refusal')) or r.get('not_run_or_error_reason')=='MODEL_REFUSAL' for r in attempted),len(attempted)),
        provenance=ratio(len(exact),len(quotes),unit='submitted quote entries',reason='Exact substring independently rechecked; not interpretation correctness'),
        quote_errors=ratio(len(quotes)-len(exact),len(quotes),unit='submitted quote entries'),
        unsupported_interpretations=ratio(len(unsupported),len(exact),unit='verbatim quote entries',reason='Recorded validator rejection/unverified disposition, not independent semantic ground truth'),
        predicate_agreement=predicates,
        latency_seconds=dict(sum=sum(latency) if latency else None, mean=sum(latency)/len(latency) if latency else None, measured=len(latency), executed=len(executed), scope='pipeline row runtime; historical/simulated origin retained'),
        token_usage=usage, provider_reported_cost_usd=dict(sum=sum(costs) if costs else None, reported=len(costs), attempted=len(attempted), independent_billing_verification=False),
        model_ids=sorted({r['returned_model'] for r in rows if isinstance(r.get('returned_model'),str)}),
        false_positive_ids=[r['case_id'] for r in fp], false_negative_ids=[r['case_id'] for r in fn],
        safety_target='NOT_EVALUATED' if len(removed)<len(removed_all) or not removed else ('FAIL' if any(r['factual_evidence_status'] in CONFIDENT or r.get('proposed_table_item') is not None for r in removed) else 'PASS_ON_THIS_VISIBLE_SET'),
        case_results=[dict(case_id=r['case_id'], expected=by_id[r['case_id']]['expected_fact_status'], observed=r['factual_evidence_status'] if r['run_status']=='OK' else None, run_status=r['run_status'],
            matches=r in correct, false_positive=r in fp, false_negative=r in fn,
            abstained=r['run_status']=='OK' and r['factual_evidence_status'] in (INSUFFICIENT,CONFLICT),
            reason=r.get('not_run_or_error_reason'), validation_failures=r.get('validation_failures',[]),
            annotation_note=by_id[r['case_id']].get('label_note',by_id[r['case_id']].get('annotation_rationale'))) for r in rows])
    if not applicable:
        for name in ('provenance','quote_errors','unsupported_interpretations'):
            result[name]=ratio(0,0,reason='Direct category baseline does not extract facts or quotations')
    return result
