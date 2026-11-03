"""Mocked live UI workflow, never sends data to an inference provider."""
import argparse
import json
from pathlib import Path
import tempfile
import threading
from http.server import ThreadingHTTPServer
from playwright.sync_api import sync_playwright, expect
from webapp.server import App, make_handler
from tests.test_live_app import CONFIG, response, SAMPLES


def run(engine, name):
    checks, calls = [], []
    def check(label, condition=True):
        if not condition: raise AssertionError(label)
        checks.append(label)
    def transport(config, record, mode):
        calls.append((record, mode))
        return response(config, record, mode)
    browser = engine.launch(**({'channel':'chrome'} if name == 'chrome' else {}))
    result = dict(browser=name, version=browser.version, checks=checks, status='FAIL', execution_kind='SIMULATED')
    try:
        with tempfile.TemporaryDirectory(prefix='tds-live-browser-') as folder:
            app = App(folder, live_config=CONFIG, _live_transport=transport, _live_interval=0)
            server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(app))
            app.port = server.server_address[1]
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = 'http://127.0.0.1:' + str(app.port)
            context = browser.new_context()
            blocked, errors = [], []
            def route(r):
                if r.request.url.startswith(base + '/'): r.continue_()
                else:
                    blocked.append(r.request.url)
                    r.abort()
            context.route('**/*', route)
            page = context.new_page()
            page.on('pageerror', lambda e: errors.append(str(e)))
            try:
                page.goto(base + '/#/new')
                expect(page.get_by_role('heading', name='New evidence review', exact=True)).to_be_visible()
                check('offline remains default with live configured', page.locator('input[value=baseline]').is_checked())
                expect(page.get_by_text('synthetic/fixed:free', exact=False).first).to_be_visible()
                check('configured model is displayed before opting in')
                page.locator('#file-contract').set_input_files(str(SAMPLES / 'warehouse_agreement.pdf'))
                page.get_by_label('Invoice description', exact=True).fill('Synthetic live UI test')
                page.get_by_label('Credit date', exact=True).fill('2026-04-01')
                page.get_by_label('Payment date', exact=True).fill('2026-04-02')
                page.locator('input[value=live_hybrid]').check()
                check('selecting live mode alone sends nothing', not calls)
                page.get_by_role('button', name='Run evidence review', exact=True).click()
                dialog = page.get_by_role('dialog')
                expect(dialog).to_be_visible()
                expect(dialog).to_contain_text('external model provider')
                expect(dialog).to_contain_text('SIMULATED')
                check('per-run external transmission and simulation notice displayed', not calls)
                page.get_by_role('button', name='Cancel, keep data local', exact=True).click()
                expect(dialog).to_have_count(0)
                check('cancel makes zero requests and creates no case', not calls and not app.store.cases())
                page.get_by_role('button', name='Run evidence review', exact=True).click()
                expect(dialog).to_be_visible()
                page.get_by_role('button', name='Confirm this one external request', exact=True).click()
                expect(page.locator('#tab-evidence')).to_be_visible(timeout=20000)
                view = app.service.case_view(page.url.rsplit('/',1)[-1])
                check('one explicit confirmation invokes one mock', len(calls) == 1)
                check('saved run is simulated with zero network calls', view['run']['execution']['execution_kind']=='SIMULATED' and view['run']['model_network_calls']==0)
                check('all PDF proposals remain withheld', view['finding']['proposed_table_item'] is None)
                page.locator('#tab-transaction').click()
                expect(page.get_by_text('SIMULATED; configured', exact=False)).to_be_visible()
                check('workspace shows actual execution provenance')
                check('no external browser requests or uncaught errors', not blocked and not errors)
                result['status']='PASS'
            except Exception as exc:
                result['error']=str(exc)
            finally:
                result['mock_invocations']=len(calls)
                result['live_network_calls']=0
                context.close()
                server.shutdown(); server.server_close(); thread.join(timeout=5)
    finally:
        browser.close()
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', required=True)
    args=p.parse_args()
    path=Path(args.output); path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as f: f.write('{}\n')
    results=[]
    with sync_playwright() as p:
        for name, engine in [('chrome',p.chromium), ('firefox',p.firefox)]:
            result=run(engine,name); results.append(result)
            path.write_text(json.dumps(dict(execution_kind='SIMULATED', browsers=results),indent=2)+'\n')
            print(name,result['status'],len(result['checks']),'checks')
    return 0 if all(r['status']=='PASS' for r in results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
