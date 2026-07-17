from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO, TypeAlias, cast

from pypdf import PdfReader
from pypdf.errors import PdfReadError as PypdfReadError

from .exceptions import PdfLimitError, PdfReadError
from .models import ParseResult
from .parsing import parse_page

DEFAULT_MAX_FILE_SIZE = 100 * 1024 * 1024
DEFAULT_MAX_PAGES = 500
_STREAM_CHUNK_SIZE = 1024 * 1024
_STREAM_SPOOL_MEMORY_LIMIT = 8 * 1024 * 1024

PdfSource: TypeAlias = str | os.PathLike[str] | BinaryIO


def _source_size(source: PdfSource) -> int | None:
    if isinstance(source, (str, os.PathLike)):
        return Path(source).stat().st_size

    if not source.seekable():
        return None

    try:
        return os.fstat(source.fileno()).st_size
    except (AttributeError, OSError):
        pass

    position = source.tell()
    try:
        source.seek(0, os.SEEK_END)
        return source.tell()
    finally:
        source.seek(position)


def enforce_source_size(source: PdfSource, max_file_size: int) -> None:
    if max_file_size < 1:
        raise ValueError("max_file_size must be positive")

    size = _source_size(source)
    if size is not None and size > max_file_size:
        raise PdfLimitError(f"PDF exceeds the {max_file_size}-byte size limit")


@contextmanager
def _bounded_reader_source(
    source: PdfSource,
    max_file_size: int,
) -> Iterator[BinaryIO]:
    if max_file_size < 1:
        raise ValueError("max_file_size must be positive")

    if isinstance(source, (str, os.PathLike)):
        source_path = Path(source)
        with source_path.open("rb") as handle:
            enforce_source_size(handle, max_file_size)
            yield handle
        return

    if source.seekable():
        position = source.tell()
        try:
            enforce_source_size(source, max_file_size)
            yield source
        finally:
            source.seek(position)
        return

    with tempfile.SpooledTemporaryFile(
        max_size=_STREAM_SPOOL_MEMORY_LIMIT,
        mode="w+b",
    ) as temporary_source:
        total_size = 0
        while chunk := source.read(_STREAM_CHUNK_SIZE):
            total_size += len(chunk)
            if total_size > max_file_size:
                raise PdfLimitError(f"PDF exceeds the {max_file_size}-byte size limit")
            temporary_source.write(chunk)

        temporary_source.seek(0)
        yield cast(BinaryIO, temporary_source)


@contextmanager
def validated_pdf_reader(
    source: PdfSource,
    *,
    max_pages: int,
    max_file_size: int,
) -> Iterator[tuple[PdfReader, BinaryIO]]:
    """Open one bounded source and validate the shared PDF input contract."""
    if max_pages < 1:
        raise ValueError("max_pages must be positive")

    with _bounded_reader_source(source, max_file_size) as reader_source:
        reader = PdfReader(reader_source, strict=False)
        if reader.is_encrypted:
            raise PdfReadError("Encrypted PDFs are not supported")
        if len(reader.pages) > max_pages:
            raise PdfLimitError(f"PDF exceeds the {max_pages}-page limit")
        yield reader, reader_source


def parse_pdf(
    source: PdfSource,
    *,
    include_raw_text: bool = False,
    max_pages: int = DEFAULT_MAX_PAGES,
    max_file_size: int = DEFAULT_MAX_FILE_SIZE,
) -> ParseResult:
    """Parse every text page from a bounded PDF path or binary stream.

    Raw page text is excluded unless ``include_raw_text`` is enabled. Expected input and
    resource failures are reported with the package exception types.
    """

    try:
        with validated_pdf_reader(
            source,
            max_pages=max_pages,
            max_file_size=max_file_size,
        ) as (reader, _reader_source):
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
