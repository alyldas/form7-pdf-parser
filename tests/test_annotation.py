from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest
from pdf_assertions import drawn_label, render_page
from pypdf import PdfReader, PdfWriter
from pypdf.generic import ArrayObject, NameObject
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase.pdfmetrics import stringWidth

from form7_pdf_parser import (
    Overlay,
    OverlayError,
    PdfLimitError,
    PdfReadError,
    annotate_pdf,
    normalize_overlay_label,
    parse_pdf,
)
from form7_pdf_parser.annotation import _overlay_layout

FIXTURE = Path(__file__).parent / "fixtures" / "synthetic-form7.pdf"


def test_annotate_pdf_adds_sanitized_label_and_uses_owner_only_mode(tmp_path: Path) -> None:
    output = tmp_path / "annotated.pdf"

    annotate_pdf(FIXTURE, output, [Overlay(page_number=1, order_label="6904")])

    reader = PdfReader(output)
    assert len(reader.pages) == 2
    assert "Заказ № 6904" in drawn_label(reader.pages[0])
    if os.name == "posix":
        assert stat.S_IMODE(output.stat().st_mode) == 0o600


@pytest.mark.parametrize("fixture", ["synthetic-form7.pdf", "synthetic-waybill.pdf"])
@pytest.mark.parametrize("content_array", [False, True])
@pytest.mark.parametrize("rotation", [0, 90])
def test_annotate_pdf_isolates_content_and_shares_resources(
    tmp_path: Path, fixture: str, content_array: bool, rotation: int
) -> None:
    original = PdfReader(FIXTURE.with_name(fixture)).pages[0]
    if content_array:
        original[NameObject("/Contents")] = ArrayObject([original.raw_get("/Contents")])
    original.rotate(rotation)
    writer = PdfWriter()
    for _ in range(3):
        writer.add_page(original)
    source = tmp_path / "shared.pdf"
    writer.write(source)
    original_bytes = source.read_bytes()
    output = tmp_path / "annotated.pdf"

    annotate_pdf(source, output, [Overlay(1, "001234"), Overlay(3, "567890")])

    pages = PdfReader(output).pages
    assert [drawn_label(page) for page in pages] == ["Заказ № 001234", "", "Заказ № 567890"]
    assert render_page(source, 1) == render_page(output, 1)
    assert source.read_bytes() == original_bytes
    assert parse_pdf(source) == parse_pdf(output)
    fonts = [page["/Resources"]["/Font"] for page in pages]
    for name in fonts[0]:
        assert fonts[0].raw_get(name) == fonts[1].raw_get(name) == fonts[2].raw_get(name)


def test_overlay_layout_fits_maximum_label_within_a4() -> None:
    width, height = A4
    label = "1" * 64

    text_x, text_y, font_size = _overlay_layout(width, height, label)

    assert 8 <= font_size <= 12
    assert text_x >= 40
    assert text_x + stringWidth(label, "Form7NotoSansBold", font_size) <= width - 40
    assert text_y >= 0


def test_overlay_layout_rejects_page_too_narrow_for_label() -> None:
    with pytest.raises(OverlayError, match="fit"):
        _overlay_layout(100, 100, "A" * 64)


def test_annotate_pdf_replaces_readonly_output_atomically(tmp_path: Path) -> None:
    output = tmp_path / "annotated.pdf"
    output.write_text("stale", encoding="utf-8")
    output.chmod(0o400)

    annotate_pdf(FIXTURE, output, [Overlay(page_number=2, order_label="7")])

    assert output.read_bytes().startswith(b"%PDF-")
    if os.name == "posix":
        assert stat.S_IMODE(output.stat().st_mode) == 0o600


def test_annotate_pdf_without_effective_labels_is_byte_identical(tmp_path: Path) -> None:
    output = tmp_path / "copy.pdf"

    annotate_pdf(FIXTURE, output, [Overlay(page_number=1, order_label="  ")])

    assert output.read_bytes() == FIXTURE.read_bytes()


def test_annotate_pdf_preserves_parsed_shipping_fields(tmp_path: Path) -> None:
    output = tmp_path / "annotated.pdf"

    before = parse_pdf(FIXTURE)
    annotate_pdf(FIXTURE, output, [Overlay(page_number=1, order_label="6904")])
    after = parse_pdf(output)

    assert [page.tracking_number for page in after.pages] == [
        page.tracking_number for page in before.pages
    ]
    assert [page.recipient_name for page in after.pages] == [
        page.recipient_name for page in before.pages
    ]
    assert [page.recipient_address for page in after.pages] == [
        page.recipient_address for page in before.pages
    ]
    assert [page.recipient_phone for page in after.pages] == [
        page.recipient_phone for page in before.pages
    ]
    assert "Заказ № 6904" in drawn_label(PdfReader(output).pages[0])


def test_annotate_pdf_uses_cropbox_coordinates(tmp_path: Path) -> None:
    source = tmp_path / "cropped.pdf"
    output = tmp_path / "annotated.pdf"
    writer = PdfWriter()
    page = writer.add_blank_page(width=400, height=300)
    page.cropbox.lower_left = (50, 40)
    page.cropbox.upper_right = (350, 260)
    with source.open("wb") as handle:
        writer.write(handle)

    annotate_pdf(source, output, [Overlay(page_number=1, order_label="987")])

    output_page = PdfReader(output).pages[0]
    assert "Заказ № 987" in drawn_label(output_page)
    assert tuple(float(value) for value in output_page.cropbox) == (50.0, 40.0, 350.0, 260.0)


