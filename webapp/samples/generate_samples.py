"""Generate the synthetic Phase 5 demonstration PDFs deterministically (stdlib only).

Every document is invented for demonstration. Parties are fictional placeholders and no
real contract, invoice or financial record was used. Output bytes contain no timestamps,
so rerunning reproduces identical files and hashes (recorded in samples.json).

Run from the repository root:  python webapp/samples/generate_samples.py
"""
import hashlib
import json
import textwrap
from pathlib import Path

HERE = Path(__file__).resolve().parent
NOTICE = "Synthetic demonstration document for software testing. Not a real agreement or invoice."


def _escape(text):
    text.encode("cp1252")  # Standard Type 1 fonts with WinAnsiEncoding only.
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _page_stream(title, paragraphs):
    ops, y = [], 740
    ops.append("BT /F2 16 Tf 72 {} Td ({}) Tj ET".format(y, _escape(title)))
    y -= 22
    ops.append("BT /F3 9 Tf 72 {} Td ({}) Tj ET".format(y, _escape(NOTICE)))
    y -= 30
    for paragraph in paragraphs:
        for line in textwrap.wrap(paragraph, 84):
            ops.append("BT /F1 11 Tf 72 {} Td ({}) Tj ET".format(y, _escape(line)))
            y -= 16
        y -= 10
    return "\n".join(ops).encode("cp1252")


def build_pdf(pages):
    """pages: list of (title, [paragraph, ...]). Returns deterministic PDF bytes."""
    objects = []

    def add(body):
        objects.append(body)
        return len(objects)

    catalog = add(None)
    pages_id = add(None)
    fonts = [add(b"<< /Type /Font /Subtype /Type1 /BaseFont /" + name + b" /Encoding /WinAnsiEncoding >>")
             for name in (b"Helvetica", b"Helvetica-Bold", b"Helvetica-Oblique")]
    kids = []
    for title, paragraphs in pages:
        stream = _page_stream(title, paragraphs)
        content = add(b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream")
        resources = "<< /Font << /F1 {} 0 R /F2 {} 0 R /F3 {} 0 R >> >>".format(*fonts)
        kids.append(add("<< /Type /Page /Parent {} 0 R /MediaBox [0 0 612 792] /Resources {} /Contents {} 0 R >>"
                        .format(pages_id, resources, content).encode()))
    objects[catalog - 1] = "<< /Type /Catalog /Pages {} 0 R >>".format(pages_id).encode()
    objects[pages_id - 1] = "<< /Type /Pages /Kids [{}] /Count {} >>".format(
        " ".join("{} 0 R".format(k) for k in kids), len(kids)).encode()
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for number, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += "{} 0 obj\n".format(number).encode() + body + b"\nendobj\n"
    xref = len(out)
    out += "xref\n0 {}\n0000000000 65535 f \n".format(len(objects) + 1).encode()
    for offset in offsets:
        out += "{:010d} 00000 n \n".format(offset).encode()
    out += "trailer\n<< /Size {} /Root {} 0 R >>\nstartxref\n{}\n%%EOF\n".format(
        len(objects) + 1, catalog, xref).encode()
    return bytes(out)


DOCUMENTS = {
    "warehouse_agreement.pdf": [
        ("Manpower Support Agreement", [
            "Parties: Example Buyer Private Limited (the Customer) and Example Staffing Private "
            "Limited (the Vendor). Both parties are fictional placeholders.",
            "1. Personnel. The Vendor supplies six warehouse workers for the Customer's distribution site.",
            "2. Supervision. The Customer supervises each worker during every shift.",
            "3. Working hours. Shift rosters are agreed monthly between both parties.",
            "4. Fees. The Customer pays a monthly fee per worker as shown on each invoice.",
        ]),
        ("Manpower Support Agreement (continued)", [
            "5. Term. This agreement runs from 1 April 2026 to 31 March 2027.",
            "6. Records. The Vendor keeps payroll and attendance records for its workers.",
            "7. Signatures. Signed for the Customer and for the Vendor on 15 March 2026.",
        ]),
    ],
    "warehouse_invoice.pdf": [
        ("Invoice SYN-0042", [
            "Issued by Example Staffing Private Limited to Example Buyer Private Limited.",
            "Description: Monthly warehouse personnel support for October 2026.",
            "Quantity: six workers for 26 working days.",
            "Amount before taxes: INR 4,80,000 (synthetic figure).",
        ]),
    ],
    "event_staffing_agreement.pdf": [
        ("Event Staffing Agreement", [
            "Parties: Example Events Private Limited (the Customer) and Example Crew Private "
            "Limited (the Vendor). Both parties are fictional placeholders.",
            "1. Crew. The Vendor supplies ten event workers for the annual conference.",
            "2. Daily coordination. The buyer-side coordinator chooses what each worker does next "
            "and checks progress throughout the shift.",
            "3. Venue. The conference takes place at the Customer's premises over three days.",
            "4. Fees. Fees are charged per crew member per day.",
        ]),
    ],
    "maintenance_agreement.pdf": [
        ("Plant Maintenance Agreement", [
            "Parties: Example Manufacturing Private Limited (the Customer) and Example Technical "
            "Services Private Limited (the Vendor). Both parties are fictional placeholders.",
            "1. Personnel. The Vendor supplies four technicians for the plant maintenance programme.",
            "2. Site supervision. The Customer supervises each technician on site.",
            "3. Work allocation. The Vendor directs all technicians and allocates their daily tasks.",
            "4. Fees. Fees are charged monthly in arrears.",
        ]),
    ],
}


def main():
    hashes = {}
    for name, pages in DOCUMENTS.items():
        data = build_pdf(pages)
        (HERE / name).write_bytes(data)
        hashes[name] = hashlib.sha256(data).hexdigest()
        print(name, hashes[name])
    return hashes


if __name__ == "__main__":
    main()
