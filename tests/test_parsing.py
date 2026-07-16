from __future__ import annotations

import json
from pathlib import Path

import pytest

from form7_pdf_parser import PageValidationIssue
from form7_pdf_parser.parsing import (
    normalize_lines,
    parse_page,
    parse_recipient_name_address_phone,
    parse_tracking_number,
)

PARSING_CASES = json.loads(
    (Path(__file__).parent / "fixtures" / "parsing-cases.json").read_text(encoding="utf-8")
)

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
    assert page.validation_issues == ()


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


def test_parse_tracking_number_supports_inline_digits() -> None:
    text = "Оплачивается при вручении 000000 00 00000 0"

    assert parse_tracking_number(text) == "00000000000000"


def test_parse_tracking_number_supports_compact_inline_digits() -> None:
    text = "Оплачивается при вручении 00000000000000"

    assert parse_tracking_number(text) == "00000000000000"


def test_parse_tracking_number_supports_wrapped_group_lines() -> None:
    text = """Оплачивается при вручении
000000 00
00000 0
"""

    assert parse_tracking_number(text) == "00000000000000"


def test_parse_tracking_number_supports_mixed_inline_and_wrapped_groups() -> None:
    text = """Оплачивается при вручении 000000 00
00000 0
"""

    assert parse_tracking_number(text) == "00000000000000"


@pytest.mark.parametrize(
    "marker",
    [
        "Оплачивается при\nвручении",
        "Оплачивается\nпри\nвручении",
    ],
)
def test_parse_tracking_number_supports_wrapped_marker(marker: str) -> None:
    text = f"{marker}\n000000 00 00000 0"

    assert parse_tracking_number(text) == "00000000000000"


def test_parse_tracking_number_accepts_trailing_amount_text() -> None:
    text = "Оплачивается при вручении 000000 00 00000 0 100 руб 00 коп"

    assert parse_tracking_number(text) == "00000000000000"


def test_parse_tracking_number_skips_numeric_service_line() -> None:
    text = """Оплачивается при вручении
160726
000000
00
00000
0
"""

    assert parse_tracking_number(text) == "00000000000000"


def test_parse_tracking_number_falls_through_after_invalid_inline_candidate() -> None:
    text = """Оплачивается при вручении 00000 0 0000 0
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


def test_parse_tracking_number_continues_after_marker_without_digits() -> None:
    text = "\n".join(
        [
            "Оплачивается при вручении: инструкция",
            *(f"служебная строка {index}" for index in range(10)),
            "Оплачивается при вручении",
            "000000 00 00000 0",
        ]
    )

    assert parse_tracking_number(text) == "00000000000000"


def test_parse_tracking_number_rejects_non_fourteen_digit_candidate() -> None:
    text = "Оплачивается при вручении 00000 0 0000 0"

    assert parse_tracking_number(text) is None


def test_parse_tracking_number_rejects_invalid_split_part_lengths() -> None:
    text = """Оплачивается при вручении: данные ниже
