from __future__ import annotations

import os
from pathlib import Path
from typing import BinaryIO, TypeAlias

from pypdf import PdfReader
from pypdf.errors import PdfReadError as PypdfReadError

from .exceptions import PdfLimitError, PdfReadError
from .models import ParseResult
from .parsing import parse_page

DEFAULT_MAX_FILE_SIZE = 100 * 1024 * 1024
DEFAULT_MAX_PAGES = 500

PdfSource: TypeAlias = str | os.PathLike[str] | BinaryIO


def _source_size(source: PdfSource) -> int | None:
    if isinstance(source, (str, os.PathLike)):
        return Path(source).stat().st_size

    if not source.seekable():
        return None

    position = source.tell()
    source.seek(0, os.SEEK_END)
    size = source.tell()
    source.seek(position)
    return size


def enforce_source_size(source: PdfSource, max_file_size: int) -> None:
    if max_file_size < 1:
        raise ValueError("max_file_size must be positive")

    size = _source_size(source)
    if size is not None and size > max_file_size:
        raise PdfLimitError(f"PDF exceeds the {max_file_size}-byte size limit")


def parse_pdf(
    source: PdfSource,
    *,
    include_raw_text: bool = False,
    max_pages: int = DEFAULT_MAX_PAGES,
    max_file_size: int = DEFAULT_MAX_FILE_SIZE,
) -> ParseResult:
    if max_pages < 1:
        raise ValueError("max_pages must be positive")

    enforce_source_size(source, max_file_size)

    try:
        reader_source = Path(source) if isinstance(source, os.PathLike) else source
        reader = PdfReader(reader_source, strict=False)
        if reader.is_encrypted:
            raise PdfReadError("Encrypted PDFs are not supported")
        if len(reader.pages) > max_pages:
            raise PdfLimitError(f"PDF exceeds the {max_pages}-page limit")

        pages = tuple(
            parse_page(
                page.extract_text() or "",
                page_number,
                include_raw_text=include_raw_text,
            )
            for page_number, page in enumerate(reader.pages, start=1)
        )
    except (OSError, PypdfReadError) as error:
        raise PdfReadError("Unable to read the PDF") from error

    return ParseResult(pages=pages)
