from __future__ import annotations

from contextlib import closing
from io import BytesIO
from pathlib import Path

import pypdfium2 as pdfium
import pytest
from pdf_assertions import drawn_label
from pypdf import PdfReader, PdfWriter
from pypdf.generic import ArrayObject, DictionaryObject, FloatObject, NameObject, RectangleObject
from reportlab.lib.pagesizes import A4, A6
from reportlab.pdfbase.pdfmetrics import registerFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas

from form7_pdf_parser import Overlay, OverlayError, PdfReadError, annotate_pdf, parse_pdf

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module", autouse=True)
def _placement_font() -> None:
    # Fixture generation must not depend on the package registering its own font.
    registerFont(
        TTFont(
            "PlacementFixtureFont",
            str(FIXTURES.parent.parent / "src/form7_pdf_parser/fonts/NotoSans-Bold.ttf"),
        )
    )


def _pdf(
    tmp_path: Path,
    *,
    kind: str = "legacy",
    obstacle: str = "",
    recipient_y: float = 700,
    recipient_caption: str = "Кому",
) -> Path:
    path = tmp_path / "source.pdf"
    c = Canvas(str(path), pagesize=A4, invariant=1)
    c.setFont("PlacementFixtureFont", 21.5)
    c.drawString(239, 815.89, "ПОСЫЛКА")
    c.setFont("PlacementFixtureFont", 10)
    c.drawString(307, recipient_y, recipient_caption)
    c.drawString(307, recipient_y - 20, "Получатель Тестовый")
    if kind == "multiple":
        c.drawString(50, 500, recipient_caption)
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

    def visit(operator, operands, cm, tm):
        if operator == b"Do" and str(operands[0]).startswith("/FormXob.g1047"):
            positions.append((cm[4], cm[5], (cm[0] ** 2 + cm[1] ** 2) ** 0.5 * 1000))

    PdfReader(path).pages[0].extract_text(visitor_operand_before=visit)
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
    assert drawn_label(PdfReader(output).pages[0]) == "Заказ № 1234"
    assert "Заказ №" not in text
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
    assert drawn_label(PdfReader(output).pages[0]) == "Заказ № 1234"
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
    assert f"Заказ № {number}" == drawn_label(PdfReader(output).pages[0])
    assert parse_pdf(output) == parse_pdf(source)


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
@pytest.mark.parametrize("cropped", [False, True])
def test_fallback_label_is_upright_at_visible_top_right(
    tmp_path: Path, rotation: int, cropped: bool
) -> None:
    writer = PdfWriter()
    page = writer.add_blank_page(width=400, height=300)
    if cropped:
        page.cropbox = RectangleObject((50, 40, 350, 260))
    page.rotate(rotation)
    source = tmp_path / "rotated.pdf"
    writer.write(source)
    output = tmp_path / "labelled.pdf"

    annotate_pdf(source, output, [Overlay(1, "001234")])

    result = PdfReader(output).pages[0]
    assert result.rotation == 0
    directions = []

    def visit(operator, operands, cm, tm):
        if operator == b"Do" and str(operands[0]).startswith("/FormXob.g1047"):
            scale = (cm[0] ** 2 + cm[1] ** 2) ** 0.5
            directions.append((cm[0] / scale, cm[1] / scale))

    result.extract_text(visitor_operand_before=visit)
    assert directions == [pytest.approx((1, 0))]
    with (
        pdfium.PdfDocument(str(output)) as document,
        closing(document[0]) as rendered_page,
        closing(rendered_page.render(grayscale=True)) as bitmap,
    ):
        ink = [
            (x, y)
            for y in range(bitmap.height)
            for x in range(bitmap.width)
            if bitmap.buffer[y * bitmap.stride + x] < 250
        ]
        assert ink
        assert min(x for x, _ in ink) > 35
        assert max(x for x, _ in ink) == pytest.approx(bitmap.width - 40, abs=3)
        assert 5 < min(y for _, y in ink) < max(y for _, y in ink) < 40


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
@pytest.mark.parametrize("cropped", [False, True])
def test_rotated_fallback_checks_visible_corner_for_obstacles(
    tmp_path: Path, rotation: int, cropped: bool
) -> None:
    left, bottom, right, top = (50, 40, 350, 260) if cropped else (0, 0, 400, 300)
    points = {
        0: (right - 60, top - 25),
        90: (left + 25, top - 60),
        180: (left + 60, bottom + 25),
        270: (right - 25, bottom + 60),
    }
    drawing = BytesIO()
    canvas = Canvas(drawing, pagesize=(400, 300), invariant=1)
    canvas.circle(*points[rotation], 2, fill=1)
    canvas.save()
    writer = PdfWriter()
    page = writer.add_page(PdfReader(drawing).pages[0])
    page.cropbox = RectangleObject((left, bottom, right, top))
    page.rotate(rotation)
    source = tmp_path / "occupied.pdf"
    writer.write(source)
    output = tmp_path / "labelled.pdf"
    output.write_bytes(b"existing output")

    with pytest.raises(OverlayError, match="occupied"):
        annotate_pdf(source, output, [Overlay(1, "001234")])

    assert output.read_bytes() == b"existing output"


