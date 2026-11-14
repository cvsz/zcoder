"""PDF document understanding for Phase 16.

Provides functionality to extract text, tables, and structural information
from PDF documents. Uses pymupdf (fitz) for document analysis.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    import fitz  # PyMuPDF

    HAS_PYMUPPDF = True
except ImportError:
    HAS_PYMUPPDF = False

from zcoder.agent.multi_modal.types import (
    ModalityResult,
)


def extract_pdf_text(
    pdf_path: str | Path,
    pages: list[int] | None = None,
    start_page: int = 1,
    end_page: int | None = None,
) -> dict[str, Any]:
    """
    Extract text content from a PDF document.

    Args:
        pdf_path: Path to the PDF file
        pages: Specific page numbers to extract (1-indexed); if None, uses start_page/end_page
        start_page: Starting page number (1-indexed)
        end_page: Ending page number (1-indexed); None = last page

    Returns:
        Dict with:
        - text: Full extracted text
        - pages: Number of pages processed
        - per_page: Dict mapping page number to extracted text
        - metadata: PDF metadata (title, author, etc.)
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    if not HAS_PYMUPPDF:
        return {
            "text": "",
            "pages": 0,
            "per_page": {},
            "metadata": {},
            "error": "PyMuPDF (fitz) not installed. Install with: pip install pymupdf",
        }

    try:
        doc = fitz.open(pdf_path)
        total_pages = len(doc)

        # Determine which pages to extract
        if pages is not None:
            page_numbers = [p for p in pages if 1 <= p <= total_pages]
        else:
            end = end_page if end_page is not None else total_pages
            page_numbers = list(range(max(1, start_page), min(total_pages, end) + 1))

        per_page: dict[int, str] = {}
        full_text_parts: list[str] = []

        for page_num in page_numbers:
            page_index = page_num - 1  # fitz uses 0-index
            page = doc[page_index]
            text = page.get_text("text")
            per_page[page_num] = text
            full_text_parts.append(text)

        doc.close()

        # Extract metadata
        metadata = doc.metadata if hasattr(doc, "metadata") else {}
        # Normalize metadata keys
        normalized_meta = {}
        for k, v in metadata.items():
            if v:
                normalized_meta[k] = v

        return {
            "text": "\n\n".join(full_text_parts),
            "pages": len(page_numbers),
            "per_page": per_page,
            "metadata": normalized_meta,
        }
    except Exception as e:
        return {
            "text": "",
            "pages": 0,
            "per_page": {},
            "metadata": {},
            "error": str(e),
        }


def extract_pdf_structure(
    pdf_path: str | Path,
) -> dict[str, Any]:
    """
    Extract structural information from a PDF document.

    Returns information about headings, tables, lists, and other structural elements.

    Returns dict with:
    - headings: List of detected headings with level and text
    - tables: Information about detected tables
    - lists: Information about detected lists
    - outline: Document outline/table of contents
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    if not HAS_PYMUPPDF:
        return {
            "headings": [],
            "tables": [],
            "lists": [],
            "outline": [],
            "error": "PyMuPDF (fitz) not installed",
        }

    try:
        doc = fitz.open(pdf_path)
        total_pages = len(doc)

        headings: list[dict[str, Any]] = []
        tables: list[dict[str, Any]] = []
        lists: list[dict[str, Any]] = []
        outline: list[dict[str, Any]] = []

        # Extract outline/toc
        try:
            toc = doc.get_toc()
            for item in toc:
                if len(item) >= 3:
                    level = item[0]  # 1=H1, 2=H2, etc.
                    title = item[2]
                    page = item[3] if len(item) > 3 else None
                    outline.append(
                        {
                            "level": level,
                            "title": title,
                            "page": page,
                        }
                    )
                    # Also add to headings list
                    headings.append(
                        {
                            "level": level,
                            "title": title,
                            "page": page,
                        }
                    )
        except Exception:  # nosec
            pass

        # Extract text and look for structural patterns
        for page_num in range(1, total_pages + 1):
            page_index = page_num - 1
            page = doc[page_index]
            text = page.get_text("text")

            # Simple heading detection (all-caps or numbered headings)
            for line in text.split("\n"):
                line = line.strip()
                if not line:
                    continue
                # Check for heading patterns
                is_heading = (
                    line.isupper()
                    and len(line) > 3
                    and len(line) < 200
                    or line.startswith(("1.", "2.", "3.", "4.", "5.", "Chapter", "Section"))
                    or line.endswith(":")
                    and len(line) < 100
                )
                if is_heading:
                    # Determine level based on patterns
                    level = 1
                    if line.startswith(("2.", "3.", "4.", "5.")):
                        level = 2
                    elif line.startswith(("3.", "4.", "5.")):
                        level = 3
                    headings.append(
                        {
                            "level": level,
                            "title": line,
                            "page": page_num,
                        }
                    )

            # Simple table detection (lines with many tab-separated or pipe-separated values)
            for line in text.split("\n"):
                if "\t" in line and line.count("\t") >= 2:
                    cells = line.split("\t")
                    if len(cells) >= 3:
                        tables.append(
                            {
                                "page": page_num,
                                "row_text": line,
                                "column_count": len(cells),
                            }
                        )

        doc.close()

        # Deduplicate headings by title
        seen = set()
        unique_headings = []
        for h in headings:
            if h["title"] not in seen:
                seen.add(h["title"])
                unique_headings.append(h)

        return {
            "headings": sorted(unique_headings, key=lambda h: (h["page"], h["level"])),
            "tables": tables,
            "lists": lists,  # Basic list detection not implemented yet
            "outline": outline,
        }
    except Exception as e:
        return {
            "headings": [],
            "tables": [],
            "lists": [],
            "outline": [],
            "error": str(e),
        }


def process_pdf_for_ml(
    pdf_path: str | Path,
    pages: list[int] | None = None,
) -> ModalityResult:
    """
    Full PDF processing pipeline for machine learning workflows.

    Extracts text and structure, returns content suitable for multimodal model ingestion.

    Returns ModalityResult with:
    - success: Whether processing succeeded
    - extracted_text: Full extracted text from the PDF
    - confidence: Overall processing confidence
    - error: Error message if processing failed
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        return ModalityResult(
            success=False,
            error=f"PDF file not found: {pdf_path}",
        )

    if not HAS_PYMUPPDF:
        return ModalityResult(
            success=False,
            error="PyMuPDF (fitz) not installed. Install with: pip install pymupdf",
        )

    # Extract text
    text_result = extract_pdf_text(pdf_path, pages=pages)
    extracted_text = text_result.get("text", "")

    # Extract structure
    structure_result = extract_pdf_structure(pdf_path)
    headings = structure_result.get("headings", [])

    # Combine text with structure info
    full_text = extracted_text
    if headings:
        # Prepend structure info
        structure_summary = "\n\nDocument Structure:\n"
        for h in headings[:10]:  # Top 10 headings
            level_markers = {1: "H1", 2: "H2", 3: "H3"}
            structure_summary += f"  {level_markers.get(h['level'], 'H?')}: {h['title']} (p. {h['page']})\n"
        full_text = structure_summary + extracted_text

    success = len(extracted_text.strip()) > 0

    return ModalityResult(
        success=success,
        content=None,  # Will be populated by higher-level orchestrator
        extracted_text=full_text,
        confidence=0.95 if success else 0.3,
        error=text_result.get("error") or structure_result.get("error"),
    )
