"""Bounded, local-only document text extraction for the zGPU knowledge library."""

from __future__ import annotations

from html.parser import HTMLParser
from io import BytesIO
from pathlib import Path
from typing import ClassVar
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile


class DocumentLoadError(ValueError):
    """A document is unsupported, malformed, or exceeds extraction limits."""

    def __init__(self, message: str, status: int = 400):
        self.status = status
        super().__init__(message)


MAX_UPLOAD_BYTES = 512 * 1024
MAX_EXTRACTED_BYTES = 262_144
MAX_PDF_PAGES = 100
MAX_DOCX_MEMBERS = 128
MAX_DOCX_UNCOMPRESSED_BYTES = 4 * 1024 * 1024
TEXT_EXTENSIONS = {".txt", ".md", ".markdown"}


def extract_document_text(filename: str, data: bytes) -> str:
    """Extract UTF-8 text from supported local files without network access."""
    if not isinstance(filename, str) or not filename or len(filename) > 255 or "\x00" in filename:
        raise DocumentLoadError("filename must contain 1 to 255 characters")
    if not isinstance(data, bytes) or not data:
        raise DocumentLoadError("uploaded file must not be empty")
    if len(data) > MAX_UPLOAD_BYTES:
        raise DocumentLoadError(f"uploaded file must be at most {MAX_UPLOAD_BYTES} bytes", status=413)

    extension = Path(filename).suffix.lower()
    if extension in TEXT_EXTENSIONS:
        try:
            text = data.decode("utf-8-sig").strip()
        except UnicodeDecodeError as exc:
            raise DocumentLoadError("text documents must use UTF-8 encoding") from exc
    elif extension == ".pdf":
        text = _extract_pdf_text(data)
    elif extension == ".docx":
        text = _extract_docx_text(data)
    elif extension in {".html", ".htm"}:
        text = _extract_html_text(data)
    else:
        raise DocumentLoadError(
            "supported document types are .txt, .md, .markdown, .html, .htm, .docx, and .pdf", status=415
        )

    if not text:
        raise DocumentLoadError("document contains no extractable text", status=422)
    if len(text.encode("utf-8")) > MAX_EXTRACTED_BYTES:
        raise DocumentLoadError(
            f"extracted text must be at most {MAX_EXTRACTED_BYTES} UTF-8 bytes", status=413
        )
    return text


class _TextHTMLParser(HTMLParser):
    """Collect visible HTML text while dropping executable and non-content elements."""

    _IGNORED: ClassVar[set[str]] = {
        "head",
        "iframe",
        "noscript",
        "object",
        "script",
        "style",
        "svg",
        "template",
    }
    _BLOCKS: ClassVar[set[str]] = {
        "article",
        "blockquote",
        "br",
        "dd",
        "div",
        "h1",
        "h2",
        "h3",
        "h4",
        "li",
        "p",
        "section",
        "tr",
    }

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.ignored_depth = 0

    def handle_starttag(self, tag: str, attrs):
        if tag in self._IGNORED:
            self.ignored_depth += 1
        elif not self.ignored_depth and tag in self._BLOCKS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str):
        if tag in self._IGNORED and self.ignored_depth:
            self.ignored_depth -= 1
        elif not self.ignored_depth and tag in self._BLOCKS:
            self.parts.append("\n")

    def handle_data(self, data: str):
        if not self.ignored_depth:
            self.parts.append(data)


def _extract_html_text(data: bytes) -> str:
    try:
        html = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise DocumentLoadError("HTML documents must use UTF-8 encoding") from exc
    parser = _TextHTMLParser()
    try:
        parser.feed(html)
        parser.close()
    except Exception as exc:
        raise DocumentLoadError("HTML could not be parsed") from exc
    return " ".join(" ".join(parser.parts).split())


def _extract_docx_text(data: bytes) -> str:
    document_path = "word/document.xml"
    try:
        with ZipFile(BytesIO(data)) as archive:
            members = archive.infolist()
            if len(members) > MAX_DOCX_MEMBERS:
                raise DocumentLoadError(
                    f"DOCX archives are limited to {MAX_DOCX_MEMBERS} entries", status=413
                )
            if sum(member.file_size for member in members) > MAX_DOCX_UNCOMPRESSED_BYTES:
                raise DocumentLoadError(
                    f"DOCX expanded content is limited to {MAX_DOCX_UNCOMPRESSED_BYTES} bytes", status=413
                )
            if any(member.flag_bits & 0x1 for member in members):
                raise DocumentLoadError("encrypted DOCX archives are not supported", status=415)
            documents = [member for member in members if member.filename == document_path]
            if len(documents) != 1:
                raise DocumentLoadError("DOCX archive is missing its main document part")
            if documents[0].file_size > MAX_DOCX_UNCOMPRESSED_BYTES:
                raise DocumentLoadError("DOCX document part is too large", status=413)
            with archive.open(documents[0]) as document:
                xml = document.read(MAX_DOCX_UNCOMPRESSED_BYTES + 1)
    except DocumentLoadError:
        raise
    except (BadZipFile, KeyError, RuntimeError, OSError) as exc:
        raise DocumentLoadError("DOCX archive could not be read") from exc

    if len(xml) > MAX_DOCX_UNCOMPRESSED_BYTES:
        raise DocumentLoadError("DOCX document part is too large", status=413)
    normalized_xml = xml.replace(b"\x00", b"").lower()
    if b"<!doctype" in normalized_xml or b"<!entity" in normalized_xml:
        raise DocumentLoadError("DOCX document contains a forbidden XML declaration", status=415)
    try:
        root = ElementTree.fromstring(xml)  # nosec B314 - XML pre-validated for DOCTYPE/ENTITY
    except ElementTree.ParseError as exc:
        raise DocumentLoadError("DOCX document XML is malformed") from exc

    namespace = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    paragraphs = []
    for paragraph in root.iter(f"{namespace}p"):
        parts = []
        for element in paragraph.iter():
            if element.tag == f"{namespace}t" and element.text:
                parts.append(element.text)
            elif element.tag == f"{namespace}tab":
                parts.append("\t")
            elif element.tag == f"{namespace}br":
                parts.append("\n")
        content = "".join(parts).strip()
        if content:
            paragraphs.append(content)
    return "\n".join(paragraphs)


def _extract_pdf_text(data: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise DocumentLoadError("PDF support requires the optional zGPU documents extra", status=503) from exc

    try:
        reader = PdfReader(BytesIO(data), strict=False)
        if reader.is_encrypted:
            raise DocumentLoadError("encrypted PDF documents are not supported", status=415)
        if len(reader.pages) > MAX_PDF_PAGES:
            raise DocumentLoadError(f"PDF documents are limited to {MAX_PDF_PAGES} pages", status=413)

        pages = []
        extracted_bytes = 0
        for page in reader.pages:
            page_text = page.extract_text() or ""
            extracted_bytes += len(page_text.encode("utf-8"))
            if extracted_bytes > MAX_EXTRACTED_BYTES:
                raise DocumentLoadError(
                    f"extracted text must be at most {MAX_EXTRACTED_BYTES} UTF-8 bytes", status=413
                )
            if page_text.strip():
                pages.append(page_text.strip())
    except DocumentLoadError:
        raise
    except Exception as exc:
        raise DocumentLoadError("PDF could not be parsed") from exc
    return "\n\n".join(pages)
