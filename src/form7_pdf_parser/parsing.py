from __future__ import annotations

import re

from .models import PageValidationIssue, ParsedPage

_TRACKING_MARKER = "Оплачивается при вручении"
_TRACKING_PATTERN = re.compile(
    r"Оплачивается\s+при\s+вручении\s*"
    r"([0-9]{5,7})\s*([0-9]{1,3})\s*([0-9]{4,6})\s*([0-9])",
    flags=re.IGNORECASE | re.DOTALL,
)
_TRACKING_PART_LENGTHS = ((5, 7), (1, 3), (4, 6), (1, 1))
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
        digits = re.sub(r"\s+", "", line) if re.fullmatch(r"[0-9\s]+", line) else ""
        if re.fullmatch(r"\d{1,7}", digits):
            parts.append(digits)

    for start in range(len(parts) - 3):
        candidate_parts = parts[start : start + 4]
        if all(
            minimum <= len(part) <= maximum
            for part, (minimum, maximum) in zip(
                candidate_parts,
                _TRACKING_PART_LENGTHS,
                strict=True,
            )
        ):
            return _valid_tracking_number(candidate_parts)

    return None


def _join_lines(lines: list[str]) -> str | None:
    compact = re.sub(r"\s+", " ", " ".join(line.strip() for line in lines if line.strip()))
    return compact.strip() or None


def _phone_digits(line: str) -> str | None:
    digits = re.sub(r"\D+", "", line)
    return digits[-10:] if len(digits) in (10, 11) else None


def _find_recipient_phone(lines: list[str]) -> tuple[int, str, int | None] | None:
    for amount_index in range(len(lines) - 1, -1, -1):
        if not _AMOUNT_PATTERN.search(lines[amount_index]):
            continue

        for phone_index in range(amount_index + 1, min(amount_index + 9, len(lines))):
            if phone_digits := _phone_digits(lines[phone_index]):
                return phone_index, phone_digits, amount_index

    for phone_index in range(len(lines) - 1, -1, -1):
        if phone_digits := _phone_digits(lines[phone_index]):
            return phone_index, phone_digits, None

    return None


def _trim_tracking_preamble(lines: list[str]) -> list[str]:
    marker_index = next(
        (
            index
            for index in range(len(lines) - 1, -1, -1)
            if _TRACKING_MARKER.casefold() in lines[index].casefold()
        ),
        None,
    )
    if marker_index is None:
        return lines

    candidate_lines = lines[marker_index + 1 :]
    tracking_digits = 0
    for index, line in enumerate(candidate_lines):
        if re.fullmatch(r"[0-9\s]+", line):
            tracking_digits += len(re.sub(r"\s+", "", line))
            if tracking_digits >= 14:
                return candidate_lines[index + 1 :]
        elif tracking_digits:
            return candidate_lines[index:]

    return candidate_lines


def parse_recipient_name_address_phone(
    lines: list[str],
) -> tuple[str | None, str | None, str | None]:
    phone_match = _find_recipient_phone(lines)
    if phone_match is None:
        return None, None, None

    phone_index, phone_digits, amount_index = phone_match
    search_start = max(phone_index - 8, 0)
    recipient_block = (
        lines[amount_index + 1 : phone_index]
        if amount_index is not None
        else _trim_tracking_preamble(lines[search_start:phone_index])
    )

    if not recipient_block:
        return None, None, phone_digits

    return recipient_block[0], _join_lines(recipient_block[1:]), phone_digits


def _page_validation_issues(
    tracking_number: str | None,
    recipient_name: str | None,
    recipient_phone: str | None,
) -> tuple[PageValidationIssue, ...]:
    issues: list[PageValidationIssue] = []
    if tracking_number is None:
        issues.append(PageValidationIssue.MISSING_TRACKING_NUMBER)
    if recipient_name is None and recipient_phone is None:
        issues.append(PageValidationIssue.MISSING_RECIPIENT)
    return tuple(issues)


def parse_page(text: str, page_number: int, *, include_raw_text: bool = False) -> ParsedPage:
    if page_number < 1:
        raise ValueError("page_number must be at least 1")

    lines = normalize_lines(text)
    tracking_number = parse_tracking_number(text, lines)
    recipient_name, recipient_address, recipient_phone = parse_recipient_name_address_phone(lines)
    validation_issues = _page_validation_issues(
        tracking_number,
        recipient_name,
        recipient_phone,
    )

    return ParsedPage(
        page_number=page_number,
        recipient_name=recipient_name,
        recipient_phone=recipient_phone,
        recipient_address=recipient_address,
        tracking_number=tracking_number,
        raw_text=text.strip() or None if include_raw_text else None,
        is_valid=not validation_issues,
        validation_issues=validation_issues,
    )