@pytest.mark.parametrize(
    "caption",
    ["Кому", "Кому:", "кому :", "КОМУ: Получатель Тестовый", "Кому Получатель Тестовый"],
)
@pytest.mark.parametrize("scenario", ["safe", "close", "multiple"])
def test_recipient_caption_variants_share_placement_guards(
    tmp_path: Path, caption: str, scenario: str
) -> None:
    source = _pdf(
        tmp_path,
        kind="multiple" if scenario == "multiple" else "legacy",
        recipient_y=790 if scenario == "close" else 700,
        recipient_caption=caption,
    )
    output = tmp_path / "out.pdf"
    if scenario == "safe":
        annotate_pdf(source, output, [Overlay(1, "001234")])
        assert drawn_label(PdfReader(output).pages[0]) == "Заказ № 001234"
    else:
        output.write_bytes(b"existing output")
        with pytest.raises(OverlayError, match="7 mm" if scenario == "close" else "multiple"):
            annotate_pdf(source, output, [Overlay(1, "001234")])
        assert output.read_bytes() == b"existing output"


def test_unrelated_word_is_not_a_recipient_caption(tmp_path: Path) -> None:
    source = _pdf(tmp_path, recipient_y=790, recipient_caption="Комус")
    annotate_pdf(source, tmp_path / "out.pdf", [Overlay(1, "001234")])


