"""Offline audit-only PDF stress probe. Each parse is isolated by this harness, NOT the app.
Run: python -m tests.phase6_resource_probe --output NEW.json
Linux/POSIX resource limits keep the audit from exhausting the host. No PDFs are retained.
"""
import argparse
import json
import os
import resource
import signal
import subprocess
import sys
import tempfile
import time
import zlib
from pathlib import Path
from unittest.mock import patch


def worker(path):
    resource.setrlimit(resource.RLIMIT_AS, (256 * 1024 * 1024,) * 2)
    resource.setrlimit(resource.RLIMIT_CPU, (5, 6))
    signal.signal(signal.SIGXCPU, lambda *args: (_ for _ in ()).throw(TimeoutError('CPU budget')))
    from src.pdf_ingestion import read_pdf
    started=time.monotonic()
    result=read_pdf(path)
    print(json.dumps(dict(status=result['status'], issues=result['issues'],
                         page_issues=[p['issues'] for p in result['pages']],
                         elapsed_seconds=round(time.monotonic()-started,3),
                         peak_rss_kib=int(next(line for line in Path("/proc/self/status").read_text().splitlines() if line.startswith("VmHWM:")).split()[1]),
                         rss_source="Linux /proc/self/status VmHWM after exec (avoids inherited fork high-water)",
                         external_audit_limits='256 MiB address space; 5/6 seconds CPU; not application limits')))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--worker');parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    if args.worker: return worker(args.worker)
    from tests.test_phase6 import bomb_pdf
    from webapp.samples.generate_samples import build_pdf
    results=[]
    with tempfile.TemporaryDirectory() as tmp:
        compressed=bomb_pdf()
        with patch('webapp.samples.generate_samples._page_stream',return_value=b'q Q\n'*480000):
            operations=build_pdf([('Synthetic stress',[])]*2)
        encoded_ops=zlib.compress(b'q Q\n'*480000,9)
        with patch('tests.test_phase6.zlib.compress',return_value=encoded_ops):
            dense_compressed=bomb_pdf(pages=20,raw_bytes=0)
        for name,data in [('compressed_20_page',compressed),('dense_operators_2_page',operations),('dense_operators_compressed_20_page',dense_compressed)]:
            p=Path(tmp)/(name+'.pdf');p.write_bytes(data)
            started=time.monotonic()
            try:
                run=subprocess.run([sys.executable,'-m','tests.phase6_resource_probe','--worker',str(p)],
                                   capture_output=True,text=True,timeout=12)
                result=dict(probe=name,file_bytes=len(data),exit_code=run.returncode,
                            wall_seconds=round(time.monotonic()-started,3),
                            result=json.loads(run.stdout) if run.stdout.strip() else None,
                            stderr_present=bool(run.stderr))
            except subprocess.TimeoutExpired:
                result=dict(probe=name,file_bytes=len(data),watchdog='12-second audit timeout')
            results.append(result)
    with args.output.open('x') as stream: json.dump(results,stream,indent=2);stream.write('\n')
    print(json.dumps(results,indent=2))


if __name__=='__main__':main()
