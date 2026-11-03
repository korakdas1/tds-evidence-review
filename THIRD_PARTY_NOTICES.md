# Optional PDF dependencies and fixtures

The PDF path pins **pypdf 6.21.4**, a maintained Python PDF parser under the BSD 3-Clause license. It requires Python 3.9+. The library is installed from PyPI and is not vendored here. Retain its license/copyright notices if redistributing it. This notice does not introduce or change a project-wide license.

Sources: [pypdf package](https://pypi.org/project/pypdf/6.21.4/), [upstream license](https://github.com/py-pdf/pypdf/blob/main/LICENSE), [text-extraction limitations](https://pypdf.readthedocs.io/en/stable/user/extract-text.html).

The frozen synthetic fixtures were authored with ReportLab 5.1.0 (BSD license), Pillow 13.0.0 (MIT-CMU license) and pypdf 6.21.4, on Python 3.13.12. ReportLab and Pillow are authoring-only dependencies; neither is required to run ingestion or tests. No proprietary font files, real contracts or financial documents were copied into fixtures. Poppler rendered temporary previews during development; it is not invoked by runtime ingestion and is not distributed here.

Sources: [ReportLab](https://pypi.org/project/reportlab/5.1.0/), [Pillow](https://pypi.org/project/pillow/13.0.0/).

The optional generator `tests/fixtures/generate_pdf_v1.py` requires the authoring versions above and a NEW destination directory. Never regenerate the frozen `pdf_v1` suite in place. Normal tests consume committed bytes without authoring dependencies. The generator's `add_js` call emitted an upstream deprecation warning; it is used only to author an intentionally inert security fixture, not by runtime ingestion.

`encrypted.pdf` uses the public synthetic password `synthetic-test-password` and RC4-128 solely to test rejection. It is not an encryption recommendation. `active_content.pdf` deliberately contains an alert action to test detection/nonexecution; ingestion flags it and never executes it. All fixture content is synthetic. The parser does not perform OCR or guarantee visual reading order, and its configured limits do not constitute process isolation for hostile documents.
