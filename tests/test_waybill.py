from __future__ import annotations

from io import BytesIO
from itertools import product
from pathlib import Path

import pytest
from pypdf import PdfWriter

from form7_pdf_parser import (
    Overlay,
    PageValidationIssue,
    annotate_pdf,
    parse_page,
    parse_pdf,
    parse_recipient_name_address_phone,
    parse_tracking_number,
)
from form7_pdf_parser.parsing import normalize_lines

FIXTURES = Path(__file__).parent / "fixtures"
WAYBILL_TEXT = (FIXTURES / "synthetic-waybill.txt").read_text(encoding="utf-8")


def test_waybill_extracts_recipient_instead_of_sender() -> None:
    page = parse_page(WAYBILL_TEXT, 1)

    assert page.as_dict() == {
        "page_number": 1,
        "recipient_name": "Получатель Тестовый",
        "recipient_phone": "0000000000",
        "recipient_address": "000000, Россия, г. Примерск, ул. Макетная, д. 0",
        "tracking_number": "00000000000000",
        "raw_text": None,
        "is_valid": True,
    }
    assert page.validation_issues == ()
    assert page.recipient_postcode == "000000"
    assert parse_recipient_name_address_phone(normalize_lines(WAYBILL_TEXT)) == (
        page.recipient_name,
        page.recipient_address,
        page.recipient_phone,
    )


@pytest.mark.parametrize(
    "tracking",
    ["000000 00 00000 0", "00000000000000", "000000\n00\n00000\n0", "000000\t00\u00a000000 0"],
)
def test_waybill_tracking_layouts(tracking: str) -> None:
    text = WAYBILL_TEXT.replace("000000 00 00000 0", tracking)

    assert parse_tracking_number(text) == "00000000000000"


@pytest.mark.parametrize(
    "tracking",
    ["", "0000000000000", "000000000000000", "000000 00 00000 00", "ID 00000000000000"],
)
def test_waybill_rejects_missing_or_malformed_tracking(tracking: str) -> None:
    text = WAYBILL_TEXT.replace("000000 00 00000 0", tracking)
    page = parse_page(text, 1)

    assert page.tracking_number is None
    assert page.is_valid is False
    assert page.validation_issues == (PageValidationIssue.MISSING_TRACKING_NUMBER,)


def test_waybill_rejects_conflicting_tracking_numbers() -> None:
    text = WAYBILL_TEXT.replace("000000 00 00000 0", "000000 00 00000 0\n11111111111111")

    assert parse_tracking_number(text) is None


def test_waybill_accepts_repeated_identical_tracking_number() -> None:
    assert parse_tracking_number("00000000000000\n" + WAYBILL_TEXT) == "00000000000000"


@pytest.mark.parametrize(
    "caption",
    ["Оплачивается при вручении", "Оплачивается\nпри вручении", "Оплачивается\nпри\nвручении"],
)
def test_waybill_has_priority_over_legacy_payment_marker(caption: str) -> None:
    text = WAYBILL_TEXT.replace(
        "Объявленная ценность", f"{caption}\n111111 11 11111 1\n100 руб 00 коп"
    )
    page = parse_page(text, 1)

    assert page.tracking_number == "00000000000000"
    assert page.recipient_name == "Получатель Тестовый"
    assert page.recipient_address == "000000, Россия, г. Примерск, ул. Макетная, д. 0"


def test_waybill_does_not_use_tracking_from_sender_or_recipient() -> None:
    text = WAYBILL_TEXT.replace("000000 00 00000 0\n", "").replace(
        "Объявленная ценность", "Оплачивается при вручении\n111111 11 11111 1"
    )

    assert parse_tracking_number(text + "\n22222222222222") is None


@pytest.mark.parametrize("sender, recipient", [("от кого:", "кому:"), ("От кого", "Кому")])
def test_waybill_accepts_case_and_colon_variants(sender: str, recipient: str) -> None:
    page = parse_page(WAYBILL_TEXT.replace("ОТ КОГО", sender).replace("КОМУ", recipient), 1)

    assert page.is_valid is True
    assert page.recipient_name == "Получатель Тестовый"


def test_waybill_joins_wrapped_recipient_name() -> None:
    page = parse_page(WAYBILL_TEXT.replace("Получатель Тестовый", "Получатель\nТестовый"), 1)

    assert page.recipient_name == "Получатель Тестовый"


def test_waybill_without_recipient_phone_does_not_use_sender_phone() -> None:
    page = parse_page(WAYBILL_TEXT.replace("+7 000 000 0000\n", ""), 1)

    assert page.recipient_phone is None
    assert page.recipient_name == "Получатель Тестовый"
    assert page.recipient_address == "000000, Россия, г. Примерск, ул. Макетная, д. 0"
    assert page.is_valid is False
    assert page.validation_issues == (PageValidationIssue.MISSING_RECIPIENT_PHONE,)


