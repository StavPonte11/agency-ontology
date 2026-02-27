"""
PDF text processor for the Agency Ontology pipeline.
Primary: pdfplumber (layout-aware, table detection)
Fallback: Tesseract OCR with Hebrew language pack (heb+eng)

Designed for Hebrew military documents which may contain:
- Nikud (diacritics)
- Mixed Hebrew/English text
- Military tables with classified codes
- Scanned pages requiring OCR
"""
from __future__ import annotations

import io
import logging
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Hebrew Unicode range: U+0590–U+05FF + U+FB1D–U+FB4F
HEBREW_PATTERN = re.compile(r"[\u0590-\u05FF\uFB1D-\uFB4F]")
# Nikud (diacritics): U+05B0–U+05C7
NIKUD_PATTERN = re.compile(r"[\u05B0-\u05C7]")
# Military abbreviation patterns in Hebrew: word.word or ר"מ, מפ"ג, etc.
MILITARY_ABBR_PATTERN = re.compile(r'[\u05D0-\u05EA]+"[\u05D0-\u05EA]+')


@dataclass
class TextChunk:
    """A text chunk ready for LLM extraction."""

    chunk_id: str
    document_id: str
    content: str           # Normalized text (nikud stripped, whitespace cleaned)
    content_raw: str       # Original text before normalization
    section_title: Optional[str]
    page_range: str        # e.g., "1-3"
    char_count: int
    has_hebrew: bool
    has_tables: bool
    extracted_via: str     # "pdfplumber" | "tesseract"


