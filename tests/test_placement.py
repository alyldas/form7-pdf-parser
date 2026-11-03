from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest
from pypdf import PdfReader, PdfWriter
from pypdf.generic import ArrayObject, DictionaryObject, FloatObject, NameObject, RectangleObject
from reportlab.lib.pagesizes import A4, A6
from reportlab.pdfgen.canvas import Canvas

from form7_pdf_parser import Overlay, OverlayError, annotate_pdf, parse_pdf

FIXTURES = Path(__file__).parent / "fixtures"


def _pdf(
    tmp_path: Path, *, kind: str = "legacy", obstacle: str = "", recipient_y: float = 700
) -> Path:
    path = tmp_path / "source.pdf"
    c = Canvas(str(path), pagesize=A4, invariant=1)
    c.setFont("Form7NotoSansBold", 21.5)
    c.drawString(239, 815.89, "ПОСЫЛКА")
    c.setFont("Form7NotoSansBold", 10)
    c.drawString(307, recipient_y, "Кому")
    c.drawString(307, recipient_y - 20, "Получатель Тестовый")
    if kind == "multiple":
        c.drawString(50, 500, "Кому")
    if obstacle == "text":
        c.drawString(420, 820, "9999")
    elif obstacle == "line":
        c.line(420, 820, 500, 820)
    elif obstacle == "image":
        # One opaque black pixel, scaled over the proposed label area.
        from reportlab.lib.utils import ImageReader

        image = ImageReader(
            BytesIO(
                b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
                b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc```\x00\x00"
                b"\x00\x04\x00\x01\xf6\x178U\x00\x00\x00\x00IEND\xaeB`\x82"
            )
        )
        c.drawImage(image, 420, 815, 60, 15)
    c.save()
    return path


def _label_position(path: Path) -> tuple[float, float, float]:
    positions = []

    def visit(text, cm, tm, font, size):
        if "Заказ №" in text:
            positions.append(
                (tm[4] * cm[0] + tm[5] * cm[2] + cm[4], tm[4] * cm[1] + tm[5] * cm[3] + cm[5], size)
            )

    PdfReader(path).pages[0].extract_text(visitor_text=visit)
    assert len(positions) == 1
    return positions[0]


def test_legacy_label_uses_approved_header_position(tmp_path: Path) -> None:
    source = _pdf(tmp_path)
    output = tmp_path / "labelled.pdf"
    annotate_pdf(source, output, [Overlay(1, "1234")])

    x, y, size = _label_position(output)
    assert x == pytest.approx(414, abs=0.1)
    assert y == pytest.approx(815, abs=0.1)
    assert size == 12
    text = PdfReader(output).pages[0].extract_text()
    assert "Заказ № 1234" in text
    assert "Order" not in text


@pytest.mark.parametrize("obstacle", ["text", "line", "image"])
def test_occupied_header_is_rejected_without_replacing_output(
    tmp_path: Path, obstacle: str
) -> None:
    source = _pdf(tmp_path, obstacle=obstacle)
    output = tmp_path / "labelled.pdf"
    output.write_bytes(b"existing output")

    with pytest.raises(OverlayError, match="occupied"):
        annotate_pdf(source, output, [Overlay(1, "1234")])

    assert output.read_bytes() == b"existing output"


def test_label_too_close_to_recipient_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(OverlayError, match="7 mm"):
        annotate_pdf(_pdf(tmp_path, recipient_y=790), tmp_path / "out.pdf", [Overlay(1, "1234")])


