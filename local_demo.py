"""Complete disposable local-review walkthrough. Synthetic inputs; no network/model calls."""
import json
import sqlite3
import tempfile
from pathlib import Path

from demo import demo_text
from webapp.checkpoint import create_checkpoint, write_checkpoint, read_checkpoint, verify_checkpoint
from webapp.service import ReviewService, ServiceError
from webapp.store import Store


def walkthrough():
    with tempfile.TemporaryDirectory(prefix='tds-local-demo-') as folder:
        root=Path(folder)
        store=Store(root/'application')
        service=ReviewService(store)
        supported=service.create_sample_case('warehouse')
        suggestion=service.create_sample_case('event-crew')
        scanned=service.create_sample_case('scanned')
        case_id=supported['case']['id']
        card=next(c for c in supported['evidence'] if any(a['fact']=='worker_supervisor' for a in c['assertions']))
        fragment=card['occurrences'][0]['fragments'][0]
        reviewed=service.record_event(case_id,dict(kind='QUOTE_CHECK',target=card['key'],decision='MATCHES_DOCUMENT',
                                                  reviewer='Synthetic Demo Reviewer',note='Compared words only; no tax approval.'))
        unchanged=reviewed['finding']==supported['finding'] and reviewed['run']['report_sha256']==supported['run']['report_sha256']
        receipt=create_checkpoint(store.data_dir,case_id)
        path=root/'reviewer-held-checkpoint.json'
        write_checkpoint(path,store.data_dir,receipt)
        service.record_event(case_id,dict(kind='NOTE',reviewer='Synthetic Demo Reviewer',note='Later note, outside the held prefix.'))
        verified=verify_checkpoint(store.data_dir,read_checkpoint(path))
        export=service.export(case_id)
        return dict(
            execution='OFFLINE_WITH_EXPLICIT_HAND_AUTHORED_REPLAY',
            supported=dict(document=supported['documents'][0]['name'],page=fragment['page_number'],
                           start=fragment['start'],end=fragment['end'],quote=card['quote'],
                           status=supported['finding']['factual_evidence_status']),
            suggestion=dict(status=suggestion['finding']['factual_evidence_status'],
                            states=[c['category'] for c in suggestion['evidence']],execution='SIMULATED_NOT_A_MODEL'),
            scanned=dict(status=scanned['report_status'],evidence_count=len(scanned['evidence'])),
            reviewer=dict(findings_unchanged=unchanged,statutory_proposal=reviewed['finding']['statutory_proposal']),
            checkpoint=verified,export_integrity=export['integrity_status'],
            model_network_calls=sum(v['run']['model_network_calls'] for v in (supported,suggestion,scanned)),
            simulated_client_invocations=sum(v['run']['simulated_client_invocations'] for v in (supported,suggestion,scanned)),
            human_review_required=True,storage='Disposable synthetic database removed after this function returns')


def render(result):
    source=result['supported']
    return '\n'.join([
        'Complete local review demo — synthetic, offline, no tax approval',
        '1. PDF evidence: {} page {}, characters {}:{} (extracted text).'.format(source['document'],source['page'],source['start'],source['end']),
        '   Exact quote: '+source['quote'],
        '   Factual status: '+source['status'],
        '2. Hand-authored AI-suggestion replay (NOT a model): '+', '.join(result['suggestion']['states']),
        '   Factual status: '+result['suggestion']['status'],
        '3. Scanned document: '+result['scanned']['status']+'; no evidence invented.',
        '4. Reviewer quote decision: findings unchanged='+str(result['reviewer']['findings_unchanged'])+'; statutory proposal '+result['reviewer']['statutory_proposal']+'.',
        '5. External checkpoint: '+result['checkpoint']['status']+'; later events='+str(result['checkpoint']['later_events'])+'.',
        '   Independently held prefix only; no authenticated identity, trusted timestamp or legal approval.',
        '6. Export: '+result['export_integrity']+'. All results require qualified human review.',
        '   Real model calls='+str(result['model_network_calls'])+'; simulated extraction invocations='+str(result['simulated_client_invocations'])+'.',
        'Temporary synthetic database and uploads have been removed.',
        '',
        'Original JSON/historical-evidence walkthrough follows:',
        demo_text(),
    ])


def main():
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--json',action='store_true',help='Print the disposable workflow summary as JSON')
    args=parser.parse_args()
    try:
        result=walkthrough()
        print(json.dumps(result,indent=2) if args.json else render(result))
        return 0
    except (OSError,ValueError,KeyError,StopIteration,sqlite3.Error,ServiceError):
        print('Demo could not complete. Use Linux, install requirements-pdf.txt and keep the frozen synthetic files intact.')
        return 1


if __name__=='__main__':
    raise SystemExit(main())