def test_waybill_with_empty_recipient_does_not_fall_back_to_sender() -> None:
    page = parse_page(WAYBILL_TEXT.split("КОМУ")[0] + "КОМУ", 1)

    assert page.recipient_name is None
    assert page.recipient_phone is None
    assert page.recipient_address is None
    assert page.is_valid is False
    assert page.validation_issues == (
        PageValidationIssue.MISSING_RECIPIENT,
        PageValidationIssue.MISSING_RECIPIENT_NAME,
        PageValidationIssue.MISSING_RECIPIENT_PHONE,
        PageValidationIssue.MISSING_RECIPIENT_ADDRESS,
        PageValidationIssue.MISSING_RECIPIENT_POSTCODE,
    )


def test_waybill_phone_only_recipient() -> None:
    page = parse_page(WAYBILL_TEXT.split("КОМУ")[0] + "КОМУ\n+7 000 000 0000", 1)

    assert page.recipient_name is None
    assert page.recipient_phone == "0000000000"
    assert page.recipient_address is None


@pytest.mark.parametrize("postcode", ["000002", ""])
def test_waybill_preserves_distinct_routing_postcode(postcode: str) -> None:
    text = WAYBILL_TEXT.replace("000000, Россия", f"{postcode}, Россия")
    page = parse_page(text, 1)

    assert page.recipient_address == f"{postcode}, Россия, г. Примерск, ул. Макетная, д. 0 000000"


@pytest.mark.parametrize("markers", ["КОМУ\nОТ КОГО", "ОТ КОГО", "КОМУ", ""])
def test_arbitrary_numeric_header_does_not_enable_waybill_tracking(markers: str) -> None:
    assert parse_tracking_number("00000000000000\n" + markers) is None


def test_parse_pdf_supports_mixed_waybill_and_legacy_pages() -> None:
    writer = PdfWriter()
    writer.append(FIXTURES / "synthetic-waybill.pdf")
    writer.append(FIXTURES / "synthetic-form7.pdf")
    stream = BytesIO()
    writer.write(stream)
    stream.seek(0)

    result = parse_pdf(stream)

    assert result.page_count == 3
    assert [page.page_number for page in result.pages] == [1, 2, 3]
    assert result.pages[0].as_dict() == parse_page(WAYBILL_TEXT, 1).as_dict()
    assert result.pages[1].recipient_name == "Тестов Тест Тестович"
    assert result.pages[1].is_valid is True
    assert result.pages[2].is_valid is False
    assert all(page.raw_text is None for page in result.pages)


@pytest.mark.parametrize("label", ["0000", "0000000000"])
def test_waybill_order_annotation_preserves_parsed_fields(tmp_path: Path, label: str) -> None:
    source = FIXTURES / "synthetic-waybill.pdf"
    output = tmp_path / "annotated-waybill.pdf"

    annotate_pdf(source, output, [Overlay(page_number=1, order_label=label)])

    assert parse_pdf(output).as_dict() == parse_pdf(source).as_dict()


def test_waybill_without_phone_ignores_numeric_overlay_after_postcode() -> None:
    text = WAYBILL_TEXT.replace("+7 000 000 0000\n", "")

    assert parse_page(text + "0000000000\n", 1).as_dict() == parse_page(text, 1).as_dict()


@pytest.mark.parametrize(
    "phone",
    ["+7 000\n000 0000", "+7 000\n000\n0000", "+7 (000) 000‑00‑00"],
)
def test_waybill_recovers_split_and_unicode_phone(phone: str) -> None:
    page = parse_page(WAYBILL_TEXT.replace("+7 000 000 0000", phone), 1)

    assert page.as_dict() == parse_page(WAYBILL_TEXT, 1).as_dict()


@pytest.mark.parametrize("prefix", ["Тел.: ", "телефон: ", "PHONE "])
@pytest.mark.parametrize(
    "phone",
    ["+7 000\n000 0000", "8 (000)\n000\n00‑00", "+7000\n0000000", "000\n0000000"],
)
@pytest.mark.parametrize("after_address", [False, True])
def test_waybill_recovers_labelled_wrapped_phone(
    prefix: str, phone: str, after_address: bool
) -> None:
    text = WAYBILL_TEXT.replace("+7 000 000 0000\n", "")
    insertion = "д. 0\n" if after_address else "Получатель Тестовый\n"
    text = text.replace(insertion, insertion + prefix + phone + "\n")

    assert parse_page(text, 1) == parse_page(WAYBILL_TEXT, 1)


