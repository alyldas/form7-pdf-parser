from __future__ import annotations

import json
from itertools import product
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


@pytest.mark.parametrize(
    "text",
    [
        pytest.param(
            "Оплачивается при вручении\n000000\n00\n00000\n0",
            id="split-lines",
        ),
        pytest.param(
            "Оплачивается при вручении 000000 00 00000 0",
            id="inline-groups",
        ),
        pytest.param(
            "Оплачивается при вручении 00000000000000",
            id="compact-inline",
        ),
        pytest.param(
            "Оплачивается при вручении00000000000000",
            id="compact-touching-marker",
        ),
        pytest.param(
            "Оплачивается при вручении\n000000 00\n00000 0",
            id="wrapped-groups",
        ),
        pytest.param(
            "Оплачивается при вручении 000000 00\n00000 0",
            id="mixed-inline-and-wrapped",
        ),
        pytest.param(
            "Оплачивается при вручении 00000000 00000 0",
            id="merged-first-and-second-parts",
        ),
        pytest.param(
            "Оплачивается при вручении 000000 0000000 0",
            id="merged-second-and-third-parts",
        ),
        pytest.param(
            "Оплачивается при вручении 000000 00 000000",
            id="merged-third-and-final-parts",
        ),
        pytest.param(
            "Оплачивается при вручении 000000 00 00000 0100 руб 00 коп",
            id="final-part-merged-with-amount",
        ),
        pytest.param(
            "Оплачивается при вручении\n№ 000000\n00\n00000\n0",
            id="number-labelled-first-part",
        ),
        pytest.param(
            "Оплачивается при\nвручении\n000000 00 00000 0",
            id="two-line-marker",
        ),
        pytest.param(
            "Оплачивается\nпри\nвручении\n000000 00 00000 0",
            id="three-line-marker",
        ),
        pytest.param(
            "Оплачивается при вручении 000000 00 00000 0 100 руб 00 коп",
            id="trailing-amount",
        ),
        pytest.param(
            "Оплачивается при вручении\n160726\n000000\n00\n00000\n0",
            id="numeric-service-line",
        ),
        pytest.param(
            "Оплачивается при вручении 00000 0 0000 0\n000000\n00\n00000\n0",
            id="invalid-inline-then-split",
        ),
        pytest.param(
            "Оплачивается при вручении: данные ниже\nслужебная строка\n000000\n00\n00000\n0",
            id="text-service-line",
        ),
        pytest.param(
            "\n".join(
                [
                    "Оплачивается при вручении: инструкция",
                    *(f"служебная строка {index}" for index in range(10)),
                    "Оплачивается при вручении",
                    "000000 00 00000 0",
                ]
            ),
            id="repeated-marker",
        ),
    ],
)
def test_parse_tracking_number_accepts_supported_layouts(text: str) -> None:
    assert parse_tracking_number(text) == "00000000000000"


def test_parse_tracking_number_accepts_merged_and_labelled_layouts() -> None:
    layouts = (
        layout
        for layout in product(range(5, 8), range(1, 4), range(4, 7), (1,))
        if sum(layout) == 14
    )
    for layout in layouts:
        parts = [str(index) * length for index, length in enumerate(layout, start=1)]
        expected = "".join(parts)
        for boundary in range(3):
            tokens = [
                *parts[:boundary],
                "".join(parts[boundary : boundary + 2]),
                *parts[boundary + 2 :],
            ]

            assert (
                parse_tracking_number(f"Оплачивается при вручении {' '.join(tokens)}") == expected
            )

        assert (
            parse_tracking_number(
                "\n".join(["Оплачивается при вручении", f"№ {parts[0]}", *parts[1:]])
            )
            == expected
        )
        amount_tokens = [*parts[:-1], f"{parts[-1]}100"]
        assert (
            parse_tracking_number(f"Оплачивается при вручении {' '.join(amount_tokens)} руб 00 коп")
            == expected
        )


def test_parse_tracking_number_skips_textual_numeric_service_tail() -> None:
    text = """Оплачивается при вручении 160726 дата
123456
78
90123
4
"""

    assert parse_tracking_number(text) == "12345678901234"


@pytest.mark.parametrize(
    "text",
    [
        "Оплачивается при вручении 123456 78 90123 4 принято",
        "Оплачивается при вручении\n123456\n78\n90123\n4 принято",
    ],
)
def test_parse_tracking_number_accepts_valid_prefix_before_text(text: str) -> None:
    assert parse_tracking_number(text) == "12345678901234"


def test_parse_tracking_number_returns_first_valid_candidate() -> None:
    text = """Оплачивается при вручении
123456 78 90123 4
160726
99
12345
0
"""

    assert parse_tracking_number(text) == "12345678901234"


def test_parse_tracking_number_keeps_earliest_merged_candidate() -> None:
    text = """Оплачивается при вручении
12345678 901234
99
12345
0
"""

    assert parse_tracking_number(text) == "12345678901234"


def test_parse_tracking_number_accepts_amount_word_on_next_line() -> None:
    text = """Оплачивается при вручении 123456 78 90123 4100
руб 00 коп
"""

    assert parse_tracking_number(text) == "12345678901234"


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
        ("+7 900 1234567", "9001234567"),
        ("8 900 1234567", "9001234567"),
        ("+7 (900) 1234567", "9001234567"),
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


@pytest.mark.parametrize("suffix", ["", " получатель", " / получатель", ", получатель"])
def test_parse_recipient_ignores_text_after_merged_phone(suffix: str) -> None:
    lines = [
        "100 руб 00 коп",
        "Тестов Тест Тестович",
        f"000000, г. Примерск +7 (000) 000-00-00{suffix}",
    ]

    assert parse_recipient_name_address_phone(lines) == (
        "Тестов Тест Тестович",
        "000000, г. Примерск",
        "0000000000",
    )


@pytest.mark.parametrize("label", ["Телефон:", "Телефон получателя:", "phone recipient:"])
def test_parse_recipient_strips_phone_label_before_trailing_text(label: str) -> None:
    assert parse_recipient_name_address_phone([f"{label} +7 (000) 000-00-00 получатель"]) == (
        None,
        None,
        "0000000000",
    )


@pytest.mark.parametrize(
    "prefix",
    ["Телегин Иван", "Телефонов Иван", "Телефонная ул.", "phonebook entry"],
)
def test_parse_recipient_preserves_phone_label_prefix_words(prefix: str) -> None:
    lines = [
        "100 руб 00 коп",
        "Тестов Тест Тестович",
        f"{prefix} +7 (000) 000-00-00 получатель",
    ]

    assert parse_recipient_name_address_phone(lines) == (
        "Тестов Тест Тестович",
        prefix,
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


@pytest.mark.parametrize(
    "service_label",
    ["Телефон справочной службы", "Номер заказа", "phone support"],
)
def test_parse_recipient_skips_split_service_phone_before_recipient(
    service_label: str,
) -> None:
    lines = [
        "100 руб 00 коп",
        service_label,
        "+7 (111) 111-11-11",
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
