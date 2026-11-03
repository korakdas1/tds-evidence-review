"""Record actual default-worker containment of the preserved audit's 43 KB stress recipe."""
import argparse
import hashlib
import json
import tempfile
from pathlib import Path
from src.pdf_worker import read_pdf_isolated
from tests.test_pdf_worker import stress_bytes


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    data=stress_bytes()
    with tempfile.TemporaryDirectory() as tmp:
        path=Path(tmp)/'synthetic-43kb-stress.pdf';path.write_bytes(data)
        result=read_pdf_isolated(path)
    record=dict(kind='SYNTHETIC_RESOURCE_TEST_NOT_MODEL_EVALUATION', input_bytes=len(data),
                input_sha256=hashlib.sha256(data).hexdigest(),
                status=result['status'],issues=result['issues'],worker=result['worker'],
                source_text_characters=len(result['text']),source_pages_retained=len(result['pages']))
    with args.output.open('x') as stream:json.dump(record,stream,indent=2);stream.write('\n')
    print(json.dumps(record,indent=2))
    if record['status']!='REJECTED' or not result['worker']['reaped'] or result['pages'] or result['text']:
        raise SystemExit('Containment failed')


if __name__=='__main__':main()
