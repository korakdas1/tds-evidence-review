"""Optional reproducible Chrome/Firefox workflow checks, synthetic temporary data only.

Run: python -m browser_tests.run --output results/local/browser.json
Install requirements-browser.txt and `python -m playwright install firefox` first.
Chrome uses the installed stable channel; Chromium can be selected explicitly.
"""
import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
from http.server import ThreadingHTTPServer
from urllib.parse import urlsplit

from webapp.server import App, make_handler

ROOT = Path(__file__).resolve().parent.parent


def exercise(engine, name, output):
    from playwright.sync_api import expect
    checks, errors, blocked, internal = [], [], [], []
    def check(label, value=True):
        if not value:
            raise AssertionError(label)
        checks.append(label)
    browser = engine.launch(**({'channel': 'chrome'} if name == 'chrome' else {}))
    output.update(browser=name, version=browser.version, checks=checks)
    try:
        with tempfile.TemporaryDirectory(prefix='tds-browser-') as folder:
            app = App(folder, 0)
            server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(app))
            app.port = server.server_address[1]
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = 'http://127.0.0.1:' + str(app.port)
            context = browser.new_context(viewport={'width': 1440, 'height': 950})
            # Browser interactions are limited to this local synthetic server.
            def route(request):
                if request.request.url.startswith(base + '/'):
                    request.continue_()
                elif urlsplit(request.request.url).scheme not in ('http', 'https'):
                    internal.append(urlsplit(request.request.url).scheme)
                    request.continue_()
                else:
                    blocked.append(request.request.url)
                    request.abort()
            context.route('**/*', route)
            page = context.new_page()
            page.on('pageerror', lambda e: errors.append(str(e)))
            try:
                page.goto(base)
                expect(page.get_by_role('heading', name='Evidence reviews', exact=True)).to_be_visible()
                check('fresh dashboard has zero cases', page.locator('.case-row').count() == 0)
                page.get_by_role('link', name='New review', exact=True).first.click()
                page.get_by_role('button', name='Run evidence review', exact=True).click()
                expect(page.get_by_text('Add a contract PDF.', exact=True)).to_be_visible()
                check('empty form gives actionable validation')
                page.get_by_label('Invoice description', exact=True).fill('Synthetic warehouse service')
                check('typing clears stale error', page.get_by_label('Invoice description', exact=True).get_attribute('aria-invalid') is None)
                page.locator('#file-contract').set_input_files(str(ROOT / 'webapp/samples/warehouse_agreement.pdf'))
                page.get_by_label('Credit date', exact=True).fill('2026-03-31')
                page.get_by_label('Payment date', exact=True).fill('2026-04-02')
                page.get_by_role('button', name='Run evidence review', exact=True).click()
                expect(page.locator('#tab-evidence')).to_be_visible(timeout=20000)
                case_id = page.url.rsplit('/', 1)[-1]
                view = app.service.case_view(case_id)
                check('manual upload creates baseline case with withheld proposal', view['run']['method'] == 'baseline' and view['finding']['proposed_table_item'] is None)
                page.get_by_role('button', name='Contract page 1, characters', exact=False).first.click()
                expect(page.locator('mark').first).to_be_visible()
                check('source button selects exact extracted passage')
                page.locator('#tab-evidence').focus()
                page.keyboard.press('ArrowRight')
                expect(page.locator('#tab-transaction')).to_be_focused()
                page.keyboard.press('End')
                expect(page.locator('#tab-history')).to_be_focused()
                page.keyboard.press('Home')
                expect(page.locator('#tab-evidence')).to_be_focused()
                check('roving tabs support arrows Home End')
                page.get_by_role('button', name='Set reviewer name', exact=True).click()
                dialog = page.get_by_role('dialog')
                expect(dialog).to_be_visible()
                check('dialog removes background from focus/accessibility', page.locator('#main').evaluate('(e)=>e.inert'))
                for _ in range(5):
                    page.keyboard.press('Tab')
                    check('dialog focus remains contained ' + str(_), dialog.evaluate('(e)=>e.contains(document.activeElement)'))
                page.keyboard.press('Escape')
                expect(dialog).to_have_count(0)
                check('Escape restores background', not page.locator('#main').evaluate('(e)=>e.inert'))
                page.get_by_role('button', name='Matches the PDF', exact=True).first.click()
                page.get_by_label('Note', exact=True).first.fill('Synthetic browser check')
                page.get_by_role('button', name='Record decision', exact=True).first.click()
                page.get_by_label('Reviewer name', exact=True).fill('Browser Test Reviewer')
                page.get_by_role('button', name='Save name', exact=True).click()
                expect(page.locator('.stamp')).to_have_count(1)
                expect(page.locator('.stamp')).to_contain_text('Browser Test Reviewer')
                after = app.service.case_view(case_id)
                check('review decision appends history without changing findings', after['finding'] == view['finding'] and len(after['events']) == len(view['events']) + 1)
                page.get_by_role('button', name='Original PDF', exact=True).click()
                expect(page.locator('iframe.pdf-frame')).to_have_count(1)
                check('original PDF viewer has accessible title and local URL', page.locator('iframe').get_attribute('title').startswith('Original PDF:') and page.locator('iframe').get_attribute('src').startswith('/api/documents/'))
                # Native PDF rendering differs by headless engine; test wrapper/provenance, not raster fidelity.
                check('visible buttons and tabs have accessible names', page.locator('button:visible,[role=tab]:visible').evaluate_all('els=>els.every(e=>Boolean(e.getAttribute("aria-label") || e.textContent.trim()))'))
                sha = app.store.run(view['run']['id'])['contract_sha256']
                _, path = app.store.verify_document(sha)
                path.write_bytes(b'damaged synthetic PDF')
                page.reload()
                expect(page.get_by_text('Quotation checks are unavailable', exact=False).first).to_be_visible()
                check('damaged PDF prevents quotation decisions', page.get_by_role('button', name='Matches the PDF', exact=True).count() == 0)
                # Re-upload repairs only exact synthetic bytes; historical analysis unchanged.
                app.service.upload('warehouse_agreement.pdf', (ROOT / 'webapp/samples/warehouse_agreement.pdf').read_bytes())
                with closing(sqlite3.connect(str(app.store.db_path))) as db, db:
                    db.execute('DROP TRIGGER runs_no_update')
                    raw = db.execute('SELECT report_json FROM runs WHERE id=?', (view['run']['id'],)).fetchone()[0]
                    changed = json.loads(raw)
                    changed['forged'] = 'FORGED_BROWSER_SENTINEL'
                    raw = json.dumps(changed)
                    db.execute('UPDATE runs SET report_json=?,report_sha256=? WHERE id=?', (raw, hashlib.sha256(raw.encode()).hexdigest(), view['run']['id']))
                page.reload()
                expect(page.get_by_text('Integrity check failed', exact=False).first).to_be_visible()
                check('untrusted view contains no findings/decision buttons', page.locator('.ev').count() == 0 and 'FORGED_BROWSER_SENTINEL' not in page.inner_text('body') and page.get_by_role('button', name='Record decision', exact=True).count() == 0)
                export = app.service.export(case_id)
                check('untrusted export quarantines altered run', len(export['runs']) == 0 and len(export['forensic_untrusted']['runs']) == 1)
                page.get_by_role('link', name='Reviews', exact=True).first.click()
                expect(page.get_by_text('Not shown: integrity check failed', exact=True)).to_be_visible()
                check('dashboard suppresses untrusted findings')
                page.set_viewport_size({'width': 390, 'height': 844})
                check('mobile dashboard has no horizontal overflow', page.evaluate('document.documentElement.scrollWidth <= innerWidth'))
                page.locator('.sample').filter(has_text='Scanned').first.get_by_role('button', name='Open', exact=True).click()
                expect(page.locator('#tab-evidence')).to_be_visible(timeout=20000)
                check('scanned sample remains document review with no proposal', app.service.case_view(page.url.rsplit('/', 1)[-1])['report_status'] == 'NEEDS_DOCUMENT_REVIEW')
                check('mobile workspace has no horizontal overflow', page.evaluate('document.documentElement.scrollWidth <= innerWidth'))
                check('no uncaught browser exceptions', not errors)
                check('no attempted external browser requests', not blocked)
                output['status'] = 'PASS'
            finally:
                output['page_errors'] = errors
                output['blocked_external_requests'] = len(blocked)
                output['blocked_external_urls'] = blocked
                output['browser_internal_request_schemes'] = sorted(set(internal))
                context.close()
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)
    finally:
        browser.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    parser.add_argument('--browsers', nargs='+', choices=['chrome', 'chromium', 'firefox'], default=['chrome', 'firefox'])
    args = parser.parse_args()
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Refuse historical-result overwrite before starting any browser.
    with path.open('x') as f:
        f.write('{}\n')
    from playwright.sync_api import sync_playwright
    result = dict(schema='tds-browser-regression-v1', synthetic=True, live_model_calls=0, browsers=[])
    with sync_playwright() as p:
        for name in args.browsers:
            row = dict(browser=name, status='FAIL', checks=[])
            result['browsers'].append(row)
            try:
                exercise(p.firefox if name == 'firefox' else p.chromium, name, row)
            except Exception as exc:
                row['error'] = str(exc)
            path.write_text(json.dumps(result, indent=2) + '\n')
            print(name, row['status'], len(row['checks']), 'checks')
    return 0 if all(r['status'] == 'PASS' for r in result['browsers']) else 1


if __name__ == '__main__':
    raise SystemExit(main())