@pytest.mark.parametrize("phone", ["Тел.: +7 000", "PHONE +1 000\n000 0000"])
def test_invalid_labelled_phone_preserves_address_and_postcode(phone: str) -> None:
    page = parse_page(WAYBILL_TEXT.replace("+7 000 000 0000", phone), 1)

    assert page.recipient_phone is None
    assert page.recipient_postcode == "000000"
    assert "г. Примерск, ул. Макетная, д. 0" in (page.recipient_address or "")
    assert PageValidationIssue.MISSING_RECIPIENT_PHONE in page.validation_issues


@pytest.mark.parametrize("prefix", ["", "Тел.: "])
def test_wrapped_phone_after_address_does_not_hide_conflicting_postcode(prefix: str) -> None:
    text = WAYBILL_TEXT.replace("+7 000 000 0000\n", "")
    text = text.rsplit("000000\n", 1)[0] + prefix + "+7 0000\n000000\n000002\n"
    page = parse_page(text, 1)

    assert page.recipient_phone == "0000000000"
    assert page.recipient_address == "000000, Россия, г. Примерск, ул. Макетная, д. 0 000002"
    assert page.validation_issues == (PageValidationIssue.CONFLICTING_POSTCODES,)


def test_waybill_incomplete_phone_does_not_consume_address() -> None:
    page = parse_page(WAYBILL_TEXT.replace("+7 000 000 0000", "+7 000"), 1)

    assert page.recipient_phone is None
    assert PageValidationIssue.MISSING_RECIPIENT_PHONE in page.validation_issues
    assert "г. Примерск, ул. Макетная, д. 0" in (page.recipient_address or "")


@pytest.mark.parametrize(
    "block, name, phone, address",
    [
        (
            "Получатель Тестовый\n+7 000 000 0000\n000000\nг. Примерск, д. 0",
            "Получатель Тестовый",
            "0000000000",
            "000000 г. Примерск, д. 0",
        ),
        (
            "Получатель\nТестовый\n000000, г. Примерск, д. 0\n000000",
            None,
            None,
            None,
        ),
        (
            "Получатель Тестовый\n000000, г. Примерск, д. 0\n+7 000 000 0000\n000000",
            "Получатель Тестовый",
            "0000000000",
            "000000, г. Примерск, д. 0",
        ),
        ("000000", None, None, "000000"),
        ("000000, г. Примерск, д. 0\n000000", None, None, "000000, г. Примерск, д. 0"),
    ],
)
def test_waybill_field_boundaries(
    block: str, name: str | None, phone: str | None, address: str | None
) -> None:
    page = parse_page(WAYBILL_TEXT.split("КОМУ")[0] + "КОМУ\n" + block, 1)

    assert (page.recipient_name, page.recipient_phone, page.recipient_address) == (
        name,
        phone,
        address,
    )
    assert page.is_valid is (name is not None and phone is not None)
    if block.startswith("Получатель\nТестовый"):
        assert PageValidationIssue.AMBIGUOUS_RECIPIENT in page.validation_issues


def test_waybill_accepts_inline_section_values() -> None:
    text = WAYBILL_TEXT.replace("ОТ КОГО\n", "ОТ КОГО: ").replace("КОМУ\n", "КОМУ: ")

    assert parse_page(text, 1).as_dict() == parse_page(WAYBILL_TEXT, 1).as_dict()


def test_waybill_without_routing_postcode_ignores_order_label() -> None:
    text = WAYBILL_TEXT.rsplit("000000\n", 1)[0] + "Order #0000\n"

    assert parse_page(text, 1).as_dict() == parse_page(WAYBILL_TEXT, 1).as_dict()


def test_waybill_reports_conflicting_postcodes_without_selecting_one() -> None:
    page = parse_page(WAYBILL_TEXT.replace("000000, Россия", "000002, Россия"), 1)

    assert page.recipient_postcode is None
    assert page.validation_issues == (PageValidationIssue.CONFLICTING_POSTCODES,)
    assert page.is_valid is False
    assert page.recipient_address == "000002, Россия, г. Примерск, ул. Макетная, д. 0 000000"


def test_waybill_reports_conflicting_phones() -> None:
    text = WAYBILL_TEXT.replace("+7 000 000 0000", "+7 000 000 0000\n+7 000 000 0002")
    page = parse_page(text, 1)

    assert page.recipient_phone is None
    assert page.recipient_address == parse_page(WAYBILL_TEXT, 1).recipient_address
    assert PageValidationIssue.AMBIGUOUS_RECIPIENT_PHONE in page.validation_issues
    assert page.is_valid is False


