"""Read-only Git/private-file checks for the authorized multi-phase development goal.

Does not print credentials or claim a full penetration test. Output must be a NEW file.
"""
import argparse
import json
import os
import re
import subprocess
from pathlib import Path

START = 'HEAD'  # Every committed prior phase is historical at the next release check.
SUBMISSION = 'e075a9087b8f4dbebee3fe74f2cb427c5bc3a3c0'
PATTERN = re.compile(rb'sk-or-v1-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|\b(?:AKIA|ASIA)[A-Z0-9]{16}\b|https?://[^\s/@:]+:[^\s/@]+@')


def git(*args):return subprocess.check_output(['git',*args])


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    secrets=[]
    if os.environ.get('OPENROUTER_API_KEY'):secrets.append(os.environ['OPENROUTER_API_KEY'].encode())
    if Path('.env').is_file():
        for line in Path('.env').read_text().splitlines():
            name,sep,value=(line[7:] if line.startswith('export ') else line).partition('=')
            if sep and re.search(r'(KEY|SECRET|TOKEN|PASSWORD)$',name.strip()):
                value=value.strip().strip('\"\'')
                if value:secrets.append(value.encode())
    paths=sorted(set(git('ls-files','-z','--cached','--others','--exclude-standard').decode().strip('\0').split('\0')))
    findings=[]
    def scan(raw,label):
        if PATTERN.search(raw) or any(secret in raw for secret in secrets):findings.append(label)
    for p in paths:
        scan(Path(p).read_bytes(),p)
        if any(x in Path(p).parts for x in ('.env','.aws','.venv','local_data','__pycache__','private')):
            findings.append('private-path:'+p)
    prior=git('ls-tree','-r','--name-only',START).decode().splitlines()
    protected=[p for p in prior if p.startswith(('results/','tests/','webapp/samples/','tresata_','PHASE_','phase3_extraction'))
               or p.endswith('_manifest.json') or p in ('RUN_REPORT.md','DEMO_WALKTHROUGH.md','src/extraction.py','src/rules_v1.json','src/act_selection_v1.json')]
    for p in protected:
        if not Path(p).is_file() or Path(p).read_bytes()!=git('show',START+':'+p):findings.append('historical-change:'+p)
    history=0
    for line in git('rev-list','--objects','--all').decode().splitlines():
        oid=line.split()[0]
        if git('cat-file','-t',oid).strip()!=b'blob':continue
        history+=1;scan(git('cat-file','blob',oid),'history:'+oid)
    if git('branch','--show-current').strip()!=b'feature/full-product':findings.append('wrong-branch')
    if git('rev-parse','main').decode().strip()!=SUBMISSION:findings.append('main-changed')
    for p in ('.env','local_data/','.aws','.venv/'):
        if subprocess.run(['git','check-ignore','-q',p]).returncode:findings.append('not-ignored:'+p)
    result=dict(status='PASS' if not findings else 'FAIL',findings=findings,
                candidate_files_scanned=len(paths),history_blobs_scanned=history,
                protected_historical_files_unchanged=len(protected),credential_values_compared=len(secrets),
                main_sha=git('rev-parse','main').decode().strip(),branch='feature/full-product',
                limitation='Exact-known-secret and pattern/file checks, not a complete security assessment. Review new files manually too.')
    with args.output.open('x') as stream:json.dump(result,stream,indent=2);stream.write('\n')
    print(json.dumps(result,indent=2))
    return 0 if not findings else 1


if __name__=='__main__':raise SystemExit(main())
