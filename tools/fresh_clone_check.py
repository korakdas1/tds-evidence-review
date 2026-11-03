"""Verify a committed development snapshot in a disposable clone and fresh venv.

Dependency installation uses PyPI; demonstrations and HTTP checks are offline.
No credentials are copied, no model APIs are called, and no branch is changed/pushed.
"""
import argparse
import http.client
import json
import os
from pathlib import Path
import re
import select
import subprocess
import sys
import tempfile
import time


def probe_server(clone, python, env, log):
    with log.open('w') as output:
        proc=subprocess.Popen([str(python),'review_app.py','--port','0','--data-dir','local_data'],
                              cwd=str(clone),env=env,stdout=subprocess.PIPE,stderr=output,text=True)
        try:
            if not select.select([proc.stdout],[],[],15)[0]:
                raise RuntimeError('Server startup deadline exceeded')
            banner=proc.stdout.readline()
            output.write(banner);output.flush()
            match=re.search(r'http://127\.0\.0\.1:(\d+)/',banner)
            if not match: raise RuntimeError('Server did not expose a loopback URL')
            port=int(match.group(1))
            def request(method,path):
                connection=http.client.HTTPConnection('127.0.0.1',port,timeout=30)
                try:
                    connection.request(method,path,headers={'X-TDS-Review':'1'})
                    response=connection.getresponse();value=json.loads(response.read())
                    return response.status,value
                finally:
                    connection.close()
            status,health=request('GET','/api/health')
            if status!=200 or health['model_calls']!='DISABLED' or not health['pdf_parser']['available']:
                raise RuntimeError('Fresh server health failed offline/parser checks')
            status,view=request('POST','/api/samples/warehouse/cases')
            if status!=201 or view['finding']['proposed_table_item'] is not None or view['integrity']['status']!='VERIFIED':
                raise RuntimeError('Fresh sample workflow failed')
            status,export=request('GET','/api/cases/'+view['case']['id']+'/export')
            if status!=200 or export['integrity_status']!='VERIFIED':
                raise RuntimeError('Fresh export verification failed')
            return dict(health='PASS_OFFLINE',sample='PASS_WITHHELD_PROPOSAL',export='PASS_VERIFIED',
                        model_network_calls=view['run']['model_network_calls'],port_kind='ephemeral_loopback')
        finally:
            proc.terminate()
            try: proc.wait(timeout=10)
            except subprocess.TimeoutExpired: proc.kill();proc.wait()
            proc.stdout.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,default=Path.cwd(),help='Local committed repository to clone')
    parser.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args()
    output=args.output_dir.resolve();output.mkdir(parents=True,exist_ok=False)
    source=args.source.resolve()
    # Deliberately exclude credentials/configuration from the isolated demonstration environment.
    env={k:v for k,v in os.environ.items() if not re.search(r'KEY|TOKEN|SECRET|PASSWORD|OPENROUTER|TDS_LIVE|PYTHONPATH|VIRTUAL_ENV|PIP_INDEX|PIP_EXTRA_INDEX',k,re.I)}
    env['PIP_CONFIG_FILE']=os.devnull
    report=dict(status='FAIL',commands=[],live_model_calls=0,credential_files_copied=False)
    started=time.monotonic()
    with tempfile.TemporaryDirectory(prefix='tds-fresh-clone-') as folder:
        clone=Path(folder)/'checkout'
        def command(name,args,cwd=None,timeout=180):
            with (output/(name+'.txt')).open('x') as log:
                result=subprocess.run([str(a) for a in args],cwd=str(cwd or source),env=env,
                                      stdout=log,stderr=subprocess.STDOUT,timeout=timeout)
            report['commands'].append(dict(name=name,argv=[str(a).replace(str(clone),'<fresh-clone>') for a in args],exit_code=result.returncode))
            if result.returncode: raise RuntimeError('Fresh-clone command failed: '+name)
        try:
            command('clone',['git','clone','--no-hardlinks','--single-branch','--branch','feature/full-product',source,clone])
            report['commit_sha']=subprocess.check_output(['git','rev-parse','HEAD'],cwd=str(clone),text=True).strip()
            if (clone/'.env').exists(): raise RuntimeError('Credential file unexpectedly present in clone')
            command('venv',[sys.executable,'-m','venv',clone/'.venv'],clone)
            python=clone/'.venv/bin/python'
            command('install',[python,'-m','pip','install','--disable-pip-version-check','--index-url','https://pypi.org/simple','-r','requirements-pdf.txt'],clone)
            command('versions',[python,'-c','import sys,pypdf; print(sys.version); print("pypdf",pypdf.__version__)'],clone)
            command('tests',[python,'-m','unittest','discover','-v'],clone)
            for demo in ('demo.py','pdf_demo.py','local_demo.py'):
                command(demo.replace('.py',''),[python,demo],clone)
            command('evaluation',[python,'evaluate_comparison.py','--output-dir','results/local/fresh-evaluation'],clone)
            report['http']=probe_server(clone,python,env,output/'server.txt')
            command('unchanged_checkout',['git','diff','--exit-code'],clone)
            report['status']='PASS'
        except (OSError,ValueError,RuntimeError,subprocess.SubprocessError) as exc:
            report['error_type']=type(exc).__name__
        finally:
            report['elapsed_seconds']=round(time.monotonic()-started,3)
            (output/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
    return 0 if report['status']=='PASS' else 1


if __name__=='__main__':
    raise SystemExit(main())
