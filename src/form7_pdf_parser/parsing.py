from __future__ import annotations

import re

from .models import ParsedPage

_TRACKING_MARKER = "Оплачивается при вручении"
_TRACKING_PATTERN = re.compile(
    r"Оплачивается\s+при\s+вручении\s*"
    r"([0-9]{5,7})\s*([0-9]{1,3})\s*([0-9]{4,6})\s*([0-9])",
    flags=re.IGNORECASE | re.DOTALL,
)
_AMOUNT_PATTERN = re.compile(r"\b(?:руб|коп)\b", flags=re.IGNORECASE)


def normalize_lines(text: str) -> list[str]:
    return [line for raw in text.splitlines() if (line := re.sub(r"\s+", " ", raw).strip())]


def _valid_tracking_number(parts: list[str] | tuple[str, ...]) -> str | None:
    candidate = "".join(parts)
    return candidate if len(candidate) == 14 and candidate.isdigit() else None


def parse_tracking_number(text: str, lines: list[str] | None = None) -> str | None:
    match = _TRACKING_PATTERN.search(text)
    if match:
        return _valid_tracking_number(match.groups())

    normalized_lines = lines if lines is not None else normalize_lines(text)
    marker_index = next(
        (
            index
            for index, line in enumerate(normalized_lines)
            if _TRACKING_MARKER.casefold() in line.casefold()
        ),
        None,
    )
    if marker_index is None:
        return None

    parts: list[str] = []
    for line in normalized_lines[marker_index + 1 : marker_index + 10]:
        digits = re.sub(r"\D+", "", line)
        if re.fullmatch(r"\d{1,7}", digits or ""):
            parts.append(digits)
            if len(parts) >= 4:
                return _valid_tracking_number(parts[:4])

    return None


def _join_lines(lines: list[str]) -> str | None:
    compact = re.sub(r"\s+", " ", " ".join(line.strip() for line in lines if line.strip()))
    return compact.strip() or None


def _find_amount_line(lines: list[str], phone_index: int, search_start: int) -> int | None:
    for index in range(phone_index - 1, search_start - 1, -1):
        if _AMOUNT_PATTERN.search(lines[index]):
            return index
    return None


def parse_recipient_name_address_phone(
    lines: list[str],
) -> tuple[str | None, str | None, str | None]:
    phone_index: int | None = None
    phone_digits: str | None = None

    for index in range(len(lines) - 1, -1, -1):
        digits = re.sub(r"\D+", "", lines[index])
        if len(digits) in (10, 11):
            phone_index = index
            phone_digits = digits[-10:]
            break

    if phone_index is None or phone_digits is None:
        return None, None, None

    search_start = max(phone_index - 8, 0)
    amount_index = _find_amount_line(lines, phone_index, search_start)
    recipient_block = (
        lines[amount_index + 1 : phone_index]
        if amount_index is not None
        else lines[search_start:phone_index]
    )

    if not recipient_block:
        return None, None, phone_digits

    return recipient_block[0], _join_lines(recipient_block[1:]), phone_digits


def parse_page(text: str, page_number: int, *, include_raw_text: bool = False) -> ParsedPage:
    if page_number < 1:
        raise ValueError("page_number must be at least 1")

    lines = normalize_lines(text)
    tracking_number = parse_tracking_number(text, lines)
    recipient_name, recipient_address, recipient_phone = parse_recipient_name_address_phone(lines)

    return ParsedPage(
        page_number=page_number,
        recipient_name=recipient_name,
        recipient_phone=recipient_phone,
        recipient_address=recipient_address,
        tracking_number=tracking_number,
        raw_text=text.strip() or None if include_raw_text else None,
        is_valid=tracking_number is not None
        and (recipient_name is not None or recipient_phone is not None),
    )
