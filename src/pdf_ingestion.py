"""Local, bounded PDF text extraction and exact page-text provenance. No OCR/network."""
import hashlib
import io
import logging
import re
from contextlib import contextmanager
from pathlib import Path

MAX_BYTES = 5 * 1024 * 1024
MAX_PAGES = 20
MAX_PAGE_CHARS = 100000
MAX_TOTAL_CHARS = 200000
MAX_STREAM_BYTES = 2 * 1024 * 1024


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def normalized(text):
    return " ".join(text.split())


def compile_text(pages):
    """Whitespace-only normalization; raw pages + token/whitespace spans remain intact."""
    pieces, segments, offset = [], [], 0
    for page in pages:
        tokens = list(re.finditer(r"\S+", page["text"]))
        if not tokens:
            continue
        if pieces:
            pieces.append(" ")  # Synthetic page separator: deliberately no page coordinates.
            offset += 1
        previous = None
        for token in tokens:
            if previous is not None:
                pieces.append(" ")
                segments.append(dict(page_number=page["page_number"], text_start=offset,
                                     text_end=offset + 1, page_start=previous, page_end=token.start(),
                                     kind="WHITESPACE"))
                offset += 1
            value = token.group()
            pieces.append(value)
            segments.append(dict(page_number=page["page_number"], text_start=offset,
                                 text_end=offset + len(value), page_start=token.start(),
                                 page_end=token.end(), kind="COPY"))
            offset += len(value)
            previous = token.end()
    return "".join(pieces), segments


@contextmanager
def quiet_parser():
    # Parser diagnostics can contain untrusted document strings. Return bounded codes instead.
    logger = logging.getLogger("pypdf")
    handlers, propagate = logger.handlers, logger.propagate
    logger.handlers, logger.propagate = [logging.NullHandler()], False
    try:
        yield
    finally:
        logger.handlers, logger.propagate = handlers, propagate