def _annotation_objects_pdf(
    tmp_path: Path,
    *,
    annots: bytes = b"4 0 R",
    rect: bytes = b"6 0 R",
    coordinates: bytes = b"[20 20 40 40]",
    unit: bytes = b"1",
) -> Path:
    # A minimal PDF keeps indirect arrays/numbers intact without private writer APIs.
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 400 300] /UserUnit 7 0 R /Annots "
        + annots
        + b" >>",
        b"[5 0 R]",
        b"<< /Type /Annot /Subtype /Link /Rect " + rect + b" /Border [0 0 0] >>",
        coordinates,
        unit,
        b"280",
        b"265",
        b"310",
        b"285",
    ]
    data = bytearray(b"%PDF-1.7\n")
    offsets = [0]
    for number, body in enumerate(objects, 1):
        offsets.append(len(data))
        data.extend(f"{number} 0 obj\n".encode() + body + b"\nendobj\n")
    xref = len(data)
    data.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        data.extend(f"{offset:010d} 00000 n \n".encode())
    data.extend(
        f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    path = tmp_path / "objects.pdf"
    path.write_bytes(data)
    return path


@pytest.mark.parametrize("annots", [b"[5 0 R]", b"4 0 R"])
@pytest.mark.parametrize("indirect_rect", [False, True])
@pytest.mark.parametrize("occupied", [False, True])
def test_direct_and_indirect_annotation_geometry(
    tmp_path: Path, annots: bytes, indirect_rect: bool, occupied: bool
) -> None:
    coordinates = b"[280 265 310 285]" if occupied else b"[20 20 40 40]"
    source = _annotation_objects_pdf(
        tmp_path,
        annots=annots,
        rect=b"6 0 R" if indirect_rect else coordinates,
        coordinates=coordinates,
    )
    output = tmp_path / "out.pdf"
    output.write_bytes(b"existing output")
    if occupied:
        with pytest.raises(OverlayError, match="occupied"):
            annotate_pdf(source, output, [Overlay(1, "001234")])
        assert output.read_bytes() == b"existing output"
    else:
        annotate_pdf(source, output, [Overlay(1, "001234")])
        page = PdfReader(output).pages[0]
        assert len(page.annotations) == 1
        assert drawn_label(page) == "Заказ № 001234"


@pytest.mark.parametrize("coordinates", [b"[310 285 280 265]", b"[8 0 R 9 0 R 10 0 R 11 0 R]"])
def test_reversed_and_indirect_coordinates_cannot_bypass_collision(
    tmp_path: Path, coordinates: bytes
) -> None:
    source = _annotation_objects_pdf(tmp_path, coordinates=coordinates)
    with pytest.raises(OverlayError, match="occupied"):
        annotate_pdf(source, tmp_path / "out.pdf", [Overlay(1, "001234")])


@pytest.mark.parametrize("rect", [b"null", b"[1 2 3]", b"[0 0 (bad) 1]"])
def test_unverifiable_annotation_bounds_leave_output_unchanged(tmp_path: Path, rect: bytes) -> None:
    source = _annotation_objects_pdf(tmp_path, rect=rect)
    output = tmp_path / "out.pdf"
    output.write_bytes(b"existing output")
    with pytest.raises(OverlayError, match="annotation"):
        annotate_pdf(source, output, [Overlay(1, "001234")])
    assert output.read_bytes() == b"existing output"


@pytest.mark.parametrize("annots", [b"null", b"[]"])
def test_empty_annotation_arrays_are_supported(tmp_path: Path, annots: bytes) -> None:
    source = _annotation_objects_pdf(tmp_path, annots=annots)
    annotate_pdf(source, tmp_path / "out.pdf", [Overlay(1, "001234")])


@pytest.mark.parametrize("annots", [b"42", b"[null]"])
def test_invalid_annotation_objects_are_rejected(tmp_path: Path, annots: bytes) -> None:
    source = _annotation_objects_pdf(tmp_path, annots=annots)
    with pytest.raises(OverlayError, match="annotation"):
        annotate_pdf(source, tmp_path / "out.pdf", [Overlay(1, "001234")])


@pytest.mark.parametrize("unit", [b"null", b"0.5"])
def test_indirect_page_units_are_resolved(tmp_path: Path, unit: bytes) -> None:
    source = _annotation_objects_pdf(tmp_path, unit=unit)
    if unit == b"null":
        annotate_pdf(source, tmp_path / "out.pdf", [Overlay(1, "001234")])
    else:
        with pytest.raises(OverlayError, match="UserUnit"):
            annotate_pdf(source, tmp_path / "out.pdf", [Overlay(1, "001234")])


def test_overflowing_annotation_coordinates_are_rejected(tmp_path: Path) -> None:
    source = _annotation_objects_pdf(tmp_path, coordinates=b"[" + b"9" * 400 + b" 0 1 1]")
    output = tmp_path / "out.pdf"
    output.write_bytes(b"existing output")
    with pytest.raises(PdfReadError, match="Unable to annotate"):
        annotate_pdf(source, output, [Overlay(1, "001234")])
    assert output.read_bytes() == b"existing output"
