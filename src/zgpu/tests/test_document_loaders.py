from __future__ import annotations

from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from zgpu.integrations.document_loaders import MAX_UPLOAD_BYTES, DocumentLoadError, extract_document_text


def test_extracts_utf8_text_and_markdown():
    assert extract_document_text("guide.MD", b"\xef\xbb\xbf# zGPU\n\n32-bit ISA") == "# zGPU\n\n32-bit ISA"


@pytest.mark.parametrize(
    ("filename", "data", "status"),
    [
        ("notes.odt", b"data", 415),
        ("notes.txt", b"\xff", 400),
        ("notes.txt", b"  \n", 422),
        ("notes.txt", b"x" * (MAX_UPLOAD_BYTES + 1), 413),
    ],
)
def test_rejects_unsupported_or_invalid_text(filename, data, status):
    with pytest.raises(DocumentLoadError) as error:
        extract_document_text(filename, data)
    assert error.value.status == status


def test_extracts_real_pdf_text():
    pypdf = pytest.importorskip("pypdf")
    from pypdf.generic import DictionaryObject, NameObject

    writer = pypdf.PdfWriter()
    page = writer.add_blank_page(width=300, height=144)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})}
    )
    content = b"BT /F1 12 Tf 20 100 Td (zGPU PDF ingestion works) Tj ET"
    page[NameObject("/Contents")] = writer._add_object(pypdf.generic.DecodedStreamObject())
    stream = page[NameObject("/Contents").get_object()]
    stream.set_data(content)
    output = BytesIO()
    writer.write(output)

    assert "zGPU PDF ingestion works" in extract_document_text("guide.pdf", output.getvalue())


def test_rejects_invalid_pdf():
    pytest.importorskip("pypdf")
    with pytest.raises(DocumentLoadError, match="PDF could not be parsed"):
        extract_document_text("broken.pdf", b"not a pdf")


def _docx_with_document(document_xml: bytes) -> bytes:
    output = BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("word/document.xml", document_xml)
    return output.getvalue()


def test_extracts_docx_paragraphs_tabs_and_line_breaks():
    xml = (
        b'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        b"<w:body><w:p><w:r><w:t>zGPU</w:t></w:r><w:r><w:tab/>"
        b"<w:t>workspace</w:t><w:br/><w:t>local only</w:t></w:r></w:p>"
        b"<w:p><w:r><w:t>Second paragraph</w:t></w:r></w:p></w:body></w:document>"
    )
    extracted = extract_document_text("spec.docx", _docx_with_document(xml))
    assert extracted == "zGPU\tworkspace\nlocal only\nSecond paragraph"


def test_rejects_docx_xml_declarations_and_expansion_bombs():
    with pytest.raises(DocumentLoadError, match="forbidden XML declaration"):
        extract_document_text(
            "unsafe.docx",
            _docx_with_document(b'<!DOCTYPE x [<!ENTITY y "expanded">]><x>&y;</x>'),
        )
    encoded_doctype = '<!DOCTYPE x [<!ENTITY y "expanded">]><x>&y;</x>'.encode("utf-16")
    with pytest.raises(DocumentLoadError, match="forbidden XML declaration"):
        extract_document_text("encoded-unsafe.docx", _docx_with_document(encoded_doctype))

    oversized_xml = b"<x>" + (b" " * (4 * 1024 * 1024)) + b"</x>"
    compressed = _docx_with_document(oversized_xml)
    assert len(compressed) < MAX_UPLOAD_BYTES
    with pytest.raises(DocumentLoadError, match="expanded content") as error:
        extract_document_text("zipbomb.docx", compressed)
    assert error.value.status == 413


def test_rejects_docx_with_too_many_archive_entries():
    output = BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("word/document.xml", b"<x/>")
        for index in range(128):
            archive.writestr(f"extra/{index}.txt", b"")
    with pytest.raises(DocumentLoadError, match="limited to 128 entries") as error:
        extract_document_text("many-parts.docx", output.getvalue())
    assert error.value.status == 413


def test_extracts_html_text_without_script_or_style_content():
    html = b"<html><head><title>Hidden title</title></head><body><h1>zGPU &amp; ISA</h1><script>secret()</script><p>Local docs</p><style>.x{}</style></body></html>"
    extracted = extract_document_text("guide.html", html)
    assert extracted == "zGPU & ISA Local docs"
    assert "secret" not in extracted