0000
00
00000
0
"""

    assert parse_tracking_number(text) is None


def test_parse_recipient_returns_phone_when_name_block_is_empty() -> None:
    assert parse_recipient_name_address_phone(["+7 (000) 000-00-00"]) == (
        None,
        None,
        "0000000000",
    )


@pytest.mark.parametrize(
    ("line", "expected_phone"),
    [
        ("+70000000000", "0000000000"),
        ("70000000000", "0000000000"),
        ("80000000000", "0000000000"),
        ("8 0000000000", "0000000000"),
        ("+7(000)0000000", "0000000000"),
        ("+7 (000) 000-0000", "0000000000"),
        ("+7 000 000 0000", "0000000000"),
        ("000.000.00.00", "0000000000"),
        ("000 000 0000", "0000000000"),
        ("7 000 000 0000", "0000000000"),
        ("8 000 000 0000", "0000000000"),
        ("8-000-000-0000", "0000000000"),
        ("+7 (000) 000‑00‑00", "0000000000"),
        ("+7 (000) 000–00–00", "0000000000"),
        ("+7 (000) 000−00−00", "0000000000"),
        ("Телефон: 0000000000", "0000000000"),
        ("Телефон получателя +7 (000) 000-00-00", "0000000000"),
        ("0000000000", None),
        ("60000000000", None),
        ("71234567890123", None),
        ("123456, 12, 34", None),
        ("Телефон справочной службы +70000000000", None),
        ("phone support +70000000000", None),
    ],
)
def test_parse_recipient_classifies_phone_candidate(
    line: str,
    expected_phone: str | None,
) -> None:
    assert parse_recipient_name_address_phone([line]) == (None, None, expected_phone)


def test_parse_recipient_preserves_address_merged_with_phone() -> None:
    lines = [
        "100 руб 00 коп",
        "Тестов Тест Тестович",
        "000000, г. Примерск +7 (000) 000-00-00",
    ]

    assert parse_recipient_name_address_phone(lines) == (
        "Тестов Тест Тестович",
        "000000, г. Примерск",
        "0000000000",
    )


@pytest.mark.parametrize("suffix", ["получатель", "/ получатель", ", получатель"])
def test_parse_recipient_ignores_text_after_merged_phone(suffix: str) -> None:
    lines = [
        "100 руб 00 коп",
        "Тестов Тест Тестович",
        f"000000, г. Примерск +7 (000) 000-00-00 {suffix}",
    ]

    assert parse_recipient_name_address_phone(lines) == (
        "Тестов Тест Тестович",
        "000000, г. Примерск",
        "0000000000",
    )


@pytest.mark.parametrize(
    "service_line",
    [
        "Номер заказа +7 111 111 1111",
        "Код заявки 8 (111) 111-11-11",
        "Телефон справочной службы +7 (111) 111-11-11",
    ],
)
def test_parse_recipient_skips_phone_shaped_service_line_before_recipient(
    service_line: str,
) -> None:
    lines = [
        "100 руб 00 коп",
        service_line,
        "Тестов Тест Тестович",
        "000000, г. Примерск",
        "+7 (000) 000-00-00",
    ]

    assert parse_recipient_name_address_phone(lines) == (
        "Тестов Тест Тестович",
        "000000, г. Примерск",
        "0000000000",
    )


def test_parse_recipient_preserves_name_that_starts_like_order_label() -> None:
    lines = [
        "100 руб 00 коп",
        "Заказов Заказ Заказович",
        "000000, г. Примерск",
        "+7 (000) 000-00-00",
    ]

    assert parse_recipient_name_address_phone(lines) == (
        "Заказов Заказ Заказович",
        "000000, г. Примерск",
        "0000000000",
    )


def test_parse_page_handles_all_reviewed_extraction_artifacts_together() -> None:
    text = "\n".join(
        [
            "Оплачивается при вручении: инструкция",
            *(f"служебная строка {index}" for index in range(10)),
            "Оплачивается при вручении",
            "000000 00 00000 0",
            "100 руб 00 коп",
            "Номер заказа +7 111 111 1111",
            "Тестов Тест Тестович",
            "000000, г. Примерск +7 (000) 000-00-00 получатель",
        ]
    )

    page = parse_page(text, 1)

    assert page.recipient_name == "Тестов Тест Тестович"
    assert page.recipient_address == "000000, г. Примерск"
    assert page.recipient_phone == "0000000000"
    assert page.tracking_number == "00000000000000"
    assert page.is_valid is True


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
    assert page.validation_issues == (
        PageValidationIssue.MISSING_TRACKING_NUMBER,
        PageValidationIssue.MISSING_RECIPIENT,
    )


@pytest.mark.parametrize("case", PARSING_CASES, ids=lambda case: case["name"])
def test_synthetic_parsing_matrix(case: dict[str, object]) -> None:
    expected = case["expected"]
    assert isinstance(expected, dict)

    page = parse_page(str(case["text"]), 1)

    assert page.recipient_name == expected["recipient_name"]
    assert page.recipient_address == expected["recipient_address"]
    assert page.recipient_phone == expected["recipient_phone"]
    assert page.tracking_number == expected["tracking_number"]
    assert page.is_valid is expected["is_valid"]
    assert page.validation_issues == tuple(
        PageValidationIssue(issue) for issue in expected["validation_issues"]
    )


def test_normalize_lines_removes_blank_lines_and_compacts_whitespace() -> None:
    assert normalize_lines("  First   line\n\nSecond\tline  ") == ["First line", "Second line"]


def test_page_number_must_be_positive() -> None:
    with pytest.raises(ValueError, match="page_number"):
        parse_page(VALID_PAGE_TEXT, 0)