def test_multiple_forms_cannot_share_one_order_label(tmp_path: Path) -> None:
    with pytest.raises(OverlayError, match="multiple"):
        annotate_pdf(_pdf(tmp_path, kind="multiple"), tmp_path / "out.pdf", [Overlay(1, "1234")])


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_compact_waybill_crop_and_rotation_preserve_shipping_fields(
    tmp_path: Path, rotation: int
) -> None:
    p = PdfReader(FIXTURES / "synthetic-waybill.pdf").pages[0]
    top = float(p.mediabox.top)
    p.cropbox = RectangleObject((0, top - A6[1], A6[0], top))
    p.rotate(rotation)
    writer = PdfWriter()
    writer.add_page(p)
    source = tmp_path / "compact.pdf"
    writer.write(source)
    output = tmp_path / "labelled.pdf"

    annotate_pdf(source, output, [Overlay(1, "1234")])

    assert parse_pdf(output) == parse_pdf(source)
    assert "Заказ № 1234" in PdfReader(output).pages[0].extract_text()
    assert PdfReader(output).pages[0].rotation == 0


def test_long_number_shrinks_and_unfittable_number_is_rejected(tmp_path: Path) -> None:
    source = _pdf(tmp_path)
    output = tmp_path / "labelled.pdf"
    annotate_pdf(source, output, [Overlay(1, "12345678901234567")])
    assert 8 <= _label_position(output)[2] < 12

    with pytest.raises(OverlayError, match="fit"):
        annotate_pdf(source, output, [Overlay(1, "1" * 64)])


def test_second_annotation_cannot_overwrite_first(tmp_path: Path) -> None:
    source = _pdf(tmp_path)
    output = tmp_path / "labelled.pdf"
    annotate_pdf(source, output, [Overlay(1, "1234")])
    with pytest.raises(OverlayError, match="occupied"):
        annotate_pdf(output, tmp_path / "second.pdf", [Overlay(1, "9876")])


def test_cropped_away_header_is_rejected(tmp_path: Path) -> None:
    source = _pdf(tmp_path)
    p = PdfReader(source).pages[0]
    p.cropbox = RectangleObject((0, 0, 400, 800))
    w = PdfWriter()
    w.add_page(p)
    w.write(tmp_path / "cropped.pdf")
    with pytest.raises(OverlayError, match="visible page"):
        annotate_pdf(tmp_path / "cropped.pdf", tmp_path / "out.pdf", [Overlay(1, "1234")])


def test_annotation_rectangle_is_protected(tmp_path: Path) -> None:
    source = _pdf(tmp_path)
    page = PdfReader(source).pages[0]
    page[NameObject("/Annots")] = ArrayObject(
        [
            DictionaryObject(
                {
                    NameObject("/Type"): NameObject("/Annot"),
                    NameObject("/Subtype"): NameObject("/Text"),
                    NameObject("/Rect"): RectangleObject((420, 815, 440, 830)),
                }
            )
        ]
    )
    writer = PdfWriter()
    writer.add_page(page)
    writer.write(tmp_path / "comment.pdf")
    with pytest.raises(OverlayError, match="occupied"):
        annotate_pdf(tmp_path / "comment.pdf", tmp_path / "out.pdf", [Overlay(1, "1234")])


def test_nonstandard_page_units_do_not_bypass_physical_gap(tmp_path: Path) -> None:
    page = PdfReader(_pdf(tmp_path)).pages[0]
    page[NameObject("/UserUnit")] = FloatObject(0.5)
    writer = PdfWriter()
    writer.add_page(page)
    writer.write(tmp_path / "units.pdf")
    with pytest.raises(OverlayError, match="UserUnit"):
        annotate_pdf(tmp_path / "units.pdf", tmp_path / "out.pdf", [Overlay(1, "1234")])


@pytest.mark.parametrize("number", ["12345", "123456", "001234"])
@pytest.mark.parametrize("kind", ["legacy", "waybill"])
def test_five_and_six_digit_orders_use_small_font(tmp_path: Path, number: str, kind: str) -> None:
    source = _pdf(tmp_path) if kind == "legacy" else FIXTURES / "synthetic-waybill.pdf"
    output = tmp_path / "labelled.pdf"

    annotate_pdf(source, output, [Overlay(1, number)])

    assert _label_position(output)[2] == 12
    assert f"Заказ № {number}" in PdfReader(output).pages[0].extract_text()
    assert parse_pdf(output) == parse_pdf(source)