def test_waybill_rejects_multiple_shipments_per_page() -> None:
    text = WAYBILL_TEXT + WAYBILL_TEXT.replace("000000 00 00000 0", "111111 11 11111 1")
    page = parse_page(text, 1)

    assert page.validation_issues == (PageValidationIssue.MULTIPLE_SHIPMENTS,)
    assert page.is_valid is False
    assert page.tracking_number is None
    assert page.recipient_name is None
    assert parse_recipient_name_address_phone(normalize_lines(text)) == (None, None, None)


@pytest.mark.parametrize(
    "caption",
    [
        "Оплачивается при вручении",
        "Оплачивается\nпри вручении",
        "Оплачивается при\nвручении",
        "ОПЛАЧИВАЕТСЯ\nпри\nвручении",
        "Оплачивается\u00a0при\tвручении",
    ],
)
def test_legacy_form_with_section_captions_keeps_previous_behavior(caption: str) -> None:
    text = """Synthetic legacy Form 7
ОТ КОГО
Отправитель Тестовый
КОМУ
Оплачивается при вручении
000000 00 00000 0
100 руб 00 коп
Получатель Тестовый
000000, г. Примерск, д. 0
+7 000 000 0000
"""
    page = parse_page(text.replace("Оплачивается при вручении", caption), 1)

    assert page.is_valid is True
    assert page.validation_issues == ()
    assert page.tracking_number == "00000000000000"
    assert page.recipient_name == "Получатель Тестовый"
    assert page.recipient_phone == "0000000000"
    assert page.recipient_address == "000000, г. Примерск, д. 0"


@pytest.mark.parametrize("block", ["Получатель Тестовый", "+7 000 000 0000"])
def test_waybill_incomplete_fields_are_not_valid(block: str) -> None:
    page = parse_page(WAYBILL_TEXT.split("КОМУ")[0] + "КОМУ\n" + block, 1)

    assert page.is_valid is False
    assert PageValidationIssue.MISSING_RECIPIENT_ADDRESS in page.validation_issues
    assert PageValidationIssue.MISSING_RECIPIENT_POSTCODE in page.validation_issues


def test_waybill_layout_variations() -> None:
    for name, phone, address, tracking, space, markers in product(
        ["Получатель Тестовый", "Тестов\nТест Тестович", "Тестова-Макетная Ёлка", "Ли"],
        ["+7 000 000 0000", "8 (000) 000-00-00", "0000000000", "Тел.: +7 (000) 000-00-00"],
        [
            "000000, г. Примерск, д. 0",
            "000000, г. Примерск,\nул. Макетная,\nд. 0",
            "г. Примерск, д. 0",
        ],
        ["000000 00 00000 0", "00000000000000", "000000\n00\n00000\n0"],
        [" ", "\u00a0", "\t"],
        [("ОТ КОГО", "КОМУ"), ("от кого:", "кому:"), ("От кого", "Кому")],
    ):
        text = WAYBILL_TEXT.split("КОМУ")[0] + f"КОМУ\n{name}\n{phone}\n{address}\n000000\n"
        text = text.replace("000000 00 00000 0", tracking)
        text = text.replace("ОТ КОГО", markers[0]).replace("КОМУ", markers[1]).replace(" ", space)
        page = parse_page(text, 1)
        expected_address = " ".join(address.split())
        if "000000" not in address:
            expected_address += " 000000"

        assert page.recipient_name == " ".join(name.split())
        assert page.recipient_phone == "0000000000"
        assert page.recipient_address == expected_address
        assert page.recipient_postcode == "000000"
        assert page.tracking_number == "00000000000000"
        assert page.is_valid is True


@pytest.mark.parametrize(
    "address",
    [
        "Москва\nСНТ Ромашка",
        "аул Примерный\nтерритория Садовая",
        "Example locality\nExample street",
    ],
)
def test_waybill_address_does_not_require_a_place_name_dictionary(address: str) -> None:
    block = f"Получатель Тестовый\n+7 000 000 0000\n{address}\n000000"
    page = parse_page(WAYBILL_TEXT.split("КОМУ")[0] + "КОМУ\n" + block, 1)

    assert page.recipient_name == "Получатель Тестовый"
    assert page.recipient_address == " ".join(address.splitlines()) + " 000000"
    assert page.recipient_postcode == "000000"
    assert page.is_valid is True


