"""Offline factual comparison with explicit simulated/recorded provenance; no live inference CLI."""
import argparse
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from src.comparison import ROOT, METHODS, sha, metrics, validate_dataset
from src.extraction import OpenRouterClient, DIRECT_PROMPT, EXTRACTION_PROMPT
from src.pipeline import run_batch
from src.schema import INSUFFICIENT, parse_json


class Simulation:
    configured = True
    model = 'HAND_AUTHORED_SIMULATION_NOT_A_MODEL'
    def __init__(self, fixtures):
        self.fixtures = {f['case_id']:f['extraction'] for f in fixtures}
    def complete(self, record, mode):
        value = {'factual_status':INSUFFICIENT} if mode=='direct-llm' else self.fixtures[record['id']]
        return dict(raw_output=json.dumps(value), returned_model=None, usage=None,
                    response_metadata=dict(execution_kind='SIMULATED'))


def save(path, value):
    with Path(path).open('x', encoding='utf-8') as f:
        json.dump(value,f,indent=2,allow_nan=False)
        f.write('\n')


def recorded_reports(path, digest, cases):
    manifest = parse_json(Path(path).read_text())
    if manifest.get('schema') != 'tds-recorded-comparison-v1' or manifest.get('dataset_sha256') != digest:
        raise ValueError('Recorded manifest does not match frozen input')
    if manifest.get('execution_kind') not in ('HISTORICAL_RECORDED_LIVE','RECORDED_LIVE'):
        raise ValueError('Recorded reports need explicit origin; simulations cannot be relabelled live')
    sources = manifest.get('reports')
    if not isinstance(sources,dict) or set(sources) != {'direct-llm','hybrid'}:
        raise ValueError('Both recorded methods are required, including missing-case records')
    result={}
    for method, source in sources.items():
        report_path = Path(path).parent / source['path']
        if sha(report_path) != source['sha256']:
            raise ValueError('Recorded source report hash mismatch')
        report = parse_json(report_path.read_text())
        if report.get('input_sha256') != digest or report.get('method') != method:
            raise ValueError('Recorded report input or method mismatch')
        if 'FIXTURE' in report.get('experiment_kind','') or report.get('execution_kind')=='SIMULATED':
            raise ValueError('Simulation cannot be imported as live evidence')
        rows=report.get('results')
        if not isinstance(rows,list): raise ValueError('Recorded results are missing')
        ids=[r.get('case_id') for r in rows]
        if len(ids)!=len(set(ids)) or not set(ids).issubset({c['id'] for c in cases}):
            raise ValueError('Duplicate or unknown case IDs in recorded report')
        by_id={r['case_id']:r for r in rows}
        normalized=[]
        for case in cases:
            if case['id'] in by_id:
                row=by_id[case['id']]
                if ((row.get('response_metadata') or {}).get('execution_kind')=='SIMULATED'
                        or row.get('simulated_client_calls',0)>0):
                    raise ValueError('Simulation cannot be relabelled as a live result')
                if row.get('run_status')=='OK' and (row.get('api_calls') != 1 or not row.get('returned_model')):
                    raise ValueError('Successful recorded live row lacks a call and model record')
                normalized.append(row)
            else:
                row=run_batch([case],method,digest,OpenRouterClient('',''))['results'][0]
                row['not_run_or_error_reason']='MISSING_RECORDED_ROW'
                row['runtime_seconds']=None
                normalized.append(row)
        result[method]=dict(rows=normalized, kind=manifest['execution_kind'],
                            source_sha256=source['sha256'], source_name=report_path.name, source_path=report_path,
                            provenance='Hash-pinned supplied report, not an authenticated provider receipt')
    return result