def read_pdf(path, max_bytes=MAX_BYTES, max_pages=MAX_PAGES):
    path = Path(path)
    doc = dict(schema_version="pdf-text-v1", name=path.name, document_id=None, file_sha256=None,
               status="REJECTED", issues=[], pages=[], text="", segments=[],
               human_review_required=True, extractor=None,
               normalization="Whitespace runs collapse to one space; page separators are synthetic spaces. Raw page text is retained.",
               limits=dict(file_bytes=max_bytes, pages=max_pages, page_chars=MAX_PAGE_CHARS,
                           total_chars=MAX_TOTAL_CHARS, decoded_page_stream_bytes=MAX_STREAM_BYTES))
    def reject(code):
        doc["issues"].append(code)
        return doc
    if max_bytes <= 0 or max_pages <= 0:
        return reject("INVALID_LIMIT")
    try:
        if not path.is_file():
            return reject("FILE_UNAVAILABLE")
        if path.stat().st_size > max_bytes:
            return reject("FILE_SIZE_LIMIT")
        with path.open("rb") as stream:
            data = stream.read(max_bytes + 1)
    except OSError:
        return reject("FILE_UNAVAILABLE")
    if len(data) > max_bytes:
        return reject("FILE_SIZE_LIMIT")
    doc["file_sha256"] = sha256(data)
    doc["document_id"] = "sha256:" + doc["file_sha256"]
    if path.suffix.lower() != ".pdf" or not data.startswith(b"%PDF-"):
        return reject("UNSUPPORTED_FILE")
    try:
        import pypdf
    except ImportError:
        return reject("PDF_DEPENDENCY_MISSING_INSTALL_REQUIREMENTS_PDF")
    doc["extractor"] = "pypdf " + pypdf.__version__
    try:
        with quiet_parser():
            reader = pypdf.PdfReader(io.BytesIO(data), strict=True)
            if reader.is_encrypted:
                return reject("ENCRYPTED_PDF_NOT_SUPPORTED")
            if len(reader.pages) > max_pages:
                return reject("PAGE_COUNT_LIMIT")
            if not reader.pages:
                return reject("NO_PAGES")
            root = reader.trailer["/Root"]
            names = root.get("/Names", {})
            names = names.get_object() if hasattr(names, "get_object") else names
            if root.get("/OpenAction") or root.get("/AA") or names.get("/JavaScript"):
                doc["issues"].append("ACTIVE_CONTENT_NOT_EXECUTED")
            total = 0
            for number, page in enumerate(reader.pages, 1):
                item = dict(page_number=number, text="", text_sha256=None, issues=[],
                            status="NEEDS_DOCUMENT_REVIEW", order_check="NOT_CHECKED", alternate_layout_text=None)
                try:
                    stream = page.get_contents()
                    if stream is not None and len(stream.get_data()) > MAX_STREAM_BYTES:
                        item["issues"].append("CONTENT_STREAM_LIMIT")
                    else:
                        raw = page.extract_text()
                        if not isinstance(raw, str):
                            raise ValueError("No text string")
                        raw.encode("utf-8")  # Reject undecodable surrogate output at the page boundary.
                        if len(raw) > MAX_PAGE_CHARS or total + len(raw) > MAX_TOTAL_CHARS:
                            item["issues"].append("TEXT_SIZE_LIMIT")
                        else:
                            item["text"] = raw
                            total += len(raw)
                            if not raw.strip():
                                item["issues"].append("NO_SELECTABLE_TEXT_OCR_OR_MANUAL_REVIEW")
                            elif not any(ch.isalnum() for ch in raw) or "\ufffd" in raw or any(ord(ch) < 32 and ch not in "\n\r\t\f" for ch in raw):
                                item["issues"].append("UNREADABLE_TEXT")
                            if raw.strip():
                                layout = page.extract_text(extraction_mode="layout", layout_mode_strip_rotated=False)
                                if not isinstance(layout, str) or len(layout) > MAX_PAGE_CHARS:
                                    item["issues"].append("LAYOUT_EXTRACTION_UNAVAILABLE")
                                else:
                                    layout.encode("utf-8")
                                    item["alternate_layout_text"] = layout
                                    if normalized(raw) != normalized(layout):
                                        item["order_check"] = "DISAGREES"
                                        item["issues"].append("EXTRACTION_ORDER_DISAGREEMENT")
                                    else:
                                        item["order_check"] = "AGREES_NOT_PROOF_OF_VISUAL_ORDER"
                            resources = page.get("/Resources", {})
                            resources = resources.get_object() if hasattr(resources, "get_object") else resources
                            objects = resources.get("/XObject", {})
                            objects = objects.get_object() if hasattr(objects, "get_object") else objects
                            if any(obj.get_object().get("/Subtype") == "/Image" for obj in objects.values()):
                                item["issues"].append("IMAGE_CONTENT_REQUIRES_VISUAL_REVIEW")
                            if page.get("/Rotate", 0) % 360:
                                item["issues"].append("ROTATED_PAGE_REQUIRES_VISUAL_REVIEW")
                            if page.get("/AA") or any(a.get_object().get("/A") for a in page.get("/Annots", [])):
                                item["issues"].append("ACTIVE_CONTENT_NOT_EXECUTED")
                except Exception:
                    # Third-party parser errors remain per-page failures, never invented text.
                    item["issues"].append("PAGE_EXTRACTION_FAILED")
                item["text_sha256"] = sha256(item["text"].encode("utf-8"))
                item["status"] = "NEEDS_DOCUMENT_REVIEW" if item["issues"] else "EXTRACTED"
                doc["pages"].append(item)
    except Exception:
        return reject("MALFORMED_OR_UNSUPPORTED_PDF")
    doc["text"], doc["segments"] = compile_text(doc["pages"])
    doc["text_sha256"] = sha256(doc["text"].encode("utf-8"))
    doc["status"] = "NEEDS_DOCUMENT_REVIEW" if doc["issues"] or any(p["issues"] for p in doc["pages"]) else "EXTRACTED"
    return doc


