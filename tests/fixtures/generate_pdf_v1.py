"""Author synthetic PDF fixtures into a NEW directory; never overwrite the frozen suite.

Authoring only: reportlab 5.1.0 (with Pillow) and pypdf 6.21.4.
Application/tests need only pypdf and the committed fixtures, not ReportLab.
"""
import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw
from pypdf import PdfReader, PdfWriter
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen.canvas import Canvas
from reportlab.lib.utils import ImageReader


def generate(destination):
    destination.mkdir(parents=True, exist_ok=False)
    entries = []

    def pdf(name, pages, expected="EXTRACTED", note=""):
        path = destination / name
        canvas = Canvas(str(path), pagesize=(612, 792), invariant=True, pageCompression=0)
        canvas.setTitle("Synthetic TDS ingestion test fixture")
        canvas.setAuthor("Synthetic fixture generator")
        for lines in pages:
            canvas.setFont("Helvetica", 12)
            for index, line in enumerate(lines):
                canvas.drawString(50, 750 - index * 22, line)
            canvas.showPage()
        canvas.save()
        entries.append(dict(file=name, expected_status=expected, note=note))
        return path

    pdf("supported.pdf", [["Vendor supplies workers.", "Customer supervises each worker."]])
    pdf("multipage.pdf", [["Vendor supplies workers."], ["Customer supervises each worker."]])
    pdf("wrapped.pdf", [["Vendor    supplies workers.", "Customer directly", "supervises each worker."]])
    pdf("cross_page.pdf", [["Vendor supplies workers. Customer directly"], ["supervises each worker."]], note="Cross-page quote must retain two real spans and require document review.")
    pdf("negation_lines.pdf", [["Vendor supplies workers.", "Customer must not", "supervise workers."]])
    pdf("negation_pages.pdf", [["Vendor supplies workers. Customer must not"], ["supervise workers."]])
    order = destination / "reading_order.pdf"
    c = Canvas(str(order), pagesize=(612, 792), invariant=True, pageCompression=0)
    c.setAuthor("Synthetic fixture generator")
    c.setFont("Helvetica", 12)
    c.drawString(50, 750, "Vendor supplies workers.")
    prefix = "Customer does "
    c.drawString(50, 710, prefix)
    c.drawString(50 + stringWidth(prefix + "not ", "Helvetica", 12), 710, "supervise workers.")
    # Draw the negation last in stream order, but between the other words visually.
    c.drawString(50 + stringWidth(prefix, "Helvetica", 12), 710, "not ")
    c.showPage(); c.save()
    entries.append(dict(file=order.name, expected_status="NEEDS_DOCUMENT_REVIEW", note="Visually Customer does not supervise; content-stream order displaces not. Deliberate reading-order hazard."))
    pdf("missing.pdf", [["Vendor supplies workers.", "The parties agree monthly billing dates."]])
    pdf("conflicting.pdf", [["Vendor supplies workers.", "Customer supervises each worker."], ["Supplier supervises each worker."]])
    pdf("empty.pdf", [[]], "NEEDS_DOCUMENT_REVIEW", "Deliberately blank; never invent text.")
    image = Image.new("RGB", (900, 150), "white")
    ImageDraw.Draw(image).text((20, 50), "SYNTHETIC SCAN: Customer supervises workers.", fill="black", font_size=24)
    c = Canvas(str(destination / "scanned.pdf"), pagesize=(612, 792), invariant=True)
    c.drawImage(ImageReader(image), 50, 620, width=510, height=85)
    c.showPage(); c.save()
    entries.append(dict(file="scanned.pdf", expected_status="NEEDS_DOCUMENT_REVIEW", note="Synthetic raster only; requires OCR/manual review. No real document image."))
    pdf("partial.pdf", [["Vendor supplies workers.", "Customer supervises each worker."], []], "NEEDS_DOCUMENT_REVIEW", "Missing second page text blocks reliance on the first page alone.")
    writer = PdfWriter()
    writer.append(PdfReader(destination / "supported.pdf"))
    writer.encrypt("synthetic-test-password", algorithm="RC4-128")
    writer.write(destination / "encrypted.pdf")
    entries.append(dict(file="encrypted.pdf", expected_status="REJECTED", note="Public fixture password, not a secret. Legacy encryption used only to test rejection without crypto extras."))
    (destination / "corrupted.pdf").write_bytes(b"%PDF-1.7\nINTENTIONALLY CORRUPTED SYNTHETIC FIXTURE\n%%EOF\n")
    entries.append(dict(file="corrupted.pdf", expected_status="REJECTED", note="Deliberately not a valid PDF."))
    (destination / "unsupported.txt").write_text("Synthetic plain text; not a PDF.\n")
    entries.append(dict(file="unsupported.txt", expected_status="REJECTED", note="Wrong format."))
    pdf("invoice.pdf", [["SYNTHETIC INVOICE", "Description: monthly personnel support.", "Payment terms: see contract."]], note="Extract for inspection only; transaction fields remain manually supplied.")
    writer = PdfWriter()
    reader = PdfReader(destination / "supported.pdf")
    writer.add_page(reader.pages[0].rotate(90))
    writer.write(destination / "rotated.pdf")
    entries.append(dict(file="rotated.pdf", expected_status="NEEDS_DOCUMENT_REVIEW", note="Rotated page requires visual inspection."))
    writer = PdfWriter()
    writer.append(PdfReader(destination / "supported.pdf"))
    writer.add_js('app.alert("SYNTHETIC FIXTURE - DO NOT EXECUTE");')
    writer.write(destination / "active_content.pdf")
    entries.append(dict(file="active_content.pdf", expected_status="NEEDS_DOCUMENT_REVIEW", note="Intentional inert JavaScript test payload; parser must never execute it."))
    pdf("unreadable.pdf", [["\u25a0\u25a0\u25a0"]], "NEEDS_DOCUMENT_REVIEW", "Deliberate non-language glyphs, not meaningful contract text.")
    for entry in entries:
        entry["sha256"] = hashlib.sha256((destination / entry["file"]).read_bytes()).hexdigest()
    metadata = dict(id="PDF_DEMO_SYNTHETIC", invoice_description="Monthly personnel support (manually supplied).",
                    payer_type="Indian resident private company", payee_residency="India resident",
                    payee_legal_form="Indian resident private company", credit_date="2026-10-10", payment_date="2026-10-20")
    (destination / "transaction.json").write_text(json.dumps(metadata, indent=2) + "\n")
    manifest = dict(version="pdf-fixtures-v1", construction="Synthetic source-informed development fixtures; expected extraction/review outcomes authored before ingestion evaluation. Not independent model or legal ground truth.",
                    authoring_versions={"reportlab":"5.1.0", "pypdf":"6.21.4"}, fixtures=entries,
                    transaction_sha256=hashlib.sha256((destination / "transaction.json").read_bytes()).hexdigest())
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print("Created", len(entries), "fixtures in", destination)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    generate(parser.parse_args().destination)