def test_waybill_unlabelled_name_address_boundary_is_ambiguous() -> None:
    block = "Получатель Тестовый\nМосква\nСНТ Ромашка\n000000"
    page = parse_page(WAYBILL_TEXT.split("КОМУ")[0] + "КОМУ\n" + block, 1)

    assert page.recipient_name is None
    assert page.recipient_address is None
    assert PageValidationIssue.AMBIGUOUS_RECIPIENT in page.validation_issues
    assert page.is_valid is False


@pytest.mark.parametrize("phone", ["", "+7 000 000 0000\n"])
@pytest.mark.parametrize("locality", ["Москва", "аул Примерный", "Example locality"])
@pytest.mark.parametrize("street", ["ул. Макетная, д. 1", "000000, ул. Макетная, д. 1"])
def test_waybill_ambiguous_prefix_is_not_accepted_as_part_of_name(
    phone: str, locality: str, street: str
) -> None:
    block = f"Получатель Тестовый\n{locality}\n{street}\n{phone}000000"
    page = parse_page(WAYBILL_TEXT.split("КОМУ")[0] + "КОМУ\n" + block, 1)

    assert page.is_valid is False
    assert PageValidationIssue.AMBIGUOUS_RECIPIENT in page.validation_issues
    assert page.recipient_name is None
    assert page.recipient_address is None
    assert page.recipient_phone == ("0000000000" if phone else None)


@pytest.mark.parametrize(
    "prefix,label,after_address",
    [
        (prefix, label, after_address)
        for prefix, label, after_address in product(
            ["+7", "7", "8"], ["", "Тел.: ", "PHONE "], [False, True]
        )
        # After the address, six bare digits are a routing postcode; an explicit
        # plus or label is needed to distinguish every possible phone partition.
        if not (after_address and prefix in {"7", "8"} and not label)
    ],
)
def test_country_prefixed_phone_all_line_partitions(
    label: str, prefix: str, after_address: bool
) -> None:
    expected = parse_page(WAYBILL_TEXT, 1)
    # All 1,024 partitions after the prefix and between subscriber digits.
    for breaks in product((False, True), repeat=10):
        phone = label + prefix + "".join("\n0" if split else "0" for split in breaks)
        text = WAYBILL_TEXT.replace("+7 000 000 0000\n", "")
        insertion = "д. 0\n" if after_address else "Получатель Тестовый\n"
        actual = parse_page(text.replace(insertion, insertion + phone + "\n"), 1)
        assert actual == expected, (prefix, label, breaks)


@pytest.mark.parametrize("label", ["Тел.: ", "PHONE "])
@pytest.mark.parametrize("number", ["0000000000", "7000000000", "8000000000"])
def test_labelled_national_phone_all_line_partitions(label: str, number: str) -> None:
    expected = parse_page(WAYBILL_TEXT.replace("+7 000 000 0000", number), 1)
    # All 512 partitions, including compact national numbers beginning in 7/8.
    for breaks in product((False, True), repeat=9):
        phone = (
            label
            + number[0]
            + "".join(
                ("\n" if split else "") + digit
                for split, digit in zip(breaks, number[1:], strict=True)
            )
        )
        actual = parse_page(WAYBILL_TEXT.replace("+7 000 000 0000", phone), 1)
        assert actual == expected, (number, label, breaks)


@pytest.mark.parametrize("footer", ["0000", "00000", "0000000000"])
def test_routing_postcode_is_not_joined_to_numeric_footer(footer: str) -> None:
    text = WAYBILL_TEXT.rsplit("000000\n", 1)[0] + "800000\n"

    assert parse_page(text + footer + "\n", 1) == parse_page(text, 1)


def test_bare_six_digit_line_after_address_remains_a_postcode() -> None:
    text = WAYBILL_TEXT.replace("+7 000 000 0000\n", "")
    text = text.rsplit("000000\n", 1)[0] + "800000\n00000\n"
    page = parse_page(text, 1)

    assert page.recipient_phone is None
    assert page.recipient_address == "000000, Россия, г. Примерск, ул. Макетная, д. 0 800000"
    assert PageValidationIssue.MISSING_RECIPIENT_PHONE in page.validation_issues
    assert PageValidationIssue.CONFLICTING_POSTCODES in page.validation_issues


@pytest.mark.parametrize("prefix", ["+7 ", "7 ", "8 ", "7-", "8-", "7(", "8("])
@pytest.mark.parametrize("label", ["", "Тел.: "])
def test_formatted_country_prefix_survives_line_breaks(prefix: str, label: str) -> None:
    number = prefix + "000" + (")" if prefix.endswith("(") else "") + "\n000\n0000"

    assert parse_page(WAYBILL_TEXT.replace("+7 000 000 0000", label + number), 1) == parse_page(
        WAYBILL_TEXT, 1
    )
