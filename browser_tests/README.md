# Reproducible local browser regression harness

Optional development dependency, separate from the application:

```sh
python -m pip install -r requirements-pdf.txt -r requirements-browser.txt
python -m playwright install firefox
# Install stable Google Chrome separately; the harness reports its actual version.
python -m browser_tests.run --output results/local/browser.json
```

Choose a new output filename for each run; existing reports cannot be overwritten. Exit 0 means all requested browsers passed; unavailable browsers are failures, not silent skips. The default runs installed Google Chrome (`channel=chrome`) and pinned Playwright Firefox. For bundled Chromium instead, install it with `python -m playwright install chromium` and specify `--browsers chromium firefox`. Browser downloads need internet during setup only. See [Playwright installation](https://playwright.dev/python/docs/intro).

Each browser starts an ephemeral loopback server and fresh synthetic data directory, uploads the frozen warehouse PDF through the UI, records a named decision and verifies no change to findings, navigates exact source spans, exercises keyboard tabs and dialog focus/inert/Escape, checks names on visible controls, then damages a PDF and tampers with a run in this temporary database. It checks API-export quarantine, UI/list suppression, scan warnings, mobile overflow and browser errors. The server and browser are closed and scratch data removed. Browser requests outside the test server are blocked. No model client is used.

This is a focused regression harness, not a WCAG audit or a full security certification. PDF tests check the local original-PDF frame, title and provenance; they do not certify the native browser PDF viewer's raster rendering or active-content sandbox. Headless Firefox may download rather than render PDFs. Chrome and Firefox versions are recorded, and backend unit tests independently cover the security guards.