def verify_location(document, location):
    """Verify a claimed page-text span; coordinates are not PDF drawing/glyph coordinates."""
    try:
        number, start, end = location["page_number"], location["start"], location["end"]
        if not all(type(x) is int for x in (number, start, end)) or not 1 <= number <= len(document["pages"]):
            return False
        page = document["pages"][number - 1]
        text = page["text"]
        context = location["context"]
        return (location["document_id"] == document["document_id"]
                and location["file_sha256"] == document["file_sha256"]
                and location["document_name"] == document["name"]
                and page["page_number"] == number
                and sha256(text.encode("utf-8")) == page["text_sha256"]
                and 0 <= start < end <= len(text) and text[start:end] == location["quote"]
                and type(context["start"]) is int and type(context["end"]) is int
                and 0 <= context["start"] <= start < end <= context["end"] <= len(text)
                and text[context["start"]:context["end"]] == context["text"])
    except (KeyError, TypeError, IndexError, AttributeError, UnicodeError):
        return False


def map_span(document, start, end):
    """Map one normalized span to real page slices; never assign coordinates to separators."""
    unresolved = dict(status="UNRESOLVED", fragments=[], requires_human_review=True)
    try:
        text, segments = compile_text(document["pages"])
        if (text != document["text"] or segments != document["segments"]
                or sha256(text.encode("utf-8")) != document["text_sha256"]):
            return unresolved
        if not all(type(x) is int for x in (start, end)) or not 0 <= start < end <= len(text):
            return unresolved
        groups, covered = {}, []
        for s in segments:
            lo, hi = max(start, s["text_start"]), min(end, s["text_end"])
            if lo >= hi:
                continue
            a = s["page_start"] + lo - s["text_start"] if s["kind"] == "COPY" else s["page_start"]
            b = s["page_start"] + hi - s["text_start"] if s["kind"] == "COPY" else s["page_end"]
            group = groups.setdefault(s["page_number"], [a, b])
            group[0], group[1] = min(group[0], a), max(group[1], b)
            covered.append((lo, hi))
        cursor = start
        for lo, hi in covered:
            if text[cursor:lo].strip():
                return unresolved
            cursor = hi
        if text[cursor:end].strip() or not groups:
            return unresolved
        fragments = []
        for number, (a, b) in groups.items():
            raw = document["pages"][number - 1]["text"]
            left, right = max(0, a - 80), min(len(raw), b + 80)
            fragment = dict(document_id=document["document_id"], file_sha256=document["file_sha256"],
                            document_name=document["name"], page_number=number, start=a, end=b,
                            quote=raw[a:b], context=dict(start=left, end=right, text=raw[left:right]))
            if not verify_location(document, fragment):
                return unresolved
            fragments.append(fragment)
        if normalized(" ".join(f["quote"] for f in fragments)) != normalized(text[start:end]):
            return unresolved
        return dict(status="MAPPED_TO_EXTRACTED_TEXT", text_start=start, text_end=end,
                    normalized_quote=text[start:end], fragments=fragments, cross_page=len(groups) > 1,
                    requires_human_review=True)
    except (KeyError, TypeError, IndexError, AttributeError, UnicodeError):
        return unresolved


def locate_quote(document, quote, positions=None):
    from .evidence import quote_positions
    expected = quote_positions(document["text"], quote)
    if not expected or positions is not None and positions != expected:
        return dict(status="UNRESOLVED", occurrences=[], requires_human_review=True)
    mapped = [map_span(document, p["start"], p["end"]) for p in expected]
    if any(m["status"] == "UNRESOLVED" for m in mapped):
        return dict(status="UNRESOLVED", occurrences=[], requires_human_review=True)
    return dict(status="MAPPED_TO_EXTRACTED_TEXT", occurrences=mapped, requires_human_review=True)
