from __future__ import annotations

import pytest

from form7_pdf_parser import parse_page, parse_recipient_name_address_phone
from form7_pdf_parser.parsing import normalize_lines, parse_tracking_number

VALID_PAGE_TEXT = """Synthetic Form 7 fixture
Оплачивается при вручении
000000 00 00000 0
100 руб 00 коп
Тестов Тест Тестович
000000, г. Примерск, ул. Макетная,
д. 0
+7 (000) 000-00-00
"""


def test_parse_page_extracts_synthetic_recipient_without_raw_text() -> None:
    page = parse_page(VALID_PAGE_TEXT, 1)

    assert page.page_number == 1
    assert page.recipient_name == "Тестов Тест Тестович"
    assert page.recipient_address == "000000, г. Примерск, ул. Макетная, д. 0"
    assert page.recipient_phone == "0000000000"
    assert page.tracking_number == "00000000000000"
    assert page.raw_text is None
    assert page.is_valid is True


def test_parse_page_includes_raw_text_only_when_requested() -> None:
    page = parse_page(VALID_PAGE_TEXT, 1, include_raw_text=True)

    assert page.raw_text == VALID_PAGE_TEXT.strip()


def test_parse_tracking_number_supports_split_digit_lines() -> None:
    text = """Оплачивается при вручении
000000
00
00000
0
"""

    assert parse_tracking_number(text) == "00000000000000"


def test_parse_tracking_number_uses_bounded_line_fallback() -> None:
    text = """Оплачивается при вручении: данные ниже
служебная строка
000000
00
00000
0
"""

    assert parse_tracking_number(text) == "00000000000000"


def test_parse_tracking_number_rejects_non_fourteen_digit_candidate() -> None:
    text = "Оплачивается при вручении 00000 0 0000 0"

    assert parse_tracking_number(text) is None


def test_parse_recipient_returns_phone_when_name_block_is_empty() -> None:
    assert parse_recipient_name_address_phone(["+7 (000) 000-00-00"]) == (
        None,
        None,
        "0000000000",
    )


def test_invalid_page_has_stable_null_fields() -> None:
    page = parse_page("Synthetic page without shipping data", 2)

    assert page.as_dict() == {
        "page_number": 2,
        "recipient_name": None,
        "recipient_phone": None,
        "recipient_address": None,
        "tracking_number": None,
        "raw_text": None,
        "is_valid": False,
    }


def test_normalize_lines_removes_blank_lines_and_compacts_whitespace() -> None:
    assert normalize_lines("  First   line\n\nSecond\tline  ") == ["First line", "Second line"]


def test_page_number_must_be_positive() -> None:
    with pytest.raises(ValueError, match="page_number"):
        parse_page(VALID_PAGE_TEXT, 0)