class PDFProcessor:
    """
    Extracts and chunks text from PDF source documents.
    Returns chunks ready for LLM extraction.
    """

    def __init__(
        self,
        chunk_size: int = 1500,
        chunk_overlap: int = 200,
        min_text_length: int = 100,
        ocr_language: str = "heb+eng",   # Tesseract language for Hebrew military docs
    ) -> None:
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap
        self._min_text_length = min_text_length
        self._ocr_language = ocr_language

    def process(
        self,
        pdf_bytes: bytes,
        document_id: str,
        document_title: str,
    ) -> list[TextChunk]:
        """
        Extract text from PDF bytes and return chunks.
        Falls back to Tesseract OCR if text extraction yields insufficient text.
        """
        try:
            chunks = self._extract_with_pdfplumber(pdf_bytes, document_id, document_title)
            # If extraction was too sparse, fall back to OCR
            total_text = sum(c.char_count for c in chunks)
            if total_text < self._min_text_length and chunks:
                logger.info(
                    f"Sparse text ({total_text} chars) for {document_title} — trying OCR"
                )
                ocr_chunks = self._extract_with_tesseract(pdf_bytes, document_id, document_title)
                if sum(c.char_count for c in ocr_chunks) > total_text:
                    return ocr_chunks
            return chunks

        except Exception as exc:
            logger.error(f"pdfplumber failed for {document_title}: {exc}, trying OCR")
            try:
                return self._extract_with_tesseract(pdf_bytes, document_id, document_title)
            except Exception as ocr_exc:
                logger.error(f"OCR also failed for {document_title}: {ocr_exc}")
                return []

    def _extract_with_pdfplumber(
        self, pdf_bytes: bytes, document_id: str, document_title: str
    ) -> list[TextChunk]:
        import pdfplumber

        chunks: list[TextChunk] = []
        current_text: list[str] = []
        current_pages: list[int] = []
        current_section: Optional[str] = None
        has_tables = False

        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page_num, page in enumerate(pdf.pages, start=1):
                # Extract tables separately and append as structured text
                tables = page.extract_tables()
                if tables:
                    has_tables = True
                    for table in tables:
                        table_text = self._table_to_text(table)
                        current_text.append(table_text)

                # Extract regular text, excluding table bounding boxes
                text = page.extract_text(x_tolerance=3, y_tolerance=3) or ""
                text = self._normalize_hebrew(text)

                # Detect section headers (common military doc pattern: bold short line)
                lines = text.splitlines()
                for line in lines:
                    stripped = line.strip()
                    if self._is_section_header(stripped):
                        # Flush current chunk before new section
                        if current_text and len(" ".join(current_text)) > 50:
                            chunk = self._make_chunk(
                                document_id=document_id,
                                text_parts=current_text,
                                pages=current_pages,
                                section=current_section,
                                chunk_index=len(chunks),
                                extracted_via="pdfplumber",
                                has_tables=has_tables,
                            )
                            if chunk:
                                chunks.append(chunk)
                            current_text = []
                            current_pages = []
                            has_tables = False
                        current_section = stripped
                    else:
                        current_text.append(stripped)

                current_pages.append(page_num)

                # Chunk when we exceed target size
                combined = " ".join(current_text)
                if len(combined) >= self._chunk_size:
                    chunk = self._make_chunk(
                        document_id=document_id,
                        text_parts=current_text,
                        pages=current_pages,
                        section=current_section,
                        chunk_index=len(chunks),
                        extracted_via="pdfplumber",
                        has_tables=has_tables,
                    )
                    if chunk:
                        chunks.append(chunk)
                    # Keep overlap from the end
                    overlap_text = combined[-self._chunk_overlap:]
                    current_text = [overlap_text]
                    current_pages = [page_num]
                    has_tables = False

        # Flush remaining
        if current_text:
            chunk = self._make_chunk(
                document_id=document_id,
                text_parts=current_text,
                pages=current_pages,
                section=current_section,
                chunk_index=len(chunks),
                extracted_via="pdfplumber",
                has_tables=has_tables,
            )
            if chunk:
                chunks.append(chunk)

        return chunks

    def _extract_with_tesseract(
        self, pdf_bytes: bytes, document_id: str, document_title: str
    ) -> list[TextChunk]:
        """OCR fallback using Tesseract with Hebrew language pack."""
        import pdf2image
        import pytesseract

        chunks: list[TextChunk] = []
        images = pdf2image.convert_from_bytes(pdf_bytes, dpi=200)

        for page_num, image in enumerate(images, start=1):
            # Tesseract: use Hebrew + English, enable page segmentation mode 6 (single block)
            custom_config = f"--oem 3 --psm 6 -l {self._ocr_language}"
            text = pytesseract.image_to_string(image, config=custom_config)
            text = self._normalize_hebrew(text)

            if len(text.strip()) < 20:
                continue

            # Split into chunks
            for i in range(0, len(text), self._chunk_size - self._chunk_overlap):
                segment = text[i: i + self._chunk_size]
                if len(segment.strip()) < 20:
                    continue
                chunks.append(
                    TextChunk(
                        chunk_id=f"{document_id}::ocr::p{page_num}::c{len(chunks)}",
                        document_id=document_id,
                        content=segment,
                        content_raw=segment,
                        section_title=None,
                        page_range=str(page_num),
                        char_count=len(segment),
                        has_hebrew=bool(HEBREW_PATTERN.search(segment)),
                        has_tables=False,
                        extracted_via="tesseract",
                    )
                )

        return chunks

    def _normalize_hebrew(self, text: str) -> str:
        """
        Normalize Hebrew military text:
        1. Strip nikud (diacritics) — military docs often have them, LLMs don't need them
        2. Normalize Unicode (NFC)
        3. Clean whitespace
        4. Preserve military abbreviations (ר"מ, מפ"ג patterns)
        """
        if not text:
            return text
        # Strip nikud
        text = NIKUD_PATTERN.sub("", text)
        # Unicode normalization
        text = unicodedata.normalize("NFC", text)
        # Clean control characters except newlines and tabs
        text = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]", "", text)
        # Collapse multiple blank lines
        text = re.sub(r"\n{3,}", "\n\n", text)
        # Clean excessive spaces
        text = re.sub(r"[ \t]{2,}", " ", text)
        return text.strip()

    def _is_section_header(self, line: str) -> bool:
        """
        Heuristic: detect section headers in military Hebrew documents.
        Headers are typically: short, ALL CAPS Hebrew, or numbered (e.g., 1. or א.)
        """
        if not line or len(line) > 80:
            return False
        # Numbered sections: "1.", "1.1", "א.", "סעיף 1"
        if re.match(r"^(\d+\.|\u05D0\.-\u05EA\.|\d+\.\d+)", line):
            return True
        # Hebrew section keywords
        military_headers = [
            "נוהל", "פרק", "סעיף", "חלק", "נספח", "מבוא", "רקע", "הגדרות",
            "אחריות", "הוראות", "כללי", "מטרה", "הפעלה"
        ]
        for kw in military_headers:
            if line.startswith(kw) or line.endswith(kw):
                return True
        # All-caps short line (likely a title)
        if len(line) <= 40 and line == line.upper() and any(c.isalpha() for c in line):
            return True
        return False

    def _table_to_text(self, table: list[list[Optional[str]]]) -> str:
        """Convert a pdfplumber table to pipe-delimited text for LLM consumption."""
        rows = []
        for row in table:
            cells = [str(cell or "").strip() for cell in row]
            rows.append(" | ".join(cells))
        return "\n".join(rows)

    def _make_chunk(
        self,
        document_id: str,
        text_parts: list[str],
        pages: list[int],
        section: Optional[str],
        chunk_index: int,
        extracted_via: str,
        has_tables: bool,
    ) -> Optional[TextChunk]:
        content = " ".join(text_parts).strip()
        if len(content) < 30:
            return None
        page_range = (
            str(pages[0])
            if len(pages) == 1
            else f"{pages[0]}-{pages[-1]}"
        ) if pages else "?"

        return TextChunk(
            chunk_id=f"{document_id}::{chunk_index}",
            document_id=document_id,
            content=content,
            content_raw=content,
            section_title=section,
            page_range=page_range,
            char_count=len(content),
            has_hebrew=bool(HEBREW_PATTERN.search(content)),
            has_tables=has_tables,
            extracted_via=extracted_via,
        )
