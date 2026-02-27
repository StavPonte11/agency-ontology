"""
PDF source connector for the Agency Ontology pipeline.
Supports: layout-aware PDF parsing (pdfplumber), Hebrew OCR fallback (Tesseract).
Designed for Hebrew military documents — PDFs may include nikud, RTL text, tables.
"""
from __future__ import annotations

import logging
import os
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncIterator, Optional

from pydantic import BaseModel, Field

from .base import ConnectorHealthStatus, ConnectorType, SourceConnector, SourceDocument

logger = logging.getLogger(__name__)

try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False
    logger.warning("pdfplumber not installed — PDF parsing disabled")

try:
    import pdf2image
    import pytesseract
    HAS_TESSERACT = True
except ImportError:
    HAS_TESSERACT = False
    logger.warning("pdf2image / pytesseract not installed — OCR fallback disabled")


class PDFConnectorConfig(BaseModel):
    """Configuration for the PDF directory connector."""

    directory: str = Field(
        description="Absolute path to the directory containing PDF files (recursive)"
    )
    glob_pattern: str = Field(
        default="**/*.pdf",
        description="Glob pattern for PDF files within directory",
    )
    # Hebrew-specific settings
    primary_language: str = Field(
        default="he",
        description="Primary language for OCR: 'heb' for Tesseract Hebrew, 'eng' for English",
    )
    ocr_language: str = Field(
        default="heb+eng",
        description="Tesseract language code(s). 'heb+eng' for mixed Hebrew/English military docs.",
    )
    min_text_length: int = Field(
        default=100,
        description="Minimum extracted text length (chars) before triggering OCR fallback",
    )
    max_pages: Optional[int] = Field(
        default=None,
        description="Max pages per PDF to extract (None = all pages)",
    )
    chunk_size: int = Field(
        default=1500,
        description="Target chunk size in characters for LLM extraction",
    )
    chunk_overlap: int = Field(
        default=200,
        description="Overlap between chunks in characters",
    )


class PDFConnector(SourceConnector):
    """
    Scans a directory for PDF files and yields each as a SourceDocument.
    Supports Hebrew military PDFs with OCR fallback.
    """

    connector_type = ConnectorType.PDF

    def __init__(self, config: PDFConnectorConfig, connector_id: str) -> None:
        self._config = config
        self._connector_id = connector_id
        self._root = Path(config.directory)

    def validate_config(self, config: dict[str, Any]) -> bool:
        parsed = PDFConnectorConfig(**config)
        if not Path(parsed.directory).exists():
            raise ValueError(f"Directory does not exist: {parsed.directory}")
        return True

    async def test_connection(self) -> ConnectorHealthStatus:
        import time
        start = time.monotonic()
        try:
            if not self._root.exists():
                return ConnectorHealthStatus(
                    healthy=False, error=f"Directory not found: {self._root}"
                )
            pdf_count = sum(1 for _ in self._root.glob(self._config.glob_pattern))
            return ConnectorHealthStatus(
                healthy=True,
                latency_ms=(time.monotonic() - start) * 1000,
            )
        except Exception as exc:
            return ConnectorHealthStatus(healthy=False, error=str(exc))

    async def list_documents(
        self,
        since: Optional[datetime] = None,
    ) -> AsyncIterator[SourceDocument]:
        """Yield each PDF as a SourceDocument. Skips unreadable files without stopping."""
        for pdf_path in sorted(self._root.glob(self._config.glob_pattern)):
            if not pdf_path.is_file():
                continue

            # Skip if not modified since cutoff
            if since is not None:
                mtime = datetime.utcfromtimestamp(pdf_path.stat().st_mtime)
                if mtime < since:
                    continue

            try:
                raw_bytes = pdf_path.read_bytes()
                doc = SourceDocument(
                    external_id=str(pdf_path.relative_to(self._root)),
                    title=pdf_path.stem,
                    content_type="pdf",
                    raw_content=raw_bytes,
                    metadata={
                        "file_path": str(pdf_path),
                        "file_size": pdf_path.stat().st_size,
                        "modified_at": datetime.utcfromtimestamp(
                            pdf_path.stat().st_mtime
                        ).isoformat(),
                    },
                    content_hash=SourceDocument.compute_hash(raw_bytes),
                    document_type="PDF_GENERAL",
                    source_connector_id=self._connector_id,
                    connector_type=ConnectorType.PDF,
                    primary_language=self._config.primary_language,
                )
                yield doc
            except Exception as exc:
                logger.warning(
                    f"Failed to read PDF {pdf_path}: {exc}",
                    extra={"path": str(pdf_path)},
                )
                continue

    async def get_document(self, external_id: str) -> SourceDocument:
        pdf_path = self._root / external_id
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")
        raw_bytes = pdf_path.read_bytes()
        return SourceDocument(
            external_id=external_id,
            title=pdf_path.stem,
            content_type="pdf",
            raw_content=raw_bytes,
            metadata={"file_path": str(pdf_path)},
            content_hash=SourceDocument.compute_hash(raw_bytes),
            document_type="PDF_GENERAL",
            source_connector_id=self._connector_id,
            connector_type=ConnectorType.PDF,
            primary_language=self._config.primary_language,
        )

    def get_config_schema(self) -> dict[str, Any]:
        return PDFConnectorConfig.model_json_schema()
