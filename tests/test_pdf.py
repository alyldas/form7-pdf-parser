from __future__ import annotations

from io import BytesIO, UnsupportedOperation
from pathlib import Path

import pytest
from pypdf import PdfWriter

from form7_pdf_parser import PdfLimitError, PdfReadError, parse_pdf
from form7_pdf_parser.pdf import enforce_source_size

FIXTURE = Path(__file__).parent / "fixtures" / "synthetic-form7.pdf"


class NonSeekableStream(BytesIO):
    def seekable(self) -> bool:
        return False

    def seek(self, offset: int, whence: int = 0) -> int:
        raise UnsupportedOperation

    def tell(self) -> int:
        raise UnsupportedOperation


def test_parse_pdf_reads_synthetic_fixture() -> None:
    result = parse_pdf(FIXTURE)

    assert result.page_count == 2
    assert result.pages[0].recipient_name == "Тестов Тест Тестович"
    assert result.pages[0].recipient_phone == "0000000000"
    assert result.pages[0].tracking_number == "00000000000000"
    assert result.pages[0].raw_text is None
    assert result.pages[0].is_valid is True
    assert result.pages[1].is_valid is False


def test_parse_pdf_can_opt_in_to_raw_text() -> None:
    result = parse_pdf(FIXTURE, include_raw_text=True)

    assert result.pages[0].raw_text is not None
    assert "Оплачивается при вручении" in result.pages[0].raw_text


def test_parse_pdf_supports_binary_streams() -> None:
    stream = BytesIO(FIXTURE.read_bytes())

    result = parse_pdf(stream)

    assert result.page_count == 2


def test_parse_pdf_spools_non_seekable_stream_within_limit() -> None:
    payload = FIXTURE.read_bytes()

    result = parse_pdf(NonSeekableStream(payload), max_file_size=len(payload))

    assert result.page_count == 2


def test_parse_pdf_enforces_size_limit_for_non_seekable_stream() -> None:
    payload = FIXTURE.read_bytes()

    with pytest.raises(PdfLimitError, match="size limit"):
        parse_pdf(NonSeekableStream(payload), max_file_size=len(payload) - 1)


def test_enforce_source_size_allows_unknown_non_seekable_size() -> None:
    enforce_source_size(NonSeekableStream(b"larger than the limit"), max_file_size=1)


def test_parse_pdf_enforces_page_limit() -> None:
    with pytest.raises(PdfLimitError, match="page limit"):
        parse_pdf(FIXTURE, max_pages=1)


def test_parse_pdf_enforces_file_size_limit() -> None:
    with pytest.raises(PdfLimitError, match="size limit"):
        parse_pdf(FIXTURE, max_file_size=1)


def test_parse_pdf_rejects_invalid_limits() -> None:
    with pytest.raises(ValueError, match="max_pages"):
        parse_pdf(FIXTURE, max_pages=0)
    with pytest.raises(ValueError, match="max_file_size"):
        parse_pdf(FIXTURE, max_file_size=0)


def test_parse_pdf_rejects_encrypted_input(tmp_path: Path) -> None:
    encrypted = tmp_path / "encrypted.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.encrypt("synthetic-password")
    with encrypted.open("wb") as handle:
        writer.write(handle)

    with pytest.raises(PdfReadError, match="Encrypted"):
        parse_pdf(encrypted)


def test_parse_pdf_wraps_invalid_pdf_errors(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid.pdf"
    invalid.write_text("not a pdf", encoding="utf-8")

    with pytest.raises(PdfReadError, match="Unable to read"):
        parse_pdf(invalid)
