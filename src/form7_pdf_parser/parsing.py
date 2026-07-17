from __future__ import annotations

import re

from .models import PageValidationIssue, ParsedPage

_TRACKING_MARKER = "Оплачивается при вручении"
_TRACKING_PATTERN = re.compile(
    r"Оплачивается\s+при\s+вручении\s*"
    r"([0-9]{5,7})\s*([0-9]{1,3})\s*([0-9]{4,6})\s*([0-9])",
    flags=re.IGNORECASE | re.DOTALL,
)
_AMOUNT_PATTERN = re.compile(r"\b(?:руб|коп)\b", flags=re.IGNORECASE)
_PHONE_LINE_PATTERN = re.compile(
    r"(?:(?:тел(?:ефон)?|phone)\.?\s*:?\s*)?\+?[0-9()\-\s]+",
    flags=re.IGNORECASE,
)
_TRACKING_FRAGMENT_PATTERN = re.compile(r"[0-9][0-9\s-]*")
_TRACKING_GROUP_LENGTHS = ((5, 7), (1, 3), (4, 6), (1, 1))


def normalize_lines(text: str) -> list[str]:
    return [line for raw in text.splitlines() if (line := re.sub(r"\s+", " ", raw).strip())]


def _valid_tracking_number(parts: list[str] | tuple[str, ...]) -> str | None:
    if len(parts) != len(_TRACKING_GROUP_LENGTHS):
        return None
    if any(
        not minimum <= len(part) <= maximum
        for part, (minimum, maximum) in zip(parts, _TRACKING_GROUP_LENGTHS, strict=True)
    ):
        return None

    candidate = "".join(parts)
    return candidate if len(candidate) == 14 and candidate.isdigit() else None


def parse_tracking_number(text: str, lines: list[str] | None = None) -> str | None:
    """Best-effort extraction of one unambiguous 14-digit tracking number."""
    direct_candidates = {
        candidate
        for match in _TRACKING_PATTERN.finditer(text)
        if (candidate := _valid_tracking_number(match.groups())) is not None
    }
    if direct_candidates:
        return next(iter(direct_candidates)) if len(direct_candidates) == 1 else None

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
        if _TRACKING_FRAGMENT_PATTERN.fullmatch(line) is None:
            continue
        digits = re.sub(r"\D+", "", line)
        if re.fullmatch(r"\d{1,7}", digits or ""):
            parts.append(digits)

    candidates: set[str] = set()
    for start in range(len(parts) - len(_TRACKING_GROUP_LENGTHS) + 1):
        candidate = _valid_tracking_number(parts[start : start + len(_TRACKING_GROUP_LENGTHS)])
        if candidate is not None:
            candidates.add(candidate)

    return next(iter(candidates)) if len(candidates) == 1 else None


def _parse_phone_line(line: str) -> str | None:
    if _PHONE_LINE_PATTERN.fullmatch(line) is None:
        return None

    digits = re.sub(r"\D+", "", line)
    if "+" in line and not digits.startswith("7"):
        return None
    if len(digits) == 11 and digits[0] in "78":
        return digits[-10:]
    if len(digits) == 10:
        return digits
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
    """Best-effort extraction of the recipient block ending in a supported phone line."""
    phone_index: int | None = None
    phone_digits: str | None = None

    for index in range(len(lines) - 1, -1, -1):
        phone_digits = _parse_phone_line(lines[index])
        if phone_digits is not None:
            phone_index = index
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
    """Parse normalized fields and validation diagnostics from one extracted text page."""
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
