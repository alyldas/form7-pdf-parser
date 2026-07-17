from __future__ import annotations

import os
import re
import shutil
from collections.abc import Iterable
from io import BytesIO
from pathlib import Path
from typing import BinaryIO

from pypdf import PageObject, PdfReader, PdfWriter
from pypdf.errors import PdfReadError as PypdfReadError
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen.canvas import Canvas

from .atomic import atomic_output_path
from .exceptions import OverlayError, PdfReadError
from .models import Overlay
from .pdf import DEFAULT_MAX_FILE_SIZE, DEFAULT_MAX_PAGES, validated_pdf_reader

MAX_OVERLAY_LABEL_LENGTH = 64
_OVERLAY_FONT_NAME = "Helvetica-Bold"
_OVERLAY_MAX_FONT_SIZE = 18.0
_OVERLAY_MIN_FONT_SIZE = 8.0
_OVERLAY_HORIZONTAL_MARGIN = 40.0
_OVERLAY_TOP_MARGIN = 16.0
_COPY_CHUNK_SIZE = 1024 * 1024


def normalize_overlay_label(label: str) -> str:
    """Return the documented safe ASCII subset used for PDF labels."""
    compact = re.sub(r"\s+", " ", label).strip()
    if not compact:
        return ""

    ascii_only = re.sub(r"[^A-Za-z0-9#\-_/ ]+", "", compact)
    return re.sub(r"\s+", " ", ascii_only).strip()


def _overlay_layout(width: float, height: float, label: str) -> tuple[float, float, float]:
    available_width = width - 2 * _OVERLAY_HORIZONTAL_MARGIN
    unit_width = stringWidth(label, _OVERLAY_FONT_NAME, 1.0)
    if available_width <= 0 or unit_width <= 0:
        raise OverlayError("PDF page is too narrow for an overlay label")

    font_size = min(_OVERLAY_MAX_FONT_SIZE, available_width / unit_width)
    if font_size < _OVERLAY_MIN_FONT_SIZE:
        raise OverlayError("Overlay label does not fit within the PDF page")

    text_width = stringWidth(label, _OVERLAY_FONT_NAME, font_size)
    text_x = width - _OVERLAY_HORIZONTAL_MARGIN - text_width
    text_y = height - _OVERLAY_TOP_MARGIN - font_size
    if text_y < 0:
        raise OverlayError("PDF page is too short for an overlay label")
    return text_x, text_y, font_size


def _overlay_page(width: float, height: float, label: str) -> PageObject:
    buffer = BytesIO()
    canvas = Canvas(buffer, pagesize=(width, height), pageCompression=1, invariant=1)
    text_x, text_y, font_size = _overlay_layout(width, height, label)
    canvas.setFont(_OVERLAY_FONT_NAME, font_size)
    canvas.drawString(text_x, text_y, label)
    canvas.save()
    buffer.seek(0)
    return PdfReader(buffer, strict=False).pages[0]


def _overlay_map(overlays: Iterable[Overlay]) -> dict[int, str]:
    result: dict[int, str] = {}
    for overlay in overlays:
        if overlay.page_number < 1:
            raise OverlayError("Overlay page numbers must be positive")

        label = normalize_overlay_label(overlay.order_label)
        if len(label) > MAX_OVERLAY_LABEL_LENGTH:
            raise OverlayError(
                f"Overlay labels must not exceed {MAX_OVERLAY_LABEL_LENGTH} characters"
            )
        if not label:
            continue
        if overlay.page_number in result:
            raise OverlayError(f"Duplicate overlay for page {overlay.page_number}")

        result[overlay.page_number] = label

    return result


def _copy_validated_source(source: BinaryIO, destination: Path) -> None:
    source.seek(0)
    with (
        atomic_output_path(destination, suffix=".pdf") as temporary_path,
        temporary_path.open("wb") as handle,
    ):
        shutil.copyfileobj(source, handle, length=_COPY_CHUNK_SIZE)
        handle.flush()
        os.fsync(handle.fileno())


def annotate_pdf(
    source: str | os.PathLike[str],
    destination: str | os.PathLike[str],
    overlays: Iterable[Overlay],
    *,
    max_pages: int = DEFAULT_MAX_PAGES,
    max_file_size: int = DEFAULT_MAX_FILE_SIZE,
) -> None:
    """Atomically add validated page labels to a bounded, unencrypted PDF.

    Labels are normalized to the documented ASCII subset and fitted into the visible CropBox.
    Empty normalized overlays produce a byte-identical atomic copy after input validation.
    """

    source_path = Path(source)
    destination_path = Path(destination)
    labels = _overlay_map(overlays)

    try:
        if destination_path.exists() and source_path.samefile(destination_path):
            raise OverlayError("Input and output PDF paths must be different")

        with validated_pdf_reader(
            source_path,
            max_pages=max_pages,
            max_file_size=max_file_size,
        ) as (reader, reader_source):
            if any(page_number > len(reader.pages) for page_number in labels):
                raise OverlayError("Overlay references a page outside the PDF")

            if not labels:
                _copy_validated_source(reader_source, destination_path)
                return

            writer = PdfWriter()
            for page_number, page in enumerate(reader.pages, start=1):
                label = labels.get(page_number)
                if label:
                    # Isolate the source resource graph before and after a content merge.
                    writer.reset_translation(reader)

                writer.add_page(page)
                if label:
                    writer_page = writer.pages[-1]
                    if writer_page.rotation and "/Annots" in writer_page:
                        raise OverlayError(
                            "Rotated PDF pages with interactive annotations are not supported"
                        )
                    if writer_page.rotation:
                        writer_page.transfer_rotation_to_content()

                    cropbox = writer_page.cropbox
                    writer_page.merge_translated_page(
                        _overlay_page(
                            float(cropbox.width),
                            float(cropbox.height),
                            label,
                        ),
                        float(cropbox.left),
                        float(cropbox.bottom),
                    )
                    writer.reset_translation(reader)

            with (
                atomic_output_path(destination_path, suffix=".pdf") as temporary_path,
                temporary_path.open("wb") as handle,
            ):
                writer.write(handle)
                handle.flush()
                os.fsync(handle.fileno())
    except (OSError, PypdfReadError) as error:
        raise PdfReadError("Unable to annotate the PDF") from error
