from __future__ import annotations

import os
import re
from collections.abc import Iterable
from io import BytesIO
from pathlib import Path

from pypdf import PageObject, PdfReader, PdfWriter
from pypdf.errors import PdfReadError as PypdfReadError
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen.canvas import Canvas

from .atomic import atomic_output_path
from .exceptions import OverlayError, PdfLimitError, PdfReadError
from .models import Overlay
from .pdf import DEFAULT_MAX_FILE_SIZE, DEFAULT_MAX_PAGES, enforce_source_size

MAX_OVERLAY_LABEL_LENGTH = 64


def normalize_overlay_label(label: str) -> str:
    compact = re.sub(r"\s+", " ", label).strip()
    if not compact:
        return ""

    ascii_only = re.sub(r"[^A-Za-z0-9#\-_/ ]+", "", compact)
    return re.sub(r"\s+", " ", ascii_only).strip()


def _overlay_page(width: float, height: float, label: str) -> PageObject:
    buffer = BytesIO()
    canvas = Canvas(buffer, pagesize=(width, height), pageCompression=1, invariant=1)
    font_name = "Helvetica-Bold"
    font_size = 18
    text_width = stringWidth(label, font_name, font_size)
    text_x = max(min(width - 60 - text_width, width - 180), 40)
    text_y = max(height - 34, 10)
    canvas.setFont(font_name, font_size)
    canvas.drawString(text_x, text_y, label)
    canvas.save()
    buffer.seek(0)
    return PdfReader(buffer, strict=False).pages[0]


def _overlay_map(overlays: Iterable[Overlay]) -> dict[int, str]:
    result: dict[int, str] = {}
    for overlay in overlays:
        if overlay.page_number < 1:
            raise OverlayError("Overlay page numbers must be positive")
        if overlay.page_number in result:
            raise OverlayError(f"Duplicate overlay for page {overlay.page_number}")

        label = normalize_overlay_label(overlay.order_label)
        if len(label) > MAX_OVERLAY_LABEL_LENGTH:
            raise OverlayError(
                f"Overlay labels must not exceed {MAX_OVERLAY_LABEL_LENGTH} characters"
            )
        if label:
            result[overlay.page_number] = label

    return result


def annotate_pdf(
    source: str | os.PathLike[str],
    destination: str | os.PathLike[str],
    overlays: Iterable[Overlay],
    *,
    max_pages: int = DEFAULT_MAX_PAGES,
    max_file_size: int = DEFAULT_MAX_FILE_SIZE,
) -> None:
    if max_pages < 1:
        raise ValueError("max_pages must be positive")

    source_path = Path(source)
    destination_path = Path(destination)
    if destination_path.exists() and source_path.samefile(destination_path):
        raise OverlayError("Input and output PDF paths must be different")

    enforce_source_size(source_path, max_file_size)
    labels = _overlay_map(overlays)

    try:
        reader = PdfReader(source_path, strict=False)
        if reader.is_encrypted:
            raise PdfReadError("Encrypted PDFs are not supported")
        if len(reader.pages) > max_pages:
            raise PdfLimitError(f"PDF exceeds the {max_pages}-page limit")
        if any(page_number > len(reader.pages) for page_number in labels):
            raise OverlayError("Overlay references a page outside the PDF")

        writer = PdfWriter()
        for page_number, page in enumerate(reader.pages, start=1):
            writer.add_page(page)
            writer_page = writer.pages[-1]
            label = labels.get(page_number)
            if label:
                writer_page.merge_page(
                    _overlay_page(
                        float(writer_page.mediabox.width),
                        float(writer_page.mediabox.height),
                        label,
                    )
                )

        with (
            atomic_output_path(destination_path, suffix=".pdf") as temporary_path,
            temporary_path.open("wb") as handle,
        ):
            writer.write(handle)
            handle.flush()
            os.fsync(handle.fileno())
    except (OSError, PypdfReadError) as error:
        raise PdfReadError("Unable to annotate the PDF") from error