@pytest.mark.parametrize("rotation", [90, 180, 270])
def test_annotate_pdf_transfers_page_rotation_before_merge(
    tmp_path: Path,
    rotation: int,
) -> None:
    source = tmp_path / f"rotated-{rotation}.pdf"
    output = tmp_path / "annotated.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=300, height=400).rotate(rotation)
    with source.open("wb") as handle:
        writer.write(handle)

    annotate_pdf(source, output, [Overlay(page_number=1, order_label=str(rotation))])

    output_page = PdfReader(output).pages[0]
    assert output_page.rotation == 0
    assert f"Заказ № {rotation}" in drawn_label(output_page)


def test_annotate_pdf_rejects_rotated_page_with_interactive_annotations(
    tmp_path: Path,
) -> None:
    source = tmp_path / "interactive.pdf"
    writer = PdfWriter()
    page = writer.add_blank_page(width=300, height=400).rotate(90)
    page[NameObject("/Annots")] = ArrayObject()
    with source.open("wb") as handle:
        writer.write(handle)

    with pytest.raises(OverlayError, match="interactive"):
        annotate_pdf(source, tmp_path / "output.pdf", [Overlay(1, "1234")])


def test_annotate_pdf_ignores_empty_sanitized_label(tmp_path: Path) -> None:
    output = tmp_path / "annotated.pdf"

    annotate_pdf(FIXTURE, output, [Overlay(page_number=1, order_label="  ")])

    assert drawn_label(PdfReader(output).pages[0]) == ""


@pytest.mark.parametrize(
    "overlays",
    [
        [Overlay(1, "  "), Overlay(1, "1234")],
        [Overlay(1, "1234"), Overlay(1, "  ")],
    ],
)
def test_annotate_pdf_ignores_empty_label_before_duplicate_check(
    tmp_path: Path,
    overlays: list[Overlay],
) -> None:
    output = tmp_path / "annotated.pdf"

    annotate_pdf(FIXTURE, output, overlays)

    assert "Заказ № 1234" in drawn_label(PdfReader(output).pages[0])


def test_annotate_pdf_rejects_duplicate_pages(tmp_path: Path) -> None:
    with pytest.raises(OverlayError, match="Duplicate"):
        annotate_pdf(
            FIXTURE,
            tmp_path / "output.pdf",
            [Overlay(1, "1"), Overlay(1, "2")],
        )


def test_annotate_pdf_rejects_out_of_range_page(tmp_path: Path) -> None:
    with pytest.raises(OverlayError, match="outside"):
        annotate_pdf(FIXTURE, tmp_path / "output.pdf", [Overlay(3, "3")])


def test_annotate_pdf_rejects_non_positive_page(tmp_path: Path) -> None:
    with pytest.raises(OverlayError, match="positive"):
        annotate_pdf(FIXTURE, tmp_path / "output.pdf", [Overlay(0, "0")])


def test_annotate_pdf_rejects_overlong_normalized_label(tmp_path: Path) -> None:
    with pytest.raises(OverlayError, match="64 characters"):
        annotate_pdf(FIXTURE, tmp_path / "output.pdf", [Overlay(1, "1" * 65)])


def test_annotate_pdf_rejects_same_input_and_output() -> None:
    with pytest.raises(OverlayError, match="different"):
        annotate_pdf(FIXTURE, FIXTURE, [])


def test_annotate_pdf_rejects_invalid_page_limit(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="max_pages"):
        annotate_pdf(FIXTURE, tmp_path / "output.pdf", [], max_pages=0)


def test_annotate_pdf_enforces_page_limit(tmp_path: Path) -> None:
    with pytest.raises(PdfLimitError, match="page limit"):
        annotate_pdf(FIXTURE, tmp_path / "output.pdf", [], max_pages=1)


def test_annotate_pdf_rejects_encrypted_input(tmp_path: Path) -> None:
    encrypted = tmp_path / "encrypted.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.encrypt("synthetic-password")
    with encrypted.open("wb") as handle:
        writer.write(handle)

    with pytest.raises(PdfReadError, match="Encrypted"):
        annotate_pdf(encrypted, tmp_path / "output.pdf", [])


def test_annotate_pdf_wraps_invalid_pdf_errors(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid.pdf"
    invalid.write_text("not a pdf", encoding="utf-8")

    with pytest.raises(PdfReadError, match="Unable to annotate"):
        annotate_pdf(invalid, tmp_path / "output.pdf", [])


def test_annotate_pdf_wraps_missing_pdf_errors(tmp_path: Path) -> None:
    with pytest.raises(PdfReadError, match="Unable to annotate"):
        annotate_pdf(tmp_path / "missing.pdf", tmp_path / "output.pdf", [])


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("6904", "6904"),
        ("  00123  ", "00123"),
        ("Заказ № 6904", "6904"),
        ("123456", "123456"),
        ("000000", "000000"),
        ("", ""),
    ],
)
def test_normalize_overlay_label(label: str, expected: str) -> None:
    assert normalize_overlay_label(label) == expected


@pytest.mark.parametrize("label", ["Order #6904", "1 2", "12/34", "１２３４", "abc"])
def test_invalid_order_number_is_rejected(label: str) -> None:
    with pytest.raises(OverlayError):
        normalize_overlay_label(label)
