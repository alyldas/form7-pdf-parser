from __future__ import annotations

import os
import re
import shutil
from collections.abc import Iterable
from io import BytesIO
from math import hypot, isfinite
from pathlib import Path
from threading import Lock
from typing import BinaryIO

import pypdfium2 as pdfium  # type: ignore[import-untyped]
from pypdf import PageObject, PdfReader, PdfWriter
from pypdf.errors import PdfReadError as PypdfReadError
from pypdf.generic import DictionaryObject
from reportlab.pdfbase.pdfmetrics import registerFont, stringWidth
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas

from .atomic import atomic_output_path
from .exceptions import OverlayError, PdfReadError
from .models import Overlay
from .pdf import DEFAULT_MAX_FILE_SIZE, DEFAULT_MAX_PAGES, validated_pdf_reader

MAX_OVERLAY_LABEL_LENGTH = 64
_OVERLAY_FONT_NAME = "Form7NotoSansBold"
_OVERLAY_MAX_FONT_SIZE = 12.0
_OVERLAY_MIN_FONT_SIZE = 8.0
_OVERLAY_HORIZONTAL_MARGIN = 40.0
_OVERLAY_TOP_MARGIN = 16.0
_COPY_CHUNK_SIZE = 1024 * 1024
_RENDER_LOCK = Lock()
_ADDRESS_GAP = 7 * 72 / 25.4
_INK_PADDING = 2.0

registerFont(TTFont(_OVERLAY_FONT_NAME, str(Path(__file__).parent / "fonts/NotoSans-Bold.ttf")))


def normalize_overlay_label(label: str) -> str:
    """Validate an order number without silently changing its digits."""
    compact = label.strip()
    if not compact:
        return ""

    match = re.fullmatch(r"(?:Заказ\s*№\s*)?([0-9]+)", compact)
    if match is None:
        raise OverlayError("Order number must contain ASCII digits only")
    return match[1]


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


def _page_overlay_layout(page: PageObject, label: str) -> tuple[float, float, float]:
    if float(page.get("/UserUnit", 1)) != 1:
        raise OverlayError("Custom PDF UserUnit is not supported for order label placement")
    anchors: list[tuple[str, float, float, float]] = []

    def visit(
        text: str, cm: list[float], tm: list[float], font: DictionaryObject | None, size: float
    ) -> None:
        title = " ".join(text.split()).casefold()
        if title == "кому" or title == "посылка" or title.startswith("посылка "):
            x = tm[4] * cm[0] + tm[5] * cm[2] + cm[4]
            y = tm[4] * cm[1] + tm[5] * cm[3] + cm[5]
            height = size * hypot(tm[2] * cm[0] + tm[3] * cm[2], tm[2] * cm[1] + tm[3] * cm[3])
            anchors.append((title, x, y, height))

    page.extract_text(visitor_text=visit)
    crop = page.cropbox
    headers = [anchor for anchor in anchors if anchor[0] != "кому"]
    recipients = [anchor for anchor in anchors if anchor[0] == "кому"]
    if len(headers) > 1 or len(recipients) > 1:
        raise OverlayError("Cannot place an order label on a page with multiple shipping forms")
    if not headers:
        layout = _overlay_layout(float(crop.width), float(crop.height), label)
    else:
        title, x, y, height = headers[0]
        compact = title != "посылка"
        scale = height / (9.0 if compact else 21.5)
        if not isfinite(scale) or scale <= 0:
            raise OverlayError("Invalid shipping header geometry")
        left = x + (38.54 if compact else 175.0) * scale - float(crop.left)
        available = (150.5 if compact else 130.0) * scale
        baseline = y + (24.58 if compact else -0.89) * scale - float(crop.bottom)
        font_size = min(
            _OVERLAY_MAX_FONT_SIZE * scale, available / stringWidth(label, _OVERLAY_FONT_NAME, 1)
        )
        if font_size < _OVERLAY_MIN_FONT_SIZE:
            raise OverlayError("Order label does not fit within the shipping header")
        if compact:
            left += available - stringWidth(label, _OVERLAY_FONT_NAME, font_size)
        layout = left, baseline, font_size

    x, y, font_size = layout
    if recipients:
        _, _, recipient_y, recipient_height = recipients[0]
        if y - font_size * 0.3 + float(crop.bottom) < recipient_y + recipient_height + _ADDRESS_GAP:
            raise OverlayError("Order label must remain at least 7 mm above the recipient block")
    return layout


def _check_overlay_space(page: PageObject, label: str, layout: tuple[float, float, float]) -> None:
    x, y, size = layout
    width, height = float(page.cropbox.width), float(page.cropbox.height)
    left, bottom = x - _INK_PADDING, y - size * 0.3 - _INK_PADDING
    right = x + stringWidth(label, _OVERLAY_FONT_NAME, size) + _INK_PADDING
    top = y + size * 1.1 + _INK_PADDING
    if not all(isfinite(value) for value in (left, bottom, right, top)) or not (
        0 <= left < right <= width and 0 <= bottom < top <= height
    ):
        raise OverlayError("Order label falls outside the visible page")
    for reference in page.get("/Annots", []):
        rect = reference.get_object().get("/Rect")
        if rect and (
            float(rect[0]) < right + float(page.cropbox.left)
            and float(rect[2]) > left + float(page.cropbox.left)
            and float(rect[1]) < top + float(page.cropbox.bottom)
            and float(rect[3]) > bottom + float(page.cropbox.bottom)
        ):
            raise OverlayError("Order label area is occupied by an annotation")
    # Render only the protected rectangle, including its safety margin. This also
    # detects paths, barcodes, logos and annotations, not just extractable text.
    writer = PdfWriter()
    writer.add_page(page)
    writer.pages[0].rotation = 0
    stream = BytesIO()
    writer.write(stream)
    with _RENDER_LOCK:
        try:
            with pdfium.PdfDocument(stream.getvalue()) as document:
                document.init_forms()
                rendered_page = document[0]
                try:
                    bitmap = rendered_page.render(
                        scale=3,
                        crop=(left, bottom, width - right, height - top),
                        grayscale=True,
                        draw_annots=True,
                    )
                    try:
                        occupied = any(
                            value < 255
                            for row in range(bitmap.height)
                            for value in bitmap.buffer[
                                row * bitmap.stride : row * bitmap.stride + bitmap.width
                            ]
                        )
                    finally:
                        bitmap.close()
                finally:
                    rendered_page.close()
        except pdfium.PdfiumError as error:
            raise OverlayError("Unable to verify free space for the order label") from error
    if occupied:
        raise OverlayError(
            "Order label area is occupied; existing page content was not overwritten"
        )


def _overlay_page(
    width: float, height: float, label: str, layout: tuple[float, float, float]
) -> PageObject:
    buffer = BytesIO()
    canvas = Canvas(buffer, pagesize=(width, height), pageCompression=1, invariant=1)
    text_x, text_y, font_size = layout
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

        result[overlay.page_number] = f"Заказ № {label}"

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

    Order numbers are rendered as ``Заказ № <number>`` in a verified free header area.
    Empty overlays produce a byte-identical atomic copy after input validation.
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
                    cropbox = writer_page.cropbox
                    layout = _page_overlay_layout(writer_page, label)
                    _check_overlay_space(writer_page, label, layout)
                    writer_page.merge_translated_page(
                        _overlay_page(
                            float(cropbox.width),
                            float(cropbox.height),
                            label,
                            layout,
                        ),
                        float(cropbox.left),
                        float(cropbox.bottom),
                    )
                    if writer_page.rotation:
                        writer_page.transfer_rotation_to_content()
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