def run(input_path, output_dir, input_sha=None, simulate=False, recorded=None):
    cases,digest,origin=validate_dataset(input_path,input_sha)
    if simulate and recorded: raise ValueError('Simulation and recorded import are separate comparisons')
    sources={}
    fixture_path=ROOT/'phase3_extraction_fixtures.json'
    if simulate:
        manifest=parse_json((ROOT/'phase3_manifest.json').read_text())
        if digest!=manifest['files']['tresata_challenge_v3.json'] or sha(fixture_path)!=manifest['files'][fixture_path.name]:
            raise ValueError('Simulation uses only the frozen Phase 3 dataset and fixtures')
        client=Simulation(parse_json(fixture_path.read_text())['fixtures'])
        sources[str(fixture_path.relative_to(ROOT))]=sha(fixture_path)
    else:
        client=OpenRouterClient('','')  # Explicitly empty, even if shell contains credentials.
    imported=recorded_reports(recorded,digest,cases) if recorded else {}
    if recorded:
        sources[Path(recorded).name]=sha(recorded)
    watched = {Path(input_path):digest, ROOT/'evaluation/protocol_v1.json':sha(ROOT/'evaluation/protocol_v1.json')}
    if simulate: watched[fixture_path]=sha(fixture_path)
    if recorded: watched[Path(recorded)]=sha(recorded)
    for source in imported.values(): watched[source['source_path']]=source['source_sha256']
    out=Path(output_dir)
    out.mkdir(parents=True,exist_ok=False)
    protocol_path=ROOT/'evaluation/protocol_v1.json'
    implementation={str(p.relative_to(ROOT)):sha(p) for p in sorted((ROOT/'src').glob('*')) if p.suffix in ('.py','.json')}
    implementation['evaluate_comparison.py']=sha(ROOT/'evaluate_comparison.py')
    save(out/'protocol.json',dict(schema='tds-comparison-run-v1',created_at=datetime.now(timezone.utc).isoformat(),
        input_sha256=digest, input_name=Path(input_path).name, cases=len(cases), annotation_origin=origin,
        protocol_sha256=sha(protocol_path), sources_sha256=sources, implementation_sha256=implementation,
        prompt_sha256={k:hashlib.sha256(v.encode()).hexdigest() for k,v in [('direct-llm',DIRECT_PROMPT),('hybrid',EXTRACTION_PROMPT)]},
        requested_execution='SIMULATED' if simulate else 'RECORDED_IMPORT' if recorded else 'OFFLINE_ONLY',
        actual_live_calls_this_run=0, independent_practitioner_validation='NOT_ESTABLISHED'))
    comparisons={}
    for method in METHODS:
        if method in imported:
            rows,kind=imported[method]['rows'],imported[method]['kind']
            provenance={k:v for k,v in imported[method].items() if k not in ('rows','source_path')}
        else:
            batch=run_batch(cases,method,digest,client=client)
            rows=batch['results']
            kind='OFFLINE' if method=='baseline' else 'SIMULATED' if simulate else 'NOT_RUN'
            if kind=='SIMULATED':
                for r in rows:
                    r['simulated_client_calls'],r['api_calls']=r['api_calls'],0
            provenance=dict(kind=kind, limitation='Synthetic fixtures are not model measurements' if simulate else 'No live model requested')
        summary=metrics(cases,rows,method,kind)
        comparisons[method]=summary
        save(out/(method+'.json'),dict(schema='tds-method-comparison-v1',method=method,input_sha256=digest,
             execution_kind=kind,provenance=provenance,metrics=summary,results=rows))
    models={m:c['model_ids'] for m,c in comparisons.items() if m!='baseline'}
    conclusion=dict(schema='tds-comparison-summary-v1',input_sha256=digest,annotation_origin=origin,
        actual_live_calls_this_run=0,methods=comparisons,model_ids=models,
        same_single_model_observed=bool(models['direct-llm']) and models['direct-llm']==models['hybrid'] and len(models['direct-llm'])==1,
        limitations=['No legally validated tax accuracy.', 'No independent practitioner validation is established by a file format.',
                    'Current baseline and historical methods may use different implementations; no causal superiority claim.',
                    'Errors and missing outputs are separate from successful abstentions; directional false negatives may be justified.',
                    'Simulated/historical/live metrics must not be pooled as one experiment.'])
    if any(sha(p)!=h for p,h in watched.items()) or any(sha(ROOT/p)!=h for p,h in implementation.items()):
        raise ValueError('Input or implementation changed during evaluation; run is incomplete')
    save(out/'summary.json',conclusion)
    with (out/'cases.csv').open('x',newline='') as f:
        fields=['method','execution_kind','case_id','expected','observed','run_status','matches','false_positive','false_negative','abstained','reason']
        writer=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');writer.writeheader()
        for method,summary in comparisons.items():
            for row in summary['case_results']:
                writer.writerow(dict(row,method=method,execution_kind=summary['execution_kind']))
    return conclusion


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',type=Path,default=ROOT/'tresata_challenge_v3.json')
    p.add_argument('--input-sha256',help='Required for a new separately frozen dataset; original manifests take precedence')
    p.add_argument('--output-dir',type=Path,required=True)
    modes=p.add_mutually_exclusive_group()
    modes.add_argument('--simulate',action='store_true',help='Hand-authored/stub responses, explicitly not live results')
    modes.add_argument('--recorded-manifest',type=Path,help='Hash-pinned historical or recorded live reports; never sends requests')
    a=p.parse_args()
    try:
        result=run(a.input,a.output_dir,a.input_sha256,a.simulate,a.recorded_manifest)
    except (ValueError,OSError,KeyError,TypeError) as exc:
        p.exit(1,'Evaluation failed: '+type(exc).__name__+'; inputs/results were not rewritten.\n')
    for method, summary in result['methods'].items():
        agreement=summary['agreement_successful'];coverage=summary['successful']
        print('{} [{}]: completed {}/{}; matched {}/{} successful cases'.format(method,summary['execution_kind'],coverage['numerator'],coverage['denominator'],agreement['numerator'],agreement['denominator']))
    print('No live calls made. Factual development agreement, not legal accuracy.')
    return 0


if __name__=='__main__':
    raise SystemExit(main())
