from __future__ import annotations

import stat
from pathlib import Path

import pytest
from pypdf import PageObject, PdfReader, PdfWriter

from form7_pdf_parser import (
    Overlay,
    OverlayError,
    PdfLimitError,
    PdfReadError,
    annotate_pdf,
    normalize_overlay_label,
)

FIXTURE = Path(__file__).parent / "fixtures" / "synthetic-form7.pdf"


def test_annotate_pdf_adds_sanitized_label_and_uses_owner_only_mode(tmp_path: Path) -> None:
    output = tmp_path / "annotated.pdf"

    annotate_pdf(FIXTURE, output, [Overlay(page_number=1, order_label="Order #6904")])

    reader = PdfReader(output)
    assert len(reader.pages) == 2
    assert "Order #6904" in (reader.pages[0].extract_text() or "")
    assert stat.S_IMODE(output.stat().st_mode) == 0o600


def test_annotate_pdf_isolates_cloned_resources_around_merge(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    original_merge_page = PageObject.merge_page
    original_reset_translation = PdfWriter.reset_translation

    def record_merge(
        page: PageObject,
        overlay: PageObject,
        *args: object,
        **kwargs: object,
    ) -> None:
        events.append("merge")
        original_merge_page(page, overlay, *args, **kwargs)

    def record_reset(writer: PdfWriter, reader: PdfReader) -> None:
        events.append("reset")
        original_reset_translation(writer, reader)

    monkeypatch.setattr(PageObject, "merge_page", record_merge)
    monkeypatch.setattr(PdfWriter, "reset_translation", record_reset)

    annotate_pdf(FIXTURE, tmp_path / "annotated.pdf", [Overlay(1, "SAFE")])

    assert events == ["reset", "merge", "reset"]


def test_annotate_pdf_replaces_readonly_output_atomically(tmp_path: Path) -> None:
    output = tmp_path / "annotated.pdf"
    output.write_text("stale", encoding="utf-8")
    output.chmod(0o400)

    annotate_pdf(FIXTURE, output, [Overlay(page_number=2, order_label="#7")])

    assert output.read_bytes().startswith(b"%PDF-")
    assert stat.S_IMODE(output.stat().st_mode) == 0o600


def test_annotate_pdf_ignores_empty_sanitized_label(tmp_path: Path) -> None:
    output = tmp_path / "annotated.pdf"

    annotate_pdf(FIXTURE, output, [Overlay(page_number=1, order_label="Только текст")])

    assert "Только текст" not in (PdfReader(output).pages[0].extract_text() or "")


@pytest.mark.parametrize(
    "overlays",
    [
        [Overlay(1, "Только текст"), Overlay(1, "SAFE")],
        [Overlay(1, "SAFE"), Overlay(1, "Только текст")],
    ],
)
def test_annotate_pdf_ignores_empty_label_before_duplicate_check(
    tmp_path: Path,
    overlays: list[Overlay],
) -> None:
    output = tmp_path / "annotated.pdf"

    annotate_pdf(FIXTURE, output, overlays)

    assert "SAFE" in (PdfReader(output).pages[0].extract_text() or "")


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
        annotate_pdf(FIXTURE, tmp_path / "output.pdf", [Overlay(1, "A" * 65)])


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
        ("Order #6904", "Order #6904"),
        ("  SAFE / LABEL  ", "SAFE / LABEL"),
        ("Заказ № 6904", "6904"),
        ("Только текст", ""),
        ("", ""),
    ],
)
def test_normalize_overlay_label(label: str, expected: str) -> None:
    assert normalize_overlay_label(label) == expected
